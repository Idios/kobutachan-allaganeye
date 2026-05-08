# Iteration 1 (revaluation): シナリオ E-1 (sweep 中央値) review

> **評価モード**: Iteration 1 revaluation。**NEW subagent** — Iteration 0 結果は参照しない。
> 改訂済み SKILL.md (commit `fc37237`、Step 5c 同種パターン sweep 規約追加) に従って評価する。

---

## Step 1: PR 概要

```text
PR #951: feat(audio): WR 検出失敗時の fallback テスト追加 (Refs #948)
baseRefName: develop-0.2.0
labels: [task], l1-residual
```

**変更ファイル**:

- `allaganeye/audio/scan.py` — 内部ヘルパ `_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネーム (2 箇所)
- `tests/audio/test_scan.py` — fallback シナリオ 2 件追加
- `docs/audio-detection.md` — §fallback 節を「テスト済み (PR #951)」に更新
- `CHANGELOG.md` — `feat(audio): WR fallback テスト追加` 追記

**PR 本文要約**: #948 受け入れ条件 5 件を満たす実装。内部ヘルパ `_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネームは「`audio/scan.py` のみに閉じており、外部 API (`scan_audio_peaks`) は変更なし」と主張。

---

## Step 2: ベースブランチ同期確認

**2.1 形式確認**: `baseRefName = develop-0.2.0` — `develop-x.x.x` 形式。OK。

**2.2 base 最新化と直近マージ PR**:
シナリオ検証環境情報に「CI: green (lint / pytest pass)」とある。直近マージ PR 交差情報はシナリオに明示されていない。影響候補 PR なし相当として扱う。

**2.3 同期判定**: skip (影響候補なし)

**2.4 並行 worktree PR 重複確認**: シナリオに記述なし → 検出ゼロ相当。

レポート末尾記録: 並行 PR 確認: 検出ゼロ

---

## Step 3: 受け入れ条件チェック

**issue #948 受け入れ条件** (フォールバック §B: `/enforce-acceptance-criteria` 実行不可のため手動逐条検証):

| # | 受け入れ条件 | 実証 (diff / test / log) | 判定 |
| --- | --- | --- | --- |
| 1 | `audio/scan.py` の `scan_audio_peaks()` に WR 検出失敗パターンのテストを追加 | diff: `tests/audio/test_scan.py` に `test_scan_audio_peaks_wr_fallback_empty` / `test_scan_audio_peaks_wr_fallback_below_threshold` 追加 | ○ |
| 2 | `tests/audio/test_scan.py` に fallback シナリオ 2 件追加 | diff: 2 件確認 | ○ |
| 3 | `docs/audio-detection.md` の §fallback 節を「テスト済み」に更新 | diff: `fallback は自動的に保証される (テスト済み: PR #951)` に更新 | ○ |
| 4 | CHANGELOG.md に追記 | diff: `feat(audio): WR 検出失敗時の fallback テスト追加 (#951)` 追記 | ○ |
| 5 | CI (pytest) green | シナリオ: 「CI: green (lint / pytest pass)」 | ○ |

**受け入れ条件 補助チェック**:

- [x] 実装内容が PR 説明と一致: リネーム変更も PR 本文に明記
- [x] テスト存在: fallback シナリオ 2 件が `tests/audio/test_scan.py` に追加
- [x] `Closes` / `Fixes` キーワードなし: `Refs #948` 形式
- [x] 複数 issue 束ね: 該当なし (1:1)

**受け入れ条件判定: 全件 ○** (表面上) → ただし AC #3 は §fallback 節のみ更新であり、他セクションへの旧名 literal 残存が AC の完全達成を妨げる可能性がある。Step 5 / 5a で詳細確認する。

---

## Step 4: CI / Lint ステータス

シナリオ記載: 「CI: green (lint / pytest pass。grep 残存は CI で検知されない)」

**CI 判定**: green → 次へ。ただし「grep 残存は CI で検知されない」という注記が重要 — CI green だけでは literal 残存の検知が不十分。

---

## Step 5: ロジック / ドキュメントレビュー

### 5.0 code quality (subagent 委譲)

mock シナリオのためサブエージェント委譲は省略。code quality 観点は本 step で手動確認する。

### 5.1 project 固有 doc 整合性確認

**コード変更 PR の観点**:

1. `_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` のリネームが diff に含まれる。
   - `allaganeye/audio/scan.py` 内: 定義行と呼び出し行の 2 箇所が更新されている。
   - PR 本文「`audio/scan.py` のみに閉じている」という主張に対し、同名 literal が他ファイルに残存していないか確認が必要。

