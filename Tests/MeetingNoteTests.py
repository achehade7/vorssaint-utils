#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Production note writer and draft, temporary files; no calendar/browser access."""
from pathlib import Path
import os
import subprocess
import tempfile
import sys

repo = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import Combine

var checks = 0
func expect(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    checks += 1
    if try !condition() { fatalError(message) }
}
func wait(_ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition(), Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    precondition(condition(), "async operation finished")
}
let fm = FileManager.default
let root = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MEETING_NOTE_TEST_ROOT"]!).resolvingSymlinksInPath()
try fm.createDirectory(at: root.appendingPathComponent("meetings"), withIntermediateDirectories: true)
try fm.createDirectory(at: root.appendingPathComponent("templates"), withIntermediateDirectories: true)
defer { try? fm.removeItem(at: root) }
let template = """
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

Purpose prompt.

## Notes

Notes prompt.

## Decisions

Decision prompt.

## Follow-ups

Follow-up prompt.
"""
try template.write(to: root.appendingPathComponent("templates/Meeting.md"), atomically: true, encoding: .utf8)
let store = MeetingNoteStore(vault: root)
let format = DateFormatter(); format.dateFormat = "yyyy-MM-dd HH:mm"; format.locale = Locale(identifier: "en_US_POSIX")
let start = format.date(from: "2026-10-22 14:00")!
let berlin = TimeZone(identifier: "Europe/Berlin")!
let iso = ISO8601DateFormatter()
let reference = iso.date(from: "2026-10-21T11:30:00Z")!
let external = "5kn4208capdumknrj3p8s9dfo0@google.com"
try expect(MeetingNoteKey.google(externalIdentifier: external, start: reference, timeZone: berlin) == "5kn4208capdumknrj3p8s9dfo0 2026-10-21T13:30", "Google ID plus local ISO start, with no private EventKit identifier")
try expect(MeetingNoteKey.google(externalIdentifier: external, start: iso.date(from: "2026-10-28T12:30:00Z")!, timeZone: berlin) == "5kn4208capdumknrj3p8s9dfo0 2026-10-28T13:30", "same series ID across the daylight-saving change")
try expect(MeetingNoteKey.google(externalIdentifier: external, start: reference.addingTimeInterval(1800), timeZone: berlin)?.hasSuffix("T14:00") == true, "moved occurrence uses actual start")
for invalid in [nil, "", "private-local-id", "person@example.com", "imported_uid@google.com", "abc@google.com", "abcde@google.com.evil"] as [String?] {
    try expect(MeetingNoteKey.google(externalIdentifier: invalid, start: reference) == nil, "unavailable/unrecognized external IDs use name fallback")
}
let people = [MeetingNotePerson(name: "Anwar Chehade", isCurrentUser: true), MeetingNotePerson(name: "Andreas Braun"), MeetingNotePerson(name: "private@example.com")]
let input = MeetingNoteInput(identity: MeetingNoteKey.google(externalIdentifier: "5kn4208capdumknrj3p8s9dfo0@google.com", start: start), title: "Anwar / Andreas", start: start, end: start.addingTimeInterval(1800), people: people)
let topic = MeetingNoteStore.suggestedTopic(input)
print("Suggested topic:", topic)
try expect(topic == "A.B. one-on-one", "initials use attendee full name; self is omitted")
try expect(MeetingNoteStore.purpose(input) == "14:00–14:30, A.C., A.B.", "Purpose uses time and initials only")
let unsafe = MeetingNoteStore.topic("../../Anwar / Andreas: \"check\" <x> | ? * [y] #test private@example.com +49 123 456789 https://example.com/private", people: people)
try expect(!unsafe.contains("/") && !unsafe.contains(":") && !unsafe.hasPrefix(".") && !unsafe.contains("@") && !unsafe.contains("123"), "safe filename strips paths and contact data")
try expect(MeetingNoteStore.topic(String(repeating: "é", count: 200), people: []).utf8.count <= 160, "length bounded in bytes")
let firstPreparation = try store.prepare(input, topic: topic)
try expect(firstPreparation.created, "new note reports created")
let note = firstPreparation.file
try expect(try !store.prepare(input, topic: topic).created, "existing note reports ready, not created")
let body = try String(contentsOf: note, encoding: .utf8)
try expect(note.lastPathComponent == "2026-10-22 A.B. one-on-one.md", "dated path")
try expect(body.contains("date: 2026-10-22\n") && body.contains("project: []\n") && body.contains("topics: []\n") && body.contains("folded: false\n"), "template properties filled")
try expect(body.contains("# 2026-10-22 A.B. one-on-one\n") && body.contains("## Purpose\n\n14:00–14:30, A.C., A.B.\n"), "heading and Purpose filled")
try expect(MeetingNoteStore.eventID(in: body) == input.identity, "calendar_event stores occurrence ID")
try expect(body.contains("Notes prompt.") && body.contains("Decision prompt.") && body.contains("Follow-up prompt."), "other template sections kept")
for forbidden in ["Anwar", "Chehade", "Andreas", "Braun", "@", "https://", "{{"] {
    try expect(!body.contains(forbidden), "no raw personal data or placeholders")
}
let before = try Data(contentsOf: note)
let reused = try store.prepare(input, topic: "Different topic").file
try expect(reused == note, "same calendar_event wins despite topic change")
try expect(try Data(contentsOf: note) == before, "existing note never overwritten")
let renamed = root.appendingPathComponent("meetings/Already curated.md")
try fm.moveItem(at: note, to: renamed)
try expect(try store.prepare(input, topic: topic).file == renamed, "same calendar_event reused without rename")
let clash = root.appendingPathComponent("meetings/2026-10-22 Different topic.md")
try "existing unrelated note".write(to: clash, atomically: true, encoding: .utf8)
try expect(try store.prepare(input, topic: "Different topic").file == renamed, "event lookup precedes date/topic collision")
let other = MeetingNoteInput(identity: "event-2", title: "Different topic", start: start, end: start.addingTimeInterval(60), people: [])
try expect(try store.prepare(other, topic: "Different topic").file == clash, "date/topic fallback reuses existing note")
try expect(try String(contentsOf: clash, encoding: .utf8) == "existing unrelated note", "fallback never edits existing file")
for value in ["plain-id", "'single-id'", "\"double-id\""] {
    try expect(MeetingNoteStore.eventID(in: "---\ncalendar_event: \(value)\n---\n") != nil, "reads supported YAML scalar")
}
let manual = root.appendingPathComponent("meetings/Manual.md")
try "---\ncalendar_event: manual-event\n---\nUnchanged".write(to: manual, atomically: true, encoding: .utf8)
let manualInput = MeetingNoteInput(identity: "manual-event", title: "Planning", start: start, end: start, people: [])
try expect(try store.prepare(manualInput, topic: "Planning").file == manual, "manual calendar_event property is recognized")
let tomorrow = MeetingNoteInput(identity: MeetingNoteKey.google(externalIdentifier: "5kn4208capdumknrj3p8s9dfo0@google.com", start: start.addingTimeInterval(86400)), title: "Anwar / Andreas", start: start.addingTimeInterval(86400), end: start.addingTimeInterval(88200), people: people)
let tomorrowNote = try store.prepare(tomorrow, topic: topic).file
try expect(tomorrowNote != renamed && tomorrowNote.lastPathComponent.hasPrefix("2026-10-23"), "recurrence gets a note only for explicitly requested occurrence")
// Map exact Jira properties, not all SAP keys to the same project.
for name in ["sap-support", "abs"] { try fm.createDirectory(at: root.appendingPathComponent("projects/" + name), withIntermediateDirectories: true) }
try "---\njira: [SAP-531]\n---\n".write(to: root.appendingPathComponent("projects/sap-support/ticket.md"), atomically: true, encoding: .utf8)
try "---\njira:\n  - SAP-599\n---\n".write(to: root.appendingPathComponent("projects/abs/ticket.md"), atomically: true, encoding: .utf8)
for (key, project) in [("SAP-531", "sap-support"), ("SAP-599", "abs"), ("SAP-999", "")] {
    let event = MeetingNoteInput(identity: key, title: key + " Review", start: start, end: start, people: [])
    let file = try store.prepare(event, topic: event.title).file
    let property = String(data: try JSONEncoder().encode(project.isEmpty ? [] : [project]), encoding: .utf8)!
    try expect(try String(contentsOf: file, encoding: .utf8).contains("project: " + property + "\n"), "project mapped from existing Jira property")
}
// Title matches use actual top-level project folders and must agree with Jira.
for name in ["platform", "phase.2", "true"] {
    try fm.createDirectory(at: root.appendingPathComponent("projects/" + name), withIntermediateDirectories: true)
}
try fm.createDirectory(at: root.appendingPathComponent("projects/abs/investigations"), withIntermediateDirectories: true)
try "not a folder".write(to: root.appendingPathComponent("projects/readme"), atomically: true, encoding: .utf8)
let projectCases: [(String, [String])] = [
    ("Weekly ABS KT", ["abs"]),
    ("weekly abs kt", ["abs"]),
    ("Weekly (AbS): KT", ["abs"]),
    ("ABS and abs follow-up", ["abs"]),
    ("ABSOLUTE preABS ABS2 _ABS ABS_ éABS ABSé", []),
    ("SAP-SUPPORT review", ["sap-support"]),
    ("Platform planning", ["platform"]),
    ("PHASE.2 review", ["phase.2"]),
    ("phaseX2 review", []),
    ("true planning", ["true"]),
    ("readme investigations review", []),
    ("Unmatched planning", []),
    ("ABS SAP-599 review", ["abs"]),
    ("ABS SAP-999 review", ["abs"]),
    ("ABS SAP-531 review", []),
    ("platform SAP-599 review", []),
    ("ABS sap-support review", []),
    ("ABS sap-support SAP-599 review", []),
    ("SAP-531 SAP-599 review", []),
    ("ABS SAP-531 SAP-599 review", [])
]
for (index, entry) in projectCases.enumerated() {
    let (title, expected) = entry
    let event = MeetingNoteInput(identity: "project-case-\(index)", title: title, start: start, end: start, people: [])
    // Editing the topic does not change the original event-title mapping.
    let file = try store.prepare(event, topic: "Mapping case \(index)").file
    let body = try String(contentsOf: file, encoding: .utf8)
    let property = String(data: try JSONEncoder().encode(expected), encoding: .utf8)!
    try expect(body.contains("project: " + property + "\n"), "project mapping for \(title)")
}
// Preview and Escape cannot write or trigger join callbacks.
let countBefore = try fm.contentsOfDirectory(atPath: root.appendingPathComponent("meetings").path).count
let draft = MeetingNoteDraft(input: input, store: store)
var completed = 0
try expect(draft.cancel(), "Escape cancels an idle draft")
draft.save(allowed: true) { _ in completed += 1 }
RunLoop.main.run(until: Date().addingTimeInterval(0.03))
try expect(completed == 0 && !draft.saving, "cancelled draft cannot create or join")
try expect(try fm.contentsOfDirectory(atPath: root.appendingPathComponent("meetings").path).count == countBefore, "Escape creates no file")
let failing = MeetingNoteDraft(input: input, store: .init(vault: root.appendingPathComponent("missing-vault")))
failing.topic = "Keep draft"
var failureFinished = false
failing.save(allowed: true) { file in precondition(file == nil); failureFinished = true }
wait { failureFinished }
try expect(failing.failed && failing.topic == "Keep draft" && !failing.saving, "failed save keeps editable topic and cannot join")
let denied = MeetingNoteDraft(input: input, store: store)
denied.save(allowed: false) { file in precondition(file == nil) }
try expect(denied.failed && !denied.saving, "expired/permission-revoked guard prevents write")
let success = MeetingNoteDraft(input: input, store: store)
var joined = 0
success.save(allowed: true) { file in precondition(file?.file == renamed && file?.created == false); joined += 1 }
success.save(allowed: true) { _ in joined += 100 }
wait { !success.saving }
try expect(joined == 1, "repeated Return during save completes only once")
let noKey = MeetingNoteInput(identity: nil, title: "No external ID", start: start, end: start, people: [])
let noKeyFile = try store.prepare(noKey, topic: noKey.title).file
try expect(try MeetingNoteStore.eventID(in: String(contentsOf: noKeyFile, encoding: .utf8)) == nil, "no private identifier is written as fallback")
try expect(try store.prepare(noKey, topic: noKey.title).file == noKeyFile, "missing external ID still deduplicates by date/topic")
try expect(try store.prepare(noKey, topic: "Another topic").file != noKeyFile, "blank calendar_event never matches an unrelated note")
// Template failure cannot publish a partial file.
try "broken template".write(to: root.appendingPathComponent("templates/Meeting.md"), atomically: true, encoding: .utf8)
let invalid = MeetingNoteInput(identity: "bad-template", title: "New topic", start: start, end: start, people: [])
do { _ = try store.prepare(invalid, topic: invalid.title).file; fatalError("must reject invalid template") } catch { checks += 1 }
try expect(!fm.fileExists(atPath: root.appendingPathComponent("meetings/2026-10-22 New topic.md").path), "template failure creates no note")

