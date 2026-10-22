// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

struct MeetingNoteStrings {
    let title: String, join: String, ready: String, created: String, failed: String
    static func localized(_ language: AppLanguage) -> Self {
        switch language {
        case .enUS: return .init(title: "Meeting note", join: "Prepare & join", ready: "Note ready", created: "Note created", failed: "Could not prepare the note. Nothing was opened.")
        case .ptBR: return .init(title: "Nota da reunião", join: "Preparar e entrar", ready: "Nota pronta", created: "Nota criada", failed: "Não foi possível preparar a nota. Nada foi aberto.")
        case .tr: return .init(title: "Toplantı notu", join: "Hazırla ve katıl", ready: "Not hazır", created: "Not oluşturuldu", failed: "Not hazırlanamadı. Hiçbir şey açılmadı.")
        case .ru: return .init(title: "Заметка встречи", join: "Создать и войти", ready: "Заметка готова", created: "Заметка создана", failed: "Не удалось подготовить заметку. Ничего не открыто.")
        case .es: return .init(title: "Nota de reunión", join: "Preparar y unirse", ready: "Nota lista", created: "Nota creada", failed: "No se pudo preparar la nota. No se abrió nada.")
        case .sk: return .init(title: "Poznámka zo stretnutia", join: "Pripraviť a pripojiť", ready: "Poznámka pripravená", created: "Poznámka vytvorená", failed: "Poznámku sa nepodarilo pripraviť. Nič sa neotvorilo.")
        case .de: return .init(title: "Besprechungsnotiz", join: "Vorbereiten & beitreten", ready: "Notiz bereit", created: "Notiz erstellt", failed: "Die Notiz konnte nicht vorbereitet werden. Nichts wurde geöffnet.")
        case .fr: return .init(title: "Note de réunion", join: "Préparer et rejoindre", ready: "Note prête", created: "Note créée", failed: "Impossible de préparer la note. Rien n’a été ouvert.")
        case .it: return .init(title: "Nota della riunione", join: "Prepara e partecipa", ready: "Nota pronta", created: "Nota creata", failed: "Impossibile preparare la nota. Non è stato aperto nulla.")
        case .ja: return .init(title: "会議メモ", join: "準備して参加", ready: "メモを準備しました", created: "メモを作成しました", failed: "メモを準備できませんでした。何も開いていません。")
        case .ko: return .init(title: "회의 메모", join: "준비하고 참여", ready: "메모 준비 완료", created: "메모 생성 완료", failed: "메모를 준비하지 못했습니다. 아무것도 열지 않았습니다.")
        case .uk: return .init(title: "Нотатка зустрічі", join: "Підготувати й приєднатися", ready: "Нотатка готова", created: "Нотатку створено", failed: "Не вдалося підготувати нотатку. Нічого не відкрито.")
        case .zhHans: return .init(title: "会议笔记", join: "准备并加入", ready: "笔记已准备好", created: "笔记已创建", failed: "无法准备笔记。未打开任何内容。")
        case .zhTW: return .init(title: "會議筆記", join: "準備並加入", ready: "筆記已準備好", created: "筆記已建立", failed: "無法準備筆記。未開啟任何內容。")
        case .zhHK: return .init(title: "會議筆記", join: "準備並加入", ready: "筆記已準備好", created: "筆記已建立", failed: "無法準備筆記。未開啟任何內容。")
        }
    }
}
