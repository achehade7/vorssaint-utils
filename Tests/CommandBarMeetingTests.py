#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Run the real meeting command with controlled calendar and browser boundaries."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/CommandBar/CommandBarMeetingSearch.swift").read_text()
# Advance row rendering and activation across the exact five-minute boundary.
source = source.replace("Date()", "meetingClock")
strings = (repo / "Sources/Vorssaint/Core/MeetingNoteStrings.swift").read_text()
fixture = r'''
import Foundation
var meetingClock = Date()
struct NotchCalendarEvent {
    var id = UUID().uuidString
    var allDay = false
    var title = "Planning"
    var start = Date().addingTimeInterval(600)
    var end = Date().addingTimeInterval(2400)
    var meetingURL = URL(string: "https://meet.google.com/abc-defg-hij")
}
enum CommandBarNoteSearch {
    static func matches(_ title: String, filter: String) -> Bool {
        filter.lowercased().split(separator: " ").allSatisfy { title.lowercased().contains($0) }
    }
}
final class MeetingNoteService {
    static let shared = MeetingNoteService()
    var prepared: [String] = []
    func show(_ event: NotchCalendarEvent, joining: Bool) { precondition(!joining); prepared.append(event.id) }
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
enum AppLanguage: String, CaseIterable { case enUS = "en-US", ptBR = "pt-BR", tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans = "zh-Hans", zhTW = "zh-TW", zhHK = "zh-HK" }
struct L10n { static var shared = Self(); var language = AppLanguage.enUS }
enum FeatureStrings {
    struct Strings {
        let title = "Calendar", description = "Setup", allow = "Allow", permission = "Permission"
        let noMeetingLink = "No call", openCalendar = "Open Calendar", untitled = "Untitled", ongoing = "Happening now", noResultsTitle = "No results"
    }
    static func notchCalendar(_ language: AppLanguage) -> Strings { Strings() }
    static func commandBar(_ language: AppLanguage) -> Strings { Strings() }
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
_ = search.rows(); spin()
let choices = search.rows()
precondition(choices.count == 3 && Set(choices.map(\.id)).count == 3, "overlapping events remain separate selectable rows")
precondition(choices.prefix(2).allSatisfy { $0.subtitle.hasPrefix("Just started") }, "just-started meetings are labelled")
precondition(choices[2].title == "Next" && search.rows().count == 3, "bare meet offers the next three joinable meetings")
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
NotchCalendarSupport.enabled = true
search.reset()
NotchCalendarService.shared.events = [
    NotchCalendarEvent(id: "1", title: "First"),
    NotchCalendarEvent(id: "2", title: "Second"),
    NotchCalendarEvent(id: "3", title: "Third"),
    NotchCalendarEvent(id: "4", title: "ABS weekly KT", meetingURL: nil),
    NotchCalendarEvent(id: "5", title: "ABS weekly KT", end: Date().addingTimeInterval(-1)),
    NotchCalendarEvent(id: "6", allDay: true, title: "ABS weekly KT")
]
_ = search.rows(limit: 3, noteFilter: ""); spin()
precondition(search.rows(limit: 3, noteFilter: "").count == 3, "bare note offers three")
let filtered = search.rows(limit: 40, noteFilter: "weekly abs")
precondition(filtered.count == 1 && filtered[0].id == "action.note.upcoming.4", "filter before limit, any word order; no call link required")
let callsBefore = NSWorkspace.shared.opened.count
precondition(MeetingNoteService.shared.prepared.isEmpty, "typing never prepares notes")
filtered[0].run(nil)
precondition(MeetingNoteService.shared.prepared == ["4"] && NSWorkspace.shared.opened.count == callsBefore, "note opens the note flow without joining")
precondition(search.noteEvent(entryID: filtered[0].id) == nil, "Cmd-Return does not turn note preparation into a call")
EKEventStore.status = .denied
filtered[0].run(nil)
precondition(MeetingNoteService.shared.prepared.count == 1, "stale note result respects revoked permission")
EKEventStore.status = .fullAccess
let clock = Date(timeIntervalSince1970: 1_800_000_000)
meetingClock = clock
search.reset()
NotchCalendarService.shared.events = [NotchCalendarEvent(id: "rounding", title: "In 80 seconds",
    start: clock.addingTimeInterval(80), end: clock.addingTimeInterval(1800))]
_ = search.rows(); spin()
precondition(search.rows()[0].subtitle.hasPrefix("in 2 min"), "80 remaining seconds round up to two minutes")
precondition(search.rows(noteFilter: "")[0].subtitle.hasPrefix("in 2 min"), "note uses the same ceiling countdown")

search.reset()
NotchCalendarService.shared.events = [
    NotchCalendarEvent(id: "old", title: "Older ongoing", start: clock.addingTimeInterval(-301), end: clock.addingTimeInterval(1800)),
    NotchCalendarEvent(id: "late", title: "Late join", start: clock.addingTimeInterval(-300), end: clock.addingTimeInterval(1800)),
    NotchCalendarEvent(id: "next", title: "Upcoming", start: clock.addingTimeInterval(120), end: clock.addingTimeInterval(1800)),
    NotchCalendarEvent(id: "ended", title: "Ended", start: clock.addingTimeInterval(-60), end: clock)
]
_ = search.rows(); spin()
let lateMeet = search.rows(), lateNote = search.rows(noteFilter: "")
precondition(lateMeet.map(\.id) == ["action.meet.late", "action.meet.next"], "meet keeps the exact five-minute late-join boundary and excludes older or ended events")
precondition(lateNote.map(\.id) == ["action.note.upcoming.late", "action.note.upcoming.next"], "note keeps the same late-join window")
precondition(lateMeet[0].subtitle.hasPrefix("Started 5 min. ago") && lateNote[0].subtitle.hasPrefix("Started 5 min. ago"), "late suggestions state when the meeting started")
precondition(search.noteEvent(entryID: lateMeet[0].id)?.id == "late", "late Cmd-Return preserves the exact calendar occurrence")
let joinedBefore = NSWorkspace.shared.opened.count, preparedBefore = MeetingNoteService.shared.prepared.count
lateMeet[0].run(nil); lateNote[0].run(nil)
precondition(NSWorkspace.shared.opened.count == joinedBefore + 1 && MeetingNoteService.shared.prepared.last == "late", "late rows retain their explicit join and note actions")
meetingClock = clock.addingTimeInterval(0.001)
precondition(search.rows().map(\.id) == ["action.meet.next"] && search.rows(noteFilter: "").map(\.id) == ["action.note.upcoming.next"], "both lists stop suggesting the occurrence after five minutes")
precondition(search.noteEvent(entryID: lateMeet[0].id) == nil, "expired late suggestion cannot prepare through Cmd-Return")
lateMeet[0].run(nil); lateNote[0].run(nil)
precondition(NSWorkspace.shared.opened.count == joinedBefore + 1 && MeetingNoteService.shared.prepared.count == preparedBefore + 1, "stale late rows cannot activate after their suggestion window")
meetingClock = clock
for seconds in [0.001, 59.999, 60, 60.001, 80, 120, 120.001, 3599.999] {
    search.reset()
    NotchCalendarService.shared.events = [NotchCalendarEvent(id: "round", start: clock.addingTimeInterval(seconds), end: clock.addingTimeInterval(7200))]
    _ = search.rows(); spin()
    let prefix = "in \(Int(ceil(seconds / 60))) min"
    precondition(search.rows()[0].subtitle.hasPrefix(prefix) && search.rows(noteFilter: "")[0].subtitle.hasPrefix(prefix), "both commands round upcoming fractional minutes upward at each boundary")
}
for seconds in [0.0, -0.001, -59.999, -60, -299.999] {
    search.reset()
    NotchCalendarService.shared.events = [NotchCalendarEvent(id: "recent", start: clock.addingTimeInterval(seconds), end: clock.addingTimeInterval(7200))]
    _ = search.rows(); spin()
    let prefix = seconds > -60 ? "Just started" : "Started \(Int(-seconds / 60)) min. ago"
    precondition(search.rows()[0].subtitle.hasPrefix(prefix) && search.rows(noteFilter: "")[0].subtitle.hasPrefix(prefix), "both commands clearly label the elapsed time since starting")
}
search.reset()
NotchCalendarService.shared.events = [NotchCalendarEvent(id: "note-only", title: "Local discussion", start: clock.addingTimeInterval(-120), end: clock.addingTimeInterval(1800), meetingURL: nil)]
_ = search.rows(noteFilter: "local"); spin()
precondition(search.rows(noteFilter: "local").first?.id == "action.note.upcoming.note-only", "a recent meeting without a call URL still supports note preparation")
precondition(search.rows().first?.id == "action.meet.empty", "late-join window does not invent missing call URLs")
for language in AppLanguage.allCases {
    precondition(!MeetingNoteStrings.started(nil, language).isEmpty && MeetingNoteStrings.started("relative-time", language).contains("relative-time"), "all languages preserve the localized relative time")
}
let previousTimeZone = NSTimeZone.default
NSTimeZone.default = TimeZone(identifier: "Europe/Berlin")!
defer { NSTimeZone.default = previousTimeZone }
let iso = ISO8601DateFormatter()
for (nowText, startText, prefix) in [
    ("2026-10-23T12:04:00+02:00", "2026-10-26T11:45:00+01:00", "in 3 days"),
    ("2026-10-23T23:30:00+02:00", "2026-10-24T01:00:00+02:00", "in 1 day"),
    ("2026-10-24T12:00:00+02:00", "2026-10-25T12:00:00+01:00", "in 1 day"),
    ("2026-03-28T12:00:00+01:00", "2026-03-29T12:00:00+02:00", "in 1 day"),
    ("2026-10-24T23:30:00+02:00", "2026-10-26T00:15:00+01:00", "in 2 days"),
    ("2026-10-31T23:00:00+01:00", "2026-11-02T00:15:00+01:00", "in 2 days"),
    ("2026-10-23T23:30:00+02:00", "2026-10-24T00:15:00+02:00", "in 45 min"),
    ("2026-10-23T12:04:00+02:00", "2026-10-23T14:04:00+02:00", "in 2 hr")
] {
    meetingClock = iso.date(from: nowText)!
    let starts = iso.date(from: startText)!
    search.reset()
    NotchCalendarService.shared.events = [NotchCalendarEvent(id: "calendar-day", start: starts, end: starts.addingTimeInterval(3600))]
    _ = search.rows(); spin()
    precondition(search.rows()[0].subtitle.hasPrefix(prefix), "meet uses calendar-day distance across midnight and DST while preserving short countdowns: \(nowText) → \(startText)")
    precondition(search.rows(noteFilter: "")[0].subtitle.hasPrefix(prefix), "note uses the same calendar-aware label")
}
print("Meeting command: calendar-day labels across midnight/DST, ceiling countdowns, five-minute late join in meet/note, elapsed labels, exact identity, stale actions, cancellation and permission gates passed")
'''
with tempfile.TemporaryDirectory(prefix="meeting-command-tests-") as temporary:
    folder = Path(temporary)
    swift = folder / "main.swift"
    swift.write_text(source + "\n" + strings + "\n" + fixture)
    binary = folder / "test"
    subprocess.run(["swiftc", str(swift), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
