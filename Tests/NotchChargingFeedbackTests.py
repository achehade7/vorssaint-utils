#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise production power feedback without changing the Mac's power state."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()


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
    return text[start:end].replace("private func", "func", 1)


handlers = "\n".join(declaration(marker) for marker in [
    "    private func powerChanged()", "    private func stopPower()", "    private func setChargingSignal(",
    "    private func setLowBatterySignal(",
    "    private func setFullChargeSignal(",
])
charging = declaration('enum NotchChargingSignal', (repo / 'Sources/Vorssaint/UI/Notch/NotchNeonEdge.swift').read_text())
battery = declaration('enum NotchBatterySignal', (repo / 'Sources/Vorssaint/UI/Notch/NotchBatteryPulse.swift').read_text())
full_charge = declaration('enum NotchFullChargeSignal', (repo / 'Sources/Vorssaint/UI/Notch/NotchFullChargeEdge.swift').read_text())
swift = r'''
import Foundation
import CoreGraphics
CHARGING_PROFILE
BATTERY_PROFILE
FULL_CHARGE_PROFILE
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
    var running = true, suspended = false, acceptsSystemFeedback = true, displayIsFullscreen = false
    var power = PowerReading(), powerSampler: Sampler? = Sampler(), powerSource: Int? = 1
    var neonChargeAt: Date?
    var neonFullChargeAt: Date?
    var fullChargeWork: DispatchWorkItem?
    var neonLowBatteryAt: Date?
    var lowBatteryWork: DispatchWorkItem?
    var criticalPublications = 0
    func publishCriticalBattery() { criticalPublications += 1 }
    var chargingWork: DispatchWorkItem?
    var surfaceSize = CGSize(width: 285, height: 32)
    func refreshPresentation() {}
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
expect(full.neonFullChargeAt != nil && full.shown.isEmpty && full.neonChargeAt == nil,
       "real full-charge crossing starts the signature without text or plug-in animation")
expect(full.reactions.isEmpty, "full charge leaves agent marks and the companion undisturbed")
let fullDate = full.neonFullChargeAt
full.sample(percent: 100, charging: true)
full.sample(percent: 100, charging: false)
expect(full.neonFullChargeAt == fullDate && full.shown.isEmpty,
       "repeated100 or charging-status changes cannot replay completion")
let oldFull = full.fullChargeWork
full.sample(percent: 99, charging: true)
expect(full.neonFullChargeAt == nil && oldFull?.isCancelled == true,
       "leaving full charge cancels its short signature")
full.sample(percent: 100, charging: false)
let newFull = full.neonFullChargeAt
oldFull?.perform()
expect(full.neonFullChargeAt == newFull, "stale completion expiry cannot erase a newer genuine crossing")
full.fullChargeWork?.perform()
expect(full.neonFullChargeAt == nil && full.fullChargeWork == nil, "completion expiry retracts idle wings")
full.power = PowerReading(chargePercent: 99, externalConnected: true, isCharging: true)
full.sample(percent: 100, charging: false)
let stoppedFull = full.fullChargeWork
full.stopPower()
expect(full.neonFullChargeAt == nil && stoppedFull?.isCancelled == true,
       "sleep and teardown clear completion without replay")
let alreadyFull = Service()
alreadyFull.power = PowerReading(chargePercent: 100, externalConnected: true, isCharging: false)
alreadyFull.sample(percent: 100, charging: false)
expect(alreadyFull.neonFullChargeAt == nil && alreadyFull.shown.isEmpty,
       "startup or wake baseline at100 is silent")
let pluggedFull = Service()
pluggedFull.sample(percent: 100, charging: false)
expect(pluggedFull.neonFullChargeAt == nil && pluggedFull.neonChargeAt != nil,
       "plugging in already-full uses only the ordinary charging arrival")
for accepts in [true, false] {
    let suppressedFull = Service()
    suppressedFull.acceptsSystemFeedback = accepts
    NotchSupport.batteryRoute = !accepts
    suppressedFull.power = PowerReading(chargePercent: 99, externalConnected: true, isCharging: true)
    suppressedFull.sample(percent: 100, charging: false)
    expect(suppressedFull.neonFullChargeAt == nil && suppressedFull.shown.isEmpty,
           "quiet and disabled battery routes suppress full-charge signature")
    suppressedFull.acceptsSystemFeedback = true; NotchSupport.batteryRoute = true
    suppressedFull.sample(percent: 100, charging: false)
    expect(suppressedFull.neonFullChargeAt == nil, "reenabling never replays completion reached while suppressed")
}
let unpluggedFull = Service()
unpluggedFull.power = PowerReading(chargePercent: 99, externalConnected: true, isCharging: true)
unpluggedFull.sample(percent: 100, charging: false)
unpluggedFull.sample(percent: 100, plugged: false, charging: false)
expect(unpluggedFull.neonFullChargeAt == nil && unpluggedFull.fullChargeWork == nil,
       "unplug immediately cancels completion")
expect(!NotchFullChargeSignal.crossed(before: nil, next: 100, wasExternal: true, external: true)
       && !NotchFullChargeSignal.crossed(before: -1, next: 100, wasExternal: true, external: true)
       && !NotchFullChargeSignal.crossed(before: 99, next: 100, wasExternal: true, external: false),
       "unknown and invalid baselines or battery operation never announce full charge")
let low = Service()
low.power.chargePercent = 21
low.sample(percent: 20, plugged: false, charging: false)
expect(low.shown.isEmpty && low.neonChargeAt == nil && low.neonLowBatteryAt == nil,
       "twenty percent leaves the persistent orange warning to SketchyBar")
expect(low.reactions.isEmpty, "the bar warning does not interrupt agents with a mascot reaction")
let lowConnected = Service()
lowConnected.power.chargePercent = 21
lowConnected.sample(percent: 20)
expect(lowConnected.shown.isEmpty && lowConnected.neonChargeAt != nil, "plugging in at twenty percent keeps only green feedback")
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
let lifecycle = Service()
lifecycle.sample()
let stale = lifecycle.chargingWork
expect(stale != nil, "plug-in schedules a bounded lifetime for temporary charging wings")
lifecycle.sample(plugged: false, charging: false)
expect(lifecycle.chargingWork == nil && lifecycle.neonChargeAt == nil,
       "unplugging cancels the charging lifetime immediately")
lifecycle.sample()
let renewed = lifecycle.neonChargeAt
stale?.perform()
expect(lifecycle.neonChargeAt == renewed, "an old expiry must not clear a newer plug-in")
lifecycle.chargingWork?.perform()
expect(lifecycle.chargingWork == nil && lifecycle.neonChargeAt == nil,
       "the real expiry handler clears the signal so idle wings retract")
lifecycle.sample(plugged: false, charging: false)
lifecycle.sample()
lifecycle.stopPower()
expect(lifecycle.chargingWork == nil, "stopping power monitoring cancels the outstanding expiry")
let critical = Service()
critical.power.chargePercent = 11
critical.sample(percent: 10, plugged: false, charging: false)
expect(critical.neonLowBatteryAt != nil && critical.criticalPublications == 1 && critical.shown.isEmpty,
       "ten percent sends one synchronized red pulse without replacing live content")
let criticalDate = critical.neonLowBatteryAt
let staleCritical = critical.lowBatteryWork
critical.sample(percent: 9, plugged: false, charging: false)
expect(critical.neonLowBatteryAt == criticalDate && critical.criticalPublications == 1,
       "falling further below ten does not repeat the heartbeat")
critical.sample(percent: 9)
expect(critical.neonLowBatteryAt == nil && critical.lowBatteryWork == nil && critical.neonChargeAt != nil,
       "plugging in replaces the red pulse with green immediately")
critical.sample(percent: 11, plugged: false, charging: false)
critical.sample(percent: 10, plugged: false, charging: false)
let newerCritical = critical.neonLowBatteryAt
staleCritical?.perform()
expect(critical.neonLowBatteryAt == newerCritical, "an obsolete red expiry cannot erase a new threshold crossing")
critical.lowBatteryWork?.perform()
expect(critical.neonLowBatteryAt == nil && critical.lowBatteryWork == nil,
       "red heartbeat expires and removes its temporary wings")
for suppressed in [true, false] {
    let muted = Service()
    muted.power.chargePercent = 11
    muted.acceptsSystemFeedback = !suppressed
    NotchSupport.batteryRoute = suppressed
    muted.sample(percent: 10, plugged: false, charging: false)
    expect(muted.neonLowBatteryAt == nil && muted.criticalPublications == 0,
           "quiet mode and disabled battery route do not pulse either surface")
}
NotchSupport.batteryRoute = true
expect(!NotchBatterySignal.crossedCritical(before: nil, next: 9, externalConnected: false),
       "missing baseline cannot invent a threshold crossing")
expect(!NotchBatterySignal.crossedCritical(before: 11, next: nil, externalConnected: false),
       "missing next percentage is ignored")
expect(!NotchBatterySignal.crossedCritical(before: 11, next: -1, externalConnected: false),
       "invalid percentages are ignored")
expect(!NotchBatterySignal.crossedCritical(before: 11, next: 10, externalConnected: true),
       "a charging battery does not warn at ten percent")
expect(NotchBatterySignal.crossedCritical(before: 25, next: 8, externalConnected: false),
       "a reading that skips ten still warns")
for reduced in [false, true] {
    expect(NotchBatterySignal.opacity(at: -0.1, reduceMotion: reduced) == 0
           && NotchBatterySignal.opacity(at: NotchBatterySignal.duration, reduceMotion: reduced) == 0,
           "the finite pulse has no residual pixels outside its lifetime")
}
expect(NotchBatterySignal.opacity(at: 0.55, reduceMotion: false) > 0.99
       && NotchBatterySignal.opacity(at: 1.85, reduceMotion: false) > 0.99
       && NotchBatterySignal.opacity(at: 1.2, reduceMotion: false) == 0,
       "two soft peaks match the bar's 0.55 and 1.85 second beats")
expect(NotchBatterySignal.opacity(at: 0.55, reduceMotion: true)
       == NotchBatterySignal.opacity(at: 1.85, reduceMotion: true),
       "Reduce Motion holds steady red instead of beating")
critical.sample(percent: 11, plugged: false, charging: false)
critical.sample(percent: 10, plugged: false, charging: false)
critical.stopPower()
expect(critical.neonLowBatteryAt == nil && critical.lowBatteryWork == nil,
       "stopping battery feedback cancels its finite work")
for age in [-0.1, 1.6, 1.8, 3.2] {
    expect(NotchChargingSignal.opacity(at: age, fullscreen: true) == 0,
           "fullscreen bolt and streaks have no light outside their shared lifetime")
}
expect(NotchChargingSignal.opacity(at: 1.2, fullscreen: true) > 0
       && NotchChargingSignal.opacity(at: 1.5, fullscreen: true) < NotchChargingSignal.opacity(at: 1.2, fullscreen: true),
       "fullscreen feedback eases out together before its endpoint")
expect(NotchChargingSignal.opacity(at: 1.8) > 0,
       "desktop and lock-screen charging retain their longer signature")
let desktopExpiry = Service(), fullscreenExpiry = Service(), switchedExpiry = Service()
fullscreenExpiry.displayIsFullscreen = true
for service in [desktopExpiry, fullscreenExpiry, switchedExpiry] { service.sample() }
let originalDate = switchedExpiry.neonChargeAt
switchedExpiry.displayIsFullscreen = true
switchedExpiry.setChargingSignal(at: originalDate)
expect(switchedExpiry.neonChargeAt == originalDate, "entering fullscreen never restarts the effect")
RunLoop.main.run(until: Date().addingTimeInterval(1.8))
expect(fullscreenExpiry.neonChargeAt == nil && fullscreenExpiry.chargingWork == nil,
       "fullscreen temporary wings retire with the streaks, without the old extra hold")
expect(switchedExpiry.neonChargeAt == nil && switchedExpiry.chargingWork == nil,
       "entering fullscreen reschedules the original effect's shorter deadline")
expect(desktopExpiry.neonChargeAt != nil, "desktop feedback retains its full duration")
for service in [desktopExpiry, fullscreenExpiry, switchedExpiry] { service.stopPower() }
print("PASS: \(checks) charging feedback checks")
'''.replace("HANDLERS", handlers).replace("CHARGING_PROFILE", charging).replace("BATTERY_PROFILE", battery).replace("FULL_CHARGE_PROFILE", full_charge)
with tempfile.TemporaryDirectory(prefix="notch-charging-feedback-") as directory:
    path = Path(directory)
    (path / "main.swift").write_text(swift)
    subprocess.run(["swiftc", str(path / "main.swift"), "-o", str(path / "checks")], check=True)
    subprocess.run([str(path / "checks")], check=True)
