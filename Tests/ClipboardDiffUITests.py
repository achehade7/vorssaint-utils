#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native diff window with isolated clipboard history and a private pasteboard."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit

enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct L10n { static let shared = Self(); let language = AppLanguage.enUS }
enum AppFeature {
    case clipboardHistory
    static var enabled = true
    var isAvailable: Bool { Self.enabled }
}
struct ClipboardHistoryEntry {
    enum Kind { case text, image, files }
    var text: String
    var copiedAt: Date
    var kind = Kind.text
}
final class ClipboardHistoryService {
    static let shared = ClipboardHistoryService()
    var entries: [ClipboardHistoryEntry] = []
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    precondition(condition, message)
}
func until(_ predicate: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(5)
    repeat {
        if predicate() { return true }
        RunLoop.main.run(until: Date().addingTimeInterval(0.01))
    } while Date() < deadline
    return false
}
func views(_ root: NSView) -> [NSView] { [root] + root.subviews.flatMap(views) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let history = ClipboardHistoryService.shared
let service = ClipboardDiffService.shared
let strings = ClipboardDiffStrings.localized(.enUS)
func window() -> NSWindow { app.windows.first { $0.isVisible && $0.title == strings.title }! }
func texts(_ window: NSWindow) -> [NSTextView] { views(window.contentView!).compactMap { $0 as? NSTextView } }
func edit(_ text: NSTextView, _ value: String) {
    text.setSelectedRange(NSRange(location: 0, length: (text.string as NSString).length))
    text.insertText(value, replacementRange: text.selectedRange())
}
func escape(_ window: NSWindow) {
    app.sendEvent(NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 1,
                                  windowNumber: window.windowNumber, context: nil, characters: "\u{1b}",
                                  charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53)!)
}
let before = "<invoice>\n  <amount>100</amount>\n</invoice>"
let after = "<invoice>\n  <amount>120</amount>\n</invoice>"
history.entries = [.init(text: after, copiedAt: Date(timeIntervalSince1970: 2)),
                   .init(text: before, copiedAt: Date(timeIntervalSince1970: 1))]
service.show()
let first = window(), areas = texts(first)
expect(areas.count == 3, "two editors and one result")
let inputs = areas.filter(\.isEditable), output = areas.first { !$0.isEditable }!
expect(inputs[0].string == before && inputs[1].string == after, "copy then copy prepopulates older and newer")
expect(until { output.string.contains("−   <amount>100</amount>") && output.string.contains("+   <amount>120</amount>") }, "opening automatically computes the diff")
expect(views(first.contentView!).allSatisfy { !($0 is NSButton) }, "no Compare button is required")
expect(output.isSelectable && !output.isEditable, "result is selectable and read-only")
let removed = (output.string as NSString).range(of: "− ")
let added = (output.string as NSString).range(of: "+ ")
expect(output.textStorage?.attribute(.foregroundColor, at: removed.location, effectiveRange: nil) as? NSColor == .systemRed, "removals use red")
expect(output.textStorage?.attribute(.foregroundColor, at: added.location, effectiveRange: nil) as? NSColor == .systemGreen, "additions use green")
first.contentView!.layoutSubtreeIfNeeded()
expect(inputs.allSatisfy { $0.visibleRect.width > 100 && $0.visibleRect.height > 100 }, "both editors are visible")
expect(output.visibleRect.width > 400 && output.visibleRect.height > 100, "comparison remains visible")
if let bitmap = first.contentView!.bitmapImageRepForCachingDisplay(in: first.contentView!.bounds) {
    first.contentView!.cacheDisplay(in: first.contentView!.bounds, to: bitmap)
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
}
edit(inputs[1], before)
expect(until { views(first.contentView!).compactMap { $0 as? NSTextField }.contains { $0.stringValue == strings.identical } }, "editing refreshes the comparison automatically")
expect(!output.string.contains("− ") && !output.string.contains("+ "), "identical inputs contain no changes")
let privatePasteboard = NSPasteboard.withUniqueName()
privatePasteboard.setString("OCR text corrected", forType: .string)
inputs[1].setSelectedRange(NSRange(location: 0, length: (inputs[1].string as NSString).length))
expect(inputs[1].readSelection(from: privatePasteboard), "native plain-text paste succeeds")
expect(until { output.string.contains("+ OCR text corrected") }, "pasting refreshes without confirmation")
privatePasteboard.releaseGlobally()
edit(inputs[1], "stale edit")
edit(inputs[1], "latest edit")
expect(until { output.string.contains("+ latest edit") }, "rapid edits keep the latest result")
expect(!output.string.contains("stale edit"), "cancelled comparison cannot replace the latest result")
expect(history.entries[0].text == after && history.entries[1].text == before, "manual edits do not alter saved clipboard text")
edit(inputs[1], String(repeating: "x", count: ClipboardDiff.maxBytes + 1))
expect(until { output.string == strings.tooLarge }, "oversized text shows a clear message, not truncated output")
first.makeFirstResponder(inputs[0]); escape(first)
expect(!first.isVisible, "Escape closes from an editor")
history.entries = []
service.show()
let empty = window(), emptyAreas = texts(empty)
let emptyInputs = emptyAreas.filter(\.isEditable), emptyResult = emptyAreas.first { !$0.isEditable }!
expect(emptyInputs.allSatisfy { $0.string.isEmpty } && emptyResult.string == strings.missing, "empty history offers manual inputs")
edit(emptyInputs[0], "manual before"); edit(emptyInputs[1], "manual after")
expect(until { emptyResult.string.contains("− manual before") && emptyResult.string.contains("+ manual after") }, "manual comparison needs no saved history")
edit(emptyInputs[0], "pending"); empty.close()
service.show()
let reopened = window(), reopenedAreas = texts(reopened)
RunLoop.main.run(until: Date().addingTimeInterval(0.3))
expect(reopenedAreas.filter(\.isEditable).allSatisfy { $0.string.isEmpty }, "closing discards edits")
expect(reopenedAreas.first { !$0.isEditable }!.string == strings.missing, "closing cancels pending delivery")
reopened.makeFirstResponder(reopenedAreas.first { !$0.isEditable }); escape(reopened)
expect(!reopened.isVisible, "Escape closes from the result")
AppFeature.enabled = false
service.show()
expect(!app.windows.contains { $0.isVisible && $0.title == strings.title }, "uninstalled feature cannot open")
print("PASS: \(checks) native clipboard diff checks")
'''
with tempfile.TemporaryDirectory(prefix='clipboard-diff-ui-') as directory:
    folder = Path(directory)
    main = folder / 'main.swift'
    main.write_text(fixture)
    executable = folder / 'check'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Core/ClipboardDiffStrings.swift'),
                    str(repo / 'Sources/Vorssaint/Services/Clipboard/ClipboardDiff.swift'),
                    str(repo / 'Sources/Vorssaint/Services/Clipboard/ClipboardDiffService.swift'),
                    str(main), '-o', str(executable)], check=True)
    subprocess.run([str(executable), '/tmp/clipboard-diff-preview.png'], check=True)
