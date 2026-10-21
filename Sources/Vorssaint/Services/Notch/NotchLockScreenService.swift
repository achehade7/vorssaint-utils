// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import AudioToolbox
import Combine
import IOKit.ps
import SwiftUI

/// The island over the lock screen: music on a pane of Liquid Glass between
/// the clock and the login controls, the activities as a line under the
/// clock, the padlock at the camera, and the padlock sounds. The
/// island drives it from its own session state. On locking it follows the
/// island's teardown, which stops the sources this service then restarts.
/// On unlocking the scene starts leaving before the island comes back, and
/// stops none of the sources the island takes back.
final class NotchLockScreenService {
    static let shared = NotchLockScreenService()

    private struct Frames: Equatable {
        var player: CGRect?
        var row: CGRect?
        var island: CGRect?
        /// The island itself inside its window, at the camera's fitted size.
        var islandSurface: CGRect?
    }

    private let model = NotchLockScreenModel()
    /// The player and the line of activities.
    private var scene: [NotchLockScreenPanel] = []
    private var island: NotchLockScreenPanel?
    private var space: NotchOverlaySpace?
    private var playbackSubscription: AnyCancellable?
    private var trackSubscription: AnyCancellable?
    private var accessorySubscription: AnyCancellable?
    private var microphoneSubscription: AnyCancellable?
    private var batteryPercent: Int?
    private var batteryExternal: Bool?
    private var fullChargeWork: DispatchWorkItem?
    private var lowBatteryWork: DispatchWorkItem?
    private var deviceFeedbackWork: DispatchWorkItem?
    private var displayArrivalWork: DispatchWorkItem?
    private var displayConnections = NotchDisplayConnectionTracker()
    private var powerSource: CFRunLoopSource?
    private var chargeArrival = NotchLockScreenChargeArrival()
    private var screenObserver: NSObjectProtocol?
    private var padlockWork: DispatchWorkItem?
    private var shownFrames = Frames()
    private var wasLocked = false
    private var unlockHandoffGeneration = 0

    private init() {}

    var isShowing: Bool { space != nil }

    func sync(_ session: NotchSessionState) {
        let locking = session.locked && !wasLocked
        wasLocked = session.locked
        if !session.locked { model.playedWhileLocked = false }
        if session.showsLockScreen, NotchLockScreenSupport.isEnabled(), !NotchService.shared.quietMode {
            // Locked at the Mac, the padlock is seen closing; back from a
            // dark display it is simply closed.
            show(closingPadlock: locking)
            syncFeedbackSources()
        } else {
            // Unlocked, the island owns the sources again; otherwise nothing
            // shows them until the lock screen returns.
            hide(unlocking: !session.locked && session.canPresent, stopsSources: !session.canPresent)
        }
    }

    /// The island is off: nothing it started keeps running.
    func close() {
        wasLocked = false
        model.playedWhileLocked = false
        hide(unlocking: false, stopsSources: true)
    }

    func playSound(locking: Bool) {
        guard let url = NotchLockScreenSupport.soundURL(locking: locking) else { return }
        var sound: SystemSoundID = 0
        guard AudioServicesCreateSystemSoundID(url as CFURL, &sound) == noErr else { return }
        // Asked for here, so it plays even with interface sound effects off
        // in System Settings. The alert volume and the sound effects output
        // still apply, as they do to the Mac's own sounds.
        var interface: UInt32 = 0
        AudioServicesSetProperty(kAudioServicesPropertyIsUISound, UInt32(MemoryLayout<SystemSoundID>.size), &sound,
                                 UInt32(MemoryLayout<UInt32>.size), &interface)
        AudioServicesPlaySystemSoundWithCompletion(sound) { AudioServicesDisposeSystemSoundID(sound) }
    }

    /// Where each part goes on the displays as they are now.
    private static func frames() -> Frames {
        var frames = Frames()
        // macOS draws the clock and the password field on the main display.
        let main = CGMainDisplayID()
        if let screen = (NSScreen.screens.first(where: { $0.notchDisplayID == main }) ?? NSScreen.screens.first)?.frame {
            frames.player = NotchLockScreenLayout.playerFrame(in: screen)
            frames.row = NotchLockScreenLayout.rowFrame(in: screen)
        }
        // The island's own reading of its camera, with the fit the person set.
        let geometry = NotchService.shared.geometry
        if geometry.isNotched, NSScreen.screens.contains(where: { $0.frame == geometry.screen && $0.safeAreaInsets.top > 0 }) {
            let surface = NotchLockScreenLayout.islandSurface(
                in: geometry.screen, cameraWidth: geometry.bareCutout.width, cameraHeight: geometry.bareCutout.height,
                wing: geometry.lockScreenMusicGeometry.compactActivityWingWidth)
            frames.islandSurface = surface
            frames.island = surface.map(NotchLockScreenLayout.islandFrame(around:))
        }
        return frames
    }

