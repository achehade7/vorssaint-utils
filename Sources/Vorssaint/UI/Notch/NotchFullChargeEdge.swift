// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// Full charge is a measured crossing while already connected, not a charger
/// arrival or a charging-status toggle at an unchanged percentage.
enum NotchFullChargeSignal {
    static let duration: TimeInterval = 1.7
    static let travelDuration: TimeInterval = 0.75

    static func crossed(before: Int?, next: Int?, wasExternal: Bool, external: Bool) -> Bool {
        guard wasExternal, external, let before, (0..<100).contains(before), next == 100 else { return false }
        return true
    }

    static func progress(at age: TimeInterval) -> Double {
        let phase = min(1, max(0, age / travelDuration))
        return phase * phase * (3 - 2 * phase)
    }

    static func beamOpacity(at age: TimeInterval) -> Double {
        guard age >= 0, age < travelDuration + 0.12 else { return 0 }
        return min(1, age / 0.08) * min(1, (travelDuration + 0.12 - age) / 0.16)
    }

    static func flashOpacity(at age: TimeInterval, reduceMotion: Bool) -> Double {
        let start = reduceMotion ? 0 : travelDuration - 0.06
        let length = duration - start
        let phase = (age - start) / length
        guard phase >= 0, phase < 1 else { return 0 }
        return pow(sin(phase * .pi), 2) * 0.75
    }
}

/// Two lights converge, then leave one soft green flash. Fullscreen keeps
/// the convergence inside each side edge so the camera cannot cover it and
/// no light extends down over the application.
struct NotchFullChargeEdge: View {
    let shape: Path
    let size: CGSize
    let age: TimeInterval
    let fullscreen: Bool
    let reduceMotion: Bool

    var body: some View {
        let green = NotchNeonPalette.charging
        let progress = NotchFullChargeSignal.progress(at: age)
        let flash = NotchFullChargeSignal.flashOpacity(at: age, reduceMotion: reduceMotion)
        let beam = NotchFullChargeSignal.beamOpacity(at: age)
        let width = fullscreen ? min(10, size.height * 0.28) : min(48, size.width * 0.17)
        ZStack {
            shape.stroke(green, lineWidth: 1.8).opacity(flash)
            if !reduceMotion {
                ZStack {
                    ForEach(0..<2) { side in
                        let span = fullscreen ? max(0, size.height - 10) : size.width
                        let position = span * (side == 0 ? progress / 2 : 1 - progress / 2)
                        LinearGradient(colors: [.clear, green, .white.opacity(0.95), green, .clear],
                                       startPoint: fullscreen ? .top : .leading,
                                       endPoint: fullscreen ? .bottom : .trailing)
                            .frame(width: fullscreen ? size.width : width,
                                   height: fullscreen ? width : size.height)
                            .position(x: fullscreen ? size.width / 2 : position,
                                      y: fullscreen ? position + 5 : size.height / 2)
                    }
                }
                .mask(shape.stroke(lineWidth: 2))
                .opacity(beam)
            }
        }
        .shadow(color: green.opacity(fullscreen ? 0.4 : 0.7), radius: fullscreen ? 1 : 2)
        .mask {
            if fullscreen {
                HStack {
                    Rectangle().frame(width: 8)
                    Spacer(minLength: 0)
                    Rectangle().frame(width: 8)
                }
                .padding(.vertical, 4)
            } else {
                VStack { Spacer(minLength: 0); Rectangle().frame(height: 12) }
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct NotchFullscreenFullChargePulse: View {
    @ObservedObject var service: NotchService
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if let began = service.neonFullChargeAt, service.displayIsFullscreen,
           service.acceptsSystemFeedback, !service.expanded, !service.peeking,
           !service.dragPlaceholder, !service.showsAeroSpace, service.captureControls == nil {
            TimelineView(.animation(minimumInterval: 1.0 / 30)) { context in
                let size = service.surfaceSize
                let shape = NotchShape.island(height: size.height, geometry: service.geometry)
                    .path(in: CGRect(origin: .zero, size: size))
                NotchFullChargeEdge(shape: shape, size: size,
                                    age: context.date.timeIntervalSince(began), fullscreen: true,
                                    reduceMotion: reduceMotion)
                    .clipShape(shape)
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}
