#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native primary/Command click routing; no personal calendar, vault, or browser."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
service = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()
view = (repo / "Sources/Vorssaint/UI/Notch/NotchView.swift").read_text()
start = service.index("        if selectedNotice.meetingReminder {")
end, depth = service.index("{", start) + 1, 1
while depth:
    depth += (service[end] == "{") - (service[end] == "}")
    end += 1
handler = service[start:end]
action = next(line.strip() for line in view.splitlines() if "service.activateNotice(notice, modifiers:" in line)
code = r'''
import AppKit
import SwiftUI
import CoreGraphics
var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    checks += 1
    if !condition() { fatalError(message) }
}
struct NotchNotice: Equatable {
    var meetingReminder = true
    var meetingURL: URL? = URL(string: "https://meet.google.com/abc-defg-hij")
    var meetingCalendarItemIdentifier: String? = "calendar-item"
    var meetingStart: Date? = Date().addingTimeInterval(60)
}
struct NotchCalendarEvent: Equatable {
    var calendarItemIdentifier: String
    var start: Date
    var end = Date().addingTimeInterval(1800)
    var meetingURL: URL?
    var allDay = false
    var noteEventKey = "exact-note-identity"
}
final class NotchCalendarService {
    static let shared = NotchCalendarService()
    var events: [NotchCalendarEvent] = [], reads = 0
    func meetingEvents() async -> [NotchCalendarEvent] { reads += 1; return events }
}
final class MeetingNoteService {
    static let shared = MeetingNoteService()
    var prepared: [NotchCalendarEvent] = []
    func show(_ event: NotchCalendarEvent) { prepared.append(event) }
}
final class NSWorkspace {
    static let shared = NSWorkspace()
    var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
final class ClickHost {
    enum Page { case calendar }
    var notice: NotchNotice?
    var dismissed = 0, calendars = 0
    var modifiers: [NSEvent.ModifierFlags] = []
    func dismissNotice() { dismissed += 1; notice = nil }
    func open(_ page: Page) { calendars += 1 }
    func activateNotice(_ selectedNotice: NotchNotice, modifiers: NSEvent.ModifierFlags = []) {
        self.modifiers.append(modifiers)
        guard notice == selectedNotice else { return }
HANDLER
    }
}
let session = CGSessionCopyCurrentDictionary() as? [String: Any]
guard session?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native meeting reminder clicks require an unlocked Mac. No input was sent.\n", stderr)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let notice = NotchNotice(), service = ClickHost()
let calendar = NotchCalendarService.shared, notes = MeetingNoteService.shared, workspace = NSWorkspace.shared
let event = NotchCalendarEvent(calendarItemIdentifier: notice.meetingCalendarItemIdentifier!, start: notice.meetingStart!, meetingURL: notice.meetingURL)
calendar.events = [event]
let button = Button {
    ACTION
} label: { Text("Planning · 1 min").frame(width: 300, height: 60) }.buttonStyle(.plain)
let host = NSHostingView(rootView: button)
let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 300, height: 60), styleMask: [.titled], backing: .buffered, defer: false)
window.contentView = host
window.makeKeyAndOrderFront(nil)
app.activate(ignoringOtherApps: true)
func drain() {
    let end = Date().addingTimeInterval(0.15)
    while Date() < end {
        if let event = app.nextEvent(matching: .any, until: Date().addingTimeInterval(0.01), inMode: .default, dequeue: true) {
            app.sendEvent(event)
        }
        RunLoop.main.run(until: Date().addingTimeInterval(0.002))
    }
}
drain()
func click(_ modifiers: NSEvent.ModifierFlags) {
    for type: NSEvent.EventType in [.leftMouseDown, .leftMouseUp] {
        let event = NSEvent.mouseEvent(with: type, location: NSPoint(x: 150, y: 30), modifierFlags: modifiers,
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
        // Only this test process receives input; no global key or mouse events.
        app.postEvent(event, atStart: false)
    }
    drain()
}
service.notice = notice
click([])
expect(service.modifiers.count == 1 && !service.modifiers[0].contains(.command), "ordinary mouse event reaches the production notice action")
expect(workspace.opened == [notice.meetingURL!] && service.dismissed == 1, "ordinary click dismisses the reminder and joins once")
expect(calendar.reads == 0 && notes.prepared.isEmpty, "ordinary click does not prepare a note")
service.notice = notice
click(.command)
expect(service.modifiers.last?.contains(.command) == true, "the clicked event's Command flag reaches the production action")
expect(calendar.reads == 1 && notes.prepared == [event], "Command-click resolves the exact occurrence for the existing Prepare & join service")
expect(workspace.opened.count == 1 && service.dismissed == 2, "Command-click does not join before confirmation")
expect(notes.prepared[0].noteEventKey == "exact-note-identity", "the existing calendar note identity survives the click")
calendar.events = []
service.notice = notice
click(.command)
expect(service.calendars == 1 && notes.prepared.count == 1 && workspace.opened.count == 1, "a deleted event opens Calendar without joining or creating a note")
service.notice = nil
click(.command)
expect(calendar.reads == 2 && notes.prepared.count == 1, "a departing reminder cannot prepare a stale note")
window.orderOut(nil)
print("PASS: \(checks) native meeting reminder click checks")
'''.replace("HANDLER", handler).replace("ACTION", action)
with tempfile.TemporaryDirectory(prefix="meeting-reminder-ui-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(code)
    binary = folder / "checks"
    subprocess.run(["swiftc", str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
