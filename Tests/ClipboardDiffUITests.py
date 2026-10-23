#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise the real AppKit diff window without changing clipboard history or the system clipboard."""
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
    let deadline = Date().addingTimeInterval(8)
    repeat {
        if predicate() { return true }
        RunLoop.main.run(until: Date().addingTimeInterval(0.01))
    } while Date() < deadline
    return false
}
func drain(_ seconds: TimeInterval = 0.3) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
func views(_ root: NSView) -> [NSView] { [root] + root.subviews.flatMap(views) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let history = ClipboardHistoryService.shared
let service = ClipboardDiffService.shared
let strings = ClipboardDiffStrings.localized(.enUS)
let clipboardChangeCount = NSPasteboard.general.changeCount
func window() -> NSWindow { app.windows.first { $0.isVisible && $0.title == strings.title }! }
func editors(_ window: NSWindow) -> [ClipboardDiffTextView] {
    views(window.contentView!).compactMap { $0 as? ClipboardDiffTextView }.sorted { $0.isBefore && !$1.isBefore }
}
func summary(_ window: NSWindow) -> NSTextField {
    views(window.contentView!).first { $0.identifier?.rawValue == "diff.summary" } as! NSTextField
}
func button(_ window: NSWindow, _ id: String) -> NSButton {
    views(window.contentView!).first { $0.identifier?.rawValue == id } as! NSButton
}
func edit(_ text: NSTextView, _ value: String) {
    text.setSelectedRange(NSRange(location: 0, length: (text.string as NSString).length))
    text.insertText(value, replacementRange: text.selectedRange())
}
func settled(_ window: NSWindow) -> Bool {
    until {
        let inputs = editors(window)
        return summary(window).stringValue != strings.loading && inputs.allSatisfy { input in
            let source = input.diffRows.compactMap { input.isBefore ? $0.before : $0.after }.map(\.text).joined(separator: "\n")
            return source == input.string
        }
    }
}
func escape(_ window: NSWindow) {
    // Dispatch only to this test app's window; never synthesize a global key.
    app.sendEvent(NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 1,
                                  windowNumber: window.windowNumber, context: nil, characters: "\u{1b}",
                                  charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53)!)
}
func capture(_ window: NSWindow, _ name: String, size: NSSize = NSSize(width: 980, height: 650)) {
    window.setContentSize(size)
    for input in editors(window) { input.scrollToContent(.zero) }
    for (label, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
        window.appearance = NSAppearance(named: appearance)
        drain(0.08)
        let content = window.contentView!
        content.layoutSubtreeIfNeeded()
        content.displayIfNeeded()
        let bitmap = content.bitmapImageRepForCachingDisplay(in: content.bounds)!
        content.cacheDisplay(in: content.bounds, to: bitmap)
        try! bitmap.representation(using: .png, properties: [:])!.write(
            to: URL(fileURLWithPath: "/tmp/clipboard-diff-\(name)-\(label).png"))
        for input in editors(window) {
            let start = input.convert(input.textContainerOrigin, to: content).x
            let gutterEdge = input.gutter!.convert(input.gutter!.bounds, to: content).maxX
            expect(start >= gutterEdge, "\(name) first source character and placeholder stay clear of the gutter in \(label)")
        }
        expect(editors(window).allSatisfy { $0.visibleRect.width > 150 && $0.visibleRect.height > 150 },
               "\(name) keeps both editors useful in \(label) appearance")
    }
}
func glyphY(_ text: NSTextView, containing needle: String) -> CGFloat {
    let range = (text.string as NSString).range(of: needle)
    precondition(range.location != NSNotFound)
    let manager = text.layoutManager!
    manager.ensureLayout(for: text.textContainer!)
    let glyph = manager.glyphIndexForCharacter(at: range.location)
    return manager.lineFragmentRect(forGlyphAt: glyph, effectiveRange: nil).minY + text.textContainerOrigin.y
}
func glyphX(_ text: NSTextView, containing needle: String) -> CGFloat {
    let range = (text.string as NSString).range(of: needle)
    precondition(range.location != NSNotFound)
    let manager = text.layoutManager!
    manager.ensureLayout(for: text.textContainer!)
    let glyph = manager.glyphIndexForCharacter(at: range.location)
    return manager.boundingRect(forGlyphRange: NSRange(location: glyph, length: 1), in: text.textContainer!).minX
}
let before = "Invoice total: €100.00\nPayment due in 14 days."
let after = "Invoice total: €120.00\nPayment due in 14 days."
history.entries = [.init(text: after, copiedAt: Date(timeIntervalSince1970: 2)),
                   .init(text: before, copiedAt: Date(timeIntervalSince1970: 1))]