// Optional real-vault fixture, deleted by the Python harness after its checker runs.
if let path = ProcessInfo.processInfo.environment["MEETING_NOTE_CHECK_VAULT"] {
    let actual = MeetingNoteStore(vault: URL(fileURLWithPath: path))
    let fixture = MeetingNoteInput(identity: MeetingNoteKey.google(externalIdentifier: "00000000000000000000000000@google.com", start: start),
                                  title: "Island note validation", start: start, end: start.addingTimeInterval(1800), people: [])
    let file = try actual.prepare(fixture, topic: fixture.title).file
    print("VAULT_FIXTURE=" + file.path)
}
print("PASS: \(checks) meeting-note checks")
'''
with tempfile.TemporaryDirectory(prefix="meeting-note-tests-") as directory:
    main = Path(directory) / "main.swift"
    main.write_text(code)
    binary = Path(directory) / "tests"
    subprocess.run(["swiftc", str(repo / "Sources/Vorssaint/Core/MeetingNotePerson.swift"),
                    str(repo / "Sources/Vorssaint/Core/MeetingNoteKey.swift"),
                    str(repo / "Sources/Vorssaint/Services/CommandBar/MeetingNoteStore.swift"),
                    str(repo / "Sources/Vorssaint/Services/CommandBar/MeetingNoteDraft.swift"), str(main), "-o", str(binary)], check=True)
    env = dict(os.environ, MEETING_NOTE_TEST_ROOT=str((Path(directory) / "vault").resolve()))
    vault = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if vault:
        fixture_path = vault / "meetings/2026-10-22 Island note validation.md"
        if fixture_path.exists():
            raise SystemExit("Validation fixture already exists; refusing to reuse/delete it")
        env["MEETING_NOTE_CHECK_VAULT"] = str(vault)
    try:
        result = subprocess.run([str(binary)], env=env, text=True, capture_output=True)
        print(result.stdout)
        print(result.stderr, end="")
        result.check_returncode()
        if vault:
            created = next(Path(line.removeprefix("VAULT_FIXTURE=")) for line in result.stdout.splitlines() if line.startswith("VAULT_FIXTURE="))
            assert created == fixture_path
            subprocess.run(["python3", "scripts/check-vault.py", str(created.relative_to(vault))], cwd=vault, check=True)
    finally:
        if vault and fixture_path.exists():
            fixture_path.unlink()