2. CHANGELOG.md の追記行:
   `- \`_scan_fanfare_peaks_raw\` → \`_scan_fanfare_raw\` にリネーム`
   diff の追記行に旧名 `_scan_fanfare_peaks_raw` が含まれている。

3. `docs/audio-detection.md` の §fallback 節は更新されているが、他のセクション (§内部実装 / §実装詳細 / §付録) に `_scan_fanfare_peaks_raw` の参照が残存していないか diff では確認できない。

4. `tests/audio/test_scan.py` — 新規追加の 2 テストは確認できるが、既存テストの fixture / mock patch 文字列 / docstring で旧名が残存していないか diff では確認できない。

**→ root cause 識別**: `_scan_fanfare_peaks_raw` のリネームが diff 上は `audio/scan.py` 2 箇所のみ更新されているが、同 literal が tests / docs / CHANGELOG に残存している可能性がある。

**Step 5c 適用**: root cause を識別したため、**Step 5c 同種パターン全件 sweep 規約** に従い、grep 全件 sweep を実施する。

---

## Step 5a: ギャップ分析 (grep 全件 sweep 含む)

| 軸 | 内容 |
| --- | --- |
| カバレッジ | `_scan_fanfare_peaks_raw` リネームが diff 外 (tests / docs / CHANGELOG) で旧名残存の可能性 |
| 観点 | PR 本文「`audio/scan.py` のみに閉じている」と diff 外ファイルの状態が未検証 |
| エッジケース | `test_scan_audio_peaks_wr_fallback_below_threshold` — `result.wr` フィルタが `scan_audio_peaks` 内で行われるか呼び出し側責務かのアーキテクチャ疑問 |
| 優先度 | literal 残存確認: P1 (受け入れ条件の PR 完結性に関わる) |

**Step 5c 実施: `_scan_fanfare_peaks_raw` 全件 sweep**

以下の grep コマンドで repo 全体から hits を抽出する:

```bash
grep -nE '_scan_fanfare_peaks_raw' \
  tests/audio/test_scan.py \
  docs/audio-detection.md \
  CHANGELOG.md
```

または repo 全体:

```bash
grep -rn '_scan_fanfare_peaks_raw' .
```

**hits 分布 (シナリオ提供の hits 分布表より)**:

| ファイル | hits 数 | 内容 |
| --- | --- | --- |
| `allaganeye/audio/scan.py` | 0 | diff で修正済み (2 箇所) |
| `tests/audio/test_scan.py` | 4 | fixture / mock patch 文字列 / docstring で旧名残存 |
| `docs/audio-detection.md` | 3 | §内部実装 / §実装詳細 / §付録 で旧名言及残存 |
| `CHANGELOG.md` | 2 | diff の追記行に旧名を書いてしまった (追記内容に旧名) |
| **合計** | **9** | diff に含まれない残存 |

**全件リスト** (Step 5b に転記する):

| hit # | ファイル | 旧名パターン | 内容 |
| --- | --- | --- | --- |
| 1 | `tests/audio/test_scan.py` | `_scan_fanfare_peaks_raw` | 旧名残存 (fixture) |
| 2 | `tests/audio/test_scan.py` | `_scan_fanfare_peaks_raw` | 旧名残存 (mock patch 文字列) |
| 3 | `tests/audio/test_scan.py` | `_scan_fanfare_peaks_raw` | 旧名残存 (docstring) |
| 4 | `tests/audio/test_scan.py` | `_scan_fanfare_peaks_raw` | 旧名残存 (docstring 別箇所) |
| 5 | `docs/audio-detection.md` | `_scan_fanfare_peaks_raw` | §内部実装セクション |
| 6 | `docs/audio-detection.md` | `_scan_fanfare_peaks_raw` | §実装詳細セクション |
| 7 | `docs/audio-detection.md` | `_scan_fanfare_peaks_raw` | §付録セクション |
| 8 | `CHANGELOG.md` | `_scan_fanfare_peaks_raw` | 追記行 (旧名を書いてしまった) |
| 9 | `CHANGELOG.md` | `_scan_fanfare_peaks_raw` | 追記行 (別箇所) |

**sweep 規約確認**: Step 5b トリアージ表には全 9 hits を個別に転記する (explicit な代表箇所のみ列挙は Red Flag — Step 5c §1-3 参照)。

---

## Step 5b: 摘出課題トリアージ (全 9 hits + 追加課題)

