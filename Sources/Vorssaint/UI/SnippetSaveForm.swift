// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

struct SnippetSaveForm: View {
    @ObservedObject var draft: SnippetSaveDraft
    @ObservedObject private var l10n = L10n.shared
    @FocusState private var nameFocused: Bool
    private var text: SnippetFeatureStrings { FeatureStrings.snippets(l10n.language) }
    private var capture: SnippetCaptureStrings { .localized(l10n.language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(capture.save, systemImage: "text.badge.plus")
                    .font(.system(size: 17, weight: .semibold)).foregroundStyle(NotchNeonPalette.purple)
                Spacer()
                Text("esc").font(.caption.monospaced()).foregroundStyle(.secondary)
            }
            TextField(text.namePlaceholder, text: $draft.name)
                .textFieldStyle(.plain).focused($nameFocused)
                .padding(10).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 9))
                .onSubmit { SnippetLibraryService.shared.finishSave() }
            TextEditor(text: $draft.text)
                .font(.system(size: 13, design: .monospaced))
                .scrollContentBackground(.hidden).padding(8)
                .frame(height: 150)
                .background(.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 9))
                .accessibilityLabel(text.replacementLabel)
            Toggle(capture.today, isOn: $draft.temporary).toggleStyle(.checkbox).font(.callout)
            if let error = draft.error {
                Text(error == .permanentName ? capture.permanentName : text.clipboardChanged)
                    .font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
            } else if let replacement = draft.replacement {
                Text(String(format: text.replaceClipboardFormat, replacement.name))
                    .font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Button(l10n.s.uninstallerCancel) { SnippetLibraryService.shared.hide() }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                Spacer()
                Button { SnippetLibraryService.shared.finishSave() } label: {
                    Text(text.saveButton + "  ⌘↩")
                        .font(.system(size: 13, weight: .semibold)).padding(.horizontal, 14).padding(.vertical, 8)
                        .background(LinearGradient(colors: [NotchNeonPalette.purple, NotchNeonPalette.blue],
                                                   startPoint: .leading, endPoint: .trailing), in: Capsule())
                        .foregroundStyle(.black).opacity(draft.canSave ? 1 : 0.35)
                }.buttonStyle(.plain).disabled(!draft.canSave)
            }
        }.padding(20).background(.black.opacity(0.94)).preferredColorScheme(.dark)
            .onAppear { nameFocused = true; SnippetLibraryService.shared.refreshPanelLayout() }
            .onChange(of: draft.error) { SnippetLibraryService.shared.refreshPanelLayout() }
            .onChange(of: draft.replacement) { SnippetLibraryService.shared.refreshPanelLayout() }
    }
}
