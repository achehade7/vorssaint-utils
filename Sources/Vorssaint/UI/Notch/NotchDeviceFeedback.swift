// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import SwiftUI

/// These cues decorate existing, confirmed device notices. They neither
/// observe devices nor infer a call app's private microphone state.
enum NotchDeviceFeedback: Equatable {
    case headphones, microphoneMuted, microphoneLive

    init?(_ notice: NotchNotice) {
        if notice.event == .accessory, notice.audioHandoff,
           ["headphones", "airpods", "airpodspro", "airpodsmax"].contains(notice.symbol) {
            self = .headphones
        } else if notice.event == .microphone, notice.symbol == "mic.slash.fill" {
            self = .microphoneMuted
        } else if notice.event == .microphone, notice.symbol == "mic.fill" {
            self = .microphoneLive
        } else {
            return nil
        }
    }

    var tint: Color {
        switch self {
        case .headphones: return Color(red: 0.72, green: 0.46, blue: 1)
        case .microphoneMuted: return .orange
        case .microphoneLive: return Color(red: 0.44, green: 0.61, blue: 1)
        }
    }

    var duration: TimeInterval { self == .headphones ? NotchEvent.accessory.duration : NotchEvent.microphone.duration }

    func arrival(at age: TimeInterval) -> Double { min(1, max(0, age / 0.22)) }

    func departure(at age: TimeInterval) -> Double {
        self == .headphones ? min(1, max(0, (age - (duration - 0.6)) / 0.6)) : 0
    }

    func light(at age: TimeInterval) -> Double {
        guard age >= 0, age < 0.85 else { return 0 }
        return sin(.pi * age / 0.85)
    }
}

/// One short timeline per device notice; other notices have no extra clock.
/// The light stays inside the strip, including fullscreen and camera displays.
struct NotchDeviceNoticeEffect: ViewModifier {
    let notice: NotchNotice
    var clearsCamera = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var beganAt = Date()
    @State private var running = false

    func body(content: Content) -> some View {
        if let cue = NotchDeviceFeedback(notice) {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !running || reduceMotion)) { context in
                let age = context.date.timeIntervalSince(beganAt)
                let arrival = reduceMotion ? 1 : cue.arrival(at: age)
                let departure = reduceMotion ? 0 : cue.departure(at: age)
                content
                    .offset(x: cue == .headphones ? -5 * (1 - arrival) : 0)
                    .opacity(cue == .headphones ? arrival * (1 - departure) : 1)
                    .colorMultiply(Color(red: 1 - 0.28 * departure, green: 1 - 0.54 * departure, blue: 1))
                    .overlay(alignment: .bottom) {
                        if cue != .headphones, !reduceMotion, running {
                            GeometryReader { proxy in
                                let sweep = min(1, max(0, age / 0.65))
                                let split = clearsCamera && cue == .microphoneLive
                                ForEach(0..<(split ? 2 : 1), id: \.self) { side in
                                    Capsule()
                                        .fill(LinearGradient(colors: [.clear, cue.tint, .white, cue.tint, .clear],
                                                             startPoint: .leading, endPoint: .trailing))
                                        .frame(width: min(split ? 28 : 48, proxy.size.width * 0.2), height: 1.5)
                                        .shadow(color: cue.tint.opacity(0.6), radius: 2)
                                        .position(x: cue == .microphoneMuted
                                            ? 20 + (proxy.size.width - 40) * sweep
                                            : split ? (side == 0 ? 20 : proxy.size.width - 20) : proxy.size.width / 2,
                                                  y: proxy.size.height - 3)
                                        .opacity(cue.light(at: age))
                                }
                            }
                            .allowsHitTesting(false)
                            .accessibilityHidden(true)
                        }
                    }
                    .clipped()
            }
            .task(id: notice) {
                beganAt = Date()
                running = true
                do { try await Task.sleep(nanoseconds: UInt64(cue.duration * 1_000_000_000)) }
                catch { return }
                running = false
            }
        } else {
            content
        }
    }
}
