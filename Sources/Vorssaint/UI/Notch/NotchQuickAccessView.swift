// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI

/// Only the transition owns animation state. No timer or display link survives
/// the reveal, and a reversed transition cannot enable a departing button.
final class NotchQuickAccessMotion: ObservableObject {
    @Published private(set) var progress: CGFloat = 0
    @Published private(set) var interactive = false
    @Published private(set) var configuration = NotchQuickAccessConfiguration(side: .left, actions: [.explore])
    @Published private(set) var placements: [NotchQuickAccessPlacement] = []
    @Published private(set) var workspaceBadgeFrame: CGRect?
    @Published private(set) var workspaceSurfaceFrame: CGRect?
    @Published private(set) var workspaceDeparting = false
    @Published private(set) var neonCanvasOffset = CGPoint.zero
    @Published private(set) var neonPointer: CGPoint?

    func setNeonPointer(_ point: CGPoint?) {
        if neonPointer != point { neonPointer = point }
    }

    func setNeonCanvasOffset(_ offset: CGPoint) {
        if neonCanvasOffset != offset { neonCanvasOffset = offset }
    }

    func setWorkspaceBadge(_ frame: CGRect?, surface: CGRect?) {
        guard workspaceBadgeFrame != frame || workspaceSurfaceFrame != surface else { return }
        if workspaceBadgeFrame == nil || frame == nil { workspaceDeparting = false }
        workspaceBadgeFrame = frame
        workspaceSurfaceFrame = surface
    }

    /// The label, its black extension and the neon return together.
    func setWorkspaceDeparting(_ departing: Bool, animated: Bool) {
        guard workspaceDeparting != departing else { return }
        withAnimation(animated ? .easeInOut(duration: NotchAeroSpaceState.labelFadeDuration) : nil) {
            workspaceDeparting = departing
        }
    }

    private var bodyFrame = CGRect.zero
    private var visible = false
    private var generation = 0

    func configure(_ configuration: NotchQuickAccessConfiguration, body: CGRect, headerTop: CGFloat, animated: Bool) {
        let values = NotchQuickAccessLayout.placements(configuration, body: body, headerTop: headerTop)
        guard self.configuration != configuration || placements != values else { return }
        let spring = NotchMotion.sideSpring(from: bodyFrame.size, to: body.size)
        let animation: Animation? = animated && visible ? .spring(duration: spring.duration, bounce: spring.bounce) : nil
        bodyFrame = body
        withAnimation(animation) {
            self.configuration = configuration
            placements = values
        }
    }

    var hoverRects: [CGRect] {
        NotchQuickAccessSide.allCases.compactMap { side in
            let values = placements.filter { $0.side == side }
            guard let first = values.first else { return nil }
            return NotchQuickAccessLayout.hoverRect(count: values.count, edge: first.edge, top: first.top, side: side)
        }
    }

    func setVisible(_ visible: Bool, animated: Bool, delay: TimeInterval = 0) {
        guard self.visible != visible else { return }
        self.visible = visible
        generation += 1
        let token = generation
        interactive = false
        let animation: Animation? = animated
            ? (visible ? .spring(duration: 0.38, bounce: 0.12).delay(delay) : .easeIn(duration: NotchQuickAccessLayout.withdrawalDuration))
            : nil
        withAnimation(animation, completionCriteria: .logicallyComplete) {
            progress = visible ? 1 : 0
        } completion: { [weak self] in
            guard let self, self.generation == token else { return }
            self.interactive = visible
        }
    }

    func contains(_ point: CGPoint) -> Bool {
        if workspaceBadgeFrame?.contains(point) == true { return true }
        return interactive && placements.contains { value in
            let center = value.center(progress: 1)
            return hypot(point.x - center.x, point.y - center.y) <= NotchQuickAccessLayout.diameter / 2
        }
    }
}

