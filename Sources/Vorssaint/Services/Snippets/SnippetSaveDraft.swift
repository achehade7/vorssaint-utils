// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import Combine

/// Owns the OCR result, independent of later clipboard changes. Replacement
/// confirmation is bound to the exact existing snippet and the current draft.
final class SnippetSaveDraft: ObservableObject {
    @Published var name = "" { didSet { resetConfirmation() } }
    @Published var text: String { didSet { resetConfirmation() } }
    @Published var temporary = true { didSet { resetConfirmation() } }
    @Published private(set) var replacement: TextSnippet?
    @Published private(set) var error: TextSnippetSupport.SaveFailure?
    private let defaults: UserDefaults

    init(text: String, defaults: UserDefaults = .standard) { self.text = text; self.defaults = defaults }
    var canSave: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    private func resetConfirmation() { replacement = nil; error = nil }

    /// false keeps the draft open for confirmation or correction. No clipboard IO.
    func save() -> Bool {
        guard canSave else { return false }
        let data = defaults.data(forKey: DefaultsKey.textSnippets)
        let matches = TextSnippetSupport.named(name.trimmingCharacters(in: .whitespacesAndNewlines),
                                               in: TextSnippetSupport.decode(data))
        if matches.count > 1 { error = .changed; return false }
        if temporary, let existing = matches.first, existing.expiresAt == nil {
            error = .permanentName; return false
        }
        if let replacement, matches.first != replacement {
            self.replacement = nil; error = .changed; return false
        }
        if replacement == nil, let existing = matches.first {
            replacement = existing; error = nil; return false
        }
        do {
            let saved = try TextSnippetSupport.saving(name: name, text: text, temporary: temporary,
                                                      expected: replacement, data: data)
            defaults.set(saved, forKey: DefaultsKey.textSnippets)
            return true
        } catch { self.error = (error as? TextSnippetSupport.SaveFailure) ?? .changed; return false }
    }
}
