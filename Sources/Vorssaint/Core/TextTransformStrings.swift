// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

enum TextTransformStrings {
    static var title: String { values[0] }
    static var edit: String { values[1] }
    static var hint: String { values[7] }
    static var tooLarge: String { values[8] }
    static func title(for kind: TextTransform.Kind) -> String {
        switch kind {
        case .joinLines: return values[2]
        case .cleanSpacing: return values[3]
        case .formatJSON: return values[4]
        case .decodeURL: return values[5]
        case .decodeBase64: return values[6]
        }
    }
    private static var values: [String] { localized(L10n.shared.language) }
    static func localized(_ language: AppLanguage) -> [String] {
        switch language {
        case .enUS: return ["Text tools", "Edit", "Join lines", "Clean spacing", "Format JSON", "Decode URL", "Decode Base64", "Choose a transformation. The source stays unchanged.", "Text is too large (maximum 256 KB)."]
        case .de: return ["Textwerkzeuge", "Bearbeiten", "Zeilen verbinden", "Abstände bereinigen", "JSON formatieren", "URL dekodieren", "Base64 dekodieren", "Wähle eine Umwandlung. Der Ausgangstext bleibt unverändert.", "Der Text ist zu groß (maximal 256 KB)."]
        case .fr: return ["Outils de texte", "Modifier", "Joindre les lignes", "Nettoyer les espaces", "Formater JSON", "Décoder l’URL", "Décoder Base64", "Choisissez une transformation. Le texte source reste inchangé.", "Le texte est trop volumineux (256 Ko maximum)."]
        case .ptBR: return ["Ferramentas de texto", "Editar", "Unir linhas", "Limpar espaços", "Formatar JSON", "Decodificar URL", "Decodificar Base64", "Escolha uma transformação. O texto original não será alterado.", "O texto é muito grande (máximo de 256 KB)."]
        case .es: return ["Herramientas de texto", "Editar", "Unir líneas", "Limpiar espacios", "Formatear JSON", "Decodificar URL", "Decodificar Base64", "Elige una transformación. El texto original no cambia.", "El texto es demasiado grande (máximo 256 KB)."]
        case .it: return ["Strumenti di testo", "Modifica", "Unisci righe", "Pulisci spazi", "Formatta JSON", "Decodifica URL", "Decodifica Base64", "Scegli una trasformazione. Il testo originale resta invariato.", "Il testo è troppo grande (massimo 256 KB)."]
        case .tr: return ["Metin araçları", "Düzenle", "Satırları birleştir", "Boşlukları temizle", "JSON biçimlendir", "URL çöz", "Base64 çöz", "Bir dönüşüm seçin. Kaynak metin değişmez.", "Metin çok büyük (en fazla 256 KB)."]
        case .sk: return ["Textové nástroje", "Upraviť", "Spojiť riadky", "Vyčistiť medzery", "Formátovať JSON", "Dekódovať URL", "Dekódovať Base64", "Vyberte transformáciu. Zdrojový text zostane nezmenený.", "Text je príliš veľký (najviac 256 KB)."]
        case .ru: return ["Инструменты текста", "Изменить", "Объединить строки", "Убрать лишние пробелы", "Форматировать JSON", "Декодировать URL", "Декодировать Base64", "Выберите преобразование. Исходный текст не изменится.", "Текст слишком большой (не более 256 КБ)."]
        case .uk: return ["Інструменти тексту", "Редагувати", "Об’єднати рядки", "Прибрати зайві пробіли", "Форматувати JSON", "Декодувати URL", "Декодувати Base64", "Виберіть перетворення. Початковий текст не зміниться.", "Текст завеликий (щонайбільше 256 КБ)."]
        case .ja: return ["テキストツール", "編集", "行を結合", "空白を整理", "JSONを整形", "URLをデコード", "Base64をデコード", "変換を選択してください。元のテキストは変更されません。", "テキストが大きすぎます（最大256 KB）。"]
        case .ko: return ["텍스트 도구", "편집", "줄 합치기", "공백 정리", "JSON 서식 지정", "URL 디코딩", "Base64 디코딩", "변환을 선택하세요. 원본 텍스트는 변경되지 않습니다.", "텍스트가 너무 큽니다(최대 256 KB)."]
        case .zhHans: return ["文本工具", "编辑", "合并行", "清理空格", "格式化 JSON", "解码 URL", "解码 Base64", "选择转换方式。原始文本保持不变。", "文本过大（最大 256 KB）。"]
        case .zhTW, .zhHK: return ["文字工具", "編輯", "合併行", "清理空格", "格式化 JSON", "解碼 URL", "解碼 Base64", "選擇轉換方式。原始文字保持不變。", "文字過大（最大 256 KB）。"]
        }
    }
}
