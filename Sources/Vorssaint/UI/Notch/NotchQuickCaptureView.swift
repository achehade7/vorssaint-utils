// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

struct NotchQuickCaptureView: View {
    let service: NotchService
    @ObservedObject var draft = NotchQuickCaptureService.shared
    @ObservedObject private var l10n = L10n.shared
    @FocusState private var focused: Bool
    @FocusState private var extractFocused: Bool
    @State private var preview: Preview?
    private var text: NotchQuickCaptureStrings { .localized(l10n.language) }

    private enum Preview: Identifiable {
        case image(UUID)
        case extract(UUID)
        var id: UUID {
            switch self {
            case .image(let id), .extract(let id): return id
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(text.title).foregroundStyle(NotchNeonPalette.purple)
                Spacer(minLength: 0)
                if draft.pendingCount > 0 || draft.saving {
                    ProgressView().controlSize(.mini).accessibilityLabel(text.pending)
                }
                Text(String(format: text.count, draft.imageCount, draft.extracts.count))
                    .foregroundStyle(.secondary).lineLimit(1)
                    .accessibilityIdentifier("notch.quickCapture.count")
            }
            .font(.system(size: 11, weight: .semibold))
            .help(text.title + " · ⌃⌥⌘O")
            meetingContext
            HStack(spacing: 8) {
                TextField(text.labelPrompt, text: $draft.label)
                    .textFieldStyle(.plain).disabled(!draft.canEdit)
                    .accessibilityIdentifier("notch.quickCapture.label")
                Button {
                    if draft.capturingGroup { draft.pauseGroupCapture() }
                    else { draft.captureGroup() }
                } label: {
                    HStack(spacing: 4) {
                        Label(draft.capturingGroup ? text.stopSession : text.startSession,
                              systemImage: draft.capturingGroup ? "pause.fill" : "rectangle.stack")
                            .lineLimit(1)
                        Text("⌘G").foregroundStyle(.secondary)
                    }
                }
                .foregroundStyle(NotchNeonPalette.purple)
                .disabled(!draft.canEdit)
                .help(text.startSession + " · ⌘G")
                .accessibilityIdentifier("notch.quickCapture.repeat")
            }
            .font(.system(size: 11, weight: .medium))
            .buttonStyle(.plain).frame(height: 22)
            ZStack(alignment: .topLeading) {
                TextEditor(text: $draft.text)
                    .font(.system(size: 14))
                    .scrollContentBackground(.hidden)
                    .focused($focused).disabled(!draft.canEdit)
                    .onKeyPress(.return, phases: .down) { press in
                        guard press.modifiers.intersection([.command, .control, .option, .shift]).isEmpty,
                              (NSApp.keyWindow?.firstResponder as? NSTextView)?.hasMarkedText() != true
                        else { return .ignored }
                        draft.save()
                        return .handled
                    }
                    .accessibilityIdentifier("notch.quickCapture.text")
                if draft.text.isEmpty {
                    Text(text.prompt).font(.system(size: 14)).foregroundStyle(.secondary)
                        .padding(.leading, 5).allowsHitTesting(false).accessibilityHidden(true)
                }
            }
            .frame(minHeight: 32, maxHeight: .infinity, alignment: .topLeading)
            errorMessage
            if !draft.images.isEmpty || !draft.extracts.isEmpty { attachments }
            HStack(spacing: 10) {
                Button { draft.captureRegion() } label: {
                    Label(text.region, systemImage: "viewfinder")
                }
                .disabled(!draft.canEdit).help(text.screenshot + " · ⌘R")
                .accessibilityIdentifier("notch.quickCapture.region")
                Button { draft.captureText() } label: {
                    Label(text.captureText, systemImage: "text.viewfinder")
                }
                .disabled(!draft.canEdit).help(text.textExtract + " · ⌘T")
                .accessibilityIdentifier("notch.quickCapture.ocr")
                Button { draft.undoLastScreenshot() } label: { Image(systemName: "arrow.uturn.backward") }
                    .disabled(!draft.canUndoScreenshot)
                    .help(text.undoScreenshot + " · ⌃⌘Z")
                    .accessibilityLabel(text.undoScreenshot)
                    .accessibilityIdentifier("notch.quickCapture.undo")
                Spacer(minLength: 0)
                Button(text.discard) { draft.discard() }
                    .disabled(!draft.canDiscard).help(text.discard + " · ⌘W")
                    .accessibilityIdentifier("notch.quickCapture.discard")
                Button(draft.error == .uncertain ? text.retry : text.save) { draft.save() }
                    .foregroundStyle(NotchNeonPalette.purple)
                    .disabled(!draft.canSave).help(text.save + " · ↩ · ⌘S")
                    .accessibilityIdentifier("notch.quickCapture.save")
            }
            .buttonStyle(.plain).font(.system(size: 11, weight: .medium)).frame(height: 24)
        }
        .padding(.horizontal, NotchLayout.horizontalInset)
        .padding(.top, service.geometry.safeContentTop)
        .padding(.bottom, NotchLayout.bottomInset)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(NotchQuickCaptureUndoKeys(draft: draft))
        .onAppear { draft.open(); focused = true }
        .onChange(of: draft.saving) { if !draft.saving { focused = true } }
        .popover(item: $preview) { item in previewContent(item) }
        .onExitCommand { if preview != nil { preview = nil } else { draft.hide() } }
    }

