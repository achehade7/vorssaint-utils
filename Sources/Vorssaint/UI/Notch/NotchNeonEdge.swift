// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// A narrow light along the island's lower edge. Its clock exists only while
/// something is active; the camera and the rest of the surface stay black.
enum NotchNeonPalette {
    static var blue: Color {
        let night = NotchService.shared.nightPalette
        return Color(red: 0.486 + 0.126 * night, green: 0.60 - 0.098 * night, blue: 1)
    }
    static var purple: Color {
        let night = NotchService.shared.nightPalette
        return Color(red: 0.72 + 0.123 * night, green: 0.53 - 0.075 * night, blue: 1)
    }
    static let amber = Color(red: 1, green: 0.573, blue: 0.188)
    static func workspace(_ name: String?) -> Color {
        switch name {
        case "1": blue
        case "G": amber
        case "P": Color(red: 0.95, green: 0.42, blue: 0.73)
        default: purple
        }
    }
}

struct NotchNeonEdge: View, Animatable {
    @ObservedObject var service: NotchService
    static let drop: CGFloat = 2
    var surfaceSize: CGSize
    var contour: Path? = nil
    var pointerX: CGFloat?
    @ObservedObject private var music = NotchMusicService.shared
    @ObservedObject private var agents = AgentUsageService.shared
    @ObservedObject private var downloads = NotchDownloadService.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private enum Signature: Equatable {
        case agent, agentFinished(AgentProvider), message, wake, charge, handoff, terminalSuccess, terminalFailure

        var completionProvider: AgentProvider? {
            if case .agentFinished(let provider) = self { return provider }
            return nil
        }
    }
    @State private var signature: Signature = .agent
    @State private var signalAt: Date?
    @State private var workspaceAt: Date?
    @State private var lastPointerX: CGFloat = 0.5
    private var blue: Color { NotchNeonPalette.blue }
    private var purple: Color { NotchNeonPalette.purple }

