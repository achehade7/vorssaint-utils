// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// Command Bar access to the existing snippet store. Reading the clipboard
/// happens only on Return, on the shared pasteboard lane, never while typing.
enum CommandBarSnippetCommands {
    private static var strings: SnippetFeatureStrings { FeatureStrings.snippets(L10n.shared.language) }

    static func preview(_ snippet: TextSnippet) -> String {
        // Show the saved template literally: previewing never expands clipboard variables.
        String(snippet.replacement.prefix(240)).components(separatedBy: .newlines)
            .filter { !$0.isEmpty }.joined(separator: " · ")
    }

    static func rows(for query: String) -> [CommandBarEntry]? {
        guard AppFeature.textSnippets.isAvailable else { return nil }
        let parts = query.split(maxSplits: 2, whereSeparator: { $0.isWhitespace }).map(String.init)
        guard parts.first?.lowercased() == "snip" else { return nil }
        if parts.count == 1 {
            return [CommandBarEntry(id: "action.snippetLibrary", title: strings.libraryTitle,
                                    subtitle: strings.saveClipboardHint, icon: .symbol("text.append"),
                                    run: { _ in
                                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
                                            SnippetLibraryService.shared.show()
                                        }
                                    })]
        }
        if parts.count == 2, parts[1].lowercased() == "last" {
            if let id = UserDefaults.standard.string(forKey: DefaultsKey.lastUsedSnippetID),
               let last = snippet(for: "snippet." + id) {
                return [CommandBarEntry(id: "snippet." + last.id.uuidString, title: last.name,
                                        subtitle: preview(last), icon: .symbol("text.append"),
                                        run: { _ in copy(last) })]
            }
            return [CommandBarEntry(id: "action.snippetLast.empty", title: strings.libraryNoResults,
                                    subtitle: strings.libraryTitle, icon: .symbol("text.append"),
                                    countsUsage: false, keepsBarOpen: true, run: { _ in })]
        }
        guard parts[1].lowercased() == "save", parts.count == 3,
              !parts[2].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return [CommandBarEntry(id: "action.snippetSaveHelp", title: strings.saveClipboardHint,
                                    subtitle: strings.pageTitle, icon: .symbol("text.badge.plus"),
                                    countsUsage: false, keepsBarOpen: true, run: { _ in })]
        }
        let name = parts[2].trimmingCharacters(in: .whitespacesAndNewlines)
        let matches = matching(name, in: TextSnippetSupport.decode(UserDefaults.standard.data(forKey: DefaultsKey.textSnippets)))
        let expected = matches.first
        return [CommandBarEntry(id: "action.snippetSave", title: name,
                                subtitle: strings.saveClipboardHint, icon: .symbol("text.badge.plus"),
                                confirmationPrompt: expected.map { String(format: strings.replaceClipboardFormat, $0.name) },
                                countsUsage: false, keepsBarOpen: true,
                                run: { _ in save(name: name, expected: expected) })]
    }

    private static func matching(_ name: String, in snippets: [TextSnippet]) -> [TextSnippet] {
        snippets.filter { $0.name.trimmingCharacters(in: .whitespacesAndNewlines)
            .compare(name, options: .caseInsensitive) == .orderedSame }
    }

    private static func save(name: String, expected: TextSnippet?) {
        let bar = CommandBarService.shared
        let presentation = bar.presentationID, query = bar.query, mode = bar.mode
        GeneralPasteboardAccess.shared.async({ NSPasteboard.general.string(forType: .string) }, then: { text in
            guard AppFeature.textSnippets.isAvailable, bar.isVisible,
                  bar.presentationID == presentation, bar.query == query, bar.mode == mode else { return }
            guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                QuickToolHUD.show(icon: "exclamationmark.circle", message: strings.clipboardEmpty)
                return
            }
            let data = UserDefaults.standard.data(forKey: DefaultsKey.textSnippets)
            // A damaged store must not be replaced by a new one-item library.
            if let data, (try? JSONDecoder().decode([TextSnippet].self, from: data)) == nil {
                QuickToolHUD.show(icon: "exclamationmark.circle", message: strings.clipboardChanged)
                return
            }
            var snippets = TextSnippetSupport.decode(data)
            let matches = matching(name, in: snippets)
            guard matches.count <= 1, matches.first == expected else {
                QuickToolHUD.show(icon: "exclamationmark.circle", message: strings.clipboardChanged)
                return
            }
            var saved = expected ?? TextSnippet()
            saved.name = name
            saved.replacement = text
            if let index = snippets.firstIndex(where: { $0.id == saved.id }) { snippets[index] = saved }
            else { snippets.append(saved) }
            guard let encoded = TextSnippetSupport.encode(snippets) else { return }
            UserDefaults.standard.set(encoded, forKey: DefaultsKey.textSnippets)
            TextSnippetService.shared.syncWithPreferences()
            SnippetLibraryService.shared.syncWithPreferences()
            bar.hide()
            QuickToolHUD.show(icon: "checkmark", message: strings.clipboardSaved)
        })
    }

    static func snippet(for entryID: String) -> TextSnippet? {
        guard AppFeature.textSnippets.isAvailable, entryID.hasPrefix("snippet."),
              let id = UUID(uuidString: String(entryID.dropFirst("snippet.".count))) else { return nil }
        return TextSnippetSupport.decode(UserDefaults.standard.data(forKey: DefaultsKey.textSnippets))
            .first { $0.id == id && $0.enabled }
    }

    static func insert(entryID: String) {
        guard let snippet = snippet(for: entryID) else { return }
        SnippetLibraryService.shared.insert(snippet)
    }

    static func copy(_ snippet: TextSnippet) {
        SnippetLibraryService.shared.resolveTemplate(snippet, action: .copy) { copyResolved($0) }
    }

    private static func copyResolved(_ snippet: TextSnippet) {
        GeneralPasteboardAccess.shared.async({
            let clipboard = TextSnippetSupport.needsClipboard(snippet.replacement)
                ? NSPasteboard.general.string(forType: .string) : nil
            let text = TextSnippetSupport.expand(snippet.replacement, date: Date(), clipboard: clipboard)
            NSPasteboard.general.clearContents()
            NSPasteboard.general.declareVorssaintSource()
            return NSPasteboard.general.setString(text, forType: .string)
        }, then: { copied in
            if copied { UserDefaults.standard.set(snippet.id.uuidString, forKey: DefaultsKey.lastUsedSnippetID) }
            QuickToolHUD.show(icon: copied ? "doc.on.doc" : "exclamationmark.circle",
                              message: copied ? snippet.name : FeatureStrings.commandBar(L10n.shared.language).copyFailed)
        })
    }
}
