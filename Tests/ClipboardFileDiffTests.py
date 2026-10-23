#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Real file decoding, private pasteboards, and asynchronous drop replacement."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
import Combine

enum AppLanguage: CaseIterable { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct L10n { static let shared = Self(); let language = AppLanguage.enUS }
enum AppFeature { case clipboardHistory; static var enabled = true; var isAvailable: Bool { Self.enabled } }
struct ClipboardHistoryEntry {
    enum Kind { case text, image, files }
    var text: String; var copiedAt: Date; var kind = Kind.text
}
enum ClipboardJSONFormat { static func pretty(_ text: String) -> String? { nil } }
final class ClipboardDiffService {
    static let shared = ClipboardDiffService()
    struct Opened { let pair: ClipboardDiff.Pair; let beforeName: String?; let afterName: String? }
    var opened: [Opened] = []
    func show(pair: ClipboardDiff.Pair, beforeName: String?, afterName: String?) {
        opened.append(.init(pair: pair, beforeName: beforeName, afterName: afterName))
    }
}
final class NotchService {
    static let shared = NotchService()
    var actions = 0
    var deferred = false
    var pending: [() -> Void] = []
    func perform(_ action: @escaping () -> Void) {
        actions += 1
        if deferred { pending.append(action) } else { action() }
    }
    func finish() { let actions = pending; pending = []; actions.forEach { $0() } }
}
var checks = 0
func expect(_ condition: @autoclosure () throws -> Bool, _ message: String) rethrows {
    checks += 1
    let result = try condition()
    precondition(result, message)
}
func until(_ predicate: () -> Bool) -> Bool {
    let end = Date().addingTimeInterval(5)
    repeat {
        if predicate() { return true }
        RunLoop.main.run(until: Date().addingTimeInterval(0.005))
    } while Date() < end
    return false
}
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.1)) }
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
var originals: [URL: Data] = [:]
func file(_ name: String, _ bytes: Data) throws -> URL {
    let url = root.appendingPathComponent(name)
    try bytes.write(to: url)
    originals[url] = bytes
    return url
}
func text(_ name: String, _ content: String) throws -> URL { try file(name, Data(content.utf8)) }
func failure(_ url: URL, _ wanted: ClipboardFileDiff.Failure) {
    do { _ = try ClipboardFileDiff.read(url); expect(false, "file should fail") }
    catch let error as ClipboardFileDiff.Failure {
        expect(String(describing: error) == String(describing: wanted), "failure distinguishes unsupported, oversized, and unreadable")
    } catch { expect(false, "unexpected error") }
}
let clipboardCount = NSPasteboard.general.changeCount
let samples = ["", "\r\n\n\t  \r", "cafe\u{301} → café 👩🏽‍💻\r\n尾行\n", "\u{feff}JSON: {}", "\t    "]
for (index, sample) in samples.enumerated() {
    let url = try text("exact-\(index).txt", sample)
    let input = try ClipboardFileDiff.read(url)
    expect(Data(input.text.utf8) == Data(sample.utf8), "valid UTF-8 bytes, BOM, line endings and whitespace remain exact")
    expect(input.name == url.lastPathComponent, "source name preserved")
}
let bytesAtLimit = try text("byte-limit.txt", String(repeating: "é", count: ClipboardDiff.maxBytes / 2))
try expect(ClipboardFileDiff.read(bytesAtLimit).text.utf8.count == ClipboardDiff.maxBytes, "exact byte limit accepted including multibyte text")
failure(try text("byte-over.txt", String(repeating: "x", count: ClipboardDiff.maxBytes + 1)), .tooLarge)
let linesAtLimit = try text("line-limit.txt", String(repeating: "\n", count: ClipboardDiff.maxLines - 1))
try expect(ClipboardFileDiff.read(linesAtLimit).text.utf8.count == ClipboardDiff.maxLines - 1, "blank lines count without normalization")
failure(try text("line-over.txt", String(repeating: "\n", count: ClipboardDiff.maxLines)), .tooLarge)
failure(try file("nul.txt", Data([65, 0, 66])), .unsupported)
failure(try file("invalid.txt", Data([0xff, 0xfe, 0x41])), .unsupported)
failure(root.appendingPathComponent("missing.txt"), .unreadable)
failure(root, .unreadable)
let before = try text("Before config.json", "{\"stage\":\"Q\"}\r\n\t")
let after = try text("After config.json", "{\"stage\":\"P\"}\r\n\t")
let replacement = try text("Replacement.json", "replacement\n")
let binary = try file("binary.txt", Data([1, 0, 2]))
expect(ClipboardFileDiff.accepts([before]) && ClipboardFileDiff.accepts([before, after]), "one or two text files accepted")
expect(!ClipboardFileDiff.accepts([]) && !ClipboardFileDiff.accepts([before, after, replacement]), "empty and three-file batches refused")
expect(!ClipboardFileDiff.accepts([URL(string: "https://example.invalid/file.txt")!]), "remote URLs refused")
expect(!ClipboardFileDiff.accepts([root]), "directory drag refused")
expect(!ClipboardFileDiff.accepts([root.appendingPathComponent("image.png")]), "non-text type refused")
for ext in ["JSON", "xml", "yaml", "yml", "properties", "groovy", "iflw", "abap", "", "env"] {
    expect(ClipboardFileDiff.accepts([root.appendingPathComponent(ext.isEmpty ? "LICENSE" : "source." + ext)]), "expected local text/config type accepted")
}
let service = ClipboardFileDiffService.shared, editor = ClipboardDiffService.shared
let board = NSPasteboard.withUniqueName()
defer { board.releaseGlobally() }
func pasteboard(_ urls: [URL]) {
    board.clearContents()
    expect(board.writeObjects(urls as [NSURL]), "test files written only to a private pasteboard")
}
pasteboard([before])
let privateCount = board.changeCount
expect(service.accept(board, side: .before) && service.loading == [.before], "single drop enters its target loading state")
expect(until { service.loading.isEmpty }, "single drop settles")
expect(service.inputs[.before]?.name == before.lastPathComponent && service.inputs[.after] == nil && editor.opened.isEmpty,
       "single drop waits for the other explicit target")
