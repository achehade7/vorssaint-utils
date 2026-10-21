// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

enum NotchUnlockHandoffSignal {
    static let contraction: TimeInterval = 0.3
    static let duration: TimeInterval = 1.15

    static func opacity(age: TimeInterval, leaving: Bool) -> Double {
        guard age.isFinite, age >= 0, age < duration else { return 0 }
        if leaving { return max(0, 1 - age / contraction) }
        let elapsed = age - contraction
        guard elapsed >= 0 else { return 0 }
        return min(1, elapsed / 0.16) * min(1, (duration - age) / 0.45)
    }

    static func width(age: TimeInterval, leaving: Bool, reduceMotion: Bool) -> CGFloat {
        guard !reduceMotion else { return 1 }
        let progress = min(1, max(0, leaving ? age / contraction : (age - contraction) / 0.4))
        let smooth = progress * progress * (3 - 2 * progress)
        return leaving ? 1 - 0.96 * smooth : 0.04 + 0.96 * smooth
    }
}

/// A lock-screen contraction and a desktop return share one timestamp. The
/// fullscreen return stays inside the side contours, clear of the application.
struct NotchUnlockHandoffEdge: View {
    let shape: Path
    let size: CGSize
    let age: TimeInterval
    let leaving: Bool
    let fullscreen: Bool
    let reduceMotion: Bool

    var body: some View {
        let light = LinearGradient(colors: [NotchNeonPalette.purple, NotchNeonPalette.blue],
                                   startPoint: .leading, endPoint: .trailing)
        shape.stroke(light, lineWidth: 1.7)
            .scaleEffect(x: fullscreen ? 1 : NotchUnlockHandoffSignal.width(
                age: age, leaving: leaving, reduceMotion: reduceMotion), y: 1, anchor: .bottom)
            .shadow(color: NotchNeonPalette.purple.opacity(0.6), radius: 1.5)
            .mask {
                if fullscreen {
                    HStack {
                        Rectangle().frame(width: 12)
                        Spacer(minLength: 0)
                        Rectangle().frame(width: 12)
                    }
                    .padding(.vertical, 5)
                } else {
                    VStack(spacing: 0) {
                        Spacer(minLength: 0)
                        Rectangle().frame(height: 7)
                    }
                }
            }
            .clipShape(shape)
            .opacity(NotchUnlockHandoffSignal.opacity(age: age, leaving: leaving))
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

struct NotchUnlockHandoffPulse: View {
    @ObservedObject var service: NotchService
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if let began = service.neonUnlockAt, service.acceptsSystemFeedback,
           !service.expanded, !service.peeking, !service.dragPlaceholder,
           !service.showsAeroSpace, service.captureControls == nil {
            TimelineView(.animation(minimumInterval: 1.0 / 30)) { context in
                let size = service.surfaceSize
                NotchUnlockHandoffEdge(
                    shape: NotchShape.island(height: size.height, geometry: service.geometry)
                        .path(in: CGRect(origin: .zero, size: size)),
                    size: size, age: context.date.timeIntervalSince(began), leaving: false,
                    fullscreen: service.displayIsFullscreen, reduceMotion: reduceMotion)
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}
