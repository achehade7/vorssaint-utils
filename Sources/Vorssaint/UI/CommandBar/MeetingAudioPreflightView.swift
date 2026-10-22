// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// Borrow live app-owned audio state; displaying a meeting never starts capture,
/// changes devices, joins a call, or installs another polling loop.
struct MeetingAudioPreflightView: View {
    @ObservedObject private var microphone = MicMuteService.shared
    @ObservedObject private var mixer = AppVolumeMixer.shared
    @ObservedObject private var l10n = L10n.shared

    var body: some View {
        let output = mixer.outputDevices.first { $0.uid == mixer.currentOutputDeviceUID }
        let micLabel = microphone.isMuted ? l10n.s.micMutedHUD : l10n.s.micUnmutedHUD
        HStack(spacing: 5) {
            badge(microphone.isMuted ? "mic.slash.fill" : "mic.fill", title: micLabel,
                  tint: microphone.isMuted ? .orange : NotchNeonPalette.purple)
                .help(l10n.s.micMuteName + " · " + micLabel)
            badge(output.map { $0.isHeadphones ? "headphones" : "speaker.wave.2.fill" } ?? "questionmark",
                  title: output?.name ?? l10n.s.mixerOutputUnavailable, tint: NotchNeonPalette.blue)
                .help(l10n.s.mixerSystemOutputTitle + " · " + (output?.name ?? l10n.s.mixerOutputUnavailable))
        }
        .accessibilityElement(children: .combine)
    }

    private func badge(_ symbol: String, title: String, tint: Color) -> some View {
        Label(title, systemImage: symbol)
            .font(.system(size: 9, weight: .medium))
            .foregroundStyle(tint)
            .lineLimit(1)
            .padding(.horizontal, 6).padding(.vertical, 3)
            .background(tint.opacity(0.08), in: RoundedRectangle(cornerRadius: 5))
            .overlay(RoundedRectangle(cornerRadius: 5).stroke(tint.opacity(0.2), lineWidth: 0.5))
    }
}