expect(board.changeCount == privateCount, "reading the drag pasteboard does not rewrite it")
pasteboard([after])
expect(service.accept(board, side: .after), "second side accepts")
expect(until { editor.opened.count == 1 }, "completing the pair automatically opens comparison")
expect(!service.hasDraft && service.inputs.isEmpty && service.error == nil, "completed draft resets")
expect(editor.opened[0].pair.older == "{\"stage\":\"Q\"}\r\n\t" && editor.opened[0].pair.newer == "{\"stage\":\"P\"}\r\n\t", "source text reaches editor unchanged")
expect(editor.opened[0].beforeName == before.lastPathComponent && editor.opened[0].afterName == after.lastPathComponent, "both names reach editor")

pasteboard([after, before])
expect(service.accept(board, side: .after), "two-file drop works on either target")
expect(until { editor.opened.count == 2 }, "two-file drop compares automatically")
expect(editor.opened.last?.beforeName == after.lastPathComponent && editor.opened.last?.afterName == before.lastPathComponent, "two files preserve pasteboard order")

service.load([before], side: .before); service.load([after], side: .after)
expect(until { editor.opened.count == 3 }, "overlapping opposite-side reads finish independently")
expect(editor.opened.last?.beforeName == before.lastPathComponent && editor.opened.last?.afterName == after.lastPathComponent, "opposite-side reads retain both intended targets")
service.load([before], side: .before); service.load([replacement], side: .before)
expect(until { service.loading.isEmpty }, "same-side replacement settles")
expect(service.inputs[.before]?.name == replacement.lastPathComponent, "stale same-side delivery cannot overwrite newer drop")
service.load([after], side: .after)
expect(until { editor.opened.count == 4 }, "replacement pairs normally")
expect(editor.opened.last?.beforeName == replacement.lastPathComponent, "comparison uses newest source")

service.load([before, after], side: .before); service.clear(); drain()
expect(!service.hasDraft && editor.opened.count == 4, "clear invalidates pending pair and prevents reopening")
service.load([before, after], side: .before); service.load([replacement], side: .after)
expect(until { service.loading.isEmpty }, "replacing one side cancels an overlapping atomic pair")
expect(service.inputs[.before] == nil && service.inputs[.after]?.name == replacement.lastPathComponent && editor.opened.count == 4,
       "canceled pair cannot leak either half")