    @ViewBuilder private var meetingContext: some View {
        if let meeting = draft.meeting {
            HStack(spacing: 6) {
                if let note = meeting.note, let url = MeetingNoteStore.obsidianURL(note) {
                    Link(destination: url) {
                        Label(meeting.title, systemImage: "calendar").lineLimit(1)
                    }
                } else {
                    Label(meeting.title, systemImage: "calendar").lineLimit(1)
                }
                Spacer(minLength: 0)
                Button { draft.chooseMeeting(nil) } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain).disabled(!draft.canEdit)
                    .accessibilityLabel(text.noMeeting)
            }
            .font(.system(size: 11, weight: .medium)).foregroundStyle(NotchNeonPalette.purple)
            .frame(height: 20).accessibilityIdentifier("notch.quickCapture.meeting")
        } else if draft.needsMeetingChoice {
            Menu {
                ForEach(draft.meetingChoices, id: \.id) { meeting in
                    Button(meeting.title) { draft.chooseMeeting(meeting.id) }
                }
                Divider()
                Button(text.noMeeting) { draft.chooseMeeting(nil) }
            } label: {
                Label(text.chooseMeeting, systemImage: "calendar").lineLimit(1)
            }
            .menuStyle(.borderlessButton).font(.system(size: 11, weight: .medium))
            .fixedSize()
            .foregroundStyle(NotchNeonPalette.purple).disabled(!draft.canEdit)
            .frame(height: 20).accessibilityIdentifier("notch.quickCapture.chooseMeeting")
        }
    }

    @ViewBuilder private var errorMessage: some View {
        if let error = draft.error {
            VStack(alignment: .leading, spacing: 3) {
                Text(message(for: error)).font(.system(size: 10)).foregroundStyle(.red.opacity(0.9))
                    .fixedSize(horizontal: false, vertical: true)
                if draft.hasFailedWork || error == .meeting {
                    HStack(spacing: 12) {
                        Button(text.retry) { draft.retryFailedWork() }
                        if draft.hasFailedAttachments {
                            Button(text.removeFailed) { draft.removeFailedAttachments() }
                        }
                        if error == .meeting {
                            Button(text.noMeeting) { draft.chooseMeeting(nil) }
                        }
                    }
                    .buttonStyle(.plain).font(.system(size: 10, weight: .medium))
                    .foregroundStyle(NotchNeonPalette.purple).disabled(draft.saving || draft.publishing)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier("notch.quickCapture.error")
        }
    }

    private func message(for error: NotchQuickCaptureService.CaptureError) -> String {
        switch error {
        case .save: return text.saveFailed
        case .screenshot: return text.screenshotFailed
        case .ocr: return text.ocrFailed
        case .meeting: return text.meetingFailed
        case .uncertain: return text.saveUncertain
        }
    }

    private var attachments: some View {
        ScrollViewReader { scroll in
            ScrollView(.vertical) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                    ForEach(Array(draft.images.enumerated()), id: \.element.id) { index, attachment in
                        Button { preview = .image(attachment.id) } label: {
                            thumbnail(attachment.image,
                                      label: attachment.file?.lastPathComponent ?? String(index + 1),
                                      saved: attachment.file != nil)
                        }
                        .overlay(alignment: .topTrailing) {
                            Button { draft.removeImage(attachment.id) } label: { removeMark }
                                .disabled(!draft.canEdit).accessibilityLabel(text.remove)
                        }
                        .draggable(attachment.id.uuidString)
                        .dropDestination(for: String.self) { values, _ in
                            guard draft.canEdit, let value = values.first, let id = UUID(uuidString: value) else { return false }
                            return draft.moveImage(id, to: attachment.id)
                        }
                        .accessibilityIdentifier("notch.quickCapture.image." + attachment.id.uuidString)
                        .id(attachment.id)
                    }
                    ForEach(draft.extracts, id: \.id) { extract in
                        Button { preview = .extract(extract.id) } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(extract.text).font(.system(size: 9)).lineLimit(3)
                                    .frame(width: 78, height: 36, alignment: .topLeading).padding(5)
                                    .background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 5))
                                    .overlay(RoundedRectangle(cornerRadius: 5)
                                        .stroke(NotchNeonPalette.purple.opacity(0.2), lineWidth: 0.5))
                                Label(text.captureText, systemImage: "text.alignleft")
                                    .font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary)
                            }
                            .frame(width: 88)
                        }
                        .overlay(alignment: .topTrailing) {
                            Button { draft.removeExtract(extract.id) } label: { removeMark }
                                .disabled(!draft.canEdit).accessibilityLabel(text.remove)
                        }
                        .accessibilityLabel(text.textExtract + ": " + extract.text)
                        .accessibilityIdentifier("notch.quickCapture.extract." + extract.id.uuidString)
                        .id(extract.id)
                    }
                }
                .buttonStyle(.plain)
            }
            .scrollIndicators(.visible)
            .onChange(of: draft.images.count) {
                if let last = draft.images.last { scroll.scrollTo(last.id, anchor: .bottom) }
            }
            .onChange(of: draft.extracts.count) {
                if let last = draft.extracts.last { scroll.scrollTo(last.id, anchor: .bottom) }
            }
        }
        .frame(height: draft.error == nil ? 86 : 64)
    }

    private var removeMark: some View {
        Image(systemName: "xmark.circle.fill").symbolRenderingMode(.palette)
            .foregroundStyle(.white, .black.opacity(0.8)).padding(3)
    }

    private func thumbnail(_ image: CGImage, label: String, saved: Bool) -> some View {
        VStack(spacing: 3) {
            Image(decorative: image, scale: 1).resizable().scaledToFit()
                .frame(width: 88, height: 46)
                .background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 5))
                .clipShape(RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5).stroke(NotchNeonPalette.purple.opacity(0.2), lineWidth: 0.5))
            HStack(spacing: 3) {
                if saved { Image(systemName: "checkmark").foregroundStyle(NotchNeonPalette.purple) }
                Text(label).lineLimit(1)
            }
            .font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary)
        }
        .frame(width: 88)
    }

    private func previewContent(_ item: Preview) -> some View {
        VStack(spacing: 10) {
            HStack {
                switch item {
                case .image(let id):
                    Text(draft.images.first { $0.id == id }?.file?.lastPathComponent ?? text.screenshot)
                case .extract: Text(text.textExtract)
                }
                Spacer()
                Button { preview = nil } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain).accessibilityLabel(text.close)
            }
            .font(.system(size: 12, weight: .semibold)).foregroundStyle(NotchNeonPalette.purple)
            switch item {
            case .image(let id):
                if let attachment = draft.images.first(where: { $0.id == id }) {
                    if let file = attachment.file, let image = NSImage(contentsOf: file) {
                        Image(nsImage: image).resizable().scaledToFit()
                    } else {
                        Image(decorative: attachment.image, scale: 1).resizable().scaledToFit()
                    }
                }
            case .extract(let id):
                if draft.extracts.contains(where: { $0.id == id }) {
                    TextEditor(text: Binding(
                        get: { draft.extracts.first(where: { $0.id == id })?.text ?? "" },
                        set: { draft.updateExtract(id, text: $0) }
                    ))
                    .font(.system(size: 13)).scrollContentBackground(.hidden)
                    .focused($extractFocused).disabled(!draft.canEdit)
                    .onAppear { extractFocused = true }
                    .accessibilityIdentifier("notch.quickCapture.previewText")
                }
            }
        }
        .padding(14).frame(width: 560, height: 360)
        .background(.black.opacity(0.96)).environment(\.colorScheme, .dark)
        .background(NotchQuickCaptureUndoKeys(draft: draft, closePreview: { preview = nil }))
        .onExitCommand { preview = nil }
    }
}

