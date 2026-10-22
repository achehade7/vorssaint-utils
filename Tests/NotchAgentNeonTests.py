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
progress_advancing = declaration("    private var progressAdvancing:").replace("private ", "", 1)
receive = declaration(".onReceive(agents.completions) { provider in")
receive = receive[receive.index("{ provider in") + len("{ provider in"):-1]
appearance = source[source.index("        let completion ="):source.index("        let phase =")]
rendering = source[source.index("        let completion ="):source.index("        let workspaceOpacity =")]
provider_colors = (repo / "Sources/Vorssaint/UI/Notch/NotchAgentComponents.swift").read_text()
provider_colors = provider_colors[provider_colors.index("extension AgentProvider {"):provider_colors.index("\n}\n") + 2]
service_source = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()
meeting_handler = declaration("    func signalMeetingStarted(at", service_source)
meeting_click = declaration("        if selectedNotice.meetingReminder {", service_source)
reminder_handler = declaration("    func signalMeetingReminder(title:", service_source)
notice_can_present = declaration("    private var noticeCanPresent:", service_source).replace("private ", "", 1)
notice_changed = declaration(".onChange(of: service.notice) { _, notice in")
notice_changed = notice_changed[notice_changed.index("{ _, notice in") + len("{ _, notice in"):-1]
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
    var timer = TimerFixture()
    var showsTimerFuse = false
