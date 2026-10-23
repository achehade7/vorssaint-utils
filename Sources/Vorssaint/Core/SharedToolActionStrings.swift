// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

enum SharedToolActionStrings {
    static var actions: String { values[0] }
    static var filter: String { values[1] }
    static var inspect: String { values[2] }
    static var before: String { values[3] }
    static var after: String { values[4] }
    static var extract: String { values[5] }
    static var annotate: String { values[6] }
    static var replace: String { values[7] }
    static var cancel: String { values[8] }
    static func replaceTitle(side: String) -> String { String(format: values[9], side) }
    static var replaceMessage: String { values[10] }
    static var inspectorReplaceTitle: String { values[11] }
    static var inspectorReplaceMessage: String { values[10] }
    static var editableHint: String { values[12] }
    static var unavailable: String { values[13] }
    static var loading: String { values[14] }
    private static var values: [String] { localized(L10n.shared.language) }
    static var selectionNeedsAccessibility: String { selectionMessages[0] }
    static var selectionUnavailable: String { selectionMessages[1] }
    static var selectionSecureInput: String { selectionMessages[2] }

    private static var selectionMessages: [String] {
        switch L10n.shared.language {
        case .enUS: return ["Allow Accessibility for Vorssaint to read selected text.", "Select text in the current app. Some apps do not expose their selection.", "Actions are unavailable while secure input is active."]
        case .de: return ["Erlaube Vorssaint Bedienungshilfen, um ausgewählten Text zu lesen.", "Wähle Text in der aktuellen App aus. Manche Apps geben ihre Auswahl nicht frei.", "Aktionen sind bei sicherer Eingabe nicht verfügbar."]
        case .fr: return ["Autorisez l’accessibilité pour que Vorssaint lise le texte sélectionné.", "Sélectionnez du texte dans l’app actuelle. Certaines apps ne transmettent pas leur sélection.", "Les actions sont indisponibles pendant la saisie sécurisée."]
        case .ptBR: return ["Permita Acessibilidade para o Vorssaint ler o texto selecionado.", "Selecione texto no app atual. Alguns apps não fornecem a seleção.", "As ações não estão disponíveis durante a entrada segura."]
        case .es: return ["Permite Accesibilidad para que Vorssaint lea el texto seleccionado.", "Selecciona texto en la app actual. Algunas apps no exponen su selección.", "Las acciones no están disponibles durante la entrada segura."]
        case .it: return ["Consenti Accessibilità per leggere il testo selezionato con Vorssaint.", "Seleziona testo nell’app attuale. Alcune app non espongono la selezione.", "Le azioni non sono disponibili durante l’inserimento sicuro."]
        case .tr: return ["Seçili metni okuyabilmesi için Vorssaint’a Erişilebilirlik izni verin.", "Geçerli uygulamada metin seçin. Bazı uygulamalar seçimi paylaşmaz.", "Güvenli giriş etkinken eylemler kullanılamaz."]
        case .sk: return ["Povoľte Prístupnosť, aby Vorssaint mohol čítať vybraný text.", "Vyberte text v aktuálnej aplikácii. Niektoré aplikácie výber neposkytujú.", "Akcie nie sú dostupné počas zabezpečeného zadávania."]
        case .ru: return ["Разрешите Универсальный доступ, чтобы Vorssaint читал выделенный текст.", "Выделите текст в текущем приложении. Некоторые приложения не предоставляют выделение.", "Действия недоступны при защищённом вводе."]
        case .uk: return ["Дозвольте Доступність, щоб Vorssaint читав вибраний текст.", "Виберіть текст у поточній програмі. Деякі програми не надають вибраний текст.", "Дії недоступні під час захищеного введення."]
        case .ja: return ["選択したテキストを読むにはVorssaintのアクセシビリティを許可してください。", "現在のアプリでテキストを選択してください。選択内容を提供しないアプリもあります。", "セキュア入力中はアクションを利用できません。"]
        case .ko: return ["선택한 텍스트를 읽도록 Vorssaint에 손쉬운 사용 권한을 허용하세요.", "현재 앱에서 텍스트를 선택하세요. 일부 앱은 선택 내용을 제공하지 않습니다.", "보안 입력 중에는 작업을 사용할 수 없습니다."]
        case .zhHans: return ["允许 Vorssaint 使用辅助功能以读取所选文本。", "请在当前应用中选择文本。某些应用不会提供所选内容。", "安全输入启用时无法使用操作。"]
        case .zhTW, .zhHK: return ["允許 Vorssaint 使用輔助使用以讀取所選文字。", "請在目前的 App 中選取文字。某些 App 不會提供所選內容。", "安全輸入啟用時無法使用操作。"]
        }
    }

