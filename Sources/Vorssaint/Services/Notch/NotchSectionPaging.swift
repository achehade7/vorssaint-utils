// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// The gallery advances two rows per page, or one when only one fits.
/// The final page stays full and keyboard selection reveals its containing page.
enum NotchSectionPaging {
    static func rows(count: Int, columns: Int) -> Int {
        let columns = max(1, columns)
        return max(1, (max(0, count) + columns - 1) / columns)
    }

    /// Rows the first visible row can rest on.
    static func positions(rows: Int, visible: Int) -> [Int] {
        let last = max(0, max(1, rows) - max(1, visible))
        let step = min(2, max(1, visible))
        var positions = Array(stride(from: 0, through: last, by: step))
        if positions.last != last { positions.append(last) }
        return positions
    }

    static func clamped(_ row: Int, rows: Int, visible: Int) -> Int {
        positions(rows: rows, visible: visible).last(where: { $0 <= max(0, row) }) ?? 0
    }

    static func stepping(from first: Int, by pages: Int, rows: Int, visible: Int) -> Int {
        let positions = positions(rows: rows, visible: visible)
        let current = positions.firstIndex(of: clamped(first, rows: rows, visible: visible)) ?? 0
        return positions[min(max(0, current + pages), positions.count - 1)]
    }

    /// The first row that keeps `row` in view while moving as little as
    /// possible away from `first`.
    static func revealing(row: Int, first: Int, rows: Int, visible: Int) -> Int {
        let visible = max(1, visible)
        let first = clamped(first, rows: rows, visible: visible)
        if row < first { return clamped(row, rows: rows, visible: visible) }
        if row < first + visible { return first }
        let positions = positions(rows: rows, visible: visible)
        return positions.first(where: { row < $0 + visible }) ?? positions.last!
    }
}

/// Wheel and trackpad input becomes page steps. A flick moves one page: the
/// first step needs the same small distance as the island's own gestures,
/// later steps of one continuous drag follow the row pitch, and momentum
/// after the fingers lift is left alone. A wheel notch steps one page.
struct NotchSectionScroll {
    static let firstStep = 24.0
    static let rowStep = Double(NotchLayout.sectionTileHeight + NotchLayout.sectionSpacing)
    /// Continuous sequences without phases (wheel smoothing glides, some
    /// mice) end when their events pause.
    static let sequenceGap = 0.35
    private var distance = 0.0
    private var direction = 0
    private var stepped = false
    private var lastTimestamp: TimeInterval?

    /// Pages to move; positive reveals the rows below. `deltaY` is AppKit's
    /// scrolling delta, already flipped for natural scrolling.
    mutating func steps(deltaY: Double, timestamp: TimeInterval, precise: Bool, hasPhase: Bool,
                        began: Bool, ended: Bool, momentum: Bool) -> Int {
        guard deltaY.isFinite, timestamp.isFinite else { self = Self(); return 0 }
        if momentum { return 0 }
        if ended { self = Self(); return 0 }
        guard precise else {
            self = Self()
            return deltaY == 0 ? 0 : (deltaY < 0 ? 1 : -1)
        }
        if began || lastTimestamp.map({ timestamp < $0 || (!hasPhase && timestamp - $0 > Self.sequenceGap) }) == true {
            self = Self()
        }
        lastTimestamp = timestamp
        // Turning back starts over with the short first step, so a change
        // of mind answers as quickly as the first movement did.
        if deltaY != 0 {
            let incomingDirection = deltaY < 0 ? 1 : -1
            if direction != 0, direction != incomingDirection { distance = 0; stepped = false }
            direction = incomingDirection
        }
        distance += deltaY
        var steps = 0
        while abs(distance) >= (stepped ? Self.rowStep : Self.firstStep) {
            distance += Double(direction) * (stepped ? Self.rowStep : Self.firstStep)
            stepped = true
            steps += 1
        }
        return direction * steps
    }
}
