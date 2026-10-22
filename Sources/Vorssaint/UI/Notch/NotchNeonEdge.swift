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
    static let charging = Color(red: 76.0 / 255, green: 1, blue: 136.0 / 255)
    static func workspace(_ name: String?) -> Color {
        switch name {
        case "1": blue
        case "G": amber
        case "P": Color(red: 0.95, green: 0.42, blue: 0.73)
        default: purple
        }
    }
}

/// A bounded plug-in signal, independent of notifications and agent completions.
enum NotchChargingSignal {
    static let duration: TimeInterval = 2.2
    static let fullscreenDuration: TimeInterval = 1.6
    static let travelDuration: TimeInterval = 0.52
    static let echoDelay: TimeInterval = 0.13
    static let sweepDuration = travelDuration * 2 + echoDelay
    static let riseDuration: TimeInterval = 0.12
    static let fadeDuration: TimeInterval = 0.7

    static func lifetime(fullscreen: Bool) -> TimeInterval { fullscreen ? fullscreenDuration : duration }

    static func opacity(at age: TimeInterval, fullscreen: Bool = false) -> Double {
        let duration = lifetime(fullscreen: fullscreen)
        guard age >= 0, age < duration else { return 0 }
        let rise = min(1, age / riseDuration)
        let fade = min(1, (duration - age) / fadeDuration)
        return rise * rise * (3 - 2 * rise) * fade * fade * (3 - 2 * fade)
    }

    /// Two staggered lights each cross the edge, turn, and return off-screen.
    static func beamPosition(at age: TimeInterval, echo: Int) -> Double? {
        let elapsed = age - Double(echo) * echoDelay
        guard elapsed >= 0, elapsed <= travelDuration * 2 else { return nil }
        return (1 - cos(elapsed / travelDuration * .pi)) / 2
    }

    static func glow(at age: TimeInterval, reduceMotion: Bool) -> Double {
        guard !reduceMotion else { return 0.72 }
        let settle = min(1, max(0, age / sweepDuration))
        return 0.24 + 0.48 * settle * settle * (3 - 2 * settle)
    }
}

/// The same fine green edge on the desktop and lock screen. The moving lights
/// leave the contour before it settles; the soft halo is never clipped flat.
struct NotchChargingEdge: View {
    let shape: Path
    let size: CGSize
    let age: TimeInterval
    let reduceMotion: Bool