DURATION
SIGNAL
CHARGE
PROGRESS_ADVANCING
    func receive(_ provider: AgentProvider) {
RECEIVE
    }
    func noticeChanged(_ notice: NotchNotice?) {
NOTICE_CHANGED
    }
    func appearance(working: Bool, elapsed: TimeInterval? = nil, reduceMotion: Bool = false) -> (Color, Color) {
        let age = elapsed ?? signalAt.map { Date().timeIntervalSince($0) }
        let blue = Color.blue, purple = Color.purple
        let workspace: Double? = nil
        let workspaceName: String? = nil
APPEARANCE
        return (tint, steadyTint)
    }
    func profile(at elapsed: TimeInterval, working: Bool = true, reduceMotion: Bool = false) -> (phase: Double, stops: [Gradient.Stop], opacity: Double) {
        let age: TimeInterval? = elapsed
        let blue = Color.blue, purple = Color.purple
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
        var elapsed: TimeInterval = 0
    }
    var playback: Playback?
}
struct TimerFixture {
    struct Session { var isRunning = false }
    var session = Session()
}
enum NotchNeonPalette {
    static func workspace(_ name: String?) -> Color { .purple }
}
final class MeetingService {
    var acceptsSystemFeedback = true, displayIsFullscreen = false
    var expanded = false, dragPlaceholder = false, canShow = true
    var captureControls: Bool?
    var neonMeetingAt: Date?
    var lastMeetingReminderStart: Date?
    var lastMeetingAnnouncementStart: Date?
    var notices: [NotchNotice] = []
    func show(_ notice: NotchNotice) -> Bool {
        guard canShow else { return false }
        notices.append(notice)
        return true
    }
NOTICE_CAN_PRESENT
MEETING_HANDLER
REMINDER_HANDLER
}
final class NSWorkspace {
    static let shared = NSWorkspace()
    var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
final class MeetingClickHost {
    enum Page { case calendar }
    var dismissed = 0, calendars = 0
    func dismissNotice() { dismissed += 1 }
    func open(_ page: Page) { calendars += 1 }
    func click(_ selectedNotice: NotchNotice) {
MEETING_CLICK
    }
}
enum AppLanguage: String { case enUS = "en-US" }
struct L10n {
    static let shared = L10n()
    let language = AppLanguage.enUS
}
struct FeatureStrings {
    struct CalendarText { let untitled = "Untitled event"; let ongoing = "Happening now" }
    static func notchCalendar(_ language: AppLanguage) -> CalendarText { CalendarText() }
}
enum NotchCalendarSupport {
    static func meetingURL(url: URL?, location: String?, notes: String?) -> URL? {
        guard url?.scheme == "https", url?.host == "meet.google.com" else { return nil }
        return url
    }
}
enum NotchEvent { case systemNotification, agents }
struct NotchNotice {
    let event: NotchEvent
    let title: String, detail: String, symbol: String
    var meetingReminder = false
    var meetingStartsNow = false
    var meetingURL: URL? = nil
    var audioHandoff = false
    var terminalStatus: Int?
    struct Notification { var app: String }
    var notification: Notification?
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
    for other in [Model.Signature.message, .handoff, .terminalSuccess, .clipboard, .meeting] {
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
expect(NotchChargingSignal.duration >= 2 && NotchChargingSignal.duration <= 2.5,
       "the charging edge must have a bounded roughly two-second lifetime")
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
expect(calmEnd - calmStart > 0.25
       && NotchChargingSignal.glow(at: calmStart, reduceMotion: false)
          == NotchChargingSignal.glow(at: calmEnd, reduceMotion: false)
       && NotchChargingSignal.opacity(at: calmStart) == 1
       && NotchChargingSignal.opacity(at: calmEnd) > 0.99,
       "after the double sweep, green must hold calmly for at least a quarter-second without pulsing")
expect(NotchChargingSignal.glow(at: 0.3, reduceMotion: true)
       == NotchChargingSignal.glow(at: calmStart, reduceMotion: true),
       "Reduce Motion must keep the green glow still throughout the hold")
let halfFade = NotchChargingSignal.duration - NotchChargingSignal.fadeDuration / 2
expect(abs(NotchChargingSignal.opacity(at: halfFade) - 0.5) < 0.000001,
       "both surfaces must fade smoothly into their existing neon")
let track = Model()
track.music.playback = Music.Playback()
track.music.artworkTint = Music.Artwork(color: .red)
expect(!track.progressAdvancing, "playing music does not start a neon progress clock")
expect(track.appearance(working: false).1 == .purple,
       "music artwork no longer changes the idle neon palette")
track.music.playback?.elapsed = 199
expect(!track.progressAdvancing, "a track ending does not create a music countdown line")
track.showsTimerFuse = true; track.timer.session.isRunning = true
expect(track.progressAdvancing, "an active timer keeps its existing countdown fuse")
track.timer.session.isRunning = false
expect(!track.progressAdvancing, "pausing a timer stops the remaining progress clock")
let meeting = Model()
meeting.signal(.meeting)
let cyan = NSColor(meeting.appearance(working: true, elapsed: 0).0).usingColorSpace(.sRGB)!
expect(meeting.signalDuration == 1.2 && abs(cyan.redComponent - 125.0 / 255) < 0.001
       && abs(cyan.greenComponent - 220.0 / 255) < 0.001 && abs(cyan.blueComponent - 232.0 / 255) < 0.001,
       "meeting start uses icy cyan even while a blue agent is working")
let halfway = NSColor(meeting.appearance(working: true, elapsed: 0.3).0).usingColorSpace(.sRGB)!
let peak = NSColor(meeting.appearance(working: true, elapsed: 0.6).0).usingColorSpace(.sRGB)!
expect(halfway.redComponent > cyan.redComponent && halfway.redComponent < peak.redComponent,
       "meeting colour moves smoothly from cyan toward white")
expect(peak.redComponent > 0.999 && peak.greenComponent > 0.999 && peak.blueComponent > 0.999,
       "meeting pulse reaches white at its peak")
expect(meeting.appearance(working: true, elapsed: 0.6, reduceMotion: true).0
       == meeting.appearance(working: true, elapsed: 0, reduceMotion: true).0,
       "Reduce Motion preserves steady cyan without a colour flash")
expect(meeting.profile(at: 0).opacity == 0 && meeting.profile(at: 0.6).opacity > 0.99
       && meeting.profile(at: 1.2).opacity < 0.0001,
       "meeting pulse fades in and out without a persistent edge")
expect(meeting.profile(at: 0.6, reduceMotion: true).opacity == 0.75,
       "Reduce Motion keeps the short meeting signal steady")
for condition in 0..<5 {
    let service = MeetingService()
    let at = Date().addingTimeInterval(condition == 3 ? -5 : condition == 4 ? 5 : -0.01)
    if condition == 0 { service.acceptsSystemFeedback = false }
    if condition == 1 { service.displayIsFullscreen = true }
    if condition == 2 { service.captureControls = true }
    service.signalMeetingStarted(at: at)
    expect(service.neonMeetingAt == nil, "quiet, suspended, fullscreen, capture and expired signals stay silent")
}
let service = MeetingService(), freshMeeting = Date().addingTimeInterval(-0.01)
service.signalMeetingStarted(at: freshMeeting)
expect(service.neonMeetingAt == freshMeeting, "live desktop meeting signal reaches the existing neon")
let reminder = MeetingService(), reminderStart = Date().addingTimeInterval(599)
reminder.signalMeetingReminder(title: "  Planning\nreview  ", start: reminderStart, at: Date().addingTimeInterval(-0.01))
expect(reminder.notices.count == 1 && reminder.notices[0].title == "Planning review"
       && reminder.notices[0].detail == "10 min" && reminder.notices[0].symbol == "calendar"
       && reminder.notices[0].meetingReminder,
       "ten-minute notice carries a clean title on the left and localized minutes on the right")
reminder.signalMeetingReminder(title: "Duplicate", start: reminderStart, at: Date())
expect(reminder.notices.count == 1, "duplicate transport payload cannot show the same reminder twice")
let noticeModel = Model()
noticeModel.noticeChanged(reminder.notices[0])
expect(noticeModel.signature == .meeting, "reminder notice uses cyan meeting neon, not the generic message pulse")
noticeModel.noticeChanged(NotchNotice(event: .systemNotification, title: "Slack", detail: "Meeting soon", symbol: "bell"))
expect(noticeModel.signature == .message, "ordinary Slack and other notifications retain their existing pulse")
for condition in 0..<10 {
    let blocked = MeetingService()
    var timestamp = Date(), start = Date().addingTimeInterval(599)
    switch condition {
    case 0: blocked.acceptsSystemFeedback = false
    case 1: blocked.expanded = true
    case 2: blocked.dragPlaceholder = true
    case 3: blocked.captureControls = true
    case 4: blocked.canShow = false
    case 5: timestamp = Date().addingTimeInterval(-5)
    case 6: timestamp = Date().addingTimeInterval(5)
    case 7: start = Date().addingTimeInterval(590)
    case 8: start = Date().addingTimeInterval(610)
    default: start = Date(timeIntervalSince1970: .nan)
    }
    blocked.signalMeetingReminder(title: "Ignored", start: start, at: timestamp)
    expect(blocked.notices.isEmpty && blocked.lastMeetingReminderStart == nil,
           "unavailable surfaces, rejected notices and stale/early/invalid reminders stay silent")
}
let blank = MeetingService()
blank.signalMeetingReminder(title: "\n\t  ", start: reminderStart, at: Date())
expect(blank.notices.first?.title == "Untitled event", "blank title reuses the calendar's localized fallback")
let long = MeetingService()
long.signalMeetingReminder(title: String(repeating: "界", count: 200), start: reminderStart, at: Date())
expect(long.notices.first?.title.count == 160, "long Unicode titles are bounded without splitting characters")
let starting = MeetingService()
let startDate = Date().addingTimeInterval(-0.01)
let joinLink = "https://meet.google.com/abc-defg-hij"
starting.signalMeetingStarted(at: startDate, title: " Planning ", start: startDate, url: joinLink)
expect(starting.notices.count == 1 && starting.notices[0].title == "Planning"
       && starting.notices[0].meetingStartsNow && starting.notices[0].meetingURL?.absoluteString == joinLink,
       "start banner preserves the exact Meet link and title")
starting.signalMeetingStarted(at: startDate, title: "Duplicate", start: startDate, url: joinLink)
expect(starting.notices.count == 1, "a duplicate start cannot repeat the banner")
let linkedReminder = MeetingService()
linkedReminder.signalMeetingReminder(title: "Planning", start: reminderStart, at: Date(), url: joinLink)
expect(linkedReminder.notices.first?.meetingURL?.absoluteString == joinLink,
       "ten-minute reminder also preserves the direct call link")
for offset in [-5.0, 5.0] {
    let late = MeetingService()
    late.signalMeetingStarted(at: Date(), title: "Missed", start: Date().addingTimeInterval(offset), url: joinLink)
    expect(late.notices.isEmpty, "early and missed starts do not announce")
}
let missingLink = MeetingService()
missingLink.signalMeetingStarted(at: startDate, title: "No call", start: startDate, url: "https://example.com")
expect(missingLink.notices.first?.meetingURL == nil, "unrelated event URL keeps the Calendar fallback")
let clicks = MeetingClickHost()
clicks.click(starting.notices[0])
clicks.click(linkedReminder.notices[0])
expect(NSWorkspace.shared.opened.map(\.absoluteString) == [joinLink, joinLink]
       && clicks.dismissed == 2 && clicks.calendars == 0,
       "both meeting banners dismiss and open Google Meet directly, not Calendar")
clicks.click(missingLink.notices[0])
expect(clicks.calendars == 1 && NSWorkspace.shared.opened.count == 2,
       "only a meeting without a call link opens Calendar")
print("PASS: \(checks) agent neon checks")
'''
for token, value in [("SIGNATURE", signature), ("DURATION", duration), ("SIGNAL", signal),
                     ("ELECTRIC_PROFILE", charging_signal), ("CHARGE", charge),
                     ("RECEIVE", receive), ("APPEARANCE", appearance), ("RENDERING", rendering),
                     ("PROVIDER_COLORS", provider_colors), ("PROGRESS_ADVANCING", progress_advancing),
                     ("MEETING_CLICK", meeting_click), ("MEETING_HANDLER", meeting_handler), ("REMINDER_HANDLER", reminder_handler),
                     ("NOTICE_CAN_PRESENT", notice_can_present), ("NOTICE_CHANGED", notice_changed)]:
    swift = swift.replace(token, value)

with tempfile.TemporaryDirectory(prefix="notch-agent-neon-") as directory:
    path = Path(directory)
    (path / "main.swift").write_text(swift)
    subprocess.run(["swiftc", str(path / "main.swift"), "-o", str(path / "checks")], check=True)
    subprocess.run([str(path / "checks")], check=True)
