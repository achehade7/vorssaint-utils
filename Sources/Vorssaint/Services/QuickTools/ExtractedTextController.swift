// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// Extracted text uses the same compact transform/editor surface as selected text.
enum ExtractedTextController {
    static func show(image: CGImage) { TextTransformController.show(image: image) }
    static func show(text: String) { TextTransformController.show(text: text, editing: true) }
}