struct NotchQuickAccessView: View {
    @ObservedObject var service: NotchService
    @ObservedObject var motion: NotchQuickAccessMotion
    /// Only the glass surface below follows it; it changes every frame of a resize.
    let backdrop: NotchBackdropPresentation
    @ObservedObject private var l10n = L10n.shared
    @ObservedObject private var awake = KeepAwakeManager.shared
    @ObservedObject private var microphone = MicMuteService.shared
    @ObservedObject private var recorder = ScreenRecorderService.shared
    @ObservedObject private var music = NotchMusicService.shared
    @State private var musicVolumeFeedback: Double?
    @State private var musicVolumeFeedbackID: UUID?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage(DefaultsKey.notchLiquidGlassEnabled) private var glass = false
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    /// Increase Contrast keeps the buttons solid beside a lip that barely opens.
    private var followsGlass: Bool {
#if compiler(>=6.2)
        if #available(macOS 26, *) { return glass && !reduceTransparency && contrast != .increased }
#endif
        return false
    }

    var body: some View {
        let drops = NotchQuickAccessDrops(placements: motion.placements, progress: motion.progress)
        let buttons = ZStack(alignment: .topLeading) {
            ForEach(motion.placements) { placement in
                bubble(placement.button)
                    .scaleEffect(0.4 + 0.6 * motion.progress)
                    .opacity(Double(motion.progress))
                    .position(placement.center(progress: motion.progress))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        Group {
            if followsGlass {
                buttons.modifier(NotchQuickAccessGlassSurface(presentation: backdrop, drops: drops))
            } else {
                buttons.background { drops }
            }
        }
        .environment(\.colorScheme, .dark)
        .environment(\.notchPresentation, true)
        .foregroundStyle(.white)
        .tint(.white)
        .allowsHitTesting(motion.interactive)
        .accessibilityHidden(!motion.interactive)
        .background(alignment: .topLeading) {
            if let frame = motion.workspaceSurfaceFrame {
                NotchShape.island(height: frame.height, geometry: service.geometry)
                    .fill(.black)
                    .frame(width: frame.width, height: frame.height)
                    .position(x: frame.midX, y: frame.midY)
                    .opacity(motion.workspaceDeparting ? 0 : 1)
                    .allowsHitTesting(false)
            }
        }
        .overlay(alignment: .topLeading) {
            if let frame = motion.workspaceBadgeFrame,
               let current = NotchAeroSpaceService.shared.state.current {
                NotchMenuButton(title: "AeroSpace", items: NotchAeroSpaceState.workspaces.map { workspace in
                    NotchMenuItem(title: workspace, checked: workspace == current) {
                        NotchAeroSpaceService.shared.select(workspace)
                    }
                }, cornerRadius: 8) {
                    NotchWorkspaceSignal(workspace: current, motion: motion)
                        .id(current)
                        .frame(width: frame.width, height: frame.height)
                        .contentShape(Rectangle())
                }
                .position(x: frame.midX, y: frame.midY)
                .accessibilityLabel("AeroSpace " + current)
                .accessibilityIdentifier("notch.aerospace.current")
            }
        }
        .task(id: musicVolumeFeedbackID) {
            guard musicVolumeFeedbackID != nil else { return }
            do { try await Task.sleep(for: .milliseconds(800)) } catch { return }
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { musicVolumeFeedback = nil }
        }
        .onChange(of: motion.interactive) {
            if !motion.interactive { musicVolumeFeedback = nil; musicVolumeFeedbackID = nil }
        }
    }

    private func adjustMusicVolume(by amount: Double) {
        guard motion.interactive else { return }
        let mixer = AppVolumeMixer.shared
        service.noteOwnLevelAdjustment(.volume)
        mixer.requestOutputStep(level: { min(1, max(0, $0 + amount)) }) { applied in
            guard applied, motion.interactive, let level = mixer.systemOutputVolume else { return }
            service.noteOwnLevelAdjustment(.volume)
            musicVolumeFeedback = mixer.systemOutputMuted == true ? 0 : level
            musicVolumeFeedbackID = UUID()
        }
    }

    private func bubble(_ button: NotchQuickButton) -> some View {
        let action = button.action ?? .explore
        let isBack = action == .explore && service.showingSections
        let isMusic = action == .module(.music) || action == .control(.music)
        let selected: Bool = {
            if action == .explore { return service.showingSections }
            if action == .pin { return service.pinned }
            if action == .control(.keepAwake) { return awake.isActive }
            if action == .control(.microphone) { return microphone.isMuted }
            if action == .control(.recording) { return recorder.isRecording }
            if isMusic && music.playback?.isPlaying == true { return true }
            if case .module(let module) = action {
                return !service.showingSections && !service.showingAppPanel && service.selected == module
            }
            return false
        }()
        var actionTitle = action.title(l10n)
        var symbol = action.symbol
        switch action {
        case .explore where isBack: symbol = "arrow.uturn.backward"
        case .settings: actionTitle = "System Settings"
        case .pin:
            actionTitle = service.pinned ? FeatureStrings.notch(l10n.language).unpin : FeatureStrings.notch(l10n.language).pin
            if service.pinned { symbol = "pin.fill" }
        case .control(.microphone):
            actionTitle = microphone.isMuted ? l10n.s.micUnmuteName : l10n.s.micMuteName
            if microphone.isMuted { symbol = "mic.slash.fill" }
        case .control(.keepAwake) where awake.isActive: symbol = "cup.and.saucer.fill"
        case .control(.recording) where recorder.isRecording: symbol = "stop.circle.fill"
        default: break
        }
        let title = isBack ? l10n.s.obBack : button.label.isEmpty ? actionTitle : button.label
        return Button {
            if isMusic, NotchMusicShortcutScroll.optionOnly(NSEvent.modifierFlags) {
                if music.canPerform(.toggle) { music.send(.toggle) }
            } else if action == .settings {
                service.perform {
                    if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.systempreferences") {
                        NSWorkspace.shared.open(url)
                    }
                }
            } else {
                service.activateQuickAction(action)
            }
        } label: {
            Group {
                if isMusic, let artwork = music.artwork, music.playback != nil {
                    NotchMusicCover(artwork: artwork, side: 27, radius: 7)
                } else if action == .settings {
                    Image(nsImage: NSWorkspace.shared.icon(forFile: "/System/Applications/System Settings.app"))
                        .resizable()
                        .scaledToFit()
                        .frame(width: 24, height: 24)
                } else if action == .appleMusic {
                    Image(nsImage: NSWorkspace.shared.icon(forFile: "/System/Applications/Music.app"))
                        .resizable()
                        .scaledToFit()
                        .frame(width: 24, height: 24)
                } else {
                    Image(systemName: symbol)
                        .font(.system(size: 17, weight: .medium))
                }
            }
                .foregroundStyle(selected ? NotchNeonPalette.amber : Color.white)
                .frame(width: NotchQuickAccessLayout.diameter, height: NotchQuickAccessLayout.diameter)
                // In glass the drop beneath carries the island's shade, which
                // the window server does not count as the window's own pixels:
                // a faint fill keeps the whole circle from passing clicks to
                // the app behind, not just the glyph.
                .background(followsGlass ? Color.black.opacity(0.02) : Color.black, in: Circle())
                .overlay {
                    Circle().strokeBorder((selected ? NotchNeonPalette.amber : Color.white)
                        .opacity(selected || contrast == .increased ? 0.6 : 0.16), lineWidth: 0.75)
                        .allowsHitTesting(false)
                }
                .contentShape(Circle())
                .overlay {
                    if isMusic, let level = musicVolumeFeedback {
                        ZStack {
                            Circle().trim(from: 0, to: 0.75)
                                .stroke(NotchNeonPalette.purple.opacity(0.2), style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                            Circle().trim(from: 0, to: 0.75 * level)
                                .stroke(NotchNeonPalette.purple, style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                        }
                        .rotationEffect(.degrees(135))
                        .padding(3)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                        .transition(.opacity)
                    }
                }
        }
        .buttonStyle(NotchButtonStyle(cornerRadius: NotchQuickAccessLayout.diameter / 2))
        .background {
            if isMusic, motion.interactive {
                NotchMusicShortcutScroll(adjusted: adjustMusicVolume)
            } else if action == .control(.keepAwake), motion.interactive {
                NotchObsidianRightClick(action: awake.toggleIndefinitely)
            }
        }
        .help(title)
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("notch.quickAccess.\(button.id.uuidString)")
    }
}

/// A passive listener over just the live music shortcut. Ordinary scrolling,
/// horizontal swipes and clicks still belong to the island and its button.
struct NotchMusicShortcutScroll: NSViewRepresentable {
    let adjusted: (Double) -> Void

    static func optionOnly(_ flags: NSEvent.ModifierFlags) -> Bool {
        flags.intersection([.command, .control, .option, .shift]) == .option
    }

    func makeNSView(context: Context) -> ScrollArea {
        let view = ScrollArea()
        view.adjusted = adjusted
        return view
    }

    func updateNSView(_ view: ScrollArea, context: Context) { view.adjusted = adjusted }
    static func dismantleNSView(_ view: ScrollArea, coordinator: ()) { view.stop() }

    final class ScrollArea: NSView {
        var adjusted: ((Double) -> Void)?
        private var monitor: Any?
        private var travel: CGFloat = 0
        private var lastTimestamp: TimeInterval?

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
                self?.handle(event) == true ? nil : event
            }
        }

        func handle(_ event: NSEvent) -> Bool {
            guard event.type == .scrollWheel, let window, window.isVisible, event.window === window,
                  !isHiddenOrHasHiddenAncestor, Self.inCircle(convert(event.locationInWindow, from: nil), bounds),
                  NotchMusicShortcutScroll.optionOnly(event.modifierFlags),
                  event.scrollingDeltaX.isFinite, event.scrollingDeltaY.isFinite, event.timestamp.isFinite,
                  abs(event.scrollingDeltaY) > abs(event.scrollingDeltaX) else {
                travel = 0; lastTimestamp = nil
                return false
            }
            guard event.momentumPhase.isEmpty else { travel = 0; return true }
            if !event.phase.intersection([.ended, .cancelled]).isEmpty {
                travel = 0; lastTimestamp = nil
                return true
            }
            if event.phase.contains(.began) || lastTimestamp.map({ event.timestamp < $0 || event.timestamp - $0 > 0.35 }) == true {
                travel = 0
            }
            lastTimestamp = event.timestamp
            // Physical upward motion raises the level with either scrolling preference.
            let delta = event.scrollingDeltaY * (event.isDirectionInvertedFromDevice ? -1 : 1)
            if travel * delta < 0 { travel = 0 }
            travel += delta
            let threshold: CGFloat = event.hasPreciseScrollingDeltas ? 20 : 1
            let steps = Int(min(4, max(-4, (travel / threshold).rounded(.towardZero))))
            if steps != 0 {
                travel = travel.truncatingRemainder(dividingBy: threshold)
                adjusted?(Double(steps) / 32)
            }
            return true
        }

        private static func inCircle(_ point: CGPoint, _ bounds: CGRect) -> Bool {
            hypot(point.x - bounds.midX, point.y - bounds.midY) <= min(bounds.width, bounds.height) / 2
        }

        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil; travel = 0; lastTimestamp = nil
        }

        deinit { stop() }
    }
}

