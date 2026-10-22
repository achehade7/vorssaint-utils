// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import Combine

/// Nothing is written until confirmation. Failure retains the editable topic.
final class MeetingNoteDraft: ObservableObject {
    let input: MeetingNoteInput
    @Published var topic: String
    @Published private(set) var saving = false
    @Published private(set) var failed = false
    private(set) var cancelled = false
    private let store: MeetingNoteStore
    private let io = DispatchQueue(label: "Vorssaint.meeting-note", qos: .userInitiated)

    init(input: MeetingNoteInput, store: MeetingNoteStore) {
        self.input = input; self.store = store
        topic = MeetingNoteStore.suggestedTopic(input)
    }

    var fileName: String {
        MeetingNoteStore.date(input.start, format: "yyyy-MM-dd") + " "
            + MeetingNoteStore.topic(topic, people: input.people) + ".md"
    }

    @discardableResult func cancel() -> Bool {
        guard !saving else { return false }
        cancelled = true
        return true
    }

    func save(allowed: Bool, completion: @escaping (MeetingNoteStore.Prepared?) -> Void) {
        guard !saving, !cancelled else { return }
        guard allowed else { failed = true; completion(nil); return }
        saving = true; failed = false
        let store = store, input = input, topic = topic
        io.async { [weak self] in
            let file = try? store.prepare(input, topic: topic)
            DispatchQueue.main.async {
                guard let self else { return }
                self.saving = false; self.failed = file == nil
                completion(file)
            }
        }
    }
}
