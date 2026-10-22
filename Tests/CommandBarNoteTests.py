#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise production local-note search against an isolated vault and URL sink."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import Foundation
struct L10n { static let shared = Self(); let language = 0 }
enum FeatureStrings {
    struct Text { let noResultsTitle = "No results" }
    static func commandBar(_ language: Int) -> Text { Text() }
}
enum MeetingNoteStrings { static func readFailure(_ language: Int) -> String { "Could not read meeting notes" } }
struct CommandBarEntry {
    enum Icon { case symbol(String) }
    let id: String, title: String, subtitle: String, icon: Icon, countsUsage: Bool
    var keepsBarOpen = false
    let run: (Int?) -> Void
}
final class NSWorkspace {
    static let shared = NSWorkspace()
    var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
var checks = 0
func expect(_ value: @autoclosure () throws -> Bool, _ message: String) rethrows {
    checks += 1; if try !value() { fatalError(message) }
}
let root = URL(fileURLWithPath: CommandLine.arguments[1]).resolvingSymlinksInPath()
let fm = FileManager.default
func write(_ path: String, _ body: String) throws {
    let file = root.appendingPathComponent(path)
    try fm.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
    try body.write(to: file, atomically: true, encoding: .utf8)
}
try write("meetings/2026-10-16 ABS weekly KT.md", "---\ndate: 2026-10-16\n---\nNotes")
try write("meetings/Renamed ABS weekly.md", "---\ndate: '2026-10-22'\n---\nNotes")
try write("meetings/2026-10-21 SAP-531 review.md", "---\ndate: 2026-10-21\n---\nNotes")
try write("projects/SAP-531 Tax check.md", "---\njira: [SAP-531]\n---\nNotes")
try write("reference/Tax behavior.md", "See https://example.test/browse/sap-531.")
try write("projects/Other.md", "SAP-5310 SAP-531x SAP-531_extra")
try write(".private/SAP-531.md", "hidden")
try write("meetings/.hidden.md", "hidden")
let outside = root.deletingLastPathComponent().appendingPathComponent("SAP-531-secret.md")
try "outside".write(to: outside, atomically: true, encoding: .utf8)
try fm.createSymbolicLink(at: root.appendingPathComponent("meetings/SAP-531 linked.md"), withDestinationURL: outside)

expect(CommandBarNoteSearch.query("NOTE weekly abs")?.filter == "weekly abs", "free-text filter")
expect(CommandBarNoteSearch.query("note prev weekly abs")?.previous == true, "history mode")
expect(CommandBarNoteSearch.query("noteworthy") == nil, "whole command token")
expect(CommandBarNoteSearch.query("note preview")?.previous == false, "prev is a whole token")
expect(CommandBarNoteSearch.matches("ABS Wéekly KT", filter: "weekly abs"), "case, accents, any word order")
expect(!CommandBarNoteSearch.matches("ABS monthly", filter: "weekly abs"), "all words required")
let history = try CommandBarNoteSearch.read(vault: root, request: .previous("weekly abs"))
expect(history.map(\.title) == ["Renamed ABS weekly", "2026-10-16 ABS weekly KT"], "history sorted by meeting date, including renamed files")
let tickets = try CommandBarNoteSearch.read(vault: root, request: .ticket("SAP-531"))
expect(tickets.count == 3, "exact key in title or body; no partial keys, hidden files or symlinks")
expect(tickets.prefix(2).allSatisfy(\.titleMatch) && !tickets[2].titleMatch, "title matches precede body mentions")
let search = CommandBarNoteSearch(vault: root)
var deliveries = 0
search.onResult = { deliveries += 1 }
func wait() {
    let deadline = Date().addingTimeInterval(5)
    while search.isAwaiting, Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    precondition(!search.isAwaiting)
}
expect(search.rows(for: .previous("weekly abs")).isEmpty && search.isAwaiting, "asynchronous search")
wait()
let rows = search.rows(for: .previous("weekly abs"))
expect(rows.count == 2 && NSWorkspace.shared.opened.isEmpty, "typing only reads")
rows[0].run(nil)
let opened = URLComponents(url: NSWorkspace.shared.opened[0], resolvingAgainstBaseURL: false)!
expect(opened.scheme == "obsidian" && opened.queryItems?.first?.value == history[0].file.path, "Return opens selected note through Obsidian")
expect(deliveries == 1, "same query reuses results while open")
search.reset()
_ = search.rows(for: .previous("weekly"))
_ = search.rows(for: .ticket("SAP-531"))
wait()
expect(deliveries == 2 && search.rows(for: .ticket("SAP-531")).count == 3, "changed query discards stale results")
search.reset()
_ = search.rows(for: .previous("")); search.reset()
RunLoop.main.run(until: Date().addingTimeInterval(0.1))
expect(deliveries == 2 && !search.isAwaiting, "closing discards pending reads")
_ = search.rows(for: .previous("missing")); wait()
expect(search.rows(for: .previous("missing"))[0].keepsBarOpen, "empty history is an inert row")
_ = search.rows(for: .ticket("SAP-999")); wait()
expect(search.rows(for: .ticket("SAP-999")).isEmpty, "no local ticket matches leaves Jira alone")
try fm.removeItem(at: history[0].file)
try fm.createSymbolicLink(at: history[0].file, withDestinationURL: outside)
rows[0].run(nil)
expect(NSWorkspace.shared.opened.count == 1, "activation rechecks confinement")
print("PASS: \(checks) note search checks")
'''
with tempfile.TemporaryDirectory(prefix="command-note-tests-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(fixture)
    binary = folder / "test"
    sources = ["Core/MeetingNotePerson.swift", "Services/CommandBar/MeetingNoteStore.swift",
               "Services/CommandBar/CommandBarNoteSearch.swift"]
    subprocess.run(["swiftc", *(str(repo / "Sources/Vorssaint" / p) for p in sources), str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(folder / "vault")], check=True)