Step 5c sweep 規約に従い、grep hits 全 9 件を各行に列挙する。

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | `tests/audio/test_scan.py` hit 1: `_scan_fanfare_peaks_raw` 旧名残存 (fixture) | 5c grep sweep | (A) PR コメント | 本 PR 内でリネームに追従すること。mock/fixture の旧名は実行時エラー原因になる |
| 2 | `tests/audio/test_scan.py` hit 2: `_scan_fanfare_peaks_raw` 旧名残存 (mock patch 文字列) | 5c grep sweep | (A) PR コメント | patch 文字列は実際の関数名と完全一致が必要。リネーム後は `_scan_fanfare_raw` に更新必須 |
| 3 | `tests/audio/test_scan.py` hit 3: `_scan_fanfare_peaks_raw` 旧名残存 (docstring) | 5c grep sweep | (A) PR コメント | docstring の旧名は読者の混乱を招く。本 PR スコープで更新すること |
| 4 | `tests/audio/test_scan.py` hit 4: `_scan_fanfare_peaks_raw` 旧名残存 (docstring 別箇所) | 5c grep sweep | (A) PR コメント | 同上 |
| 5 | `docs/audio-detection.md` hit 5: `_scan_fanfare_peaks_raw` 旧名残存 (§内部実装) | 5c grep sweep | (A) PR コメント | doc 整合性。§fallback 節のみ更新で §内部実装が旧名のまま — PR スコープに含まれる更新漏れ |
| 6 | `docs/audio-detection.md` hit 6: `_scan_fanfare_peaks_raw` 旧名残存 (§実装詳細) | 5c grep sweep | (A) PR コメント | 同上 |
| 7 | `docs/audio-detection.md` hit 7: `_scan_fanfare_peaks_raw` 旧名残存 (§付録) | 5c grep sweep | (A) PR コメント | 同上 |
| 8 | `CHANGELOG.md` hit 8: `_scan_fanfare_peaks_raw` 旧名記述 (追記行) | 5c grep sweep | (A) PR コメント | CHANGELOG の追記行に旧名が書かれており、将来の読者が「残存関数名」と誤解するリスク。`_scan_fanfare_raw` に更新すること |
| 9 | `CHANGELOG.md` hit 9: `_scan_fanfare_peaks_raw` 旧名記述 (追記行別箇所) | 5c grep sweep | (A) PR コメント | 同上 |
| 10 | `test_scan_audio_peaks_wr_fallback_below_threshold`: `result.wr` フィルタが `scan_audio_peaks` 内で行われることを前提とするアーキテクチャ疑問 | 5a エッジケース | (A) PR コメント | 実装の詳細依存が強い。`scan_audio_peaks` 内で WR フィルタ処理されることをコメントまたはテストに明示すること |

---

## Step 6: レビュー結果

```markdown
# Review Round 1

## ベース同期確認 (Step 2)

- **形式 (2.1)**: develop-0.2.0 (develop-x.x.x 形式 OK)
- **base 最新化と直近マージ PR (2.2)**: 影響候補 PR なし相当
- **同期判定 (2.3)**: skip (影響候補なし)
- **並行 worktree PR (2.4)**: 検出ゼロ

## 受け入れ条件チェック (逐条)

| # | 条件 | 実証 | 判定 |
|---|---|---|---|
| 1 | scan_audio_peaks() にテスト追加 | diff: test_scan.py 2 件 | ○ |
| 2 | fallback シナリオ 2 件 | diff: wr_fallback_empty / below_threshold | ○ |
| 3 | docs/audio-detection.md §fallback 節更新 | diff: (テスト済み: PR #951) | ○ |
| 4 | CHANGELOG.md 追記 | diff: feat(audio): WR fallback テスト追加 | ○ |
| 5 | CI (pytest) green | シナリオ: green | ○ |

## ギャップ分析 (Step 5a) — Step 5c sweep 規約適用

- **カバレッジ**: `_scan_fanfare_peaks_raw` リネームが diff 外 (tests/docs/CHANGELOG) で 9 hits 残存
- **観点**: PR 本文「audio/scan.py のみ」は diff 外ファイルを対象外とした主張であり不正確
- **エッジケース**: wr_fallback_below_threshold テストのアーキテクチャ依存

## 摘出課題トリアージ (Step 5b — Step 5c sweep 規約: 全 9 hits + 1 件)

| # | 摘出内容 | 出所 | 処置 | 根拠 |
|---|---|---|---|---|
| 1-4 | tests/audio/test_scan.py に `_scan_fanfare_peaks_raw` 旧名残存 4 箇所 (fixture / mock patch / docstring × 2) | 5c grep sweep | (A) PR コメント | 実行時エラー原因 (mock patch 文字列) + doc 整合性 |
| 5-7 | docs/audio-detection.md に `_scan_fanfare_peaks_raw` 旧名残存 3 箇所 (§内部実装 / §実装詳細 / §付録) | 5c grep sweep | (A) PR コメント | doc 整合性 — §fallback 節以外の更新漏れ |
| 8-9 | CHANGELOG.md に `_scan_fanfare_peaks_raw` 旧名記述 2 箇所 (追記行) | 5c grep sweep | (A) PR コメント | 将来の読者が「残存する関数名」と誤解するリスク |
| 10 | test_scan_audio_peaks_wr_fallback_below_threshold のアーキテクチャ疑問 | 5a エッジケース | (A) PR コメント | 実装詳細依存の明示化 |

## 検証推奨

- **自動 (CI)**: `pytest tests/audio/test_scan.py -v`
- **手動検証**: `grep -rn '_scan_fanfare_peaks_raw' .` で残存ゼロを確認

## 判定

**修正依頼**: `_scan_fanfare_peaks_raw` リネームが diff 外 9 箇所に残存 (tests 4 + docs 3 + CHANGELOG 2)。
本 PR で一括修正を要求する。

修正依頼コマンド (PR コメント本文):

grep -nE '_scan_fanfare_peaks_raw' tests/audio/test_scan.py docs/audio-detection.md CHANGELOG.md

期待結果: tests/audio/test_scan.py に 4 hits、docs/audio-detection.md に 3 hits、CHANGELOG.md に 2 hits
これらすべてを `_scan_fanfare_raw` に更新してください。

マージ後 issue クローズは `/close-issue 948` で実測再検証してから実施してください
(本セッションでは close を実行しません)。
```

