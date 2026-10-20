#!/usr/bin/env python3
"""Exercise the island's actual agent-event and neon precedence handlers."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/UI/Notch/NotchNeonEdge.swift").read_text()


def declaration(marker, text=source):
    start = text.index(marker)
    opening = text.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
        end += 1
    return text[start:end]


signature = declaration("    private enum Signature").replace("private ", "", 1)
signal = declaration("    private func signal(").replace("private ", "", 1)
charge = declaration("    private func charge(").replace("private ", "", 1)
charging_signal = declaration("enum NotchChargingSignal")
duration = declaration("    private var signalDuration:").replace("private ", "", 1)
music_gate = declaration("    private var showsMusicProgress:").replace("private ", "", 1)
progress_advancing = declaration("    private var progressAdvancing:").replace("private ", "", 1)
music_remaining = next(line for line in source.splitlines() if "let remaining = min(1, max(0, 1 - playback.position" in line)
playback_source = (repo / "Sources/Vorssaint/Services/Notch/NotchMusicSupport.swift").read_text()
playback_position = declaration("    func position(at date:", playback_source)
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
ELECTRIC_PROFILE
final class Model {
SIGNATURE
    var signature: Signature = .agent
    var signalAt: Date?
    var chargeAt: Date?
    var workspaceAt: Date?
    var working = false
    var music = Music()
    var service = Service()
    var timer = TimerFixture()
    var showsTimerFuse = false
    var playing: Bool { music.playback?.isPlaying == true }
    var animated: Bool { signalAt != nil || workspaceAt != nil }
DURATION
SIGNAL
CHARGE
MUSIC_GATE
PROGRESS_ADVANCING
    func remaining(at date: Date) -> Double {
        guard let playback = music.playback else { return 0 }
MUSIC_REMAINING
        return remaining
    }
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
    struct Playback {
        var isPlaying = true
        var duration: TimeInterval = 200
        var elapsed: TimeInterval = 0
        var rate = 1.0
        var sampledAt = Date(timeIntervalSince1970: 0)
        var hasPosition = true
PLAYBACK_POSITION
    }
    var playback: Playback?
}
enum Activity { case music, agents, timer, calendar, downloads, watch, keepAwake }
final class Service {
    var modules: Set<Activity> = [.music]
    var compactActivity: Activity? = .music
    var expanded = false, peeking = false, dragPlaceholder = false, fullscreenCompact = false
    var showsAeroSpace = false, showsAeroSpaceBadge = false, showsCompactActivityPicker = false
    var notice: Int?, departingNotice: Int?, captureControls: Int?
}
struct TimerFixture {
    struct Session { var isRunning = false }
    var session = Session()
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
    for other in [Model.Signature.message, .handoff, .terminalSuccess, .clipboard] {
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
let copied = Model()
let copiedAt = Date()
copied.signal(.clipboard, at: copiedAt)
expect(copied.signalDuration > 0 && copied.signalDuration <= 1,
       "copy feedback must be a brief pulse rather than a persistent notice")
let copyColors = copied.appearance(working: true)
expect(copyColors.0 == .white && copyColors.1 == .blue,
       "copy feedback must briefly turn white while preserving the agent's steady blue")
expect(copied.profile(at: 0).opacity == 0
       && copied.profile(at: copied.signalDuration / 2).opacity > 0.9,
       "copy feedback must rise smoothly from the existing edge to a visible white peak")
let copyFade = copied.profile(at: copied.signalDuration - 0.1).opacity
expect(copyFade > 0 && copyFade < 0.5
       && abs(copied.profile(at: copied.signalDuration).opacity) < 0.000001,
       "copy feedback must fade completely at the end of its short pulse")
let copiedAgainAt = copiedAt.addingTimeInterval(0.3)
copied.signal(.clipboard, at: copiedAgainAt)
expect(copied.signature == .clipboard && copied.signalAt == copiedAgainAt,
       "another copy must restart its pulse from the new copy time")
copied.signalAt = nil
expect(copied.appearance(working: true).0 == .blue,
       "after copy feedback ends, the continuing agent must regain its steady blue")
let charging = Model()
let pluggedInAt = Date()
charging.receive(.claude)
let completionAt = charging.signalAt
charging.charge(at: pluggedInAt)
expect(charging.chargeAt == pluggedInAt && charging.signalAt == completionAt
       && charging.signature == .agentFinished(.claude),
       "plugging in must preserve the independent provider completion beneath the green overlay")
charging.receive(.codex)
expect(charging.chargeAt == pluggedInAt && charging.signature == .agentFinished(.codex),
       "an agent completing during the charging signal must not erase its green overlay")
charging.signalAt = nil
charging.signal(.clipboard)
expect(charging.chargeAt == pluggedInAt && charging.signature == .clipboard,
       "clipboard feedback must not replace the independent charging signal")
charging.charge(at: nil)
expect(charging.chargeAt == nil && charging.signature == .clipboard,
       "unplugging must clear only the charging overlay")
charging.charge(at: Date().addingTimeInterval(-NotchChargingSignal.duration - 0.1))
expect(charging.chargeAt == nil, "a recreated view must not replay an expired plug-in signal")
charging.charge(at: Date().addingTimeInterval(10))
expect(charging.chargeAt == nil, "a timestamp in the future must not keep the animation clock alive")
expect(NotchChargingSignal.duration >= 3 && NotchChargingSignal.duration <= 3.5,
       "the charging edge must have a bounded roughly three-second lifetime")
for echo in 0..<2 {
    let delay = Double(echo) * NotchChargingSignal.echoDelay
    let leg = NotchChargingSignal.travelDuration
    expect(NotchChargingSignal.beamPosition(at: delay, echo: echo) == 0
           && NotchChargingSignal.beamPosition(at: delay + leg, echo: echo) == 1
           && abs(NotchChargingSignal.beamPosition(at: delay + leg * 2, echo: echo) ?? 1) < 0.000001,
           "each light must travel left to right and back to the left")
    expect(NotchChargingSignal.beamPosition(at: delay - 0.01, echo: echo) == nil
           && NotchChargingSignal.beamPosition(at: delay + leg * 2 + 0.01, echo: echo) == nil,
           "lights must not linger at either end before or after their sweep")
}
expect((NotchChargingSignal.beamPosition(at: 0.3, echo: 0) ?? 0)
       > (NotchChargingSignal.beamPosition(at: 0.3, echo: 1) ?? 1),
       "the second light must visibly follow the first on the outward pass")
expect((NotchChargingSignal.beamPosition(at: 0.85, echo: 0) ?? 1)
       < (NotchChargingSignal.beamPosition(at: 0.85, echo: 1) ?? 0),
       "the second light must follow back after the direction reverses")
expect(NotchChargingSignal.opacity(at: 0) == 0
       && NotchChargingSignal.opacity(at: NotchChargingSignal.duration) == 0,
       "the overlay must start and finish transparent so the underlying neon is revealed")
let calmStart = NotchChargingSignal.sweepDuration + 0.01
let calmEnd = NotchChargingSignal.duration - NotchChargingSignal.fadeDuration
expect(calmEnd - calmStart > 1
       && NotchChargingSignal.glow(at: calmStart, reduceMotion: false)
          == NotchChargingSignal.glow(at: calmEnd, reduceMotion: false)
       && NotchChargingSignal.opacity(at: calmStart) == 1
       && NotchChargingSignal.opacity(at: calmEnd) > 0.99,
       "after the double sweep, green must hold calmly for at least a second without pulsing")
expect(NotchChargingSignal.glow(at: 0.3, reduceMotion: true)
       == NotchChargingSignal.glow(at: calmStart, reduceMotion: true),
       "Reduce Motion must keep the green glow still throughout the hold")
let halfFade = NotchChargingSignal.duration - NotchChargingSignal.fadeDuration / 2
expect(abs(NotchChargingSignal.opacity(at: halfFade) - 0.5) < 0.000001,
       "both surfaces must fade smoothly into their existing neon")
let track = Model()
track.music.playback = Music.Playback()
expect(track.showsMusicProgress && track.progressAdvancing,
       "music alone shows its remaining-time line without hovering and advances with playback")
track.charge(at: Date())
expect(track.chargeAt != nil && track.showsMusicProgress && track.progressAdvancing,
       "charging must preserve the music remaining-time line underneath until the green fades")
track.charge(at: nil)
let sample = Date(timeIntervalSince1970: 0)
expect(track.remaining(at: sample) == 1
       && track.remaining(at: sample.addingTimeInterval(100)) == 0.5
       && track.remaining(at: sample.addingTimeInterval(300)) == 0,
       "the music line shrinks with time and stops at zero when the track ends")
track.music.playback?.elapsed = 150
expect(track.remaining(at: sample) == 0.25, "seeking updates the remaining line from the player's new position")
track.working = true
expect(!track.showsMusicProgress && !track.progressAdvancing,
       "any live agent keeps coding neon even if music remains the selected activity")
track.working = false
expect(track.showsMusicProgress, "music remaining time returns when the last agent finishes")
for activity in [Activity.agents, .timer, .calendar, .downloads, .watch, .keepAwake] {
    track.service.compactActivity = activity
    expect(!track.showsMusicProgress, "a different primary activity takes priority over music progress")
}
track.service.compactActivity = .music
let openStates: [ReferenceWritableKeyPath<Service, Bool>] = [
    \.expanded, \.peeking, \.dragPlaceholder, \.fullscreenCompact,
    \.showsAeroSpace, \.showsAeroSpaceBadge, \.showsCompactActivityPicker,
]
for state in openStates {
    track.service[keyPath: state] = true
    expect(!track.showsMusicProgress, "open, fullscreen and workspace surfaces keep their existing neon")
    track.service[keyPath: state] = false
}
let overrides: [ReferenceWritableKeyPath<Service, Int?>] = [\.notice, \.departingNotice, \.captureControls]
for override in overrides {
    track.service[keyPath: override] = 1
    expect(!track.showsMusicProgress, "notifications and capture surfaces preempt music remaining time")
    track.service[keyPath: override] = nil
}
for pulse in [Model.Signature.message, .clipboard, .agentFinished(.claude)] {
    track.signal(pulse)
    expect(!track.showsMusicProgress, "notification, copy and completion signals retain the full neon edge")
    track.signalAt = nil
    expect(track.showsMusicProgress, "music remaining time resumes after a transient signal ends")
}
track.workspaceAt = Date()
expect(!track.showsMusicProgress, "workspace neon takes priority until its signal finishes")
track.workspaceAt = nil
track.music.playback?.isPlaying = false
expect(!track.showsMusicProgress && !track.progressAdvancing,
       "a paused player neither shows a moving remaining line nor starts a progress timeline")
track.music.playback?.isPlaying = true
for duration in [0.0, -1, Double.nan, Double.infinity] {
    track.music.playback?.duration = duration
    expect(!track.showsMusicProgress, "unknown or invalid durations never invent remaining progress")
}
track.music.playback?.duration = 200
track.music.playback?.hasPosition = false
expect(!track.showsMusicProgress, "a player without a position cannot display remaining progress")
track.music.playback?.hasPosition = true
track.service.modules = []
expect(!track.showsMusicProgress, "disabling music removes its progress line")
track.service.modules = [.music]
track.music.playback = nil
expect(!track.showsMusicProgress, "a departed player removes its progress line")
print("PASS: \(checks) agent neon checks")
'''
for token, value in [("SIGNATURE", signature), ("DURATION", duration), ("SIGNAL", signal),
                     ("ELECTRIC_PROFILE", charging_signal), ("CHARGE", charge),
                     ("RECEIVE", receive), ("APPEARANCE", appearance), ("RENDERING", rendering),
                     ("PROVIDER_COLORS", provider_colors), ("MUSIC_GATE", music_gate),
                     ("PROGRESS_ADVANCING", progress_advancing), ("MUSIC_REMAINING", music_remaining),
                     ("PLAYBACK_POSITION", playback_position)]:
    swift = swift.replace(token, value)

with tempfile.TemporaryDirectory(prefix="notch-agent-neon-") as directory:
    path = Path(directory)
    (path / "main.swift").write_text(swift)
    subprocess.run(["swiftc", str(path / "main.swift"), "-o", str(path / "checks")], check=True)
    subprocess.run([str(path / "checks")], check=True)
