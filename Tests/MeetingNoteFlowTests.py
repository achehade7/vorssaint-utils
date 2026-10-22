#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Run production note confirmation with real writes and controlled launch/notice sinks."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/CommandBar/MeetingNoteService.swift").read_text()
confirmation = source[source.index("    private func allowed("):source.index("    private func close()")]
fixture = r'''
import Foundation
struct NotchCalendarEvent {
    var end = Date().addingTimeInterval(3600)
    var meetingURL: URL? = URL(string: "https://example.test/call")
}
enum NotchCalendarSupport { static var enabled = true; static func isEnabled() -> Bool { enabled } }
enum EKEventStore {
    enum Status { case fullAccess, denied }; enum Kind { case event }
    static var status = Status.fullAccess
    static func authorizationStatus(for: Kind) -> Status { status }
}
final class NSWorkspace {
    static let shared = NSWorkspace(); var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
struct L10n { static let shared = Self(); let language = 0 }
enum MeetingNoteStrings {
    struct Text { let created = "Note created", ready = "Note ready" }
    static func localized(_ language: Int) -> Text { Text() }
    static func readFailure(_ language: Int) -> String { "Could not read meeting notes" }
}
struct NotchNotice {
    enum Event { case capture }
    let event: Event, title: String, detail: String, symbol: String, fileURL: URL?, meetingNote: Bool
}
final class NotchService {
    static let shared = NotchService(); var failures = 0; var notices: [NotchNotice] = []
    func signalQuickCapture(success: Bool) { precondition(!success); failures += 1 }
    func show(_ notice: NotchNotice) -> Bool { notices.append(notice); return true }
}
final class MeetingNoteService {
    var closed = 0, kept: [URL?] = []
    var draft: MeetingNoteDraft?
    var previews = 0
    func close() { closed += 1; draft = nil }
    func showPreview(_ event: NotchCalendarEvent, draft: MeetingNoteDraft, joining: Bool) {
        precondition(!joining); previews += 1
    }
    func begin(_ event: NotchCalendarEvent, draft: MeetingNoteDraft) {
        self.draft = draft; openOrAsk(event, draft: draft)
    }
    func keepShortcut(_ link: URL?, until: Date) { kept.append(link) }
    func run(_ event: NotchCalendarEvent, draft: MeetingNoteDraft, joining: Bool) { confirm(event, draft: draft, joining: joining) }
CONFIRMATION
}
let root = URL(fileURLWithPath: CommandLine.arguments[1])
let fm = FileManager.default
try fm.createDirectory(at: root.appendingPathComponent("meetings"), withIntermediateDirectories: true)
try fm.createDirectory(at: root.appendingPathComponent("templates"), withIntermediateDirectories: true)
try """
---
type: meeting
date: {{date:YYYY-MM-DD}}
calendar_event:
project: []
topics: []
folded: false
---
# {{title}}
## Purpose

""".write(to: root.appendingPathComponent("templates/Meeting.md"), atomically: true, encoding: .utf8)
let input = MeetingNoteInput(identity: "occurrence", title: "Weekly project", start: Date(), end: Date().addingTimeInterval(3600), people: [])
let store = MeetingNoteStore(vault: root), service = MeetingNoteService()
let workspace = NSWorkspace.shared, notices = NotchService.shared
func draft() -> MeetingNoteDraft { MeetingNoteDraft(input: input, store: store) }
func wait(_ draft: MeetingNoteDraft) {
    let end = Date().addingTimeInterval(5)
    while draft.saving, Date() < end { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    precondition(!draft.saving)
}
func check(_ value: @autoclosure () throws -> Bool, _ message: String) throws { let result = try value(); precondition(result, message) }
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.15)) }
func files() throws -> [String] { try fm.contentsOfDirectory(atPath: root.appendingPathComponent("meetings").path) }
let cancelledCreation = draft()
service.begin(.init(), draft: cancelledCreation); drain()
precondition(service.previews == 1 && workspace.opened.isEmpty, "missing note asks first")
try check(try files().isEmpty, "lookup and question cannot create a note")
precondition(cancelledCreation.cancel()); service.close()
service.run(.init(), draft: cancelledCreation, joining: false); drain()
try check(try files().isEmpty, "cancelling creation writes nothing")
let preparation = draft()
service.begin(.init(meetingURL: nil), draft: preparation); drain()
precondition(service.previews == 2 && workspace.opened.isEmpty, "missing note without call URL asks too")
try check(try files().isEmpty, "nothing is written before explicit confirmation")
service.run(.init(meetingURL: nil), draft: preparation, joining: false); wait(preparation)
precondition(workspace.opened.count == 1 && workspace.opened[0].scheme == "obsidian", "note preparation opens only Obsidian, even without a call URL")
precondition(service.kept.isEmpty, "preparing a future note preserves the active meeting shortcut")
precondition(notices.notices.last?.detail == "Note created")
let path = URLComponents(url: workspace.opened[0], resolvingAgainstBaseURL: false)!.queryItems![0].value!
let first = try Data(contentsOf: URL(fileURLWithPath: path))
let join = draft()
service.run(.init(), draft: join, joining: true); wait(join)
precondition(workspace.opened.count == 2 && workspace.opened.last?.scheme == "https", "join with notes opens only the call")
precondition(notices.notices.last?.detail == "Note ready" && service.kept.count == 1, "join reuses prepared note and exposes shortcut")
let reused = try Data(contentsOf: URL(fileURLWithPath: path))
precondition(reused == first, "existing content preserved")
let again = draft()
let previewsBefore = service.previews
service.begin(.init(), draft: again); drain()
precondition(workspace.opened.last?.scheme == "obsidian" && service.previews == previewsBefore, "existing note opens directly without a question")
try check(try Data(contentsOf: URL(fileURLWithPath: path)) == first, "opening preserves all note contents")
precondition(service.kept.count == 1, "opening preserves active meeting shortcut")
let openedBeforeLookup = workspace.opened.count
let cancelledLookup = draft()
service.begin(.init(), draft: cancelledLookup); cancelledLookup.cancel(); drain()
precondition(workspace.opened.count == openedBeforeLookup, "cancelled lookup cannot open")
service.begin(.init(), draft: draft()); service.begin(.init(), draft: draft()); drain()
precondition(workspace.opened.count == openedBeforeLookup + 1, "replaced lookup cannot open a stale note")
let openedBeforeDenied = workspace.opened.count
service.begin(.init(), draft: draft()); EKEventStore.status = .denied; drain()
precondition(workspace.opened.count == openedBeforeDenied && service.draft == nil, "permission revocation during lookup blocks opening")
EKEventStore.status = .fullAccess
service.begin(.init(end: Date().addingTimeInterval(-1)), draft: draft()); drain()
precondition(workspace.opened.count == openedBeforeDenied && service.previews == previewsBefore, "ended meeting lookup neither opens nor asks")
let unreadable = MeetingNoteDraft(input: input, store: .init(vault: root.appendingPathComponent("unavailable")))
service.begin(.init(), draft: unreadable); drain()
precondition(workspace.opened.count == openedBeforeDenied && service.previews == previewsBefore, "lookup error cannot be mistaken for a missing note")
precondition(notices.notices.last?.detail == "Could not read meeting notes")
let before = workspace.opened.count
let cancelled = draft(); cancelled.cancel()
service.run(.init(), draft: cancelled, joining: false)
EKEventStore.status = .denied
let denied = draft(); service.run(.init(), draft: denied, joining: false)
precondition(denied.failed && workspace.opened.count == before, "cancelled and permission-revoked flows open nothing")
EKEventStore.status = .fullAccess
let expired = draft(); service.run(.init(end: Date().addingTimeInterval(-1)), draft: expired, joining: false)
let noCall = draft(); service.run(.init(meetingURL: nil), draft: noCall, joining: true)
precondition(expired.failed && noCall.failed && workspace.opened.count == before)
let missing = MeetingNoteDraft(input: input, store: .init(vault: root.appendingPathComponent("missing")))
service.run(.init(), draft: missing, joining: false); wait(missing)
precondition(missing.failed && workspace.opened.count == before, "save failure cannot open a note or call")
print("PASS: direct open, ask-before-create, cancellation without writes, stale lookup, lookup failure, permission/expiry, confirmed create, join/reuse, preserved contents and shortcuts")
'''.replace("CONFIRMATION", confirmation)
with tempfile.TemporaryDirectory(prefix="meeting-note-flow-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(fixture)
    binary = folder / "test"
    sources = ["Core/MeetingNotePerson.swift", "Services/CommandBar/MeetingNoteStore.swift", "Services/CommandBar/MeetingNoteDraft.swift"]
    subprocess.run(["swiftc", *(str(repo / "Sources/Vorssaint" / p) for p in sources), str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(folder / "vault")], check=True)
