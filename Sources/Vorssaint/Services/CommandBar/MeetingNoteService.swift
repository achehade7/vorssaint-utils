// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI
import EventKit

final class MeetingNoteService {
    static let shared = MeetingNoteService()
    private var panel: NSPanel?
    private var draft: MeetingNoteDraft?

    func show(_ event: NotchCalendarEvent) {
        guard allowed(event), draft?.saving != true else { return }
        close()
        var people = event.notePeople
        if !people.contains(where: \.isCurrentUser), !NSFullUserName().isEmpty {
            people.append(.init(name: NSFullUserName(), isCurrentUser: true))
        }
        let draft = MeetingNoteDraft(input: .init(identity: event.noteEventKey, title: event.title,
                                                  start: event.start, end: event.end, people: people), store: .personal)
        self.draft = draft
        let panel = MeetingNotePanel(contentRect: NSRect(x: 0, y: 0, width: 440, height: 250),
                                     styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isReleasedWhenClosed = false
        panel.level = .floating; panel.isOpaque = false; panel.backgroundColor = .clear
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.contentView = NSHostingView(rootView: MeetingNoteView(draft: draft, cancel: { [weak self] in
            if draft.cancel() { self?.close() }
        }, confirm: { [weak self] in self?.confirm(event, draft: draft) }))
        let screen = NSScreen.screens.first { $0.frame.contains(NSEvent.mouseLocation) } ?? NSScreen.main
        if let frame = screen?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: frame.midX - 220, y: frame.midY + frame.height * 0.12 - 125))
        }
        self.panel = panel
        panel.orderFrontRegardless(); panel.makeKey()
    }

    private func allowed(_ event: NotchCalendarEvent) -> Bool {
        NotchCalendarSupport.isEnabled() && event.end > Date() && event.meetingURL != nil
            && EKEventStore.authorizationStatus(for: .event) == .fullAccess
    }

    private func confirm(_ event: NotchCalendarEvent, draft: MeetingNoteDraft) {
        draft.save(allowed: allowed(event)) { [weak self] file in
            guard let self else { return }
            guard let file else { NotchService.shared.signalQuickCapture(success: false); return }
            self.close()
            if self.allowed(event), let meeting = event.meetingURL { NSWorkspace.shared.open(meeting) }
            var link = URLComponents()
            link.scheme = "obsidian"; link.host = "open"
            link.queryItems = [URLQueryItem(name: "path", value: file.path)]
            let text = MeetingNoteStrings.localized(L10n.shared.language)
            _ = NotchService.shared.show(NotchNotice(event: .capture, title: "", detail: text.ready,
                                                    symbol: "doc.text", fileURL: link.url, meetingNote: true))
        }
    }

    private func close() { panel?.orderOut(nil); panel = nil; draft = nil }
}

private final class MeetingNotePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

private struct MeetingNoteView: View {
    @ObservedObject var draft: MeetingNoteDraft
    let cancel: () -> Void, confirm: () -> Void
    @FocusState private var focused: Bool
    private var text: MeetingNoteStrings { .localized(L10n.shared.language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                MeetingNoteMark().frame(width: 22, height: 24)
                Text(text.title).font(.system(size: 16, weight: .semibold))
                Spacer()
                Text("esc").font(.caption.monospaced()).foregroundStyle(.secondary)
            }.foregroundStyle(NotchNeonPalette.purple)
            TextField(text.title, text: $draft.topic)
                .textFieldStyle(.plain).font(.system(size: 14)).focused($focused)
                .padding(10).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                .disabled(draft.saving)
            Text("meetings/" + draft.fileName).font(.system(size: 10, design: .monospaced))
                .foregroundStyle(NotchNeonPalette.blue).lineLimit(1).truncationMode(.middle)
            Text(MeetingNoteStore.purpose(draft.input)).font(.system(size: 12)).foregroundStyle(.secondary)
            Spacer(minLength: 0)
            if draft.failed { Text(text.failed).font(.system(size: 11)).foregroundStyle(.orange).lineLimit(2) }
            HStack {
                Button(NotchQuickCaptureStrings.localized(L10n.shared.language).cancel, action: cancel)
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                Spacer()
                if draft.saving { ProgressView().controlSize(.small) }
                Button(action: confirm) {
                    Text(text.join + "  ↩").font(.system(size: 12, weight: .semibold))
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(LinearGradient(colors: [NotchNeonPalette.purple, NotchNeonPalette.blue],
                                                   startPoint: .leading, endPoint: .trailing), in: Capsule())
                        .foregroundStyle(.black)
                }.buttonStyle(.plain)
            }.disabled(draft.saving)
        }.padding(18).frame(width: 440, height: 250)
            .background(.black.opacity(0.97), in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(NotchNeonPalette.purple.opacity(0.3), lineWidth: 0.7))
            .preferredColorScheme(.dark).onAppear { focused = true }
            .onSubmit(confirm).onExitCommand(perform: cancel)
    }
}

struct MeetingNoteMark: View {
    private static let image = Bundle.main.url(forResource: "obsidian-crystal", withExtension: "png", subdirectory: "Images")
        .flatMap { NSImage(contentsOf: $0) }
    var body: some View {
        if let image = Self.image { Image(nsImage: image).resizable().scaledToFit() }
        else { Image(systemName: "diamond.fill").foregroundStyle(NotchNeonPalette.purple) }
    }
}
