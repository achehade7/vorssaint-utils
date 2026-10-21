// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

enum NotchSectionPagingTests {
    static func run(_ suite: TestSuite) {
        suite.expect(NotchSectionPaging.rows(count: 14, columns: 4) == 4 && NotchSectionPaging.rows(count: 12, columns: 4) == 3
               && NotchSectionPaging.rows(count: 0, columns: 4) == 1 && NotchSectionPaging.rows(count: 5, columns: 0) == 5,
               "rows round the last partial row up and never vanish")
        suite.expect(NotchSectionPaging.positions(rows: 4, visible: 3) == [0, 1] && NotchSectionPaging.positions(rows: 2, visible: 3) == [0]
               && NotchSectionPaging.positions(rows: 5, visible: 1) == [0, 1, 2, 3, 4] && NotchSectionPaging.positions(rows: 4, visible: 0) == [0, 1, 2, 3],
               "page positions fill the final page and never skip rows in a one-row gallery")
        suite.expect(NotchSectionPaging.positions(rows: 4, visible: 2) == [0, 2],
                     "four rows shown two at a time have exactly two page dots")
        suite.expect(NotchSectionPaging.positions(rows: 5, visible: 2) == [0, 2, 3]
                     && NotchSectionPaging.stepping(from: 3, by: -1, rows: 5, visible: 2) == 2
                     && NotchSectionPaging.stepping(from: 2, by: 1, rows: 5, visible: 2) == 3,
                     "a partial last step returns to the preceding page without skipping it")
        suite.expect(NotchSectionPaging.stepping(from: 0, by: 1, rows: 4, visible: 2) == 2
                     && NotchSectionPaging.stepping(from: 2, by: -1, rows: 4, visible: 2) == 0,
                     "scrolling advances and returns two rows at a time")
        for rows in 1...10 {
            for visible in 1...4 {
                let positions = NotchSectionPaging.positions(rows: rows, visible: visible)
                for first in positions {
                    for row in 0..<rows {
                        let revealed = NotchSectionPaging.revealing(row: row, first: first, rows: rows, visible: visible)
                        suite.expect(positions.contains(revealed) && (revealed..<(revealed + visible)).contains(row),
                                     "keyboard selection reveals every row on a valid page")
                    }
                }
            }
        }
        suite.expect(NotchSectionPaging.clamped(5, rows: 4, visible: 3) == 1 && NotchSectionPaging.clamped(-1, rows: 4, visible: 3) == 0
               && NotchSectionPaging.clamped(1, rows: 4, visible: 3) == 1,
               "the first row never rests past the last position")
        suite.expect(NotchSectionPaging.revealing(row: 3, first: 0, rows: 4, visible: 3) == 1
               && NotchSectionPaging.revealing(row: 0, first: 1, rows: 4, visible: 3) == 0
               && NotchSectionPaging.revealing(row: 1, first: 0, rows: 4, visible: 3) == 0
               && NotchSectionPaging.revealing(row: 2, first: 1, rows: 4, visible: 3) == 1
               && NotchSectionPaging.revealing(row: 4, first: 0, rows: 5, visible: 1) == 4
               && NotchSectionPaging.revealing(row: 2, first: 9, rows: 4, visible: 3) == 1,
               "a highlighted row comes into view with the least movement, from a clamped start")

        var scroll = NotchSectionScroll()
        var time = 10.0
        func feed(_ y: Double, began: Bool = false, ended: Bool = false, momentum: Bool = false,
                  precise: Bool = true, phased: Bool = true, after gap: TimeInterval = 0.01) -> Int {
            time += gap
            return scroll.steps(deltaY: y, timestamp: time, precise: precise, hasPhase: phased,
                                began: began, ended: ended, momentum: momentum)
        }
        suite.expect(feed(0, began: true) == 0 && feed(-5) == 0 && feed(-10) == 0 && feed(-10) == 1,
               "a short downward movement accumulates into one row below, matching the island's gesture distance")
        suite.expect(feed(-50) == 0 && feed(-50) == 1,
               "further rows in the same drag follow the row pitch rather than the short first step")
        suite.expect(feed(-300) == 3, "a long continuous drag steps several rows at once")
        suite.expect(feed(0, ended: true) == 0 && feed(-400, momentum: true) == 0 && feed(-400, momentum: true) == 0,
               "momentum after lifting the fingers never moves another row")
        suite.expect(feed(-30, began: true) == 1 && feed(30) == -1,
               "turning back answers with the short first step again, revealing the row above")
        for sign in [-1, 1] {
            for (distance, rows) in [(23.0, 0), (24.0, 1), (25.0, 1), (118.0, 2)] {
                suite.expect(feed(Double(sign) * distance, began: true) == -sign * rows
                       && feed(0) == 0 && feed(Double(-sign) * 24) == sign,
                       "reversing resets the first step in either direction, even with zero distance left after \(distance) points")
            }
            suite.expect(feed(Double(sign) * 24, began: true) == -sign
                   && feed(0) == 0 && feed(Double(sign) * 24) == 0
                   && feed(Double(sign) * 70) == -sign,
                   "zero remainder and resting fingers preserve the longer pitch when continuing in the same direction")
        }
        suite.expect(feed(0, ended: true) == 0 && feed(-20, began: true) == 0 && feed(0) == 0 && feed(-3) == 0 && feed(-2) == 1,
               "resting fingers and sideways events keep the accumulated distance")
        suite.expect(feed(-1, precise: false, phased: false) == 1 && feed(3, precise: false, phased: false) == -1
               && feed(0, precise: false, phased: false) == 0,
               "each wheel notch steps one row in its direction")
        suite.expect(feed(-8, phased: false) == 0 && feed(-8, phased: false) == 0 && feed(-8, phased: false) == 1
               && feed(-8, phased: false) == 0,
               "a smoothed wheel glide steps once for its notch")
        suite.expect(feed(-8, phased: false, after: 0.5) == 0 && feed(-8, phased: false) == 0 && feed(-8, phased: false) == 1,
               "a paused glide sequence starts over, so the next notch steps its own row")
        suite.expect(feed(-100, phased: false) == 1 && feed(-100, phased: false, after: -1) == 1,
               "a clock that runs backwards starts a fresh sequence instead of stalling")
        suite.expect(feed(.nan) == 0 && feed(-24, began: true) == 1,
               "an unreadable delta resets the sequence and the next gesture begins cleanly")
        suite.expect(feed(-10, began: true) == 0 && feed(-10, began: true) == 0 && feed(-10) == 0 && feed(-5) == 1,
               "a new beginning discards the previous gesture's distance")
        routing(suite)
    }

