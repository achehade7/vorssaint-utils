#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Run clipboard ticket search with controlled pasteboard, saved links and browser."""
from pathlib import Path
import subprocess
import tempfile
repo = Path(__file__).resolve().parents[1]
fixture = r'''
import Foundation
enum CommandBarSearch { static func normalized(_ text: String) -> String { text.lowercased() } }
enum CommandBarSource { case links; var idPrefix: String? { "link." } }
enum DefaultsKey { static let commandBarLinks = "links" }
final class UserDefaults {
    static let standard = UserDefaults()
    var links: Data?
    func data(forKey key: String) -> Data? { links }
}
struct L10n { static let shared = Self(); let language = 0 }
enum FeatureStrings {
    struct Strings { let linksTitle = "Links", openInBrowser = "Open", noResultsTitle = "No results", sourceClipboard = "Clipboard" }
    static func commandBar(_ language: Int) -> Strings { Strings() }
}
final class NSPasteboard {
    enum Kind { case string }
    static let general = NSPasteboard()
    var text: String?, reads = 0
    func string(forType kind: Kind) -> String? { reads += 1; return text }
}
final class GeneralPasteboardAccess {
    static let shared = GeneralPasteboardAccess()
    var pending: (() -> Void)?
    func async<T>(_ work: @escaping () -> T, then completion: @escaping (T) -> Void) { pending = { completion(work()) } }
    func finish() { let work = pending; pending = nil; work?() }
}
final class NSWorkspace {
    static let shared = NSWorkspace()
    var urls: [URL] = []
    func open(_ url: URL) { urls.append(url) }
}
struct CommandBarEntry {
    enum Icon { case symbol(String) }
    let id: String, title: String, subtitle: String, icon: Icon, countsUsage: Bool
    var keepsBarOpen = false
    let run: (Int?) -> Void
}
let search = CommandBarTicketSearch()
let board = NSPasteboard.general
let access = GeneralPasteboardAccess.shared
var deliveries = 0
search.onResult = { deliveries += 1 }
precondition(search.rows()[0].id == "action.jclip.setup" && board.reads == 0)
let link = CommandBarLink(name: "j", kind: .link, destination: "https://example.atlassian.net/browse/{query}")
UserDefaults.standard.links = CommandBarLinks.encode([link])
board.text = "Please check SAP-531, sap-531 and https://example.atlassian.net/browse/OPS-42. Other words stay local."
precondition(search.rows().isEmpty && search.isAwaiting)
access.finish()
let rows = search.rows()
precondition(rows.map(\.title) == ["SAP-531", "OPS-42"], "deduplicate keys while preserving order")
precondition(NSWorkspace.shared.urls.isEmpty, "typing never opens the browser")
rows[1].run(nil)
precondition(NSWorkspace.shared.urls.map(\.absoluteString) == ["https://example.atlassian.net/browse/OPS-42"], "only selected key goes to configured Jira destination")
_ = search.rows()
precondition(board.reads == 1, "no clipboard polling")
search.reset(); _ = search.rows(); search.reset()
let before = deliveries; access.finish()
precondition(deliveries == before && !search.isAwaiting, "late clipboard response is ignored after leaving")
board.text = "2026-10-22 words SAP-0 not-a-ticket"
_ = search.rows(); access.finish()
precondition(search.rows()[0].id == "action.jclip.empty" && search.rows()[0].keepsBarOpen)
precondition(CommandBarTicketSearch.ticketKeys(in: "xSAP-12_foo SAP-123a SAP-123 sap-123") == ["SAP-123"], "reject partial keys")
precondition(CommandBarTicketSearch.ticketKeys(in: (1...20).map { "SAP-\($0)" }.joined(separator: " ")).count == 12)
let direct = CommandBarTicketSearch.directEntry(query: "J sap-531")!
precondition(direct.key == "SAP-531" && direct.entry.title == "Jira · SAP-531")
let clipboardReads = board.reads
let openedBefore = NSWorkspace.shared.urls.count
precondition(CommandBarTicketSearch.directEntry(query: "j SAP-5310")?.key == "SAP-5310")
for invalid in ["j", "j clip", "j SAP-531 extra", "j SAP-0", "j SAP-531!", "note SAP-531"] {
    precondition(CommandBarTicketSearch.directEntry(query: invalid) == nil, "only exact typed keys are handled")
}
precondition(board.reads == clipboardReads && NSWorkspace.shared.urls.count == openedBefore, "typed key neither reads clipboard nor opens browser")
direct.entry.run(nil)
precondition(NSWorkspace.shared.urls.last?.absoluteString == "https://example.atlassian.net/browse/SAP-531", "Return opens configured Jira URL")
UserDefaults.standard.links = CommandBarLinks.encode([])
precondition(CommandBarTicketSearch.directEntry(query: "j SAP-531") == nil, "missing j shortcut is not replaced with a hardcoded site")
print("Ticket command: extraction, deduplication, explicit selection, configured URL, empty input and cancellation passed")
'''
source = (repo/'Sources/Vorssaint/Services/CommandBar/CommandBarLinks.swift').read_text()
source += (repo/'Sources/Vorssaint/Services/CommandBar/CommandBarTicketSearch.swift').read_text()
with tempfile.TemporaryDirectory(prefix='ticket-command-tests-') as directory:
    folder=Path(directory); swift=folder/'main.swift'; binary=folder/'test'
    swift.write_text(source+'\n'+fixture)
    subprocess.run(['swiftc',str(swift),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