/// Every button's drop, in the coordinates of the whole floating layer.
private struct NotchQuickAccessDrops: View {
    let placements: [NotchQuickAccessPlacement]
    let progress: CGFloat

    var body: some View {
        ZStack {
            ForEach(placements) { placement in
                NotchQuickAccessDrop(progress: progress, index: placement.index, edge: placement.edge,
                                     top: placement.top, side: placement.side)
                    .fill(.black)
            }
        }
        .allowsHitTesting(false)
    }
}

/// On glass each drop takes the island's shade at its own height, so it
/// leaves the island without a seam and buttons below the island are as
/// translucent as its lip. The island no longer hides what lies beneath its
/// edge, so a drop still inside it is cut away.
private struct NotchQuickAccessGlassSurface: ViewModifier {
    @ObservedObject var presentation: NotchBackdropPresentation
    let drops: NotchQuickAccessDrops
    @Environment(\.colorSchemeContrast) private var contrast

    func body(content: Content) -> some View {
        let island = presentation.usesGlass ? presentation.contour : Path()
        content
            .background {
                if presentation.usesGlass {
                    GeometryReader { proxy in
                        // Past the island the shade keeps the lip's tone,
                        // measured from the top edge as the island's own.
                        LinearGradient(stops: NotchSurfaceBackground.shade(openness: presentation.openness, contrast: contrast),
                                       startPoint: .top,
                                       endPoint: UnitPoint(x: 0.5, y: (island.isEmpty ? 0 : island.boundingRect.maxY)
                                                            / max(1, proxy.size.height)))
                            .mask { drops }
                    }
                } else {
                    drops
                }
            }
            .clipShape(NotchQuickAccessOutside(island: island), style: FillStyle(eoFill: true))
    }
}