service.show()
let first = window(), inputs = editors(first)
expect(views(first.contentView!).compactMap { $0 as? NSTextView }.count == 2 && inputs.count == 2,
       "only two editable panes, with differences inside their text")
expect(inputs.allSatisfy { $0.isEditable && $0.isSelectable && $0.allowsUndo }, "both panes retain native editing")
expect(inputs[0].string == before && inputs[1].string == after, "opening uses the two latest saved text copies")
expect(settled(first), "opening compares automatically")
expect(views(first.contentView!).compactMap { $0 as? NSButton }.allSatisfy { !$0.title.localizedCaseInsensitiveContains("compare") },
       "there is no Compare button")
expect(first.styleMask.contains(.resizable), "window can resize")
expect(inputs[0].diffRows.first?.kind == .changed, "correction has an inline changed row")
for input in inputs {
    let line = input.isBefore ? input.diffRows[0].before! : input.diffRows[0].after!
    expect(line.changedRanges == [NSRange(location: 17, length: 1)], "one corrected character has a precise highlight")
    expect(input.layoutManager!.temporaryAttribute(.backgroundColor, atCharacterIndex: 17, effectiveRange: nil) != nil,
           "corrected character receives a visible inline background")
    expect(input.layoutManager!.temporaryAttribute(.backgroundColor, atCharacterIndex: 16, effectiveRange: nil) == nil,
           "unchanged neighboring character keeps the subtle line background")
    expect(input.layoutManager!.temporaryAttribute(.underlineStyle, atCharacterIndex: 17, effectiveRange: nil) != nil,
           "character changes are distinguished beyond color")
}
capture(first, "correction")

// A redraw or completed comparison must not rewrite text storage and disrupt selection or undo.
first.makeFirstResponder(inputs[1])
inputs[1].undoManager!.removeAllActions()
let oldSelection = NSRange(location: 3, length: 5)
inputs[1].setSelectedRange(oldSelection)
edit(inputs[0], before + "\nReference: A17")
expect(settled(first), "opposite-pane edit recomputes")
expect(inputs[1].selectedRange() == oldSelection, "comparison preserves selection in the untouched pane")
inputs[1].undoManager!.beginUndoGrouping()
inputs[1].setSelectedRange(NSRange(location: (inputs[1].string as NSString).length, length: 0))
inputs[1].insertText("\nReviewed ✓", replacementRange: inputs[1].selectedRange())
inputs[1].undoManager!.endUndoGrouping()
let edited = inputs[1].string, caret = inputs[1].selectedRange()
expect(settled(first), "typing recomputes after the pause")
expect(inputs[1].selectedRange() == caret, "comparison preserves the caret")
expect(inputs[1].undoManager!.canUndo, "typing remains undoable after comparison")
inputs[1].undoManager!.undo()
expect(inputs[1].string == after && settled(first), "native undo restores the preceding text and comparison")
expect(inputs[1].undoManager!.canRedo, "comparison does not clear redo")
inputs[1].undoManager!.redo()
expect(inputs[1].string == edited && settled(first), "native redo restores the edit")
inputs[1].setSelectedRange(NSRange(location: 0, length: 0))
inputs[1].moveRight(nil)
expect(inputs[1].selectedRange() == NSRange(location: 1, length: 0), "native keyboard movement still works")
inputs[1].moveToEndOfDocument(nil)
expect(inputs[1].selectedRange().location == (inputs[1].string as NSString).length, "document navigation uses actual content")

