// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import CoreGraphics
import Carbon.HIToolbox

/// Production monitor bodies run against plain value doubles. No windows are
/// shown, no native monitors are installed and no keyboard input is generated.
enum NotchCaptureKeyboardContract {
    class NSPanel {
        var isVisible = true
        var attachedSheet: NSPanel?
        var firstResponder: Any?
    }
    final class NSText {}
    final class ScreenshotOverlayPanel: NSPanel {
        var overlayView = Overlay()
        let screenFrame = CGRect(x: 0, y: 0, width: 100, height: 100)
    }
    final class Overlay { var isDragging = false }
    struct NSRunningApplication { let processIdentifier: Int32 }
    final class NSWorkspace {
        static let shared = NSWorkspace()
        static let didActivateApplicationNotification = Notification.Name("fixture.applicationActivated")
        static let applicationUserInfoKey = "application"
        let notificationCenter = NotificationCenter()
    }
    enum ShortcutCapture { static var isCapturing = false }
    struct NSEvent {
        static let mouseLocation = CGPoint(x: 23, y: 61)
        struct ModifierFlags: OptionSet {
            let rawValue: Int
            static let command = Self(rawValue: 1)
            static let control = Self(rawValue: 2)
            static let option = Self(rawValue: 4)
            static let shift = Self(rawValue: 8)
            static let capsLock = Self(rawValue: 16)
            static let deviceIndependentFlagsMask = Self(rawValue: 31)
        }
        struct EventTypeMask: OptionSet {
            let rawValue: Int
            static let keyDown = Self(rawValue: 1)
            static let keyUp = Self(rawValue: 2)
            static let flagsChanged = Self(rawValue: 4)
        }
        enum EventType { case keyDown, keyUp, flagsChanged }
        let window: NSPanel?
        let keyCode: UInt16
        var modifierFlags: ModifierFlags = []
        var type: EventType = .keyDown
        var isARepeat = false
        var charactersIgnoringModifiers: String?
        var cgEvent: CGEvent?
        static var handler: ((Self) -> Self?)?
        static var monitoredTypes: EventTypeMask = []
        static func addLocalMonitorForEvents(matching: EventTypeMask, handler: @escaping (Self) -> Self?) -> Any? {
            self.handler = handler
            monitoredTypes = matching
            return 1
        }
        static func addGlobalMonitorForEvents(matching: EventTypeMask, handler: @escaping (Self) -> Void) -> Any? { nil }
    }
}

enum NotchCaptureKeyboardTests {
    private typealias Contract = NotchCaptureKeyboardContract
    private typealias Event = Contract.NSEvent

    static func run(_ suite: TestSuite) {
        defer {
            Event.handler = nil
            Contract.ShortcutCapture.isCapturing = false
            Contract.NotchService.shared = Contract.NotchService()
        }
        preview(suite)
        chooser(suite)
    }

