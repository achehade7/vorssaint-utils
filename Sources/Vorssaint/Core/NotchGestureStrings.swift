// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

struct NotchGestureStrings {
    let title: String
    let description: String
    let hint: String
}

extension FeatureStrings {
    static func notchGestures(_ language: AppLanguage) -> NotchGestureStrings {
        switch language {
        case .enUS: return NotchGestureStrings(
            title: "Dynamic Island Gestures",
            description: "Open and close the Dynamic Island with scrolling, and swipe back through its pages.",
            hint: "Scroll down to open. Scroll up over the top row to close. Swipe right with two fingers to go back one level. From a main page, go back to Home. Lists keep vertical scrolling.")
        case .ptBR: return NotchGestureStrings(
            title: "Gestos do Dynamic Island",
            description: "Abra e feche o Dynamic Island com a rolagem e deslize para voltar pelas páginas.",
            hint: "Role para baixo para abrir e para cima sobre a faixa superior para fechar. Deslize dois dedos para a direita para voltar um nível. De uma página principal, volte ao início. As listas mantêm a rolagem vertical.")
        case .es: return NotchGestureStrings(
            title: "Gestos del Dynamic Island",
            description: "Abre y cierra el Dynamic Island al desplazarte y desliza para volver por sus páginas.",
            hint: "Desplázate hacia abajo para abrir y hacia arriba sobre la fila superior para cerrar. Desliza dos dedos a la derecha para retroceder un nivel. Desde una página principal, vuelve al inicio. Las listas conservan el desplazamiento vertical.")
        case .sk: return NotchGestureStrings(
            title: "Gestá Dynamic Island",
            description: "Otvorte a zatvorte Dynamic Island posúvaním a potiahnutím sa vráťte na predchádzajúcu stránku.",
            hint: "Posunutím nadol otvoríte a nahor nad horným riadkom zatvoríte. Potiahnutím dvoma prstami doprava sa vrátite o úroveň späť. Z hlavnej stránky sa vrátite domov. Zoznamy zachovávajú zvislé posúvanie.")
        case .de: return NotchGestureStrings(
            title: "Dynamic Island-Gesten",
            description: "Öffne und schließe den Dynamic Island durch Scrollen und gehe durch Wischen eine Seite zurück.",
            hint: "Scrolle zum Öffnen nach unten und über der oberen Zeile zum Schließen nach oben. Wische mit zwei Fingern nach rechts, um eine Ebene zurückzugehen. Von einer Hauptseite geht es zur Startseite. Listen bleiben vertikal scrollbar.")
        case .fr: return NotchGestureStrings(
            title: "Gestes du Dynamic Island",
            description: "Ouvrez et fermez le Dynamic Island par défilement et balayez pour revenir à la page précédente.",
            hint: "Faites défiler vers le bas pour ouvrir, vers le haut sur la rangée supérieure pour fermer. Balayez à droite avec deux doigts pour revenir d’un niveau. Depuis une page principale, revenez à l’accueil. Les listes gardent le défilement vertical.")
        case .it: return NotchGestureStrings(
            title: "Gesti del Dynamic Island",
            description: "Apri e chiudi il Dynamic Island scorrendo e torna alla pagina precedente con un gesto laterale.",
            hint: "Scorri verso il basso per aprire e verso l’alto sulla riga superiore per chiudere. Scorri a destra con due dita per tornare indietro di un livello. Da una pagina principale, torna alla Home. Le liste mantengono lo scorrimento verticale.")
        case .ru: return NotchGestureStrings(
            title: "Жесты для выреза",
            description: "Открывайте и закрывайте панель прокруткой и возвращайтесь на предыдущую страницу смахиванием.",
            hint: "Прокрутите вниз для открытия и вверх над верхней строкой для закрытия. Смахните двумя пальцами вправо, чтобы вернуться на один уровень. С основной страницы вы вернётесь на главную. Списки сохраняют вертикальную прокрутку.")
        case .tr: return NotchGestureStrings(
            title: "Çentik Hareketleri",
            description: "Kaydırarak çentiği açıp kapatın ve önceki sayfaya dönün.",
            hint: "Açmak için aşağı, kapatmak için üst satırda yukarı kaydırın. Bir seviye geri gitmek için iki parmakla sağa kaydırın. Ana bölüm sayfasından ana ekrana dönersiniz. Listeler dikey kaydırmayı korur.")
        case .ja: return NotchGestureStrings(
            title: "Dynamic Islandのジェスチャ",
            description: "スクロールでDynamic Islandを開閉し、スワイプで前のページに戻ります。",
            hint: "下にスクロールすると開き、上部の行で上にスクロールすると閉じます。2本指で右にスワイプすると1つ前の階層に戻ります。メインページからはホームに戻ります。リストは縦にスクロールできます。")
        case .ko: return NotchGestureStrings(
            title: "Dynamic Island 제스처",
            description: "스크롤로 Dynamic Island를 열고 닫고, 옆으로 쓸어 이전 페이지로 돌아가세요.",
            hint: "아래로 스크롤하면 열리고 상단 줄에서 위로 스크롤하면 닫힙니다. 두 손가락으로 오른쪽으로 쓸면 한 단계 뒤로 돌아갑니다. 기본 페이지에서는 홈으로 돌아갑니다. 목록은 세로로 스크롤됩니다.")
        case .zhHans: return NotchGestureStrings(
            title: "Dynamic Island手势",
            description: "滚动以打开或关闭Dynamic Island，轻扫以返回上一页。",
            hint: "向下滚动以打开，在顶部栏向上滚动以关闭。用双指向右轻扫以返回上一级。从主页面返回主页。列表保留垂直滚动。")
        case .zhTW: return NotchGestureStrings(
            title: "Dynamic Island手勢",
            description: "捲動以打開或關閉Dynamic Island，滑動以返回上一頁。",
            hint: "向下捲動以打開，在頂部列向上捲動以關閉。用雙指向右滑動以返回上一層。從主要頁面返回首頁。列表保留垂直捲動。")
        case .zhHK: return NotchGestureStrings(
            title: "Dynamic Island手勢",
            description: "捲動以開啟或關閉Dynamic Island，滑動以返回上一頁。",
            hint: "向下捲動以開啟，在頂部列向上捲動以關閉。用雙指向右滑動以返回上一層。從主要頁面返回首頁。列表保留垂直捲動。")
        case .uk: return NotchGestureStrings(
            title: "Жести Dynamic Island",
            description: "Відкривайте та закривайте Dynamic Island прокручуванням і повертайтеся на попередню сторінку змахуванням.",
            hint: "Прокрутіть униз, щоб відкрити, і вгору над верхнім рядком, щоб закрити. Змахніть двома пальцями праворуч, щоб повернутися на один рівень. З основної сторінки ви повернетеся на головну. Списки зберігають вертикальне прокручування.")
        }
    }
}
