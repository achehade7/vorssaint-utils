#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Render the production lock island without locking the Mac or changing preferences."""
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]


def declaration(path, marker):
    source = (repo / path).read_text()
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


view = "Sources/Vorssaint/UI/Notch/NotchLockScreenView.swift"
neon = "Sources/Vorssaint/UI/Notch/NotchNeonEdge.swift"
battery = "Sources/Vorssaint/UI/Notch/NotchBatteryPulse.swift"
full_charge = "Sources/Vorssaint/UI/Notch/NotchFullChargeEdge.swift"
unlock = "Sources/Vorssaint/UI/Notch/NotchUnlockHandoff.swift"
device = "Sources/Vorssaint/UI/Notch/NotchDeviceFeedback.swift"
production = "\n".join(declaration(path, marker) for path, markers in [
    (view, ["final class NotchLockScreenModel:", "struct NotchLockScreenIsland:",
            "private struct NotchLockScreenEdgePulse:", "private enum NotchLockScreenSurface"]),
    (neon, ["enum NotchNeonPalette", "enum NotchChargingSignal", "struct NotchChargingEdge:"]),
    (battery, ["enum NotchBatterySignal", "struct NotchBatteryEdge:"]),
    (full_charge, ["enum NotchFullChargeSignal", "struct NotchFullChargeEdge:"]),
    (unlock, ["enum NotchUnlockHandoffSignal", "struct NotchUnlockHandoffEdge:"]),
    (device, ["enum NotchDeviceFeedback:", "struct NotchDeviceNoticeEffect:"]),
    ("Sources/Vorssaint/UI/Notch/NotchDisplayArrivalEdge.swift", ["struct NotchDisplayArrivalEdge:"]),
    ("Sources/Vorssaint/UI/Notch/NotchView.swift", ["struct NotchShape:"]),
] for marker in markers)
# SwiftUI's accessibilityReduceMotion is read-only. Inject its value at this
# environment boundary while keeping both production rendering branches intact.
production = production.replace("@Environment(\\.accessibilityReduceMotion) private var reduceMotion",
                                'private let reduceMotion = CommandLine.arguments.contains("--reduce-motion")')
