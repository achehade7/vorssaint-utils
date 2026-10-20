// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI

/// What the lock screen may show, settled when it appears: preferences cannot
/// change while the Mac is locked, so the views never read them again.
final class NotchLockScreenModel: ObservableObject {
    struct Gates: Equatable {
        var music = false
        var timer = false
        var agents = false
        var downloads = false
        var countdown = false
        var timeLeft = false
    }

    @Published var gates = Gates()
    /// Kept for the whole time the Mac stays locked, across the display
    /// sleeping and waking, and cleared once it unlocks.
    @Published var playedWhileLocked = false
    @Published var padlockOpen = false
    @Published var lockRippleID: UUID?
    @Published var trackShimmerID: UUID?
    @Published var chargingArrivalID: UUID?
    @Published var chargingPercent: Int?

    func showsMusic(_ playback: NotchPlayback?) -> Bool {
        gates.music && playback.map {
            NotchLockScreenSupport.showsMusic(isPlaying: $0.isPlaying, playedWhileLocked: playedWhileLocked)
        } == true
    }
}

/// The island at rest with a padlock beside the camera, and the music's bars
/// on the other side while a song plays. The padlock closes as the Mac locks
/// and opens as it unlocks, before the island returns underneath.
struct NotchLockScreenIsland: View {
    @ObservedObject var model: NotchLockScreenModel
    let size: CGSize
    let cameraWidth: CGFloat
    /// The music strip's own geometry: the padlock takes the cover's place and
    /// the bars keep theirs, so locking changes what shows, not where.
    let geometry: NotchGeometry
    /// The window on whole points around the island, and the island's top
    /// left corner inside it; the rest of the window stays clear.
    var window: CGSize? = nil
    var origin: CGPoint = .zero
    @ObservedObject private var music = NotchMusicService.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showsChargingSignal = false
    @State private var chargingAt: Date?

