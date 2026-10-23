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
        let now = Date()
        return events.first { "action.meet." + $0.id == entryID && Self.isSuggested($0, now: now) && $0.meetingURL != nil }
    }

    private static func isSuggested(_ event: NotchCalendarEvent, now: Date) -> Bool {
        !event.allDay && event.end > now && event.start.timeIntervalSince(now) >= -300
    }

    func rows(limit: Int = 3, noteFilter: String? = nil) -> [CommandBarEntry] {
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
            .filter { event in Self.isSuggested(event, now: now) && (noteFilter != nil || event.meetingURL != nil)
                && (noteFilter.map { CommandBarNoteSearch.matches(event.title, filter: $0) } ?? true) }.prefix(limit)
        guard !meetings.isEmpty else {
            return [CommandBarEntry(id: "action.meet.empty", title: noteFilter == nil ? strings.noMeetingLink : FeatureStrings.commandBar(L10n.shared.language).noResultsTitle,
                                    subtitle: strings.openCalendar, icon: .symbol("calendar"),
                                    countsUsage: false, run: { _ in NotchService.shared.open(.calendar) })]
        }
        return meetings.map { event in
            let start = DateFormatter.localizedString(from: event.start, dateStyle: .short, timeStyle: .short)
            let remaining = event.start.timeIntervalSince(now)
            let formatter = RelativeDateTimeFormatter()
            formatter.locale = Locale(identifier: L10n.shared.language.rawValue)
            formatter.unitsStyle = .short
            let relative: String
            if remaining <= 0 {
                let minutes = Int(-remaining / 60)
                let elapsed = minutes == 0 ? nil : formatter.localizedString(from: DateComponents(minute: -minutes))
                relative = MeetingNoteStrings.started(elapsed, L10n.shared.language)
            } else if remaining < 3600 {
                relative = formatter.localizedString(from: DateComponents(minute: Int(ceil(remaining / 60))))
            } else {
                relative = formatter.localizedString(for: event.start, relativeTo: now)
            }
            return CommandBarEntry(id: (noteFilter == nil ? "action.meet." : "action.note.upcoming.") + event.id,
                                    title: event.title.isEmpty ? strings.untitled : event.title,
                                    subtitle: relative + " · " + start + " · " + (noteFilter == nil ? (event.meetingURL?.host ?? "") : MeetingNoteStrings.localized(L10n.shared.language).title),
                                    icon: .symbol(noteFilter == nil ? "video" : "doc.text"), countsUsage: false, run: { _ in
                guard NotchCalendarSupport.isEnabled(), Self.isSuggested(event, now: Date()),
                      EKEventStore.authorizationStatus(for: .event) == .fullAccess else { return }
                if noteFilter != nil { MeetingNoteService.shared.show(event, joining: false) }
                else if let url = event.meetingURL { NSWorkspace.shared.open(url) }
            })
        }
    }
}
