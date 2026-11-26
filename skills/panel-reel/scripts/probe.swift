// Sample an upright 9:16 recording for fit_room.py, on-device (Apple Vision).
//
//   probe <video> <outdir> [samples]
//
// Writes frames.gray and masks.gray (samples x 960 x 540, one byte a pixel, top row first) and
// faces.json: for each sample the eyes' midpoint and the face box in 1080x1920 pixels, or null.
import AVFoundation
import CoreImage
import Foundation
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!); exit(2)
}
let args = CommandLine.arguments
guard args.count >= 3 else { fail("usage: probe <video> <outdir> [samples]") }
let out = URL(fileURLWithPath: args[2])
let samples = args.count > 3 ? Int(args[3]) ?? 12 : 12
let W = 540, H = 960

let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let seconds = try await asset.load(.duration).seconds
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero

let grey = CGColorSpaceCreateDeviceGray()
func bytes(_ image: CGImage) -> Data {
    var data = [UInt8](repeating: 0, count: W * H)
    data.withUnsafeMutableBytes { buffer in
        let canvas = CGContext(data: buffer.baseAddress, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W,
                               space: grey, bitmapInfo: CGImageAlphaInfo.none.rawValue)!
        canvas.interpolationQuality = .high
        canvas.draw(image, in: CGRect(x: 0, y: 0, width: W, height: H))
    }
    return Data(data)
}

let context = CIContext()
let segment = VNGeneratePersonSegmentationRequest()
segment.qualityLevel = .accurate
segment.outputPixelFormat = kCVPixelFormatType_OneComponent8
let landmarks = VNDetectFaceLandmarksRequest()
var frames = Data(), masks = Data()
var faces: [Any] = []

for index in 0..<samples {
    let at = CMTime(seconds: seconds * (Double(index) + 0.5) / Double(samples), preferredTimescale: 600)
    let image = try await generator.image(at: at).image
    guard abs(Double(image.width) / Double(image.height) - 9.0 / 16.0) < 0.01 else {
        fail("the recording is \(image.width)x\(image.height); this needs an upright 9:16 recording")
    }
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([segment, landmarks])
    guard let result = segment.results?.first else { fail("no outline at sample \(index)") }
    let mask = CIImage(cvPixelBuffer: result.pixelBuffer)
    guard let picture = context.createCGImage(mask, from: mask.extent, format: .L8, colorSpace: grey) else { fail("bad outline") }
    frames.append(bytes(image))
    masks.append(bytes(picture))

    var entry: Any = NSNull()
    if let face = landmarks.results?.max(by: { $0.boundingBox.width < $1.boundingBox.width }),
       let left = face.landmarks?.leftEye, let right = face.landmarks?.rightEye {
        let size = CGSize(width: 1080, height: 1920)
        let eyes = left.pointsInImage(imageSize: size) + right.pointsInImage(imageSize: size)
        let x = eyes.map { Double($0.x) }.reduce(0, +) / Double(eyes.count)
        let y = 1920 - eyes.map { Double($0.y) }.reduce(0, +) / Double(eyes.count)
        let box = face.boundingBox
        entry = ["eyes": [x, y], "box": [box.minX * 1080, (1 - box.maxY) * 1920, box.width * 1080, box.height * 1920]]
    }
    faces.append(entry)
}
try frames.write(to: out.appendingPathComponent("frames.gray"))
try masks.write(to: out.appendingPathComponent("masks.gray"))
try JSONSerialization.data(withJSONObject: faces).write(to: out.appendingPathComponent("faces.json"))