    static func localized(_ language: AppLanguage) -> [String] {
        switch language {
        case .enUS: return ["Actions", "Filter actions", "Inspect JSON / XML", "Use as Left", "Use as Right", "Extract text", "Annotate", "Replace", "Cancel", "Replace %@?", "This replaces the current content in this destination. Your other content is kept.", "Replace inspector source?", "Before / After remain editable · ⌘Z Text undo", "This item is no longer available.", "Reading…"]
        case .de: return ["Aktionen", "Aktionen filtern", "JSON / XML untersuchen", "Links verwenden", "Rechts verwenden", "Text extrahieren", "Kommentieren", "Ersetzen", "Abbrechen", "%@ ersetzen?", "Der aktuelle Inhalt dieses Ziels wird ersetzt. Andere Inhalte bleiben erhalten.", "Quelle im Inspektor ersetzen?", "Vorher / Nachher bleiben bearbeitbar · ⌘Z Text rückgängig", "Dieses Objekt ist nicht mehr verfügbar.", "Lesen…"]
        case .fr: return ["Actions", "Filtrer les actions", "Inspecter JSON / XML", "Utiliser à gauche", "Utiliser à droite", "Extraire le texte", "Annoter", "Remplacer", "Annuler", "Remplacer %@ ?", "Le contenu actuel de cette destination sera remplacé. Les autres contenus sont conservés.", "Remplacer la source de l’inspecteur ?", "Avant / Après restent modifiables · ⌘Z Annuler le texte", "Cet élément n’est plus disponible.", "Lecture…"]
        case .ptBR: return ["Ações", "Filtrar ações", "Inspecionar JSON / XML", "Usar à esquerda", "Usar à direita", "Extrair texto", "Anotar", "Substituir", "Cancelar", "Substituir %@?", "Isso substitui o conteúdo atual deste destino. Os demais conteúdos são mantidos.", "Substituir a fonte do inspetor?", "Antes / Depois continuam editáveis · ⌘Z Desfazer texto", "Este item não está mais disponível.", "Lendo…"]
        case .es: return ["Acciones", "Filtrar acciones", "Inspeccionar JSON / XML", "Usar a la izquierda", "Usar a la derecha", "Extraer texto", "Anotar", "Reemplazar", "Cancelar", "¿Reemplazar %@?", "Se reemplaza el contenido actual de este destino. Se conserva el resto del contenido.", "¿Reemplazar la fuente del inspector?", "Antes / Después siguen editables · ⌘Z Deshacer texto", "Este elemento ya no está disponible.", "Leyendo…"]
        case .it: return ["Azioni", "Filtra azioni", "Ispeziona JSON / XML", "Usa a sinistra", "Usa a destra", "Estrai testo", "Annota", "Sostituisci", "Annulla", "Sostituire %@?", "Il contenuto attuale di questa destinazione verrà sostituito. Gli altri contenuti saranno mantenuti.", "Sostituire la sorgente dell’ispettore?", "Prima / Dopo restano modificabili · ⌘Z Annulla testo", "Questo elemento non è più disponibile.", "Lettura…"]
        case .tr: return ["Eylemler", "Eylemleri filtrele", "JSON / XML incele", "Sola gönder", "Sağa gönder", "Metni çıkar", "Açıklama ekle", "Değiştir", "İptal", "%@ değiştirilsin mi?", "Bu hedefin mevcut içeriği değiştirilir. Diğer içerikler korunur.", "İnceleyici kaynağı değiştirilsin mi?", "Önce / Sonra düzenlenebilir · ⌘Z Metni geri al", "Bu öğe artık kullanılamıyor.", "Okunuyor…"]
        case .sk: return ["Akcie", "Filtrovať akcie", "Preskúmať JSON / XML", "Použiť vľavo", "Použiť vpravo", "Získať text", "Anotovať", "Nahradiť", "Zrušiť", "Nahradiť %@?", "Nahradí sa aktuálny obsah tohto cieľa. Ostatný obsah sa zachová.", "Nahradiť zdroj prieskumníka?", "Pred / Po zostávajú upraviteľné · ⌘Z Vrátiť text", "Táto položka už nie je dostupná.", "Čítanie…"]
        case .ru: return ["Действия", "Фильтр действий", "Проверить JSON / XML", "Использовать слева", "Использовать справа", "Извлечь текст", "Добавить пометки", "Заменить", "Отмена", "Заменить %@?", "Текущее содержимое этого назначения будет заменено. Остальное содержимое сохранится.", "Заменить источник инспектора?", "До / После можно редактировать · ⌘Z Отмена текста", "Этот элемент больше недоступен.", "Чтение…"]
        case .uk: return ["Дії", "Фільтрувати дії", "Переглянути JSON / XML", "Використати зліва", "Використати справа", "Видобути текст", "Додати примітки", "Замінити", "Скасувати", "Замінити %@?", "Поточний вміст цього призначення буде замінено. Інший вміст збережеться.", "Замінити джерело інспектора?", "До / Після можна редагувати · ⌘Z Скасувати текст", "Цей елемент більше недоступний.", "Читання…"]
        case .ja: return ["アクション", "アクションを絞り込む", "JSON / XMLを調べる", "左側として使用", "右側として使用", "テキストを抽出", "注釈を付ける", "置き換える", "キャンセル", "%@を置き換えますか？", "この移動先の現在の内容を置き換えます。他の内容は保持されます。", "インスペクタのソースを置き換えますか？", "変更前 / 変更後は編集可能 · ⌘Z テキストを取り消す", "この項目は利用できなくなりました。", "読み取り中…"]
        case .ko: return ["작업", "작업 필터", "JSON / XML 검사", "왼쪽으로 사용", "오른쪽으로 사용", "텍스트 추출", "주석 추가", "바꾸기", "취소", "%@을(를) 바꿀까요?", "이 대상의 현재 내용을 바꿉니다. 다른 내용은 유지됩니다.", "검사기 소스를 바꿀까요?", "이전 / 이후 편집 가능 · ⌘Z 텍스트 실행 취소", "이 항목은 더 이상 사용할 수 없습니다.", "읽는 중…"]
        case .zhHans: return ["操作", "筛选操作", "检查 JSON / XML", "用作左侧", "用作右侧", "提取文本", "添加标注", "替换", "取消", "替换%@？", "这将替换此目标中的当前内容。其他内容将保留。", "替换检查器源文本？", "之前 / 之后仍可编辑 · ⌘Z 撤销文本", "此项目已不可用。", "正在读取…"]
        case .zhTW, .zhHK: return ["操作", "篩選操作", "檢查 JSON / XML", "用作左側", "用作右側", "擷取文字", "加入註解", "取代", "取消", "取代%@？", "這將取代此目標中的目前內容。其他內容將保留。", "取代檢查器原始文字？", "之前 / 之後仍可編輯 · ⌘Z 復原文字", "此項目已無法使用。", "正在讀取…"]
        }
    }
}
