// On-device word-level transcription with Apple's SpeechAnalyzer (macOS 26+).
// usage: swift transcribe.swift <audio.wav> <words.json> [locale]
// Writes [[start, end, "word"], ...] in seconds.
import AVFoundation
import Foundation
import Speech

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: transcribe.swift <audio.wav> <words.json> [locale]"); exit(2) }
let wanted = Locale(identifier: args.count > 3 ? args[3] : "en-US")

guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: wanted) else {
    print("unsupported locale \(wanted.identifier)"); exit(1)
}
let transcriber = SpeechTranscriber(locale: locale, transcriptionOptions: [],
                                    reportingOptions: [], attributeOptions: [.audioTimeRange])
if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
    print("installing Apple speech assets for \(locale.identifier)…")
    try await request.downloadAndInstall()
}
let analyzer = SpeechAnalyzer(modules: [transcriber])
let collector = Task { () throws -> [[Any]] in
    var words: [[Any]] = []
    for try await result in transcriber.results {
        for run in result.text.runs {
            guard let range = run.audioTimeRange else { continue }
            let text = String(result.text[run.range].characters).trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty { continue }
            words.append([(range.start.seconds * 1000).rounded() / 1000,
                          (range.end.seconds * 1000).rounded() / 1000, text])
        }
    }
    return words
}
let file = try AVAudioFile(forReading: URL(fileURLWithPath: args[1]))
if let last = try await analyzer.analyzeSequence(from: file) {
    try await analyzer.finalizeAndFinish(through: last)
} else {
    await analyzer.cancelAndFinishNow()
}
let words = try await collector.value
try JSONSerialization.data(withJSONObject: words).write(to: URL(fileURLWithPath: args[2]))
print("\(words.count) words, locale \(locale.identifier)")
