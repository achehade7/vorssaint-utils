// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

struct SnippetCaptureStrings {
    let save: String, today: String, permanent: String, permanentName: String
    static func localized(_ language: AppLanguage) -> Self {
        switch language {
        case .enUS: return .init(save: "Save snippet", today: "Until midnight", permanent: "Keep permanently", permanentName: "A temporary snippet cannot replace a permanent one")
        case .ptBR: return .init(save: "Salvar trecho", today: "Até meia-noite", permanent: "Manter permanentemente", permanentName: "Um trecho temporário não pode substituir um permanente")
        case .tr: return .init(save: "Parçacığı kaydet", today: "Gece yarısına kadar", permanent: "Kalıcı olarak sakla", permanentName: "Geçici parçacık kalıcı olanın yerini alamaz")
        case .ru: return .init(save: "Сохранить фрагмент", today: "До полуночи", permanent: "Сохранить навсегда", permanentName: "Временный фрагмент не может заменить постоянный")
        case .es: return .init(save: "Guardar fragmento", today: "Hasta medianoche", permanent: "Conservar permanentemente", permanentName: "Un fragmento temporal no puede reemplazar uno permanente")
        case .sk: return .init(save: "Uložiť úryvok", today: "Do polnoci", permanent: "Uchovať natrvalo", permanentName: "Dočasný úryvok nemôže nahradiť trvalý")
        case .de: return .init(save: "Textbaustein speichern", today: "Bis Mitternacht", permanent: "Dauerhaft behalten", permanentName: "Ein temporärer Textbaustein kann keinen dauerhaften ersetzen")
        case .fr: return .init(save: "Enregistrer l’extrait", today: "Jusqu’à minuit", permanent: "Conserver définitivement", permanentName: "Un extrait temporaire ne peut pas remplacer un permanent")
        case .it: return .init(save: "Salva frammento", today: "Fino a mezzanotte", permanent: "Conserva permanentemente", permanentName: "Un frammento temporaneo non può sostituirne uno permanente")
        case .ja: return .init(save: "スニペットを保存", today: "午前0時まで", permanent: "永久に保存", permanentName: "一時スニペットで永久スニペットを置き換えることはできません")
        case .ko: return .init(save: "스니펫 저장", today: "자정까지", permanent: "영구 보관", permanentName: "임시 스니펫은 영구 스니펫을 대체할 수 없습니다")
        case .uk: return .init(save: "Зберегти фрагмент", today: "До опівночі", permanent: "Зберегти назавжди", permanentName: "Тимчасовий фрагмент не може замінити постійний")
        case .zhHans: return .init(save: "保存片段", today: "保留至午夜", permanent: "永久保留", permanentName: "临时片段不能替换永久片段")
        case .zhTW: return .init(save: "儲存片段", today: "保留至午夜", permanent: "永久保留", permanentName: "暫時片段不能取代永久片段")
        case .zhHK: return .init(save: "儲存片段", today: "保留至午夜", permanent: "永久保留", permanentName: "暫時片段不能取代永久片段")
        }
    }
}
