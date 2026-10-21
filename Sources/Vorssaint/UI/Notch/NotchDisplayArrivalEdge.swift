// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// One blue-violet light travels toward the newly attached screen. The parent
/// owns its short clock; the view never monitors displays or keeps animating.
struct NotchDisplayArrivalEdge: View {
    let shape: Path
    let size: CGSize
    let direction: NotchDisplayConnectionDirection
    let age: TimeInterval
    let reduceMotion: Bool

    var body: some View {
        let blue = NotchNeonPalette.blue, purple = NotchNeonPalette.purple
        let phase = min(1, max(0, age / 0.85))
        let stops: [Gradient.Stop] = reduceMotion ? [
            .init(color: purple, location: 0), .init(color: blue, location: 1)
        ] : [
            .init(color: .clear, location: 0),
            .init(color: .clear, location: max(0, phase - 0.24)),
            .init(color: purple, location: max(0, phase - 0.1)),
            .init(color: blue, location: phase),
            .init(color: .clear, location: min(1, phase + 0.08)),
            .init(color: .clear, location: 1)
        ]
        // Convert the screen vector once, including the island's aspect ratio,
        // so a display above produces upward travel rather than a sideways cue.
        let width = max(1, size.width), height = max(1, size.height)
        let reach = (abs(direction.x) * width + abs(direction.y) * height) / 2
        let x = direction.x * reach / width, y = direction.y * reach / height
        let light = LinearGradient(stops: stops,
                                   startPoint: UnitPoint(x: 0.5 - x, y: 0.5 + y),
                                   endPoint: UnitPoint(x: 0.5 + x, y: 0.5 - y))
        shape.stroke(light, lineWidth: 1.6)
            .shadow(color: purple.opacity(0.65), radius: 2)
            .opacity(NotchDisplayArrivalSignal.opacity(at: age))
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

/// Fullscreen keeps feedback inside the side edges, with no lower neon or spill.
struct NotchFullscreenDisplayPulse: View {
    @ObservedObject var service: NotchService
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if let arrival = service.displayArrival, service.displayIsFullscreen,
           service.acceptsSystemFeedback, !service.expanded, !service.peeking,
           !service.dragPlaceholder, !service.showsAeroSpace, service.captureControls == nil {
            TimelineView(.animation(minimumInterval: 1.0 / 30)) { context in
                let size = service.surfaceSize
                let shape = NotchShape.island(height: size.height, geometry: service.geometry)
                    .path(in: CGRect(origin: .zero, size: size))
                NotchDisplayArrivalEdge(shape: shape, size: size, direction: arrival.direction,
                                        age: context.date.timeIntervalSince(arrival.began), reduceMotion: reduceMotion)
                    .mask {
                        HStack {
                            Rectangle().frame(width: 14)
                            Spacer(minLength: 0)
                            Rectangle().frame(width: 14)
                        }
                        .padding(.vertical, 5)
                    }
                    .clipShape(shape)
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}