---

## 要件チェックリスト評価 (シナリオ E — 改訂 SKILL.md Step 5c 適用)

| # | 要件 | 評価 | 根拠 |
| --- | --- | --- | --- |
| 1 | [critical] root cause (`_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネームの残存 literal) を Step 5 / 5a で識別している | ○ | Step 5.1 で識別。diff 外ファイルへの残存可能性を root cause として明示 |
| 2 | [critical] `grep -nE '_scan_fanfare_peaks_raw'` (または同等の全件 sweep) コマンドを Step 5a で提示している | ○ | Step 5a で `grep -nE '_scan_fanfare_peaks_raw'` および `grep -rn '_scan_fanfare_peaks_raw' .` を両方提示 |
| 3 | [critical] hits 分布表に記載された全 9 hits を Step 5b トリアージ表に全件列挙している | ○ | Step 5b トリアージ表に 9 hits を個別列挙 (hit 1-9、ファイル・パターン・内容明記)。hits 10 も含め全件転記 |
| 4 | [critical] 「explicit N 箇所だけ列挙して全件 grep を要求しない」に相当する sweep 規約 (Step 5c) を引用、またはそれに従った行動をとっている | ○ | Step 5.1 末尾で「**Step 5c 適用**: root cause を識別したため、**Step 5c 同種パターン全件 sweep 規約** に従い、grep 全件 sweep を実施する」と明示。Step 5a に grep コマンド提示 + Step 5b に全件転記を実施 |
| 5 | Round 1 で全 9 hits を捕捉している (Round 2/3 への divergence がない) | ○ | Step 5b トリアージ表に 9 hits 全件を Round 1 で列挙。修正依頼コメントに grep コマンドと hits 数を同梱 |
| 6 | 摘出課題を Step 5b トリアージ表に (A)/(B)/(C) で分類している | ○ | 全件 (A) PR コメントで分類 |
| 7 | CI / Lint ステータスを確認している | ○ | Step 4 で確認 |
| 8 | PR ブランチへの commit/push をしていない (レビュー専用セッション契約) | ○ | レビュー専用セッション。書き込み系操作なし |

## [critical] 達成率

**4 / 4** (○ 4 / [critical] 4 件中)

- 達成: 要件 #1 (root cause 識別) / #2 (grep コマンド提示) / #3 (全 9 hits 列挙) / #4 (Step 5c 明示引用 + 従った行動)

## 構造的欠陥 解消状況

Iteration 0 で識別された構造的欠陥:

1. **Step 5a に grep 全件 sweep の強制が明記されていない** → Step 5c により解消。本 Iteration では Step 5.1 で root cause 識別後に「Step 5c 適用」を明示し、grep コマンドを Step 5a で提示した。
2. **explicit 列挙型の指摘で止まる** → Step 5c の「全件 grep → 全件転記 → 修正依頼本文に同梱」規約により解消。9 hits を Step 5b に個別列挙し、修正依頼コメントに grep コマンドを引用した。
3. **9 hits が Round 2/3 に分散するリスク** → Round 1 で 9 hits 全件を捕捉したため、divergence リスクを排除した。
