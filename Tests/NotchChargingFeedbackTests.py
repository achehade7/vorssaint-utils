#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise production power feedback without changing the Mac's power state."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()


def declaration(marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end].replace("private func", "func", 1)


handlers = "\n".join(declaration(marker) for marker in [
    "    private func powerChanged()", "    private func stopPower()",
])
swift = r'''
import Foundation
struct PowerReading {
    var chargePercent: Int? = 42
    var externalConnected = false, isCharging = false
}
final class Sampler {
    var next = PowerReading()
    func sample() -> PowerReading { next }
}
enum Reaction: Equatable { case love, celebrate, yawn }
enum NotchMascotSupport {
    static func powerReaction(pluggedIn: Bool, charged: Bool, low: Bool) -> Reaction? {
        pluggedIn ? .love : charged ? .celebrate : low ? .yawn : nil
    }
}
struct NotchNotice {
    enum Event { case battery, agents }
    var event: Event
    var title: String, detail: String, symbol: String
    var mascot: Reaction?
}
enum NotchSupport {
    static var batteryRoute = true
    static func routes(_ event: NotchNotice.Event) -> Bool { event != .battery || batteryRoute }
}
struct Strings {
    let lowBattery = "low", charging = "charging", charged = "charged"
    let powerPluggedIn = "plugged", onBattery = "on-battery"
}
enum FeatureStrings { static func notch(_ language: Int) -> Strings { Strings() } }
final class L10n {
    static let shared = L10n()
    let language = 0, s = Strings()
}
enum RunLoopMode { case commonModes }
func CFRunLoopGetMain() -> Int { 0 }
func CFRunLoopRemoveSource(_ loop: Int, _ source: Int, _ mode: RunLoopMode) { }
func CFRunLoopSourceInvalidate(_ source: Int) { }
final class Service {
    var running = true, suspended = false, acceptsSystemFeedback = true
    var power = PowerReading(), powerSampler: Sampler? = Sampler(), powerSource: Int? = 1
    var neonChargeAt: Date?
    var shown: [NotchNotice] = [], reactions: [Reaction] = []
    var notice = NotchNotice(event: .agents, title: "agents", detail: "0:20 / 12:34", symbol: "agents")
    func show(_ incoming: NotchNotice) {
        guard acceptsSystemFeedback, NotchSupport.routes(incoming.event) else { return }
        shown.append(incoming); notice = incoming
    }
    func reactMascot(_ reaction: Reaction) { reactions.append(reaction) }
    func sample(percent: Int? = 42, plugged: Bool = true, charging: Bool = true) {
        powerSampler?.next = PowerReading(chargePercent: percent, externalConnected: plugged, isCharging: charging)
        powerChanged()
    }
HANDLERS
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    guard condition else { fatalError("FAIL: " + message) }
}
let connected = Service()
connected.sample()
expect(connected.neonChargeAt != nil, "plugging in starts the green signal")
expect(connected.shown.isEmpty && connected.notice.event == .agents && connected.notice.detail == "0:20 / 12:34",
       "charging preserves the displayed agent timers rather than replacing them with a notice")
expect(connected.reactions.isEmpty, "charging does not send a mascot over the agent marks")
let firstSignal = connected.neonChargeAt
connected.sample(percent: 43)
expect(connected.neonChargeAt == firstSignal && connected.shown.isEmpty,
       "battery readings while connected do not retrigger the charging animation")
connected.sample(percent: 43, plugged: false, charging: false)
expect(connected.neonChargeAt == nil, "unplugging clears the old animation event")
expect(connected.shown.last?.title == "on-battery", "unplugging keeps its existing notice")
connected.sample(percent: 43)
expect(connected.neonChargeAt != nil && connected.neonChargeAt != firstSignal,
       "reconnecting produces a new charging event")
connected.stopPower()
expect(connected.neonChargeAt == nil && connected.powerSampler == nil && connected.powerSource == nil,
       "stopping power monitoring clears the signal so it cannot replay after resume")
let full = Service()
full.power = PowerReading(chargePercent: 99, externalConnected: true, isCharging: true)
full.sample(percent: 100, charging: false)
expect(full.shown.last?.title == "charged" && full.neonChargeAt == nil,
       "reaching full charge retains its notice without pretending the cable was just plugged in")
expect(full.reactions == [.celebrate], "full charge retains its celebration")
let low = Service()
low.power.chargePercent = 21
low.sample(percent: 20, plugged: false, charging: false)
expect(low.shown.last?.title == "low" && low.neonChargeAt == nil,
       "low battery crossing retains its notice")
expect(low.reactions == [.yawn], "low battery retains its reaction")
let lowConnected = Service()
lowConnected.power.chargePercent = 21
lowConnected.sample(percent: 20)
expect(lowConnected.shown.last?.title == "low", "a simultaneous low-battery crossing remains visible")
for charging in [true, false] {
    let held = Service()
    held.sample(charging: charging)
    expect(held.neonChargeAt != nil && held.shown.isEmpty,
           "plugging in shows green even when optimized charging holds the battery")
}
NotchSupport.batteryRoute = false
let disabled = Service()
disabled.sample()
expect(disabled.neonChargeAt == nil && disabled.shown.isEmpty && disabled.reactions.isEmpty,
       "disabling battery feedback suppresses charging effects and banners")
NotchSupport.batteryRoute = true
let quiet = Service()
quiet.acceptsSystemFeedback = false
quiet.sample()
expect(quiet.neonChargeAt == nil && quiet.shown.isEmpty && quiet.reactions.isEmpty,
       "quiet/hidden feedback gates suppress the charging event")
quiet.acceptsSystemFeedback = true
quiet.sample(percent: 43)
expect(quiet.neonChargeAt == nil, "reenabling feedback does not replay a cable connected while quiet")
for suspended in [true, false] {
    let stopped = Service()
    stopped.suspended = suspended
    stopped.running = suspended
    stopped.sample()
    expect(stopped.neonChargeAt == nil && stopped.shown.isEmpty,
           "suspended or stopped services ignore power callbacks")
}
print("PASS: \(checks) charging feedback checks")
'''.replace("HANDLERS", handlers)
with tempfile.TemporaryDirectory(prefix="notch-charging-feedback-") as directory:
    path = Path(directory)
    (path / "main.swift").write_text(swift)
    subprocess.run(["swiftc", str(path / "main.swift"), "-o", str(path / "checks")], check=True)
    subprocess.run([str(path / "checks")], check=True)
