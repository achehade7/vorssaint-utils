// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import EventKit

/// A calendar read only while `meet` is requested. Closing or changing the
/// query cancels the result; typing never opens a call or requests permission.
final class CommandBarMeetingSearch {
    var onResult: (() -> Void)?
    private var task: Task<Void, Never>?
    private var generation = UUID()
    private var loaded = false
    private var event: NotchCalendarEvent?
    var isAwaiting: Bool { task != nil }

    func reset() {
        generation = UUID()
        task?.cancel()
        task = nil
        loaded = false
        event = nil
    }

    func rows() -> [CommandBarEntry] {
        let strings = FeatureStrings.notchCalendar(L10n.shared.language)
        guard NotchCalendarSupport.isEnabled() else {
            reset()
            return [CommandBarEntry(id: "action.meet.setup", title: strings.title,
                                    subtitle: strings.description, icon: .symbol("calendar"),
                                    countsUsage: false, run: { _ in
                NotchService.shared.openSettings(showing: .calendar)
            })]
        }
        guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else {
            reset()
            return [CommandBarEntry(id: "action.meet.permission", title: strings.allow,
                                    subtitle: strings.permission, icon: .symbol("calendar"),
                                    countsUsage: false, run: { _ in Permissions.shared.requestCalendar() })]
        }
        guard loaded else {
            if task == nil {
                let token = generation
                task = Task { @MainActor [weak self] in
                    let events = await NotchCalendarService.shared.meetingEvents()
                    guard let self, !Task.isCancelled, self.generation == token else { return }
                    self.event = NotchCalendarSupport.nextMeeting(events, now: Date())
                    self.loaded = true
                    self.task = nil
                    self.onResult?()
                }
            }
            return []
        }
        guard let event, event.end > Date(), let url = event.meetingURL else {
            return [CommandBarEntry(id: "action.meet.empty", title: strings.noMeetingLink,
                                    subtitle: strings.openCalendar, icon: .symbol("calendar"),
                                    countsUsage: false, run: { _ in NotchService.shared.open(.calendar) })]
        }
        let start = DateFormatter.localizedString(from: event.start, dateStyle: .short, timeStyle: .short)
        return [CommandBarEntry(id: "action.meet", title: event.title.isEmpty ? strings.untitled : event.title,
                                subtitle: start + " · " + (url.host ?? ""), icon: .symbol("video"),
                                countsUsage: false, run: { _ in
            guard NotchCalendarSupport.isEnabled(), event.end > Date(),
                  EKEventStore.authorizationStatus(for: .event) == .fullAccess else { return }
            NSWorkspace.shared.open(url)
        })]
    }
}
