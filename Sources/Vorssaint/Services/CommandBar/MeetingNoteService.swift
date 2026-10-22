// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI
import EventKit

final class MeetingNoteService: ObservableObject {
    static let shared = MeetingNoteService()
    private var panel: NSPanel?
    private var draft: MeetingNoteDraft?
    @Published private(set) var activeNote: URL?
    private var activeNoteEnd: Date?
    private var expiry: Timer?

    func openActiveNote() {
        guard let activeNote, let activeNoteEnd, activeNoteEnd > Date() else { clearActiveNote(); return }
        NotchService.shared.perform { NSWorkspace.shared.open(activeNote) }
    }

    private func clearActiveNote() {
        expiry?.invalidate(); expiry = nil
        activeNote = nil; activeNoteEnd = nil
    }

    private func keepShortcut(_ link: URL?, until end: Date) {
        clearActiveNote()
        guard let link, end > Date() else { return }
        activeNote = link; activeNoteEnd = end
        let timer = Timer(fire: end, interval: 0, repeats: false) { [weak self] _ in self?.clearActiveNote() }
        expiry = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    func show(_ event: NotchCalendarEvent, joining: Bool = true) {
        guard allowed(event, joining: joining), draft?.saving != true else { return }
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
        panel.contentView = NSHostingView(rootView: MeetingNoteView(draft: draft, joining: joining, cancel: { [weak self] in
            if draft.cancel() { self?.close() }
        }, confirm: { [weak self] in self?.confirm(event, draft: draft, joining: joining) }))
        let screen = NSScreen.screens.first { $0.frame.contains(NSEvent.mouseLocation) } ?? NSScreen.main
        if let frame = screen?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: frame.midX - 220, y: frame.midY + frame.height * 0.12 - 125))
        }
        self.panel = panel
        panel.orderFrontRegardless(); panel.makeKey()
    }

    private func allowed(_ event: NotchCalendarEvent, joining: Bool) -> Bool {
        NotchCalendarSupport.isEnabled() && event.end > Date() && (!joining || event.meetingURL != nil)
            && EKEventStore.authorizationStatus(for: .event) == .fullAccess
    }

    private func confirm(_ event: NotchCalendarEvent, draft: MeetingNoteDraft, joining: Bool) {
        draft.save(allowed: allowed(event, joining: joining)) { [weak self] file in
            guard let self else { return }
            guard let prepared = file else { NotchService.shared.signalQuickCapture(success: false); return }
            self.close()
            let link = MeetingNoteStore.obsidianURL(prepared.file)
            if joining {
                if self.allowed(event, joining: true), let meeting = event.meetingURL { NSWorkspace.shared.open(meeting) }
                self.keepShortcut(link, until: event.end)
            } else if let link { NSWorkspace.shared.open(link) }
            let text = MeetingNoteStrings.localized(L10n.shared.language)
            _ = NotchService.shared.show(NotchNotice(event: .capture, title: "", detail: prepared.created ? text.created : text.ready,
                                                    symbol: "doc.text", fileURL: link, meetingNote: true))
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
    var joining = true
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
                    Text((joining ? text.join : MeetingNoteStrings.prepareAndOpen(L10n.shared.language)) + "  ↩").font(.system(size: 12, weight: .semibold))
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