    // The generated Service uses the production scroll handlers verbatim.
    // Events stay inside this fixture and never post input to the desktop.
    struct NSEvent {
        var locationInWindow: CGPoint
        var scrollingDeltaY: CGFloat = -24
        var scrollingDeltaX: CGFloat = 0
        var timestamp: TimeInterval = 10
        var hasPreciseScrollingDeltas = true
        var isDirectionInvertedFromDevice = true
        var phase: AppKit.NSEvent.Phase = .began
        var momentumPhase: AppKit.NSEvent.Phase = []
        var modifierFlags: AppKit.NSEvent.ModifierFlags = []
    }
    final class Panel {
        let frame = CGRect(x: 173, y: 127, width: 600, height: 260)
        func convertPoint(toScreen point: CGPoint) -> CGPoint {
            CGPoint(x: frame.minX + point.x, y: frame.minY + point.y)
        }
    }
    final class Host {
        var acceptsPoint = true
        func containsSurface(_ point: CGPoint) -> Bool { acceptsPoint }
    }
    class State {
        var running = true, suspended = false, expanded = true, showingSections = true, trackingMenu = false
        var gesturesEnabled = true, heldDrag = false
        var showingQuickCapture = false
        var gesture = NotchGestureSupport()
        var captureControls: Bool?
        var panel: Panel? = Panel()
        var windowHost: Host? = Host()
        var geometry = NotchGeometry(screen: CGRect(x: 0, y: 0, width: 1470, height: 956),
                                     safeAreaTop: 32, cameraWidth: 180)
        var expandedGeometry: NotchGeometry { geometry }
        var sectionScroll = NotchSectionScroll()
        var backGesture = NotchGestureSupport()
        var movedRows = 0, gestureCalls = 0
        var homeOpenings = 0
        func toggleSections() { showingSections.toggle(); homeOpenings += 1 }
        func swipeBack() { if !showingSections { toggleSections() } }
        func scrollSections(by rows: Int) { movedRows += rows }
        func handleGesture(_ event: NSEvent) -> Bool { gestureCalls += 1; return false }
        func handleRewindScroll(_ event: NSEvent) -> Bool { false }
    }

