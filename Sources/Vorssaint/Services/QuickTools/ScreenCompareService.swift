// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Ephemeral image comparison. Captures and loaded images remain in memory;
/// neither the clipboard, screenshot inbox nor source files are modified.
final class ScreenCompareService: NSObject, NSWindowDelegate {
    static let shared = ScreenCompareService()
    private var panel: ScreenComparePanel?
    private var canvas: ScreenCompareCanvas?
    private var beforeSource: ScreenCompareSourceView?
    private var afterSource: ScreenCompareSourceView?
    private var summary: NSTextField?
    private var mode: NSSegmentedControl?
    private var wipe: NSSlider?
    private var tolerance: NSSlider?
    private var toleranceValue: NSTextField?
    private var before: CGImage?, after: CGImage?
    private var beforeName = "", afterName = ""
    private var region: RecorderSupport.Region?
    private var sourceScreenFrame: CGRect?
    private var selection: ScreenshotSelectionController?
    private var captureTask: Task<Void, Never>?
    private var calculation: Task<Void, Never>?
    private var analysisWork: Task<ScreenCompareModel.Analysis, Error>?
    private var overlayWork: Task<ScreenCompareModel.Overlay, Error>?
    private var beforeLoad: Task<Void, Never>?, afterLoad: Task<Void, Never>?
    private var beforeLoadWork: Task<CGImage, Error>?, afterLoadWork: Task<CGImage, Error>?
    private var generation = 0
    private var captureGeneration = 0
    private var beforeLoadGeneration = 0, afterLoadGeneration = 0
    private var analysis: ScreenCompareModel.Analysis?
    private var result: ScreenCompareModel.Overlay?
    private var isComparing = false
    private var errorMessage: String?
    private let pendingPresentationID = UUID()
    private var shownInIsland = false
    private var strings: ScreenCompareStrings { .localized(L10n.shared.language) }
    private var diffStrings: ClipboardDiffStrings { .localized(L10n.shared.language) }

    var hasPendingCapture: Bool { region != nil && before != nil && after == nil && captureTask == nil }

    private var protectedWindowIDs: Set<CGWindowID> {
        var ids = NotchService.shared.protectedWindowIDs
        ids.formUnion(selection?.protectedWindowIDs ?? [])
        if let number = panel?.windowNumber, number > 0 { ids.insert(CGWindowID(number)) }
        return ids
    }

