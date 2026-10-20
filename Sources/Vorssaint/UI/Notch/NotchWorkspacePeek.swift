// SPDX-License-Identifier: GPL-3.0-or-later
import AppKit
import SwiftUI

struct NotchWorkspacePeek: View {
    let workspace: String
    let service: NotchService
    let close: () -> Void
    @State private var windows: [NotchWorkspaceWindow] = []
    @State private var message = "Loading windows…"

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("WORKSPACE " + workspace)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(NotchNeonPalette.workspace(workspace))
                Spacer()
                Button(action: close) { Image(systemName: "xmark").font(.system(size: 10, weight: .semibold)) }
                    .buttonStyle(.plain).help("Back to home")
            }
            ScrollView {
                LazyVStack(spacing: 6) {
                    if windows.isEmpty {
                        Text(message).font(.system(size: 12)).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, minHeight: 80)
                    }
                    ForEach(windows) { window in
                        Button {
                            service.perform {
                                Task {
                                    do { _ = try await NotchWorkspaceWindows.run(["focus", "--window-id", String(window.id)]) }
                                    catch { NSSound.beep() }
                                }
                            }
                        } label: {
                            HStack(spacing: 10) {
                                if let icon = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == window.app })?.icon {
                                    Image(nsImage: icon).resizable().scaledToFit().frame(width: 24, height: 24)
                                } else {
                                    Image(systemName: "macwindow").frame(width: 24, height: 24)
                                }
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(window.app).font(.system(size: 11, weight: .semibold))
                                    Text(window.title.isEmpty ? window.app : window.title)
                                        .font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "arrow.up.right").font(.system(size: 10))
                                    .foregroundStyle(NotchNeonPalette.workspace(workspace))
                            }
                            .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                            .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 10))
                        }.buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(.horizontal, 4)
        .task(id: workspace) {
            windows = []; message = "Loading windows…"
            do {
                let result = try await NotchWorkspaceWindows.list(workspace)
                guard !Task.isCancelled else { return }
                windows = result; message = "No windows here"
            } catch {
                guard !Task.isCancelled else { return }
                message = "AeroSpace is unavailable"
            }
        }
    }
}
