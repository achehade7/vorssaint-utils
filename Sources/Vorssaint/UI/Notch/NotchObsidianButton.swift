// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

struct NotchObsidianButton: View {
    let service: NotchService
    @ObservedObject private var capture = NotchQuickCaptureService.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hovered = false
    @State private var clickedAt: Date?

    private static let mark: NSImage? = {
        guard let url = Bundle.main.url(forResource: "obsidian-crystal", withExtension: "png",
                                        subdirectory: "Images") else { return nil }
        return NSImage(contentsOf: url)
    }()

    var body: some View {
        if let mark = Self.mark {
            Button {
                if !reduceMotion { clickedAt = Date() }
                service.openQuickCapture()
            } label: {
                HStack(spacing: 0) {
                    Image(nsImage: mark).resizable().aspectRatio(contentMode: .fit)
                        .overlay {
                            Path { path in
                                path.move(to: CGPoint(x: 7, y: 0))
                                path.addLines([CGPoint(x: 11, y: 8), CGPoint(x: 7, y: 5)])
                                path.closeSubpath()
                            }
                            .fill(NotchNeonPalette.blue.opacity(hovered ? 0.9 : 0))
                            .blendMode(.screen)
                            .mask(Image(nsImage: mark).resizable().aspectRatio(contentMode: .fit))
                        }
                        .frame(width: 12, height: 12)
                        .shadow(color: NotchNeonPalette.blue.opacity(hovered ? 0.5 : 0), radius: 3)
                        .frame(width: 22, height: 26)
                        .contentShape(Rectangle())
                        .overlay {
                            if let clickedAt {
                                TimelineView(.animation(minimumInterval: 1.0 / 24)) { context in
                                    let progress = min(1, max(0, context.date.timeIntervalSince(clickedAt) / 0.4))
                                    Circle().stroke(NotchNeonPalette.purple.opacity(0.7 * (1 - progress)), lineWidth: 1)
                                        .frame(width: 8 + 16 * progress, height: 8 + 16 * progress)
                                }
                                .allowsHitTesting(false)
                            }
                        }
                    if let session = capture.session {
                        Text("\(session.count)")
                            .font(.system(size: 10, weight: .semibold, design: .monospaced))
                            .foregroundStyle(NotchNeonPalette.purple)
                            .padding(.trailing, 4)
                    }
                }
            }
            .buttonStyle(.plain)
            .onHover { hovered = $0 }
            .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: hovered)
            .task(id: clickedAt) {
                guard clickedAt != nil else { return }
                do { try await Task.sleep(for: .seconds(0.4)) } catch { return }
                clickedAt = nil
            }
            .background(NotchObsidianRightClick(action: openHome))
            .help("\(NotchQuickCaptureStrings.localized(L10n.shared.language).title) · ⌃⌥⌘O · \(NotchQuickCaptureStrings.localized(L10n.shared.language).homeHint)")
            .accessibilityLabel(NotchQuickCaptureStrings.localized(L10n.shared.language).title)
            .accessibilityAction(named: "HOME", openHome)
            .accessibilityValue(capture.session.map {
                String(format: NotchQuickCaptureStrings.localized(L10n.shared.language).sessionCount, $0.count)
            } ?? "")
            .accessibilityIdentifier("notch.obsidian.capture")
        }
    }
    private func openHome() {
        service.perform {
            if let url = URL(string: "obsidian://open?vault=a69ab35a152e299d&file=Home.md") {
                NSWorkspace.shared.open(url)
            }
        }
    }

}

/// A separate shortcut leaves quick capture and its HOME right-click unchanged.
struct NotchMeetingNoteButton: View {
    @ObservedObject private var notes = MeetingNoteService.shared
    var body: some View {
        if notes.activeNote != nil {
            Button { notes.openActiveNote() } label: {
                HStack(spacing: 3) {
                    MeetingNoteMark().frame(width: 12, height: 12)
                    Image(systemName: "doc.text").font(.system(size: 10, weight: .medium))
                }
                .foregroundStyle(NotchNeonPalette.purple).padding(.horizontal, 6).frame(height: 26)
                .background(NotchNeonPalette.purple.opacity(0.12), in: RoundedRectangle(cornerRadius: 7))
            }.buttonStyle(.plain)
                .help(MeetingNoteStrings.localized(L10n.shared.language).title)
                .accessibilityLabel(MeetingNoteStrings.localized(L10n.shared.language).title)
                .accessibilityIdentifier("notch.meetingNote")
        }
    }
}