/// The floating layer except the island, centered between equal gutters.
private struct NotchQuickAccessOutside: Shape {
    let island: Path

    func path(in rect: CGRect) -> Path {
        var path = Path(rect)
        guard !island.isEmpty else { return path }
        path.addPath(island, transform: CGAffineTransform(translationX: rect.midX - island.boundingRect.midX, y: 0))
        return path
    }
}

struct NotchQuickAccessDrop: Shape {
    var progress: CGFloat
    let index: Int
    var edge: CGFloat
    var top: CGFloat
    let side: NotchQuickAccessSide
    var animatableData: AnimatablePair<CGFloat, AnimatablePair<CGFloat, CGFloat>> {
        get { AnimatablePair(progress, AnimatablePair(edge, top)) }
        set { progress = newValue.first; edge = newValue.second.first; top = newValue.second.second }
    }

    func path(in rect: CGRect) -> Path {
        let phase = min(1.1, max(0, progress))
        guard phase > 0.001 else { return Path() }
        let anchor = side == .bottom ? rect.height - edge : side == .left ? edge : rect.width - edge
        let center = NotchQuickAccessLayout.center(index: index, progress: phase, edge: anchor, top: top, side: .left)
        let radius = NotchQuickAccessLayout.diameter / 2 * (0.4 + 0.6 * phase)
        var path = Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2))
        // The narrow connection dissolves before the circle finishes moving.
        // Its other end sits under the notch, so there is no visible seam.
        let neck = radius * max(0, 1 - phase / 0.84)
        if neck > 0, center.x + radius < anchor {
            path.move(to: CGPoint(x: anchor + 2, y: center.y + neck))
            path.addCurve(to: CGPoint(x: center.x + radius * 0.55, y: center.y + neck * 0.75),
                          control1: CGPoint(x: anchor - 7, y: center.y + neck),
                          control2: CGPoint(x: center.x + radius, y: center.y + neck * 0.15))
            path.addLine(to: CGPoint(x: center.x + radius * 0.55, y: center.y - neck * 0.75))
            path.addCurve(to: CGPoint(x: anchor + 2, y: center.y - neck),
                          control1: CGPoint(x: center.x + radius, y: center.y - neck * 0.15),
                          control2: CGPoint(x: anchor - 7, y: center.y - neck))
            path.closeSubpath()
        }
        if side == .bottom { return path.applying(CGAffineTransform(a: 0, b: -1, c: 1, d: 0, tx: 0, ty: rect.height)) }
        if side == .right { return path.applying(CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: rect.width, ty: 0)) }
        return path
    }
}

extension NotchQuickAction {
    var symbol: String {
        switch self {
        case .explore: return "square.grid.2x2"
        case .settings: return "gearshape"
        case .appleMusic: return "music.note"
        case .pin: return "pin"
        case .module(let module): return module.symbol
        case .control(let item): return item.symbol
        }
    }

    func title(_ l10n: L10n) -> String {
        switch self {
        case .explore: return FeatureStrings.notch(l10n.language).sectionsTitle
        case .settings: return l10n.s.menuSettings
        case .appleMusic: return "Apple Music"
        case .pin: return FeatureStrings.notch(l10n.language).pin
        case .module(let module): return module.title(l10n.language)
        case .control(let item): return item.title(l10n)
        }
    }
}
