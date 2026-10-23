// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import ApplicationServices
import Carbon.HIToolbox

/// Reads one external selection on demand; neither reading nor routing uses the clipboard.
final class SharedSelectionActionsService {
    struct Source {
        let processID: pid_t
        let name: String
    }
    enum Failure { case accessibility, unavailable, secureInput }

    static let shared = SharedSelectionActionsService()
    private let owner = UUID()
    private let frontmost: () -> Source?
    private let trusted: () -> Bool
    private let secureInput: () -> Bool
    private let readSelection: (pid_t, @escaping (String?) -> Void) -> Void
    private let present: (String, String, UUID, @escaping () -> Void) -> Void
    private let dismiss: (UUID) -> Void
    private let feedback: (Failure) -> Void
    private let applicationNotifications: NotificationCenter
    private let workspaceNotifications: NotificationCenter
    private var applicationObserver: NSObjectProtocol?
    private var workspaceObserver: NSObjectProtocol?
    private var request: UUID?
    private var reading = false

    init(frontmost: @escaping () -> Source? = {
        NSWorkspace.shared.frontmostApplication.map { Source(processID: $0.processIdentifier, name: $0.localizedName ?? "") }
    }, trusted: @escaping () -> Bool = { AXIsProcessTrusted() },
         secureInput: @escaping () -> Bool = { IsSecureEventInputEnabled() },
         readSelection: @escaping (pid_t, @escaping (String?) -> Void) -> Void = { pid, completion in
             DispatchQueue.global(qos: .userInitiated).async {
                 let text = SelectedTextReader.read(processID: pid)?.text
                 DispatchQueue.main.async { completion(text) }
             }
         }, present: @escaping (String, String, UUID, @escaping () -> Void) -> Void = { text, title, owner, close in
             SharedToolActions.present(content: .text(text), title: title, from: nil, owner: owner, onClose: close)
         }, dismiss: @escaping (UUID) -> Void = { SharedToolActions.cancel(owner: $0) },
         feedback: @escaping (Failure) -> Void = { failure in
             let message: String
             switch failure {
             case .accessibility: message = SharedToolActionStrings.selectionNeedsAccessibility
             case .unavailable: message = SharedToolActionStrings.selectionUnavailable
             case .secureInput: message = SharedToolActionStrings.selectionSecureInput
             }
             QuickToolHUD.show(icon: "text.cursor", message: message)
         }, applicationNotifications: NotificationCenter = .default,
         workspaceNotifications: NotificationCenter = NSWorkspace.shared.notificationCenter) {
        self.frontmost = frontmost; self.trusted = trusted; self.secureInput = secureInput
        self.readSelection = readSelection; self.present = present; self.dismiss = dismiss; self.feedback = feedback
        self.applicationNotifications = applicationNotifications; self.workspaceNotifications = workspaceNotifications
    }

    /// Called on main by the global shortcut, after its own-window routing check.
    func trigger(expectedSourcePID: pid_t? = nil) {
        if request != nil { cancel(); return }
        let source = frontmost()
        if let expectedSourcePID, source?.processID != expectedSourcePID { return }
        guard !secureInput() else { feedback(.secureInput); return }
        guard trusted() else { feedback(.accessibility); return }
        guard let source, source.processID != ProcessInfo.processInfo.processIdentifier else {
            feedback(.unavailable); return
        }
        let id = UUID()
        request = id; reading = true
        applicationObserver = applicationNotifications.addObserver(forName: NSApplication.didResignActiveNotification,
            object: nil, queue: .main) { [weak self] _ in
                if self?.reading == true { self?.cancel() }
            }
        workspaceObserver = workspaceNotifications.addObserver(forName: NSWorkspace.didActivateApplicationNotification,
            object: nil, queue: .main) { [weak self] _ in
                guard let self, self.frontmost()?.processID != source.processID else { return }
                self.cancel()
            }
        readSelection(source.processID) { [weak self] text in
            guard let self, self.request == id else { return }
            guard self.frontmost()?.processID == source.processID else { self.cancel(); return }
            self.reading = false
            guard !self.secureInput() else { self.cancel(); self.feedback(.secureInput); return }
            guard self.trusted() else { self.cancel(); self.feedback(.accessibility); return }
            guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                self.cancel(); self.feedback(.unavailable); return
            }
            self.present(text, source.name, self.owner) { [weak self] in
                guard let self, self.request == id else { return }
                self.request = nil
                self.removeObservers()
            }
        }
    }

    /// Invalidates delayed reads and closes only this service's menu.
    func cancel() {
        request = nil; reading = false
        removeObservers()
        dismiss(owner)
    }

    private func removeObservers() {
        if let applicationObserver { applicationNotifications.removeObserver(applicationObserver) }
        if let workspaceObserver { workspaceNotifications.removeObserver(workspaceObserver) }
        applicationObserver = nil; workspaceObserver = nil
    }

    deinit { removeObservers() }
}
