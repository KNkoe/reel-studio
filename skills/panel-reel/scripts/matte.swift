// Cut the speaker out of the face video with Apple Vision person segmentation (on-device).
//
//   matte <face.mp4> <rows> | ffmpeg -f rawvideo -pix_fmt bgra ... cutout.webm
//
// Writes the top <rows> of every frame to stdout as straight-alpha BGRA: the person is
// opaque, everything behind them is transparent. Only the strip around the card's top
// edge is needed; below it the ordinary video shows through the rounded card.
import AVFoundation
import CoreImage
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count == 3, let wanted = Int(args[2]), wanted > 0 else {
    FileHandle.standardError.write("usage: matte <face.mp4> <rows>\n".data(using: .utf8)!); exit(2)
}

let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let track = try await asset.loadTracks(withMediaType: .video)[0]
let size = try await track.load(.naturalSize)
let width = Int(size.width), height = Int(size.height), rows = min(wanted, height)
let reader = try AVAssetReader(asset: asset)
let output = AVAssetReaderTrackOutput(track: track, outputSettings:
    [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
reader.add(output)
reader.startReading()

let context = CIContext(options: [.workingColorSpace: NSNull()])
let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .accurate
request.outputPixelFormat = kCVPixelFormatType_OneComponent8

// Core Image's origin is bottom-left, so the top strip starts at height - rows.
let strip = CGRect(x: 0, y: height - rows, width: width, height: rows)
var colour = [UInt8](repeating: 0, count: width * rows * 4)
var maskBytes = [UInt8](repeating: 0, count: width * rows * 4)
var previous = [Float](repeating: 0, count: width * rows)
var count = 0, empty = 0

while let sample = output.copyNextSampleBuffer() {
    try autoreleasepool {
        guard let buffer = CMSampleBufferGetImageBuffer(sample) else { return }
        try VNImageRequestHandler(cvPixelBuffer: buffer, options: [:]).perform([request])
        guard let result = request.results?.first else { fatalError("no segmentation at frame \(count)") }
        var mask = CIImage(cvPixelBuffer: result.pixelBuffer)
        mask = mask.transformed(by: CGAffineTransform(scaleX: size.width / mask.extent.width,
                                                      y: size.height / mask.extent.height))
        // pull the edge in a touch so no pale wall fringe shows against a dark stage
        mask = mask.clampedToExtent()
            .applyingFilter("CIMorphologyMinimum", parameters: [kCIInputRadiusKey: 1.2])
            .applyingGaussianBlur(sigma: 0.8)
            .cropped(to: CGRect(origin: .zero, size: size))
        context.render(CIImage(cvPixelBuffer: buffer), toBitmap: &colour, rowBytes: width * 4,
                       bounds: strip, format: .BGRA8, colorSpace: nil)
        context.render(mask, toBitmap: &maskBytes, rowBytes: width * 4,
                       bounds: strip, format: .BGRA8, colorSpace: nil)
        var solid = 0
        for i in 0..<(width * rows) {
            var value = Float(maskBytes[i * 4 + 2]) / 255
            // steady the edge between frames; a big change is real movement or a cut
            if count > 0 && abs(value - previous[i]) < 0.35 { value = 0.7 * value + 0.3 * previous[i] }
            previous[i] = value
            let t = min(1, max(0, (value - 0.3) / 0.4))
            let alpha = UInt8((t * t * (3 - 2 * t) * 255).rounded())
            if alpha > 127 { solid += 1 }
            colour[i * 4 + 3] = alpha
        }
        if solid == 0 { empty += 1 }
        colour.withUnsafeBytes { FileHandle.standardOutput.write(Data($0)) }
    }
    count += 1
    if count % 600 == 0 { FileHandle.standardError.write("matte \(count) frames\n".data(using: .utf8)!) }
}
withExtendedLifetime(reader) {}
guard reader.status == .completed else {
    FileHandle.standardError.write("read failed: \(String(describing: reader.error))\n".data(using: .utf8)!); exit(1)
}
FileHandle.standardError.write("matte done: \(count) frames, \(empty) with nobody above the card line\n".data(using: .utf8)!)