let privatePasteboard = NSPasteboard.withUniqueName()
let pasted = "OCR: cafe\u{301} → café 👩🏽‍💻\r\n\n  keep\tspaces  \n"
privatePasteboard.setString(pasted, forType: .string)
inputs[1].setSelectedRange(NSRange(location: 0, length: (inputs[1].string as NSString).length))
expect(inputs[1].readSelection(from: privatePasteboard), "native plain-text paste succeeds")
expect(inputs[1].string == pasted && settled(first), "multiline Unicode, CRLF, tabs and blank lines survive paste exactly")
inputs[1].selectAll(nil)
let copyTypes = inputs[1].writablePasteboardTypes
privatePasteboard.declareTypes(copyTypes, owner: nil)
expect(inputs[1].writeSelection(to: privatePasteboard, types: copyTypes), "native copy to a private pasteboard succeeds")
expect(privatePasteboard.string(forType: copyTypes[0]) == pasted, "copy includes only real source text")
privatePasteboard.releaseGlobally()

edit(inputs[0], "OCR: café"); edit(inputs[1], "OCR: caf")
expect(settled(first), "composition baseline compares")
inputs[1].setSelectedRange(NSRange(location: 8, length: 0))
var compositionNotifications = 0
let compositionObserver = NotificationCenter.default.addObserver(forName: NSText.didChangeNotification, object: inputs[1], queue: nil) { _ in compositionNotifications += 1 }
inputs[1].setMarkedText("é", selectedRange: NSRange(location: 1, length: 0),
                        replacementRange: NSRange(location: NSNotFound, length: 0))
let markedRange = inputs[1].markedRange(), markedSelection = inputs[1].selectedRange()
expect(inputs[1].hasMarkedText(), "native input-method composition begins")
edit(inputs[0], "OCR: café")
expect(settled(first) && inputs[1].hasMarkedText(), "input-method composition remains active during an opposite-pane comparison")
expect(inputs[1].markedRange() == markedRange && inputs[1].selectedRange() == markedSelection,
       "comparison preserves marked text and its selection")
inputs[1].insertText("é", replacementRange: inputs[1].markedRange())
expect(inputs[1].string == "OCR: café" && !inputs[1].hasMarkedText() && settled(first), "composition commits without text loss")
expect(compositionNotifications > 0, "native composition commit posts the editing notification")
NotificationCenter.default.removeObserver(compositionObserver)

let codeBefore = """
# API service configuration
[server]
host = "127.0.0.1"
port = 8080
read_timeout = 30

[database]
url = "postgres://localhost/app"
pool_size = 5

[logging]
level = "debug"
format = "text"
"""
let codeAfter = """
# API service configuration
[server]
host = "127.0.0.1"
port = 8443
read_timeout = 30
tls = true
certificate = "/etc/app/server.pem"

[database]
url = "postgres://localhost/app"
pool_size = 12

[logging]
level = "info"
format = "json"
"""
edit(inputs[0], codeBefore); edit(inputs[1], codeAfter)
expect(summary(first).stringValue == strings.loading, "pending comparison has a clear loading state")
expect(inputs.allSatisfy { !$0.presentationCurrent }, "pending comparisons hide stale change presentation")
expect(settled(first), "multiline configuration compares automatically")
expect(inputs[0].string == codeBefore && inputs[1].string == codeAfter, "alignment inserts no text into either source")
expect(inputs[0].diffRows.contains { $0.before == nil && $0.after != nil }, "insertions have visual gaps in Before")
expect(abs(glyphY(inputs[0], containing: "[database]") - glyphY(inputs[1], containing: "[database]")) < 1,
       "corresponding real lines align after inserted rows")
expect(abs(glyphY(inputs[0], containing: "[logging]") - glyphY(inputs[1], containing: "[logging]")) < 1,
       "later sections stay aligned")
let previous = button(first, "diff.previous"), next = button(first, "diff.next")
expect(previous.isEnabled && next.isEnabled, "change navigation is available")
let sourceBeforeNavigation = inputs.map(\.string)
next.performClick(nil); previous.performClick(nil)
expect(inputs.map(\.string) == sourceBeforeNavigation, "change navigation never changes source text")
capture(first, "code")
capture(first, "code-small", size: NSSize(width: 620, height: 440))

// Gaps participate in layout, never in selection, arrow-key navigation or hit testing.
edit(inputs[0], "anchor\nlast"); edit(inputs[1], "inserted\nanchor\nlast")
expect(settled(first), "leading inserted line aligns")
expect(abs(glyphY(inputs[0], containing: "anchor") - glyphY(inputs[1], containing: "anchor")) < 1,
       "leading visual gap aligns the first real line")
