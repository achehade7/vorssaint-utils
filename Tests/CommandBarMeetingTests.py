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
    var id = UUID().uuidString
    var allDay = false
    var title = "Planning"
    var start = Date().addingTimeInterval(600)
    var end = Date().addingTimeInterval(2400)
    var meetingURL = URL(string: "https://meet.google.com/abc-defg-hij")
}
enum NotchCalendarSupport {
    static var enabled = true
    static func isEnabled() -> Bool { enabled }
    static func upcoming(_ events: [NotchCalendarEvent], now: Date) -> [NotchCalendarEvent] { events.filter { $0.end > now }.sorted { $0.start < $1.start } }
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
enum L10n { static let shared = Self(); var language: Language { .init() }; struct Language { var rawValue = "en-US" }; init() { self = .instance }; case instance }
enum FeatureStrings {
    struct Strings {
        let title = "Calendar", description = "Setup", allow = "Allow", permission = "Permission"
        let noMeetingLink = "No call", openCalendar = "Open Calendar", untitled = "Untitled", ongoing = "Happening now"
    }
    static func notchCalendar(_ language: L10n.Language) -> Strings { Strings() }
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
search.reset()
let simultaneous = Date().addingTimeInterval(-30)
NotchCalendarService.shared.events = [
    NotchCalendarEvent(id: "a", title: "Parallel A", start: simultaneous),
    NotchCalendarEvent(id: "b", title: "Parallel B", start: simultaneous),
    NotchCalendarEvent(id: "c", title: "Next", start: Date().addingTimeInterval(1200)),
    NotchCalendarEvent(id: "d", title: "Later", start: Date().addingTimeInterval(2400)),
    NotchCalendarEvent(allDay: true, title: "All day"),
    NotchCalendarEvent(title: "No call", meetingURL: nil)
]
_ = search.rows(limit: 3); spin()
let choices = search.rows(limit: 3)
precondition(choices.count == 3 && Set(choices.map(\.id)).count == 3, "overlapping events remain separate selectable rows")
precondition(choices.prefix(2).allSatisfy { $0.subtitle.contains("Happening now") }, "ongoing meetings are labelled")
precondition(choices[2].title == "Next" && search.rows().count == 1, "meet remains one result; meet next offers three")
precondition(search.noteEvent(entryID: choices[0].id)?.id == "a", "Cmd-Return resolves the selected meeting only")
precondition(search.noteEvent(entryID: "action.meet.empty") == nil, "placeholder cannot prepare a note")
EKEventStore.status = .denied
precondition(search.noteEvent(entryID: choices[0].id) == nil, "revoked calendar access blocks note preparation")
EKEventStore.status = .fullAccess
let readCount = NotchCalendarService.shared.reads
_ = search.rows(limit: 3)
precondition(NotchCalendarService.shared.reads == readCount, "switching list size does not add a calendar read")
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
