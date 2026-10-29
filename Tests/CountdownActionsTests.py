#!/usr/bin/env python3
"""Exercise production countdown actions without opening calls or vault notes."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Sources/Vorssaint/Services/Notch/NotchService.swift').read_text()
start = source.index('    func activateCountdownEvent(')
opening = source.index('{', start)
end, depth = opening + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
method = source[start:end]
fixture = r'''
import AppKit
struct Event: Equatable {
    var id = "clicked-occurrence"
    var allDay = false
    var end = Date().addingTimeInterval(1200)
    var meetingURL: URL? = URL(string: "https://meet.google.com/example")
}
struct Countdown { let event: Event }
final class NotchCalendarService {
    static let shared = NotchCalendarService()
    var countdown: Countdown? = Countdown(event: Event())
}
enum NotchCalendarSupport {
    static var enabled = true
    static func isEnabled() -> Bool { enabled }
    static func meetingURL(url: URL?, location: String?, notes: String?) -> URL? {
        url?.scheme == "https" && url?.host == "meet.google.com" ? url : nil
    }
}
enum EKEventStore {
    enum Kind { case event }
    enum Status { case fullAccess, denied }
    static var status = Status.fullAccess
    static func authorizationStatus(for: Kind) -> Status { status }
}
final class NSWorkspace {
    static let shared = NSWorkspace()
    var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
final class MeetingNoteService {
    static let shared = MeetingNoteService()
    var prepared: [Event] = []
    func show(_ event: Event) { prepared.append(event) }
}
final class Service {
    var collapsed = 0, calendars = 0
    func collapse() { collapsed += 1 }
    func openCountdownEvent() { calendars += 1 }
    // METHOD
}
let service = Service(), calendar = NotchCalendarService.shared
let event = Event()
calendar.countdown = Countdown(event: event)
service.activateCountdownEvent(modifiers: [])
precondition(NSWorkspace.shared.opened == [event.meetingURL!] && service.collapsed == 1)
precondition(MeetingNoteService.shared.prepared.isEmpty)
service.activateCountdownEvent(modifiers: .command)
precondition(MeetingNoteService.shared.prepared == [event] && NSWorkspace.shared.opened.count == 1)
for condition in 0..<6 {
    var invalid = event
    switch condition {
    case 0: invalid.meetingURL = nil
    case 1: invalid.meetingURL = URL(string: "https://example.com")
    case 2: invalid.end = Date().addingTimeInterval(-1)
    case 3: invalid.allDay = true
    case 4: NotchCalendarSupport.enabled = false
    default: EKEventStore.status = .denied
    }
    calendar.countdown = Countdown(event: invalid)
    service.activateCountdownEvent(modifiers: [])
    service.activateCountdownEvent(modifiers: .command)
    NotchCalendarSupport.enabled = true; EKEventStore.status = .fullAccess
}
calendar.countdown = nil
service.activateCountdownEvent(modifiers: .command)
precondition(service.calendars == 13 && service.collapsed == 2)
precondition(NSWorkspace.shared.opened.count == 1 && MeetingNoteService.shared.prepared == [event])
print("PASS: countdown join, Command-click exact occurrence, and 13 invalid/stale fallback paths")
'''.replace('// METHOD', method)
with tempfile.TemporaryDirectory(prefix='countdown-actions-') as tmp:
    path = Path(tmp)
    (path / 'main.swift').write_text(fixture)
    subprocess.run(['swiftc', str(path / 'main.swift'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
