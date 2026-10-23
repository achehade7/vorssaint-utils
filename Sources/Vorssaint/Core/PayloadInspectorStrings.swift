// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

struct PayloadInspectorStrings {
    let title, tree, source, search, copyValue, copyPath, openJSON, back: String
    let empty, loading, invalidJSON, invalidXML, tooLarge, tooComplex, unsupportedXML: String
    let selectField, noMatches, local, fields, copied: String

    private init(_ values: [String]) {
        precondition(values.count == 20)
        title = values[0]; tree = values[1]; source = values[2]; search = values[3]
        copyValue = values[4]; copyPath = values[5]; openJSON = values[6]; back = values[7]
        empty = values[8]; loading = values[9]; invalidJSON = values[10]; invalidXML = values[11]
        tooLarge = values[12]; tooComplex = values[13]; unsupportedXML = values[14]
        selectField = values[15]; noMatches = values[16]; local = values[17]; fields = values[18]; copied = values[19]
    }

    func message(_ error: Error) -> String {
        switch error {
        case PayloadInspector.Failure.empty: return empty
        case PayloadInspector.Failure.tooLarge: return tooLarge
        case PayloadInspector.Failure.tooComplex: return tooComplex
        case PayloadInspector.Failure.invalidJSON(let byte): return String(format: invalidJSON, byte)
        case PayloadInspector.Failure.invalidXML(let line): return String(format: invalidXML, line)
        case PayloadInspector.Failure.unsupportedXML: return unsupportedXML
        default: return invalidJSON.replacingOccurrences(of: "%d", with: "?")
        }
    }

