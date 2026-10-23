#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native drop targets and named editable comparisons; never touches the system clipboard."""
import ast
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
island = r'''
import AppKit
import SwiftUI
import Combine

enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
final class L10n: ObservableObject { static let shared = L10n(); @Published var language = AppLanguage.enUS }
enum ClipboardFileDiff {
    enum Side: String, CaseIterable { case before, after }
    struct Input { let name: String; let text: String }
}
final class ClipboardFileDiffService: ObservableObject {
    static let shared = ClipboardFileDiffService()
    @Published var inputs: [ClipboardFileDiff.Side: ClipboardFileDiff.Input] = [:]
    @Published var loading: Set<ClipboardFileDiff.Side> = []
    @Published var error: String?
    func clear() { inputs = [:]; loading = []; error = nil }
}
final class NotchService: ObservableObject {
    @Published var offeringFileDiff = true
    @Published var fileDiffTarget: ClipboardFileDiff.Side? = .after
}
final class Frames { var values: [ClipboardFileDiff.Side: CGRect] = [:] }
var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ message: String) { checks += 1; precondition(condition(), message) }
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.12)) }
guard (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native file comparison checks require an unlocked Mac. No input was sent.\n", stderr)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let draft = ClipboardFileDiffService.shared, service = NotchService()
let clipboardCount = NSPasteboard.general.changeCount
let name = "SAP-Finance-Products-CPI-IntegrationFlow-Configuration-Q-2026-10-23-really-long-file-name.properties"
for scenario in ["empty", "filename", "pending", "error"] {
    draft.clear()
    if scenario != "empty" { draft.inputs[.before] = .init(name: name, text: "before") }
    if scenario == "pending" { draft.loading = [.before, .after] }
    if scenario == "error" { draft.error = ClipboardFileDiffStrings.localized(.enUS).unreadable }
    for width: CGFloat in [600, 420] {
        for (appearanceName, appearance, scheme) in [("light", NSAppearance.Name.aqua, ColorScheme.light), ("dark", .darkAqua, .dark)] {
            let frames = Frames()
            let view = NotchFileDiffView(service: service)
                .padding(.horizontal, 18).padding(.vertical, 12)
                .frame(width: width, height: 220)
                .background(Color.black)
                .coordinateSpace(name: "islandDropSurface")
                .onPreferenceChange(FileDiffDropFrames.self) { frames.values = $0 }
                .preferredColorScheme(scheme)
            let host = NSHostingView(rootView: view)
            let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: width, height: 220), styleMask: [.titled], backing: .buffered, defer: false)
            window.appearance = NSAppearance(named: appearance)
            window.contentView = host; window.makeKeyAndOrderFront(nil)
            drain(); host.layoutSubtreeIfNeeded(); host.displayIfNeeded()
            expect(frames.values.count == 2, "both targets publish native drop geometry")
            let before = frames.values[.before]!, after = frames.values[.after]!
            expect(before.width > 150 && after.width > 150 && before.height > 50 && after.height > 50, "small island keeps useful targets")
            expect(before.minX >= 0 && after.maxX <= width && before.minY >= 0 && before.maxY <= 220, "targets stay inside island")
            expect(before.maxX < after.minX && before.minY == after.minY && before.maxY == after.maxY, "targets align without overlap")
            let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
            host.cacheDisplay(in: host.bounds, to: bitmap)
            try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/clipboard-file-diff-\(scenario)-\(Int(width))-\(appearanceName).png"))
            window.orderOut(nil)
        }
    }
}
expect(NSPasteboard.general.changeCount == clipboardCount, "native presentation does not touch the clipboard")
print("PASS: \(checks) native file-drop layout checks; screenshots /tmp/clipboard-file-diff-*.png")
'''
# Reuse the established native editor fixture's types/helpers without executing its suite.
existing = ast.parse((repo / 'Tests/ClipboardDiffUITests.py').read_text())
shared = next(ast.literal_eval(node.value) for node in existing.body
              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'fixture' for target in node.targets))
