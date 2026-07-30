# W6: doc 一括再同期 (SSoT 適用) 設計

- issue: [#862](https://github.com/Idios/kobutachan-allaganeye/issues/862)
- 上位 spec: [audit-remediation design §W6](2026-06-10-audit-remediation-design.md)
- 前提: [#818](https://github.com/Idios/kobutachan-allaganeye/issues/818) (doc SSoT 規約) merge 済み
- 作成: 2026-07-30

## 背景

2026-06-10 full audit が検出した doc drift のうち、Wave 2 テーマ W6 に残された
P2-25〜P2-35 + doc 系 P3 を消化する。W1〜W5 は消化済みで、W6 のみ issue が
起票されないまま欠番だった。

監査の構造所見 3 が指摘するとおり、doc drift は「複数 doc への値の複製」と
「実装後の『予定』文言残存」の 2 パターンに収斂している。本作業は個別の誤記を
潰すだけでなく、[`docs/coding-conventions.md` §ドキュメント SSoT 規約](../../coding-conventions.md)
を適用して複製値をリンク化し、再発要因そのものを減らす。

## 事前検証の結果

着手前に監査項目を実装と突合し直した (監査から 7 週間経過しており、既に修正済みの
項目が混在するため)。

### STILL DRIFTED (本 issue で対応)

| 項目 | doc 側 | 実装側の正 |
| --- | --- | --- |
| P2-25 | workers 上限 `min(cpu_count, 24)` が **4 doc 15 箇所** | `allaganeye/video/detector.py:283` = `min(cpu_count, 32)` |
| P2-26 | CPU Pass 1 を「並列 `-ss` プローブ」と記載 | #214 以降チャンク分割デコード |
| P2-27 | #576 新 path を「output seek + Python 側 sampling」と記載 | dual seek + `select='not(mod(n,N))'` filter (`detector.py:1520,1586`) |
| P2-28 | tuning-guide「デフォルト = `--no-gpu`」 | codec ベース auto (#414) |
| P2-29 | CLAUDE.md モジュール表に 17 module 欠落、§コマンドに `export` 不在 | `allaganeye/` 実ファイル |
| P2-30 | L2 が「開発中」のまま | v0.2.0 / v0.2.1 リリース済み |
| P2-31 | scorebar-design が #803 と**逆**の記述 (「最長 run」)、#797 / #811 不在 | 中央跨ぎ run + 幅上限 1440px |
| P2-32 | system-architecture §2.1 起動経路 / §2.3 export 経路が同一 doc 内 §2.6 と矛盾、quickstart ZIP レイアウトが pre-#752 | #752 / #761 後の実装 |
| P2-33 | versioning「pyproject.toml のみ」 | 3 箇所 (pyproject / tauri.conf.json / package.json)。「Director」旧用語も残存 |
| P2-34 | cli-spec detect 節に `--progress-format` / `--gpu-vendor` 不在、split / detect 両節に `--masked` 不在、export `--concurrency` の codec=copy 規則不在 | `allaganeye/cli.py` / `commands/export.py:256` |
| P2-35 | developer-setup が LGPL 推奨と言いつつ GPL `winget Gyan.FFmpeg` を「推奨」表記 | #508 方針 |
| P3 | gui-development CI「3 ジョブ」 | 実際 8 ジョブ |
| P3 | cli-spec metadata トップレベル表に **7 field** 欠落 + 抜粋である旨の注記なし | `schemas/metadata.schema.json` |
| P3 | output-spec 適用範囲に `detect` 不在 | — |
| 新規 | #860 の PowerShell CIM fallback が CLAUDE.md §GPU モードに不在 | `allaganeye/system_info.py` |
| 新規 | #879 の optional field write 検証硬化が metadata-spec に不在。cli-spec の `_load_cache` は `_load_cache_hit` に改名済み | `gui/src-tauri` / `detection/` |

### ALREADY FIXED (対応不要と確認)

- skill の `../../docs/` 相対リンク 14 件 — 現在すべて `../../../docs/` で正しい
- cli-spec の行番号参照 `:521` — 該当参照は現存しない
- metadata-spec §将来の拡張 の #810 — `capture_regions` として実装済み・本文に記載済み
- `docs/design/bundle/README.md` のパス — doc 内で自己整合

### 監査の計数誤り (2 件)

P2-25 の headline「6 doc 7 箇所」は実測と不一致。実測は **4 doc 15 箇所**
(監査の列挙も 8 箇所で、headline・列挙・実測の三者が食い違っていた)。

cli-spec metadata トップレベル表の欠落も監査は「6 field」としているが、実測は
**7 field** (`schemas/metadata.schema.json` の 16 field に対し doc は 9 field)。
欠落は `schema_version` / `source_fps` / `warnings` / `system_info` /
`brightness_samples` / `capture_regions` / `minimap_regions`。

| doc | 行 | 分類 |
| --- | --- | --- |
| `docs/cli-spec.md` | 53 / 269 / 515 | 仕様主張 → SSoT 化 |
| `docs/cli-spec.md` | 82 | 実測記録 (`allaganeye 0.1.1` と version 印字された出力サンプル) → 保持 |
| `docs/tuning-guide.md` | 173 / 249 | 仕様主張 → SSoT 化 |
| `docs/benchmarks.md` | 78 / 79 | 仕様主張 (§CPU コア数 の指針) → SSoT 化 |
| `docs/benchmarks.md` | 28 / 36 / 50 / 58 | 実測記録 (§性能改善の推移 の計測値) → 保持 |
| `docs/video-processing.md` | 53 | 仕様主張 → SSoT 化 |
| `docs/video-processing.md` | 380 / 381 | 実測記録 (§性能チューニング の施策と計測効果) → 保持 |

**仕様主張 8 箇所を SSoT 化、実測記録 7 箇所を保持**する。

`:380` `:381` は「施策と計測効果」を記録する表であり、`~3x スループット` という
効果は上限 24 で計測された値である。行ごと保持しつつ、現在値と誤読されないよう
計測時点の値である旨を明記する (設計判断 2 の適用)。

上位 spec §W6 の突合指示に従い、この値を引用している
`docs/coding-conventions.md` §背景 も訂正する。訂正後の記述は
「4 doc 15 箇所 (うち仕様主張は 8 箇所)」とし、実測記録との区別を明示する。

## 設計判断

### 1. SSoT の正の置き場所 (workers 上限)

SSoT 規約は「管轄が重なる場合は実装側を正とし、spec doc は具体値を複製せず
『auto (実装の cap に従う)』のような記述 + 実装への参照で書く」と規定し、
worker 数上限を実装 docstring が正となる例として明示している。

したがって **`_resolve_workers` の docstring を正**とし、各 doc は具体値を書かず
参照する。この結果、[doc] issue でありながら Python ファイル (docstring のみ) を
変更する。ロジック変更はゼロ。

`allaganeye/commands/split_matches.py` と `tests/test_split_matches.py` の docstring にも
誤値 24 が残存しており、これらも同時に正へ寄せる。

### 2. 実測記録は書き換えない

workers 上限 24 の出現箇所は「仕様の主張」と「実測記録」が混在している。
**実測記録を 32 に書き換えると、実際には行われていない測定条件を記録することに
なりデータの改竄にあたる**ため、史実として保持する。

保持する 7 箇所:

- `benchmarks.md:28` `:36` — #69 当時の計測条件と、その条件下での所見
- `benchmarks.md:50` `:58` — §性能改善の推移 の時系列記録 (PR 番号付き)
- `video-processing.md:380` `:381` — §性能チューニング の施策と計測効果
  (`~3x スループット` は上限 24 で計測された値)
- `cli-spec.md:82` — `allaganeye 0.1.1` と version 印字された出力サンプル。
  サンプル全体が v0.1.1 時点の実出力であり、workers の数値だけ差し替えると
  version 印字と矛盾する

保持する箇所のうち、現在値と誤読されうる `video-processing.md:380` `:381` には
計測時点の値である旨を明記する。

SSoT 化するのは仕様を主張している 8 箇所のみ。

### 3. 監査 doc は書き換えない

`docs/audits/2026-06-10-full-audit.md` は 2026-06-10 時点の観測記録であり、
履歴として保持する。修正状況の追跡は issue 側で行う。

### 4. ui-interaction-spec の行番号 anchor は本 issue のスコープ外

`docs/ui-interaction-spec.md` は `[File.tsx:NNN]` 形式の code line anchor を 99 箇所
持ち、GUI コードの増分により相当数が stale になっている (#862 コメントで記録)。

これを行番号のまま再同期しても、**行番号は「値の複製」そのもの**であり、
CI ガードが存在しない以上 GUI が 1 PR 動くだけで再 drift する。SSoT 規約が
潰そうとしている構造的問題を再生産するだけになる。

根治には anchor 形式を名前参照 (`ExportScreen.tsx » handleExportClick` 等) へ移行する
設計判断が必要で、これは再同期ではなく形式移行である。よって**別 issue に切り出す**
(Iron Law 3)。v0.3.0 リリースをブロックしないためでもある。

## PR 分割

2 PR に分割する (上位 spec §W6 が許容)。**両 PR で同じファイルを触らない**ことを
不変条件とし、コンフリクトを構造的に排除する。`docs/video-processing.md` は
workers 記述と #576 記述の両方を持つが、アーキテクチャ doc なので全体を PR-B に置く。

### PR-A: CLI / コマンド仕様系

| 変更ファイル | 対象項目 |
| --- | --- |
| `allaganeye/video/detector.py` (docstring) | workers SSoT の**正を確立** |
| `allaganeye/commands/split_matches.py` (docstring) | 誤値 24 → 正へ寄せる |
| `tests/test_split_matches.py` (docstring) | 同上 |
| `docs/cli-spec.md` | P2-25 x3 / P2-34 / metadata 表 7 field + 抜粋注記 / `_load_cache_hit` |
| `docs/tuning-guide.md` | P2-25 x2 / P2-28 |
| `docs/benchmarks.md` | `:78` のみ SSoT 化 |
| `docs/output-spec.md` | 適用範囲に `detect` 追加 |
| `docs/developer-setup.md` | P2-35 |
| `docs/coding-conventions.md` | §背景 の引用値訂正 |

### PR-B: アーキテクチャ説明系

| 変更ファイル | 対象項目 |
| --- | --- |
| `CLAUDE.md` | P2-26 / P2-29 / P2-30 / #860 反映 |
| `docs/design-overview.md` | P2-30 |
| `docs/video-processing.md` | P2-26 / P2-27 / workers リンク化 |
| `docs/scorebar-detection-design.md` | P2-31 |
| `docs/system-architecture.md` | P2-32 |
| `docs/quickstart.md` | P2-32 |
| `docs/versioning.md` | P2-33 |
| `docs/metadata-spec.md` | #879 反映 |
| `docs/gui-development.md` | CI ジョブ数 |

**順序**: PR-A → PR-B。PR-B の workers リンクが PR-A で確立した正を指すため。

## 検証

| 対象 | チェック |
| --- | --- |
| 両 PR | `bash scripts/check-markdownlint.sh` |
| PR-A | `ruff check .` / `ruff format --check .` / `pyright` / `pytest` (全 repo、引数なし) |
| PR-B | doc のみ。markdownlint のみ |

ロジック変更ゼロのため実機検証 trigger (GPU / audio / 長時間動画 / GUI Tauri) は非該当。
CI の doc drift gate (`doc-tauri-commands-drift` / `doc-error-hint-drift`) は本変更で
対象 doc を触らないため影響しない。

PR-A の Python 変更は docstring のみだが、gate は全 repo で回す
(touched-only 指定は変更を漏らして CI を赤にする実績あり)。

## 受け入れ条件

- P2-25〜P2-35 のうち STILL DRIFTED と確認した項目がすべて解消している
- doc 系 P3 のうち STILL DRIFTED と確認した 3 項目が解消している
- #860 / #879 の実装が CLAUDE.md / metadata-spec に反映されている
- workers 上限の仕様主張 8 箇所が SSoT 参照になっている
- 実測記録 7 箇所 (`benchmarks.md:28,36,50,58` / `video-processing.md:380,381` /
  `cli-spec.md:82`) の数値が改変されていない
- `coding-conventions.md` §背景 の引用値が実測と一致している
- 両 PR で `bash scripts/check-markdownlint.sh` が pass する
- PR-A で `ruff check .` / `ruff format --check .` / `pyright` / `pytest` が pass する
- ui-interaction-spec の anchor 移行が別 issue として起票されている

## スコープ外

- `docs/ui-interaction-spec.md` の行番号 anchor 99 箇所 (別 issue へ)
- 監査 doc (`docs/audits/`) の書き換え
- Wave 3 (issue 棚卸し) の項目
- doc 以外の P3 (コード / GUI / テスト)
