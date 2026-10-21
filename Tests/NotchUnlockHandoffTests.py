#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint

"""Render both handoff halves and exercise production cancellation/expiry."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]


def declaration(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


view = (repo / "Sources/Vorssaint/UI/Notch/NotchUnlockHandoff.swift").read_text()
service = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()
swift = r'''
import AppKit
import SwiftUI
SIGNAL
EDGE
enum NotchNeonPalette {
    static let purple = Color(red: 0.72, green: 0.53, blue: 1)
    static let blue = Color(red: 0.486, green: 0.6, blue: 1)
}
struct Session { var canPresent = true }
final class Service {
    var session = Session(), acceptsSystemFeedback = true
    var neonUnlockAt: Date?, unlockHandoffWork: DispatchWorkItem?
    var refreshes = 0
    func refreshPresentation(animated: Bool) { refreshes += 1 }
PLAY
CLEAR
}
var checks = 0
func expect(_ condition: Bool, _ description: String) {
    checks += 1
    precondition(condition, description)
}
let signal = NotchUnlockHandoffSignal.self
expect(signal.opacity(age: 0, leaving: true) == 1, "lock starts with its glow")
expect(signal.opacity(age: 0.15, leaving: true) > 0, "lock contracts before leaving")
expect(signal.opacity(age: signal.contraction, leaving: true) == 0, "lock half ends before desktop return")
expect(signal.opacity(age: 0.15, leaving: false) == 0, "desktop waits for contraction")
expect(signal.opacity(age: 0.55, leaving: false) > 0.9, "desktop returns visibly")
for leaving in [true, false] {
    for age in [-1.0, Double.nan, Double.infinity, signal.duration, 90] {
        expect(signal.opacity(age: age, leaving: leaving) == 0, "invalid/expired signal is invisible")
    }
    expect(signal.width(age: 0.05, leaving: leaving, reduceMotion: true) == 1
        && signal.width(age: 0.8, leaving: leaving, reduceMotion: true) == 1,
        "Reduce Motion does not scale the edge")
}
let state = Service()
let first = Date()
state.playUnlockHandoff(at: first)
let oldWork = state.unlockHandoffWork
expect(state.neonUnlockAt == first && state.refreshes == 1, "handoff begins from its shared timestamp")
let second = first.addingTimeInterval(0.1)
state.playUnlockHandoff(at: second)
oldWork?.perform()
expect(state.neonUnlockAt == second && oldWork?.isCancelled == true, "old expiry cannot clear newer handoff")
state.clearUnlockHandoff()
expect(state.neonUnlockAt == nil && state.unlockHandoffWork == nil, "teardown cancels the clock and clears the signal")
state.session.canPresent = false
state.playUnlockHandoff(at: first)
expect(state.neonUnlockAt == nil, "locked/asleep sessions reject desktop return")
state.session.canPresent = true; state.acceptsSystemFeedback = false
state.playUnlockHandoff(at: first)
expect(state.neonUnlockAt == nil, "quiet/fullscreen-hidden/disabled presentation rejects return")
state.acceptsSystemFeedback = true
state.playUnlockHandoff(at: first)
RunLoop.main.run(until: Date().addingTimeInterval(signal.duration + 0.08))
expect(state.neonUnlockAt == nil && state.unlockHandoffWork == nil, "expiry removes its timeline state")

@MainActor func rendered(age: Double, leaving: Bool, fullscreen: Bool, reduced: Bool,
                         width: CGFloat = 265) -> (lit: Int, span: Int, bottom: Int) {
    let size = CGSize(width: width, height: fullscreen ? 32 : 38)
    let shape = Path(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: 11)
    let content = NotchUnlockHandoffEdge(shape: shape, size: size, age: age, leaving: leaving,
                                        fullscreen: fullscreen, reduceMotion: reduced)
        .frame(width: size.width, height: size.height)
        .overlay(alignment: .top) { Color.black.frame(width: 185, height: 32) }
        .background(.black)
    let renderer = ImageRenderer(content: content)
    renderer.scale = 2
    guard let image = renderer.cgImage else { fatalError("handoff did not render") }
    let bitmap = NSBitmapImageRep(cgImage: image)
    var lit = 0, bottom = 0, first = bitmap.pixelsWide, last = -1
    for y in 0..<bitmap.pixelsHigh {
        for x in 0..<bitmap.pixelsWide {
            guard let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB), c.blueComponent > 0.06 else { continue }
            lit += 1; first = min(first, x); last = max(last, x)
            if y >= bitmap.pixelsHigh - 8 { bottom += 1 }
        }
    }
    return (lit, max(0, last - first), bottom)
}
MainActor.assumeIsolated {
    let wide = rendered(age: 0.01, leaving: true, fullscreen: false, reduced: false)
    let narrow = rendered(age: 0.22, leaving: true, fullscreen: false, reduced: false)
    expect(wide.lit > 0 && narrow.lit > 0 && narrow.span < wide.span / 2,
           "actual lock glow visibly contracts around its centre")
    for fullscreen in [false, true] {
        for reduced in [false, true] {
            for width: CGFloat in [265, 420] {
                let returning = rendered(age: 0.62, leaving: false, fullscreen: fullscreen, reduced: reduced, width: width)
                expect(returning.lit > 0, "idle and busy return remains visible beside/below the physical camera")
                if fullscreen { expect(returning.bottom == 0, "fullscreen return does not touch the lower app edge") }
                expect(rendered(age: signal.duration, leaving: false, fullscreen: fullscreen,
                                reduced: reduced, width: width).lit == 0, "expiry leaves no residual pixel")
            }
        }
    }
}
print("Notch unlock handoff: \(checks) lifecycle/render checks passed")
'''
for marker, value in {
    "SIGNAL": declaration(view, "enum NotchUnlockHandoffSignal"),
    "EDGE": declaration(view, "struct NotchUnlockHandoffEdge"),
    "PLAY": declaration(service, "    func playUnlockHandoff("),
    "CLEAR": declaration(service, "    private func clearUnlockHandoff()").replace("private ", "", 1),
}.items():
    swift = swift.replace(marker, value)
with tempfile.TemporaryDirectory(prefix="notch-unlock-handoff-") as directory:
    main = Path(directory) / "main.swift"
    main.write_text(swift)
    subprocess.run(["xcrun", "swift", str(main)], check=True)
