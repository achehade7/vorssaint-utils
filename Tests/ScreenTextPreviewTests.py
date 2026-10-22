#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise the real OCR preview/controller with an isolated island host."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/QuickTools/ScreenTextPreviewController.swift").read_text()
fixture = r'''
import AppKit
import SwiftUI
struct L10n {
    static let shared = Self()
    struct Strings { let ocrCopied = "Text copied" }
    let s = Strings()
}
final class NotchService {
    static let shared = NotchService()
    var acceptsSystemFeedback = true, expanded = false, routes = true
    var captureControls: Int?
    var id: UUID?, content: AnyView?, closeHandler: (() -> Void)?
    var takesFocus = true, closesOnCollapse = false
    func presentCapture(id: UUID, content: AnyView, height: CGFloat,
                        takeFocus: Bool, closeOnCollapse: Bool,
                        fallback: @escaping () -> Void, close: @escaping () -> Void,
                        hover: @escaping (Bool) -> Void) -> Bool {
        guard routes else { return false }
        self.id = id; self.content = content; closeHandler = close
        takesFocus = takeFocus; closesOnCollapse = closeOnCollapse
        expanded = true
        return true
    }
    func removeCapture(id: UUID) {
        guard self.id == id else { return }
        self.id = nil; content = nil; closeHandler = nil; expanded = false
    }
}
func wait(_ seconds: Double) {
    RunLoop.main.run(until: Date(timeIntervalSinceNow: seconds))
}
let island = NotchService.shared
let preview = ScreenTextPreviewController.shared
precondition(preview.show(text: "123\n456\n789"))
precondition(!island.takesFocus && island.closesOnCollapse)
let host = NSHostingView(rootView: island.content!)
host.frame = NSRect(x: 0, y: 0, width: 420, height: 150)
host.layoutSubtreeIfNeeded()
let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
host.cacheDisplay(in: host.bounds, to: bitmap)
precondition(bitmap.pixelsWide >= 420 && bitmap.pixelsHigh >= 150)
wait(2.8)
precondition(island.id != nil, "preview must last nearly three seconds")
wait(0.35)
precondition(island.id == nil, "preview must disappear after three seconds")
precondition(preview.show(text: "old"))
wait(1)
precondition(preview.show(text: "new"))
let replacement = island.id
wait(2.1)
precondition(island.id == replacement, "old timer must not close new preview")
island.closeHandler?()
precondition(island.id == nil, "collapse/lock must discard the preview")
island.expanded = true
precondition(!preview.show(text: "do not replace an open tool"))
island.expanded = false; island.captureControls = 1
precondition(!preview.show(text: "do not replace capture controls"))
island.captureControls = nil; island.acceptsSystemFeedback = false
precondition(!preview.show(text: "hidden"))
island.acceptsSystemFeedback = true; island.routes = false
precondition(!preview.show(text: "capture routing disabled"))
island.routes = true
precondition(preview.show(text: String(repeating: "column value\n", count: 2000)))
// An old completion must not remove a different capture now hosted by the island.
island.id = UUID()
let other = island.id
preview.close()
precondition(island.id == other)
print("OCR preview: timing, focus, rendering, replacement and dismissal checks passed")
'''
with tempfile.TemporaryDirectory(prefix="ocr-preview-tests-") as temporary:
    folder = Path(temporary)
    swift = folder / "main.swift"
    swift.write_text(source + "\n" + fixture)
    binary = folder / "preview-tests"
    subprocess.run(["swiftc", str(swift), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
