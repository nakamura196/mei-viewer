# mei-viewer ― 楽譜の構造化データ（MEI）× IIIF カタログ

楽譜を画像のままではなく **構造化データ（MEI: Music Encoding Initiative）** として符号化し、
**IIIF** の原資料画像・歌詞と相互にリンクして見せる、実験的なビューア兼カタログです。
最初の題材は明治期『小学唱歌集 初編』第十七「蝶々」（国立国会図書館蔵, PDM）。

🔗 **公開サイト**: https://nakamura196.github.io/mei-viewer/
🎼 **ビューア**: https://nakamura196.github.io/mei-viewer/viewer.html?id=choucho

## できること

- **音符⇄原資料**: 楽譜（Verovio が MEI から描画）の音符をクリックすると、IIIF 原資料画像の該当段がハイライト。
- **縦書き歌詞リンク**: 左丁の縦書き本文を **NDL古典籍OCR-Lite** で翻刻し、行の座標で楽譜・画像と結ぶ。
- **再生**: MEI → MIDI を生成し、ブラウザで旋律を再生（鳴っている音符を同期ハイライト）。

## 構成（データ駆動）

曲を追加する＝`data/<id>/` を置いて `catalog.json` に1行足すだけ。HTML/コードの編集は不要です。

```
index.html              カタログ（catalog.json を読んでカード生成）
viewer.html             ビューア（?id=<slug> でデータ切替）
catalog.json            目録（曲一覧）
assets/react-ui.css     デザインシステム（@nakamura196/react-ui, UTokyo VI, MIT）をベンダリング
data/<id>/
  ├── meta.json         曲メタ（NDL pid, IIIF, タイトル…）
  ├── <id>.mei          MEI 5.1（jing で検証済み）
  └── lyrics.json       縦書き歌詞のOCR結果（本文＋座標）
scripts/build_dts.py    catalog から静的 DTS API を生成
dts/                    生成物（DTS 1-alpha 静的 API, 下記）
```

## DTS API（静的）

`catalog.json` + `data/` から **DTS（Distributed Text Services）1-alpha** の静的エンドポイントを生成します。
歌詞を TEI（必須既定フォーマット）で、楽譜 MEI を代替フォーマット `application/mei+xml` で配信します。

```bash
python3 scripts/build_dts.py --base https://nakamura196.github.io/mei-viewer
```

- EntryPoint: `https://nakamura196.github.io/mei-viewer/dts/index.json`
- 既存の [dts-viewer](https://github.com/nakamura196/dts-viewer) にこの EntryPoint URL を貼ると、コード変更なしで目録閲覧・引用ナビ・TEI/MEI ダウンロードができます。

## ローカルで動かす

```bash
python3 -m http.server 8000     # もしくは npx live-server
```

`file://` 直開きは fetch がブロックされるため不可。ネットワーク（CDN・NDL IIIF）が必要です。

## 符号化の範囲と典拠

- 音高を検証済みなのは第1フレーズ（4小節, ソミミ ファレレ ドレミファ ソソソ）。第2〜4段は原資料リンクと歌詞のみ。
- 第1節「蝶々蝶々…」は野村秋足（伝）/実質は作者不詳のわらべうた、第2節は稲垣千頴の作詞。
- 旋律はドイツ由来の曲が米国唱歌 "Lightly Row" を介して伝来（「スペイン民謡」説は俗説）。
- 第2段の歌詞は底本では「桜にとまれ」。異本「桜に遊べ」は MEI/TEI の `<app>/<rdg>` で併記しうる。

## 出典・ライセンス

- 原資料: 文部省音楽取調掛 編『小学唱歌集 初編』文部省, 1881-1884.
  [国立国会図書館デジタルコレクション pid 992051](https://dl.ndl.go.jp/info:ndljp/pid/992051)（PDM / DOI: 10.11501/992051）
- 翻刻: [NDL古典籍OCR-Lite](https://github.com/ndl-lab/ndlkotenocr-lite)（CC BY 4.0）
- デザイン: [@nakamura196/react-ui](https://github.com/nakamura196/react-ui)（MIT, UTokyo VI）
- このエンコード・コード: CC0
