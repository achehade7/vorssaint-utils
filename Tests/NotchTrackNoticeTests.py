#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint

"""Render both production compact track notices without starting a music player."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
notice = (repo / "Sources/Vorssaint/UI/Notch/NotchNoticeView.swift").read_text()
capsule = (repo / "Sources/Vorssaint/UI/Notch/NotchCapsuleViews.swift").read_text()


def declaration(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


views = "\n".join(declaration(notice, marker) for marker in [
    "struct NotchNoticeView: View", "private struct NotchTrackArtwork: View", "struct NotchTrackEqualizer: View",
]) + "\nprivate typealias CapsuleLayout = NotchCapsuleLayout\n" + "\n".join(
    declaration(capsule, marker) for marker in [
        "private struct NotchCapsuleRow<", "private extension Text {",
        "private struct NotchCapsuleSymbol: View", "private extension View {",
        "struct NotchCapsuleNoticeView: View", "private struct NotchCapsuleTrackArtwork: View",
    ])

views += "\n" + (repo / "Sources/Vorssaint/UI/Notch/NotchEqualizerBars.swift").read_text()
views += "\n" + (repo / "Sources/Vorssaint/UI/Notch/NotchDecorativeClock.swift").read_text()

swift = r'''
import AppKit
import SwiftUI
enum NotchEvent { case track, agents, timer, accessory, battery }
enum AgentProvider { case codex; var symbol: String { "terminal" }; var tint: Color { .blue } }
enum NotchMascotReaction: String { case happy }
struct NotchNoticeWings: Equatable { var leading: CGFloat, trailing: CGFloat }
struct NotchNotificationContent {
    var app = 0, compactTitle = "Notification", compactDetail = "Message"
}
struct NotchNotice {
    let event: NotchEvent, title: String, detail: String, symbol: String
    var level: Double?, notification: NotchNotificationContent?, agent: AgentProvider?, mascot: NotchMascotReaction?
    var cameraGap: CGFloat { 6 }
    var readsFromEnds: Bool { true }
    var accessibilityText: String { title + ", " + detail }
    var preferredWings: NotchNoticeWings { NotchNoticeWings(leading: 240, trailing: 240) }
    func wings(in: NotchGeometry) -> NotchNoticeWings { preferredWings }
    func inset(wing: CGFloat) -> CGFloat { 12 }
}
struct NotchGeometry {
    var stripHeight: CGFloat = 36
    var noticeCameraGap: CGFloat = 100
    var compactMusicArtworkSide: CGFloat { min(26, stripHeight - 6) }
    var compactMusicBarHeight: CGFloat { min(16, max(6, stripHeight - 10)) }
}
enum NotchNotificationBannerLayout {
    static let spacing: CGFloat = 8, iconSize: CGFloat = 18
    static let titleFont = NSFont.systemFont(ofSize: 11), messageFont = NSFont.systemFont(ofSize: 11)
    static func messageLines(stripHeight: CGFloat) -> Int { 1 }
}
enum NotchCapsuleLayout {
    static let endPadding: CGFloat = 8, symbolWidth: CGFloat = 16, symbolSize: CGFloat = 12
    static let spacing: CGFloat = 6, groupSpacing: CGFloat = 10, meterHeight: CGFloat = 5, meterWidth: CGFloat = 40
    static let titleFont = NSFont.systemFont(ofSize: 11), detailFont = NSFont.systemFont(ofSize: 11)
    static let levelFont = NSFont.systemFont(ofSize: 11)
    static func side(_ geometry: NotchGeometry) -> CGFloat { 4 }
    static func notificationIconSide(_ geometry: NotchGeometry) -> CGFloat { 18 }
    static func artworkSide(_ geometry: NotchGeometry) -> CGFloat { geometry.stripHeight - 6 }
    static func levelReadingWidth(_ value: String) -> CGFloat { 40 }
    static func symbolDrop(_ symbol: String, size: CGFloat, weight: NSFont.Weight) -> CGFloat { 0 }
}
enum NotchLayout {
    static let compactMusicBarCount = 7
    static let compactMusicBarWidth: CGFloat = 1.8
}
enum NotchNeonPalette { static let blue = Color.blue }
enum NotchAudioLevelSupport {
    static func barIndex(_ index: Int, of count: Int, bands: Int) -> Int { min(bands - 1, index) }
}
enum NotchMotion { struct Motion { var duration = 0.1 }; static let steadyWidth = Motion() }
struct NotchDeviceFeedback { init?(_ notice: NotchNotice) { return nil }; var tint: Color { .green } }
struct NotchDeviceNoticeEffect: ViewModifier {
    let notice: NotchNotice
    var clearsCamera = false
    func body(content: Content) -> some View { content }
}
enum NotchMascotSupport {
    static let noticeSize: CGFloat = 18
    static func isEnabled() -> Bool { false }
    static func look() -> Int { 0 }
    static func reacts() -> Bool { true }
}
final class NotchService { static let shared = NotchService(); var mascotRestingMood = 0 }
struct NotchMascotView: View {
    let look: Int, mood: Int, size: CGFloat, reaction: NotchMascotReaction?
    var body: some View { Color.red.frame(width: size, height: size) }
}
struct NotchAgentMark: View {
    let provider: AgentProvider, size: CGFloat
    var body: some View { Color.blue.frame(width: size, height: size) }
}
struct NotchNotificationAppIcon: View {
    let app: Int, size: CGFloat
    var body: some View { Color.green.frame(width: size, height: size) }
}
struct NotchMeter: View {
    let value: Double, height: CGFloat, tint: Color
    var body: some View { tint.frame(height: height) }
}
final class NotchMusicService: ObservableObject {
    static let shared = NotchMusicService()
    struct Playback { var track = 0; var isPlaying = true }
    @Published var artwork: Color = .purple
    var playback: Playback? = Playback()
}
// The actual notice/artwork-observer views remain under test. The image itself
// is a deterministic color tile, so network artwork loading cannot affect it.
struct NotchArtwork: View {
    let image: Color, size: CGFloat, source: Int?
    var body: some View { image.frame(width: size, height: size) }
}
struct NotchMusicCover: View {
    let artwork: Color, side: CGFloat, radius: CGFloat, source: Int?
    var body: some View { artwork.frame(width: side, height: side) }
}
PRODUCTION_VIEWS
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    if !condition { print("FAIL: " + message); exit(1) }
}
@MainActor func pixels(_ notice: NotchNotice, capsule: Bool, height: CGFloat = 36) -> [UInt8] {
    let geometry = NotchGeometry(stripHeight: height)
    let view = Group {
        if capsule {
            NotchCapsuleNoticeView(notice: notice, geometry: geometry, size: CGSize(width: 580, height: height))
        } else {
            NotchNoticeView(notice: notice, geometry: geometry)
        }
    }.frame(width: 580, height: height).background(.black)
    let host = NSHostingView(rootView: view)
    let window = NSWindow(contentRect: CGRect(x: -10000, y: -10000, width: 580, height: height),
                          styleMask: .borderless, backing: .buffered, defer: false)
    window.contentView = host
    host.frame = CGRect(x: 0, y: 0, width: 580, height: height)
    host.layoutSubtreeIfNeeded()
    RunLoop.main.run(until: Date().addingTimeInterval(0.03))
    host.layoutSubtreeIfNeeded()
    func equalizers(_ view: NSView) -> [NotchEqualizerView] {
        (view as? NotchEqualizerView).map { [$0] } ?? view.subviews.flatMap { equalizers($0) }
    }
    expect(equalizers(host).count == (notice.event == .track ? 1 : 0),
           "the native equalizer exists only inside the song-change notice")
    let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
    host.cacheDisplay(in: host.bounds, to: bitmap)
    window.contentView = nil
    return Array(UnsafeBufferPointer(start: bitmap.bitmapData!, count: bitmap.bytesPerRow * bitmap.pixelsHigh))
}
MainActor.assumeIsolated {
    _ = NSApplication.shared
    let first = NotchNotice(event: .track, title: "Artist One", detail: "First Song", symbol: "music.note")
    let second = NotchNotice(event: .track, title: "Entirely Different Artist", detail: "Unrelated Track Name", symbol: "music.note")
    for capsule in [false, true] {
        for height: CGFloat in [16, 24, 36, 64] {
            let before = pixels(first, capsule: capsule, height: height)
            expect(before == pixels(second, capsule: capsule, height: height),
                   "automatic track metadata must not be drawn in \(capsule ? "capsule" : "camera") notices at height \(height)")
            NotchMusicService.shared.artwork = .orange
            expect(before != pixels(first, capsule: capsule, height: height),
                   "the actual artwork observer must still draw the new cover")
            NotchMusicService.shared.artwork = .purple
        }
        let normal = NotchNotice(event: .accessory, title: "Connected", detail: "Headphones", symbol: "headphones")
        let changed = NotchNotice(event: .accessory, title: "Disconnected", detail: "Speaker", symbol: "headphones")
        expect(pixels(normal, capsule: capsule) != pixels(changed, capsule: capsule),
               "ordinary notices must retain visible message text")
    }
}
print("PASS: \(checks) track notice render checks")
'''.replace("PRODUCTION_VIEWS", views)

with tempfile.TemporaryDirectory(prefix="notch-track-notice-") as directory:
    path = Path(directory) / "main.swift"
    path.write_text(swift)
    subprocess.run(["xcrun", "swift", str(path)], check=True)
