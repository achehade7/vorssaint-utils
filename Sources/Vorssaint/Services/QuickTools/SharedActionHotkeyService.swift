// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import ApplicationServices
import Carbon.HIToolbox

/// Option–` opens Actions; Control–Option–` retains the keyboard layout's accent entry.
/// A single tap rewrites the accent event in place, avoiding synthetic keystrokes
/// or a global hotkey registration that would consume the rewritten Option–`.
final class SharedActionHotkeyService {
    static let shared = SharedActionHotkeyService()
    private var tap: CFMachPort?
    private var source: CFRunLoopSource?
    private var preferencesObserver: NSObjectProtocol?
    private var state = SharedActionKeyState()
    private var generation = UUID()

    private init() {}

    func start() {
        if preferencesObserver == nil {
            preferencesObserver = NotificationCenter.default.addObserver(
                forName: UserDefaults.didChangeNotification, object: nil, queue: .main) { [weak self] _ in
                    self?.sync()
                }
        }
        sync()
    }

    func sync() {
        guard available, AXIsProcessTrusted() else { removeTap(); return }
        guard tap == nil else { return }
        let mask = CGEventMask(1 << CGEventType.keyDown.rawValue) | CGEventMask(1 << CGEventType.keyUp.rawValue)
        guard let tap = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap,
            options: .defaultTap, eventsOfInterest: mask, callback: { _, type, event, context in
                guard let context else { return Unmanaged.passUnretained(event) }
                return Unmanaged<SharedActionHotkeyService>.fromOpaque(context).takeUnretainedValue()
                    .handle(type: type, event: event)
            }, userInfo: Unmanaged.passUnretained(self).toOpaque()) else { return }
        self.tap = tap
        source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        if let source { CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes) }
        CGEvent.tapEnable(tap: tap, enable: true)
    }

    func stop() {
        if let preferencesObserver { NotificationCenter.default.removeObserver(preferencesObserver) }
        preferencesObserver = nil
        removeTap()
    }

    private var available: Bool {
        AppFeature.clipboardHistory.isAvailable || AppFeature.textSnippets.isAvailable
    }

    private func removeTap() {
        generation = UUID()
        state.reset()
        if let source { CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .commonModes) }
        if let tap { CGEvent.tapEnable(tap: tap, enable: false); CFMachPortInvalidate(tap) }
        source = nil; tap = nil
        SharedSelectionActionsService.shared.cancel()
    }

    private func handle(type: CGEventType, event: CGEvent) -> Unmanaged<CGEvent>? {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            state.reset()
            if let tap, available { CGEvent.tapEnable(tap: tap, enable: true) }
            return Unmanaged.passUnretained(event)
        }
        guard type == .keyDown || type == .keyUp else { return Unmanaged.passUnretained(event) }
        let key = UInt16(event.getIntegerValueField(.keyboardEventKeycode))
        guard key == SharedActionShortcut.keyCode else { return Unmanaged.passUnretained(event) }
        // The tap runs on the main loop. Native nonactivating panels can be key
        // while another app remains frontmost; their local monitors own Actions.
        let local = NSApp.keyWindow?.isVisible == true && NSApp.keyWindow?.isKeyWindow == true
        let composing = local && (NSApp.keyWindow?.firstResponder as? NSTextView)?.hasMarkedText() == true
        let outcome = state.handle(keyCode: key, isDown: type == .keyDown,
            isRepeat: event.getIntegerValueField(.keyboardEventAutorepeat) != 0,
            modifiers: NSEvent.ModifierFlags(rawValue: UInt(event.flags.rawValue)), local: local,
            enabled: available && !composing && !ShortcutCapture.isCapturing && !IsSecureEventInputEnabled())
        switch outcome {
        case .pass: return Unmanaged.passUnretained(event)
        case .consume: return nil
        case .accent:
            // Tap-delivered events can ignore a direct sourceUserData field write.
            // Attach a copied source so AppKit receives the accent marker too.
            guard let source = CGEventSource(event: event) else { return Unmanaged.passUnretained(event) }
            source.userData = SharedActionShortcut.accentEventTag
            event.setSource(source)
            event.flags.remove(.maskControl)
            return Unmanaged.passUnretained(event)
        case .openActions:
            let requestGeneration = generation
            let sourcePID = NSWorkspace.shared.frontmostApplication?.processIdentifier
            DispatchQueue.main.async { [weak self] in
                guard let self, self.generation == requestGeneration, self.available,
                      let sourcePID else { return }
                SharedSelectionActionsService.shared.trigger(expectedSourcePID: sourcePID)
            }
            return nil
        }
    }
}