editor = shared[:shared.index('let before = "Invoice total:')]
editor += r'''
let originalHistory = [ClipboardHistoryEntry(text: "saved clipboard text", copiedAt: Date())]
history.entries = originalHistory
let original = "{\"stage\":\"Q\"}\r\n\t", updated = "{\"stage\":\"P\"}\r\n\t"
let beforeName = "SAP-Finance-Products-CPI-Configuration-Before-Q-2026-10-23.properties"
let afterName = "SAP-Finance-Products-CPI-Configuration-After-P-2026-10-23.properties"
service.show(pair: .init(older: original, newer: updated), beforeName: beforeName, afterName: afterName)
let named = window(), inputs = editors(named)
expect(inputs[0].string == original && inputs[1].string == updated && settled(named), "supplied files open automatically with exact line endings")
for size in [NSSize(width: 980, height: 650), NSSize(width: 620, height: 440)] {
    capture(named, size.width < 700 ? "files-small" : "files", size: size)
    let fields = views(named.contentView!).compactMap { $0 as? NSTextField }
    let beforeLabel = fields.first { $0.stringValue.contains(beforeName) }!
    let afterLabel = fields.first { $0.stringValue.contains(afterName) }!
    let json = button(named, "diff.formatJSON")
    let content = named.contentView!
    let beforeFrame = beforeLabel.convert(beforeLabel.bounds, to: content)
    let afterFrame = afterLabel.convert(afterLabel.bounds, to: content)
    let jsonFrame = json.convert(json.bounds, to: content)
    expect(beforeFrame.width > 100 && afterFrame.width > 100, "filenames retain useful header width")
    expect(beforeFrame.height <= 20 && afterFrame.height <= 20, "long filenames remain one line clear of the editor divider")
    let summaryFrame = summary(named).convert(summary(named).bounds, to: content)
    expect(abs(jsonFrame.midY - summaryFrame.midY) <= 2, "JSON remains aligned with the toolbar status")
    expect(beforeFrame.maxX < afterFrame.minX && !beforeFrame.intersects(jsonFrame) && !afterFrame.intersects(jsonFrame),
           "long filenames never collide with the other pane or toolbar controls")
    expect(beforeLabel.lineBreakMode == .byTruncatingMiddle && afterLabel.lineBreakMode == .byTruncatingMiddle, "filename truncation retains meaningful ends")
    expect(beforeLabel.toolTip?.contains(beforeName) == true && afterLabel.toolTip?.contains(afterName) == true, "full filenames remain available in tooltips")
}
edit(inputs[1], "manual OCR correction\r\n")
expect(settled(named) && inputs[1].string == "manual OCR correction\r\n", "file comparison remains normally editable")
expect(history.entries.count == 1 && history.entries[0].text == originalHistory[0].text, "supplied pair never modifies clipboard history")
expect(NSPasteboard.general.changeCount == clipboardChangeCount, "file comparison does not modify system clipboard")
named.close()
service.show()
let regular = window()
expect(editors(regular).allSatisfy { $0.string.isEmpty }, "normal diff opening does not retain the file comparison")
expect(!views(regular.contentView!).compactMap { $0 as? NSTextField }.contains { $0.stringValue.contains(beforeName) || $0.stringValue.contains(afterName) }, "normal diff opening resets source names")
regular.close()
print("PASS: \(checks) native named-file editor checks; screenshots /tmp/clipboard-diff-files*.png")
'''
with tempfile.TemporaryDirectory(prefix='clipboard-file-diff-ui-') as temporary:
    folder = Path(temporary)
    main = folder / 'main.swift'
    main.write_text(island)
    binary = folder / 'island'
    sources = ['Core/ClipboardFileDiffStrings.swift', 'Core/ClipboardDiffStrings.swift', 'UI/Notch/NotchFileDiffView.swift']
    subprocess.run(['swiftc', *[str(repo / 'Sources/Vorssaint' / source) for source in sources], str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
    main.write_text(editor)
    support = (repo / 'Sources/Vorssaint/Services/Clipboard/ClipboardHistorySupport.swift').read_text()
    start = support.index('enum ClipboardJSONFormat {')
    end = support.index('/// How large a picture', start)
    formatter = folder / 'ClipboardJSONFormat.swift'
    formatter.write_text('import Foundation\n' + support[start:end])
    sources = ['Core/ClipboardDiffStrings.swift', 'Core/SharedToolActionStrings.swift', 'UI/ToolAppearance.swift', 'Services/Clipboard/ClipboardDiff.swift',
               'Services/Clipboard/ClipboardDiffEditor.swift', 'Services/Clipboard/ClipboardDiffService.swift']
    binary = folder / 'editor'
    subprocess.run(['swiftc', *[str(repo / 'Sources/Vorssaint' / source) for source in sources], str(formatter), str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
