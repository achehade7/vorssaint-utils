// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI
import Carbon.HIToolbox

/// A short confirmation of OCR's clipboard result, without taking focus.
final class ScreenTextPreviewController {
    static let shared = ScreenTextPreviewController()
    private var previewID: UUID?
    private var dismissWork: DispatchWorkItem?
    private var editHotkey: QuickToolHotkey?

    @discardableResult
    func show(text: String) -> Bool {
        close()
        let island = NotchService.shared
        // Recognition may finish after the user has opened another tool.
        guard island.acceptsSystemFeedback, !island.expanded,
              island.captureControls == nil else { return false }
        let id = UUID()
        previewID = id
        let edit = { [weak self] in
            guard let self, self.previewID == id, island.isCaptureVisible(id: id),
                  AppFeature.screenOCR.isAvailable, !ShortcutCapture.isCapturing,
                  !IsSecureEventInputEnabled() else { return }
            self.close()
            TextTransformController.showInIsland(text: text)
        }
        let shown = island.presentCapture(
            id: id, content: AnyView(ScreenTextPreview(text: text, edit: edit)
                .onDisappear { [weak self] in
                    guard self?.previewID == id else { return }
                    self?.close()
                }), height: 150,
            takeFocus: false, closeOnCollapse: true,
            fallback: { [weak self] in self?.close() },
            close: { [weak self] in self?.close() }, hover: { _ in })
        guard shown else {
            close()
            return false
        }
        let editHotkey = QuickToolHotkey(id: 62)
        self.editHotkey = editHotkey
        editHotkey.onPress = edit
        editHotkey.sync(enabled: !ShortcutCapture.isCapturing,
                        shortcut: GlobalShortcut(keyCode: Int64(kVK_ANSI_E), modifiers: .command),
                        storageKey: "screenTextPreviewEditShortcut")
        let work = DispatchWorkItem { [weak self] in
            guard self?.previewID == id else { return }
            self?.close()
        }
        dismissWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: work)
        return true
    }

    func close() {
        editHotkey?.unregister()
        editHotkey?.onPress = nil
        editHotkey = nil
        dismissWork?.cancel()
        dismissWork = nil
        guard let id = previewID else { return }
        previewID = nil
        NotchService.shared.removeCapture(id: id)
    }
}

private struct ScreenTextPreview: View {
    let text: String
    let edit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(L10n.shared.s.ocrCopied, systemImage: "text.viewfinder")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Button(action: edit) {
                    Label(TextTransformStrings.edit, systemImage: "pencil")
                        .font(.system(size: 11, weight: .medium))
                        .padding(.horizontal, 9).padding(.vertical, 5)
                        .background(NotchNeonPalette.purple.opacity(0.12), in: Capsule())
                        .overlay(Capsule().stroke(NotchNeonPalette.purple.opacity(0.3), lineWidth: 0.6))
                }.buttonStyle(.plain)
                    .accessibilityIdentifier("ocr.edit")
                    .keyboardShortcut("e", modifiers: .command)
                    .help(TextTransformStrings.edit + " · ⌘E")
            }.foregroundStyle(NotchNeonPalette.purple)
            Text(String(text.prefix(2000)))
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(.white.opacity(0.9))
                .lineLimit(5)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
                .onTapGesture(perform: edit)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .frame(height: 150)
    }
}