    var body: some View {
        let wing = max(0, (size.width - cameraWidth) / 2)
        let contentHeight = min(size.height, geometry.bareCutout.height)
        let padlockSide = min(geometry.compactMusicArtworkSide, wing)
        let playing = model.showsMusic(music.playback) && music.playback?.isPlaying == true
        NotchShape(attached: true, radius: NotchLayout.surfaceRadius(height: size.height))
            .fill(.black)
            .overlay(alignment: .top) {
                HStack(spacing: 0) {
                    Image(systemName: showsChargingSignal ? "bolt.fill" : model.padlockOpen ? "lock.open.fill" : "lock.fill")
                        .font(.system(size: min(13, contentHeight * 0.42), weight: .semibold))
                        .foregroundStyle(showsChargingSignal ? NotchNeonPalette.charging
                                         : model.padlockOpen ? NotchNeonPalette.blue : NotchNeonPalette.purple)
                        .contentTransition(reduceMotion ? .opacity : .symbolEffect(.replace))
                        .symbolEffect(.bounce, options: .speed(1.4), value: reduceMotion ? false : model.padlockOpen)
                        .animation(reduceMotion ? nil : .smooth(duration: 0.25), value: model.padlockOpen)
                        .frame(width: padlockSide, height: padlockSide)
                        .padding(.leading, max(0, min(geometry.compactMusicArtworkInset, wing - padlockSide)))
                        .frame(width: wing, height: contentHeight, alignment: .leading)
                    Spacer(minLength: 0)
                    ZStack {
                        NotchEqualizerBars(isPlaying: playing, bars: NotchLayout.compactMusicBarCount,
                                           barWidth: NotchLayout.compactMusicBarWidth, height: geometry.compactMusicBarHeight,
                                           tint: NotchNeonPalette.blue)
                            .opacity(playing && !showsChargingSignal ? 1 : 0)
                        if showsChargingSignal, let percent = model.chargingPercent, wing >= 30 {
                            Text("\(percent)%")
                                .font(.system(size: 10.5, weight: .semibold))
                                .monospacedDigit()
                                .foregroundStyle(NotchNeonPalette.charging)
                                .fixedSize()
                                .transition(.opacity)
                        }
                    }
                        .animation(reduceMotion ? nil : .smooth(duration: 0.3), value: playing)
                        .padding(.trailing, max(0, min(geometry.compactMusicBarsInset, wing - NotchLayout.compactMusicBarsWidth)))
                        .frame(width: wing, height: contentHeight, alignment: .trailing)
                }
            }
            .overlay {
                // The surface sits below the camera and the panel reserves
                // clear room around this light, including its soft glow.
                NotchShape(attached: true, radius: NotchLayout.surfaceRadius(height: size.height))
                    .stroke(NotchLockScreenSurface.light, lineWidth: 1)
                    .mask(alignment: .bottom) {
                        LinearGradient(colors: [.clear, .white], startPoint: .top, endPoint: .bottom)
                            .frame(height: 12)
                    }
                    .shadow(color: NotchNeonPalette.purple.opacity(0.55), radius: 2)
                    .allowsHitTesting(false)
            }
            .overlay {
                NotchLockScreenEdgePulse(event: model.lockRippleID, size: size)
                if let chargingAt {
                    TimelineView(.animation(minimumInterval: 1.0 / 60)) { context in
                        NotchChargingEdge(
                            shape: NotchShape(attached: true, radius: NotchLayout.surfaceRadius(height: size.height))
                                .path(in: CGRect(origin: .zero, size: size)),
                            size: size, age: context.date.timeIntervalSince(chargingAt), reduceMotion: reduceMotion)
                    }
                }
            }
            .frame(width: size.width, height: size.height)
            .padding(.leading, origin.x)
            .padding(.top, origin.y)
            .frame(width: window?.width ?? size.width, height: window?.height ?? size.height, alignment: .topLeading)
            .accessibilityHidden(true)
            .task(id: model.chargingArrivalID) {
                withAnimation(nil) { showsChargingSignal = false; chargingAt = nil }
                guard model.chargingArrivalID != nil else { return }
                chargingAt = Date()
                do {
                    try await Task.sleep(for: .seconds(NotchChargingSignal.riseDuration))
                    withAnimation(.easeOut(duration: 0.18)) {
                        showsChargingSignal = model.chargingPercent != nil && wing >= 30
                    }
                    try await Task.sleep(for: .seconds(NotchChargingSignal.duration
                                                      - NotchChargingSignal.riseDuration - NotchChargingSignal.fadeDuration))
                    withAnimation(.easeOut(duration: NotchChargingSignal.fadeDuration)) { showsChargingSignal = false }
                    try await Task.sleep(for: .seconds(NotchChargingSignal.fadeDuration))
                    chargingAt = nil
                } catch { return }
            }
    }
}

/// Two purple lights split from the centre on locking, then stop completely.
private struct NotchLockScreenEdgePulse: View {
    let event: UUID?
    let size: CGSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var progress: CGFloat = 0
    @State private var opacity: Double = 0

    var body: some View {
        let shape = NotchShape(attached: true, radius: NotchLayout.surfaceRadius(height: size.height))
        let tint = NotchNeonPalette.purple
        let width = min(60, size.width * 0.22)
        ZStack {
            if reduceMotion {
                shape.stroke(tint, lineWidth: 1.5)
            } else {
                ZStack(alignment: .leading) {
                    beam(tint: tint, width: width)
                        .offset(x: size.width / 2 + progress * (size.width + width) / 2 - width / 2)
                    beam(tint: tint, width: width)
                        .offset(x: size.width / 2 - progress * (size.width + width) / 2 - width / 2)
                }
                .frame(width: size.width, height: size.height, alignment: .leading)
                .mask(shape.stroke(lineWidth: 1.5))
                .mask(alignment: .bottom) { Rectangle().frame(height: size.height) }
            }
        }
        .shadow(color: tint.opacity(0.8), radius: 2)
        .opacity(opacity)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        .task(id: event) {
            withAnimation(nil) { progress = 0; opacity = 0 }
            guard event != nil else { return }
            do {
                try await Task.sleep(for: .milliseconds(30))
                withAnimation(.easeOut(duration: 0.12)) { opacity = 1 }
                if !reduceMotion {
                    withAnimation(.easeInOut(duration: 0.95)) { progress = 1 }
                }
                try await Task.sleep(for: .seconds(reduceMotion ? 0.45 : 0.95))
                withAnimation(.easeOut(duration: 0.45)) { opacity = 0 }
            } catch { return }
        }
    }

