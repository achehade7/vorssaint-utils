// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

struct MeetingNoteStrings {
    let title: String, join: String, ready: String, created: String, failed: String
    static func startsIn(_ duration: String, _ language: AppLanguage) -> String {
        switch language {
        case .enUS, .de: return "in \(duration)"
        case .ptBR: return "em \(duration)"
        case .tr: return "\(duration) sonra"
        case .ru: return "через \(duration)"
        case .es: return "en \(duration)"
        case .sk: return "o \(duration)"
        case .fr: return "dans \(duration)"
        case .it: return "tra \(duration)"
        case .ja: return "\(duration)後"
        case .ko: return "\(duration) 후"
        case .uk: return "через \(duration)"
        case .zhHans: return "\(duration)后"
        case .zhTW, .zhHK: return "\(duration)後"
        }
    }
    static func started(_ elapsed: String?, _ language: AppLanguage) -> String {
        switch language {
        case .enUS: return elapsed.map { "Started \($0)" } ?? "Just started"
        case .ptBR: return elapsed.map { "Começou \($0)" } ?? "Acabou de começar"
        case .tr: return elapsed.map { "Başladı: \($0)" } ?? "Az önce başladı"
        case .ru: return elapsed.map { "Началось \($0)" } ?? "Только что началось"
        case .es: return elapsed.map { "Empezó \($0)" } ?? "Acaba de empezar"
        case .sk: return elapsed.map { "Začalo sa \($0)" } ?? "Práve sa začalo"
        case .de: return elapsed.map { "Begonnen: \($0)" } ?? "Gerade begonnen"
        case .fr: return elapsed.map { "A commencé \($0)" } ?? "Vient de commencer"
        case .it: return elapsed.map { "Iniziata \($0)" } ?? "Appena iniziata"
        case .ja: return elapsed.map { "\($0)に開始" } ?? "開始したばかり"
        case .ko: return elapsed.map { "\($0) 시작" } ?? "방금 시작"
        case .uk: return elapsed.map { "Почалося \($0)" } ?? "Щойно почалося"
        case .zhHans: return elapsed.map { "开始于\($0)" } ?? "刚刚开始"
        case .zhTW, .zhHK: return elapsed.map { "開始於\($0)" } ?? "剛剛開始"
        }
    }
    static func readFailure(_ language: AppLanguage) -> String {
        switch language {
        case .enUS: return "Could not read meeting notes"
        case .ptBR: return "Não foi possível ler as notas das reuniões"
        case .tr: return "Toplantı notları okunamadı"
        case .ru: return "Не удалось прочитать заметки встреч"
        case .es: return "No se pudieron leer las notas de reuniones"
        case .sk: return "Poznámky zo stretnutí sa nepodarilo načítať"
        case .de: return "Besprechungsnotizen konnten nicht gelesen werden"
        case .fr: return "Impossible de lire les notes de réunion"
        case .it: return "Impossibile leggere le note delle riunioni"
        case .ja: return "会議メモを読み込めませんでした"
        case .ko: return "회의 메모를 읽을 수 없습니다"
        case .uk: return "Не вдалося прочитати нотатки зустрічей"
        case .zhHans: return "无法读取会议笔记"
        case .zhTW: return "無法讀取會議筆記"
        case .zhHK: return "無法讀取會議筆記"
        }
    }
    static func createQuestion(_ language: AppLanguage) -> String {
        switch language {
        case .enUS: return "Create meeting note?"
        case .ptBR: return "Criar nota da reunião?"
        case .tr: return "Toplantı notu oluşturulsun mu?"
        case .ru: return "Создать заметку встречи?"
        case .es: return "¿Crear nota de reunión?"
        case .sk: return "Vytvoriť poznámku zo stretnutia?"
        case .de: return "Besprechungsnotiz erstellen?"
        case .fr: return "Créer une note de réunion ?"
        case .it: return "Creare una nota della riunione?"
        case .ja: return "会議メモを作成しますか？"
        case .ko: return "회의 메모를 만들까요?"
        case .uk: return "Створити нотатку зустрічі?"
        case .zhHans: return "创建会议笔记？"
        case .zhTW, .zhHK: return "建立會議筆記？"
        }
    }
    static func createAndOpen(_ language: AppLanguage) -> String {
        switch language {
        case .enUS: return "Create & open"
        case .ptBR: return "Criar e abrir"
        case .tr: return "Oluştur ve aç"
        case .ru: return "Создать и открыть"
        case .es: return "Crear y abrir"
        case .sk: return "Vytvoriť a otvoriť"
        case .de: return "Erstellen & öffnen"
        case .fr: return "Créer et ouvrir"
        case .it: return "Crea e apri"
        case .ja: return "作成して開く"
        case .ko: return "만들고 열기"
        case .uk: return "Створити й відкрити"
        case .zhHans: return "创建并打开"
        case .zhTW, .zhHK: return "建立並開啟"
        }
    }
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
