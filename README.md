<!-- markdownlint-configure-file
{
  "MD033": {
    "allowed_elements": ["a", "b", "br", "code", "details", "div", "h3", "i", "img", "p", "sub", "summary", "table", "td", "tr"]
  }
}
-->
<!-- =============================================================== -->
<!--  ALLAGAN  EYE   ·   観測器                                       -->
<!--  README rendered in the Allagan-style of the GUI.                -->
<!--  Visual assets live in  image/ at the repo root.                  -->
<!--                                                                  -->
<!--  Lint policy: this README is an intentional design document      -->
<!--  using HTML for layout (table / div / details / img-with-attr).  -->
<!--  MD033 allowed_elements above whitelists exactly the elements    -->
<!--  used by the Allagan-style design. Any other inline HTML still   -->
<!--  fails the lint. Per docs/markdownlint-guide.md §"意図的な書き方".-->
<!-- =============================================================== -->

<div align="center">
  <a href="https://github.com/Idios/kobutachan-allaganeye">
    <img src="image/hero.svg" alt="ALLAGAN EYE — FF14 フロントライン録画を、試合ごとの戦果へ" width="100%"/>
  </a>
</div>

<p align="center">
  <a href="https://github.com/Idios/kobutachan-allaganeye/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Idios/kobutachan-allaganeye?style=for-the-badge&label=%E2%97%87%20RELEASE&labelColor=0a0e14&color=c8a35c"/></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/%E2%97%87%20LICENSE-MIT-c8a35c?style=for-the-badge&labelColor=0a0e14"/></a>
  <img alt="Platform Windows" src="https://img.shields.io/badge/%E2%97%87%20PLATFORM-WINDOWS-4ac3d9?style=for-the-badge&labelColor=0a0e14"/>
  <img alt="For FFXIV / Frontline" src="https://img.shields.io/badge/%E2%97%87%20FFXIV-%E3%83%95%E3%83%AD%E3%83%B3%E3%83%88%E3%83%A9%E3%82%A4%E3%83%B3-c8a35c?style=for-the-badge&labelColor=0a0e14"/>
</p>

<p align="center">
  <sub><i>古代アラガン文明の観測眼が、汝の長時間録画を読み解く。</i></sub><br/>
  <sub><b>OBSなどで録画した数時間の動画を、試合の切れ目を自動検知し、無劣化MP4へ分割します。</b></sub>
</p>

<br/>

<div align="center">

<sub><b>◇&nbsp;&nbsp;観 測 対 象&nbsp;&nbsp;·&nbsp;&nbsp;O B S E R V A T I O N&nbsp;&nbsp;T A R G E T&nbsp;&nbsp;◇</b></sub>

<a href="image/observation-target.gif">
  <img src="image/observation-target.gif" alt="FF14 フロントライン戦闘シーン" width="640"/>
</a>

<sub><i>──&nbsp;&nbsp;幾時間にも及ぶフロントラインの戦果を、観測眼は逃さず読み取る&nbsp;&nbsp;──</i></sub>

</div>

<br/>

<div align="center">
  <img src="image/divider.svg" width="90%" alt=""/>
</div>

<br/>

## ◆&nbsp;&nbsp;クイックスタート&nbsp;&nbsp;·&nbsp;&nbsp;Q U I C K&nbsp;&nbsp;S T A R T

<table align="center" width="100%">
<tr>
<td width="33%" valign="top" align="center">
<h3>❶</h3>
<b>取得</b><br/>
<sub>D O W N L O A D</sub>
<br/><br/>
<a href="https://github.com/Idios/kobutachan-allaganeye/releases/latest"><b><code>allaganeye-*-windows.zip</code></b></a><br/>
を <a href="https://github.com/Idios/kobutachan-allaganeye/releases/latest">Releases</a> から取得
</td>
<td width="33%" valign="top" align="center">
<h3>❷</h3>
<b>展開</b><br/>
<sub>U N P A C K</sub>
<br/><br/>
ZIP をデスクトップなどに展開<br/>
<sub>Python/FFmpeg は不要 — ZIP に同梱済</sub>
</td>
<td width="33%" valign="top" align="center">
<h3>❸</h3>
<b>観測</b><br/>
<sub>O B S E R V E</sub>
<br/><br/>
動画を <code>allaganeye.bat</code> へ<br/>
<b>ドラッグ&amp;ドロップ</b><br/>
<sub>または <code>.bat</code> をダブルクリックで GUI 起動</sub>
</td>
</tr>
</table>

<p align="center">
<sub>出力先: D&amp;D 時は <code>allaganeye-*\output\</code>、GUI 時は画面上で指定（既定は動画と同じフォルダ）。&nbsp;&nbsp;◆&nbsp;&nbsp;詳細手順は <a href="docs/quickstart.md">Quick Start Guide</a> へ。</sub>
</p>

