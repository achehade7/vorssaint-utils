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
                let process = Process(), pipe = Pipe()
                let path = executable ?? ["/opt/homebrew/bin/aerospace", "/usr/local/bin/aerospace"]
                    .first(where: { FileManager.default.isExecutableFile(atPath: $0) }).map(URL.init(fileURLWithPath:))
                guard let path else { continuation.resume(throwing: Failure.unavailable); return }
                process.executableURL = path
                process.arguments = arguments
                process.standardOutput = pipe
                process.standardError = FileHandle.nullDevice
                process.standardInput = FileHandle.nullDevice
                do { try process.run() }
                catch { continuation.resume(throwing: error); return }
                let timeout = DispatchWorkItem { if process.isRunning { process.terminate() } }
                DispatchQueue.global().asyncAfter(deadline: .now() + 2, execute: timeout)
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                timeout.cancel()
                if process.terminationStatus == 0 { continuation.resume(returning: data) }
                else { continuation.resume(throwing: Failure.commandFailed) }
            }
        }
    }

    static func list(_ workspace: String) async throws -> [NotchWorkspaceWindow] {
        let data = try await run(["list-windows", "--workspace", workspace, "--json"])
        return try JSONDecoder().decode([NotchWorkspaceWindow].self, from: data)
    }
}
