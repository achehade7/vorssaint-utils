// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

struct NotchAeroSpaceState {
    static let workspaces = ["1", "2", "G", "P"]
    static let flashDuration: TimeInterval = 1.32
    static let trailDuration: TimeInterval = 0.8
    static let trailFadeDuration: TimeInterval = 0.27
    static let labelFadeDuration: TimeInterval = 0.24
    private(set) var current: String?
    private(set) var previous: String?
    private(set) var flashUntil: TimeInterval = 0
    var trailUntil: TimeInterval { flashUntil - (Self.flashDuration - Self.trailDuration) }
    var labelFadeAt: TimeInterval { flashUntil - Self.labelFadeDuration }

    mutating func receive(_ data: Data, now: TimeInterval) -> Bool {
        guard let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              event["_event"] as? String == "focused-workspace-changed",
              let workspace = event["workspace"] as? String, !workspace.isEmpty,
              workspace != current else { return false }
        // The subscription's initial snapshot sets the highlight without flashing.
        flashUntil = current != nil && Self.workspaces.contains(workspace) ? now + Self.flashDuration : 0
        previous = current
        current = workspace
        return true
    }

    func showsStrip(hovered: Bool, blocked: Bool, now: TimeInterval) -> Bool {
        !blocked && current != nil && (hovered || now < flashUntil)
    }
}

/// One event stream while the island is enabled; no changes to AeroSpace's config.
final class NotchAeroSpaceService {
    static let shared = NotchAeroSpaceService()
    private(set) var state = NotchAeroSpaceState()
    var onChange: (() -> Void)?
    private let executable: URL?
    private var running = false
    private var process: Process?
    private var output: Pipe?
    private var buffer = Data()
    private var generation = 0
    private var reconnect: DispatchWorkItem?
    private var flashEnd: DispatchWorkItem?
    private var switching: Process?
    private var pendingWorkspace: String?

    init(executable: URL? = ["/opt/homebrew/bin/aerospace", "/usr/local/bin/aerospace"]
        .first(where: { FileManager.default.isExecutableFile(atPath: $0) }).map(URL.init(fileURLWithPath:))) {
        self.executable = executable
    }

    func start() {
        guard !running, executable != nil else { return }
        running = true
        connect()
    }

    func stop() {
        running = false
        generation += 1
        reconnect?.cancel(); reconnect = nil
        flashEnd?.cancel(); flashEnd = nil
        output?.fileHandleForReading.readabilityHandler = nil
        process?.terminationHandler = nil
        switching?.terminationHandler = nil
        if process?.isRunning == true { process?.terminate() }
        if switching?.isRunning == true { switching?.terminate() }
        process = nil; output = nil; switching = nil
        pendingWorkspace = nil
        buffer.removeAll()
        let wasConnected = state.current != nil
        state = NotchAeroSpaceState()
        if wasConnected { onChange?() }
    }

    private func connect() {
        guard running, process == nil, let executable else { return }
        generation += 1
        let requested = generation
        let child = Process(), pipe = Pipe()
        child.executableURL = executable
        child.arguments = ["subscribe", "focused-workspace-changed"]
        child.standardOutput = pipe
        child.standardError = FileHandle.nullDevice
        child.standardInput = FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async {
                guard let self, self.running, self.generation == requested else { return }
                self.receive(data)
            }
        }
        child.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, self.running, self.generation == requested else { return }
                self.disconnected()
            }
        }
        process = child; output = pipe
        do { try child.run() } catch { disconnected() }
    }

    private func receive(_ chunk: Data) {
        buffer.append(chunk)
        while let end = buffer.firstIndex(of: 10) {
            let line = Data(buffer[..<end])
            buffer.removeSubrange(...end)
            guard state.receive(line, now: ProcessInfo.processInfo.systemUptime) else { continue }
            flashEnd?.cancel()
            let work = DispatchWorkItem { [weak self] in self?.onChange?() }
            flashEnd = work
            DispatchQueue.main.asyncAfter(deadline: .now() + NotchAeroSpaceState.flashDuration, execute: work)
            onChange?()
        }
        if buffer.count > 65_536 { buffer.removeAll() }
    }

    private func disconnected() {
        generation += 1
        output?.fileHandleForReading.readabilityHandler = nil
        process = nil; output = nil
        switching?.terminationHandler = nil
        if switching?.isRunning == true { switching?.terminate() }
        switching = nil; pendingWorkspace = nil
        buffer.removeAll()
        flashEnd?.cancel(); flashEnd = nil
        state = NotchAeroSpaceState()
        onChange?()
        guard running else { return }
        let work = DispatchWorkItem { [weak self] in self?.connect() }
        reconnect = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: work)
    }

    func select(_ workspace: String) {
        guard NotchAeroSpaceState.workspaces.contains(workspace) else { return }
        switchWorkspace(workspace)
    }

    func togglePrevious() {
        guard let previous = state.previous else { return }
        switchWorkspace(previous)
    }

    private func switchWorkspace(_ workspace: String) {
        guard running, state.current != nil else { return }
        // A confirmed event can arrive before its command exits. Keep the
        // latest click until that child releases the lane instead of losing it.
        if switching != nil { pendingWorkspace = workspace; return }
        guard state.current != workspace else { return }
        startWorkspaceSwitch(workspace)
    }

    private func startWorkspaceSwitch(_ workspace: String) {
        guard let executable else { return }
        let requested = generation
        let child = Process()
        child.executableURL = executable
        child.arguments = ["workspace", workspace]
        child.standardInput = FileHandle.nullDevice
        child.standardOutput = FileHandle.nullDevice
        child.standardError = FileHandle.nullDevice
        child.terminationHandler = { [weak self] completed in
            DispatchQueue.main.async {
                guard let self, self.running, self.generation == requested,
                      self.switching === completed else { return }
                self.switching = nil
                let pending = self.pendingWorkspace
                self.pendingWorkspace = nil
                // The stream may still be delivering the prior confirmation,
                // so a queued target runs even if it matches the old reading.
                if let pending { self.startWorkspaceSwitch(pending) }
            }
        }
        // The event stream, rather than an optimistic click, updates the highlight.
        switching = child
        do { try child.run() } catch { switching = nil }
    }
}
