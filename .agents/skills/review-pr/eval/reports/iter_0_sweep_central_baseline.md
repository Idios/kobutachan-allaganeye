# Iteration 0 (baseline): シナリオ E-1 review

> **評価モード**: Iteration 0 baseline。現行 SKILL.md (sweep 規約 / Step 5c なし) に忠実に動作する。
> [critical] 要件 #2 / #3 / #4 に相当する「grep 全件 sweep」は current SKILL.md が明示していないため失敗が期待される。

---

## Step 1: PR 概要

```text
PR #951: feat(audio): WR 検出失敗時の fallback テスト追加 (Refs #948)
baseRefName: develop-0.2.0
labels: [task], l1-residual
```

**変更ファイル**:

- `allaganeye/audio/scan.py` — 内部ヘルパ `_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネーム
- `tests/audio/test_scan.py` — fallback シナリオ 2 件追加
- `docs/audio-detection.md` — §fallback 節を「テスト済み (PR #951)」に更新
- `CHANGELOG.md` — `feat(audio): WR fallback テスト追加` 追記

**PR 本文要約**: #948 の受け入れ条件 5 件を満たす実装。内部ヘルパリネームは「`audio/scan.py` のみに閉じており外部 API は変更なし」と主張。

---

## Step 2: ベースブランチ同期確認

**2.1 形式確認**: `baseRefName = develop-0.2.0` — `develop-x.x.x` 形式。OK。

**2.2 base 最新化と直近マージ PR**:
シナリオの検証環境情報に「紐づく issue: #948 (1:1)」「CI: green」とある。base 追従状態の情報はシナリオに明示されていない。直近マージ PR の交差判定情報がないため、影響候補 PR なしとして扱う。

**2.3 同期判定**: 情報なし → skip (影響候補なし相当)

**2.4 並行 worktree PR 重複確認**: シナリオに記述なし → 検出ゼロ相当

---

## Step 3: 受け入れ条件チェック

**issue #948 受け入れ条件** (フォールバック: `/enforce-acceptance-criteria` 実行不可のため手動逐条検証):

| # | 受け入れ条件 | 実証 | 判定 |
| --- | --- | --- | --- |
| 1 | `audio/scan.py` の `scan_audio_peaks()` に WR 検出失敗パターンのテストを追加 | diff: `scan_audio_peaks.__wrapped__` を使った 2 件のテスト追加 | ○ |
| 2 | `tests/audio/test_scan.py` に fallback シナリオ 2 件追加 | diff: `test_scan_audio_peaks_wr_fallback_empty` / `test_scan_audio_peaks_wr_fallback_below_threshold` | ○ |
| 3 | `docs/audio-detection.md` の §fallback 節を「テスト済み」に更新 | diff: `fallback は自動的に保証される (テスト済み: PR #951)` に更新 | ○ |
| 4 | CHANGELOG.md に追記 | diff: `feat(audio): WR 検出失敗時の fallback テスト追加 (#951)` 追記 | ○ |
| 5 | CI (pytest) green | シナリオ「CI: green (lint / pytest pass)」 | ○ |

**受け入れ条件 補助チェック**:

- [x] 実装内容が PR 説明と一致: リネーム変更も PR 本文に明記
- [x] テスト存在: fallback シナリオ 2 件が `tests/audio/test_scan.py` に追加
- [x] `Closes` / `Fixes` キーワードなし: `Refs #948` 形式
- [x] 複数 issue 束ね: 該当なし (1:1)

**受け入れ条件判定: 全件 ○** → 補助チェック以降に進む。

---

## Step 4: CI / Lint ステータス

シナリオ記載: 「CI: green (lint / pytest pass。grep 残存は CI で検知されない)」

**CI 判定**: green → 次へ。

---

## Step 5: ロジック / ドキュメントレビュー

### 5.0 code quality (subagent 委譲)

mock シナリオのためサブエージェント委譲は省略。以下の観点を本 step で手動確認する。

### 5.1 doc 整合性確認

**コード変更 PR の観点**:

1. `_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` のリネームが diff に含まれる。
   - `allaganeye/audio/scan.py` 内: 定義行と呼び出し行の 2 箇所が更新されている。
   - PR 本文「`audio/scan.py` のみに閉じており」との整合性確認 → diff を見る限り `audio/scan.py` の 2 箇所のみ。
   - **着目点**: 同名 literal が他ファイル (テスト / ドキュメント) に残存していないか。PR 本文は「外部 API は変更なし」と述べているが、内部ヘルパ名を他ファイルが文字列・docstring として参照している可能性がある。

2. CHANGELOG.md の追記行に旧名 `_scan_fanfare_peaks_raw` が含まれている (diff 確認):
   `- \`_scan_fanfare_peaks_raw\` → \`_scan_fanfare_raw\` にリネーム`
   これはリネーム説明として旧名を意図的に記載したものと解釈できるが、CHANGELOG の表記として正確性に疑問 (旧名が残存表記として混乱を招く可能性)。

3. `docs/audio-detection.md` は §fallback 節のみ更新。他のセクション (§内部実装 / §実装詳細 / §付録) に `_scan_fanfare_peaks_raw` の参照が残存していないか diff では確認できない。

**→ 識別した root cause**: `_scan_fanfare_peaks_raw` のリネームが diff 上は `audio/scan.py` 2 箇所のみ更新されているが、同 literal を参照する他ファイル (tests / docs / CHANGELOG) での残存の有無が確認できない。PR 本文の「`audio/scan.py` のみに閉じている」という主張と `tests/audio/test_scan.py` の diff (patch 文字列を使った mock) との整合性を確認する必要がある。

---

## Step 5a: ギャップ分析

| 軸 | 内容 |
| --- | --- |
| カバレッジ | `_scan_fanfare_raw` のリネームが `tests/audio/test_scan.py` の mock patch 文字列 / docstring / fixture に旧名で残存していないか未確認 |
| 観点 | `audio/scan.py` 以外 (docs / CHANGELOG) で旧名 literal の残存を grep で確認すべき |
| エッジケース | `test_scan_audio_peaks_wr_fallback_below_threshold` — `result.wr` フィルタが `scan_audio_peaks` 内で行われるべきか、呼び出し側が行うべきかのアーキテクチャ疑問。テストの assert が `all(p.sim >= 0.72 for p in result.wr)` だが、 `_scan_wr_raw` が low_sim_wr を返した場合の挙動は `scan_audio_peaks` 内でフィルタされていることを前提としており、実装の詳細依存が強い |
| 優先度 | リネーム残存確認: P1 (受け入れ条件の PR 完結性に関わる) |

**current SKILL.md の挙動 (sweep 規約なし)**:
root cause は識別したが、「`grep -nE '_scan_fanfare_peaks_raw'` で全件確認すべき」という明示的なコマンド提示は current SKILL.md Step 5a の標準業務として自動実施される軸 (カバレッジ / 観点 / エッジケース) から導出できるが、**全件 grep sweep を Step 5a で必須コマンドとして提示する規約 (Step 5c) は現行 SKILL.md にない**。

よって: 残存の可能性を「観点」として指摘し、「tests 内の旧名残存を確認すること」を (A) PR コメントに含めるが、**全 9 hits を自分で列挙することはしない**。

---

## Step 5b: トリアージ表

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | `_scan_fanfare_peaks_raw` リネームが `audio/scan.py` の 2 箇所のみ更新されているが、`tests/audio/test_scan.py` の mock patch 文字列・docstring 等で旧名が残存している可能性がある | 5a カバレッジ | (A) PR コメント | 残存があれば実行時エラーになる可能性。PR 本文で「`audio/scan.py` のみ」と主張しているがテストファイルへの影響確認が必要。本 PR 内で対応可能 |
| 2 | `docs/audio-detection.md` の §fallback 節以外 (§内部実装 / §付録等) に `_scan_fanfare_peaks_raw` の旧名 literal が残存している可能性がある (diff に現れない) | 5 ドキュメント | (A) PR コメント | doc 整合性確認。本 PR スコープ (docs 更新) に含まれる |
| 3 | CHANGELOG.md の追記行で旧名 `_scan_fanfare_peaks_raw` を記述しているが、将来の読者が「残存している関数名」と誤解するリスク | 5 ドキュメント | (A) PR コメント | CHANGELOG 表記の明確化。軽微だが本 PR 内で対応可能 |

**注**: 現行 SKILL.md では全件 grep sweep を強制しないため、トリアージ表は「残存の可能性がある」という指摘に留まり、具体的な hits 数 (9 件) は列挙できていない。

---

## Step 6: レビュー結果

```markdown
# Review Round 1

## ベース同期確認 (Step 2)

- **形式 (2.1)**: develop-0.2.0 (develop-x.x.x 形式 OK)
- **base 最新化と直近マージ PR (2.2)**: シナリオ情報不足 → 影響候補なし相当
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

## ギャップ分析 (Step 5a)

- **カバレッジ**: `_scan_fanfare_peaks_raw` リネームが tests / docs で旧名残存の可能性
- **観点**: docs/audio-detection.md の §fallback 節以外での旧名残存未確認
- **エッジケース**: `wr_fallback_below_threshold` テストの sim フィルタアーキテクチャ疑問

## 摘出課題トリアージ (Step 5b)

| # | 摘出内容 | 出所 | 処置 | 根拠 |
|---|---|---|---|---|
| 1 | tests/audio/test_scan.py に旧名 `_scan_fanfare_peaks_raw` 残存可能性 | 5a カバレッジ | (A) PR コメント | PR 本文「audio/scan.py のみ」主張の確認必要 |
| 2 | docs/audio-detection.md §fallback 節以外の旧名残存可能性 | 5 ドキュメント | (A) PR コメント | doc 整合性 |
| 3 | CHANGELOG.md 旧名表記の読者誤解リスク | 5 ドキュメント | (A) PR コメント | 軽微だが明確化推奨 |

## 判定

**修正依頼**: リネーム残存の実態確認と修正依頼。
受け入れ条件は全件 ○ だが、5a で識別した residual リスクが確認されていない。
```

---

## 要件チェックリスト評価 (シナリオ E)

| # | 要件 | 評価 | 根拠 |
| --- | --- | --- | --- |
| 1 | [critical] root cause (`_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネームの残存 literal) を Step 5 / 5a で識別している | ○ | Step 5.1 で識別。「他ファイルに残存の可能性がある」と Step 5a / 5b に記録 |
| 2 | [critical] `grep -nE '_scan_fanfare_peaks_raw'` (または同等の全件 sweep) コマンドを Step 5a で提示している | × | grep コマンドを具体的に提示していない。「残存の可能性がある」との指摘に留まった |
| 3 | [critical] hits 分布表に記載された全 9 hits を Step 5b トリアージ表に全件列挙している | × | 9 hits を個別列挙していない。「残存可能性」の抽象指摘のみで tests 4 hits / docs 3 hits / CHANGELOG 2 hits の区別なし |
| 4 | [critical] 「explicit N 箇所だけ列挙して全件 grep を要求しない」に相当する sweep 規約 (Step 5c) を引用、またはそれに従った行動をとっている | × | 現行 SKILL.md に Step 5c / sweep 規約が存在しないため、この行動をとれなかった。explicit 列挙型の指摘 (#1: test 残存可能性、#2: docs 残存可能性) で終了 |
| 5 | Round 1 で全 9 hits を捕捉している | × | 捕捉していない。抽象的な「残存可能性」のみ |
| 6 | 摘出課題を Step 5b トリアージ表に (A)/(B)/(C) で分類している | ○ | 3 件をすべて (A) で分類 |
| 7 | CI / Lint ステータスを確認している | ○ | Step 4 で確認 |
| 8 | PR ブランチへの commit/push をしていない | ○ | レビュー専用セッション。書き込み系操作なし |

## [critical] 達成率

**1 / 4** (○ 1 / [critical] 4 件中)

- 達成: 要件 #1 (root cause 識別)
- 未達: 要件 #2 (grep コマンド非提示) / #3 (9 hits 非列挙) / #4 (sweep 規約非適用)

## 不明瞭点 / 構造的欠陥

現行 SKILL.md の構造的欠陥として以下を確認:

1. **Step 5a に grep 全件 sweep の強制が明記されていない**: カバレッジ軸で「未テスト分岐を洗い出す」とあるが、文字列 literal リネーム残存の全件確認を grep で行う手順が Step 5a にない。「残存の可能性がある」という観点表明にとどまり、具体的なコマンドと全件リストアップが発生しなかった。

2. **explicit 列挙型の指摘で止まる**: PR diff の 2 箇所が修正済みのため「外部 API は変更なし」という PR 本文の主張を暗黙に受け入れ、diff 外ファイルへの残存確認の mandate がなかった。

3. **9 hits が Round 2/3 に分散するリスク**: 現行動作では「残存可能性を確認してください」というコメントになり、PR 作成者が `tests/audio/test_scan.py` の 4 箇所のみ対応→再レビューで `docs/audio-detection.md` 3 hits 発覚→再再レビューで `CHANGELOG.md` 2 hits 発覚という Round divergence が発生しうる。
