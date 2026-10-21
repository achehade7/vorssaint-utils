#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint

"""Exercise display arrival detection against actual screen-coordinate layouts."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = repo / "Sources/Vorssaint/Services/Notch/NotchDisplayConnectionSupport.swift"
view = repo / "Sources/Vorssaint/UI/Notch/NotchDisplayArrivalEdge.swift"
shape_source = (repo / "Sources/Vorssaint/UI/Notch/NotchView.swift").read_text()
shape_start = shape_source.index("struct NotchShape: Shape")
shape_end = shape_source.index("{", shape_start) + 1
depth = 1
while depth:
    depth += (shape_source[shape_end] == "{") - (shape_source[shape_end] == "}")
    shape_end += 1
shape_declaration = shape_source[shape_start:shape_end]
swift = r'''
import CoreGraphics
import Foundation

var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    guard condition else { fatalError(message) }
}
func close(_ value: CGFloat, _ expected: CGFloat) -> Bool { abs(value - expected) < 0.0001 }
let builtIn = CGRect(x: 0, y: 0, width: 1512, height: 982)
let right = builtIn.offsetBy(dx: 1512, dy: 0)
let left = builtIn.offsetBy(dx: -1512, dy: 0)
let upper = builtIn.offsetBy(dx: 0, dy: 982)
let lower = builtIn.offsetBy(dx: 0, dy: -982)
var tracker = NotchDisplayConnectionTracker()
expect(tracker.update([1: builtIn, 2: right], sourceID: 1) == nil, "startup is a silent baseline")
expect(tracker.update([1: builtIn, 2: right], sourceID: 1) == nil, "brightness notifications do not announce a monitor")
expect(tracker.update([1: builtIn, 2: left], sourceID: 1) == nil, "rearranging existing monitors stays silent")
expect(tracker.update([1: builtIn], sourceID: 1) == nil, "disconnection stays silent")
let reconnect = tracker.update([1: builtIn, 2: right], sourceID: 1)
expect(reconnect == NotchDisplayConnectionDirection(x: 1, y: 0), "a genuine reconnection points right")
expect(tracker.update([1: builtIn, 2: right], sourceID: 1) == nil, "each new monitor signals only once")

for (frame, expected, name) in [(right, NotchDisplayConnectionDirection(x: 1, y: 0), "right"),
                              (left, NotchDisplayConnectionDirection(x: -1, y: 0), "left"),
                              (upper, NotchDisplayConnectionDirection(x: 0, y: 1), "above"),
                              (lower, NotchDisplayConnectionDirection(x: 0, y: -1), "below")] {
    tracker.reset([1: builtIn])
    expect(tracker.update([1: builtIn, 2: frame], sourceID: 1) == expected, "direction follows a monitor " + name)
}
tracker.reset([1: builtIn])
let diagonal = tracker.update([1: builtIn, 2: builtIn.offsetBy(dx: -900, dy: 1200)], sourceID: 1)
expect(diagonal.map { close($0.x, -0.6) && close($0.y, 0.8) } == true, "diagonal uses a normalized actual-frame vector")
tracker.reset([1: builtIn, 2: right])
expect(tracker.update([1: builtIn, 2: right], sourceID: 1) == nil, "resuming resets already attached displays silently")
tracker.reset([1: builtIn])
expect(tracker.update([2: right], sourceID: 1) == nil, "a removed source cannot point from a stale location")
tracker.reset([1: builtIn])
expect(tracker.update([1: builtIn, 2: right], sourceID: 2) == nil, "a newly selected source has no previous location")
tracker.reset([1: builtIn])
expect(tracker.update([1: builtIn, 2: right], sourceID: nil) == nil, "missing island display stays silent")
tracker.reset([1: builtIn])
expect(tracker.update([1: builtIn, 2: builtIn], sourceID: 1) == nil, "a mirrored center has no directional sweep")
tracker.reset([1: builtIn])
expect(tracker.update([1: builtIn, 2: .zero, 3: .null, 4: .infinite], sourceID: 1) == nil,
       "unusable transient display frames do not produce a direction")
tracker.reset([1: builtIn])
expect(tracker.update([1: builtIn, 2: right, 3: upper], sourceID: 1) == NotchDisplayConnectionDirection(x: 0, y: 1),
       "simultaneous connections choose the nearest actual display")
tracker.reset([1: builtIn])
expect(tracker.update([1: builtIn, 2: right, 3: left], sourceID: 1) == NotchDisplayConnectionDirection(x: 1, y: 0),
       "equally distant arrivals choose a stable display identifier")
let translated = builtIn.offsetBy(dx: 500, dy: -400)
tracker.reset([1: builtIn])
expect(tracker.update([1: translated, 2: translated.offsetBy(dx: -1512, dy: 0)], sourceID: 1)
        == NotchDisplayConnectionDirection(x: -1, y: 0), "a changed desktop origin does not reverse direction")
expect(NotchDisplayArrivalSignal.opacity(at: -0.1) == 0, "future signal is invisible")
expect(NotchDisplayArrivalSignal.opacity(at: 0) == 0, "arrival starts without a flash")
expect(NotchDisplayArrivalSignal.opacity(at: 0.4) == 1, "arrival has a visible middle")
expect(NotchDisplayArrivalSignal.opacity(at: 1) < 0.3, "arrival fades away smoothly")
expect(NotchDisplayArrivalSignal.opacity(at: NotchDisplayArrivalSignal.duration) == 0,
       "arrival fully expires")
expect(NotchDisplayArrivalSignal.opacity(at: 20) == 0, "expired events stay invisible")
print("Notch display connection: \(checks) checks passed")
'''
render_swift = r'''
import AppKit
import SwiftUI

enum NotchNeonPalette {
    static let blue = Color(red: 0.486, green: 0.6, blue: 1)
    static let purple = Color(red: 0.72, green: 0.53, blue: 1)
}
struct NotchGeometry { var floatingGap: CGFloat? = nil }
enum NotchLayout {
    static func surfaceRadius(height: CGFloat) -> CGFloat { min(28, height * 0.34) }
    static func shoulder(height: CGFloat) -> CGFloat { min(14, height * 0.19) }
    static func capsulePath(in rect: CGRect, gap: CGFloat) -> CGPath {
        CGPath(roundedRect: rect.insetBy(dx: 0, dy: gap), cornerWidth: 12, cornerHeight: 12, transform: nil)
    }
}
final class NotchService: ObservableObject {
    var displayArrival: NotchDisplayArrival?
    var displayIsFullscreen = true, acceptsSystemFeedback = true
    var expanded = false, peeking = false, dragPlaceholder = false, showsAeroSpace = false
    var captureControls: Int? = nil
    var surfaceSize = CGSize(width: 265, height: 32)
    var geometry = NotchGeometry()
}
enum FixtureClock { static var date = Date(); static var reduced = false }
@propertyWrapper struct Environment<Value> {
    init(_ keyPath: KeyPath<EnvironmentValues, Value>) {}
    var wrappedValue: Value { FixtureClock.reduced as! Value }
}
enum FixtureSchedule {
    case animation
    static func animation(minimumInterval: TimeInterval) -> Self { .animation }
}
struct FixtureTimelineContext { let date: Date }
struct TimelineView<Content: View>: View {
    let content: Content
    init(_ schedule: FixtureSchedule, @ViewBuilder content: (FixtureTimelineContext) -> Content) {
        self.content = content(FixtureTimelineContext(date: FixtureClock.date))
    }
    var body: some View { content }
}
@MainActor func pixels(_ direction: NotchDisplayConnectionDirection, age: Double,
                       reduced: Bool = false) -> (x: Double, y: Double, lit: Int, data: Data) {
    let size = CGSize(width: 265, height: 32)
    let shape = Path(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: 11)
    let content = NotchDisplayArrivalEdge(shape: shape, size: size, direction: direction,
                                        age: age, reduceMotion: reduced)
        .frame(width: size.width, height: size.height)
        // Match the opaque 185-point camera that hid the earlier idle effect.
        .overlay { Rectangle().fill(.black).frame(width: 185, height: 32) }
        .padding(5).background(.black)
    let renderer = ImageRenderer(content: content)
    renderer.scale = 2
    let image = NSBitmapImageRep(data: renderer.nsImage!.tiffRepresentation!)!
    var sumX = 0.0, sumY = 0.0, weight = 0.0, lit = 0
    for y in 0..<image.pixelsHigh {
        for x in 0..<image.pixelsWide {
            let color = image.colorAt(x: x, y: y)!.usingColorSpace(.deviceRGB)!
            guard color.blueComponent > 0.08 else { continue }
            let brightness = color.blueComponent
            sumX += Double(x) * brightness; sumY += Double(y) * brightness
            weight += brightness; lit += 1
        }
    }
    return (sumX / max(1, weight), sumY / max(1, weight), lit,
            image.representation(using: .png, properties: [:])!)
}
@MainActor func fullscreenPixels(_ direction: NotchDisplayConnectionDirection, age: Double,
                                 width: CGFloat, reduced: Bool = false) -> Int {
    let service = NotchService()
    service.surfaceSize.width = width
    service.displayArrival = NotchDisplayArrival(began: Date(timeIntervalSince1970: 1000), direction: direction)
    FixtureClock.date = Date(timeIntervalSince1970: 1000 + age)
    FixtureClock.reduced = reduced
    let content = NotchFullscreenDisplayPulse(service: service)
        .frame(width: width, height: 32)
        .overlay { Rectangle().fill(.black).frame(width: 185, height: 32) }
        .padding(5).background(.black)
    let renderer = ImageRenderer(content: content)
    renderer.scale = 2
    let image = NSBitmapImageRep(data: renderer.nsImage!.tiffRepresentation!)!
    var lit = 0
    for y in 0..<image.pixelsHigh {
        for x in 0..<image.pixelsWide {
            let color = image.colorAt(x: x, y: y)!.usingColorSpace(.deviceRGB)!
            guard color.blueComponent > 0.08 else { continue }
            lit += 1
            precondition(y < 64, "fullscreen signal must leave bottom five points and the app below clear")
            precondition(x < 40 || x >= image.pixelsWide - 40, "fullscreen signal must stay inside the side edges")
        }
    }
    return lit
}
MainActor.assumeIsolated {
    NSApplication.shared.setActivationPolicy(.prohibited)
    for (name, direction) in [("right", NotchDisplayConnectionDirection(x: 1, y: 0)),
                              ("left", NotchDisplayConnectionDirection(x: -1, y: 0)),
                              ("above", NotchDisplayConnectionDirection(x: 0, y: 1)),
                              ("below", NotchDisplayConnectionDirection(x: 0, y: -1))] {
        let early = pixels(direction, age: 0.16), late = pixels(direction, age: 0.72)
        precondition(early.lit > 20 && late.lit > 20, name + " sweep must survive the physical camera mask")
        switch name {
        case "right": precondition(late.x > early.x + 100, "rightward light must travel right")
        case "left": precondition(late.x < early.x - 100, "leftward light must travel left")
        case "above": precondition(late.y < early.y - 15, "upward light must travel upward")
        default: precondition(late.y > early.y + 15, "downward light must travel downward")
        }
    }
    let right = NotchDisplayConnectionDirection(x: 1, y: 0)
    let reducedEarly = pixels(right, age: 0.2, reduced: true)
    let reducedLate = pixels(right, age: 0.7, reduced: true)
    precondition(reducedEarly.data == reducedLate.data, "Reduce Motion must keep the light stationary")
    precondition(pixels(right, age: -0.1).lit == 0, "unstarted signal must be invisible")
    precondition(pixels(right, age: NotchDisplayArrivalSignal.duration).lit == 0,
                 "expired signal must leave no pixels")
    print("Notch display arrival rendering: all four directions, camera cutout, Reduce Motion and expiry passed")
    for width: CGFloat in [265, 285] {
        for direction in [right, NotchDisplayConnectionDirection(x: -1, y: 0),
                          NotchDisplayConnectionDirection(x: 0, y: 1), NotchDisplayConnectionDirection(x: 0, y: -1)] {
            let counts = [0.1, 0.16, 0.55, 0.72, 0.82].map {
                fullscreenPixels(direction, age: $0, width: width)
            }
            precondition(counts.max()! > 20, "fullscreen arrival must be visible outside the idle/busy physical camera")
            let first = fullscreenPixels(direction, age: 0.2, width: width, reduced: true)
            let later = fullscreenPixels(direction, age: 0.7, width: width, reduced: true)
            precondition(first > 20 && first == later, "fullscreen Reduce Motion cue must remain still")
            precondition(fullscreenPixels(direction, age: 1.1, width: width) == 0,
                         "fullscreen arrival must completely expire")
        }
    }
    print("Notch fullscreen display arrival: idle/busy camera cutout, side-only drawing, no bottom/app spill, Reduce Motion and expiry passed")
}
'''
with tempfile.TemporaryDirectory(prefix="notch-display-tests-") as directory:
    path = Path(directory)
    main = path / "main.swift"
    main.write_text(swift)
    executable = path / "tests"
    subprocess.run(["xcrun", "swiftc", str(source), str(main), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
    main.write_text(render_swift)
    shape = path / "shape.swift"
    shape.write_text("import SwiftUI\n" + shape_declaration)
    subprocess.run(["xcrun", "swiftc", str(source), str(view), str(shape), str(main), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
