// SPDX-License-Identifier: GPL-3.0-or-later
import AppKit
import SwiftUI

/// Observe scrolling inside the preview without placing a hit-test overlay
/// above its edit button and native file drag source.
struct ScreenshotConveyorScroll: NSViewRepresentable {
    let moved: (Int) -> Void

    func makeNSView(context: Context) -> ScrollArea {
        let view = ScrollArea()
        view.moved = moved
        return view
    }

    func updateNSView(_ view: ScrollArea, context: Context) { view.moved = moved }
    static func dismantleNSView(_ view: ScrollArea, coordinator: ()) { view.stop() }

    final class ScrollArea: NSView {
        var moved: ((Int) -> Void)?
        private var monitor: Any?
        private var travel: CGFloat = 0
        private var lastStep: TimeInterval = 0

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
                guard let self, let window = self.window, event.window === window,
                      self.bounds.contains(self.convert(event.locationInWindow, from: nil)) else { return event }
                guard event.momentumPhase.isEmpty else { return nil }
                if event.phase.contains(.began) { self.travel = 0 }
                let delta = abs(event.scrollingDeltaX) > abs(event.scrollingDeltaY)
                    ? event.scrollingDeltaX : event.scrollingDeltaY
                if self.travel * delta < 0 { self.travel = 0 }
                self.travel += delta
                let threshold: CGFloat = event.hasPreciseScrollingDeltas ? 28 : 1
                if abs(self.travel) >= threshold, event.timestamp - self.lastStep >= 0.25 {
                    self.lastStep = event.timestamp
                    let step = self.travel < 0 ? 1 : -1
                    self.travel = 0
                    self.moved?(step)
                }
                return nil
            }
        }

        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
            travel = 0
        }

        deinit { stop() }
    }
}