> [!WARNING]
> **SmartScreen / `.bat` 警告が出る場合**<br/>
> 署名なし配布のため、初回起動時に Windows のセキュリティ警告が表示されることがあります。対処は [Quick Start Guide §3 — セキュリティ警告が出た場合](docs/quickstart.md#3-セキュリティ警告が出た場合) を参照。

<br/>

<div align="center">
  <img src="image/divider.svg" width="90%" alt=""/>
</div>

<br/>

## ◆&nbsp;&nbsp;観測の流れ&nbsp;&nbsp;·&nbsp;&nbsp;W O R K F L O W

数時間の録画は、4 つの観測フェーズを経て、試合ごとの戦果へと変換されます。

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'background':'#0a0e14',
  'primaryColor':'#0f1420',
  'primaryTextColor':'#e8c47a',
  'primaryBorderColor':'#c8a35c',
  'lineColor':'#c8a35c',
  'secondaryColor':'#0f1420',
  'tertiaryColor':'#0a0e14',
  'fontFamily':'Cinzel, Trajan Pro, serif'
}}}%%
flowchart LR
    A([◆ 録画<br/><b>RECORDING</b><br/><sub>2〜4h MP4/MKV</sub>]) --> B[◇ 粗スキャン<br/><b>DETECTING</b><br/><sub>輝度サンプリング</sub>]
    B --> C[◇ 精密計測<br/><b>REFINING</b><br/><sub>境界候補の解析</sub>]
    C --> D[◇ スコアバー<br/><b>SCOREBAR</b><br/><sub>FL試合の判別</sub>]
    D --> E[◇ 分割<br/><b>SPLITTING</b><br/><sub>無劣化COPY</sub>]
    E --> F([◆ 試合動画群<br/><b>MATCHES</b><br/><sub>match_001.mp4 …</sub>])

    classDef phase fill:#0f1420,stroke:#c8a35c,stroke-width:1.5px,color:#e8c47a;
    classDef io fill:#1a1408,stroke:#c8a35c,stroke-width:2px,color:#e8c47a;
    class B,C,D,E phase
    class A,F io
