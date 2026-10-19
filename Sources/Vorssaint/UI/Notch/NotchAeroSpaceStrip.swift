// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

struct NotchAeroSpaceStrip: View {
    @ObservedObject var service: NotchService

    var body: some View {
        let wings = service.aeroSpaceWings
        HStack(spacing: 0) {
            HStack(spacing: 4) {
                ForEach(service.aeroSpaceWorkspaces, id: \.self) { workspace in
                    Button { NotchAeroSpaceService.shared.select(workspace) } label: {
                        Text(workspace)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(workspace == NotchAeroSpaceService.shared.state.current ? Color.orange : .white.opacity(0.65))
                            .frame(width: 26, height: 24)
                            .background(workspace == NotchAeroSpaceService.shared.state.current ? Color.white.opacity(0.12) : .clear,
                                        in: RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("AeroSpace \(workspace)")
                }
            }
            .frame(width: wings.leading, height: service.geometry.stripHeight)
            .clipped()
            if !service.geometry.floats { Color.clear.frame(width: service.geometry.noticeCameraGap) }
            Group {
                if service.aeroSpaceIsHovered {
                    Button { service.open() } label: {
                        Image(systemName: "chevron.down")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 28, height: 26).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(FeatureStrings.notch(L10n.shared.language).open)
                } else { Color.clear }
            }
            .frame(width: wings.trailing, height: service.geometry.stripHeight)
            .clipped()
        }
        .offset(x: service.geometry.floats ? 0 : (wings.trailing - wings.leading) / 2)
        .accessibilityIdentifier("notch.aerospace")
    }
}
