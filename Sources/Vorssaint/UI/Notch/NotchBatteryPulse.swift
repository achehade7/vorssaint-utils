// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

enum NotchBatterySignal {
    static let criticalLevel = 10
    static let warningLevels = [10, 5, 1]
    static let duration: TimeInterval = 2.4

    static func crossedCritical(before: Int?, next: Int?, externalConnected: Bool) -> Bool {
        guard !externalConnected, let before, let next,
              (0...100).contains(before), (0...criticalLevel).contains(next) else { return false }
        return warningLevels.contains { before > $0 && next <= $0 }
    }

    /// Retained across sleep/lock baselines; a cable connection rearms the levels.
    struct Tracker {
        private var announced: Set<Int> = []

        mutating func update(before: Int?, next: Int?, externalConnected: Bool) -> Bool {
            if externalConnected { announced.removeAll(); return false }
            guard NotchBatterySignal.crossedCritical(before: before, next: next, externalConnected: false),
                  let next else { return false }
            let reached = Set(warningLevels.filter { next <= $0 })
            let fresh = !reached.subtracting(announced).isEmpty
            announced.formUnion(reached)
            return fresh
        }
    }

    static func contentOpacity(at age: TimeInterval) -> Double {
        guard age >= 0, age < duration else { return 0 }
        return min(1, age / 0.15) * min(1, (duration - age) / 0.3)
    }

    static func opacity(at age: TimeInterval, reduceMotion: Bool) -> Double {
        guard age >= 0, age < duration else { return 0 }
        if reduceMotion {
            return min(1, age / 0.2) * min(1, (duration - age) / 0.4) * 0.7
        }
        let beat = age < 1.3 ? age : age - 1.3
        guard beat < 1.1 else { return 0 }
        return pow(sin(beat / 1.1 * .pi), 2)
    }
}

/// The bar keeps the persistent warning. The island acknowledges the threshold
/// twice, temporarily taking the strip while the underlying activity continues.
struct NotchBatteryPulse: View {
    @ObservedObject var service: NotchService
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if let began = service.neonLowBatteryAt, service.showsLowBatteryWarning {
            TimelineView(.animation(minimumInterval: 1.0 / 30)) { context in
                let size = service.surfaceSize
                let shape = NotchShape.island(height: size.height, geometry: service.geometry)
                    .path(in: CGRect(origin: .zero, size: size))
                ZStack {
                    NotchBatteryEdge(shape: shape, size: size, age: context.date.timeIntervalSince(began),
                                     fullscreen: service.displayIsFullscreen, reduceMotion: reduceMotion)
                    if let percent = service.power.chargePercent {
                        let wing = service.geometry.floats ? size.width / 2 : (size.width - service.geometry.cameraWidth) / 2
                        HStack(spacing: 0) {
                            Image(systemName: "battery.0percent").frame(width: wing)
                            Spacer(minLength: 0)
                            Text("\(percent)%").monospacedDigit().frame(width: wing)
                        }
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(NotchBatteryEdge.tint)
                        .opacity(NotchBatterySignal.contentOpacity(at: context.date.timeIntervalSince(began)))
                    }
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}

/// Shared by the ordinary island and the awake lock-screen island.
struct NotchBatteryEdge: View {
    static let tint = Color(red: 1, green: 81.0 / 255, blue: 111.0 / 255)
    let shape: Path
    let size: CGSize
    let age: TimeInterval
    let fullscreen: Bool
    let reduceMotion: Bool

    var body: some View {
        shape.stroke(Self.tint, lineWidth: 2.5)
            .mask {
                if fullscreen {
                    HStack {
                        Rectangle().frame(width: 8)
                        Spacer(minLength: 0)
                        Rectangle().frame(width: 8)
                    }
                    .padding(.vertical, 6)
                } else {
                    VStack { Spacer(minLength: 0); Rectangle().frame(height: 10) }
                }
            }
            .blur(radius: 0.6)
            .clipShape(shape)
            .opacity(NotchBatterySignal.opacity(at: age,
                                                 reduceMotion: reduceMotion))
    }
}