let beforeOrigin = inputs[0].textContainerOrigin
expect(inputs[0].characterIndexForInsertion(at: NSPoint(x: beforeOrigin.x + 1, y: inputs[0].rowY(0) + 12)) == 0,
       "clicking a leading gap maps to the first real insertion position")
inputs[0].setSelectedRange(NSRange(location: 0, length: 0))
inputs[0].moveDown(nil)
expect(inputs[0].selectedRange().location == 7, "Down moves between real lines after a leading gap")
inputs[0].moveUp(nil)
expect(inputs[0].selectedRange().location == 0, "Up returns to the first real line")
edit(inputs[0], "anchor"); edit(inputs[1], "anchor\nadded\nmore")
expect(settled(first), "trailing inserted lines align")
inputs[0].moveToEndOfDocument(nil)
inputs[0].moveDown(nil)
expect(inputs[0].selectedRange() == NSRange(location: 6, length: 0), "Down at document end never enters a trailing visual gap")
expect(inputs[0].characterIndexForInsertion(at: NSPoint(x: beforeOrigin.x + 1, y: inputs[0].rowY(2) + 12)) == 6,
       "clicking a trailing gap maps to the real document end")
edit(inputs[0], "first\nlast\n"); edit(inputs[1], "intro\nfirst\nmiddle\nlast\noutro\n")
expect(settled(first), "leading, internal and trailing insertions align with a final blank line")
expect(abs(glyphY(inputs[0], containing: "last") - glyphY(inputs[1], containing: "last")) < 1,
       "internal gaps preserve matching text positions")
let finalRow = inputs[0].diffRows.lastIndex { $0.before?.range.location == (inputs[0].string as NSString).length }!
inputs[0].layoutManager!.ensureLayout(for: inputs[0].textContainer!)
expect(abs(inputs[0].layoutManager!.extraLineFragmentRect.minY + inputs[0].textContainerOrigin.y - inputs[0].rowY(finalRow)) < 1,
       "final blank-line caret follows its aligned source row")
inputs[0].moveToBeginningOfDocument(nil)
inputs[0].moveDown(nil)
expect(inputs[0].selectedRange().location == 6, "Down crosses an internal visual gap to the next real line")
inputs[0].moveToEndOfDocument(nil)
expect(inputs[0].selectedRange().location == 11, "End reaches the true trailing-newline position")

edit(inputs[0], "line one\r\nline two\r\nlast"); edit(inputs[1], "line one\nline two\nlast")
expect(settled(first), "CRLF and LF comparison settles")
expect(abs(glyphY(inputs[0], containing: "line two") - glyphY(inputs[1], containing: "line two")) < 1,
       "CRLF and LF lines stay aligned")
expect(inputs[0].string == "line one\r\nline two\r\nlast", "comparison preserves CRLF bytes")
let separators = "A\rB\u{2028}C\u{2029}D\nlast"
edit(inputs[0], separators); edit(inputs[1], "A B C D\nlast")
expect(settled(first), "embedded Unicode separators compare")
expect(inputs[0].string == separators, "embedded CR and Unicode separators remain exact")
for letter in ["B", "C", "D"] {
    expect(abs(glyphY(inputs[0], containing: letter) - glyphY(inputs[0], containing: "A")) < 1,
           "embedded separator keeps \(letter) on its logical source row")
}
expect(glyphX(inputs[0], containing: "A") < glyphX(inputs[0], containing: "B") &&
       glyphX(inputs[0], containing: "B") < glyphX(inputs[0], containing: "C") &&
       glyphX(inputs[0], containing: "C") < glyphX(inputs[0], containing: "D"),
       "embedded separators do not cause overlapping glyphs")
expect(abs(glyphY(inputs[0], containing: "last") - glyphY(inputs[1], containing: "last")) < 1,
       "real LF after embedded separators aligns normally")