swift = r'''
import AppKit
import SwiftUI
final class NotchService { static let shared = NotchService(); let nightPalette = 0.0 }
struct NotchPlayback { let isPlaying = false }
final class NotchMusicService: ObservableObject { static let shared = NotchMusicService(); let playback: NotchPlayback? = nil }
enum NotchLockScreenSupport {
    static func showsMusic(isPlaying: Bool, playedWhileLocked: Bool) -> Bool { isPlaying || playedWhileLocked }
}
enum NotchEvent { case accessory, microphone, battery; var duration: TimeInterval { self == .accessory ? 4 : 1.6 } }
struct NotchNotice: Equatable {
    let event: NotchEvent, title: String, detail: String, symbol: String
    var audioHandoff = false
}
struct NotchGeometry {
    let bareCutout = CGSize(width: 185, height: 32)
    let compactMusicArtworkSide: CGFloat = 20, compactMusicArtworkInset: CGFloat = 12
    let compactMusicBarHeight: CGFloat = 14, compactMusicBarsInset: CGFloat = 12
    let floatingGap: CGFloat? = nil
}
enum NotchLayout {
    static let compactMusicBarCount = 7
    static let compactMusicBarWidth: CGFloat = 1.8, compactMusicBarsWidth: CGFloat = 22.8
    static func surfaceRadius(height: CGFloat) -> CGFloat { min(28, height * 0.34) }
    static func shoulder(height: CGFloat) -> CGFloat { min(14, height * 0.19) }
    static func capsulePath(in rect: CGRect, gap: CGFloat) -> CGPath {
        CGPath(roundedRect: rect.insetBy(dx: 0, dy: gap), cornerWidth: 12, cornerHeight: 12, transform: nil)
    }
}
// No music is playing in these fixtures. Keep the absent equalizer's layout.
struct NotchEqualizerBars: View {
    let isPlaying: Bool, bars: Int, barWidth: CGFloat, height: CGFloat, tint: Color
    var body: some View { Color.clear.frame(width: 22.8, height: height) }
}
PRODUCTION
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    if !condition { FileHandle.standardError.write(Data(("FAIL: " + message + "\n").utf8)); exit(1) }
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
func pump(_ seconds: TimeInterval) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
private let model = NotchLockScreenModel()
private let content = NotchLockScreenIsland(model: model, size: CGSize(width: 300, height: 36), cameraWidth: 185,
                                          geometry: NotchGeometry(), window: CGSize(width: 320, height: 50),
                                          origin: CGPoint(x: 10, y: 4))
private let host = NSHostingView(rootView: content.background(Color(white: 0.07)).preferredColorScheme(.dark))
host.frame = NSRect(x: 0, y: 0, width: 320, height: 50)
let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
window.contentView = host; window.orderFrontRegardless()
defer { window.orderOut(nil) }
pump(0.1)
struct Pixels { let edge: Int, icon: Int; let bitmap: NSBitmapImageRep }
func snapshot(_ name: String? = nil) -> Pixels {
    host.layoutSubtreeIfNeeded()
    let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
    host.cacheDisplay(in: host.bounds, to: bitmap)
    let scale = CGFloat(bitmap.pixelsHigh) / host.bounds.height
    var edge = 0, icon = 0
    for y in 0..<bitmap.pixelsHigh { for x in 0..<bitmap.pixelsWide {
        let pixel = bitmap.colorAt(x: x, y: y)!.usingColorSpace(.sRGB)!
        let channels = [pixel.redComponent, pixel.greenComponent, pixel.blueComponent]
        if channels.max()! > 0.15 && channels.max()! - channels.min()! > 0.08 {
            if CGFloat(y) / scale >= 34 { edge += 1 }
            else { icon += 1 }
        }
    } }
    if let name { try! bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent(name + ".png")) }
    return Pixels(edge: edge, icon: icon, bitmap: bitmap)
}
func waitForEdge(_ name: String, timeout: TimeInterval = 1) {
    let end = Date().addingTimeInterval(timeout)
    var pixels = snapshot()
    while pixels.edge == 0, Date() < end { pump(0.025); pixels = snapshot() }
    _ = snapshot(name)
    expect(pixels.edge > 0, name + " must still light the lower edge")
}
func waitForRest(_ message: String, timeout: TimeInterval) {
    let end = Date().addingTimeInterval(timeout)
    var pixels = snapshot()
    while pixels.edge != 0, Date() < end { pump(0.025); pixels = snapshot() }
    expect(pixels.edge == 0, message)
}
let resting = snapshot("resting")
expect(resting.edge == 0, "resting lock island must have no persistent lower-edge glow")
expect(resting.icon > 0, "resting lock glyph remains visible")
model.lockRippleID = UUID()
waitForEdge("locking")
waitForRest("lock-entry glow fades fully to the unlit resting edge", timeout: 2)
_ = snapshot("after-locking")
model.chargingPercent = 64; model.chargingArrivalID = UUID()
waitForEdge("charging")
waitForRest("charging glow also returns to the unlit resting edge", timeout: 3)
model.lowBatteryAt = Date().addingTimeInterval(-0.4); model.lowBatteryPercent = 10
pump(0.05); waitForEdge("low-battery")
model.lowBatteryAt = nil; model.lowBatteryPercent = nil; pump(0.05)
model.fullChargeAt = Date().addingTimeInterval(-0.9)
pump(0.05); waitForEdge("full-charge")
model.fullChargeAt = nil; pump(0.05)
model.displayArrival = NotchDisplayArrival(began: Date().addingTimeInterval(-0.35), direction: .init(x: 1, y: 0))
pump(0.05); waitForEdge("display-arrival")
model.displayArrival = nil; pump(0.05)
model.unlockHandoffAt = Date()
waitForEdge("unlocking", timeout: 0.2)
model.unlockHandoffAt = nil; pump(0.05)
expect(snapshot().edge == 0, "all completed event overlays leave no permanent neon")
print("PASS: \(checks) native lock-neon checks; screenshots: \(output.path)")
'''.replace("PRODUCTION", production)
with tempfile.TemporaryDirectory(prefix="notch-lock-neon-") as temporary:
    source = Path(temporary) / "main.swift"
    source.write_text(swift)
    binary = Path(temporary) / "checks"
    subprocess.run(["xcrun", "swiftc", "-target", "arm64-apple-macosx14.0", "-sdk",
                    "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk", "-Xfrontend",
                    "-interface-compiler-version", "-Xfrontend", "6.3.2", str(source),
                    str(repo / "Sources/Vorssaint/Services/Notch/NotchDisplayConnectionSupport.swift"),
                    "-o", str(binary)], check=True)
    output = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vorssaint-lock-neon"
    subprocess.run([str(binary), output], check=True)
    subprocess.run([str(binary), output + "-reduced-motion", "--reduce-motion"], check=True)