    private func beam(tint: Color, width: CGFloat) -> some View {
        LinearGradient(colors: [.clear, tint.opacity(0.35), tint, .white.opacity(0.85), .clear],
                       startPoint: .leading, endPoint: .trailing)
            .frame(width: width, height: size.height)
    }
}

/// A smoked-black pane with the same violet-to-blue edge as the desktop
/// island. The lighting is static; it adds no animation or polling clock.
private struct NotchLockScreenSurface: ViewModifier {
    let cornerRadius: CGFloat
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    static var light: LinearGradient {
        LinearGradient(colors: [NotchNeonPalette.purple, NotchNeonPalette.blue],
                       startPoint: .leading, endPoint: .trailing)
    }

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content
            .background {
                shape.fill(.black.opacity(reduceTransparency || contrast == .increased ? 1 : 0.92))
                    .overlay {
                        shape.fill(LinearGradient(colors: [NotchNeonPalette.purple.opacity(0.10), .clear,
                                                           NotchNeonPalette.blue.opacity(0.05)],
                                                  startPoint: .topLeading, endPoint: .bottomTrailing))
                    }
            }
            .overlay {
                shape.strokeBorder(Self.light.opacity(contrast == .increased ? 0.9 : 0.42), lineWidth: 1)
                    .allowsHitTesting(false)
            }
            .overlay(alignment: .bottom) {
                Capsule().fill(Self.light)
                    .frame(height: 1.5)
                    .padding(.horizontal, cornerRadius)
                    .padding(.bottom, 1)
                    .shadow(color: NotchNeonPalette.purple.opacity(0.55), radius: 6, y: 2)
                    .allowsHitTesting(false)
            }
            .shadow(color: .black.opacity(0.3), radius: 12, y: 6)
    }
}

/// The song between the system clock and login controls, on a dark neon
/// pane. A smaller display takes a smaller cover, then puts it by the title.
struct NotchLockScreenPlayer: View {
    @ObservedObject var model: NotchLockScreenModel
    let size: CGSize
    @ObservedObject private var music = NotchMusicService.shared
    @ObservedObject private var l10n = L10n.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// What a tap on play or pause asked for, shown at once as the island's
    /// own player shows it, until the player says so.
    @State private var requestedPlaying: Bool?
    private var text: RadialMenuFeatureStrings { FeatureStrings.radialMenu(l10n.language) }
    private var accent: Color { NotchNeonPalette.purple }

    var body: some View {
        let shown = model.showsMusic(music.playback)
        ZStack {
            if shown, let playback = music.playback {
                ViewThatFits(in: .vertical) {
                    player(playback, artwork: 112)
                    player(playback, artwork: 84)
                    compact(playback)
                }
                .overlay { NotchLockScreenTrackShimmer(event: model.trackShimmerID) }
                .transition(reduceMotion ? .opacity : .opacity.combined(with: .scale(scale: 0.96)))
            }
        }
        .frame(width: size.width, height: size.height)
        .animation(reduceMotion ? nil : .smooth(duration: 0.5), value: shown)
        // A second tap before the player answers asks for the state after it,
        // so only the player reaching what was asked ends the early word.
        .onChange(of: music.playback?.isPlaying) {
            if music.playback?.isPlaying == requestedPlaying { requestedPlaying = nil }
        }
        .onChange(of: music.playback?.track) { requestedPlaying = nil }
        // A player that never answers leaves the button as it was.
        .task(id: requestedPlaying) {
            guard requestedPlaying != nil else { return }
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            if !Task.isCancelled { requestedPlaying = nil }
        }
    }

    private func player(_ playback: NotchPlayback, artwork: CGFloat) -> some View {
        VStack(spacing: 0) {
            cover(size: artwork, playback: playback)
                .padding(.bottom, 14)
            Text(playback.track.title ?? text.mediaNowPlaying)
                .font(.system(size: 18, weight: .bold))
                .lineLimit(1)
            if let artist = playback.track.artist ?? playback.track.album {
                Text(artist)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(NotchNeonPalette.purple)
                    .lineLimit(1)
                    .padding(.top, 2)
            }
            NotchMusicTimeline(playback: playback, service: music, tint: accent)
                .padding(.top, 16)
            transport(playback)
        }
        .pane()
    }