let longBefore = (0..<150).map { "setting_\($0) = \($0)" }.joined(separator: "\n")
let longAfter = longBefore.replacingOccurrences(of: "setting_70 = 70", with: "added = true\nsetting_70 = 71")
edit(inputs[0], longBefore); edit(inputs[1], longAfter)
expect(settled(first), "long configuration compares")
let leftScroll = inputs[0].enclosingScrollView!, rightScroll = inputs[1].enclosingScrollView!
inputs[0].scroll(NSPoint(x: 0, y: 900))
drain(0.05)
expect(abs(inputs[0].viewportOrigin.y - inputs[1].viewportOrigin.y) < 1, "vertical scrolling stays synchronized")
let longLine = String(repeating: "long_value_", count: 500)
edit(inputs[0], longLine); edit(inputs[1], longLine + "X")
expect(settled(first), "long unwrapped lines compare")
expect(inputs[0].string == longLine && inputs[1].string == longLine + "X", "long lines remain complete")
expect(inputs[1].frame.width > rightScroll.contentView.bounds.width, "long lines can scroll horizontally")
inputs[0].scroll(NSPoint(x: 700, y: 0))
drain(0.05)
expect(abs(inputs[0].viewportOrigin.x - inputs[1].viewportOrigin.x) < 1,
       "horizontal scrolling stays synchronized for long lines")
// A permitted pathological line must not block the main thread while drawing.
let spaces = String(repeating: " ", count: 200_000)
let letters = String(repeating: "x", count: 200_000)
edit(inputs[0], spaces); edit(inputs[1], letters)
expect(settled(first), "200000-character whitespace replacement compares")
first.setContentSize(NSSize(width: 620, height: 440))
first.contentView!.layoutSubtreeIfNeeded()
for input in inputs {
    input.scrollToContent(.zero)
    let rect = input.visibleRect
    let bitmap = input.bitmapImageRepForCachingDisplay(in: rect)!
    let began = ProcessInfo.processInfo.systemUptime
    input.cacheDisplay(in: rect, to: bitmap)
    let elapsed = ProcessInfo.processInfo.systemUptime - began
    expect(elapsed < 2, "large \(input.isBefore ? "Before" : "After") visible draw must stay below two seconds; took \(elapsed)s")
    print("RENDER: \(input.isBefore ? "Before spaces" : "After letters") \(Int(elapsed * 1000)) ms")
}
expect(inputs[0].string == spaces && inputs[1].string == letters, "large rendering preserves every source character")
edit(inputs[1], "stale edit"); edit(inputs[1], "latest edit")
expect(settled(first), "rapid edits deliver only the latest comparison")
expect(inputs[1].diffRows.compactMap(\.after).map(\.text).joined(separator: "\n") == "latest edit", "stale results never replace the latest input")
expect(history.entries[0].text == after && history.entries[1].text == before, "editing leaves saved clipboard history unchanged")

