#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint

"""Exercise actual lock feedback routing, teardown, and confirmed mic events."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]


def declaration(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


service = (repo / "Sources/Vorssaint/Services/Notch/NotchLockScreenService.swift").read_text()
support = (repo / "Sources/Vorssaint/Services/Notch/NotchLockScreenSupport.swift").read_text()
session_source = (repo / "Sources/Vorssaint/Services/Notch/NotchSupport.swift").read_text()
mic = (repo / "Sources/Vorssaint/Services/QuickTools/MicMuteService.swift").read_text()
battery = (repo / "Sources/Vorssaint/UI/Notch/NotchBatteryPulse.swift").read_text()
full_charge = (repo / "Sources/Vorssaint/UI/Notch/NotchFullChargeEdge.swift").read_text()
display = (repo / "Sources/Vorssaint/Services/Notch/NotchDisplayConnectionSupport.swift").read_text()
device = (repo / "Sources/Vorssaint/UI/Notch/NotchDeviceFeedback.swift").read_text()
accessory = (repo / "Sources/Vorssaint/Services/Notch/NotchAccessoryService.swift").read_text()

methods = "\n".join(declaration(service, marker).replace("private ", "", 1) for marker in [
    "    func sync(_ session:",
    "    private var acceptsFeedback:", "    private func syncFeedbackSources()",
    "    private func accessoryArrived(", "    private func microphoneChanged(",
    "    private func showDeviceFeedback(", "    private func showDisplayArrival(",
    "    private func showLowBattery(", "    private func clearLowBattery()",
    "    private func showFullCharge()", "    private func clearFullCharge()",
    "    private func scheduleMusicExpiry()", "    private func clearFeedback()", "    private func powerChanged()", "    private func hide(",
])
swift = r'''
import AppKit
import Combine
import SwiftUI
SESSION_STATE
enum NotchEvent { case accessory, microphone, battery; var duration: TimeInterval { self == .accessory ? 4 : 1.6 } }
struct NotchNotice: Equatable {
    let event: NotchEvent, title: String, detail: String, symbol: String
    var audioHandoff = false
}
DEVICE_CUE
BATTERY_SIGNAL
FULL_CHARGE_SIGNAL
DISPLAY_SUPPORT
CHARGE_ARRIVAL
MUSIC_RETENTION
struct NotchAccessoryArrival { let symbol: String; let percent: Int? }
enum NotchSupport {
    static var enabled: Set<NotchEvent> = [.accessory, .microphone, .battery]
    static func routes(_ event: NotchEvent) -> Bool { enabled.contains(event) }
}
enum NotchLockScreenSupport { static var enabled = true; static func isEnabled() -> Bool { enabled } }
final class NotchService {
    static let shared = NotchService()
    var lowBatteryWarnings = NotchBatterySignal.Tracker()
    var quietMode = false
    var shown: [Bool] = [], retractions = 0
    func showMicrophone(muted: Bool) -> Bool { shown.append(muted); return true }
    func retractMicrophoneNotice() { retractions += 1 }
    enum Reaction { case hush, perk }
    func reactMascot(_ reaction: Reaction) {}
    var handoffs: [Date] = []
    var handoffObserved: ((Date) -> Void)?
    func playUnlockHandoff(at date: Date) { handoffs.append(date); handoffObserved?(date) }
}
enum NotchUnlockHandoffSignal { static let contraction: TimeInterval = 0.3 }
final class NotchAccessoryService {
    static let shared = NotchAccessoryService()
    let lockScreenArrivals = PassthroughSubject<NotchAccessoryArrival, Never>()
    var starts = 0, stops = 0
    func startLockScreenMonitoring() { starts += 1 }
    func stopLockScreenMonitoring() { stops += 1 }
}
final class MicMuteService { static let shared = MicMuteService(); let confirmedChanges = PassthroughSubject<Bool, Never>() }
final class Source { var stops = 0; func stop() { stops += 1 }; func pause() { stops += 1 } }
enum NotchMusicService { static let shared = Source() }
enum NotchDownloadService { static let shared = Source() }
enum NotchCalendarService { static let shared = Source() }
enum AgentUsageService { static let shared = Source() }
final class Panel { var ordersOut = 0; func orderOut(_ sender: Any?) { ordersOut += 1 } }
final class Space { var closed = false; func close() { closed = true } }
final class NotchLockScreenModel {
    struct DeviceFeedback: Equatable { let id = UUID(); let notice: NotchNotice }
    var deviceFeedback: DeviceFeedback?
    var displayArrival: NotchDisplayArrival?
    var lowBatteryAt: Date?
    var lowBatteryPercent: Int?
    var fullChargeAt: Date?, unlockHandoffAt: Date?
    var chargingArrivalID: UUID?, lockRippleID: UUID?, trackShimmerID: UUID?
    var chargingPercent: Int?
    var padlockOpen = false
    var musicRetention = NotchLockScreenMusicRetention()
}
struct Reading { let percent: Int; var isOnBattery = true; var isOnExternalPower = false }
enum SystemInfo { static var reading: Reading?; static func batterySnapshot() -> Reading? { reading } }
final class LockService {
    let model = NotchLockScreenModel()
    var space: Space? = Space(), island: Panel? = Panel(), scene: [Panel] = [Panel()]
    var playbackSubscription: AnyCancellable?, trackSubscription: AnyCancellable?
    var accessorySubscription: AnyCancellable?, microphoneSubscription: AnyCancellable?
    var powerSource: CFRunLoopSource?
    var chargeArrival = NotchLockScreenChargeArrival()
    var batteryPercent: Int?
    var batteryExternal: Bool?
    var fullChargeWork: DispatchWorkItem?, musicExpiryWork: DispatchWorkItem?
    var unlockHandoffGeneration = 0
    var wasLocked = false, shows = 0
    func show(closingPadlock: Bool) {
        shows += 1
        if space == nil { space = Space(); island = Panel(); scene = [Panel()] }
    }
    var lowBatteryWork: DispatchWorkItem?, deviceFeedbackWork: DispatchWorkItem?, displayArrivalWork: DispatchWorkItem?
    var displayConnections = NotchDisplayConnectionTracker()
    var screenObserver: NSObjectProtocol?, padlockWork: DispatchWorkItem?
    static func fadeOut(_ panel: Panel, after: TimeInterval, completion: @escaping () -> Void) { completion() }
LOCK_METHODS
}
enum DefaultsKey { static let micMuteActive = "micMuteActive" }
final class MemoryDefaults { func set(_ value: Bool, forKey: String) {} }
final class L10n {
    static let shared = L10n()
    struct Strings { let micMutePartialHUD = "partial mute", micUnmutePartialHUD = "partial unmute", micMutedHUD = "muted", micUnmutedHUD = "unmuted" }
    let s = Strings()
}
enum QuickToolHUD { static var messages: [String] = []; static func show(icon: String, message: String) { messages.append(message) } }
final class MicFixture {
    struct MuteOutcome { let applied: Bool, failed: Bool }
    var applyGeneration = 1, isMuted = false, wantsMute = false, inputVolumeBlocked = false
    let inputVolumeLock = NSLock(), defaults = MemoryDefaults()
    let confirmedChanges = PassthroughSubject<Bool, Never>()
    func syncListeners() {}
MIC_FINISH
}
var checks = 0
func expect(_ condition: Bool, _ description: String) {
    checks += 1
    precondition(condition, description)
}
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.015)) }
let musicLock = LockService()
let expiredPause = Date().addingTimeInterval(-301)
musicLock.model.musicRetention.observe(isPlaying: true, at: expiredPause)
musicLock.model.musicRetention.observe(isPlaying: false, at: expiredPause)
musicLock.scheduleMusicExpiry(); drain()
expect(!musicLock.model.musicRetention.played, "expiry redraws without another playback event")
musicLock.model.musicRetention.observe(isPlaying: true, at: Date())
musicLock.model.musicRetention.observe(isPlaying: false, at: Date())
musicLock.scheduleMusicExpiry()
let musicExpiry = musicLock.musicExpiryWork
let pauseDeadline = musicLock.model.musicRetention.pauseDeadline
musicLock.hide(unlocking: false, stopsSources: true)
expect(musicExpiry?.isCancelled == true, "sleep cancels the scene expiry callback")
expect(musicLock.model.musicRetention.pauseDeadline == pauseDeadline, "sleep preserves the original pause deadline")
musicLock.space = Space(); musicLock.scene = [Panel()]
musicLock.scheduleMusicExpiry()
musicLock.model.musicRetention.observe(isPlaying: true, at: Date())
musicLock.scheduleMusicExpiry()
expect(musicLock.musicExpiryWork == nil, "resume cancels pause expiry")
musicLock.hide(unlocking: false, stopsSources: true)
expect(musicLock.model.musicRetention.pauseDeadline != nil, "sleep while playing bounds retention while the reader is stopped")
musicLock.sync(NotchSessionState())
expect(!musicLock.model.musicRetention.played, "unlock forgets music retention")
let lock = LockService()
lock.syncFeedbackSources()
expect(lock.accessorySubscription != nil && lock.microphoneSubscription != nil, "awake lock starts event subscriptions")
expect(lock.model.deviceFeedback == nil, "initial subscription is silent")
NotchAccessoryService.shared.lockScreenArrivals.send(.init(symbol: "airpodspro", percent: 64)); drain()
expect(lock.model.deviceFeedback?.notice.symbol == "airpodspro" && lock.model.deviceFeedback?.notice.title == "64%"
       && lock.model.deviceFeedback?.notice.detail == "", "lock connection shows known percentage with no device name")
lock.clearFeedback()
lock.accessoryArrived(.init(symbol: "hifispeaker", percent: 50))
expect(lock.model.deviceFeedback == nil, "speaker does not become a headphone arrival")
lock.accessoryArrived(.init(symbol: "headphones", percent: nil))
expect(lock.model.deviceFeedback?.notice.title == "", "missing telemetry stays absent")
let oldWork = lock.deviceFeedbackWork
lock.microphoneChanged(true)
let newest = lock.model.deviceFeedback
oldWork?.perform()
expect(lock.model.deviceFeedback == newest, "old accessory expiry cannot erase new mic feedback")
expect(newest?.notice.symbol == "mic.slash.fill" && newest?.notice.title == "" && newest?.notice.detail == "", "lock mic cue contains no text")
lock.clearFeedback()
NotchSupport.enabled.remove(.microphone)
lock.microphoneChanged(false)
expect(lock.model.deviceFeedback == nil, "disabled mic route rejects events")
NotchSupport.enabled.insert(.microphone)
SystemInfo.reading = Reading(percent: 9); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil, "first low reading after lock or wake is silent")
SystemInfo.reading = Reading(percent: 11); lock.powerChanged()
SystemInfo.reading = Reading(percent: 10, isOnBattery: false); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil, "unknown power source cannot announce a discharge crossing")
SystemInfo.reading = Reading(percent: 11); lock.powerChanged()
SystemInfo.reading = Reading(percent: 10); lock.powerChanged()
let critical = lock.model.lowBatteryAt
expect(lock.model.lowBatteryPercent == 10, "lock cue carries the real percentage")
expect(critical != nil, "real 11 to 10 crossing starts lock heartbeat")
lock.powerChanged()
expect(lock.model.lowBatteryAt == critical, "repeated low reading does not restart heartbeat")
for level in [5, 1] {
    SystemInfo.reading = Reading(percent: level); lock.powerChanged()
    expect(lock.model.lowBatteryAt != nil && lock.model.lowBatteryPercent == level,
           "lock screen announces five and one percent")
    let began = lock.model.lowBatteryAt
    SystemInfo.reading = Reading(percent: level + 1); lock.powerChanged()
    SystemInfo.reading = Reading(percent: level); lock.powerChanged()
    expect(lock.model.lowBatteryAt == began, "lock warning is once per level despite jitter")
}
SystemInfo.reading = Reading(percent: 11); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil, "known battery recovery clears heartbeat")
SystemInfo.reading = Reading(percent: 10); lock.powerChanged()
SystemInfo.reading = Reading(percent: 10, isOnBattery: false, isOnExternalPower: true); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil && lock.model.chargingArrivalID != nil, "plug clears low heartbeat and keeps charging cue")
lock.showDisplayArrival(.init(x: 1, y: 0)); lock.microphoneChanged(true)
// Charging on the lock screen must rearm the desktop's very same tracker.
expect(NotchService.shared.lowBatteryWarnings.update(before: 11, next: 10, externalConnected: false),
       "charging while locked rearms the desktop warning cycle")
SystemInfo.reading = Reading(percent: 11); lock.powerChanged()
SystemInfo.reading = Reading(percent: 10); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil, "a desktop warning cannot replay after switching to the lock-screen reader")
NotchService.shared.quietMode = true; lock.syncFeedbackSources()
expect(lock.model.displayArrival == nil && lock.model.deviceFeedback == nil && lock.model.chargingArrivalID == nil,
       "quiet clears all current transient cues")
expect(lock.accessorySubscription == nil && lock.microphoneSubscription == nil, "quiet stops connection and mic observers")
lock.showDisplayArrival(.init(x: -1, y: 0)); lock.showLowBattery(); lock.microphoneChanged(true)
expect(lock.model.displayArrival == nil && lock.model.lowBatteryAt == nil && lock.model.deviceFeedback == nil,
       "quiet rejects every new lock cue")
NotchService.shared.quietMode = false; lock.syncFeedbackSources()
lock.microphoneChanged(false); lock.showLowBattery(); lock.showDisplayArrival(.init(x: 0, y: 1))
let deviceExpiry = lock.deviceFeedbackWork, batteryExpiry = lock.lowBatteryWork, displayExpiry = lock.displayArrivalWork
let closedSpace = lock.space
lock.hide(unlocking: false, stopsSources: true)
expect(deviceExpiry?.isCancelled == true && batteryExpiry?.isCancelled == true && displayExpiry?.isCancelled == true,
       "sleep cancels every transient expiry")
expect(lock.space == nil && closedSpace?.closed == true && lock.model.deviceFeedback == nil
       && lock.model.lowBatteryAt == nil && lock.model.displayArrival == nil && lock.batteryPercent == nil,
       "sleep removes panels and clears baselines and cue state")
expect(lock.accessorySubscription == nil && lock.microphoneSubscription == nil, "sleep removes subscriptions")
NotchAccessoryService.shared.lockScreenArrivals.send(.init(symbol: "airpodspro", percent: 50))
MicMuteService.shared.confirmedChanges.send(true); drain()
expect(lock.model.deviceFeedback == nil, "sleep cannot receive or replay device cues")
lock.space = Space(); lock.island = Panel(); lock.syncFeedbackSources()
SystemInfo.reading = Reading(percent: 8); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil && lock.model.deviceFeedback == nil, "wake silently baselines low battery and existing devices")
NotchSupport.enabled.remove(.battery)
SystemInfo.reading = Reading(percent: 11); lock.powerChanged()
SystemInfo.reading = Reading(percent: 10); lock.powerChanged()
expect(lock.model.lowBatteryAt == nil, "disabled battery route rejects crossing")
lock.hide(unlocking: false, stopsSources: true)
NotchSupport.enabled.insert(.battery)
let fullLock = LockService()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
expect(fullLock.model.fullChargeAt == nil, "initial locked100 baseline is silent")
SystemInfo.reading = Reading(percent: 99, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
let fullAt = fullLock.model.fullChargeAt, oldFullWork = fullLock.fullChargeWork
expect(fullAt != nil && fullLock.model.chargingArrivalID == nil && fullLock.model.chargingPercent == nil,
       "real lock full-charge crossing starts text-free signature")
fullLock.powerChanged()
expect(fullLock.model.fullChargeAt == fullAt, "repeated100 does not replay lock completion")
SystemInfo.reading = Reading(percent: 99, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
let newFullAt = fullLock.model.fullChargeAt
oldFullWork?.perform()
expect(fullLock.model.fullChargeAt == newFullAt && oldFullWork?.isCancelled == true,
       "stale full-charge expiry cannot remove newer crossing")
fullLock.fullChargeWork?.perform()
expect(fullLock.model.fullChargeAt == nil && fullLock.fullChargeWork == nil, "lock completion fully expires")
SystemInfo.reading = Reading(percent: 99, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100); fullLock.powerChanged()
expect(fullLock.model.fullChargeAt == nil, "unplug clears lock completion")
SystemInfo.reading = Reading(percent: 99, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
NotchService.shared.quietMode = true; fullLock.syncFeedbackSources()
expect(fullLock.model.fullChargeAt == nil && fullLock.fullChargeWork == nil, "quiet immediately cancels lock completion")
NotchService.shared.quietMode = false; fullLock.powerChanged()
expect(fullLock.model.fullChargeAt == nil, "leaving quiet does not replay completion")
SystemInfo.reading = Reading(percent: 99, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
let sleepFullWork = fullLock.fullChargeWork
fullLock.hide(unlocking: false, stopsSources: true)
expect(fullLock.model.fullChargeAt == nil && sleepFullWork?.isCancelled == true && fullLock.batteryExternal == nil,
       "sleep cancels completion and resets power baseline")
fullLock.space = Space(); fullLock.island = Panel(); fullLock.powerChanged()
expect(fullLock.model.fullChargeAt == nil, "wake at100 remains silent")
NotchSupport.enabled.remove(.battery)
SystemInfo.reading = Reading(percent: 99, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
SystemInfo.reading = Reading(percent: 100, isOnBattery: false, isOnExternalPower: true); fullLock.powerChanged()
expect(fullLock.model.fullChargeAt == nil, "disabled battery route suppresses lock completion")
NotchSupport.enabled.insert(.battery)
fullLock.hide(unlocking: false, stopsSources: true)
let unlock = LockService()
let unlockedSpace = unlock.space
NotchService.shared.handoffObserved = { date in
    expect(unlock.model.unlockHandoffAt == date, "both handoff halves begin with exactly the same timestamp")
}
unlock.hide(unlocking: true, stopsSources: false)
unlock.hide(unlocking: true, stopsSources: false)
expect(unlock.model.unlockHandoffAt == nil && NotchService.shared.handoffs.isEmpty,
       "unlock waits until desktop reconstruction leaves the main thread")
drain()
expect(unlock.model.unlockHandoffAt == nil
       && NotchService.shared.handoffs.count == 1 && unlockedSpace?.closed == true,
       "handoff runs once, departing panels close and their animation state is cleared")
NotchService.shared.handoffObserved = nil
let canceledUnlock = LockService()
let canceledSpace = canceledUnlock.space
canceledUnlock.hide(unlocking: true, stopsSources: false)
canceledUnlock.hide(unlocking: false, stopsSources: true)
drain()
expect(canceledUnlock.model.unlockHandoffAt == nil && NotchService.shared.handoffs.count == 1
       && canceledSpace?.closed == true, "sleep/relock before queued handoff cancels it and closes old panels")
let quietUnlock = LockService()
NotchService.shared.quietMode = true
quietUnlock.hide(unlocking: true, stopsSources: false); drain()
expect(quietUnlock.model.unlockHandoffAt == nil && NotchService.shared.handoffs.count == 1,
       "quiet unlock never produces either half")
NotchService.shared.quietMode = false
let quietScene = LockService()
let quietSceneSpace = quietScene.space
NotchService.shared.quietMode = true
quietScene.sync(NotchSessionState(locked: true))
expect(quietScene.shows == 0 && quietScene.space == nil && quietSceneSpace?.closed == true,
       "quiet mode hides custom lock panels instead of only suppressing their feedback")
expect(quietScene.accessorySubscription == nil && quietScene.microphoneSubscription == nil,
       "quiet lock leaves no feedback subscriptions running")
NotchService.shared.quietMode = false
quietScene.sync(NotchSessionState(locked: true))
expect(quietScene.shows == 1 && quietScene.space != nil && quietScene.model.deviceFeedback == nil,
       "restoring quiet while locked restores the scene with no stale feedback")
quietScene.sync(NotchSessionState(locked: true, displaysSleeping: true))
expect(quietScene.space == nil, "quiet restoration never prevents display-sleep teardown")
let mic = MicFixture()
var confirmed: [Bool] = []
let subscription = mic.confirmedChanges.sink { confirmed.append($0) }
expect(confirmed.isEmpty, "mic event stream never emits its initial state")
mic.finish(.init(applied: true, failed: false), muted: true, announce: false, generation: 1)
expect(confirmed.isEmpty, "silent device reapplication has no success event")
mic.finish(.init(applied: true, failed: true), muted: true, announce: true, generation: 1)
expect(confirmed.isEmpty && QuickToolHUD.messages == ["partial mute"], "partial failure preserves warning and never claims successful global mute")
mic.finish(.init(applied: false, failed: true), muted: true, announce: true, generation: 1)
mic.finish(.init(applied: true, failed: false), muted: true, announce: true, generation: 0)
expect(confirmed.isEmpty, "failed and stale hardware sweeps do not emit")
mic.finish(.init(applied: true, failed: false), muted: false, announce: true, generation: 1)
mic.finish(.init(applied: true, failed: false), muted: true, announce: true, generation: 1)
expect(confirmed == [false, true], "only complete confirmed requests emit unmute and mute")
print("PASS: \(checks) lock feedback lifecycle checks")
'''
swift = swift.replace("DEVICE_CUE", declaration(device, "enum NotchDeviceFeedback:"))
swift = swift.replace("SESSION_STATE", declaration(session_source, "struct NotchSessionState"))
swift = swift.replace("BATTERY_SIGNAL", declaration(battery, "enum NotchBatterySignal"))
swift = swift.replace("FULL_CHARGE_SIGNAL", declaration(full_charge, "enum NotchFullChargeSignal"))
swift = swift.replace("DISPLAY_SUPPORT", display)
swift = swift.replace("CHARGE_ARRIVAL", declaration(support, "struct NotchLockScreenChargeArrival"))
swift = swift.replace("MUSIC_RETENTION", declaration(support, "struct NotchLockScreenMusicRetention"))
swift = swift.replace("LOCK_METHODS", methods)
swift = swift.replace("MIC_FINISH", declaration(mic, "    private func finish(").replace("private ", "", 1)
                      .replace("UserDefaults.standard", "defaults"))
with tempfile.TemporaryDirectory(prefix="notch-lock-feedback-") as directory:
    source = Path(directory) / "main.swift"
    source.write_text(swift)
    binary = Path(directory) / "check"
    subprocess.run(["xcrun", "swiftc", "-sdk", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk",
                    str(source), "-o", str(binary)], check=True, cwd=repo)
    subprocess.run([str(binary)], check=True)

# Exercise the production service and connection monitor together. Controlled
# worker/UI queues model events arriving across lock/desktop/sleep boundaries,
# without calling IOBluetooth or starting a real battery sampler.
accessory_methods = "\n".join(declaration(accessory, marker).replace("private ", "", 1) for marker in [
    "    func syncWithPreferences()", "    func stop()",
    "    func startLockScreenMonitoring()", "    func stopLockScreenMonitoring()", "    func suspend()",
    "    private func handleConnection(",
])
accessory_swift = r'''
import AppKit
import Combine
enum DefaultsKey { static let notchAccessoriesEnabled = "notchAccessoriesEnabled" }
enum NotchSupport { static func isEnabled(in defaults: UserDefaults) -> Bool { true } }
enum AppFeature { case notchAccessories, monitorPower; func isAvailable(in defaults: UserDefaults) -> Bool { true } }
enum NotchEvent { case accessory }
struct NotchNotice {
    let event: NotchEvent, title: String, detail: String, symbol: String
    var level: Double? = nil, audioHandoff = false
}
final class Tasks {
    var pending: [() -> Void] = []
    func enqueue(_ work: @escaping () -> Void) { pending.append(work) }
    func drain() { while !pending.isEmpty { pending.removeFirst()() } }
}
final class ConnectionSource: NotchAccessoryConnectionSource {
    var callback: ((NotchAccessoryConnectionEvent) -> Void)?, stops = 0
    func start(isCancelled: @escaping () -> Bool, onEvent: @escaping (NotchAccessoryConnectionEvent) -> Void) {
        callback = onEvent
    }
    func stop() { stops += 1 } // Retain the callback to model late native delivery.
}
final class SystemMonitor {
    static let shared = SystemMonitor()
    struct Snapshot { var peripheralBatterySample = PeripheralBatterySample() }
    @Published var snapshot = Snapshot()
    var samplerChanges: [Bool] = []
    func setNotchAccessoryMonitoring(_ enabled: Bool) { samplerChanges.append(enabled) }
}
final class L10n { static let shared = L10n(); let language = "en" }
enum FeatureStrings {
    struct Text { let connected = "Connected", lowBattery = "Low battery" }
    static func notchActivities(_ language: String) -> Text { Text() }
}
final class Accessory: NSObject {
    var active = false, lockOnly = false
    var activationTime: TimeInterval = 0, generation = UUID()
    var subscription: AnyCancellable?
    let connectionMonitor: NotchAccessoryConnectionMonitor
    var batteryState = NotchAccessoryBatteryState()
    var pending: [(notice: NotchNotice, device: String, expiresAt: Date)] = []
    var noticeWork: DispatchWorkItem?
    let lockScreenArrivals = PassthroughSubject<NotchAccessoryArrival, Never>()
    var desktopNotices: [NotchNotice] = []
    init(monitor: NotchAccessoryConnectionMonitor) { connectionMonitor = monitor; super.init() }
    func enqueue(_ notice: NotchNotice, device: String) { desktopNotices.append(notice) }
ACCESSORY_METHODS
}
var checks = 0
func expect(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.015)) }
let defaults = UserDefaults.standard
defaults.set(true, forKey: DefaultsKey.notchAccessoriesEnabled)
let worker = Tasks(), ui = Tasks()
var sources: [ConnectionSource] = []
let monitor = NotchAccessoryConnectionMonitor(perform: worker.enqueue, deliver: ui.enqueue,
    makeSource: { _ in let source = ConnectionSource(); sources.append(source); return source })
let accessory = Accessory(monitor: monitor)
let headset = NotchAccessoryConnectionEvent.connected(name: "AirPods Pro", majorClass: 4, minorClass: 1)
let keyboard = NotchAccessoryConnectionEvent.connected(name: "Keyboard", majorClass: 5, minorClass: 16)
let reading = PeripheralBatteryDevice(id: "headset", name: "AirPods Pro", percent: 64, kind: .audio)
func sample(_ observedAt: TimeInterval) {
    SystemMonitor.shared.snapshot.peripheralBatterySample = PeripheralBatterySample(
        devices: [reading], observedAt: [reading.id: observedAt])
}
var arrivals: [NotchAccessoryArrival] = []
let subscription = accessory.lockScreenArrivals.sink { arrivals.append($0) }
accessory.startLockScreenMonitoring(); worker.drain()
accessory.startLockScreenMonitoring(); worker.drain()
expect(sources.count == 1 && arrivals.isEmpty, "lock monitoring starts once without synthesizing a connection")
expect(SystemMonitor.shared.samplerChanges.isEmpty && accessory.subscription == nil, "lock monitoring starts no battery sampler")
let first = sources[0]
first.callback?(headset)
accessory.stopLockScreenMonitoring()
accessory.startLockScreenMonitoring(); worker.drain(); ui.drain()
expect(arrivals.isEmpty && first.stops == 1, "queued old-mode connection cannot become a new lock arrival")
let locked = sources.last!
sample(ProcessInfo.processInfo.systemUptime - 10)
locked.callback?(headset); ui.drain()
expect(arrivals.count == 1 && arrivals[0].symbol == "airpodspro" && arrivals[0].percent == 64,
       "lock arrival retains only its icon and recent pre-lock battery reading")
expect(accessory.desktopNotices.isEmpty, "lock connection never publishes a desktop notice")
sample(ProcessInfo.processInfo.systemUptime - 301)
locked.callback?(headset); ui.drain()
expect(arrivals.count == 2 && arrivals.last?.percent == nil, "lock connection suppresses stale battery percentages")
locked.callback?(headset)
defaults.set(false, forKey: DefaultsKey.notchAccessoriesEnabled); ui.drain()
expect(arrivals.count == 2, "disabled preference rejects an already queued connection")
defaults.set(true, forKey: DefaultsKey.notchAccessoriesEnabled)
locked.callback?(headset)
accessory.syncWithPreferences(); worker.drain(); ui.drain(); drain()
expect(!accessory.lockOnly && accessory.active && accessory.subscription != nil,
       "unlock transfers monitoring to desktop ownership")
expect(arrivals.count == 2 && accessory.desktopNotices.isEmpty && locked.stops == 1,
       "queued lock events cannot turn into desktop notices after unlocking")
expect(SystemMonitor.shared.samplerChanges == [true], "unlock starts the desktop sampler exactly once")
let desktop = sources.last!
accessory.stopLockScreenMonitoring(); worker.drain()
expect(accessory.active && desktop.stops == 0, "late lock teardown cannot stop desktop monitoring")
sample(accessory.activationTime - 1)
desktop.callback?(headset); ui.drain(); drain()
expect(accessory.desktopNotices.last?.title == "Connected" && accessory.desktopNotices.last?.audioHandoff == true,
       "desktop connection keeps audio handoff while rejecting pre-activation battery data")
sample(ProcessInfo.processInfo.systemUptime)
desktop.callback?(headset); ui.drain(); drain()
expect(accessory.desktopNotices.last?.title == "Connected · 64%"
       && accessory.desktopNotices.last?.detail == "AirPods Pro" && accessory.desktopNotices.last?.symbol == "airpodspro",
       "desktop connection preserves current battery, name and device icon")
desktop.callback?(keyboard); ui.drain()
expect(accessory.desktopNotices.last?.audioHandoff == false, "non-audio devices do not trigger audio handoff")
let notice = accessory.desktopNotices.last!
accessory.pending = [(notice, "Keyboard", Date().addingTimeInterval(30)),
                     (notice, "AirPods Pro", Date().addingTimeInterval(30))]
locked.callback?(.disconnected(name: "Keyboard")); ui.drain()
expect(accessory.pending.count == 2, "old-mode disconnect cannot remove a current queued notice")
desktop.callback?(.disconnected(name: "Keyboard")); ui.drain()
expect(accessory.pending.map(\.device) == ["AirPods Pro"], "current disconnect removes only its device's queued notice")
let noticeCount = accessory.desktopNotices.count
desktop.callback?(headset)
accessory.suspend(); worker.drain(); ui.drain()
expect(accessory.desktopNotices.count == noticeCount && desktop.stops == 1 && accessory.pending.isEmpty,
       "sleep cleans up the monitor and rejects queued presentation")
expect(SystemMonitor.shared.samplerChanges == [true, false], "desktop suspension releases its sampler ownership")
accessory.startLockScreenMonitoring(); worker.drain()
expect(arrivals.count == 2, "wake starts observation without replaying previous events")
accessory.stopLockScreenMonitoring(); worker.drain()
expect(SystemMonitor.shared.samplerChanges == [true, false], "lock stop leaves desktop sampler ownership unchanged")
print("PASS: \(checks) accessory lock-monitor lifecycle checks")
'''.replace("ACCESSORY_METHODS", accessory_methods)
with tempfile.TemporaryDirectory(prefix="notch-lock-accessory-") as directory:
    source = Path(directory) / "main.swift"
    source.write_text(accessory_swift)
    binary = Path(directory) / "check"
    subprocess.run(["xcrun", "swiftc", "-sdk", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk",
                    str(source), "Sources/Vorssaint/Services/Notch/NotchAccessorySupport.swift",
                    "Sources/Vorssaint/Services/Notch/NotchAccessoryConnectionMonitor.swift",
                    "Sources/Vorssaint/Services/Metrics/PeripheralBatterySupport.swift", "-o", str(binary)],
                   check=True, cwd=repo)
    # The fixture enables one fake route in an isolated preferences home.
    import os
    env = dict(os.environ, CFFIXED_USER_HOME=directory)
    subprocess.run([str(binary)], check=True, env=env)