    private static func preview(_ suite: TestSuite) {
        let notch = Contract.NotchService()
        Contract.NotchService.shared = notch
        let preview = Contract.Preview()
        notch.captureID = preview.presentationID
        let panel = notch.presentationWindow!
        preview.attach(panel)
        let commands: [(Int, Event.ModifierFlags, Contract.Preview.Action)] = [
            (kVK_ANSI_E, [], .edit), (kVK_Return, [], .edit), (kVK_Delete, [], .discard),
            (kVK_ForwardDelete, [], .discard), (kVK_ANSI_C, .command, .copy),
            (kVK_ANSI_S, .command, .save), (kVK_Delete, .command, .discard),
        ]
        func check(_ label: String, accepts: Bool) {
            for (key, flags, action) in commands {
                preview.actions = []
                let event = Event(window: panel, keyCode: UInt16(key), modifierFlags: flags)
                let forwarded = Event.handler?(event) != nil
                suite.expect(forwarded == !accepts && preview.actions == (accepts ? [action] : []), label)
            }
            let menuCount = preview.actionMenus
            let menu = Event(window: panel, keyCode: UInt16(kVK_ANSI_Grave), modifierFlags: .option,
                             charactersIgnoringModifiers: "`")
            suite.expect((Event.handler?(menu) == nil) == accepts
                         && preview.actionMenus == menuCount + (accepts ? 1 : 0),
                         "shared actions follow the same preview ownership boundary")
            let wasClosed = preview.closed
            preview.actions = []
            let close = Event(window: panel, keyCode: UInt16(kVK_ANSI_W), modifierFlags: .command,
                              charactersIgnoringModifiers: "w")
            suite.expect((Event.handler?(close) == nil) == accepts
                         && preview.closed == (wasClosed || accepts) && preview.actions.isEmpty, label)
            preview.closed = wasClosed
        }
        check("visible capture retains its existing keyboard actions", accepts: true)
        for module in NotchModule.allCases where module != .captures {
            notch.selected = module
            check("a hidden capture never edits, copies, saves or discards while another section owns the window", accepts: false)
        }
        notch.selected = .captures
        notch.showingSections = true
        check("section search keeps typing, deletion and clipboard shortcuts", accepts: false)
        notch.showingSections = false
        notch.showingAppPanel = true
        check("the app panel never inherits hidden capture commands", accepts: false)
        notch.showingAppPanel = false
        notch.expanded = false
        check("a collapsed capture cannot consume keyboard input", accepts: false)
        notch.expanded = true
        notch.captureControls = 1
        check("an active chooser cannot trigger actions on the previous capture", accepts: false)
        notch.captureControls = nil
        notch.captureID = UUID()
        check("a replaced preview cannot act on its successor", accepts: false)
        notch.captureID = preview.presentationID
        panel.firstResponder = Contract.NSText()
        check("text editing retains every preview shortcut", accepts: false)
        panel.firstResponder = nil
        panel.attachedSheet = Contract.NSPanel()
        check("a sheet owns input over its parent preview", accepts: false)
        panel.attachedSheet = nil
        Contract.ShortcutCapture.isCapturing = true
        check("shortcut recording cannot execute preview actions", accepts: false)
        Contract.ShortcutCapture.isCapturing = false
        preview.shownInNotch = false
        notch.expanded = false
        check("floating previews retain shortcuts independently of notch state", accepts: true)
        preview.actions = []
        _ = Event.handler?(Event(window: panel, keyCode: UInt16(kVK_Escape)))
        suite.expect(preview.closed && preview.actions.isEmpty, "Escape closes without dispatching a destructive action")
        check("a closed preview ignores late keyboard callbacks", accepts: false)
        preview.closed = false
        let unrelated = Contract.NSPanel()
        let unrelatedClose = Event(window: unrelated, keyCode: UInt16(kVK_ANSI_W), modifierFlags: .command,
                                   charactersIgnoringModifiers: "w")
        suite.expect(Event.handler?(unrelatedClose) != nil && !preview.closed,
                     "Command W leaves unrelated windows alone")
        for (character, key, opens) in [("`", kVK_ANSI_Grave, true), ("~", kVK_ANSI_Grave, true),
                                       ("`", kVK_ANSI_K, false), ("k", kVK_ANSI_K, false)] {
            for flags in 0..<32 {
                let before = preview.actionMenus
                let accepts = opens && flags & ~Event.ModifierFlags.capsLock.rawValue
                    == Event.ModifierFlags.option.rawValue
                let event = Event(window: panel, keyCode: UInt16(key), modifierFlags: .init(rawValue: flags),
                                  charactersIgnoringModifiers: character)
                suite.expect((Event.handler?(event) == nil) == accepts
                             && preview.actionMenus == before + (accepts ? 1 : 0),
                             "Actions uses physical backtick with exact Option and ignores additional modifiers")
            }
        }
        let repeatedActions = Event(window: panel, keyCode: UInt16(kVK_ANSI_Grave), modifierFlags: .option,
                                    isARepeat: true, charactersIgnoringModifiers: "`")
        let beforeRepeatedActions = preview.actionMenus
        suite.expect(Event.handler?(repeatedActions) != nil && preview.actionMenus == beforeRepeatedActions,
                     "holding Option-backtick does not repeatedly reopen Actions")
        let accentEvent = CGEvent(source: nil)!
        accentEvent.setIntegerValueField(.eventSourceUserData, value: Contract.SharedActionShortcut.accentEventTag)
        let accent = Event(window: panel, keyCode: UInt16(kVK_ANSI_Grave), modifierFlags: .option, cgEvent: accentEvent)
        suite.expect(Event.handler?(accent) != nil && preview.actionMenus == beforeRepeatedActions,
                     "remapped grave accent passes through preview without opening Actions")
        for (character, key, closes) in [("w", kVK_ANSI_W, true), ("W", kVK_ANSI_W, true),
                                         ("w", kVK_ANSI_Z, true), ("z", kVK_ANSI_W, false),
                                         ("é", kVK_ANSI_W, false), ("ц", kVK_ANSI_W, true),
                                         ("ц", kVK_ANSI_Z, false)] {
            for flags in 0..<32 {
                preview.closed = false
                preview.actions = []
                let accepts = closes && flags & ~Event.ModifierFlags.capsLock.rawValue
                    == Event.ModifierFlags.command.rawValue
                let event = Event(window: panel, keyCode: UInt16(key), modifierFlags: .init(rawValue: flags),
                                  charactersIgnoringModifiers: character)
                suite.expect((Event.handler?(event) == nil) == accepts
                             && preview.closed == accepts && preview.actions.isEmpty,
                             "Command W follows French and Latin letters, falls back for non-Latin input, and excludes extra modifiers")
            }
        }
    }