service.clear()
service.load([before], side: .before)
expect(until { service.loading.isEmpty }, "baseline ready before failed pair")
service.load([after, binary], side: .after)
expect(until { service.loading.isEmpty }, "invalid pair settles")
expect(service.error == ClipboardFileDiffStrings.localized(.enUS).unsupported && service.inputs[.before]?.name == before.lastPathComponent
       && service.inputs[.after] == nil && editor.opened.count == 4, "failure applies neither file and preserves prior input")
service.load([after], side: .after)
expect(until { editor.opened.count == 5 }, "valid retry completes preserved draft")
expect(editor.opened.last?.beforeName == before.lastPathComponent, "retry uses original retained input")

for _ in 0..<12 {
    service.load([before], side: .before)
    expect(until { service.loading.isEmpty }, "race baseline ready")
    service.load([binary], side: .before); service.load([after], side: .after)
    expect(until { service.loading.isEmpty }, "overlapping failure and success both settle")
    expect(service.error != nil && editor.opened.count == 5,
           "failed replacement cannot auto-open its stale previous source when the opposite read succeeds")
    service.clear()
}
let notch = NotchService.shared
notch.deferred = true
service.load([before, after], side: .before)
expect(until { notch.pending.count == 1 }, "completed pair waits for island closing animation")
service.clear(); notch.finish()
expect(editor.opened.count == 5, "clear cancels a completed pair queued behind island closing")
service.load([before, after], side: .before)
expect(until { notch.pending.count == 1 }, "second completed pair waits for closing")
service.load([replacement], side: .before); notch.finish()
expect(until { service.loading.isEmpty }, "new draft finishes while old presentation is discarded")
expect(editor.opened.count == 5 && service.inputs[.before]?.name == replacement.lastPathComponent,
       "new drop invalidates the previously completed pair without losing the new draft")
notch.deferred = false
service.load([after], side: .after)
expect(until { editor.opened.count == 6 }, "current draft can still finish normally after a stale presentation")

service.load([before], side: .before); AppFeature.enabled = false
expect(until { service.loading.isEmpty }, "feature disabled during work settles")
expect(!service.hasDraft && editor.opened.count == 6, "revoking feature prevents delayed opening")
pasteboard([before, after])
expect(!service.accept(board, side: .before), "disabled feature refuses new drops")
AppFeature.enabled = true
board.clearContents(); board.setString("ordinary text", forType: .string)
expect(service.files(from: board) == nil, "plain text drag remains available to its original destination")
board.clearContents()
let fileItem = NSPasteboardItem(), textItem = NSPasteboardItem()
fileItem.setString(before.absoluteString, forType: .fileURL); textItem.setString("other", forType: .string)
board.writeObjects([fileItem, textItem])
expect(service.files(from: board) == nil, "mixed file/text drag cannot silently discard text")
for (url, bytes) in originals { try expect(Data(contentsOf: url) == bytes, "source file bytes are never changed") }
expect(NSPasteboard.general.changeCount == clipboardCount, "all file drops leave system clipboard untouched")
expect(NotchService.shared.actions == editor.opened.count + 2, "only completed comparisons queue presentation, and both stale callbacks are discarded")
for language in AppLanguage.allCases {
    let strings = ClipboardFileDiffStrings.localized(language)
    expect(!strings.title.isEmpty && !strings.unsupported.isEmpty && !strings.unreadable.isEmpty, "every app language has drop and failure text")
}
print("PASS: \(checks) clipboard file diff checks")
'''
with tempfile.TemporaryDirectory(prefix='clipboard-file-diff-') as temporary:
    folder = Path(temporary)
    main = folder / 'main.swift'
    main.write_text(fixture)
    binary = folder / 'checks'
    sources = ['Core/ClipboardFileDiffStrings.swift', 'Core/ClipboardDiffStrings.swift',
               'Services/Clipboard/ClipboardDiff.swift', 'Services/Clipboard/ClipboardFileDiffService.swift']
    subprocess.run(['swiftc', *[str(repo / 'Sources/Vorssaint' / source) for source in sources], str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary), str(folder / 'files')], check=True, timeout=30)
