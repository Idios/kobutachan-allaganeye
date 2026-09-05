# sweep 規約検証 — 前段階事例調査メモ

## 目的

`feedback_skill_revision_empirical.md` の原則「指摘ラウンドが多かった実在 PR を 3 本ピックアップし、
Explore agent 並列で指摘パターンを抽出してからモック設計」に従い、
Step 5c sweep 規約 (issue #682) のモック設計と SKILL.md 改訂の根拠データを収集する。

---

## Agent A — 過去 PR の round 数集計 (結果)

`develop-0.2.0` ベース直近 30 PR を調査し、Round 2+ コメントを含む PR を特定した。

### Round 数集計表 (上位 5 本)

| PR | title (要約) | Round 数 | 備考 |
| --- | --- | --- | --- |
| #627 | feat(metadata): JSON Schema 化 + 型 codegen 導入 | **6** | 最多。doc literal 散在 + base conflict 未解消で長期化 |
| #675 | fix: StateSwitcher を dev only に (Refs #653) | **4** | 今回除外対象 (Agent B で精読) |
| #661 | feat(gui): GUI クラッシュ・エラー伝搬ハンドリング | **3** | PR body 更新漏れが Round 2 で発覚 |
| #655 | feat(gui): DropScreen 直近録画リスト本物化 | **2** | Round 1 修正後 Round 2 LGTM |
| #662 | fix(gui): detect 子プロセスの UTF-8 stdout 強制 | **2** | Round 1 修正後 Round 2 LGTM |

**上位 3 本 (PR #675 除外後)**: #627 (6 rounds) / #661 (3 rounds) / #655 or #662 (2 rounds)

> 多くの PR は 2 Round で収束しており、3 Round 以上は #627 / #675 / #661 に限られた。
> Round 2 だけの PR が最多ボリュームゾーンで、「1 回の修正依頼で全件解消 → LGTM」が標準パターン。

---

## Agent B — PR #675 round 詳細精読 (結果)

### PR #675 の基本情報

| 項目 | 値 |
| --- | --- |
| タイトル | fix: StateSwitcher を dev only に絞り topBar との z-index 重複を解消 (Refs #653) |
| Round 数 | **4** (Round 4 で LGTM) |
| 関連 issue | #653 |
| 散在 file 数 | 4 (StateSwitcher.tsx / StateSwitcher.test.tsx / spec doc / plan doc) |

### Round × 摘出数 × 見落としのクロス表

| Round | 摘出件数 | 見落とし (次 Round で発覚) |
| --- | --- | --- |
| Round 1 | 5 件 (A) + 1 件 (B スコープ拡大合意) | plan doc #5b で「Task 2 Step 2 のみ修正、他 4 箇所未修正」が Round 2 で発覚 → **4 箇所見落とし** |
| Round 2 | 2 件 (A) | plan doc の「#9」同種パターン追加 4 箇所が Round 3 で発覚 |
| Round 3 | 4 箇所 (A) | なし (Round 4 で全解消) |
| Round 4 | 新出なし → LGTM | — |

### 各 Round の root cause 内訳

**Round 1** で抽出された root cause (6 件):

1. test API 誤用 `vi.stubEnv('DEV', '' as any)` — vitest 4.x では `value: boolean` 必須
2. DCE 誇張コメント「本 component が tree から除去」— subscription は残存
3. production state simulate 不足 (`PROD=true` 未設定)
4. commit message vs 実装乖離 (observation only)
5. spec/plan doc literal「関数本体先頭」が実装と逆 (hook は early return より前)
6. scope-guard: Tier 0 doc 同梱判定

**Round 2** で抽出された root cause (2 件):

1. build-windows CI 失敗 = `get-pip.py` SHA pin 陳腐化 (#649 の再発)
2. plan doc `#5b` 修正が部分適用: Line 7 / 17 / 195-198 / 354 の 4 箇所残存

**Round 3** で抽出された root cause (1 件、4 箇所散在):

1. plan doc に同種パターン (Round 1 #5 / Round 2 #2 と同 root cause) が追加 4 箇所残存
   — 原因: Round 2 review 指示が「explicit な 4 箇所」のみで grep 全件 sweep を要求していなかった

### PR #675 の root cause 分類

| root cause 種類 | 具体例 | 影響ファイル数 |
| --- | --- | --- |
| **literal mismatch (doc ↔ 実装)** | 「関数本体先頭」literal が 8 箇所に散在 (spec 1 + plan 7) | 2 ファイル (spec doc / plan doc) |
| **DCE 誇張表現** | 「本 component が tree から除去」→ subscription は esbuild が温存 | 1 ファイル (StateSwitcher.tsx) |
| **旧 API 使用** | `vi.stubEnv('DEV', '' as any)` → vitest 4.x は boolean 要求 | 1 ファイル (StateSwitcher.test.tsx) |
| **外部依存 SHA 陳腐化** | `get-pip.py` SHA256 が PyPA 更新で無効化 | 1 ファイル (build-portable-zip.ps1) |

### key finding: literal mismatch の「sweep 失敗」パターン

Round 1 で `#5b` として literal 箇所を「修正依頼」したが、review 指示が特定 line のみを列挙 →
修正者が列挙された箇所のみ修正 → **同 file 内の他箇所や同 pattern の他 section が残存** →
Round 2 で再発見 → 4 箇所指摘 → Round 3 でさらに 4 箇所発見。

この「**grep 全件 sweep なし → 部分修正 → 同パターン再発**」が #675 Round 増加の根本原因。
Round 3 コメントで skill 自身が認識: 「**review-pr skill 改善余地あり**」と明記。

---

## PR #627 詳細 (Agent A 補完)

### 基本情報

| 項目 | 値 |
| --- | --- |
| タイトル | feat(metadata): JSON Schema 化 + 型 codegen 導入 (Refs #612) |
| Round 数 | **6** (Round 6 で LGTM) |
| 散在 file 数 | 多数 (schema.json / TypedDict / interface / zod / `_build_metadata_payload` / splitter.py / detect.py / test 5 ファイル + PR 本文) |

### Round × root cause × 摘出数のクロス表

| Round | root cause 主因 | 摘出件数 | 見落とし |
| --- | --- | --- | --- |
| Round 1 | doc literal「JSON Schema は strict」と実装の乖離 (root + 5 `$defs` に `additionalProperties` 未明示) | 1 件 (A) | PR 本文の literal が Round 2 で指摘 |
| Round 2 | PR 本文の literal 修正漏れ (Round 1 指摘の部分未解消) + base merge conflict + CI 未実行 | 3 件 (A) | Round 3: PR 本文の修正が再度未対応のまま |
| Round 3 | PR 本文修正未対応 (Round 2 継続) + base conflict 再発 (PR #637 マージで base 進行) | 3 件 (A) | — |
| Round 4 | #586 regression: `detection_started_at` / `detection_completed_at` が schema/実装 5 ファイルに欠落 | 1 件 (CRITICAL) | CI build-windows pending (Round 4 時点) |
| Round 5 | Round 4 #586 regression 未対応 + base 再取り込み未実施 | 2 件 (A) | — |
| Round 6 | 新出なし → LGTM | 0 | — |

### PR #627 の root cause 分類

| root cause 種類 | 具体例 | 影響ファイル数 |
| --- | --- | --- |
| **literal mismatch (PR 本文 ↔ 実装)** | 「strict (`additionalProperties` 明示なし)」が 3 Round 連続で未修正 | 1 ファイル (PR 本文) |
| **base conflict 未解消** | empty commit でトリガー試行 → CI 未実行のまま | PR 状態 |
| **regression 検出漏れ** | base 取り込み時に #586 (`detection_started_at` 等) が schema/5 ファイルに統合されなかった | 5 ファイル |

### key finding: base 取り込み時 regression が複数ファイルに波及

Round 4 で「CRITICAL」として発覚した #586 regression は、base 取り込み時に既存フィールドが
新 schema 構造に統合されなかったことが原因。影響ファイルが 5 つに散在し、1 ファイル修正では
「他ファイルへの伝搬確認」が必要なケース。**sweep なしで 1 ファイルの修正指示のみ → 残 4 ファイルに残存**。

---

## PR #661 詳細 (Agent A 補完)

### 基本情報

| 項目 | 値 |
| --- | --- |
| タイトル | feat(gui): GUI クラッシュ・エラー伝搬ハンドリング (Refs #614) |
| Round 数 | **3** (Round 3 で LGTM) |
| 散在 file 数 | 1 (PR body のみ) |

### Round × root cause

| Round | root cause | 摘出件数 | 見落とし |
| --- | --- | --- | --- |
| Round 1 | 実機検証不足 (CI 未実行状態) + Round 3-6 での検証参照の整合性確認 | 4 件 (A) | — |
| Round 2 | PR body の更新漏れ: Round 2 の実装変更 (Backtrace 削除 / dep 削除 / AC 変更 等) が PR body に未反映 | 1 件 (A) | — |
| Round 3 | 新出なし → LGTM | 0 | — |

### key finding: 実装変更が PR body に追従しないパターン

issue body は更新されたが PR body は Round 1 時点のまま。実装変更が複数の
PR body セクション (「主な変更」「受け入れ条件」「Self-Test Report」「ログ管理」) に
波及していたが、1 箇所のみ指摘 → 他セクションは自然言語確認のみ → Round 2 で集中指摘。
この PR は「**単一 file (PR body) 内の複数箇所漏れ**」パターン。

---

## SKILL.md 改訂対象 line (Agent C の出力)

### heading 一覧 (改訂関連箇所)

| 改訂対象 | line 番号 | heading text | 挿入候補 |
| --- | --- | --- | --- |
| Step 5b (摘出課題のトリアージ) | **186** | `### 5b. 摘出課題のトリアージ (握り潰し禁止、原則 (A) で完結)` | Step 5c は line 244 以降 (Step 5b 終端 = `### 6.` の直前) に挿入 |
| Red flags 表 | **504** | `## Red flags (レビュー中に浮かんだら STOP)` | sweep 関連 flag を line 521 (表末尾) に追記 |
| よくある失敗 表 | **522** | `## よくある失敗` | sweep 失敗パターンを line 533 (表末尾) に追記 |

### 挿入位置の詳細

> **注**: 以下の line 番号は本メモ commit 時点 (`63a114d`) の値。Task 5 実行時は SKILL.md が他 PR で更新されている可能性があるため `grep -nE "^### 5b|^## Red flags|^## よくある失敗" .claude/skills/review-pr/SKILL.md` で再確認すること。

```text
line 186: ### 5b. 摘出課題のトリアージ ... (Step 5b 開始)
  ...
line 244:   (Step 5b 終端、次は ### 6.)
line 245: ### 6. レビュー結果をユーザーに報告
  ↑ ここの直前 (line 244 と 245 の間) に ### 5c. 挿入
```

```text
line 504: ## Red flags ...
  ...
line 521:   (Red flags 表の末尾行)
line 522: ## よくある失敗
  ↑ この直前に sweep 関連 flag 行を追記
```

```text
line 522: ## よくある失敗
  ...
line 533:   (よくある失敗 表末尾)
line 534: ## 参考
  ↑ この直前に sweep 失敗パターン行を追記
```

---

## 抽出パターン

調査 3 本 (PR #627 / #675 / #661) から、Round 増加の共通構造を以下に分類する。

### パターン A: 「explicit 列挙 + 部分修正 + 同パターン再発」

- **代表例**: PR #675 Round 1 `#5b` / Round 2 `#8` / Round 3 `#9`
- **メカニズム**: review 指示が「ここを直してください」と explicit な箇所を列挙 →
  修正者がそこだけ修正 → 同 file / 同 pattern の他箇所に同じ root cause が残存 →
  次 Round でまた発見
- **根本**: **review 側が修正後の全体確認 (sweep) を要求しなかった**ことで、
  修正者が「列挙された箇所のみ修正すればよい」と理解

### パターン B: 「base 取り込み時の regression 未検出」

- **代表例**: PR #627 Round 4 (#586 regression: 5 ファイルに欠落)
- **メカニズム**: base 取り込みで既存フィールドを新構造に統合する際、
  影響ファイルを網羅的に確認しないまま push → 次 Round で CRITICAL として発覚
- **根本**: base 取り込み後に「既存実装の伝搬確認」を要求する手順が skill になかった

### パターン C: 「PR body の追従漏れ (単一 file 内複数箇所)」

- **代表例**: PR #661 Round 2 / PR #627 Round 2-3
- **メカニズム**: 実装変更後に PR body の「受け入れ条件」「Self-Test Report」等の
  複数セクションが陳腐化 → 1 箇所を更新したつもりで他セクションを見落とす
- **根本**: PR body 変更後の「全セクション一致確認」がレビューフローに組み込まれていない

---

## モック設計への影響

| モック名 | ベース PR | 再現パターン | 主要検証観点 |
| --- | --- | --- | --- |
| `scenario_e_sweep_central` | #675 | パターン A: 単一 root cause が plan doc 複数箇所に散在 | Round 2+ で sweep 要求後に残存ゼロになるか |
| `scenario_e_sweep_edge_mixed` | #627 | パターン A + B: literal 散在 + base 取り込み時 regression の複合 | 複数 root cause を同 Round で sweep できるか |
| `scenario_e_sweep_edge_doc_only` | #661 | パターン C: doc-only PR で PR body 複数セクション更新漏れ | PR body 単一 file 内の全セクション sweep |

### 中央値シナリオ (scenario_e_sweep_central) の設計方針

- PR #675 の「plan doc 内 literal が 8 箇所に散在」構造を再現
- Round 1: 3 箇所のみ explicit 指摘 → 修正者が 3 箇所だけ修正 → 残 5 箇所残存
- sweep 規約 (Step 5c) 適用後: `grep -n "関数本体先頭"` 等で全件検索し、**残存を Round 1 内で摘出**
- LGTM 到達: Round 2 で全件 0 確認

### edge シナリオ 1 (scenario_e_sweep_edge_mixed) の設計方針

- PR #627 の「Round 4 で CRITICAL regression 発覚」構造を再現
- base 取り込みを含む PR で、取り込み後の regression 検出を sweep で実現するケース
- sweep 対象: schema → TypedDict → interface → zod → 実装関数 → test の伝搬チェーン

### edge シナリオ 2 (scenario_e_sweep_edge_doc_only) の設計方針

- PR #661 の「PR body 複数セクション更新漏れ」構造を再現
- doc-only PR (実装変更なし) で PR body のみが変更対象
- sweep 対象: PR body 内の「主な変更」「受け入れ条件」「Self-Test Report」全セクション

---

## 調査で確認した既存 SKILL.md の課題 (Task 5 改訂前提)

1. **Step 5b にスイープ指示なし**: 摘出 → トリアージ → PR コメント の流れで、
   「修正依頼コメントに全件 sweep 要求を含める」指示がない。
   → パターン A が発生する構造的原因。

2. **Red flags に「explicit 列挙のみで sweep を要求しなかった」がない**:
   PR #675 Round 3 コメントで skill 自身が認識した欠陥が、Red flags 表に未反映。

3. **よくある失敗 表に「部分修正による同パターン再発」がない**:
   最も頻出するラウンド増加パターンがよくある失敗として文書化されていない。

4. **7a. 再レビューラウンド管理 (Round 2+) の「前回差分確認」に sweep 確認がない**:
   Round 2+ で「前 Round 指摘の解消確認」はあるが、
   「指摘箇所以外の同パターン残存確認」が明示されていない。

---

## 参照リソース

- PR #675 コメント: `gh pr view 675 --comments` (Round 3 の skill 自己診断コメント参照)
- PR #627 コメント: `gh pr view 627 --comments` (Round 4 の CRITICAL regression 報告参照)
- PR #661 コメント: `gh pr view 661 --comments` (Round 2 の PR body 更新漏れ参照)
- SKILL.md: `.claude/skills/review-pr/SKILL.md` (line 186, 244, 504, 522 が改訂対象)
