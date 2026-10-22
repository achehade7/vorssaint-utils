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
    private var events: [NotchCalendarEvent] = []
    var isAwaiting: Bool { task != nil }

    func reset() {
        generation = UUID()
        task?.cancel()
        task = nil
        loaded = false
        events = []
    }

    func noteEvent(entryID: String) -> NotchCalendarEvent? {
        guard NotchCalendarSupport.isEnabled(),
              EKEventStore.authorizationStatus(for: .event) == .fullAccess else { return nil }
        return events.first { "action.meet." + $0.id == entryID && $0.end > Date() && $0.meetingURL != nil }
    }

    func rows(limit: Int = 1) -> [CommandBarEntry] {
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
                    self.events = events
                    self.loaded = true
                    self.task = nil
                    self.onResult?()
                }
            }
            return []
        }
        let now = Date()
        let meetings = NotchCalendarSupport.upcoming(events, now: now)
            .filter { !$0.allDay && $0.meetingURL != nil }.prefix(limit)
        guard !meetings.isEmpty else {
            return [CommandBarEntry(id: "action.meet.empty", title: strings.noMeetingLink,
                                    subtitle: strings.openCalendar, icon: .symbol("calendar"),
                                    countsUsage: false, run: { _ in NotchService.shared.open(.calendar) })]
        }
        return meetings.map { event in
            let url = event.meetingURL!
            let start = DateFormatter.localizedString(from: event.start, dateStyle: .short, timeStyle: .short)
            let relative: String
            if event.start <= now { relative = strings.ongoing }
            else {
                let formatter = RelativeDateTimeFormatter()
                formatter.locale = Locale(identifier: L10n.shared.language.rawValue)
                formatter.unitsStyle = .short
                relative = formatter.localizedString(for: event.start, relativeTo: now)
            }
            return CommandBarEntry(id: "action.meet." + event.id,
                                    title: event.title.isEmpty ? strings.untitled : event.title,
                                    subtitle: relative + " · " + start + " · " + (url.host ?? ""),
                                    icon: .symbol("video"), countsUsage: false, run: { _ in
                guard NotchCalendarSupport.isEnabled(), event.end > Date(),
                      EKEventStore.authorizationStatus(for: .event) == .fullAccess else { return }
                NSWorkspace.shared.open(url)
            })
        }
    }
}
