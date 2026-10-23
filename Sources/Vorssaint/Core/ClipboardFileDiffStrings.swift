// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

struct ClipboardFileDiffStrings {
    let title, hint, dropFile, shelf, clear, unsupported, unreadable: String
    static func localized(_ language: AppLanguage) -> Self {
        let values: [String]
        switch language {
        case .enUS: values = ["Compare text files", "One file per side, or drop two together", "Drop a text file", "Keep on shelf", "Clear comparison", "Use UTF-8 text files. Nothing was changed.", "Couldn’t read this file. Nothing was changed."]
        case .ptBR: values = ["Comparar arquivos de texto", "Um arquivo por lado ou dois juntos", "Solte um arquivo de texto", "Guardar na estante", "Limpar comparação", "Use arquivos de texto UTF-8. Nada foi alterado.", "Não foi possível ler o arquivo. Nada foi alterado."]
        case .tr: values = ["Metin dosyalarını karşılaştır", "Her tarafa bir veya birlikte iki dosya bırakın", "Bir metin dosyası bırakın", "Rafa ekle", "Karşılaştırmayı temizle", "UTF-8 metin dosyaları kullanın. Hiçbir şey değiştirilmedi.", "Dosya okunamadı. Hiçbir şey değiştirilmedi."]
        case .ru: values = ["Сравнить текстовые файлы", "По файлу с каждой стороны или два сразу", "Перетащите текстовый файл", "Сохранить на полке", "Очистить сравнение", "Используйте текст UTF-8. Ничего не изменено.", "Не удалось прочитать файл. Ничего не изменено."]
        case .es: values = ["Comparar archivos de texto", "Un archivo por lado, o dos juntos", "Suelta un archivo de texto", "Guardar en la bandeja", "Borrar comparación", "Usa archivos de texto UTF-8. Nada ha cambiado.", "No se pudo leer el archivo. Nada ha cambiado."]
        case .sk: values = ["Porovnať textové súbory", "Jeden súbor na stranu alebo dva naraz", "Presuňte textový súbor", "Ponechať na poličke", "Vymazať porovnanie", "Použite textové súbory UTF-8. Nič sa nezmenilo.", "Súbor sa nepodarilo prečítať. Nič sa nezmenilo."]
        case .de: values = ["Textdateien vergleichen", "Eine Datei pro Seite oder zwei zusammen", "Textdatei hier ablegen", "In der Ablage behalten", "Vergleich leeren", "UTF-8-Textdateien verwenden. Nichts wurde geändert.", "Datei konnte nicht gelesen werden. Nichts wurde geändert."]
        case .fr: values = ["Comparer des fichiers texte", "Un fichier par côté, ou deux ensemble", "Déposez un fichier texte", "Garder sur l’étagère", "Effacer la comparaison", "Utilisez des fichiers texte UTF-8. Rien n’a changé.", "Impossible de lire le fichier. Rien n’a changé."]
        case .it: values = ["Confronta file di testo", "Un file per lato, oppure due insieme", "Trascina un file di testo", "Conserva sullo scaffale", "Cancella confronto", "Usa file di testo UTF-8. Nessuna modifica.", "Impossibile leggere il file. Nessuna modifica."]
        case .ja: values = ["テキストファイルを比較", "各側に1つ、または2つ同時にドロップ", "テキストファイルをドロップ", "シェルフに保存", "比較をクリア", "UTF-8のテキストファイルを使用してください。変更はありません。", "ファイルを読み取れませんでした。変更はありません。"]
        case .ko: values = ["텍스트 파일 비교", "각 쪽에 하나 또는 두 파일을 함께 놓기", "텍스트 파일 놓기", "선반에 보관", "비교 지우기", "UTF-8 텍스트 파일을 사용하세요. 변경 사항이 없습니다.", "파일을 읽을 수 없습니다. 변경 사항이 없습니다."]
        case .uk: values = ["Порівняти текстові файли", "По файлу з кожного боку або два разом", "Перетягніть текстовий файл", "Зберегти на полиці", "Очистити порівняння", "Використовуйте текст UTF-8. Нічого не змінено.", "Не вдалося прочитати файл. Нічого не змінено."]
        case .zhHans: values = ["比较文本文件", "每侧放一个文件，或同时放入两个", "拖入文本文件", "保留在暂存架", "清除比较", "请使用 UTF-8 文本文件。内容未更改。", "无法读取文件。内容未更改。"]
        case .zhTW, .zhHK: values = ["比較文字檔案", "每側放一個檔案，或同時放入兩個", "拖入文字檔案", "保留在暫存架", "清除比較", "請使用 UTF-8 文字檔案。內容未變更。", "無法讀取檔案。內容未變更。"]
        }
        return Self(title: values[0], hint: values[1], dropFile: values[2], shelf: values[3], clear: values[4], unsupported: values[5], unreadable: values[6])
    }
}
