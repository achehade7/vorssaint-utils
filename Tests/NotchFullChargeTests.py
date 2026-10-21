#!/usr/bin/env python3
"""Render full-charge feedback around the physical camera in every surface."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]


def declaration(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


source = (repo / "Sources/Vorssaint/UI/Notch/NotchFullChargeEdge.swift").read_text()
shape = (repo / "Sources/Vorssaint/UI/Notch/NotchView.swift").read_text()
production = "import SwiftUI\n" + "\n".join([
    declaration(source, "enum NotchFullChargeSignal"),
    declaration(source, "struct NotchFullChargeEdge:"),
    declaration(shape, "struct NotchShape:"),
])
swift = r'''
import AppKit
import SwiftUI
enum NotchNeonPalette { static let charging = Color(red: 76.0 / 255, green: 1, blue: 136.0 / 255) }
struct NotchGeometry { var floatingGap: CGFloat? = nil }
enum NotchLayout {
    static func surfaceRadius(height: CGFloat) -> CGFloat { min(28, height * 0.34) }
    static func shoulder(height: CGFloat) -> CGFloat { min(14, height * 0.19) }
    static func capsulePath(in rect: CGRect, gap: CGFloat) -> CGPath {
        CGPath(roundedRect: rect.insetBy(dx: 0, dy: gap), cornerWidth: 12, cornerHeight: 12, transform: nil)
    }
}
var checks = 0
func expect(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
struct Pixels { let lit: Int; let meanDistance: Double; let middle: Int; let bitmap: NSBitmapImageRep }
@MainActor func pixels(width: CGFloat, height: CGFloat, age: TimeInterval, fullscreen: Bool,
                       drop: CGFloat, reduced: Bool = false) -> Pixels {
    let size = CGSize(width: width, height: height)
    let shape = NotchShape(attached: true, radius: NotchLayout.surfaceRadius(height: height))
        .path(in: CGRect(origin: .zero, size: size))
    let light = NotchFullChargeEdge(shape: shape, size: size, age: age,
                                   fullscreen: fullscreen, reduceMotion: reduced)
        .frame(width: width, height: height)
    let root = ZStack(alignment: .top) {
        Color.black
        if fullscreen { light.clipShape(shape) } else { light.offset(y: drop) }
        Rectangle().fill(.black).frame(width: 185, height: 32)
    }.frame(width: width, height: height + 8)
    let renderer = ImageRenderer(content: root)
    renderer.scale = 2
    let image = NSBitmapImageRep(cgImage: renderer.cgImage!)
    var lit = 0, middle = 0, distance = 0.0
    for y in 0..<image.pixelsHigh { for x in 0..<image.pixelsWide {
        let color = image.colorAt(x: x, y: y)!.usingColorSpace(.deviceRGB)!
        let r = color.redComponent, g = color.greenComponent, b = color.blueComponent
        if g > 0.2 && g > r + 0.08 && g > b + 0.05 {
            lit += 1
            distance += abs(Double(x) - width)
            if abs(CGFloat(x) / 2 - width / 2) < 24 { middle += 1 }
            if fullscreen {
                expect(CGFloat(y) / 2 < height - 4, "fullscreen completion must leave lower edge and application untouched")
                expect(x < 18 || x >= image.pixelsWide - 18, "fullscreen completion stays within outer side contours")
            }
        }
    } }
    return Pixels(lit: lit, meanDistance: lit == 0 ? 0 : distance / Double(lit), middle: middle, bitmap: image)
}
MainActor.assumeIsolated {
    NSApplication.shared.setActivationPolicy(.prohibited)
    expect(NotchFullChargeSignal.progress(at: 0) == 0
           && NotchFullChargeSignal.progress(at: NotchFullChargeSignal.travelDuration) == 1,
           "two beams travel all the way to their common midpoint")
    for reduced in [false, true] {
        expect(NotchFullChargeSignal.flashOpacity(at: -0.1, reduceMotion: reduced) == 0
               && NotchFullChargeSignal.flashOpacity(at: NotchFullChargeSignal.duration, reduceMotion: reduced) == 0,
               "soft flash is finite in normal and reduced motion")
        expect(NotchFullChargeSignal.flashOpacity(at: 1.0, reduceMotion: reduced) > 0.3,
               "soft flash visibly follows the convergence")
    }
    for (name, width, height, drop) in [("desktop", 265.0, 32.0, 2.0), ("lock", 265.0, 36.0, 0.0)] {
        let early = pixels(width: width, height: height, age: 0.18, fullscreen: false, drop: drop)
        let late = pixels(width: width, height: height, age: 0.6, fullscreen: false, drop: drop)
        let flash = pixels(width: width, height: height, age: 1.1, fullscreen: false, drop: drop)
        expect(early.lit > 20 && late.lit > 20, "\(name) beams survive the physical camera")
        expect(late.meanDistance < early.meanDistance - 40, "\(name) beams converge toward center")
        expect(flash.middle > 15, "\(name) soft flash is visible below the camera")
        for reduced in [false, true] {
            expect(pixels(width: width, height: height, age: -0.1, fullscreen: false, drop: drop, reduced: reduced).lit == 0,
                   "\(name) signal stays absent before event")
            expect(pixels(width: width, height: height, age: 1.7, fullscreen: false, drop: drop, reduced: reduced).lit == 0,
                   "\(name) completion leaves no persistent green")
            expect(pixels(width: width, height: height, age: 0.85, fullscreen: false, drop: drop, reduced: reduced).lit > 20,
                   "\(name) full charge remains visible with Reduce Motion")
        }
    }
    for (width, height) in [(265.0, 32.0), (285.0, 36.0)] {
        for reduced in [false, true] {
            let moving = pixels(width: width, height: height, age: 0.4, fullscreen: true, drop: 0, reduced: reduced)
            let flash = pixels(width: width, height: height, age: 1.1, fullscreen: true, drop: 0, reduced: reduced)
            expect(moving.lit > 10 && flash.lit > 10, "idle/busy fullscreen shows convergence and soft flash outside camera")
            expect(moving.middle == 0 && flash.middle == 0, "fullscreen never draws under physical camera")
            expect(pixels(width: width, height: height, age: 1.7, fullscreen: true, drop: 0, reduced: reduced).lit == 0,
                   "fullscreen completion expires completely")
        }
    }
    print("PASS: \(checks) full-charge renderer checks: desktop, lock, idle/busy fullscreen, camera mask, Reduce Motion, no lower spill, expiry")
}
'''
with tempfile.TemporaryDirectory(prefix="notch-full-charge-") as directory:
    path = Path(directory)
    (path / "production.swift").write_text(production)
    (path / "main.swift").write_text(swift)
    binary = path / "check"
    subprocess.run(["xcrun", "swiftc", "-sdk", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk",
                    str(path / "production.swift"), str(path / "main.swift"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