// One explicit JSON action validates both sources before making one undoable edit.
let formatJSON = button(first, "diff.formatJSON")
expect(views(first.contentView!).compactMap { $0 as? NSButton }.filter {
    $0.identifier?.rawValue.hasPrefix("diff.format") == true
}.count == 1 && formatJSON.title == "JSON", "one compact JSON control formats both panes")
let rawJSON = #"{"id":9007199254740993,"amount":1.2300e+4,"id":2,"label":"caf\u00e9\/file","enabled":true}"#
let otherJSON = rawJSON.replacingOccurrences(of: "1.2300e+4", with: "1.2301e+4").replacingOccurrences(of: "true", with: "false")
let formattedJSON = #"""
{
  "id": 9007199254740993,
  "amount": 1.2300e+4,
  "id": 2,
  "label": "caf\u00e9\/file",
  "enabled": true
}
"""#
let formattedOtherJSON = formattedJSON.replacingOccurrences(of: "1.2300e+4", with: "1.2301e+4").replacingOccurrences(of: "true", with: "false")
edit(inputs[0], rawJSON); edit(inputs[1], otherJSON)
expect(settled(first) && inputs[0].string == rawJSON && inputs[1].string == otherJSON,
       "pasting JSON compares the raw text without automatic formatting")
expect(formatJSON.isEnabled, "nonempty panes enable the JSON action")
expect(inputs[0].undoManager === inputs[1].undoManager, "both production editors share their native window undo manager")
first.makeFirstResponder(inputs[0])
inputs[0].undoManager!.removeAllActions()
formatJSON.performClick(nil)
expect(until { inputs[0].string == formattedJSON && inputs[1].string == formattedOtherJSON } && settled(first),
       "one action formats both panes with exact large numbers, decimal spelling, duplicate keys and string escapes")
expect(inputs[0].undoManager!.canUndo, "combined formatting is a native undoable edit")
inputs[0].undoManager!.undo()
expect(inputs[0].string == rawJSON && inputs[1].string == otherJSON && settled(first), "one undo restores both complete unformatted sources")
expect(!inputs[0].undoManager!.canUndo, "combined formatting creates exactly one undo action")
inputs[1].undoManager!.redo()
expect(inputs[0].string == formattedJSON && inputs[1].string == formattedOtherJSON && settled(first), "one redo from either pane restores both formatted sources")
inputs[0].undoManager!.removeAllActions()
formatJSON.performClick(nil)
expect(until { formatJSON.isEnabled } && settled(first), "formatting two already formatted sources completes normally")
expect(!inputs[0].undoManager!.canUndo && inputs[0].string == formattedJSON && inputs[1].string == formattedOtherJSON,
       "a combined formatting no-op changes neither source nor undo history")
capture(first, "json")
capture(first, "json-small", size: NSSize(width: 620, height: 440))

let invalidJSON = #"{"port":}"#
edit(inputs[0], rawJSON); edit(inputs[1], invalidJSON)
inputs[0].undoManager!.removeAllActions()
expect(summary(first).stringValue == strings.loading, "invalid formatting test begins with a pending comparison")
formatJSON.performClick(nil)
let invalidMessage = strings.after + ": " + strings.invalidJSON
expect(until { summary(first).stringValue == invalidMessage }, "invalid JSON identifies the failing pane")
expect(settled(first), "pending raw comparison still finishes after invalid formatting")
drain()
expect(summary(first).stringValue == invalidMessage, "arriving comparison does not erase the formatting error")
expect(inputs[0].string == rawJSON && inputs[1].string == invalidJSON && !inputs[0].undoManager!.canUndo,
       "invalid After leaves valid unformatted Before untouched and creates no undo action")
capture(first, "json-invalid-small", size: NSSize(width: 620, height: 440))
edit(inputs[0], invalidJSON); edit(inputs[1], otherJSON)
formatJSON.performClick(nil)
expect(until { summary(first).stringValue == strings.before + ": " + strings.invalidJSON }, "invalid Before is identified independently")
expect(inputs[0].string == invalidJSON && inputs[1].string == otherJSON, "invalid Before also leaves valid unformatted After untouched")

for (beforeSource, afterSource, beforeResult, afterResult) in [
    ("", otherJSON, "", formattedOtherJSON), (rawJSON, "", formattedJSON, "")
] {
    edit(inputs[0], beforeSource); edit(inputs[1], afterSource)
    expect(formatJSON.isEnabled, "one empty pane still enables JSON formatting")
    inputs[0].undoManager!.removeAllActions()
    formatJSON.performClick(nil)
    expect(until { inputs[0].string == beforeResult && inputs[1].string == afterResult } && settled(first),
           "an empty pane stays empty while the other formats")
    inputs[0].undoManager!.undo()
    expect(inputs[0].string == beforeSource && inputs[1].string == afterSource && settled(first), "one-empty formatting remains undoable without creating text")
}
let tooBigJSON = "{\"value\":\"" + String(repeating: "x", count: ClipboardDiff.maxBytes) + "\"}"
let tooManyFormattedLines = "[" + Array(repeating: "0", count: ClipboardDiff.maxLines).joined(separator: ",") + "]"
let tooManyFormattedBytes = String(repeating: "[", count: 320) + "0" + String(repeating: "]", count: 320)
for (source, message) in [(tooBigJSON, strings.tooLarge), (tooManyFormattedLines, strings.formattedTooLarge),
                          (tooManyFormattedBytes, strings.formattedTooLarge)] {
    for side in 0...1 {
        let beforeSource = side == 0 ? source : rawJSON, afterSource = side == 1 ? source : otherJSON
        edit(inputs[0], beforeSource); edit(inputs[1], afterSource)
        inputs[0].undoManager!.removeAllActions()
        formatJSON.performClick(nil)
        let label = side == 0 ? strings.before : strings.after
        expect(until { summary(first).stringValue == label + ": " + message }, "formatting reports either pane's input or expanded-output limit")
        expect(inputs[0].string == beforeSource && inputs[1].string == afterSource && !inputs[0].undoManager!.canUndo,
               "either pane exceeding a limit leaves both complete sources and undo history untouched")
    }
}
edit(inputs[0], rawJSON); edit(inputs[1], otherJSON)
formatJSON.performClick(nil)
let latestJSON = #"{"latest":true}"#
edit(inputs[1], latestJSON)
expect(settled(first) && inputs[0].string == rawJSON && inputs[1].string == latestJSON,
       "an immediate edit cancels stale formatting for both panes")
expect(history.entries[0].text == after && history.entries[1].text == before, "JSON formatting never modifies saved clipboard history")

edit(inputs[0], ""); edit(inputs[1], "")
expect(until { summary(first).stringValue == strings.missing }, "both empty inputs show paste guidance")
expect(inputs.allSatisfy { !$0.presentationCurrent }, "empty panes hide stale gutter and change presentation")
expect(!formatJSON.isEnabled, "two empty panes disable JSON formatting")
capture(first, "empty")
edit(inputs[0], codeBefore); edit(inputs[1], codeBefore)
expect(until { summary(first).stringValue == strings.identical }, "identical inputs have an explicit no-differences state")
expect(settled(first) && inputs[0].diffRows.allSatisfy { $0.kind == .same }, "identical text has no stale highlights")
expect(!next.isEnabled && !previous.isEnabled, "identical inputs disable change navigation")
capture(first, "identical")
let oversized = String(repeating: "x", count: ClipboardDiff.maxBytes + 1)
edit(inputs[1], oversized)
expect(until { summary(first).stringValue == strings.tooLarge }, "oversized input shows the preserved limit")
expect(inputs[1].string == oversized, "oversized text is not truncated")
expect(inputs.allSatisfy { !$0.presentationCurrent }, "oversized input hides stale gutter and change presentation")
capture(first, "oversized", size: NSSize(width: 620, height: 440))
first.makeFirstResponder(inputs[0]); escape(first)
expect(!first.isVisible, "Escape closes from an editor")

history.entries = []
service.show()
let empty = window(), emptyInputs = editors(empty)
expect(emptyInputs.allSatisfy { $0.string.isEmpty } && summary(empty).stringValue == strings.missing, "empty history starts a manual comparison")
edit(emptyInputs[0], "manual before"); edit(emptyInputs[1], "manual after")
expect(settled(empty), "manual comparison needs no saved history")
edit(emptyInputs[0], rawJSON); edit(emptyInputs[1], otherJSON)
button(empty, "diff.formatJSON").performClick(nil)
empty.close()
service.show()
let reopened = window()
drain()
expect(editors(reopened).allSatisfy { $0.string.isEmpty } && summary(reopened).stringValue == strings.missing,
       "closing cancels pending formatting/comparison delivery and discards unsaved edits")
reopened.close()
AppFeature.enabled = false
service.show()
expect(!app.windows.contains { $0.isVisible && $0.title == strings.title }, "disabled feature cannot open")
expect(NSPasteboard.general.changeCount == clipboardChangeCount, "comparison and editing never mutate the system clipboard")
print("PASS: \(checks) native clipboard diff checks; screenshots: /tmp/clipboard-diff-*.png")
'''
with tempfile.TemporaryDirectory(prefix='clipboard-diff-ui-') as directory:
    folder = Path(directory)
    main = folder / 'main.swift'
    main.write_text(fixture)
    executable = folder / 'check'
    support = (repo / 'Sources/Vorssaint/Services/Clipboard/ClipboardHistorySupport.swift').read_text()
    start = support.index('enum ClipboardJSONFormat {')
    end = support.index('/// How large a picture', start)
    formatter = folder / 'ClipboardJSONFormat.swift'
    formatter.write_text('import Foundation\n' + support[start:end])
    sources = [
        'Core/ClipboardDiffStrings.swift',
        'Services/Clipboard/ClipboardDiff.swift',
        'Services/Clipboard/ClipboardDiffEditor.swift',
        'Services/Clipboard/ClipboardDiffService.swift',
    ]
    subprocess.run(['swiftc', *[str(repo / 'Sources/Vorssaint' / source) for source in sources],
                    str(formatter), str(main), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=90)