    /// A short display lays the cover beside the title, as the island's own
    /// player does.
    private func compact(_ playback: NotchPlayback) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                cover(size: 52, playback: playback)
                VStack(alignment: .leading, spacing: 2) {
                    Text(playback.track.title ?? text.mediaNowPlaying)
                        .font(.system(size: 16, weight: .bold))
                    if let artist = playback.track.artist ?? playback.track.album {
                        Text(artist).font(.system(size: 13, weight: .medium)).foregroundStyle(NotchNeonPalette.purple)
                    }
                }
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            NotchMusicTimeline(playback: playback, service: music, tint: accent)
                .padding(.top, 12)
            transport(playback)
        }
        .pane()
    }

    private func cover(size: CGFloat, playback: NotchPlayback) -> some View {
        // Covers often arrive after the new title. Follow the artwork itself
        // so that late arrivals crossfade too, without replaying the shimmer.
        let identity = music.artwork.map { ObjectIdentifier($0) }
        return ZStack {
            NotchArtwork(image: music.artwork, size: size, source: playback.track)
                .id(identity)
                .transition(.opacity)
        }
            .animation(.easeInOut(duration: reduceMotion ? 0.15 : 0.4), value: identity)
            .shadow(color: NotchNeonPalette.purple.opacity(0.3), radius: size * 0.16, x: -5, y: 2)
            .shadow(color: NotchNeonPalette.blue.opacity(0.25), radius: size * 0.16, x: 5, y: 2)
            .scaleEffect(playback.isPlaying || reduceMotion ? 1 : 0.92)
            .animation(reduceMotion ? nil : .smooth(duration: 0.35), value: playback.isPlaying)
    }

    /// The player's own buttons, never a permission prompt: a request made
    /// here would open behind the lock screen, where no one can answer it.
    private func transport(_ playback: NotchPlayback) -> some View {
        HStack(spacing: 46) {
            if !music.lacksTrackSkipping(.previous) {
                button("backward.fill", size: 22, title: text.mediaPrevious, command: .previous, playback: playback)
            }
            button((requestedPlaying ?? playback.isPlaying) ? "pause.fill" : "play.fill", size: 30,
                   title: text.mediaPlayPause, command: .toggle, playback: playback)
            if !music.lacksTrackSkipping(.next) {
                button("forward.fill", size: 22, title: text.mediaNext, command: .next, playback: playback)
            }
        }
        .frame(height: 46)
    }

    private func button(_ symbol: String, size: CGFloat, title: String, command: NotchMusicService.Command,
                        playback: NotchPlayback) -> some View {
        Button {
            let playing = requestedPlaying ?? playback.isPlaying
            // Only a player the island writes to directly answers fast enough
            // to show its word early. A slower path waits for the player.
            if music.send(command, context: playback.commandContext), command == .toggle,
               playback.canSendCommandsDirectly { requestedPlaying = !playing }
        } label: {
            Image(systemName: symbol)
                .font(.system(size: size, weight: .semibold))
                .foregroundStyle(.white)
                .contentTransition(.symbolEffect(.replace))
                .animation(reduceMotion ? nil : .smooth(duration: 0.22), value: symbol)
                .frame(width: 48, height: 44)
                .background {
                    if command == .toggle {
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(NotchLockScreenSurface.light.opacity((requestedPlaying ?? playback.isPlaying) ? 0.26 : 0.10))
                            .overlay {
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .strokeBorder(NotchLockScreenSurface.light.opacity(0.4), lineWidth: 0.75)
                            }
                    }
                }
                .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(NotchButtonStyle(cornerRadius: 14))
        .disabled(!music.canPerform(command))
        .accessibilityLabel(title)
    }
}

/// The new track's light passes over the card once; seeking and transport
/// remain the only interactive content underneath it.
private struct NotchLockScreenTrackShimmer: View {
    let event: UUID?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var progress: CGFloat = 0
    @State private var opacity: Double = 0