/// Scope capture actions to their editor window; the service keeps native text
/// editing shortcuts and composition untouched.
struct NotchQuickCaptureUndoKeys: NSViewRepresentable {
    let draft: NotchQuickCaptureService
    var closePreview: (() -> Void)? = nil
    func makeNSView(context: Context) -> Area {
        let view = Area(); view.draft = draft; view.closePreview = closePreview; return view
    }
    func updateNSView(_ view: Area, context: Context) {
        view.draft = draft; view.closePreview = closePreview
    }
    static func dismantleNSView(_ view: Area, coordinator: ()) { view.stop() }

    final class Area: NSView {
        weak var draft: NotchQuickCaptureService?
        var closePreview: (() -> Void)?
        private var monitor: Any?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                self?.handle(event) == true ? nil : event
            }
        }
        func handle(_ event: NSEvent) -> Bool {
            guard let window, window.isVisible, !isHiddenOrHasHiddenAncestor,
                  window.attachedSheet == nil, event.window === window else { return false }
            if let closePreview {
                guard event.type == .keyDown, !event.isARepeat else { return false }
                let modifiers = event.modifierFlags.intersection([.command, .control, .option, .shift])
                if event.keyCode == 53 || (modifiers == .command && event.keyCode == 13) {
                    closePreview(); return true
                }
                if modifiers == .command && event.keyCode == 1 {
                    if let draft, draft.canSave { draft.save(); closePreview() }
                    return true
                }
                return false
            }
            return draft?.handleKey(event, selecting: false) == true
        }
        func stop() { if let monitor { NSEvent.removeMonitor(monitor) }; monitor = nil }
        deinit { stop() }
    }
}

