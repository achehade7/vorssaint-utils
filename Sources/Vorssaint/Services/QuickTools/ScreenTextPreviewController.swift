// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// A short confirmation of OCR's clipboard result, without taking focus.
final class ScreenTextPreviewController {
    static let shared = ScreenTextPreviewController()
    private var previewID: UUID?
    private var dismissWork: DispatchWorkItem?

    @discardableResult
    func show(text: String) -> Bool {
        close()
        let island = NotchService.shared
        // Recognition may finish after the user has opened another tool.
        guard island.acceptsSystemFeedback, !island.expanded,
              island.captureControls == nil else { return false }
        let id = UUID()
        previewID = id
        let shown = island.presentCapture(
            id: id, content: AnyView(ScreenTextPreview(text: text)), height: 150,
            takeFocus: false, closeOnCollapse: true,
            fallback: { [weak self] in self?.close() },
            close: { [weak self] in self?.close() }, hover: { _ in })
        guard shown else {
            close()
            return false
        }
        let work = DispatchWorkItem { [weak self] in
            guard self?.previewID == id else { return }
            self?.close()
        }
        dismissWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: work)
        return true
    }

    func close() {
        dismissWork?.cancel()
        dismissWork = nil
        guard let id = previewID else { return }
        previewID = nil
        NotchService.shared.removeCapture(id: id)
    }
}

private struct ScreenTextPreview: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(L10n.shared.s.ocrCopied, systemImage: "text.viewfinder")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                if AppFeature.textSnippets.isAvailable {
                    Button {
                        ScreenTextPreviewController.shared.close()
                        SnippetLibraryService.shared.saveCapturedText(text)
                    } label: {
                        Label(SnippetCaptureStrings.localized(L10n.shared.language).save, systemImage: "text.badge.plus")
                            .font(.system(size: 11, weight: .medium))
                            .padding(.horizontal, 9).padding(.vertical, 5)
                            .background(NotchNeonPalette.purple.opacity(0.12), in: Capsule())
                            .overlay(Capsule().stroke(NotchNeonPalette.purple.opacity(0.3), lineWidth: 0.6))
                    }.buttonStyle(.plain)
                        .accessibilityIdentifier("ocr.saveSnippet")
                }
            }.foregroundStyle(NotchNeonPalette.purple)
            Text(String(text.prefix(2000)))
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(.white.opacity(0.9))
                .lineLimit(5)
                .frame(maxWidth: .infinity, alignment: .leading)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .frame(height: 150)
    }
}
