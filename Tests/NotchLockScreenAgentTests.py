#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint

"""Render the actual lock-screen agent entry with independent session fixtures."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
view = (repo / "Sources/Vorssaint/UI/Notch/NotchLockScreenView.swift").read_text()
support = (repo / "Sources/Vorssaint/Services/Notch/NotchAgentSupport.swift").read_text()
models = (repo / "Sources/Vorssaint/Services/AgentUsage/AgentUsageModels.swift").read_text()
components = (repo / "Sources/Vorssaint/UI/Notch/NotchAgentComponents.swift").read_text()


def declaration(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


entry = view[view.index("        case .agents:\n"):view.index("        case .downloads:\n")]
entry = entry.removeprefix("        case .agents:\n")
swift = r'''
import AppKit
import SwiftUI
import Vision
PROVIDER
PROVIDER_COLORS
READOUT
DISPLAY
FOCUS
FORMAT
struct AgentTokens { var output = 617 }
struct AgentLiveSession {
    let provider: AgentProvider
    let started: Date
    let project = "PRIVATE_PROJECT"
    var tokens = AgentTokens()
    var cost = 4.5
}
struct Limit { var usedFraction = 0.25; var remainingFraction = 0.75 }
struct AgentUsageSnapshot { var live: [AgentLiveSession]; var limits: [AgentProvider: Limit] = [:] }
enum NotchAgentSupport {
READINGS
READING
    static func focusedLimit(_ limit: Limit?, focus: NotchAgentLimitFocus, now: Date) -> Limit? { limit }
}
struct Usage { var snapshot: AgentUsageSnapshot }
struct L10n { let language = "en" }
enum FeatureStrings {
    struct Lock { let working = "Working" }
    static func notchLockScreen(_ language: String) -> Lock { Lock() }
}
// Glyph artwork is irrelevant to the reading. Preserve its occupied space.
struct NotchAgentGlyph: View {
    let provider: AgentProvider
    let size: CGFloat
    var body: some View { Color.clear.frame(width: size, height: size) }
}
struct Entry: View {
    let usage: Usage
    let date: Date
    var readout = "elapsed"
    let display = "remaining", focus = "mostUsed", l10n = L10n()
    var body: some View {
ENTRY
    }
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    guard condition else {
        FileHandle.standardError.write(Data(("FAIL: " + message + "\n").utf8))
        exit(1)
    }
}
@MainActor func rendered(_ sessions: [AgentLiveSession], at date: Date, readout: String = "elapsed",
                        checkColors: Bool = false) -> String {
    let entry = Entry(usage: Usage(snapshot: AgentUsageSnapshot(live: sessions)), date: date, readout: readout)
        .font(.system(size: 13, weight: .semibold))
        .monospacedDigit()
        .foregroundStyle(.white)
        .padding(12)
        .background(.black)
    let renderer = ImageRenderer(content: entry)
    renderer.scale = 4
    guard let image = renderer.cgImage else { fatalError("lock-screen entry did not render") }
    if checkColors {
        let bitmap = NSBitmapImageRep(cgImage: image)
        for provider in [AgentProvider.claude, .codex] {
            let columns = provider == .claude ? 0..<(bitmap.pixelsWide / 2)
                : (bitmap.pixelsWide / 2)..<bitmap.pixelsWide
            let hasColor = (0..<bitmap.pixelsHigh).contains { y in
                columns.contains { x in
                    guard let pixel = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB) else { return false }
                    let r = pixel.redComponent, g = pixel.greenComponent, b = pixel.blueComponent
                    // Allow display color conversion and text antialiasing.
                    return provider == .claude ? r > g + 0.2 && r > b + 0.3
                        : b > r + 0.2 && b > g + 0.15
                }
            }
            expect(hasColor, "\(provider.displayName)'s timer must render in its own position and desktop color")
        }
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    try! VNImageRequestHandler(cgImage: image).perform([request])
    let result = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    expect(!result.contains("PRIVATE_PROJECT"), "project names must stay off the lock screen")
    expect(!result.contains("Claude") && !result.contains("Codex"),
           "the compact agent row must show glyphs and timers without visible provider names, got: \(result)")
    return result
}
MainActor.assumeIsolated {
let now = Date(timeIntervalSince1970: 2_000_000)
func session(_ provider: AgentProvider, _ age: TimeInterval) -> AgentLiveSession {
    AgentLiveSession(provider: provider, started: now.addingTimeInterval(-age))
}
let together = [session(.codex, 754), session(.claude, 20)]
let initial = rendered(together, at: now, checkColors: true)
let paired = initial.replacingOccurrences(of: " ", with: "")
expect(paired == "0:2012:34",
       "staggered agents must render their own elapsed readings in provider order, got: \(initial)")
let advanced = rendered(together, at: now.addingTimeInterval(1))
expect(advanced.contains("0:21") && advanced.contains("12:35"),
       "each lock-screen clock must advance independently, got: \(advanced)")
let continuing = rendered([together[0]], at: now.addingTimeInterval(1))
expect(continuing == "12:35",
       "Claude finishing must leave Codex's original clock intact, got: \(continuing)")
let grouped = rendered(together + [session(.claude, 5)], at: now)
expect(grouped.contains("0:20") && grouped.contains("12:34") && !grouped.contains("0:05"),
       "a provider with multiple live sessions keeps its earliest active turn, got: \(grouped)")
let restarted = rendered([session(.codex, 754), session(.claude, 1)], at: now)
expect(restarted.contains("0:01") && restarted.contains("12:34"),
       "a restarted Claude session must not inherit Codex's duration, got: \(restarted)")
let tokens = rendered(together, at: now, readout: "tokens")
expect(tokens.contains(AgentFormat.tokens(1234)),
       "the selected token mode must retain its combined total, got: \(tokens)")
let costs = rendered(together, at: now, readout: "cost")
expect(costs.contains(AgentFormat.cost(9)),
       "the selected cost mode must retain its combined total, got: \(costs)")
print("PASS: \(checks) lock-screen agent rendering checks")
}
'''
for marker, value in {
    "PROVIDER": declaration(models, "enum AgentProvider:"),
    "PROVIDER_COLORS": declaration(components, "extension AgentProvider {"),
    "READOUT": declaration(support, "enum NotchAgentReadout:"),
    "DISPLAY": declaration(support, "enum NotchAgentLimitDisplay:"),
    "FOCUS": declaration(support, "enum NotchAgentLimitFocus:"),
    "FORMAT": declaration(support, "enum AgentFormat {"),
    "READINGS": declaration(support, "    static func stripReadings("),
    "READING": declaration(support, "    static func stripReading("),
    "ENTRY": entry,
}.items():
    swift = swift.replace("\n" + marker + "\n", "\n" + value + "\n")

with tempfile.TemporaryDirectory(prefix="notch-lock-agent-") as directory:
    path = Path(directory)
    (path / "main.swift").write_text(swift)
    subprocess.run(["swiftc", str(path / "main.swift"), "-o", str(path / "checks")], check=True)
    subprocess.run([str(path / "checks")], check=True)