    private static func routing(_ suite: TestSuite) {
        for (width, cameraHeight) in [(600.0, 32.0), (400.0, 32.0), (600.0, 0.0), (600.0, 52.0)] {
            let service = Service()
            service.geometry = NotchGeometry(screen: service.geometry.screen, safeAreaTop: cameraHeight,
                                             cameraWidth: 180, layout: .custom, customWidth: width, customHeight: 260)
            let headerBottom = service.expandedGeometry.headerTopInset + service.expandedGeometry.headerRowHeight
            func event(fromTop top: CGFloat) -> NSEvent {
                NSEvent(locationInWindow: CGPoint(x: 100, y: service.panel!.frame.height - top))
            }
            suite.expect(!service.handleScroll(event(fromTop: headerBottom))
                         && service.gestureCalls == 1 && service.movedRows == 0,
                         "the actual header keeps its gesture for width \(width) and camera height \(cameraHeight)")
            for offset in [1.0, NotchLayout.spacing + 1, NotchLayout.spacing + NotchLayout.sectionTileHeight / 2] {
                let before = service.movedRows
                let gestures = service.gestureCalls
                suite.expect(service.handleScroll(event(fromTop: headerBottom + offset))
                             && service.movedRows == before + 1 && service.gestureCalls == gestures,
                             "every part of the body steps rows below the rendered header, including the top of the first tile")
            }
            var modified = event(fromTop: headerBottom + 20)
            modified.modifierFlags = .command
            let before = service.movedRows
            suite.expect(!service.handleScroll(modified) && service.movedRows == before,
                         "modified scrolling is not captured by the gallery")
            service.windowHost?.acceptsPoint = false
            suite.expect(!service.handleScroll(event(fromTop: headerBottom + 20)) && service.movedRows == before,
                         "transparent corners and floating controls are not captured by the gallery")
        }
        homeRouting(suite)
    }

    private static func homeRouting(_ suite: TestSuite) {
        func swipe(_ service: Service, x: CGFloat = 45, y: CGFloat = 0,
                   phase: AppKit.NSEvent.Phase = .began, momentum: AppKit.NSEvent.Phase = []) -> NSEvent {
            var event = NSEvent(locationInWindow: CGPoint(x: 100, y: 80))
            event.scrollingDeltaX = x
            event.scrollingDeltaY = y
            event.phase = phase
            event.momentumPhase = momentum
            return event
        }
        let service = Service()
        service.showingSections = false
        suite.expect(service.handleScroll(swipe(service)) && service.showingSections
                     && service.homeOpenings == 1 && service.gestureCalls == 0,
                     "the production route returns Home before Music or page handlers can consume the swipe")
        suite.expect(service.handleScroll(swipe(service, phase: .changed))
                     && service.handleScroll(swipe(service, x: 0, phase: .ended))
                     && service.handleScroll(swipe(service, y: -100, phase: [], momentum: .began))
                     && service.homeOpenings == 1 && service.movedRows == 0,
                     "the swipe tail and its momentum never toggle Home back or scroll the new gallery")
        suite.expect(service.handleScroll(swipe(service, x: 0, y: -24)) && service.movedRows == 1,
                     "a new vertical gesture scrolls Home normally after navigation")
        let capture = Service()
        capture.showingSections = false
        capture.showingQuickCapture = true
        for delta in [(45.0, 0.0), (-45.0, 0.0), (0.0, -45.0)] {
            suite.expect(!capture.handleScroll(swipe(capture, x: delta.0, y: delta.1))
                         && capture.homeOpenings == 0 && capture.gestureCalls == 0 && capture.expanded,
                         "quick capture keeps thumbnail/editor scrolling instead of consuming navigation gestures")
        }
        // Replay the short sequence recorded from the user's trackpad, including
        // its small vertical drift. Previously this direction never navigated.
        let sampled = Service()
        sampled.showingSections = false
        let travel: [(CGFloat, CGFloat)] = [(1, 0), (4, 2), (8, 1), (4, 1), (9, 1), (11, 0), (21, -1)]
        for (index, delta) in travel.enumerated() {
            var event = swipe(sampled, x: delta.0, y: delta.1, phase: index == 0 ? .began : .changed)
            event.timestamp += Double(index) * 0.01
            _ = sampled.handleScroll(event)
        }
        suite.expect(sampled.showingSections && sampled.homeOpenings == 1,
                     "the captured trackpad swipe now goes back exactly once")
        for blocked in ["disabled", "suspended", "closed", "capture", "drag", "menu", "outside", "modified"] {
            let service = Service()
            service.showingSections = false
            service.gesturesEnabled = blocked != "disabled"
            service.suspended = blocked == "suspended"
            service.expanded = blocked != "closed"
            service.captureControls = blocked == "capture" ? true : nil
            service.heldDrag = blocked == "drag"
            service.trackingMenu = blocked == "menu"
            service.windowHost?.acceptsPoint = blocked != "outside"
            var event = swipe(service)
            if blocked == "modified" { event.modifierFlags = .command }
            suite.expect(!service.handleBackScroll(event) && service.homeOpenings == 0,
                         "\(blocked) input cannot navigate the island")
        }
        for natural in [true, false] {
            let service = Service()
            service.showingSections = false
            var event = swipe(service, x: natural ? 45 : -45)
            event.isDirectionInvertedFromDevice = natural
            suite.expect(service.handleBackScroll(event) && service.showingSections,
                         "physical rightward movement returns Home with natural scrolling \(natural)")
        }
    }
}
