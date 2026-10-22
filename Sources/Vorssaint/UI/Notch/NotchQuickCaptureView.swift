// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

struct NotchQuickCaptureView: View {
    let service: NotchService
    @ObservedObject var draft = NotchQuickCaptureService.shared
    @ObservedObject private var l10n = L10n.shared
    @FocusState private var focused: Bool
    @State private var preview: NotchQuickCaptureService.Attachment?
    private var text: NotchQuickCaptureStrings { .localized(l10n.language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(text.title).foregroundStyle(NotchNeonPalette.purple)
                Spacer()
                Text("⌃⌥⌘O").foregroundStyle(.secondary)
            }
            .font(.system(size: 11, weight: .semibold))
            HStack(spacing: 8) {
                if let session = draft.session {
                    Label(String(format: text.sessionCount, session.count), systemImage: "record.circle")
                        .foregroundStyle(NotchNeonPalette.purple)
                        .fixedSize()
                    if !session.label.isEmpty {
                        Text(session.label).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    if draft.canUndoScreenshot {
                        Button { draft.undoLastScreenshot() } label: { Image(systemName: "arrow.uturn.backward") }
                            .help(text.undoScreenshot + " · ⌘Z")
                            .accessibilityLabel(text.undoScreenshot)
                            .accessibilityIdentifier("notch.quickCapture.undo")
                    }
                    Button(text.startSession) { draft.captureGroup() }
                        .fixedSize()
                        .accessibilityIdentifier("notch.quickCapture.resumeSession")
                        .foregroundStyle(NotchNeonPalette.purple)
                    Button(text.stopSession) { draft.stopSession() }
                        .accessibilityIdentifier("notch.quickCapture.stopSession")
                } else {
                    TextField(text.labelPrompt, text: $draft.sessionLabel)
                        .textFieldStyle(.plain)
                        .accessibilityIdentifier("notch.quickCapture.sessionLabel")
                    Button(text.startSession) { draft.captureGroup() }
                        .foregroundStyle(NotchNeonPalette.purple)
                        .fixedSize()
                        .accessibilityIdentifier("notch.quickCapture.startSession")
                }
            }
            .font(.system(size: 11, weight: .medium))
            .buttonStyle(.plain)
            .disabled(draft.saving)
            .frame(height: 22)
            ZStack(alignment: .topLeading) {
                TextEditor(text: $draft.text)
                    .font(.system(size: 14))
                    .scrollContentBackground(.hidden)
                    .focused($focused)
                    .disabled(draft.saving)
                    .onKeyPress(.return, phases: .down) { press in
                        guard press.modifiers.intersection([.command, .control, .option, .shift]).isEmpty,
                              (NSApp.keyWindow?.firstResponder as? NSTextView)?.hasMarkedText() != true
                        else { return .ignored }
                        draft.save()
                        return .handled
                    }
                    .accessibilityIdentifier("notch.quickCapture.text")
                if draft.text.isEmpty {
                    Text(text.prompt)
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                        .padding(.leading, 5)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            if let error = draft.error {
                Text(error == .save ? text.saveFailed : text.screenshotFailed)
                    .font(.system(size: 10))
                    .foregroundStyle(.red.opacity(0.9))
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if !draft.images.isEmpty || draft.pendingSessionImage != nil {
                ScrollViewReader { scroll in
                    ScrollView(.vertical) {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                            ForEach(Array(draft.images.enumerated()), id: \.element.id) { index, attachment in
                                Button { preview = attachment } label: {
                                    thumbnail(attachment.image, label: attachment.file?.lastPathComponent ?? String(index + 1),
                                              saved: attachment.file != nil)
                                }
                                .overlay(alignment: .topTrailing) {
                                    if attachment.file == nil {
                                        Button { draft.removeImage(attachment.id) } label: {
                                            Image(systemName: "xmark.circle.fill")
                                                .symbolRenderingMode(.palette)
                                                .foregroundStyle(.white, .black.opacity(0.8)).padding(3)
                                        }
                                        .accessibilityLabel(text.cancel)
                                    }
                                }
                                .draggable(attachment.id.uuidString)
                                .dropDestination(for: String.self) { values, _ in
                                    guard let value = values.first, let id = UUID(uuidString: value) else { return false }
                                    return draft.moveImage(id, to: attachment.id)
                                }
                                .disabled(draft.saving)
                                .id(attachment.id)
                            }
                            if let image = draft.pendingSessionImage {
                                thumbnail(image, label: text.retryScreenshot, saved: false)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    .scrollIndicators(.visible)
                    .onChange(of: draft.images.count) {
                        if let last = draft.images.last { scroll.scrollTo(last.id, anchor: .bottom) }
                    }
                }
                .frame(height: 100)
            }
            HStack(spacing: 12) {
                Button { if draft.session != nil { draft.captureGroup() } else { draft.captureRegion() } } label: {
                    Label(draft.pendingSessionImage == nil ? text.screenshot : text.retryScreenshot, systemImage: "viewfinder")
                }
                .disabled(draft.saving)
                Spacer(minLength: 0)
                if draft.saving { ProgressView().controlSize(.mini) }
                Button(text.cancel) { draft.cancel() }.disabled(draft.saving)
                Button(text.save) { draft.save() }
                    .foregroundStyle(NotchNeonPalette.purple)
                    .disabled(!draft.canSave)
            }
            .buttonStyle(.plain)
            .font(.system(size: 11, weight: .medium))
            .frame(height: 24)
        }
        .padding(.horizontal, NotchLayout.horizontalInset)
        .padding(.top, service.geometry.safeContentTop)
        .padding(.bottom, NotchLayout.bottomInset)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .onAppear { focused = true }
        .onChange(of: draft.saving) { if !draft.saving { focused = true } }
        .popover(item: $preview) { attachment in
            VStack(spacing: 10) {
                HStack {
                    Text(attachment.file?.lastPathComponent ?? text.screenshot)
                        .foregroundStyle(NotchNeonPalette.purple)
                    Spacer()
                    Button { preview = nil } label: { Image(systemName: "xmark") }
                        .buttonStyle(.plain).accessibilityLabel(text.cancel)
                }
                .font(.system(size: 12, weight: .semibold))
                if let file = attachment.file, let image = NSImage(contentsOf: file) {
                    Image(nsImage: image).resizable().scaledToFit()
                } else {
                    Image(decorative: attachment.image, scale: 1).resizable().scaledToFit()
                }
            }
            .padding(14).frame(width: 560, height: 360)
            .background(.black.opacity(0.96)).environment(\.colorScheme, .dark)
            .onExitCommand { preview = nil }
        }
        .onExitCommand { if preview != nil { preview = nil } else { draft.cancel() } }
        .accessibilityIdentifier("notch.quickCapture")
    }

    private func thumbnail(_ image: CGImage, label: String, saved: Bool) -> some View {
        VStack(spacing: 3) {
            Image(decorative: image, scale: 1).resizable().scaledToFit()
                .frame(width: 88, height: 52)
                .background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 5))
                .clipShape(RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5).stroke(NotchNeonPalette.purple.opacity(0.2), lineWidth: 0.5))
            HStack(spacing: 3) {
                if saved { Image(systemName: "checkmark").foregroundStyle(NotchNeonPalette.purple) }
                Text(label).lineLimit(1)
            }
            .font(.system(size: 9, weight: .medium))
            .foregroundStyle(.secondary)
        }
        .frame(width: 88)
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