    var body: some View {
        GeometryReader { proxy in
            let shape = RoundedRectangle(cornerRadius: 28, style: .continuous)
            if reduceMotion {
                shape.strokeBorder(NotchLockScreenSurface.light, lineWidth: 1.5)
            } else {
                let width = proxy.size.width * 0.3
                LinearGradient(colors: [.clear, NotchNeonPalette.purple.opacity(0.18),
                                        NotchNeonPalette.blue.opacity(0.14), .clear],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(width: width)
                    .overlay(alignment: .bottom) {
                        Capsule().fill(NotchLockScreenSurface.light)
                            .frame(height: 1.5).padding(.bottom, 1)
                    }
                    .offset(x: -width + progress * (proxy.size.width + width))
                    .frame(width: proxy.size.width, height: proxy.size.height, alignment: .leading)
                    .clipShape(shape)
            }
        }
        .opacity(opacity)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        .task(id: event) {
            withAnimation(nil) { progress = 0; opacity = 0 }
            guard event != nil else { return }
            do {
                try await Task.sleep(for: .milliseconds(30))
                withAnimation(.easeOut(duration: 0.12)) { opacity = 1 }
                if !reduceMotion {
                    withAnimation(.easeInOut(duration: 0.85)) { progress = 1 }
                }
                try await Task.sleep(for: .seconds(reduceMotion ? 0.4 : 0.85))
                withAnimation(.easeOut(duration: 0.3)) { opacity = 0 }
            } catch { return }
        }
    }
}

private extension View {
    /// The player's pane, as wide as the timeline needs and no wider.
    func pane() -> some View {
        foregroundStyle(.white)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 26)
            .padding(.vertical, 20)
            .frame(width: NotchLockScreenLayout.paneWidth)
            .modifier(NotchLockScreenSurface(cornerRadius: 28))
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// Compact activity capsules under the clock. A line too long for the
/// display gives up its last activities first.
struct NotchLockScreenActivities: View {
    @ObservedObject var model: NotchLockScreenModel
    let size: CGSize
    @ObservedObject private var timer = NotchTimerService.shared
    @ObservedObject private var usage = AgentUsageService.shared
    @ObservedObject private var downloads = NotchDownloadService.shared
    @ObservedObject private var calendar = NotchCalendarService.shared
    @ObservedObject private var l10n = L10n.shared
    @AppStorage(DefaultsKey.notchAgentsReadout) private var readout = NotchAgentReadout.elapsed.rawValue
    @AppStorage(DefaultsKey.notchAgentsLimitDisplay) private var display = NotchAgentLimitDisplay.remaining.rawValue
    @AppStorage(DefaultsKey.notchAgentsLimitFocus) private var focus = NotchAgentLimitFocus.mostUsed.rawValue
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let items = available(at: context.date)
            ViewThatFits(in: .horizontal) {
                line(items, at: context.date)
                line(Array(items.prefix(3)), at: context.date)
                line(Array(items.prefix(2)), at: context.date)
                line(Array(items.prefix(1)), at: context.date)
            }
            .frame(width: size.width, height: size.height)
            .animation(reduceMotion ? nil : .smooth(duration: 0.35), value: items)
        }
        .allowsHitTesting(false)
    }

    private func available(at date: Date) -> [NotchLockScreenActivity] {
        let gates = model.gates
        return NotchLockScreenSupport.activities(
            timer: gates.timer && timer.session.hasSession,
            calendar: calendar.countdown.map {
                ($0.ongoing ? gates.timeLeft : gates.countdown || calendar.isChosen($0.event)) && $0.isShown(at: date)
            } == true,
            agents: gates.agents && !usage.snapshot.live.isEmpty,
            downloads: gates.downloads && downloads.items.contains { $0.active && !$0.completed })
    }