    static func localized(_ language: AppLanguage) -> Self {
        switch language {
        case .enUS: return .init(["Payload inspector", "Tree", "Source", "Find a field or value", "Copy value", "Copy path", "Open JSON", "Back", "Paste JSON or XML into Source to explore its fields.", "Reading payload…", "Invalid JSON near byte %d. Edit Source to correct it.", "Invalid XML near line %d. Edit Source to correct it.", "Input exceeds 1 MB. Nothing was truncated.", "Payload exceeds 10,000 fields, 64 levels or the path limit. Source is unchanged.", "XML with DTDs or entity declarations is not supported.", "Select a field to inspect its value and path.", "No matching fields", "Processed locally", "Fields: %d", "Copied"])
        case .ptBR: return .init(["Inspetor de dados", "Árvore", "Fonte", "Buscar campo ou valor", "Copiar valor", "Copiar caminho", "Abrir JSON", "Voltar", "Cole JSON ou XML na Fonte para explorar os campos.", "Lendo dados…", "JSON inválido perto do byte %d. Corrija na Fonte.", "XML inválido perto da linha %d. Corrija na Fonte.", "A entrada excede 1 MB. Nada foi truncado.", "Os dados excedem 10.000 campos, 64 níveis ou o limite de caminho. A fonte não mudou.", "XML com DTDs ou declarações de entidades não é compatível.", "Selecione um campo para ver seu valor e caminho.", "Nenhum campo encontrado", "Processamento local", "Campos: %d", "Copiado"])
        case .tr: return .init(["Veri inceleyici", "Ağaç", "Kaynak", "Alan veya değer ara", "Değeri kopyala", "Yolu kopyala", "JSON aç", "Geri", "Alanları incelemek için Kaynak’a JSON veya XML yapıştırın.", "Veri okunuyor…", "%d. bayt yakınında geçersiz JSON. Kaynak’ta düzeltin.", "%d. satır yakınında geçersiz XML. Kaynak’ta düzeltin.", "Girdi 1 MB sınırını aşıyor. Hiçbir şey kesilmedi.", "Veri 10.000 alan, 64 düzey veya yol sınırını aşıyor. Kaynak değişmedi.", "DTD veya varlık bildirimleri içeren XML desteklenmez.", "Değerini ve yolunu görmek için bir alan seçin.", "Eşleşen alan yok", "Yerel işleme", "Alan: %d", "Kopyalandı"])
        case .ru: return .init(["Инспектор данных", "Дерево", "Исходник", "Найти поле или значение", "Копировать значение", "Копировать путь", "Открыть JSON", "Назад", "Вставьте JSON или XML в исходник для просмотра полей.", "Чтение данных…", "Ошибка JSON около байта %d. Исправьте исходник.", "Ошибка XML около строки %d. Исправьте исходник.", "Объём превышает 1 МБ. Данные не обрезаны.", "Превышен предел в 10 000 полей, 64 уровня или длина пути. Исходник не изменён.", "XML с DTD или объявлениями сущностей не поддерживается.", "Выберите поле для просмотра значения и пути.", "Совпадений нет", "Локальная обработка", "Полей: %d", "Скопировано"])
        case .es: return .init(["Inspector de datos", "Árbol", "Fuente", "Buscar un campo o valor", "Copiar valor", "Copiar ruta", "Abrir JSON", "Atrás", "Pega JSON o XML en Fuente para explorar sus campos.", "Leyendo datos…", "JSON inválido cerca del byte %d. Corrígelo en Fuente.", "XML inválido cerca de la línea %d. Corrígelo en Fuente.", "La entrada supera 1 MB. No se ha truncado nada.", "Se superan 10.000 campos, 64 niveles o el límite de ruta. La fuente no ha cambiado.", "No se admite XML con DTD o declaraciones de entidades.", "Selecciona un campo para ver su valor y ruta.", "No hay campos coincidentes", "Procesamiento local", "Campos: %d", "Copiado"])
        case .sk: return .init(["Prieskumník údajov", "Strom", "Zdroj", "Nájsť pole alebo hodnotu", "Kopírovať hodnotu", "Kopírovať cestu", "Otvoriť JSON", "Späť", "Vložte JSON alebo XML do Zdroja a preskúmajte polia.", "Načítavanie údajov…", "Neplatný JSON pri bajte %d. Opravte Zdroj.", "Neplatné XML pri riadku %d. Opravte Zdroj.", "Vstup presahuje 1 MB. Nič nebolo skrátené.", "Údaje presahujú 10 000 polí, 64 úrovní alebo limit cesty. Zdroj je nezmenený.", "XML s DTD alebo deklaráciami entít nie je podporované.", "Vyberte pole a zobrazte jeho hodnotu a cestu.", "Žiadne zodpovedajúce polia", "Lokálne spracovanie", "Polia: %d", "Skopírované"])
        case .de: return .init(["Dateninspektor", "Baum", "Quelle", "Feld oder Wert suchen", "Wert kopieren", "Pfad kopieren", "JSON öffnen", "Zurück", "JSON oder XML in Quelle einfügen, um die Felder zu erkunden.", "Daten werden gelesen…", "Ungültiges JSON bei Byte %d. In Quelle korrigieren.", "Ungültiges XML bei Zeile %d. In Quelle korrigieren.", "Die Eingabe überschreitet 1 MB. Nichts wurde gekürzt.", "Mehr als 10.000 Felder, 64 Ebenen oder zu langer Pfad. Quelle unverändert.", "XML mit DTDs oder Entitätsdeklarationen wird nicht unterstützt.", "Ein Feld auswählen, um Wert und Pfad anzuzeigen.", "Keine passenden Felder", "Lokal verarbeitet", "Felder: %d", "Kopiert"])
        case .fr: return .init(["Inspecteur de données", "Arbre", "Source", "Rechercher un champ ou une valeur", "Copier la valeur", "Copier le chemin", "Ouvrir JSON", "Retour", "Collez du JSON ou du XML dans Source pour explorer ses champs.", "Lecture des données…", "JSON invalide près de l’octet %d. Corrigez la Source.", "XML invalide près de la ligne %d. Corrigez la Source.", "L’entrée dépasse 1 Mo. Rien n’a été tronqué.", "Les données dépassent 10 000 champs, 64 niveaux ou la limite de chemin. Source inchangée.", "Le XML avec DTD ou déclarations d’entités n’est pas pris en charge.", "Sélectionnez un champ pour voir sa valeur et son chemin.", "Aucun champ correspondant", "Traitement local", "Champs : %d", "Copié"])
        case .it: return .init(["Ispettore dati", "Albero", "Sorgente", "Cerca un campo o valore", "Copia valore", "Copia percorso", "Apri JSON", "Indietro", "Incolla JSON o XML in Sorgente per esplorare i campi.", "Lettura dati…", "JSON non valido vicino al byte %d. Correggi in Sorgente.", "XML non valido vicino alla riga %d. Correggi in Sorgente.", "L’input supera 1 MB. Nulla è stato troncato.", "I dati superano 10.000 campi, 64 livelli o il limite del percorso. Sorgente invariata.", "XML con DTD o dichiarazioni di entità non è supportato.", "Seleziona un campo per vedere valore e percorso.", "Nessun campo corrispondente", "Elaborazione locale", "Campi: %d", "Copiato"])
        case .ja: return .init(["データインスペクタ", "ツリー", "ソース", "フィールドや値を検索", "値をコピー", "パスをコピー", "JSONを開く", "戻る", "ソースにJSONまたはXMLを貼り付けてフィールドを確認できます。", "データを読み取り中…", "%dバイト付近のJSONが無効です。ソースで修正してください。", "%d行付近のXMLが無効です。ソースで修正してください。", "入力が1 MBを超えています。省略していません。", "10,000フィールド、64階層、またはパスの上限を超えています。ソースは変更されていません。", "DTDや実体宣言を含むXMLには対応していません。", "フィールドを選択すると値とパスを確認できます。", "一致するフィールドなし", "ローカル処理", "%dフィールド", "コピーしました"])
        case .ko: return .init(["데이터 검사기", "트리", "소스", "필드 또는 값 찾기", "값 복사", "경로 복사", "JSON 열기", "뒤로", "소스에 JSON 또는 XML을 붙여 넣어 필드를 살펴보세요.", "데이터 읽는 중…", "%d바이트 근처의 JSON이 잘못되었습니다. 소스에서 수정하세요.", "%d행 근처의 XML이 잘못되었습니다. 소스에서 수정하세요.", "입력이 1 MB를 초과합니다. 내용은 생략되지 않았습니다.", "10,000개 필드, 64단계 또는 경로 한도를 초과했습니다. 소스는 변경되지 않았습니다.", "DTD 또는 엔터티 선언이 있는 XML은 지원하지 않습니다.", "필드를 선택하여 값과 경로를 확인하세요.", "일치하는 필드 없음", "로컬 처리", "%d개 필드", "복사됨"])
        case .uk: return .init(["Інспектор даних", "Дерево", "Джерело", "Знайти поле або значення", "Копіювати значення", "Копіювати шлях", "Відкрити JSON", "Назад", "Вставте JSON або XML у Джерело для перегляду полів.", "Читання даних…", "Некоректний JSON біля байта %d. Виправте Джерело.", "Некоректний XML біля рядка %d. Виправте Джерело.", "Обсяг перевищує 1 МБ. Нічого не обрізано.", "Перевищено 10 000 полів, 64 рівні або довжину шляху. Джерело не змінено.", "XML із DTD або оголошеннями сутностей не підтримується.", "Виберіть поле для перегляду значення та шляху.", "Відповідних полів немає", "Локальна обробка", "Полів: %d", "Скопійовано"])
        case .zhHans: return .init(["数据检查器", "树状", "源文本", "查找字段或值", "复制值", "复制路径", "打开 JSON", "返回", "将 JSON 或 XML 粘贴到源文本以浏览字段。", "正在读取数据…", "第 %d 字节附近的 JSON 无效。请编辑源文本。", "第 %d 行附近的 XML 无效。请编辑源文本。", "输入超过 1 MB。内容未被截断。", "数据超过 10,000 个字段、64 层或路径限制。源文本未更改。", "不支持包含 DTD 或实体声明的 XML。", "选择字段以查看值和路径。", "没有匹配的字段", "本地处理", "%d 个字段", "已复制"])
        case .zhTW, .zhHK: return .init(["資料檢查器", "樹狀", "原始文字", "尋找欄位或值", "複製值", "複製路徑", "開啟 JSON", "返回", "將 JSON 或 XML 貼到原始文字以瀏覽欄位。", "正在讀取資料…", "第 %d 位元組附近的 JSON 無效。請編輯原始文字。", "第 %d 行附近的 XML 無效。請編輯原始文字。", "輸入超過 1 MB。內容未被截斷。", "資料超過 10,000 個欄位、64 層或路徑限制。原始文字未變更。", "不支援包含 DTD 或實體宣告的 XML。", "選取欄位以檢視值與路徑。", "沒有相符的欄位", "本機處理", "%d 個欄位", "已複製"])
        }
    }
}
