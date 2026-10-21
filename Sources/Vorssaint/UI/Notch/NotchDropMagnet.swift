// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// Distance changes decoration only; the native drop areas keep their exact
/// bounds and compatibility checks.
enum NotchDropMagnet {
    static func strength(at point: CGPoint?, in frame: CGRect, reach: CGFloat, available: Bool) -> Double {
        guard available, let point, point.x.isFinite, point.y.isFinite,
              !frame.isNull, !frame.isInfinite,
              frame.minX.isFinite, frame.minY.isFinite, frame.maxX.isFinite, frame.maxY.isFinite,
              frame.width > 0, frame.height > 0,
              reach.isFinite, reach > 0 else { return 0 }
        let x = max(frame.minX - point.x, 0, point.x - frame.maxX)
        let y = max(frame.minY - point.y, 0, point.y - frame.maxY)
        let nearby = Double(max(0, 1 - hypot(x, y) / reach))
        return 0.12 + 0.88 * nearby * nearby * (3 - 2 * nearby)
    }
}

/// Frames use the same island-local coordinates already reported by the
/// native drag callback. No hover monitor or animation clock is needed.
struct NotchDropMagnetOverlay: View {
    @ObservedObject var service: NotchService
    var available = true
    let cornerRadius: CGFloat
    var reach: CGFloat = 90

    var body: some View {
        GeometryReader { geometry in
            let strength = service.fileDropEmphasis(in: geometry.frame(in: .named("islandDropSurface")),
                                                    available: available, reach: reach)
            if strength > 0 {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(NotchNeonPalette.purple.opacity(0.025 + 0.08 * strength))
                    .overlay {
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .strokeBorder(NotchNeonPalette.purple.opacity(0.18 + 0.62 * strength),
                                          lineWidth: 0.7 + 0.8 * strength)
                    }
                    .shadow(color: NotchNeonPalette.purple.opacity(0.2 * strength), radius: 4 * strength)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
