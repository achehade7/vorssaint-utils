#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Check direct history-copy routing without screens or the system clipboard."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

method = declaration('Sources/Vorssaint/Services/QuickTools/RecentCaptureService.swift', '    func copyScreenshot(')
fixture = '''
import Foundation
struct RecentCaptureEntry { enum Kind { case screenshot, recording }; let kind: Kind }
enum AppFeature { case screenshot; static var enabled = true; var isAvailable: Bool { Self.enabled } }
enum NSSound { static var beeps = 0; static func beep() { beeps += 1 } }
enum ScreenshotSelectionController { struct Capture: Equatable { let pixels: Data; let scale: Double } }
final class ScreenshotService {
 static let shared = ScreenshotService()
 var copied: [ScreenshotSelectionController.Capture] = []
 func copyDirect(_ capture: ScreenshotSelectionController.Capture) { copied.append(capture) }
}
final class History {
 var loads = 0
 var completion: ((ScreenshotSelectionController.Capture?) -> Void)?
 func screenshot(for entry: RecentCaptureEntry, completion: @escaping (ScreenshotSelectionController.Capture?) -> Void) {
  loads += 1; self.completion = completion
 }
 // METHOD
}
let history = History()
let image = RecentCaptureEntry(kind: .screenshot)
let video = RecentCaptureEntry(kind: .recording)
let capture = ScreenshotSelectionController.Capture(pixels: Data([0,255,32,128]), scale: 2)
history.copyScreenshot(video)
precondition(history.loads == 0)
AppFeature.enabled = false
history.copyScreenshot(image)
precondition(history.loads == 0)
AppFeature.enabled = true
history.copyScreenshot(image)
precondition(history.loads == 1 && ScreenshotService.shared.copied.isEmpty)
history.completion?(capture)
precondition(ScreenshotService.shared.copied == [capture])
history.copyScreenshot(image)
history.completion?(nil)
precondition(NSSound.beeps == 1 && ScreenshotService.shared.copied == [capture])
history.copyScreenshot(image)
AppFeature.enabled = false
history.completion?(capture)
precondition(ScreenshotService.shared.copied == [capture])
print("PASS: 6 history-copy routing checks; no preview or real clipboard used")
'''.replace('// METHOD', method)
with tempfile.TemporaryDirectory(prefix='recent-copy-tests-') as temp:
    source = Path(temp)/'main.swift'
    source.write_text(fixture)
    binary = Path(temp)/'check'
    subprocess.run(['swiftc',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
