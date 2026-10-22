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
    func close() { closed += 1 }
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
let preparation = draft()
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
service.run(.init(), draft: again, joining: false); wait(again)
precondition(workspace.opened.last?.scheme == "obsidian" && notices.notices.last?.detail == "Note ready")
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
print("PASS: prepare/open, join/reuse, preserved contents, shortcut isolation, cancellation, permission, expiry and save-failure flows")
'''.replace("CONFIRMATION", confirmation)
with tempfile.TemporaryDirectory(prefix="meeting-note-flow-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(fixture)
    binary = folder / "test"
    sources = ["Core/MeetingNotePerson.swift", "Services/CommandBar/MeetingNoteStore.swift", "Services/CommandBar/MeetingNoteDraft.swift"]
    subprocess.run(["swiftc", *(str(repo / "Sources/Vorssaint" / p) for p in sources), str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(folder / "vault")], check=True)