```

<br/>

### 5 つの観測フェーズ

<table align="center">
<tr>
<td width="50%" valign="top" align="center">
  <a href="image/01-drop.png">
    <img src="image/01-drop.png" alt="① Drop — 録画を捧げよ" width="100%"/>
  </a>
  <br/>
  <b>① インポート&nbsp;&nbsp;·&nbsp;&nbsp;D R O P</b><br/>
  <sub>録画ファイルを観測眼に捧げる。直近の録画一覧から再検知も可能。</sub>
</td>
<td width="50%" valign="top" align="center">
  <a href="image/02-detecting.png">
    <img src="image/02-detecting.png" alt="② Detecting — 観測中" width="100%"/>
  </a>
  <br/>
  <b>② 検知中&nbsp;&nbsp;·&nbsp;&nbsp;D E T E C T I N G</b><br/>
  <sub>粗スキャン (Detecting) → 精密計測 (Refining、scorebar 分類含む) の 2 フェーズをバーとライブログでリアルタイム表示。</sub>
</td>
</tr>
<tr>
<td width="50%" valign="top" align="center">
  <a href="image/03-complete.png">
    <img src="image/03-complete.png" alt="③ Matches — 一覧" width="100%"/>
  </a>
  <br/>
  <b>③ 一覧&nbsp;&nbsp;·&nbsp;&nbsp;M A T C H E S</b><br/>
  <sub>輝度タイムライン上に検知結果。試合ごとのサムネとプレビューを並べてレビュー。</sub>
</td>
<td width="50%" valign="top" align="center">
  <a href="image/04-preview.png">
    <img src="image/04-preview.png" alt="④ Preview — 境界調整" width="100%"/>
  </a>
  <br/>
  <b>④ 境界調整&nbsp;&nbsp;·&nbsp;&nbsp;P R E V I E W</b><br/>
  <sub>IN/OUT 2画面 + 候補フレームストリップ + 微細タイムライン。秒・フレーム単位で微調整。</sub>
</td>
</tr>
<tr>
<td colspan="2" valign="top" align="center">
  <a href="image/05-export.png">
    <img src="image/05-export.png" alt="⑤ Export — 書き出し" width="70%"/>
  </a>
  <br/>
  <b>⑤ 書き出し&nbsp;&nbsp;·&nbsp;&nbsp;E X P O R T</b><br/>
  <sub>ffmpeg で試合動画を生成。無劣化 COPY / H.264 再エンコード・命名規則・出力先を選択可能。</sub>
</td>
</tr>
</table>

<br/>

<div align="center">
  <img src="image/divider.svg" width="90%" alt=""/>
</div>

<br/>

## ◆&nbsp;&nbsp;特徴&nbsp;&nbsp;·&nbsp;&nbsp;F E A T U R E S

<table align="center">
<tr>
<td width="25%" valign="top" align="center">
<h3>◇</h3>
<b>無劣化分割</b><br/>
<sub>L O S S L E S S&nbsp;&nbsp;C O P Y</sub>
<br/><br/>
<sub>ffmpeg の stream copy で<br/>再エンコードなし・高速</sub>
</td>
<td width="25%" valign="top" align="center">
<h3>◇</h3>
<b>自動境界検知</b><br/>
<sub>A U T O&nbsp;&nbsp;B O U N D A R Y</sub>
<br/><br/>
<sub>輝度 + スコアバーの<br/>二段判定で誤検知を低減</sub>
</td>
<td width="25%" valign="top" align="center">
<h3>◇</h3>
<b>GUI &amp; CLI</b><br/>
<sub>D U A L&nbsp;&nbsp;I N T E R F A C E</sub>
<br/><br/>
<sub>D&amp;D で気軽に、<br/>CLI で大量バッチも</sub>
</td>
<td width="25%" valign="top" align="center">
<h3>◇</h3>
<b>同梱配布</b><br/>
<sub>P O R T A B L E&nbsp;&nbsp;Z I P</sub>
<br/><br/>
<sub>Python / FFmpeg は<br/>ZIP に同梱・インストール不要</sub>
</td>
</tr>
</table>

<br/>

<div align="center">
  <img src="image/divider.svg" width="90%" alt=""/>
</div>

<br/>

## ◆&nbsp;&nbsp;対応プラットフォーム&nbsp;&nbsp;·&nbsp;&nbsp;P L A T F O R M

> [!IMPORTANT]
> **Windows 専用**です。Python や FFmpeg の事前インストールは必要ありません — Portable ZIP に同梱されています。

<br/>

<div align="center">
  <img src="image/divider.svg" width="90%" alt=""/>
</div>

<br/>

## ◆&nbsp;&nbsp;ドキュメント&nbsp;&nbsp;·&nbsp;&nbsp;C O D E X

<table align="center" width="100%">
<tr>
<td width="50%" valign="top">

### ◇&nbsp;&nbsp;一般ユーザー向け

<sub>F O R &nbsp; U S E R S</sub>

| | |
| --- | --- |
| 📖 | [**Quick Start Guide**](docs/quickstart.md)<br/><sub>Portable ZIP の使い方・SmartScreen 警告・トラブルシュート</sub> |
| 🎚️ | [**パラメータ調整ガイド**](docs/tuning-guide.md)<br/><sub>分割結果が期待と異なるときのチューニング</sub> |
| 🐛 | [**バグ報告ガイド**](docs/bug-report-guide.md)<br/><sub>Issue の書き方とログ添付</sub> |

</td>
<td width="50%" valign="top">

### ◇&nbsp;&nbsp;開発者向け

<sub>F O R &nbsp; D E V E L O P E R S</sub>

| | |
| --- | --- |
| ⚙️ | [**Developer Setup**](docs/developer-setup.md)<br/><sub>Git / Python / venv でソースから起動</sub> |
| 🏛️ | [**System Architecture**](docs/system-architecture.md)<br/><sub>CLI + GUI + installer の全体構成 (#527)</sub> |
| 🖥️ | [**GUI UI Architecture**](docs/ui-architecture.md)<br/><sub>L2a Tauri GUI の screen / phase state machine</sub> |

</td>
</tr>
</table>

<details>
<summary><b>◇&nbsp;&nbsp;すべての設計ドキュメントを表示</b>&nbsp;&nbsp;<sub>(specs · design · release)</sub></summary>

<br/>

| カテゴリ | ドキュメント |
| --- | --- |
| **CLI / API** | [CLI コマンド仕様](docs/cli-spec.md) · [metadata.json 仕様](docs/metadata-spec.md) · [出力仕様マトリクス](docs/output-spec.md) |
| **設計** | [システム設計概要](docs/design-overview.md) · [動画処理設計](docs/video-processing.md) · [スコアバー検出設計](docs/scorebar-detection-design.md) |
| **リリース** | [リリース戦略・手順](docs/release-process.md) · [バージョニング](docs/versioning.md) |
| **品質** | [テストガイド](docs/testing-guide.md) · [L1 品質基準](docs/l1-quality-criteria.md) · [L2 E2E チェックリスト](docs/l2-e2e-checklist.md) |
| **その他** | [コーディング規約](docs/coding-conventions.md) · [a11y ポリシー](docs/a11y-policy.md) · [ベンチマーク](docs/benchmarks.md) |

</details>

<br/>

<div align="center">
  <img src="image/divider.svg" width="90%" alt=""/>
</div>

<br/>

## ◆&nbsp;&nbsp;ライセンス&nbsp;&nbsp;·&nbsp;&nbsp;L I C E N S E

[**MIT License**](LICENSE) — 自由に使用・改変・再配布できます。

<br/>

---

<p align="center">
  <sub>
    <img src="docs/design/icon/icon-128.png" width="48" alt="Allagan Eye"/><br/>
    <br/>
    <b>ALLAGAN&nbsp;EYE&nbsp;·&nbsp;観測器</b><br/>
    <sub>An observation system from the lost Allagan civilization.</sub><br/>
    <sub>FINAL&nbsp;FANTASY&nbsp;XIV は株式会社スクウェア・エニックスの登録商標です。本ツールは非公式の有志ツールです。</sub>
  </sub>
</p>