    private static func chooser(_ suite: TestSuite) {
        let selection = Contract.Selection()
        let notch = Contract.NotchService()
        Contract.NotchService.shared = notch
        let panel = notch.presentationWindow!
        selection.attach()
        for focused in [false, true] {
            selection.screenCaptureOptions?.hasFocusedControl = focused
            for key in [kVK_Tab, kVK_Space, kVK_LeftArrow, kVK_RightArrow, kVK_UpArrow, kVK_DownArrow] {
                for phase in [Event.EventType.keyDown, .keyUp] {
                    let event = Event(window: panel, keyCode: UInt16(key), type: phase)
                    suite.expect(Event.handler?(event) != nil, "unhandled navigation and activation keys reach native controls")
                }
            }
        }
        let enter = Event(window: panel, keyCode: UInt16(kVK_Return))
        suite.expect(Event.handler?(enter) != nil && selection.actions.isEmpty,
               "Return activates the focused control instead of taking an unexpected full-screen capture")
        selection.screenCaptureOptions?.hasFocusedControl = false
        suite.expect(Event.handler?(enter) == nil && selection.actions == ["fullDisplay"],
               "Return still captures the display when no control owns it")
        selection.actions = []
        for focused in [false, true] {
            selection.screenCaptureOptions?.hasFocusedControl = focused
            let dragging = Contract.ScreenshotOverlayPanel()
            dragging.overlayView.isDragging = true
            selection.draggingPanel = dragging
            suite.expect(Event.handler?(Event(window: panel, keyCode: UInt16(kVK_Space))) == nil && selection.spaceIsDown,
                   "Space still moves a selection even while a chooser control has focus")
            dragging.overlayView.isDragging = false
            suite.expect(Event.handler?(Event(window: panel, keyCode: UInt16(kVK_Space), type: .keyUp)) == nil && !selection.spaceIsDown,
                   "releasing Space clears movement after the drag has ended")
        }
        suite.expect(Event.handler?(Event(window: panel, keyCode: UInt16(kVK_Escape))) == nil && selection.actions == ["cancel"],
               "Escape retains chooser cancellation while controls are focused")
        selection.actions = []
        selection.screenCaptureOptions?.hasFocusedControl = false
        panel.firstResponder = Contract.NSText()
        suite.expect(Event.handler?(enter) != nil && selection.actions.isEmpty, "a chooser text editor retains Return")
        panel.firstResponder = nil
        let unrelated = Contract.NSPanel()
        suite.expect(Event.handler?(Event(window: unrelated, keyCode: UInt16(kVK_Return))) != nil,
               "capture selection leaves unrelated windows alone")
        let overlay = Contract.ScreenshotOverlayPanel()
        for destination in [panel, overlay] {
            for flags in 0..<16 {
                for (character, key, matches) in [("r", kVK_ANSI_X, true),
                                                   ("R", kVK_ANSI_X, true),
                                                   ("x", kVK_ANSI_R, true),
                                                   ("x", kVK_ANSI_X, false)] {
                    selection.actions = []
                    let accepts = matches && flags & 7 == 0
                    let event = Event(window: destination, keyCode: UInt16(key),
                                      modifierFlags: .init(rawValue: flags),
                                      charactersIgnoringModifiers: character)
                    suite.expect((Event.handler?(event) == nil) == accepts
                           && selection.actions == (accepts ? ["repeat"] : []),
                           "repeat follows the typed letter or physical key, but never command, control or option")
                }
            }
        }
        selection.actions = []
        selection.screenCaptureOptions?.controlsInNotch = false
        for key in [kVK_Return, kVK_ANSI_KeypadEnter] {
            selection.actions = []
            suite.expect(Event.handler?(Event(window: overlay, keyCode: UInt16(key))) == nil
                         && selection.actions == ["fullDisplay"],
                   "Return and keypad Enter keep full-display capture in the floating chooser")
        }
        selection.isPickingColor = true
        selection.draggingPanel = overlay
        selection.panels = [overlay]
        for key in [kVK_Return, kVK_ANSI_KeypadEnter] {
            selection.actions = []
            suite.expect(Event.handler?(Event(window: overlay, keyCode: UInt16(key))) == nil
                         && selection.actions == ["color"],
                   "Return and keypad Enter confirm the color instead of capturing the display")
        }

        let commandPreview = Contract.Selection()
        commandPreview.freezeOnCommand = true
        commandPreview.screenCaptureOptions?.controlsInNotch = false
        commandPreview.attach()
        suite.expect(Event.monitoredTypes.contains(.flagsChanged),
                     "selector subscribes to modifier transitions before mouse-down")
        for flags: Event.ModifierFlags in [.command, [.command, .shift], []] {
            let event = Event(window: overlay, keyCode: UInt16(kVK_Command), modifierFlags: flags, type: .flagsChanged)
            suite.expect(Event.handler?(event) != nil && commandPreview.commandModifiers.last == flags,
                         "owned modifier events reach freeze handling unchanged without being consumed")
        }
        let ownedChanges = commandPreview.commandModifiers
        let outside = Event(window: unrelated, keyCode: UInt16(kVK_Command), modifierFlags: .command, type: .flagsChanged)
        suite.expect(Event.handler?(outside) != nil && commandPreview.commandModifiers == ownedChanges,
                     "unrelated windows cannot change the selector's frozen preview")

        let workspace = Contract.NSWorkspace.shared.notificationCenter
        let ownPID = ProcessInfo.processInfo.processIdentifier
        workspace.post(name: Contract.NSWorkspace.didActivateApplicationNotification, object: nil,
                       userInfo: [Contract.NSWorkspace.applicationUserInfoKey:
                                    Contract.NSRunningApplication(processIdentifier: ownPID)])
        suite.expect(commandPreview.commandModifiers == ownedChanges,
                     "own application activation does not thaw a Command preview")
        workspace.post(name: Contract.NSWorkspace.didActivateApplicationNotification, object: nil,
                       userInfo: [Contract.NSWorkspace.applicationUserInfoKey:
                                    Contract.NSRunningApplication(processIdentifier: ownPID + 1)])
        suite.expect(commandPreview.commandModifiers == ownedChanges + [[]],
                     "foreign activation reconciles Command release through the latched freeze handler")
        let ordinary = Contract.Selection()
        ordinary.attach()
        suite.expect(ordinary.commandActivationObserver == nil,
                     "ordinary selectors install no Command-preview activation observer")
    }
}