    private func show(closingPadlock: Bool) {
        guard space == nil,
              let space = NotchOverlaySpace(absoluteLevel: NotchLockScreenSupport.spaceLevel) else { return }
        unlockHandoffGeneration += 1
        model.unlockHandoffAt = nil
        let frames = Self.frames()
        // Settled before any view reads it, so a padlock about to close is
        // drawn open from its first frame.
        padlockWork?.cancel()
        model.padlockOpen = closingPadlock
        let gates = NotchLockScreenModel.Gates(
            music: NotchLockScreenSupport.showsMusic(), timer: NotchTimerSupport.isEnabled(),
            agents: NotchAgentSupport.showsLiveActivity(),
            downloads: NotchSupport.routes(.download), countdown: NotchCalendarSupport.showsCountdown(),
            timeLeft: NotchCalendarSupport.showsTimeLeft())
        if model.gates != gates { model.gates = gates }
        var scene: [NotchLockScreenPanel] = []
        // Without the Music section there is no player to show or to click.
        if gates.music, let frame = frames.player {
            // The one part that takes clicks: the player's buttons and timeline.
            scene.append(Self.makePanel(frame: frame, interactive: true,
                                        content: NotchLockScreenPlayer(model: model, size: frame.size)))
        }
        if let frame = frames.row {
            scene.append(Self.makePanel(frame: frame, content: NotchLockScreenActivities(model: model, size: frame.size)))
        }
        let island = frames.island.flatMap { frame in
            frames.islandSurface.map { surface in
                Self.makePanel(frame: frame, content: NotchLockScreenIsland(
                    model: model, size: surface.size, cameraWidth: NotchService.shared.geometry.bareCutout.width,
                    geometry: NotchService.shared.geometry.lockScreenMusicGeometry,
                    window: frame.size, origin: CGPoint(x: surface.minX - frame.minX, y: frame.maxY - surface.maxY)))
            }
        }
        let panels = scene + [island].compactMap { $0 }
        guard !panels.isEmpty else { space.close(); return }
        if !scene.isEmpty { startSources(gates) }
        // Joined before they are first shown, the windows belong to this
        // Space alone and are drawn over the lock screen with it.
        for panel in panels { space.add(panel) }
        self.space = space
        self.scene = scene
        self.island = island
        shownFrames = frames
        if closingPadlock {
            let work = DispatchWorkItem { [weak self] in self?.model.padlockOpen = false }
            padlockWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35, execute: work)
        }
        for panel in panels {
            panel.alphaValue = 0
            panel.orderFrontRegardless()
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.35
                panel.animator().alphaValue = 1
            }
        }
        playbackSubscription = NotchMusicService.shared.$playback
            .receive(on: DispatchQueue.main)
            .sink { [weak self] playback in
                guard let self, playback?.isPlaying == true, !self.model.playedWhileLocked else { return }
                self.model.playedWhileLocked = true
            }
        if gates.music {
            // The music service already excludes its initial snapshot,
            // pauses, seeks and metadata/cover refreshes from this event.
            trackSubscription = NotchMusicService.shared.trackChanges
                .receive(on: DispatchQueue.main)
                .sink { [weak self] in
                    guard let self, self.space != nil else { return }
                    self.model.trackShimmerID = UUID()
                }
        }
        startPower()
        syncFeedbackSources()
        displayConnections.reset(currentDisplayFrames)
        if closingPadlock { model.lockRippleID = UUID() }
        // A display attached or rearranged while locked moves the clock, the
        // login controls and the camera; the scene and the padlock follow.
        screenObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in
                guard let self, self.space != nil else { return }
                let source = NSScreen.screens.first { $0.frame == NotchService.shared.geometry.screen }?.notchDisplayID
                    ?? CGMainDisplayID()
                let direction = self.displayConnections.update(self.currentDisplayFrames, sourceID: source)
                if Self.frames() != self.shownFrames {
                    self.hide(unlocking: false, stopsSources: false)
                    self.show(closingPadlock: false)
                }
                if let direction { self.showDisplayArrival(direction) }
            }
    }

    private var currentDisplayFrames: [CGDirectDisplayID: CGRect] {
        Dictionary(NSScreen.screens.map { ($0.notchDisplayID, $0.frame) }, uniquingKeysWith: { first, _ in first })
    }

    private var acceptsFeedback: Bool {
        space != nil && island != nil && !NotchService.shared.quietMode && NotchLockScreenSupport.isEnabled()
    }

    private func syncFeedbackSources() {
        if acceptsFeedback, NotchSupport.routes(.accessory) {
            if accessorySubscription == nil {
                accessorySubscription = NotchAccessoryService.shared.lockScreenArrivals
                    .receive(on: DispatchQueue.main).sink { [weak self] arrival in self?.accessoryArrived(arrival) }
            }
            NotchAccessoryService.shared.startLockScreenMonitoring()
        } else {
            accessorySubscription = nil
            NotchAccessoryService.shared.stopLockScreenMonitoring()
        }
        if acceptsFeedback, NotchSupport.routes(.microphone) {
            if microphoneSubscription == nil {
                microphoneSubscription = MicMuteService.shared.confirmedChanges
                    .receive(on: DispatchQueue.main).sink { [weak self] muted in self?.microphoneChanged(muted) }
            }
        } else { microphoneSubscription = nil }
        if !acceptsFeedback {
            clearFeedback()
        } else {
            if !NotchSupport.routes(.battery) { clearLowBattery(); clearFullCharge() }
            if let device = model.deviceFeedback, !NotchSupport.routes(device.notice.event) {
                deviceFeedbackWork?.cancel(); deviceFeedbackWork = nil
                model.deviceFeedback = nil
            }
        }
        if !acceptsFeedback || !NotchSupport.routes(.battery) {
            model.chargingArrivalID = nil
            model.chargingPercent = nil
        }
    }

    private func accessoryArrived(_ arrival: NotchAccessoryArrival) {
        guard acceptsFeedback, NotchSupport.routes(.accessory) else { return }
        let notice = NotchNotice(event: .accessory, title: arrival.percent.map { "\($0)%" } ?? "", detail: "",
                                 symbol: arrival.symbol, audioHandoff: true)
        guard NotchDeviceFeedback(notice) == .headphones else { return }
        showDeviceFeedback(notice)
    }

    private func microphoneChanged(_ muted: Bool) {
        guard acceptsFeedback, NotchSupport.routes(.microphone) else { return }
        showDeviceFeedback(NotchNotice(event: .microphone, title: "", detail: "",
                                       symbol: muted ? "mic.slash.fill" : "mic.fill"))
    }

    private func showDeviceFeedback(_ notice: NotchNotice) {
        deviceFeedbackWork?.cancel()
        let feedback = NotchLockScreenModel.DeviceFeedback(notice: notice)
        model.deviceFeedback = feedback
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.model.deviceFeedback?.id == feedback.id else { return }
            self.model.deviceFeedback = nil
            self.deviceFeedbackWork = nil
        }
        deviceFeedbackWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + notice.event.duration, execute: work)
    }

    private func showDisplayArrival(_ direction: NotchDisplayConnectionDirection) {
        guard acceptsFeedback else { return }
        displayArrivalWork?.cancel()
        let arrival = NotchDisplayArrival(began: Date(), direction: direction)
        model.displayArrival = arrival
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.model.displayArrival == arrival else { return }
            self.model.displayArrival = nil
            self.displayArrivalWork = nil
        }
        displayArrivalWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + NotchDisplayArrivalSignal.duration, execute: work)
    }

    private func showLowBattery() {
        guard acceptsFeedback, NotchSupport.routes(.battery) else { return }
        clearLowBattery()
        let began = Date()
        model.lowBatteryAt = began
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.model.lowBatteryAt == began else { return }
            self.clearLowBattery()
        }
        lowBatteryWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + NotchBatterySignal.duration, execute: work)
    }

    private func clearLowBattery() {
        lowBatteryWork?.cancel(); lowBatteryWork = nil
        model.lowBatteryAt = nil
    }

    private func showFullCharge() {
        guard acceptsFeedback, NotchSupport.routes(.battery) else { return }
        clearFullCharge()
        model.chargingArrivalID = nil
        model.chargingPercent = nil
        let began = Date()
        model.fullChargeAt = began
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.model.fullChargeAt == began else { return }
            self.clearFullCharge()
        }
        fullChargeWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + NotchFullChargeSignal.duration, execute: work)
    }

    private func clearFullCharge() {
        fullChargeWork?.cancel(); fullChargeWork = nil
        model.fullChargeAt = nil
    }

    private func clearFeedback() {
        clearLowBattery()
        clearFullCharge()
        deviceFeedbackWork?.cancel(); deviceFeedbackWork = nil
        displayArrivalWork?.cancel(); displayArrivalWork = nil
        model.deviceFeedback = nil
        model.displayArrival = nil
    }

    private func startSources(_ gates: NotchLockScreenModel.Gates) {
        if gates.music { NotchMusicService.shared.start() }
        if gates.downloads { NotchDownloadService.shared.syncWithPreferences() }
        // An event chosen from its menu counts down with the countdown for every event off.
        if gates.countdown || gates.timeLeft || !NotchCalendarSupport.chosenCountdowns().isEmpty {
            NotchCalendarService.shared.syncWithPreferences()
        }
        if gates.agents { AgentUsageService.shared.syncWithPreferences() }
    }

    private func startPower() {
        guard PowerSampler.hasInternalBattery, powerSource == nil else { return }
        // Take a silent baseline after each appearance. Connecting while the
        // display was asleep must not play an arrival when it wakes.
        chargeArrival = NotchLockScreenChargeArrival()
        batteryPercent = nil
        batteryExternal = nil
        powerChanged()
        let callback: IOPowerSourceCallbackType = { context in
            guard let context else { return }
            Unmanaged<NotchLockScreenService>.fromOpaque(context).takeUnretainedValue().powerChanged()
        }
        if let source = IOPSNotificationCreateRunLoopSource(callback, Unmanaged.passUnretained(self).toOpaque())?.takeRetainedValue() {
            powerSource = source
            CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        }
    }

    private func powerChanged() {
        guard space != nil else { return }
        let reading = SystemInfo.batterySnapshot()
        let next = reading?.percent
        let external = reading?.isOnExternalPower == true
        if !external || next != 100 || !acceptsFeedback || !NotchSupport.routes(.battery) { clearFullCharge() }
        if NotchFullChargeSignal.crossed(before: batteryPercent, next: next,
                                         wasExternal: batteryExternal == true, external: external) {
            showFullCharge()
        }
        if reading?.isOnBattery == true,
           NotchBatterySignal.crossedCritical(before: batteryPercent, next: next,
                                              externalConnected: reading?.isOnExternalPower == true) {
            showLowBattery()
        }
        batteryPercent = next
        batteryExternal = external ? true : reading?.isOnBattery == true ? false : nil
        if reading?.isOnExternalPower == true || (next.map { $0 > NotchBatterySignal.criticalLevel } ?? false) {
            clearLowBattery()
        }
        let percent = chargeArrival.update(onBattery: reading?.isOnBattery == true,
                                           onExternalPower: reading?.isOnExternalPower == true,
                                           percent: reading?.percent)
        if let percent, acceptsFeedback, NotchSupport.routes(.battery) {
            model.chargingPercent = percent
            model.chargingArrivalID = UUID()
        } else if reading?.isOnBattery == true || !acceptsFeedback || !NotchSupport.routes(.battery) {
            model.chargingArrivalID = nil
            model.chargingPercent = nil
        }
    }

    private func hide(unlocking: Bool, stopsSources: Bool) {
        if !unlocking {
            unlockHandoffGeneration += 1
            model.unlockHandoffAt = nil
        }
        if stopsSources, !scene.isEmpty {
            NotchMusicService.shared.stop()
            NotchDownloadService.shared.stop()
            NotchCalendarService.shared.stop()
            AgentUsageService.shared.pause()
        }
        playbackSubscription = nil
        trackSubscription = nil
        accessorySubscription = nil
        microphoneSubscription = nil
        NotchAccessoryService.shared.stopLockScreenMonitoring()
        clearFeedback()
        batteryPercent = nil
        batteryExternal = nil
        displayConnections.reset([:])
        if let powerSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), powerSource, .commonModes)
            CFRunLoopSourceInvalidate(powerSource)
        }
        powerSource = nil
        chargeArrival = NotchLockScreenChargeArrival()
        model.lockRippleID = nil
        model.trackShimmerID = nil
        model.chargingArrivalID = nil
        model.chargingPercent = nil
        if let screenObserver { NotificationCenter.default.removeObserver(screenObserver) }
        screenObserver = nil
        padlockWork?.cancel()
        padlockWork = nil
        guard let space else { return }
        let scene = scene, island = island
        self.scene = []
        self.island = nil
        self.space = nil
        guard unlocking else {
            (scene + [island].compactMap { $0 }).forEach { $0.orderOut(nil) }
            space.close()
            return
        }
        // The lock screen is gone about 0.3 s after the unlock is announced;
        // the player leaves with it rather than lingering over the desktop.
        // The padlock opens first, then the island underneath takes over.
        var remaining = scene.count + (island == nil ? 0 : 1)
        let finished = { remaining -= 1; if remaining == 0 { space.close() } }
        scene.forEach { Self.fadeOut($0, after: 0, completion: finished) }
        if let island {
            model.padlockOpen = true
            unlockHandoffGeneration += 1
            let generation = unlockHandoffGeneration
            // Start both halves after the desktop's rebuild, at the same time
            // the lock view can first draw. A second lock/sleep cancels it.
            DispatchQueue.main.async { [weak self] in
                guard let self, self.unlockHandoffGeneration == generation else {
                    island.orderOut(nil)
                    finished()
                    return
                }
                if !NotchService.shared.quietMode {
                    let began = Date()
                    self.model.unlockHandoffAt = began
                    NotchService.shared.playUnlockHandoff(at: began)
                }
                Self.fadeOut(island, after: NotchUnlockHandoffSignal.contraction) { [weak self] in
                    if self?.unlockHandoffGeneration == generation { self?.model.unlockHandoffAt = nil }
                    finished()
                }
            }
        }
    }

    private static func fadeOut(_ panel: NSPanel, after delay: TimeInterval, completion: @escaping () -> Void) {
        let duration: TimeInterval = 0.2
        let fade = {
            // AppKit steps its fades on the main thread, which the island
            // coming back holds as the Mac unlocks, so the player could stay
            // over the desktop for a second. The window server fades on its own,
            // once a fade-in AppKit may still be stepping stops where it is.
            panel.alphaValue = panel.alphaValue
            if NotchWindowServerFade.fadeOut(panel, duration: duration) {
                DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
                    panel.alphaValue = 0
                    panel.orderOut(nil)
                    completion()
                }
            } else {
                NSAnimationContext.runAnimationGroup({ context in
                    context.duration = duration
                    panel.animator().alphaValue = 0
                }, completionHandler: {
                    panel.orderOut(nil)
                    completion()
                })
            }
        }
        if delay > 0 { DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: fade) } else { fade() }
    }

    private static func makePanel<Content: View>(frame: CGRect, interactive: Bool = false,
                                                 content: Content) -> NotchLockScreenPanel {
        let panel = NotchLockScreenPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel],
                                         backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.animationBehavior = .none
        panel.appearance = NSAppearance(named: .darkAqua)
        panel.level = NotchPanel.normalLevel
        panel.collectionBehavior = NotchPanel.overlayCollectionBehavior
        // Only the player's pane takes clicks, where it draws. Left unset, a
        // window lets clicks through its clear pixels, so the room around the
        // pane and a player with no song pass them to the lock screen beneath.
        // Set to false, the whole frame would take them even with nothing shown.
        if !interactive { panel.ignoresMouseEvents = true }
        let host = NotchLockScreenHostingView(rootView: AnyView(content))
        host.sizingOptions = []
        panel.contentView = host
        panel.setFrame(frame, display: false)
        return panel
    }
}

