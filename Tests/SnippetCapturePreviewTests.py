#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native OCR preview/form rendering and the no-focus, three-second preview contract."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
import SwiftUI
import Combine

enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
enum FeatureStrings {}
enum Defaults { static let defaultSnippetSoundName = "Tink" }
enum DefaultsKey { static let textSnippets = "snippets" }
final class L10n: ObservableObject {
    static let shared = L10n(); let language = AppLanguage.enUS
    struct Strings { let ocrCopied = "Text copied", uninstallerCancel = "Cancel" }
    let s = Strings()
}
enum AppFeature { case textSnippets; var isAvailable: Bool { true } }
enum NotchNeonPalette {
    static let purple = Color(red: 0.73, green: 0.49, blue: 1)
    static let blue = Color(red: 0.43, green: 0.56, blue: 1)
}
final class SnippetLibraryService {
    static let shared = SnippetLibraryService()
    var captured: String?, saves = 0, hides = 0
    func saveCapturedText(_ text: String) { captured = text }
    func finishSave() { saves += 1 }
    func hide() { hides += 1 }
    func refreshPanelLayout() {}
}
final class NotchService {
    static let shared = NotchService()
    var acceptsSystemFeedback = true, expanded = false
    var captureControls: Int?
    var content: AnyView?, previewID: UUID?, tookFocus = false, height: CGFloat = 0
    func presentCapture(id: UUID, content: AnyView, height: CGFloat, takeFocus: Bool, closeOnCollapse: Bool,
                        fallback: @escaping () -> Void, close: @escaping () -> Void, hover: @escaping (Bool) -> Void) -> Bool {
        self.content = content; self.previewID = id; self.tookFocus = takeFocus; self.height = height
        return true
    }
    func removeCapture(id: UUID) { if previewID == id { content = nil; previewID = nil } }
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let attribute = "AXEnhancedUserInterface"
let getter = NSSelectorFromString("accessibilityAttributeValue:")
let setter = NSSelectorFromString("accessibilitySetValue:forAttribute:")
let previous = app.perform(getter, with: attribute)?.takeUnretainedValue() as? NSNumber ?? false
app.perform(setter, with: true, with: attribute)
defer { app.perform(setter, with: previous, with: attribute) }
let island = NotchService.shared
let controller = ScreenTextPreviewController.shared
precondition(controller.show(text: "SAP-531\nTransport ready\n01 12345"), "preview shown")
precondition(!island.tookFocus && island.height == 150 && SnippetLibraryService.shared.captured == nil,
             "OCR preview does not take focus or open a save form automatically")
let preview = NSHostingView(rootView: island.content!.background(Color.black).preferredColorScheme(.dark))
preview.frame = NSRect(x: 0, y: 0, width: 460, height: 150)
let window = NSWindow(contentRect: preview.frame, styleMask: [.titled], backing: .buffered, defer: false)
window.contentView = preview; window.orderFrontRegardless()
RunLoop.main.run(until: Date().addingTimeInterval(0.15))
preview.layoutSubtreeIfNeeded()
precondition(preview.fittingSize.height <= 150, "preview keeps existing compact height")
func render(_ host: NSView, to path: String) throws {
    host.layoutSubtreeIfNeeded()
    let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
    host.cacheDisplay(in: host.bounds, to: bitmap)
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
}
try render(preview, to: "/tmp/island-ocr-snippet-preview.png")
// Use the actual SwiftUI action through native accessibility.
func pressSave(_ element: AnyObject) -> Bool {
    if element.accessibilityIdentifier?() == "ocr.saveSnippet" {
        return element.accessibilityPerformPress?() ?? false
    }
    for child in element.accessibilityChildren?() ?? [] {
        if pressSave(child as AnyObject) { return true }
    }
    return false
}
precondition(pressSave(preview), "optional Save snippet action is clickable")
precondition(SnippetLibraryService.shared.captured == "SAP-531\nTransport ready\n01 12345" && island.previewID == nil,
             "action transfers the exact OCR result and closes preview")
precondition(controller.show(text: "paste immediately"))
RunLoop.main.run(until: Date().addingTimeInterval(3.15))
precondition(island.previewID == nil, "unattended preview still disappears after three seconds")
let draft = SnippetSaveDraft(text: "SAP-531\nTransport ready\n01 12345")
precondition(draft.temporary, "Until midnight starts checked")
draft.name = "transport"
let form = NSHostingView(rootView: SnippetSaveForm(draft: draft).frame(width: 460))
form.frame = NSRect(x: 0, y: 0, width: 460, height: 360)
window.contentView = form
window.setContentSize(form.fittingSize)
window.makeKeyAndOrderFront(nil)
RunLoop.main.run(until: Date().addingTimeInterval(0.15))
try render(form, to: "/tmp/island-snippet-save-form.png")
app.sendEvent(NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 1,
                             windowNumber: window.windowNumber, context: nil, characters: "\r",
                             charactersIgnoringModifiers: "\r", isARepeat: false, keyCode: 36)!)
RunLoop.main.run(until: Date().addingTimeInterval(0.05))
precondition(SnippetLibraryService.shared.saves == 1, "Return from name field invokes save")
window.orderOut(nil)
print("PASS: OCR optional action, exact-result draft, no focus, three-second expiry, form render and Return")
'''
with tempfile.TemporaryDirectory(prefix='snippet-capture-preview-') as folder:
    main = Path(folder) / 'main.swift'; main.write_text(code)
    binary = Path(folder) / 'tests'
    paths = ['Core/SnippetStrings.swift', 'Core/SnippetCaptureStrings.swift',
             'Services/Snippets/TextSnippetSupport.swift', 'Services/Snippets/SnippetSaveDraft.swift',
             'UI/SnippetSaveForm.swift', 'Services/QuickTools/ScreenTextPreviewController.swift']
    subprocess.run(['swiftc'] + [str(repo / 'Sources/Vorssaint' / path) for path in paths] + [str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
