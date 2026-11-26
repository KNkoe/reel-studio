// Blur private on-screen text in moving footage, using Apple Vision OCR (on-device).
//
//   redact render <in.mp4> <rules.json> <out-silent.mp4>   OCR, then blur matches
//   redact scan   <in.mp4> <rules.json>                    report matches still legible
//
// rules.json: {"step": 2, "hold": 8,
//              "rules": [{"regex": "…", "band": false, "pad": 14}]}
// band=true blurs the full-width strip at the match's height (browser tab/bookmark rows,
// where one recognised word gives away that the rest of the row is private too).
// "hold" keeps each box for N frames either side, covering frames where OCR misses.
import AVFoundation
import CoreImage
import Foundation
import Vision

struct Rule: Decodable { let regex: String; let band: Bool?; let pad: Double? }
struct Config: Decodable { let step: Int?; let hold: Int?; let rules: [Rule] }

let args = CommandLine.arguments
guard args.count >= 4, ["render", "scan"].contains(args[1]), args[1] == "scan" || args.count >= 5 else {
    print("usage: redact render|scan <in> <rules.json> [out]"); exit(2)
}
let mode = args[1]
let input = URL(fileURLWithPath: args[2])
let config = try JSONDecoder().decode(Config.self, from: Data(contentsOf: URL(fileURLWithPath: args[3])))
let rules = try config.rules.map { (try NSRegularExpression(pattern: $0.regex, options: [.caseInsensitive]), $0) }
let step = max(1, config.step ?? 2)
let hold = config.hold ?? 8
let context = CIContext()

func openReader() async throws -> (AVAssetReader, AVAssetReaderTrackOutput, CGSize, Float) {
    let asset = AVURLAsset(url: input)
    let track = try await asset.loadTracks(withMediaType: .video)[0]
    let size = try await track.load(.naturalSize)
    let fps = try await track.load(.nominalFrameRate)
    let reader = try AVAssetReader(asset: asset)
    let output = AVAssetReaderTrackOutput(track: track, outputSettings:
        [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
    reader.add(output)
    reader.startReading()
    return (reader, output, size, fps)
}

// Boxes are in Core Image coordinates (origin bottom-left, pixels).
func matches(_ buffer: CVPixelBuffer, _ size: CGSize) throws -> [(CGRect, String)] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.minimumTextHeight = 0.006
    try VNImageRequestHandler(cvPixelBuffer: buffer, options: [:]).perform([request])
    var found: [(CGRect, String)] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let text = candidate.string
        for (regex, rule) in rules {
            for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
                guard let range = Range(match.range, in: text) else { continue }
                let normal = (try? candidate.boundingBox(for: range))?.boundingBox ?? observation.boundingBox
                let pad = rule.pad ?? 14
                var box = VNImageRectForNormalizedRect(normal, Int(size.width), Int(size.height))
                    .insetBy(dx: -pad, dy: -pad)
                if rule.band == true { box.origin.x = 0; box.size.width = size.width }
                found.append((box.intersection(CGRect(origin: .zero, size: size)), text))
            }
        }
    }
    return found
}

var perFrame: [Int: [CGRect]] = [:]
var count = 0
do {
    let (reader, output, size, fps) = try await openReader()
    defer { withExtendedLifetime(reader) {} }
    var hits = 0
    while let sample = output.copyNextSampleBuffer() {
        if count % (mode == "scan" ? 3 : step) == 0, let buffer = CMSampleBufferGetImageBuffer(sample) {
            try autoreleasepool {
                let found = try matches(buffer, size)
                if !found.isEmpty {
                    perFrame[count] = found.map { $0.0 }
                    if mode == "scan" {
                        hits += 1
                        print(String(format: "%7.2fs  %@", Double(count) / Double(fps), found.map { $0.1 }.joined(separator: " | ")))
                    }
                }
            }
        }
        count += 1
        if count % 600 == 0 { FileHandle.standardError.write("ocr \(count) frames\n".data(using: .utf8)!) }
    }
    if mode == "scan" { print("\(hits) sampled frames with legible matches (of \(count) frames)"); exit(0) }
}

let (reader, output, size, fps) = try await openReader()
let out = URL(fileURLWithPath: args[4])
try? FileManager.default.removeItem(at: out)
let writer = try AVAssetWriter(outputURL: out, fileType: .mp4)
let writerInput = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: Int(size.width), AVVideoHeightKey: Int(size.height),
    AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 14_000_000, AVVideoMaxKeyFrameIntervalKey: 30]])
writerInput.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: writerInput, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
    kCVPixelBufferWidthKey as String: Int(size.width), kCVPixelBufferHeightKey as String: Int(size.height)])
writer.add(writerInput)
writer.startWriting()
writer.startSession(atSourceTime: .zero)

var frame = 0
var blurredFrames = 0
let timescale = CMTimeScale(fps.rounded())
while let sample = output.copyNextSampleBuffer() {
    guard let source = CMSampleBufferGetImageBuffer(sample) else { continue }
    while !writerInput.isReadyForMoreMediaData { try await Task.sleep(nanoseconds: 2_000_000) }
    autoreleasepool {
        var image = CIImage(cvPixelBuffer: source)
        var boxes: [CGRect] = []
        for near in max(0, frame - hold)...(frame + hold) { boxes += perFrame[near] ?? [] }
        if !boxes.isEmpty {
            blurredFrames += 1
            let soft = image.clampedToExtent()
                .applyingFilter("CIPixellate", parameters: [kCIInputScaleKey: 16])
                .applyingGaussianBlur(sigma: 9).cropped(to: image.extent)
            for box in boxes { image = soft.cropped(to: box.integral).composited(over: image) }
        }
        var target: CVPixelBuffer?
        CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &target)
        context.render(image, to: target!)
        adaptor.append(target!, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: timescale))
    }
    frame += 1
}
guard reader.status == .completed else { print("read failed: \(String(describing: reader.error))"); exit(1) }
writerInput.markAsFinished()
await writer.finishWriting()
guard writer.status == .completed else { print("write failed: \(String(describing: writer.error))"); exit(1) }
print("redacted \(blurredFrames)/\(frame) frames")
