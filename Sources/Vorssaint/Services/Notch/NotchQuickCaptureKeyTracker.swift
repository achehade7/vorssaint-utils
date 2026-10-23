// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
/// Scope shortcuts to the editor and each selector owned by this capture.
final class NotchQuickCaptureKeyTracker {
    private var monitor: Any?

    func start(ownsWindow: @escaping (NSWindow?) -> Bool,
               handleEvent: @escaping (NSEvent) -> Bool = { _ in false }) {
        guard monitor == nil else { return }
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            guard ownsWindow(event.window) else { return event }
            return handleEvent(event) ? nil : event
        }
    }

    func stop() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
    }

    deinit { stop() }
}
