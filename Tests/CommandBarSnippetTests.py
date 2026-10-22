#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise production snippet commands with isolated clipboard, storage and UI boundaries."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
struct ColorValue {}
struct GlobalShortcut {}
enum SettingsPage {}
enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, zhHans, zhTW, zhHK, uk }
enum FeatureStrings {
    struct Bar { let copyFailed = "Copy failed" }
    static func commandBar(_ language: AppLanguage) -> Bar { Bar() }
}
struct L10n { static let shared = Self(); let language = AppLanguage.enUS }
enum AppFeature {
    case textSnippets
    static var available = true
    var isAvailable: Bool { Self.available }
}
enum Defaults { static let defaultSnippetSoundName = "Tink" }
enum DefaultsKey { static let textSnippets = "snippets"; static let lastUsedSnippetID = "last" }
final class Store {
    static let standard = Store()
    var stored: Data?
    var lastID: String?
    func string(forKey key: String) -> String? { lastID }
    func set(_ value: String, forKey key: String) { lastID = value }
    func data(forKey key: String) -> Data? { stored }
    func set(_ data: Data, forKey key: String) { stored = data }
}
typealias UserDefaults = Store
final class Pasteboard {
    static let general = Pasteboard()
    enum Kind { case string }
    var value: String?, reads = 0, accepts = true
    func string(forType kind: Kind) -> String? { reads += 1; return value }
    func clearContents() { value = nil }
    func declareVorssaintSource() {}
    func setString(_ text: String, forType kind: Kind) -> Bool {
        guard accepts else { return false }; value = text; return true
    }
}
typealias NSPasteboard = Pasteboard
final class GeneralPasteboardAccess {
    static let shared = GeneralPasteboardAccess()
    var deferred = false
    var pending: (() -> Void)?
    func async<T>(_ work: @escaping () -> T, then completion: @escaping (T) -> Void) {
        let result = work()
        if deferred { pending = { completion(result) } } else { completion(result) }
    }
    func finish() { let run = pending; pending = nil; deferred = false; run?() }
}
enum QuickToolHUD {
    static var message = ""
    static func show(icon: String, message: String) { self.message = message }
}
final class TextSnippetService {
    static let shared = TextSnippetService()
    func syncWithPreferences() {}
}
final class SnippetLibraryService {
    static let shared = SnippetLibraryService()
    enum TemplateAction { case copy, insert }
    func resolveTemplate(_ snippet: TextSnippet, action: TemplateAction, completion: (TextSnippet) -> Void) { completion(snippet) }
    var shown = false, inserted: TextSnippet?
    func syncWithPreferences() {}
    func show() { shown = true }
    func insert(_ snippet: TextSnippet) { inserted = snippet }
}
final class MeetingSearch {
    var selectedID: String?
    func noteEvent(entryID: String) -> String? { entryID == selectedID ? entryID : nil }
}
final class MeetingNoteService {
    static let shared = MeetingNoteService()
    var opened: String?
    func show(_ event: String) { opened = event }
}
final class CommandBarService {
    static let shared = CommandBarService()
    enum Mode: Equatable { case search, confirm }
    var presentationID = UUID(), query = "", mode = Mode.search, isVisible = true
    var selectedEntry: CommandBarEntry?, revealed = false, recorded = false
    let meetingSearch = MeetingSearch()
    func hide() { isVisible = false }
    func recordUsage(of entry: CommandBarEntry) { recorded = true }
    func revealInFinder(_ entry: CommandBarEntry) { revealed = true }
    // COMMAND_RETURN
}
// CATALOG
var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ label: String) {
    checks += 1; precondition(condition(), label)
}
let board = Pasteboard.general, bar = CommandBarService.shared
func stored() -> [TextSnippet] { TextSnippetSupport.decode(Store.standard.stored) }
func row(_ query: String) -> CommandBarEntry {
    bar.query = query; bar.mode = .search; bar.isVisible = true
    return CommandBarSnippetCommands.rows(for: query)!.first!
}
expect(CommandBarSnippetCommands.rows(for: "snippets elsewhere") == nil, "do not steal unrelated queries")
let library = row("snip")
library.run(nil)
RunLoop.main.run(until: Date().addingTimeInterval(0.15))
expect(SnippetLibraryService.shared.shown, "snip opens library")
let help = row("snip save")
help.run(nil)
expect(help.keepsBarOpen && Store.standard.stored == nil, "missing name saves nothing")
board.value = "DE00 TEST\nsecond line"
let create = row("snip save iban")
expect(board.reads == 0 && stored().isEmpty, "typing does not read or save the clipboard")
expect(create.confirmationPrompt == nil, "new name needs no replacement confirmation")
create.run(nil)
expect(stored().count == 1 && stored()[0].replacement == board.value && !bar.isVisible, "save exact multiline clipboard and close")
expect(stored()[0].trigger.isEmpty && stored()[0].showsInLibrary, "new snippet has no automatic trigger and appears in library")
let id = stored()[0].id
board.value = "other copy"
expect(stored()[0].replacement != board.value, "ordinary copying cannot replace saved snippet")
let saved = stored()[0]
expect(row("snip last").id == "action.snippetLast.empty", "saving alone does not count as using a snippet")
let entries = Catalog.snippetEntries(FeatureStrings.commandBar(.enUS))
expect(entries.count == 1 && entries[0].trouble == nil, "copy does not require accessibility")
expect(entries[0].subtitle == CommandBarSnippetCommands.preview(saved), "saved contents appear below the snippet name")
var template = saved; template.replacement = "{{ticket}}: transport {{message}}\n{{clipboard}}"
expect(CommandBarSnippetCommands.preview(template) == "{{ticket}}: transport {{message}} · {{clipboard}}",
       "preview shows placeholders literally without reading or expanding the clipboard")
