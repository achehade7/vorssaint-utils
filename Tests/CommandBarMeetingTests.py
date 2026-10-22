#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Run the real meeting command with controlled calendar and browser boundaries."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/CommandBar/CommandBarMeetingSearch.swift").read_text()
fixture = r'''
import Foundation
struct NotchCalendarEvent {
    var title = "Planning"
    var start = Date().addingTimeInterval(600)
    var end = Date().addingTimeInterval(2400)
    var meetingURL = URL(string: "https://meet.google.com/abc-defg-hij")
}
enum NotchCalendarSupport {
    static var enabled = true
    static func isEnabled() -> Bool { enabled }
    static func nextMeeting(_ events: [NotchCalendarEvent], now: Date) -> NotchCalendarEvent? { events.first }
}
final class NotchCalendarService {
    static let shared = NotchCalendarService()
    var events = [NotchCalendarEvent()]
    var reads = 0
    func meetingEvents() async -> [NotchCalendarEvent] {
        reads += 1
        let snapshot = events
        try? await Task.sleep(nanoseconds: 50_000_000)
        return snapshot
    }
}
enum EKEventStore {
    enum Status { case fullAccess, denied }
    enum Kind { case event }
    static var status = Status.fullAccess
    static func authorizationStatus(for kind: Kind) -> Status { status }
}
enum L10n { static let shared = Self(); var language: Int { 0 }; init() { self = .instance }; case instance }
enum FeatureStrings {
    struct Strings {
        let title = "Calendar", description = "Setup", allow = "Allow", permission = "Permission"
        let noMeetingLink = "No call", openCalendar = "Open Calendar", untitled = "Untitled"
    }
    static func notchCalendar(_ language: Int) -> Strings { Strings() }
}
final class NotchService {
    enum Module { case calendar }
    static let shared = NotchService()
    var settings = 0, opened = 0
    func openSettings(showing module: Module) { settings += 1 }
    func open(_ module: Module) { opened += 1 }
}
final class Permissions {
    static let shared = Permissions()
    var requests = 0
    func requestCalendar() { requests += 1 }
}
final class NSWorkspace {
    static let shared = NSWorkspace()
    var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
struct CommandBarEntry {
    enum Icon { case symbol(String) }
    let id: String, title: String, subtitle: String, icon: Icon, countsUsage: Bool
    let run: (Int?) -> Void
}
func spin(_ seconds: Double = 0.15) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
let search = CommandBarMeetingSearch()
var deliveries = 0
search.onResult = { deliveries += 1 }
precondition(search.rows().isEmpty && search.isAwaiting)
spin()
let rows = search.rows()
precondition(rows.count == 1 && rows[0].title == "Planning" && rows[0].subtitle.contains("meet.google.com"))
precondition(NSWorkspace.shared.opened.isEmpty && NotchCalendarService.shared.reads == 1)
rows[0].run(nil)
precondition(NSWorkspace.shared.opened.count == 1, "only Return opens a call")
search.reset()
_ = search.rows()
spin(0.01)
search.reset()
let before = deliveries
spin()
precondition(deliveries == before && !search.isAwaiting, "leaving meet discards late calendar reads")
EKEventStore.status = .denied
let permission = search.rows()[0]
precondition(Permissions.shared.requests == 0 && permission.id == "action.meet.permission")
permission.run(nil)
precondition(Permissions.shared.requests == 1)
EKEventStore.status = .fullAccess
NotchCalendarSupport.enabled = false
precondition(search.rows()[0].id == "action.meet.setup")
NotchCalendarSupport.enabled = true
NotchCalendarService.shared.events = []
_ = search.rows(); spin()
precondition(search.rows()[0].id == "action.meet.empty")
search.reset()
NotchCalendarService.shared.events = [NotchCalendarEvent(end: Date().addingTimeInterval(-1))]
_ = search.rows(); spin()
precondition(search.rows()[0].id == "action.meet.empty")
NotchCalendarSupport.enabled = false
rows[0].run(nil)
precondition(NSWorkspace.shared.opened.count == 1, "a stale row cannot join after the feature is disabled")
print("Meeting command: preview, explicit join, cancellation, empty/expired results and permission gates passed")
'''
with tempfile.TemporaryDirectory(prefix="meeting-command-tests-") as temporary:
    folder = Path(temporary)
    swift = folder / "main.swift"
    swift.write_text(source + "\n" + fixture)
    binary = folder / "test"
    subprocess.run(["swiftc", str(swift), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
