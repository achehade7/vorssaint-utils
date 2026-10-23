// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

struct FileDiffDropFrames: PreferenceKey {
    static var defaultValue: [ClipboardFileDiff.Side: CGRect] = [:]
    static func reduce(value: inout [ClipboardFileDiff.Side: CGRect], nextValue: () -> [ClipboardFileDiff.Side: CGRect]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}

struct NotchFileDiffView: View {
    @ObservedObject var service: NotchService
    @ObservedObject private var draft = ClipboardFileDiffService.shared
    @ObservedObject private var l10n = L10n.shared
    private var strings: ClipboardFileDiffStrings { .localized(l10n.language) }
    private var diff: ClipboardDiffStrings { .localized(l10n.language) }

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "arrow.left.arrow.right").foregroundStyle(.white.opacity(0.65))
                Text(strings.title).font(.system(size: 13, weight: .semibold))
                Spacer(minLength: 4)
                Button { draft.clear() } label: {
                    Image(systemName: "xmark").font(.system(size: 10, weight: .semibold)).frame(width: 24, height: 24)
                }
                .buttonStyle(.plain).help(strings.clear).accessibilityLabel(strings.clear)
            }
            HStack(spacing: 10) { target(.before); target(.after) }
                .frame(maxHeight: .infinity)
            if let error = draft.error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.system(size: 11)).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
            } else {
                Text(strings.hint).font(.system(size: 11)).foregroundStyle(.white.opacity(0.6))
            }
            if service.offeringFileDiff {
                Label(strings.shelf, systemImage: "tray.and.arrow.down")
                    .font(.system(size: 11, weight: .medium))
                    .frame(maxWidth: .infinity).padding(.vertical, 7)
                    .background(.white.opacity(service.fileDiffTarget == nil ? 0.12 : 0.04), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .foregroundStyle(.white)
    }

    private func target(_ side: ClipboardFileDiff.Side) -> some View {
        let before = side == .before
        let color: Color = before ? .orange : .blue
        let selected = service.offeringFileDiff && service.fileDiffTarget == side
        return VStack(alignment: .leading, spacing: 9) {
            Label(before ? diff.before : diff.after, systemImage: before ? "minus.circle.fill" : "plus.circle.fill")
                .font(.system(size: 12, weight: .semibold)).foregroundStyle(color)
            Spacer(minLength: 0)
            if draft.loading.contains(side) {
                ProgressView().controlSize(.small).colorScheme(.dark).frame(maxWidth: .infinity)
            } else {
                Image(systemName: draft.inputs[side] == nil ? "doc.badge.plus" : "doc.text")
                    .font(.system(size: 23, weight: .light)).foregroundStyle(.white.opacity(0.7))
                Text(draft.inputs[side]?.name ?? strings.dropFile)
                    .font(.system(size: 12, weight: draft.inputs[side] == nil ? .regular : .medium))
                    .lineLimit(2).truncationMode(.middle)
                    .help(draft.inputs[side]?.name ?? strings.dropFile)
            }
            Spacer(minLength: 0)
        }
        .padding(12).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .background(color.opacity(selected ? 0.18 : 0.07), in: RoundedRectangle(cornerRadius: 12))
        .overlay { RoundedRectangle(cornerRadius: 12).strokeBorder(color.opacity(selected ? 0.9 : 0.3), lineWidth: selected ? 1.5 : 0.75) }
        .background(GeometryReader { geometry in
            Color.clear.preference(key: FileDiffDropFrames.self, value: [side: geometry.frame(in: .named("islandDropSurface"))])
        })
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}
