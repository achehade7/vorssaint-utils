#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint

"""Render the actual separate neon host while quiet-mode height collapses."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/UI/Notch/NotchNeonEdge.swift").read_text()
start = source.index("struct NotchNeonView: View")
end = source.index("{", start) + 1
depth = 1
while depth:
    depth += (source[end] == "{") - (source[end] == "}")
    end += 1
swift = r'''
import AppKit
import SwiftUI
final class NotchService: ObservableObject {
    var quietMode = false, displayIsFullscreen = false
    var captureControls: Bool?
}
final class NotchQuickAccessMotion: ObservableObject {
    var neonCanvasOffset = CGPoint.zero, workspaceDeparting = false
    var workspaceSurfaceFrame: CGRect?, neonPointer: CGPoint?
}
final class NotchBackdropPresentation: ObservableObject { var contour = Path() }
struct NotchNeonEdge: View {
    let service: NotchService, surfaceSize: CGSize
    let contour: Path?
    let pointerX: CGFloat?
    static let drop: CGFloat = 2
    var body: some View {
        VStack(spacing: 0) { Spacer(minLength: 0); Rectangle().fill(.purple).frame(height: 2) }
    }
}
PRODUCTION_VIEW
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    if !condition { print("FAIL: " + message); exit(1) }
}
@MainActor func rows(height: CGFloat, quiet: Bool, workspace: Bool = false,
                     fullscreen: Bool = false, capturing: Bool = false) -> Set<Int> {
    let service = NotchService(), motion = NotchQuickAccessMotion(), backdrop = NotchBackdropPresentation()
    service.quietMode = quiet; service.displayIsFullscreen = fullscreen
    service.captureControls = capturing ? true : nil
    backdrop.contour = Path(CGRect(x: 0, y: 0, width: 280, height: height))
    if workspace { motion.workspaceSurfaceFrame = CGRect(x: 0, y: 0, width: 300, height: 36) }
    let view = NotchNeonView(service: service, motion: motion, backdrop: backdrop)
        .frame(width: 320, height: 80).background(.black)
    let renderer = ImageRenderer(content: view)
    guard let image = renderer.cgImage else { fatalError("neon host did not render") }
    let bitmap = NSBitmapImageRep(cgImage: image)
    var lit: Set<Int> = []
    for y in 0..<bitmap.pixelsHigh {
        for x in 0..<bitmap.pixelsWide {
            if let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB),
               c.blueComponent > 0.5 && c.redComponent > 0.3 { lit.insert(y) }
        }
    }
    return lit
}
MainActor.assumeIsolated {
    expect(rows(height: 36, quiet: false) == [36, 37], "normal neon remains at the lower edge")
    for height: CGFloat in [36, 28, 18, 8, 2, 0] {
        expect(rows(height: height, quiet: true).isEmpty,
               "quiet mode must leave no travelling neon at contour height \(height)")
        expect(rows(height: height, quiet: true, workspace: true).isEmpty,
               "a lingering workspace contour cannot retain neon in quiet mode")
    }
    expect(rows(height: 36, quiet: false) == [36, 37], "restoring shows the original lower edge")
    expect(rows(height: 36, quiet: false, fullscreen: true).isEmpty, "fullscreen remains neon-free")
    expect(rows(height: 36, quiet: false, capturing: true).isEmpty, "capture controls remain neon-free")
}
print("PASS: \(checks) quiet neon render checks")
'''.replace("PRODUCTION_VIEW", source[start:end])
with tempfile.TemporaryDirectory(prefix="notch-quiet-neon-") as directory:
    path = Path(directory) / "main.swift"
    path.write_text(swift)
    subprocess.run(["xcrun", "swift", str(path)], check=True)
