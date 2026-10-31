// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation

struct NotchWorkspaceWindow: Decodable, Identifiable {
    let id: Int
    let app: String
    let title: String
    enum CodingKeys: String, CodingKey {
        case id = "window-id", app = "app-name", title = "window-title"
    }
}

enum NotchWorkspaceWindows {
    enum Failure: Error { case unavailable, commandFailed }

    /// A one-shot query on hover. Drain stdout off the UI thread and bound the
    /// child lifetime even if AeroSpace is unresponsive.
    static func run(_ arguments: [String], executable: URL? = nil) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do { continuation.resume(returning: try runBlocking(arguments, executable: executable)) }
                catch { continuation.resume(throwing: error) }
            }
        }
    }

    /// Call only from a worker queue; the same bounded runner serves the switcher.
    static func runBlocking(_ arguments: [String], executable: URL? = nil) throws -> Data {
        let process = Process(), pipe = Pipe()
        let path = executable ?? ["/opt/homebrew/bin/aerospace", "/usr/local/bin/aerospace"]
            .first(where: { FileManager.default.isExecutableFile(atPath: $0) }).map(URL.init(fileURLWithPath:))
        guard let path else { throw Failure.unavailable }
        process.executableURL = path
        process.arguments = arguments
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        try process.run()
        let timeout = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 2, execute: timeout)
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        timeout.cancel()
        guard process.terminationStatus == 0 else { throw Failure.commandFailed }
        return data
    }

    struct FocusedSnapshot {
        let workspace: String
        let windowIDs: Set<UInt32>
    }

    static func focusedSnapshot(executable: URL? = nil) throws -> FocusedSnapshot {
        func focused() throws -> String {
            let data = try runBlocking(["list-workspaces", "--focused"], executable: executable)
            guard let name = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !name.isEmpty, !name.contains("\n") else { throw Failure.commandFailed }
            return name
        }
        struct Window: Decodable {
            let id: UInt32
            enum CodingKeys: String, CodingKey { case id = "window-id" }
        }
        let workspace = try focused()
        let data = try runBlocking(["list-windows", "--workspace", workspace, "--json"], executable: executable)
        let windows = try JSONDecoder().decode([Window].self, from: data)
        guard try focused() == workspace else { throw Failure.commandFailed }
        return .init(workspace: workspace, windowIDs: Set(windows.map(\.id)))
    }

    static func list(_ workspace: String) async throws -> [NotchWorkspaceWindow] {
        let data = try await run(["list-windows", "--workspace", workspace, "--json"])
        return try JSONDecoder().decode([NotchWorkspaceWindow].self, from: data)
    }
}
