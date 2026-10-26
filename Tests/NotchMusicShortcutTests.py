#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise the music shortcut's actual native event handler without posting input."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/UI/Notch/NotchQuickAccessView.swift").read_text()


def declaration(marker, text=source):
    start = text.index(marker)
    opening = text.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
        end += 1
    return text[start:end]


swift = r'''
import AppKit
import SwiftUI
PRODUCTION
final class Window: NSWindow {
    var fixtureVisible = true
    override var isVisible: Bool { fixtureVisible }
}
final class Scroll: NSEvent {
    var target: NSWindow?
    var flags: ModifierFlags = .option
    var x: CGFloat = 0, y: CGFloat = 1
    var location = CGPoint(x: 42, y: 42)
    var precise = false, inverted = false
    var stamp: TimeInterval = 1
    var eventPhase: Phase = [], momentum: Phase = []
    override var type: EventType { .scrollWheel }
    override var window: NSWindow? { target }
    override var modifierFlags: ModifierFlags { flags }
    override var scrollingDeltaX: CGFloat { x }
    override var scrollingDeltaY: CGFloat { y }
    override var locationInWindow: NSPoint { location }
    override var hasPreciseScrollingDeltas: Bool { precise }
    override var isDirectionInvertedFromDevice: Bool { inverted }
    override var timestamp: TimeInterval { stamp }
    override var phase: Phase { eventPhase }
    override var momentumPhase: Phase { momentum }
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    precondition(condition, message)
}
let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let window = Window(contentRect: CGRect(x: 0, y: 0, width: 100, height: 100),
                    styleMask: .borderless, backing: .buffered, defer: false)
let area = NotchMusicShortcutScroll.ScrollArea(frame: CGRect(x: 20, y: 20, width: 44, height: 44))
window.contentView!.addSubview(area)
var writes: [Double] = []
area.adjusted = { writes.append($0) }
func event(_ configure: (Scroll) -> Void = { _ in }) -> Scroll {
    let value = Scroll(); value.target = window; configure(value); return value
}
func reset() { area.stop(); writes = [] }
expect(area.hitTest(CGPoint(x: 22, y: 22)) == nil, "passive scrolling does not cover the music button's click target")
expect(area.handle(event()) && writes == [1.0 / 32], "one Option-wheel step raises output by a fine step")
reset()
expect(area.handle(event { $0.y = -1 }) && writes == [-1.0 / 32], "wheel-down lowers volume")
reset()
expect(area.handle(event { $0.y = -1; $0.inverted = true }) && writes == [1.0 / 32],
       "natural scrolling preserves physical upward volume direction")
for flags: NSEvent.ModifierFlags in [[], .command, .control, .shift, [.option, .shift], [.option, .command], [.option, .control]] {
    reset()
    expect(!area.handle(event { $0.flags = flags }) && writes.isEmpty, "ordinary scrolling and other modifiers pass through")
    expect(!NotchMusicShortcutScroll.optionOnly(flags), "only Option-click toggles playback")
}
expect(NotchMusicShortcutScroll.optionOnly([.option, .capsLock]), "Caps Lock does not interfere with Option-click")
reset()
expect(!area.handle(event { $0.x = 20; $0.y = 1 }) && writes.isEmpty, "horizontal back gestures pass through")
expect(!area.handle(event { $0.location = CGPoint(x: 21, y: 21) }) && writes.isEmpty,
       "the square around the round button is not an active volume target")
expect(!area.handle(event { $0.location = CGPoint(x: 85, y: 42) }) && writes.isEmpty,
       "nearby controls are unaffected")
expect(!area.handle(event { $0.target = nil }) && writes.isEmpty, "events from other windows pass through")
window.fixtureVisible = false
expect(!area.handle(event()) && writes.isEmpty, "hidden panels cannot adjust volume")
window.fixtureVisible = true
area.isHidden = true
expect(!area.handle(event()) && writes.isEmpty, "hidden buttons cannot adjust volume")
area.isHidden = false
expect(area.handle(event { $0.momentum = .changed }) && writes.isEmpty, "inertial scrolling never changes volume")
reset()
expect(area.handle(event { $0.precise = true; $0.y = 9; $0.eventPhase = .began }) && writes.isEmpty,
       "small trackpad movement accumulates without a sudden volume jump")
expect(area.handle(event { $0.precise = true; $0.y = 11; $0.eventPhase = .changed; $0.stamp = 1.1 })
       && writes == [1.0 / 32], "continuous vertical finger travel makes one fine step")
reset()
_ = area.handle(event { $0.precise = true; $0.y = 19 })
_ = area.handle(event { $0.precise = true; $0.y = -1; $0.stamp = 1.1 })
expect(writes.isEmpty, "reversing direction discards earlier opposite travel")
_ = area.handle(event { $0.precise = true; $0.y = -19; $0.stamp = 1.2 })
expect(writes == [-1.0 / 32], "reverse travel then reduces volume normally")
reset()
_ = area.handle(event { $0.precise = true; $0.y = 19 })
_ = area.handle(event { $0.precise = true; $0.y = 1; $0.stamp = 2 })
expect(writes.isEmpty, "an old partial gesture cannot trigger the next gesture")
reset()
_ = area.handle(event { $0.precise = true; $0.y = 19 })
_ = area.handle(event { $0.precise = true; $0.y = 1; $0.eventPhase = .ended })
expect(writes.isEmpty, "lifting fingers ends the gesture without another write")
reset()
expect(!area.handle(event { $0.y = .infinity }) && writes.isEmpty, "invalid scroll deltas do not reach the mixer")
expect(!area.handle(event { $0.stamp = .nan }) && writes.isEmpty, "invalid timestamps do not reach the mixer")
reset()
_ = area.handle(event { $0.y = 50 })
expect(writes == [0.125], "one noisy wheel event cannot jump more than four fine steps")
_ = area.handle(event { $0.stamp = 1.1 })
expect(writes == [0.125, 1.0 / 32], "a noisy event cannot leave queued volume jumps behind")

// Execute the view's real adjustment route against a fake output. No hardware
// volume or playback state changes during this test.
final class AppVolumeMixer {
    OUTPUT_RESULT
    static let shared = AppVolumeMixer()
    var systemOutputVolume: Double? = 0.5
    var systemOutputMuted: Bool? = false
    var result = OutputKeyResult.applied, writes = 0
    var beforeWrite: (() -> Void)?
    func requestOutputStep(level: (Double) -> Double, completion: (OutputKeyResult) -> Void) {
        writes += 1
        beforeWrite?()
        guard let current = systemOutputVolume else { completion(.fallback); return }
        guard result == .applied else { completion(result); return }
        systemOutputVolume = level(systemOutputMuted == true ? 0 : current)
        systemOutputMuted = systemOutputVolume == 0
        completion(.applied)
    }
}
final class Motion { var interactive = true }
final class Service {
    enum Event { case volume }
    var suppression = 0
    func noteOwnLevelAdjustment(_ event: Event) { suppression += 1 }
}
final class Shortcut {
    var motion = Motion(), service = Service()
    var musicVolumeFeedback: Double?
    var musicVolumeFeedbackID: UUID?
    ADJUSTMENT
    func adjust(_ amount: Double) { adjustMusicVolume(by: amount) }
}
let shortcut = Shortcut(), mixer = AppVolumeMixer.shared
mixer.beforeWrite = { expect(shortcut.service.suppression > 0, "duplicate volume notices are suppressed before the write") }
shortcut.adjust(1.0 / 32)
expect(mixer.systemOutputVolume == 0.53125 && shortcut.musicVolumeFeedback == 0.53125 && shortcut.musicVolumeFeedbackID != nil,
       "successful volume writes expose the actual resulting level in the arc")
expect(shortcut.service.suppression == 2, "the write and completion both preserve the open island header")
shortcut.adjust(2)
expect(mixer.systemOutputVolume == 1 && shortcut.musicVolumeFeedback == 1, "upward volume remains bounded")
shortcut.adjust(-2)
expect(mixer.systemOutputVolume == 0 && shortcut.musicVolumeFeedback == 0, "downward volume remains bounded and shows muted state")
shortcut.musicVolumeFeedback = nil
shortcut.musicVolumeFeedbackID = nil
for result: AppVolumeMixer.OutputKeyResult in [.fallback, .superseded, .unconfirmed] {
    mixer.result = result
    let suppression = shortcut.service.suppression
    shortcut.adjust(0.1)
    expect(shortcut.musicVolumeFeedback == nil && shortcut.musicVolumeFeedbackID == nil
           && shortcut.service.suppression == suppression + 1,
           "only confirmed applied writes may display or renew volume feedback")
}
mixer.result = .applied; mixer.systemOutputVolume = nil
shortcut.adjust(0.1)
expect(shortcut.musicVolumeFeedback == nil, "an output without volume control shows no false arc")
shortcut.motion.interactive = false
let count = mixer.writes
shortcut.adjust(0.1)
expect(mixer.writes == count, "withdrawing buttons cannot change volume")
area.stop()
window.contentView = nil
print("NotchMusicShortcutTests: \(checks) checks passed")
'''
swift = swift.replace("PRODUCTION", declaration("struct NotchMusicShortcutScroll:"))
swift = swift.replace("ADJUSTMENT", declaration("    private func adjustMusicVolume("))
swift = swift.replace("OUTPUT_RESULT", declaration("    enum OutputKeyResult:",
    (repo / "Sources/Vorssaint/Services/Audio/AppVolumeMixer.swift").read_text()))
with tempfile.TemporaryDirectory(prefix="notch-music-shortcut-") as temp:
    path = Path(temp) / "main.swift"
    binary = Path(temp) / "tests"
    path.write_text(swift)
    subprocess.run(["xcrun", "swiftc", str(path), "-o", str(binary)], check=True, cwd=repo)
    subprocess.run([str(binary)], check=True, cwd=repo)
