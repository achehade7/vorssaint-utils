// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import CoreGraphics
import Foundation

/// A unit vector in NSScreen coordinates, where positive Y points upward.
struct NotchDisplayConnectionDirection: Equatable {
    let x: CGFloat
    let y: CGFloat
}

struct NotchDisplayArrival: Equatable {
    let began: Date
    let direction: NotchDisplayConnectionDirection
}

/// Screen-parameter notifications also report brightness and rearrangements.
/// Only a new identifier beside the island's surviving display is an arrival.
struct NotchDisplayConnectionTracker {
    private var identifiers: Set<CGDirectDisplayID>?

    mutating func reset(_ displays: [CGDirectDisplayID: CGRect]) {
        identifiers = Set(displays.keys)
    }

    mutating func update(_ displays: [CGDirectDisplayID: CGRect],
                         sourceID: CGDirectDisplayID?) -> NotchDisplayConnectionDirection? {
        let current = Set(displays.keys)
        defer { identifiers = current }
        guard let identifiers, let sourceID, identifiers.contains(sourceID),
              let source = displays[sourceID], Self.isUsable(source) else { return nil }
        let arrivals = current.subtracting(identifiers).compactMap { id -> (id: CGDirectDisplayID, x: CGFloat, y: CGFloat, distance: CGFloat)? in
            guard let frame = displays[id], Self.isUsable(frame) else { return nil }
            let x = frame.midX - source.midX, y = frame.midY - source.midY
            let distance = hypot(x, y)
            // A mirrored display at the same center has no direction to show.
            guard distance > 0, distance.isFinite else { return nil }
            return (id, x, y, distance)
        }
        guard let nearest = arrivals.min(by: {
            $0.distance == $1.distance ? $0.id < $1.id : $0.distance < $1.distance
        }) else { return nil }
        return NotchDisplayConnectionDirection(x: nearest.x / nearest.distance, y: nearest.y / nearest.distance)
    }

    private static func isUsable(_ frame: CGRect) -> Bool {
        !frame.isNull && !frame.isInfinite && frame.width > 0 && frame.height > 0
            && frame.midX.isFinite && frame.midY.isFinite
    }
}

enum NotchDisplayArrivalSignal {
    static let duration: TimeInterval = 1.1

    static func opacity(at age: TimeInterval) -> Double {
        guard age >= 0, age < duration else { return 0 }
        let rise = min(1, age / 0.1), fade = min(1, (duration - age) / 0.3)
        return rise * rise * (3 - 2 * rise) * fade * fade * (3 - 2 * fade)
    }
}