struct NotchQuickCapturePulse: View {
    @ObservedObject var service: NotchService
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if let feedback = service.quickCaptureFeedback, service.acceptsSystemFeedback {
            TimelineView(.animation(minimumInterval: 1.0 / 24)) { context in
                let age = context.date.timeIntervalSince(feedback.began)
                let opacity = max(0, min(1, age / 0.12)) * max(0, min(1, (0.85 - age) / 0.4))
                let size = service.surfaceSize
                let shape = NotchShape.island(height: size.height, geometry: service.geometry)
                shape.stroke(feedback.success ? NotchNeonPalette.purple : .red, lineWidth: 2)
                    .mask {
                        if service.geometry.isNotched && !service.expanded {
                            HStack { Rectangle().frame(width: 24); Spacer(); Rectangle().frame(width: 24) }
                        } else {
                            VStack { Spacer(minLength: 0); Rectangle().frame(height: 14) }
                        }
                    }
                    .blur(radius: reduceMotion ? 0 : 1)
                    .clipShape(shape)
                    .opacity(opacity)
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}

/// Observe only secondary clicks over this button in this window. The view
/// itself never takes hits, so ordinary clicks and other menu bars stay native.
struct NotchObsidianRightClick: NSViewRepresentable {
    var action: () -> Void
    func makeNSView(context: Context) -> Area { let view = Area(); view.action = action; return view }
    func updateNSView(_ view: Area, context: Context) { view.action = action }
    static func dismantleNSView(_ view: Area, coordinator: ()) { view.stop() }

    final class Area: NSView {
        var action: (() -> Void)?
        private var monitor: Any?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .rightMouseDown) { [weak self] event in
                self?.handle(event) == true ? nil : event
            }
        }
        func handle(_ event: NSEvent) -> Bool {
            guard event.type == .rightMouseDown, let window, window.isVisible, event.window === window,
                  !isHiddenOrHasHiddenAncestor, bounds.contains(convert(event.locationInWindow, from: nil)) else { return false }
            action?()
            return true
        }
        func stop() { if let monitor { NSEvent.removeMonitor(monitor) }; monitor = nil }
        deinit { if let monitor { NSEvent.removeMonitor(monitor) } }
    }
}