    var body: some View {
        let green = NotchNeonPalette.charging
        let width = min(60, size.width * 0.18)
        ZStack {
            shape.stroke(green, lineWidth: 1.5)
                .opacity(NotchChargingSignal.glow(at: age, reduceMotion: reduceMotion))
            if !reduceMotion {
                ZStack(alignment: .leading) {
                    ForEach(0..<2) { echo in
                        if let position = NotchChargingSignal.beamPosition(at: age, echo: echo) {
                            LinearGradient(colors: [.clear, green.opacity(0.4), green,
                                                    .white.opacity(0.95), green, .clear],
                                           startPoint: .leading, endPoint: .trailing)
                                .frame(width: width, height: size.height)
                                .offset(x: -width + position * (size.width + width))
                                .opacity(echo == 0 ? 1 : 0.8)
                        }
                    }
                }
                .frame(width: size.width, height: size.height, alignment: .leading)
                .mask(shape.stroke(lineWidth: 1.8))
            }
        }
        .mask(alignment: .bottom) {
            LinearGradient(colors: [.clear, .white], startPoint: .top, endPoint: .bottom)
                .frame(height: 12)
        }
        .shadow(color: green.opacity(0.8), radius: 2)
        .opacity(NotchChargingSignal.opacity(at: age))
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct NotchNeonEdge: View, Animatable {
    @ObservedObject var service: NotchService
    static let drop: CGFloat = 2
    var surfaceSize: CGSize
    var contour: Path? = nil
    var pointerX: CGFloat?
    @ObservedObject private var timer = NotchTimerService.shared
    @ObservedObject private var agents = AgentUsageService.shared
    @ObservedObject private var downloads = NotchDownloadService.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private enum Signature: Equatable {
        case agent, agentFinished(AgentProvider), message, meeting, wake, clipboard, handoff, terminalSuccess, terminalFailure

        var completionProvider: AgentProvider? {
            if case .agentFinished(let provider) = self { return provider }
            return nil
        }
    }
    @State private var signature: Signature = .agent
    @State private var signalAt: Date?
    @State private var chargeAt: Date?
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
        return signature == .wake || signature == .clipboard ? 0.9 : 1.2
    }
    private var working: Bool { !agents.snapshot.live.isEmpty }
    private var animated: Bool { signalAt != nil || workspaceAt != nil }
    private var showsTimerFuse: Bool {
        service.hasTimerActivity && !timer.session.countsUp && timer.session.duration > 0
            && (timer.session.isRunning || timer.session.isPaused)
    }
    private var progressAdvancing: Bool {
        showsTimerFuse && timer.session.isRunning
    }

    var body: some View {
        Group {
            if (animated && !reduceMotion) || chargeAt != nil || service.neonFullChargeAt != nil || service.displayArrival != nil {
                TimelineView(.animation(minimumInterval: chargeAt != nil ? 1.0 / 60 : 1.0 / 24)) { context in
                    edge(at: context.date)
                }
            } else if progressAdvancing {
                // Only an active countdown needs a once-per-second progress clock.
                TimelineView(.periodic(from: .now, by: 1)) { context in
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
            else if notice.meetingReminder { signal(.meeting) }
            else if let status = notice.terminalStatus { signal(status == 0 ? .terminalSuccess : .terminalFailure) }
            else if notice.event == .agents || ["codex", "claude", "claude code"].contains(notice.notification?.app.lowercased() ?? "") {
                signal(.agent)
            } else if notice.event == .systemNotification { signal(.message) }
        }
        .onChange(of: service.neonChargeAt, initial: true) { _, date in
            charge(at: date)
        }
        .onChange(of: service.neonMeetingAt, initial: true) { _, date in
            if let date, (0..<1.2).contains(Date().timeIntervalSince(date)) { signal(.meeting, at: date) }
        }
        .onChange(of: service.neonCopyAt) { _, date in
            if let date { signal(.clipboard, at: date) }
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
        .task(id: chargeAt) {
            guard let began = chargeAt else { return }
            do {
                try await Task.sleep(for: .seconds(max(0,
                    NotchChargingSignal.duration - Date().timeIntervalSince(began))))
            } catch { return }
            chargeAt = nil
        }
    }

    private func charge(at date: Date?) {
        guard let date, (0..<NotchChargingSignal.duration).contains(Date().timeIntervalSince(date)) else {
            chargeAt = nil
            return
        }
        chargeAt = date
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
        let idle = !working && age == nil && workspace == nil
        let completion = age != nil ? signature.completionProvider : nil
        let steadyTint = working ? blue : purple
        // Meeting cyan (#7DDCE8) lifts to white at the pulse peak, then fades.
        let meetingWhite = reduceMotion ? 0 : min(1, max(0, (age ?? 0) / 0.6))
        let meetingTint = Color(red: (125 + 130 * meetingWhite) / 255,
                                green: (220 + 35 * meetingWhite) / 255,
                                blue: (232 + 23 * meetingWhite) / 255)
        let tint = completion?.tint ?? (age != nil ? (signature == .clipboard ? Color.white
                : signature == .meeting ? meetingTint
                : signature == .agent || signature == .terminalSuccess ? blue
                : signature == .terminalFailure ? Color(red: 0.95, green: 0.35, blue: 0.77) : purple)
            : workspace != nil ? NotchNeonPalette.workspace(workspaceName)
            : steadyTint)
        let phase = reduceMotion ? 0.5 : age.map { min(1, $0 / (completion != nil ? 1.35 : 0.7)) }
            ?? workspace.map { min(1, $0 / 0.65) } ?? 0.5
        let peak = max(0.01, min(0.99, phase))
        let ripple = completion != nil || (workspace != nil && workspaceName == "P")
            || (age != nil && signature == .handoff)
        let sweeps = (workspace != nil && workspaceName != "2")
            || (age != nil && [.agent, .terminalSuccess, .terminalFailure].contains(signature))
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
            if signature == .clipboard || signature == .meeting {
                return max(0, sin(min(1, t / signalDuration) * .pi))
            }
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
                .opacity(working ? 0.65 : 0.22)
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
            if showsTimerFuse {
                let remaining = min(1, max(0, timer.session.reading(at: timer.now) / timer.session.duration))
                shape.stroke(NotchNeonPalette.amber, lineWidth: 1.5)
                    .mask(alignment: .leading) {
                        Rectangle().frame(width: surfaceSize.width * remaining)
                    }
                    .opacity(completion != nil ? 0.2 : timer.session.isPaused ? 0.5 : 0.95)
            }
            if let item = downloads.items.first(where: { !$0.completed && $0.active }) {
                // Unknown totals get a faint activity line, never a made-up percentage.
                Rectangle().fill(LinearGradient(colors: [blue, purple], startPoint: .leading, endPoint: .trailing))
                    .frame(width: surfaceSize.width * max(0, min(1, item.fraction ?? 1)), height: 1.5)
                    .padding(.bottom, showsTimerFuse ? 2 : 0)
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
        .overlay {
            if let arrival = service.displayArrival {
                NotchDisplayArrivalEdge(shape: shape, size: surfaceSize,
                                        direction: arrival.direction, age: date.timeIntervalSince(arrival.began),
                                        reduceMotion: reduceMotion)
            }
            if let chargeAt {
                // Keep the ordinary edge below the shared charging light.
                NotchChargingEdge(shape: shape, size: surfaceSize,
                                  age: date.timeIntervalSince(chargeAt), reduceMotion: reduceMotion)
            }
            if let began = service.neonFullChargeAt {
                NotchFullChargeEdge(shape: shape, size: surfaceSize, age: date.timeIntervalSince(began),
                                    fullscreen: false, reduceMotion: reduceMotion)
            }
        }
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
        let resting = bounds.offsetBy(dx: offset.x, dy: offset.y)
        let frame = motion.workspaceDeparting ? resting : motion.workspaceSurfaceFrame ?? resting
        ZStack(alignment: .topLeading) {
            // This separate host does not share the content's dismissal mask.
            // Quiet mode must remove it before the outline contracts upward.
            if !service.quietMode, !frame.isNull, frame.width > 0, frame.height > 0,
               !service.displayIsFullscreen, service.captureControls == nil {
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
    @ObservedObject var motion: NotchQuickAccessMotion
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var revealed = false
    @State private var applications: [String] = []
    @State private var applicationsVisible = false

    var body: some View {
        HStack(spacing: 4) {
        Text(workspace)
            .font(.system(size: 14, weight: .semibold, design: .monospaced))
            .foregroundStyle(NotchNeonPalette.workspace(workspace))
            .shadow(color: NotchNeonPalette.workspace(workspace).opacity(revealed ? 0 : 0.8), radius: 4)
            .offset(x: revealed ? (motion.workspaceDeparting ? 4 : 0) : -5)
            .opacity(revealed && !motion.workspaceDeparting ? 1 : 0)
            .overlay {
                Rectangle().fill(NotchNeonPalette.workspace(workspace).opacity(revealed ? 0 : 0.7))
                    .frame(height: 1).offset(y: revealed ? 8 : -8)
            }
            .onAppear {
                motion.setWorkspaceDeparting(false, animated: false)
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.22)) { revealed = true }
            }
            .task(id: workspace) {
                let remaining = NotchAeroSpaceService.shared.state.labelFadeAt
                    - ProcessInfo.processInfo.systemUptime
                if remaining > 0 {
                    do { try await Task.sleep(for: .seconds(remaining)) } catch { return }
                }
                guard !Task.isCancelled else { return }
                motion.setWorkspaceDeparting(true, animated: !reduceMotion)
            }
            .frame(width: 14)
            HStack(spacing: 4) {
                ForEach(applications, id: \.self) { name in
                    if let icon = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == name })?.icon {
                        Image(nsImage: icon).resizable().scaledToFit().frame(width: 18, height: 18)
                            .help(name)
                    }
                }
            }
            .frame(width: 62, alignment: .leading)
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