entries[0].run(nil)
expect(board.value == saved.replacement && SnippetLibraryService.shared.inserted == nil, "Return copies, never inserts")
expect(row("snip last").id == entries[0].id, "last resolves the most recently copied saved identity")
board.value = "another clipboard value"
row("snip last").run(nil)
expect(board.value == saved.replacement, "last copies stored text, not the current clipboard")
bar.isVisible = true; bar.selectedEntry = entries[0]
expect(bar.runCommandReturn(), "Command Return handled for snippet")
expect(!bar.isVisible && SnippetLibraryService.shared.inserted == saved && bar.recorded, "Command Return closes then inserts selected snippet")
bar.mode = .confirm
expect(!bar.runCommandReturn(), "Command Return cannot bypass confirmation")
bar.mode = .search
bar.selectedEntry = CommandBarEntry(id: "file", title: "file", subtitle: "", icon: .symbol("doc"), revealPath: "/tmp", run: { _ in })
expect(bar.runCommandReturn() && bar.revealed, "file reveal still works")
var original = saved; original.trigger = ";iban"; original.folder = "Banking"
Store.standard.stored = TextSnippetSupport.encode([original])
board.value = "replacement"
let replace = row("snip save IBAN")
expect(replace.confirmationPrompt != nil && stored()[0] == original, "case-insensitive duplicate requires confirmation and changes nothing before Return")
replace.run(nil)
expect(stored().count == 1 && stored()[0].id == id && stored()[0].replacement == "replacement", "confirmed replacement updates one identity")
expect(stored()[0].trigger == ";iban" && stored()[0].folder == "Banking", "replacement preserves trigger and folder")
let beforeEmpty = Store.standard.stored
board.value = nil
row("snip save missing").run(nil)
expect(Store.standard.stored == beforeEmpty && bar.isVisible && QuickToolHUD.message == "Copy some text first", "empty clipboard preserves library and field")
board.value = "new"
let stale = row("snip save IBAN")
var changed = stored()[0]; changed.replacement = "edited elsewhere"
Store.standard.stored = TextSnippetSupport.encode([changed])
stale.run(nil)
expect(stored()[0] == changed && bar.isVisible, "concurrent edit cannot be overwritten by stale confirmation")
let newRow = row("snip save newly-created")
var concurrent = TextSnippet(); concurrent.name = "newly-created"; concurrent.replacement = "elsewhere"
Store.standard.stored = TextSnippetSupport.encode([changed, concurrent])
newRow.run(nil)
expect(stored().count == 2 && stored()[1].replacement == "elsewhere", "concurrent name creation cannot bypass confirmation")
let beforeCancel = Store.standard.stored
GeneralPasteboardAccess.shared.deferred = true
row("snip save cancelled").run(nil)
bar.hide(); GeneralPasteboardAccess.shared.finish()
expect(Store.standard.stored == beforeCancel, "closing while clipboard read waits cancels save")
GeneralPasteboardAccess.shared.deferred = true
row("snip save old-session").run(nil)
bar.presentationID = UUID(); GeneralPasteboardAccess.shared.finish()
expect(Store.standard.stored == beforeCancel, "reopening cannot revive old save")
Store.standard.stored = Data("damaged".utf8)
row("snip save recovery").run(nil)
expect(Store.standard.stored == Data("damaged".utf8), "corrupt library is preserved")
Store.standard.stored = TextSnippetSupport.encode([saved])
var templated = saved; templated.replacement = "before {{clipboard}} after"
board.value = "value"
CommandBarSnippetCommands.copy(templated)
expect(board.value == "before value after", "copy expands clipboard token before clearing it")
board.accepts = false
CommandBarSnippetCommands.copy(saved)
expect(QuickToolHUD.message == "Copy failed", "clipboard failure is reported")
AppFeature.available = false
expect(CommandBarSnippetCommands.rows(for: "snip") == nil && CommandBarSnippetCommands.snippet(for: entries[0].id) == nil, "disabled feature has no save or insert path")
bar.mode = .search; bar.isVisible = true
bar.selectedEntry = CommandBarEntry(id: "action.meet.fixture", title: "Meeting", subtitle: "", icon: .symbol("video"), run: { _ in })
bar.meetingSearch.selectedID = "action.meet.fixture"
expect(bar.runCommandReturn() && !bar.isVisible && MeetingNoteService.shared.opened == "action.meet.fixture", "Cmd-Return closes search and opens note preview for the selected meeting")
print("Snippet commands: \(checks) checks passed")
'''
service = 'Sources/Vorssaint/Services/CommandBar/CommandBarService.swift'
catalog = 'Sources/Vorssaint/Services/CommandBar/CommandBarCatalog.swift'
fixture = fixture.replace('// COMMAND_RETURN', declaration(service, '    func runCommandReturn('))
method = declaration(catalog, '    private static func snippetEntries(').replace('private static', 'static').replace('CommandBarFeatureStrings', 'FeatureStrings.Bar')
fixture = fixture.replace('// CATALOG', 'enum Catalog {\n' + method + '\n}')
source = declaration(catalog, 'struct CommandBarEntry:')
for path in ['Sources/Vorssaint/Services/Snippets/TextSnippetSupport.swift',
             'Sources/Vorssaint/Core/SnippetStrings.swift',
             'Sources/Vorssaint/Services/CommandBar/CommandBarSnippetCommands.swift']:
    source += '\n' + (repo / path).read_text()
with tempfile.TemporaryDirectory(prefix='snippet-command-tests-') as temporary:
    folder = Path(temporary)
    swift = folder / 'main.swift'
    swift.write_text(source + '\n' + fixture)
    binary = folder / 'test'
    subprocess.run(['swiftc', str(swift), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
