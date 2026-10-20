#!/usr/bin/env python3
"""Exercise the island's actual agent-event and neon precedence handlers."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/UI/Notch/NotchNeonEdge.swift").read_text()


def declaration(marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end]


signature = declaration("    private enum Signature").replace("private ", "", 1)
signal = declaration("    private func signal(").replace("private ", "", 1)
duration = declaration("    private var signalDuration:").replace("private ", "", 1)
receive = declaration(".onReceive(agents.completions) { provider in")
receive = receive[receive.index("{ provider in") + len("{ provider in"):-1]
appearance = source[source.index("        let completion ="):source.index("        let phase =")]
rendering = source[source.index("        let completion ="):source.index("        let workspaceOpacity =")]
provider_colors = (repo / "Sources/Vorssaint/UI/Notch/NotchAgentComponents.swift").read_text()
provider_colors = provider_colors[provider_colors.index("extension AgentProvider {"):provider_colors.index("\n}\n") + 2]
swift = r'''
import Foundation
import SwiftUI
import AppKit
enum AgentProvider { case claude, codex, opencode, copilot }
PROVIDER_COLORS
final class Model {
SIGNATURE
    var signature: Signature = .agent
    var signalAt: Date?
DURATION
SIGNAL
    func receive(_ provider: AgentProvider) {
RECEIVE
    }
    func appearance(working: Bool) -> (Color, Color) {
        let age = signalAt.map { Date().timeIntervalSince($0) }
        let blue = Color.blue, purple = Color.purple, playing = false
        let music = Music()
        let workspace: Double? = nil
        let workspaceName: String? = nil
APPEARANCE
        return (tint, steadyTint)
    }
    func profile(at elapsed: TimeInterval, working: Bool = true, reduceMotion: Bool = false) -> (phase: Double, stops: [Gradient.Stop], opacity: Double) {
        let age: TimeInterval? = elapsed
        let blue = Color.blue, purple = Color.purple, playing = false
        let music = Music()
        let workspace: Double? = nil
        let workspaceName: String? = nil
RENDERING
        return (phase, stops, pulseOpacity ?? 0)
    }
}
struct Music {
    struct Artwork { var color = Color.purple }
    var artworkTint: Artwork? = nil
}
enum NotchNeonPalette {
    static func workspace(_ name: String?) -> Color { .purple }
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    guard condition else {
        FileHandle.standardError.write(Data(("FAIL: " + message + "\n").utf8))
        exit(1)
    }
}
func gradientAlpha(_ stops: [Gradient.Stop], at point: CGFloat) -> CGFloat {
    for (left, right) in zip(stops, stops.dropFirst()) where left.location <= point && right.location >= point {
        let fraction = (point - left.location) / max(0.0001, right.location - left.location)
        let a = NSColor(left.color).alphaComponent, b = NSColor(right.color).alphaComponent
        return a + (b - a) * fraction
    }
    return 0
}
let model = Model()
for provider in [AgentProvider.claude, .codex] {
    model.receive(provider)
    let completion = String(describing: model.signature)
    expect(completion.contains("agentFinished") && completion.contains(String(describing: provider)),
           "a completion must preserve its provider instead of using the blue working signal")
    let colors = model.appearance(working: true)
    expect(colors.0 == provider.tint && colors.1 == .blue,
           "completion must draw in the provider color above the continuing agent's steady blue")
    expect(model.signalDuration >= 3, "completion should remain visible for about three seconds")
    let held = model.profile(at: 1.5)
    expect([CGFloat(0.25), 0.5, 0.75].allSatisfy { gradientAlpha(held.stops, at: $0) > 0.5 },
        "the middle of the edge must retain a clear provider tint after the wave reaches the corners")
    expect(held.opacity > 0.9, "completion must still be bright halfway through its hold")
    expect(model.profile(at: 0.7).phase < 0.75, "the outgoing wave must not reach the corners in 0.7 seconds")
    let fading = model.profile(at: model.signalDuration - 0.5).opacity
    expect(fading > 0.2 && fading < 0.8, "completion must fade smoothly into the continuing agent")
    expect(model.profile(at: model.signalDuration).opacity == 0, "completion must fully reveal the steady edge at its end")
    guard let began = model.signalAt else { fatalError("completion must start a pulse") }
    model.signal(.agent, at: began.addingTimeInterval(0.01))
    expect(String(describing: model.signature) == completion && model.signalAt == began,
           "the paired agent notice must not replace a provider's completion pulse")
    for other in [Model.Signature.message, .charge, .handoff, .terminalSuccess] {
        model.signal(other, at: began.addingTimeInterval(0.1))
        expect(String(describing: model.signature) == completion && model.signalAt == began,
               "incidental activity must not interrupt an agent's completion")
    }
    model.signal(.agent, at: began.addingTimeInterval(model.signalDuration - 0.01))
    expect(String(describing: model.signature) == completion,
           "another agent's activity must not erase the completion before its pulse ends")
    model.signal(.agent, at: began.addingTimeInterval(model.signalDuration + 0.01))
    expect(model.signature == .agent, "ordinary activity may signal after completion expires")
}
model.receive(.claude)
model.receive(.codex)
expect(String(describing: model.signature).contains("codex"),
       "a second provider completing must get its own pulse")
model.signalAt = nil
expect(model.appearance(working: true).0 == .blue,
       "after completion expires the continuing agent must regain its steady working color")
model.signal(.agent)
expect(model.signature == .agent, "the completion state must not block activity after cleanup")
print("PASS: \(checks) agent neon checks")
'''
for token, value in [("SIGNATURE", signature), ("DURATION", duration), ("SIGNAL", signal),
                     ("RECEIVE", receive), ("APPEARANCE", appearance), ("RENDERING", rendering),
                     ("PROVIDER_COLORS", provider_colors)]:
    swift = swift.replace(token, value)

with tempfile.TemporaryDirectory(prefix="notch-agent-neon-") as directory:
    path = Path(directory)
    (path / "main.swift").write_text(swift)
    subprocess.run(["swiftc", str(path / "main.swift"), "-o", str(path / "checks")], check=True)
    subprocess.run([str(path / "checks")], check=True)