    func show() {
        guard AppFeature.screenshot.isAvailable else { return }
        if panel == nil { makePanel() }
        refresh()
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func makePanel() {
        let panel = ScreenComparePanel(contentRect: NSRect(x: 0, y: 0, width: 960, height: 650),
            styleMask: [.titled, .closable, .resizable, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.title = strings[.title]
        panel.isReleasedWhenClosed = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.minSize = NSSize(width: 660, height: 420)
        panel.delegate = self
        let content = ScreenCompareBackground()
        let beforeSource = ScreenCompareSourceView(title: diffStrings.before, captureTitle: strings[.captureBefore],
            openTitle: strings[.openImage], accent: .systemOrange)
        let afterSource = ScreenCompareSourceView(title: diffStrings.after, captureTitle: strings[.captureAfter],
            openTitle: strings[.openImage], accent: .systemBlue)
        beforeSource.capture.target = self; beforeSource.capture.action = #selector(captureBefore)
        afterSource.capture.target = self; afterSource.capture.action = #selector(captureAfter)
        beforeSource.open.target = self; beforeSource.open.action = #selector(openBefore)
        afterSource.open.target = self; afterSource.open.action = #selector(openAfter)
        beforeSource.capture.identifier = .init("screenCompare.captureBefore")
        afterSource.capture.identifier = .init("screenCompare.captureAfter")
        beforeSource.open.identifier = .init("screenCompare.openBefore")
        afterSource.open.identifier = .init("screenCompare.openAfter")
        beforeSource.onDrop = { [weak self] in self?.loadImage($0, isBefore: true) }
        afterSource.onDrop = { [weak self] in self?.loadImage($0, isBefore: false) }
        beforeSource.toolTip = strings[.dropHint]; afterSource.toolTip = strings[.dropHint]
        let sourceRow = NSStackView(views: [beforeSource, afterSource])
        sourceRow.orientation = .horizontal; sourceRow.spacing = 0; sourceRow.distribution = .fillEqually
        let canvas = ScreenCompareCanvas()
        canvas.identifier = .init("screenCompare.canvas")
        canvas.beforeTitle = diffStrings.before; canvas.afterTitle = diffStrings.after
        canvas.placeholder = strings[.empty]
        canvas.onFractionChanged = { [weak self] fraction in self?.wipe?.doubleValue = fraction }
        let mode = NSSegmentedControl(labels: [strings[.wipe], strings[.differences]], trackingMode: .selectOne,
            target: self, action: #selector(modeChanged))
        mode.selectedSegment = 0; mode.controlSize = .small
        mode.identifier = .init("screenCompare.mode")
        let wipe = NSSlider(value: 0.5, minValue: 0, maxValue: 1, target: self, action: #selector(wipeChanged))
        wipe.controlSize = .small
        wipe.identifier = .init("screenCompare.wipe")
        wipe.setAccessibilityLabel(strings[.wipe])
        let tolerance = NSSlider(value: 0, minValue: 0, maxValue: 255, target: self, action: #selector(toleranceChanged))
        tolerance.controlSize = .small; tolerance.identifier = .init("screenCompare.tolerance")
        tolerance.toolTip = strings[.toleranceHint]; tolerance.setAccessibilityLabel(strings[.tolerance])
        let toleranceLabel = NSTextField(labelWithString: strings[.tolerance])
        toleranceLabel.font = .systemFont(ofSize: 11); toleranceLabel.textColor = .secondaryLabelColor
        let toleranceValue = NSTextField(labelWithString: "0")
        toleranceValue.font = .monospacedDigitSystemFont(ofSize: 10, weight: .medium)
        toleranceValue.alignment = .right
        let clear = NSButton(image: NSImage(systemSymbolName: "arrow.counterclockwise", accessibilityDescription: strings[.clear])!,
            target: self, action: #selector(clear))
        clear.bezelStyle = .texturedRounded; clear.controlSize = .small
        clear.toolTip = strings[.clear]; clear.setAccessibilityLabel(strings[.clear])
        clear.identifier = .init("screenCompare.clear")
        let controls = NSStackView(views: [mode, wipe, toleranceLabel, tolerance, toleranceValue, clear])
        controls.orientation = .horizontal; controls.spacing = 10; controls.alignment = .centerY
        let summary = NSTextField(wrappingLabelWithString: strings[.empty])
        summary.font = .systemFont(ofSize: 11)
        summary.textColor = .secondaryLabelColor
        summary.maximumNumberOfLines = 2
        summary.identifier = .init("screenCompare.summary")
        for view in [sourceRow, canvas, controls, summary] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            sourceRow.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 6),
            sourceRow.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -6),
            sourceRow.topAnchor.constraint(equalTo: content.topAnchor),
            canvas.topAnchor.constraint(equalTo: sourceRow.bottomAnchor),
            canvas.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            canvas.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            canvas.bottomAnchor.constraint(equalTo: controls.topAnchor, constant: -14),
            controls.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 18),
            controls.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -18),
            controls.bottomAnchor.constraint(equalTo: summary.topAnchor, constant: -10),
            wipe.widthAnchor.constraint(greaterThanOrEqualToConstant: 70),
            tolerance.widthAnchor.constraint(equalToConstant: 100),
            toleranceValue.widthAnchor.constraint(equalToConstant: 24),
            summary.leadingAnchor.constraint(equalTo: controls.leadingAnchor),
            summary.trailingAnchor.constraint(equalTo: controls.trailingAnchor),
            summary.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
            summary.heightAnchor.constraint(equalToConstant: 30),
        ])
        panel.contentView = content; panel.center()
        self.panel = panel; self.canvas = canvas
        self.beforeSource = beforeSource; self.afterSource = afterSource
        self.mode = mode; self.wipe = wipe; self.tolerance = tolerance
        self.toleranceValue = toleranceValue; self.summary = summary
        refresh()
    }

    @objc func captureBefore() {
        guard AppFeature.screenshot.isAvailable else { return }
        show()
        guard canCapture() else { return }
        cancelPendingCapture()
        panel?.orderOut(nil)
        let controller = ScreenshotSelectionController(freeze: false, includePointer: false,
            showLastRegion: false, hideVorssaintWindows: false,
            protectedWindowIDs: { [weak self] in self?.protectedWindowIDs ?? [] }, purpose: strings[.captureBefore],
            mode: .geometry, requiresDraggedRegion: true)
        selection = controller
        controller.begin { [weak self] outcome in
            guard let self else { return }
            self.selection = nil
            switch outcome {
            case .region(let region):
                guard let screen = NSScreen.screens.first(where: { $0.displayID == region.displayID }) else {
                    self.fail(self.strings[.displayChanged]); self.show(); return
                }
                self.region = region; self.sourceScreenFrame = screen.frame
                self.capture(region, isBefore: true)
            case .failed: self.fail(self.strings[.captureFailed]); self.show()
            default: self.show()
            }
        }
    }

    @objc func captureAfter() {
        guard AppFeature.screenshot.isAvailable, let region else { return }
        guard canCapture() else { show(); return }
        guard let screen = NSScreen.screens.first(where: { $0.displayID == region.displayID }),
              screen.frame == sourceScreenFrame, screen.backingScaleFactor == region.scale,
              CGRect(origin: .zero, size: CGSize(width: screen.frame.width * region.scale,
                height: screen.frame.height * region.scale)).contains(region.pixelRect)
        else { cancelPendingCapture(); fail(strings[.displayChanged]); show(); return }
        panel?.orderOut(nil)
        capture(region, isBefore: false)
    }

    private func canCapture() -> Bool {
        guard captureTask == nil, !ScreenshotSelectionController.isSessionOnScreen else { fail(strings[.busy]); return false }
        Permissions.shared.refresh()
        guard Permissions.shared.screenRecording else {
            Permissions.shared.requestScreenRecording()
            fail(strings[.permission]); return false
        }
        return true
    }

    private func capture(_ region: RecorderSupport.Region, isBefore: Bool) {
        guard ScreenCompareModel.validSize(width: Int(region.pixelRect.width), height: Int(region.pixelRect.height)) else {
            cancelPendingCapture(); fail(strings[.tooLarge]); show(); return
        }
        cancelLoads()
        captureGeneration += 1
        let revision = captureGeneration
        errorMessage = nil
        captureTask = Task { @MainActor [weak self] in
            guard let self else { return }
            // Let the comparison and region-selection surfaces leave the
            // compositor before sampling. The island is excluded explicitly.
            try? await Task.sleep(nanoseconds: 160_000_000)
            guard !Task.isCancelled, revision == self.captureGeneration else { return }
            let prepared = await ScreenshotCaptureEngine.prepareDisplayRegion(displayID: region.displayID,
                pixelRect: region.pixelRect, includePointer: false, hideVorssaintWindows: false,
                protectedWindowIDs: self.protectedWindowIDs, keepsIslandOut: true)
            let image = await prepared?.image()
            guard !Task.isCancelled, revision == self.captureGeneration, AppFeature.screenshot.isAvailable else { return }
            self.captureTask = nil
            if let image, image.width == Int(region.pixelRect.width), image.height == Int(region.pixelRect.height) {
                if isBefore { self.after = nil; self.afterName = "" }
                self.accept(image, name: "\(image.width) × \(image.height)", isBefore: isBefore)
            } else {
                if isBefore { self.cancelPendingCapture() }
                self.fail(self.strings[.captureFailed])
            }
            if !self.shownInIsland { self.show() }
            self.notify()
        }
        refresh(); notify()
    }

    func cancelPendingCapture() {
        cancelCapture()
        region = nil; sourceScreenFrame = nil
        refresh(); notify()
    }

    private func cancelCapture() {
        captureGeneration += 1
        captureTask?.cancel(); captureTask = nil
    }

    @objc private func openBefore() { chooseImage(isBefore: true) }
    @objc private func openAfter() { chooseImage(isBefore: false) }
    private func chooseImage(isBefore: Bool) {
        guard AppFeature.screenshot.isAvailable, let panel else { return }
        let picker = NSOpenPanel()
        picker.allowedContentTypes = [.png, .jpeg, .tiff, .heic]
        picker.allowsMultipleSelection = false; picker.canChooseDirectories = false
        picker.beginSheetModal(for: panel) { [weak self] response in
            guard response == .OK, let url = picker.url else { return }
            self?.loadImage(url, isBefore: isBefore)
        }
    }

    func loadImage(_ url: URL, isBefore: Bool) {
        guard AppFeature.screenshot.isAvailable else { return }
        show()
        if isBefore {
            beforeLoadGeneration += 1; beforeLoad?.cancel(); beforeLoadWork?.cancel()
            cancelPendingCapture()
        } else {
            afterLoadGeneration += 1; afterLoad?.cancel(); afterLoadWork?.cancel()
            // Import is the newer explicit source selection. Keep the Before
            // region available for another deliberate recapture, but never let
            // a capture already in flight replace the chosen file afterwards.
            cancelCapture()
        }
        let revision = isBefore ? beforeLoadGeneration : afterLoadGeneration
        let worker = Task.detached(priority: .userInitiated) { try ScreenCompareModel.load(url) }
        if isBefore { beforeLoadWork = worker } else { afterLoadWork = worker }
        errorMessage = nil
        let operation = Task { @MainActor [weak self] in
            do {
                let image = try await worker.value
                guard let self, !Task.isCancelled, AppFeature.screenshot.isAvailable,
                      revision == (isBefore ? self.beforeLoadGeneration : self.afterLoadGeneration) else { return }
                if isBefore { self.beforeLoad = nil; self.beforeLoadWork = nil }
                else { self.afterLoad = nil; self.afterLoadWork = nil }
                self.accept(image, name: url.lastPathComponent, isBefore: isBefore)
            } catch {
                guard let self, !Task.isCancelled,
                      revision == (isBefore ? self.beforeLoadGeneration : self.afterLoadGeneration) else { return }
                if isBefore { self.beforeLoad = nil; self.beforeLoadWork = nil }
                else { self.afterLoad = nil; self.afterLoadWork = nil }
                self.fail(self.message(for: error))
            }
        }
        if isBefore { beforeLoad = operation } else { afterLoad = operation }
        refresh()
    }

    private func accept(_ image: CGImage, name: String, isBefore: Bool) {
        guard ScreenCompareModel.validSize(width: image.width, height: image.height) else { fail(strings[.tooLarge]); return }
        if isBefore { before = image; beforeName = name } else { after = image; afterName = name }
        errorMessage = nil
        analyze(); notify()
    }

    private func cancelComparison() {
        generation += 1
        calculation?.cancel(); analysisWork?.cancel(); overlayWork?.cancel()
        calculation = nil; analysisWork = nil; overlayWork = nil
        isComparing = false
    }

    private func analyze() {
        cancelComparison()
        analysis = nil; result = nil; canvas?.overlay = nil
        guard let before, let after else { refresh(); return }
        guard before.width == after.width, before.height == after.height else { fail(strings[.sizeMismatch]); return }
        let revision = generation
        let worker = Task.detached(priority: .userInitiated) { try ScreenCompareModel.analyze(before: before, after: after) }
        analysisWork = worker; isComparing = true
        calculation = Task { @MainActor [weak self] in
            do {
                let analysis = try await worker.value
                guard let self, !Task.isCancelled, revision == self.generation else { return }
                self.analysis = analysis; self.renderOverlay()
            } catch {
                guard let self, !Task.isCancelled, revision == self.generation else { return }
                self.isComparing = false; self.fail(self.message(for: error))
            }
        }
        refresh()
    }

    private func renderOverlay() {
        cancelComparison()
        guard let analysis else { refresh(); return }
        let revision = generation, threshold = tolerance?.integerValue ?? 0
        result = nil; canvas?.overlay = nil; isComparing = true
        let worker = Task.detached(priority: .userInitiated) { try analysis.overlay(tolerance: threshold) }
        overlayWork = worker
        calculation = Task { @MainActor [weak self] in
            do {
                let overlay = try await worker.value
                guard let self, !Task.isCancelled, revision == self.generation else { return }
                self.result = overlay; self.isComparing = false
                self.canvas?.overlay = overlay.image
                self.refresh()
            } catch {
                guard let self, !Task.isCancelled, revision == self.generation else { return }
                self.isComparing = false; self.fail(self.message(for: error))
            }
        }
        refresh()
    }

    @objc private func modeChanged() { refresh() }
    @objc private func wipeChanged() { canvas?.fraction = wipe?.doubleValue ?? 0.5 }
    @objc private func toleranceChanged() {
        tolerance?.doubleValue = Double(tolerance?.integerValue ?? 0)
        renderOverlay()
    }
    @objc func clear() {
        cancelLoads()
        cancelPendingCapture(); cancelComparison()
        before = nil; after = nil; beforeName = ""; afterName = ""
        analysis = nil; result = nil; errorMessage = nil
        canvas?.overlay = nil; canvas?.fraction = 0.5; wipe?.doubleValue = 0.5
        tolerance?.doubleValue = 0; mode?.selectedSegment = 0
        refresh(); notify()
    }

    private func cancelLoads() {
        beforeLoadGeneration += 1; afterLoadGeneration += 1
        beforeLoad?.cancel(); afterLoad?.cancel(); beforeLoadWork?.cancel(); afterLoadWork?.cancel()
        beforeLoad = nil; afterLoad = nil; beforeLoadWork = nil; afterLoadWork = nil
    }

    private func fail(_ message: String) { errorMessage = message; refresh() }
    private func message(for error: Error) -> String {
        switch error as? ScreenCompareModel.Failure {
        case .tooLarge: return strings[.tooLarge]
        case .sizeMismatch: return strings[.sizeMismatch]
        default: return strings[.invalidImage]
        }
    }
    private func notify() {
        guard hasPendingCapture, AppFeature.screenshot.isAvailable else {
            if shownInIsland { shownInIsland = false; NotchService.shared.removeCapture(id: pendingPresentationID) }
            return
        }
        guard !shownInIsland, let before else { return }
        let view = ScreenComparePendingView(image: NSImage(cgImage: before, size: .zero),
            title: strings[.title], hint: strings[.pending], captureTitle: strings[.captureAfter],
            cancelTitle: strings[.cancel], capture: { [weak self] in self?.captureAfter() },
            cancel: { [weak self] in self?.cancelPendingCapture() })
        shownInIsland = NotchService.shared.presentCapture(id: pendingPresentationID, content: AnyView(view),
            height: 126, takeFocus: false, closeOnCollapse: false,
            fallback: { [weak self] in self?.shownInIsland = false; self?.show() },
            close: { [weak self] in self?.cancelPendingCapture() }, hover: { _ in })
        if shownInIsland { panel?.orderOut(nil) }
    }

    private func refresh() {
        canvas?.before = before; canvas?.after = after
        canvas?.showsDifferences = mode?.selectedSegment == 1
        let ready = analysis != nil && before != nil && after != nil
        mode?.isEnabled = ready
        wipe?.isEnabled = ready && mode?.selectedSegment == 0
        tolerance?.isEnabled = ready && mode?.selectedSegment == 1
        toleranceValue?.stringValue = String(tolerance?.integerValue ?? 0)
        beforeSource?.detail.stringValue = before.map { "\($0.width) × \($0.height)" } ?? "—"
        afterSource?.detail.stringValue = after.map { "\($0.width) × \($0.height)" } ?? "—"
        beforeSource?.detail.toolTip = beforeName; afterSource?.detail.toolTip = afterName
        beforeSource?.capture.isEnabled = captureTask == nil
        afterSource?.capture.isEnabled = region != nil && before != nil && captureTask == nil
        summary?.textColor = errorMessage == nil ? .secondaryLabelColor : .labelColor
        summary?.font = .systemFont(ofSize: 11, weight: errorMessage == nil ? .regular : .medium)
        if let errorMessage { summary?.stringValue = errorMessage }
        else if isComparing || captureTask != nil || beforeLoad != nil || afterLoad != nil { summary?.stringValue = diffStrings.loading }
        else if let result {
            summary?.stringValue = result.changedPixels == 0
                ? ((tolerance?.integerValue ?? 0) == 0 ? diffStrings.identical : strings[.noPixels])
                : String(format: strings[.changed], result.changedPixels, result.percentage)
        } else { summary?.stringValue = hasPendingCapture ? strings[.pending] : strings[.empty] }
        if let canvas { panel?.invalidateCursorRects(for: canvas) }
    }

    func windowWillClose(_ notification: Notification) {
        // Keep a pending Before capture available to the island's explicit
        // Capture After action. Completed comparisons live only this session.
        if !hasPendingCapture { clear() }
        notify()
    }
}
