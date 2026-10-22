// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// A temporary form inside the existing nonactivating snippet panel.
struct SnippetTemplateForm: View {
    @ObservedObject private var library = SnippetLibraryService.shared
    @ObservedObject private var l10n = L10n.shared
    @FocusState private var focusedField: String?
    private let violet = Color(red: 0.73, green: 0.49, blue: 1)
    private let blue = Color(red: 0.43, green: 0.56, blue: 1)

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "text.badge.plus")
                Text(library.template?.name ?? "")
                    .font(.system(size: 17, weight: .semibold))
                Spacer()
                Text("esc").font(.caption.monospaced()).foregroundStyle(.secondary)
            }
            .foregroundStyle(violet)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(library.templateFields, id: \.self) { field in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(field.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                            TextField(field, text: Binding(
                                get: { library.templateValues[field] ?? "" },
                                set: { library.templateValues[field] = $0 }))
                                .textFieldStyle(.plain)
                                .font(.system(size: 14))
                                .focused($focusedField, equals: field)
                                .padding(10)
                                .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 9))
                                .overlay(RoundedRectangle(cornerRadius: 9)
                                    .stroke(focusedField == field ? violet.opacity(0.7) : .white.opacity(0.1), lineWidth: 1))
                        }
                    }
                }
                .padding(1)
            }
            .frame(maxHeight: 260)
            .fixedSize(horizontal: false, vertical: true)
            Text(SnippetTemplateSupport.fill(library.template?.replacement ?? "", values: library.templateValues))
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(3, reservesSpace: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack {
                Button(l10n.s.uninstallerCancel) { library.hide() }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                Spacer()
                Button {
                    library.finishTemplate()
                } label: {
                    HStack(spacing: 7) {
                        Text(library.templateAction == .copy
                             ? FeatureStrings.clipboard(l10n.language).copy
                             : FeatureStrings.snippets(l10n.language).dateTimeConfirmInsert)
                        Text("↩")
                    }
                    .font(.system(size: 13, weight: .semibold))
                    .padding(.horizontal, 15).padding(.vertical, 8)
                    .background(LinearGradient(colors: [violet, blue], startPoint: .leading, endPoint: .trailing),
                                in: Capsule())
                    .foregroundStyle(.black)
                    .opacity(library.canFinishTemplate ? 1 : 0.35)
                }
                .buttonStyle(.plain)
                .disabled(!library.canFinishTemplate)
            }
        }
        .padding(20)
        .background(Color.black.opacity(0.94))
        .preferredColorScheme(.dark)
        .onAppear { focusedField = library.templateFields.first }
        .onChange(of: library.presentationID) { _, _ in focusedField = library.templateFields.first }
    }
}
