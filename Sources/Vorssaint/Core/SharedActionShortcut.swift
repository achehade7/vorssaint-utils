// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

enum SharedActionShortcut {
    static let displayString = "⌥`"
    static let keyCode: UInt16 = 50
    static let accentEventTag: Int64 = 0x5653_4143_4345_4E54

    static func matches(_ event: NSEvent) -> Bool {
        event.cgEvent?.getIntegerValueField(.eventSourceUserData) != accentEventTag
            && matches(keyCode: event.keyCode, modifiers: event.modifierFlags)
    }

    static func matches(keyCode: UInt16, modifiers: NSEvent.ModifierFlags) -> Bool {
        keyCode == self.keyCode && modifiers.intersection([.command, .control, .option, .shift]) == .option
    }
}

/// Own the entire physical press, including repeats and release after modifiers change.
struct SharedActionKeyState {
    enum Outcome: Equatable { case pass, consume, openActions, accent }
    private enum Press { case actions, accent }
    private var press: Press?

    mutating func handle(keyCode: UInt16, isDown: Bool, isRepeat: Bool,
                         modifiers: NSEvent.ModifierFlags, local: Bool, enabled: Bool) -> Outcome {
        guard keyCode == SharedActionShortcut.keyCode else { return .pass }
        if !isDown {
            let previous = press; press = nil
            switch previous {
            case .actions: return .consume
            case .accent: return .accent
            case nil: return .pass
            }
        }
        if isRepeat {
            switch press {
            case .actions: return .consume
            case .accent: return .accent
            case nil: return .pass
            }
        }
        press = nil
        guard enabled else { return .pass }
        let flags = modifiers.intersection([.command, .control, .option, .shift])
        if flags == [.control, .option] { press = .accent; return .accent }
        guard SharedActionShortcut.matches(keyCode: keyCode, modifiers: modifiers) else { return .pass }
        press = .actions
        return local ? .pass : .openActions
    }

    mutating func reset() { press = nil }
}