/// A fade the window server runs by itself, whatever the main thread is
/// doing. The symbols are resolved at runtime. Without them AppKit fades.
private enum NotchWindowServerFade {
    private typealias AlphaFunction = @convention(c) (UInt32, UnsafePointer<UInt32>, Int32, Float, Float) -> Int32

    private static let bridge: (connection: UInt32, setAlpha: AlphaFunction)? = {
        func symbol(_ name: String) -> UnsafeMutableRawPointer? {
            dlsym(UnsafeMutableRawPointer(bitPattern: -2) /* RTLD_DEFAULT */, name)
        }
        guard let main = symbol("CGSMainConnectionID"), let alpha = symbol("CGSSetWindowListAlpha") else { return nil }
        let connection = unsafeBitCast(main, to: (@convention(c) () -> UInt32).self)()
        guard connection != 0 else { return nil }
        return (connection, unsafeBitCast(alpha, to: AlphaFunction.self))
    }()

    /// Whether the window server took the fade.
    static func fadeOut(_ window: NSWindow, duration: TimeInterval) -> Bool {
        guard let bridge, window.windowNumber > 0 else { return false }
        var id = UInt32(window.windowNumber)
        return bridge.setAlpha(bridge.connection, &id, 1, 0, Float(duration)) == 0
    }
}

/// Never key and never main: while the Mac is locked every keystroke belongs
/// to the password field, and a click on the player must not take it away.
final class NotchLockScreenPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
    // A window that never holds key focus would otherwise draw its glass as
    // an inactive window does, flat and dull.
    @objc func _hasActiveAppearanceIgnoringKeyFocus() -> Bool { true }
    override func accessibilitySubrole() -> NSAccessibility.Subrole? { .unknown }
}

private final class NotchLockScreenHostingView: NSHostingView<AnyView> {
    // The panel is never key, so a button has to answer the first click.
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}