    // Rebuild the stroked path through the workspace surface's contraction.
    var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { AnimatablePair(surfaceSize.width, surfaceSize.height) }
        set { surfaceSize = CGSize(width: newValue.first, height: newValue.second) }
    }

    private var signalDuration: TimeInterval {
        if signature.completionProvider != nil { return 3.2 }
        return signature == .wake ? 0.9 : 1.2
    }
    private var working: Bool { !agents.snapshot.live.isEmpty }
    private var playing: Bool { music.playback?.isPlaying == true }
    private var animated: Bool { signalAt != nil || workspaceAt != nil }

    var body: some View {
        Group {
            if animated && !reduceMotion {
                TimelineView(.animation(minimumInterval: 1.0 / 24)) { context in
                    edge(at: context.date)
                }
            } else {
                edge(at: Date())
            }
        }
        .onChange(of: pointerX, initial: true) { _, x in
            if let x { lastPointerX = x }
        }
        .onReceive(agents.completions) { provider in
            signal(.agentFinished(provider))
        }
        .onChange(of: working) { _, active in
            if active { signal(.agent) }
        }
        .onChange(of: service.notice) { _, notice in
            guard let notice else { return }
            if notice.audioHandoff { signal(.handoff) }
            else if let status = notice.terminalStatus { signal(status == 0 ? .terminalSuccess : .terminalFailure) }
            else if notice.event == .agents || ["codex", "claude", "claude code"].contains(notice.notification?.app.lowercased() ?? "") {
                signal(.agent)
            } else if notice.event == .systemNotification { signal(.message) }
        }
        .onChange(of: service.neonChargeAt) { _, date in
            if let date { signal(.charge, at: date) }
        }
        .onChange(of: service.neonWakeAt, initial: true) { _, date in
            if let date, Date().timeIntervalSince(date) < 0.9 { signal(.wake, at: date) }
        }
        .onChange(of: NotchAeroSpaceService.shared.state.flashUntil, initial: true) { _, deadline in
            let remaining = deadline - ProcessInfo.processInfo.systemUptime
            guard remaining > 0 else { return }
            // Anchor the light to the confirmed workspace switch time.
            workspaceAt = Date(timeIntervalSinceNow: remaining - NotchAeroSpaceState.flashDuration)
        }
        .task(id: workspaceAt) {
            guard let began = workspaceAt else { return }
            let remaining = max(0, 1.1 - Date().timeIntervalSince(began))
            do { try await Task.sleep(for: .seconds(remaining)) } catch { return }
            workspaceAt = nil
        }
        .task(id: signalAt) {
            guard let began = signalAt else { return }
            do { try await Task.sleep(for: .seconds(max(0, signalDuration - Date().timeIntervalSince(began)))) } catch { return }
            signalAt = nil
        }
    }

    private func signal(_ kind: Signature, at date: Date = Date()) {
        // Let a completion finish its sweep and fade even when another notice
        // arrives. A second agent finishing can still start its own signal.
        if kind.completionProvider == nil, signature.completionProvider != nil,
           let signalAt, date.timeIntervalSince(signalAt) < signalDuration { return }
        signature = kind
        signalAt = date
    }

    private func edge(at date: Date) -> some View {
        let shape = contour ?? NotchShape.island(height: surfaceSize.height, geometry: service.geometry)
            .path(in: CGRect(origin: .zero, size: surfaceSize))
        let age = signalAt.map { max(0, date.timeIntervalSince($0)) }
        let workspace = age == nil ? workspaceAt.map { max(0, date.timeIntervalSince($0)) } : nil
        let workspaceName = NotchAeroSpaceService.shared.state.current
        let idle = !working && !playing && age == nil && workspace == nil
        let completion = age != nil ? signature.completionProvider : nil
        let steadyTint = working ? blue : playing ? music.artworkTint?.color ?? purple : purple
        let tint = completion?.tint ?? (age != nil ? (signature == .agent || signature == .terminalSuccess ? blue
                : signature == .terminalFailure ? Color(red: 0.95, green: 0.35, blue: 0.77) : purple)
            : workspace != nil ? NotchNeonPalette.workspace(workspaceName)
            : steadyTint)
        let phase = reduceMotion ? 0.5 : age.map { min(1, $0 / (completion != nil ? 1.35 : 0.7)) }
            ?? workspace.map { min(1, $0 / 0.65) } ?? 0.5
        let peak = max(0.01, min(0.99, phase))
        let ripple = completion != nil || (workspace != nil && workspaceName == "P")
            || (age != nil && signature == .handoff)
        let sweeps = (workspace != nil && workspaceName != "2")
            || (age != nil && [.agent, .charge, .terminalSuccess, .terminalFailure].contains(signature))
        let rippleRadius = max(0.02, phase * 0.48)
        let rippleWidth = min(0.08, rippleRadius * 0.6)
        let rippleBaseOpacity = completion != nil ? 0.65 : 0.1
        let stops: [Gradient.Stop] = ripple ? [
            .init(color: tint.opacity(rippleBaseOpacity), location: 0),
            .init(color: tint.opacity(rippleBaseOpacity), location: max(0, 0.5 - rippleRadius - rippleWidth)),
            .init(color: tint, location: 0.5 - rippleRadius),
            .init(color: tint.opacity(rippleBaseOpacity), location: 0.5 - rippleRadius + rippleWidth),
            .init(color: tint.opacity(rippleBaseOpacity), location: 0.5 + rippleRadius - rippleWidth),
            .init(color: tint, location: 0.5 + rippleRadius),
            .init(color: tint.opacity(rippleBaseOpacity), location: min(1, 0.5 + rippleRadius + rippleWidth)),
            .init(color: tint.opacity(rippleBaseOpacity), location: 1)
        ] : sweeps ? [
            .init(color: tint.opacity(0.1), location: 0),
            .init(color: tint.opacity(0.15), location: max(0.001, peak - 0.12)),
            .init(color: tint, location: peak),
            .init(color: tint.opacity(0.1), location: min(0.999, peak + 0.06)),
            .init(color: tint.opacity(0.1), location: 1)
        ] : [
            .init(color: tint.opacity(0.16), location: 0),
            .init(color: tint.opacity(0.9), location: 0.5),
            .init(color: tint.opacity(0.16), location: 1)
        ]
        let pulseOpacity = age.map { t -> Double in
            if reduceMotion { return 0.75 }
            if completion != nil {
                let rise = min(1, max(0, t / 0.18))
                let fade = min(1, max(0, (signalDuration - t) / 1.05))
                return rise * rise * (3 - 2 * rise) * fade * fade * (3 - 2 * fade)
            }
            return (signature == .message || signature == .handoff)
                ? 0.3 + 0.65 * sin(min(1, t / 1.2) * .pi)
                : min(1, max(0.22, (signalDuration - t) / 0.3))
        }
        let workspaceOpacity = workspace.map { t -> Double in
            if reduceMotion { return 0.75 }
            // Each switch gets one short signature, then the timeline stops.
            if workspaceName == "2" { return max(0, sin(min(1, t / 1.1) * .pi)) }
            if workspaceName == "G" {
                if t < 0.12 { return 0.45 }
                if t < 0.28 { return 0.95 }
                if t < 0.40 { return 0.30 }
            }
            return min(1, max(0, (1.1 - t) / 0.35))
        }
        let light = LinearGradient(stops: stops, startPoint: .leading, endPoint: .trailing)
        return ZStack(alignment: .bottomLeading) {
            if completion != nil {
                // Keep the live edge beneath the completion ripple so its
                // fade reveals the remaining agent without a dark flash.
                let base = LinearGradient(stops: [
                    .init(color: steadyTint.opacity(0.16), location: 0),
                    .init(color: steadyTint.opacity(0.9), location: 0.5),
                    .init(color: steadyTint.opacity(0.16), location: 1)
                ], startPoint: .leading, endPoint: .trailing)
                ZStack {
                    shape.stroke(base, lineWidth: 4).blur(radius: 4).offset(y: 1).opacity(0.5)
                    shape.stroke(base, lineWidth: 1.3)
                }
                .opacity(working || playing ? 0.65 : 0.22)
            }
            ZStack {
                shape.stroke(light, lineWidth: 4).blur(radius: 4).offset(y: 1).opacity(0.5)
                shape.stroke(light, lineWidth: 1.3)
            }
            .mask {
                Rectangle().frame(width: age != nil && signature == .wake && !reduceMotion
                    ? surfaceSize.width * min(1, (age ?? 0) / 0.6) : surfaceSize.width)
            }
            .opacity(pulseOpacity
                ?? workspaceOpacity
                ?? (idle ? 0.22 : 0.65))
            if let item = downloads.items.first(where: { !$0.completed && $0.active }) {
                // Unknown totals get a faint activity line, never a made-up percentage.
                Rectangle().fill(LinearGradient(colors: [blue, purple], startPoint: .leading, endPoint: .trailing))
                    .frame(width: surfaceSize.width * max(0, min(1, item.fraction ?? 1)), height: 1.5)
                    .opacity(item.fraction == nil ? 0.25 : 0.9)
            }
            shape.stroke(RadialGradient(colors: [purple.opacity(0.9), purple.opacity(0)],
                                        center: UnitPoint(x: pointerX ?? lastPointerX, y: 1),
                                        startRadius: 0, endRadius: 75), lineWidth: 5)
                .blur(radius: 2)
                .opacity(pointerX == nil ? 0 : 0.8)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: pointerX == nil)
        }
        .mask(alignment: .bottom) { Rectangle().frame(height: 10) }
        .clipShape(shape)
    }
}