    private func line(_ items: [NotchLockScreenActivity], at date: Date) -> some View {
        HStack(spacing: 8) {
            ForEach(items) { item in
                entry(item, at: date)
                    .padding(.horizontal, 11)
                    .frame(height: NotchLockScreenLayout.rowHeight)
                    .background {
                        RoundedRectangle(cornerRadius: NotchLockScreenLayout.rowHeight / 2, style: .continuous)
                            .fill(.black.opacity(reduceTransparency || contrast == .increased ? 1 : 0.88))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: NotchLockScreenLayout.rowHeight / 2, style: .continuous)
                            .strokeBorder(tint(item).opacity(contrast == .increased ? 0.9 : 0.45), lineWidth: 0.75)
                    }
                    .transition(.opacity)
            }
        }
        .font(.system(size: 13, weight: .semibold))
        .monospacedDigit()
        .foregroundStyle(.white.opacity(0.92))
        .lineLimit(1)
        .fixedSize()
        .legibleOnWallpaper()
    }

    private func tint(_ item: NotchLockScreenActivity) -> Color {
        switch item {
        case .timer: NotchNeonPalette.amber
        case .calendar: NotchNeonPalette.purple
        case .agents, .downloads: NotchNeonPalette.blue
        }
    }

    @ViewBuilder private func entry(_ item: NotchLockScreenActivity, at date: Date) -> some View {
        switch item {
        case .timer:
            let session = timer.session
            let now = timer.now
            let finished = NotchLockScreenSupport.timerFinished(session, at: now)
            let text = FeatureStrings.notchActivities(l10n.language)
            let clock = finished ? text.finished : NotchTimerSupport.clockText(for: session, at: now)
            HStack(spacing: 7) {
                Image(systemName: finished ? "checkmark.circle.fill" : session.isPaused ? "pause.circle.fill"
                      : session.countsUp ? "stopwatch.fill" : "timer")
                    .foregroundStyle(NotchNeonPalette.amber)
                Text(session.mode == .pomodoro && !finished ? text.phase(session.phase) + " " + clock : clock)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(text.phase(session.phase))
            .accessibilityValue(clock)
        case .calendar:
            if let countdown = calendar.countdown {
                let text = FeatureStrings.notchCalendar(l10n.language)
                HStack(spacing: 7) {
                    Image(systemName: "calendar").foregroundStyle(NotchNeonPalette.purple)
                    Text(NotchCalendarStrip.displayTitle(countdown.event, untitled: text.untitled))
                        .frame(maxWidth: 240, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(NotchCalendarSupport.countdownText(until: countdown.target, now: date))
                        .foregroundStyle(.white.opacity(0.7))
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel(countdown.ongoing ? text.ongoing : text.next)
            }
        case .agents:
            let working = AgentProvider.allCases.filter { provider in usage.snapshot.live.contains { $0.provider == provider } }
            let mode = NotchAgentReadout(rawValue: readout) ?? .elapsed
            let readings = NotchAgentSupport.stripReadings(usage.snapshot, readout: mode,
                                                          display: NotchAgentLimitDisplay(rawValue: display) ?? .remaining,
                                                          focus: NotchAgentLimitFocus(rawValue: focus) ?? .mostUsed, now: date)
            // Each elapsed clock belongs to its own agent. A project's name
            // stays off a screen anyone can walk up to.
            HStack(spacing: 12) {
                ForEach(readings, id: \.provider) { reading in
                    let providers = mode == .elapsed ? [reading.provider] : working
                    HStack(spacing: 7) {
                        HStack(spacing: 1) {
                            ForEach(providers) { NotchAgentGlyph(provider: $0, size: 13) }
                        }
                        Text(reading.text).foregroundStyle(reading.provider.tint)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(providers.map(\.displayName).joined(separator: ", ") + ", "
                                        + FeatureStrings.notchLockScreen(l10n.language).working)
                    .accessibilityValue(reading.text)
                }
            }
        case .downloads:
            // Progress without the file's name, which stays off the lock screen.
            let fraction = downloads.items.first(where: { $0.active && !$0.completed })?.fraction
            HStack(spacing: 7) {
                Image(systemName: "arrow.down.circle.fill").foregroundStyle(NotchNeonPalette.blue)
                if let fraction {
                    Text(fraction, format: .percent.precision(.fractionLength(0)))
                } else {
                    Text(FeatureStrings.notchFiles(l10n.language).inProgress)
                }
            }
            .accessibilityElement(children: .combine)
        }
    }
}

private extension View {
    /// White type over any wallpaper, the way the lock screen's own clock
    /// stays readable over a bright photo.
    func legibleOnWallpaper() -> some View {
        shadow(color: .black.opacity(0.3), radius: 8, y: 1)
    }
}