/// One unmasked outline follows the native animated contour, or the joined
/// workspace backdrop. It sits below the black surface and never takes clicks.
struct NotchNeonView: View {
    @ObservedObject var service: NotchService
    @ObservedObject var motion: NotchQuickAccessMotion
    @ObservedObject var backdrop: NotchBackdropPresentation

    var body: some View {
        let bounds = backdrop.contour.boundingRect
        let offset = motion.neonCanvasOffset
        let frame = motion.workspaceSurfaceFrame ?? bounds.offsetBy(dx: offset.x, dy: offset.y)
        ZStack(alignment: .topLeading) {
            if !frame.isNull, frame.width > 0, frame.height > 0,
               !service.hiddenInFullscreen, service.captureControls == nil {
                NotchNeonEdge(service: service, surfaceSize: frame.size,
                              contour: motion.workspaceSurfaceFrame == nil
                                ? backdrop.contour.offsetBy(dx: -bounds.minX, dy: -bounds.minY) : nil,
                              pointerX: motion.neonPointer.flatMap { point in
                                  frame.contains(point) ? (point.x - frame.minX) / frame.width : nil
                              })
                    .frame(width: frame.width, height: frame.height)
                    .position(x: frame.midX, y: frame.midY + NotchNeonEdge.drop)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// The short reveal is tied to a confirmed workspace change, not a loop.
struct NotchWorkspaceSignal: View {
    let workspace: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var revealed = false
    @State private var departing = false
    @State private var applications: [String] = []
    @State private var applicationsVisible = false

    var body: some View {
        HStack(spacing: 5) {
        Text(workspace)
            .font(.system(size: 12, weight: .semibold, design: .monospaced))
            .foregroundStyle(NotchNeonPalette.workspace(workspace))
            .shadow(color: NotchNeonPalette.workspace(workspace).opacity(revealed ? 0 : 0.8), radius: 4)
            .offset(x: revealed ? (departing ? 4 : 0) : -5)
            .opacity(revealed && !departing ? 1 : 0)
            .overlay {
                Rectangle().fill(NotchNeonPalette.workspace(workspace).opacity(revealed ? 0 : 0.7))
                    .frame(height: 1).offset(y: revealed ? 8 : -8)
            }
            .onAppear {
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.22)) { revealed = true }
            }
            .task(id: workspace) {
                let remaining = NotchAeroSpaceService.shared.state.labelFadeAt
                    - ProcessInfo.processInfo.systemUptime
                if remaining > 0 {
                    do { try await Task.sleep(for: .seconds(remaining)) } catch { return }
                }
                guard !Task.isCancelled else { return }
                withAnimation(reduceMotion ? nil : .easeInOut(duration: NotchAeroSpaceState.labelFadeDuration)) {
                    departing = true
                }
            }
            .frame(width: 14)
            HStack(spacing: 5) {
                ForEach(applications, id: \.self) { name in
                    if let icon = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == name })?.icon {
                        Image(nsImage: icon).resizable().scaledToFit().frame(width: 14, height: 14)
                            .help(name)
                    }
                }
            }
            .frame(width: 52, alignment: .leading)
            .opacity(applicationsVisible ? 1 : 0)
            .allowsHitTesting(applicationsVisible)
            .accessibilityHidden(!applicationsVisible)
        }
        .padding(.leading, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .task(id: workspace) {
            let hideAt = NotchAeroSpaceService.shared.state.trailUntil
            let windows = (try? await NotchWorkspaceWindows.list(workspace)) ?? []
            guard !Task.isCancelled else { return }
            var seen = Set<String>()
            let names = windows.map(\.app).filter { seen.insert($0).inserted }
            applications = Array(names.prefix(3))
            let remaining = hideAt - ProcessInfo.processInfo.systemUptime
            guard remaining > 0 else { return }
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.18)) { applicationsVisible = true }
            do { try await Task.sleep(for: .seconds(remaining)) } catch { return }
            // Opacity keeps the number and native island contour stationary.
            withAnimation(reduceMotion ? nil : .easeInOut(duration: NotchAeroSpaceState.trailFadeDuration)) {
                applicationsVisible = false
            }
        }
    }
}
