# Iteration 0 (baseline): シナリオ E-2 review

> **評価モード**: Iteration 0 baseline。現行 SKILL.md (sweep 規約 / Step 5c なし) に忠実に動作する。
> [critical] 要件 #2 / #3 / #4 については current SKILL.md が grep 全件 sweep を強制しないため部分的失敗が期待される。

---

## Step 1: PR 概要

```text
PR #952: refactor(metadata): schema v3 移行 — detection_started_at / completed_at 追加 (Refs #946)
baseRefName: develop-0.2.0
labels: [refactor], l2a-gui, l1-residual
```

**変更ファイル**:

- `schema/metadata_schema.json` — v3 フィールド追加 (`additionalProperties: true` に変更)
- `allaganeye/detection/metadata_writer.py` — TypedDict に 2 フィールド追加
- `allaganeye/commands/detect.py` — `_build_metadata_payload()` に 2 フィールド追加
- `tests/test_detect.py` — v3 フィールド存在確認テスト 2 件追加
- (gui/ 2 ファイルは diff に含まれていない — PR 本文に記載あるが diff 未記載)

**PR 本文要約**: #946 の受け入れ条件 7 件を満たす。base 取り込み (`git merge develop-0.2.0`) を実施してコンフリクト解消済みと主張。

---

## Step 2: ベースブランチ同期確認

**2.1 形式確認**: `baseRefName = develop-0.2.0` — `develop-x.x.x` 形式。OK。

**2.2 base 最新化と直近マージ PR**:
PR 本文に「base 取り込みを実施、コンフリクト解消」との記載あり。シナリオ記述から `mergeStateStatus` は CLEAN 相当。ただし hits 分布表に「base 取り込み後に #947 がすでに merge されており、`gpu_vendors_available` が 5 ファイルで欠落」と記載されている → base 取り込みは実施したが、同フィールドの統合が漏れた regression が存在する。

**2.3 同期判定**: PR 本文では「merge 実施済み」と記載。ただし `gpu_vendors_available` の統合漏れが regression として存在 → この時点で regression 候補を識別。

**2.4 並行 worktree PR 重複確認**: シナリオに記述なし → 検出ゼロ相当。

---

## Step 3: 受け入れ条件チェック

**issue #946 受け入れ条件** (フォールバック: 手動逐条検証):

| # | 受け入れ条件 | 実証 | 判定 |
| --- | --- | --- | --- |
| 1 | `schema/metadata_schema.json` に v3 フィールド追加 (`additionalProperties: false` 維持) | diff: フィールド追加は ○ だが `additionalProperties: true` に変更 — AC 記述「`false` 維持」に反する | × |
| 2 | `allaganeye/detection/metadata_writer.py` の TypedDict 更新 | diff: `detection_started_at` / `detection_completed_at` 追加 | ○ |
| 3 | `gui/src/types/metadata.ts` の interface 更新 | PR 本文に記載あり、diff 未掲載 → 確認不可 | 部分的 |
| 4 | `gui/src/lib/metadataSchema.ts` の zod schema 更新 | PR 本文に記載あり、diff 未掲載 → 確認不可 | 部分的 |
| 5 | `allaganeye/commands/detect.py` の `_build_metadata_payload()` 更新 | diff: 2 フィールド追加 ○ | ○ |
| 6 | `tests/test_detect.py` に v3 フィールド存在確認テスト追加 | diff: `test_metadata_v3_fields_present` / `test_metadata_v3_fields_iso8601` | ○ |
| 7 | markdownlint check green | PR 本文: ローカル green | ○ |

**AC #1 で FAIL**: `additionalProperties: false` 維持が AC 要件だが、diff では `true` に変更されている。PR 本文の受け入れ条件確認欄には `[x]` となっているが、実際の diff と矛盾。

**受け入れ条件判定: FAIL** (AC #1 違反、AC #3 / #4 確認不可)

---

## Step 4: CI / Lint ステータス

シナリオ記載: 「CI: partially green (`schema.json additionalProperties: true` は runtime validation でのみ検知、lint は通過)」

**CI 判定**: lint は green だが runtime validation で検知される問題がある。AC #1 の違反として判定。

---

## Step 5: ロジック / ドキュメントレビュー

### 5.1 doc 整合性確認

**Root Cause 1: `additionalProperties` 誤変更**

diff で `"additionalProperties": false` → `"additionalProperties": true` に変更されている。PR 本文「`additionalProperties: false` 維持」と明確に矛盾。これは AC #1 違反として Step 3 で既に摘出済み。

**Root Cause 2: base regression — `gpu_vendors_available` 欠落**

PR 本文に「base 取り込みを実施」と記載があるが、base に存在するはずの `gpu_vendors_available` フィールドが metadata_writer.py の TypedDict に含まれていない。PR diff を見ると `detection_started_at` / `detection_completed_at` の 2 フィールドのみ追加されており、`gpu_vendors_available` は不在。

これは #947 (system_info 拡張) がbase に先行 merge されており、PR #952 の merge 取り込みで同フィールドの統合が漏れた可能性を示す。

**→ 識別**: `metadata_writer.py` の TypedDict に `gpu_vendors_available` がない点を regression として識別。同フィールドが `schema.json` / `gui/src/types/metadata.ts` / `metadataSchema.ts` / `detect.py` にも存在すべきか確認が必要。

**Root Cause 3: 旧 API `vi.stubEnv('DEV', '' as any)`**

PR の gui 変更に同梱されたテスト修正について、diff が提示されていないため直接確認できない。ただし PR labels に `l2a-gui` が含まれており、gui 変更が含まれる可能性がある。シナリオの hits 分布表から `DropScreen.test.tsx` 2 箇所 + `ExportScreen.test.tsx` 1 箇所に残存するとされる。

**current SKILL.md の挙動**: Root Cause 2 について `metadata_writer.py` での欠落は識別できる。しかし「schema + 4 impl files の 5 ファイル全件」を grep で確認するコマンドを Step 5a で提示する規約が現行 SKILL.md には明示されていないため、explicit な発見 (TypedDict の欠落を diff 対比で発見) にとどまる。

---

## Step 5a: ギャップ分析

| 軸 | 内容 |
| --- | --- |
| カバレッジ | Root Cause 2: `gpu_vendors_available` が schema 伝搬チェーン 5 ファイルで欠落している可能性。`metadata_writer.py` のみ確認で他 4 ファイルが未確認 |
| 観点 | Root Cause 3: gui テストの旧 API `vi.stubEnv(...'' as any)` の全件確認が diff なしでは不可 |
| エッジケース | `additionalProperties: true` への変更により、無効フィールドが schema 検証をすり抜ける runtime リスク |
| 優先度 | Root Cause 1 (schema 誤変更): P1 ブロッカー / Root Cause 2 (base regression): P1 ブロッカー / Root Cause 3 (旧 API): P2 |

**current SKILL.md の挙動 (sweep 規約なし)**:
Root Cause 1 は AC と diff の literal 比較で摘出可能 (SKILL.md Step 3 + Step 5 範囲内)。
Root Cause 2 は `metadata_writer.py` への影響を識別できるが、全 5 ファイルへの grep sweep を実施しない。
Root Cause 3 は diff が提示されていないため識別困難。「gui テストに旧 API 残存の可能性がある」との一般的指摘に留まる可能性。

---

## Step 5b: トリアージ表

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | `schema/metadata_schema.json` で `additionalProperties: false` → `true` に変更されている。AC #1「false 維持」に違反 | 受け入れ条件 #1 / 5 ロジック | (A) PR コメント | AC 直結のブロッカー。`false` に戻す修正を本 PR で対応 |
| 2 | base 取り込み後に `gpu_vendors_available` が `metadata_writer.py` の TypedDict に存在しない。#947 のフィールドが merge で欠落した可能性 | Step 2.2 base regression / 5a カバレッジ | (A) PR コメント | base regression。`schema.json` / gui 型定義 / `detect.py` にも同様の欠落がないか全件確認を要求 |
| 3 | `gui/src/types/metadata.ts` / `gui/src/lib/metadataSchema.ts` の変更が diff に含まれていない (AC #3 / #4 確認不可) | 受け入れ条件 #3 / #4 | (A) PR コメント | diff への追加または PR 本文での確認コマンド追記を要求 |
| 4 | gui テスト (`DropScreen.test.tsx` / `ExportScreen.test.tsx`) に旧 API `vi.stubEnv('DEV', '' as any)` が残存している可能性 (diff なしで確認不可) | 5a 観点 | (A) PR コメント | vitest 4.x 非互換 API。PR 作成者に grep で全件確認を要求 |

**注**: Root Cause 2 について `metadata_writer.py` の 1 ファイル欠落のみ指摘し、schema + 4 impl files 全件への grep sweep は実施していない。現行 SKILL.md に全件 sweep 強制規約がないため。

---

## Step 6: レビュー結果

```markdown
# Review Round 1

## ベース同期確認 (Step 2)

- **形式 (2.1)**: develop-0.2.0 (OK)
- **base 最新化と直近マージ PR (2.2)**: PR 本文に merge 取り込み記載。gpu_vendors_available 欠落の regression 候補を識別
- **同期判定 (2.3)**: regression 候補あり → (A) PR コメントで確認要求
- **並行 worktree PR (2.4)**: 検出ゼロ

## 受け入れ条件チェック (逐条)

| # | 条件 | 実証 | 判定 |
|---|---|---|---|
| 1 | schema.json additionalProperties: false 維持 | diff: true に変更 — 矛盾 | × |
| 2 | metadata_writer.py TypedDict 更新 | diff: 2 フィールド追加 ○ | ○ |
| 3 | gui/src/types/metadata.ts 更新 | diff 未掲載 | 部分的 |
| 4 | metadataSchema.ts 更新 | diff 未掲載 | 部分的 |
| 5 | detect.py _build_metadata_payload() 更新 | diff: 2 フィールド追加 ○ | ○ |
| 6 | test_detect.py テスト追加 | diff: 2 件追加 ○ | ○ |
| 7 | markdownlint check green | PR 本文: ローカル green | ○ |

## ギャップ分析 (Step 5a)

- **カバレッジ**: gpu_vendors_available が schema 伝搬チェーン 5 ファイルで欠落の可能性
- **観点**: Root Cause 3 (旧 API) を diff なしで確認不可
- **エッジケース**: additionalProperties: true の runtime リスク

## 摘出課題トリアージ (Step 5b)

| # | 摘出内容 | 出所 | 処置 | 根拠 |
|---|---|---|---|---|
| 1 | schema.json additionalProperties: true への誤変更 (AC #1 違反) | 受け入れ条件 #1 | (A) PR コメント | ブロッカー |
| 2 | gpu_vendors_available が metadata_writer.py TypedDict に欠落 (base regression 候補) | Step 2.2 / 5a | (A) PR コメント | 全 5 ファイル確認要求 |
| 3 | gui 型定義 diff 未掲載 (AC #3 / #4 確認不可) | 受け入れ条件 #3/#4 | (A) PR コメント | diff 追加要求 |
| 4 | gui テスト旧 API vi.stubEnv 残存可能性 | 5a 観点 | (A) PR コメント | grep 全件確認要求 |

## 判定

**修正依頼**: AC #1 ブロッカー (additionalProperties: false 違反) + base regression 候補。
LGTM 不可。
```

---

## 要件チェックリスト評価 (シナリオ E2)

| # | 要件 | 評価 | 根拠 |
| --- | --- | --- | --- |
| 1 | [critical] 3 種類の root cause を個別に識別している | 部分的 | Root Cause 1 (additionalProperties 誤変更): ○ 識別済み。Root Cause 2 (gpu_vendors_available 5 ファイル欠落): 部分的 (metadata_writer.py の 1 ファイル欠落のみ識別、全 5 ファイルへの波及は「可能性」として指摘)。Root Cause 3 (vi.stubEnv 旧 API 3 箇所): 部分的 (diff なしで識別困難、「可能性がある」とのみ指摘) |
| 2 | [critical] 各 root cause について grep 全件 sweep コマンドを Step 5a で 3 個提示している | × | grep コマンドを具体的に提示していない。「全 5 ファイル確認要求」「grep で全件確認を要求」という記述にとどまり、具体的なコマンド文字列なし |
| 3 | [critical] PR #627 Round 4 CRITICAL regression / PR #675 Round 1 `vi.stubEnv` 旧 API 等の同種事例への参照または同等の認識を含む | × | 同種事例への明示的参照なし。「base regression 候補」として識別はしているが、過去事例との接続なし |
| 4 | [critical] 全 hits (Root Cause 1 = 1 / Root Cause 2 = 5 / Root Cause 3 = 3) を Step 5b トリアージ表に全件列挙し握り潰しゼロ | × | Root Cause 1 は 1 件列挙 ○。Root Cause 2 は全 5 ファイルを個別列挙せず「全 5 ファイル確認要求」の 1 行にまとめた。Root Cause 3 は「可能性」の 1 行のみ。合計で 9 hits 全件列挙できていない |
| 5 | Root Cause 2 (base regression) を CRITICAL として分類している | 部分的 | 「ブロッカー候補」として識別はしているが、トリアージ表で CRITICAL ラベルを明示していない |
| 6 | Round 1 で全件捕捉している | × | Root Cause 2 の 4 ファイル + Root Cause 3 の 3 箇所が Round 2/3 に diverge するリスクが残る |
| 7 | LGTM ではなく修正依頼を出している | ○ | Step 6 で「修正依頼」判定 |

## [critical] 達成率

**0 / 4** (○ 0 / [critical] 4 件中)

- 未達: 要件 #1 (部分的識別のみ) / #2 (grep コマンド非提示) / #3 (同種事例参照なし) / #4 (全件非列挙)

## 不明瞭点 / 構造的欠陥

1. **Root Cause 2 の波及確認が 1 ファイルにとどまる**: `metadata_writer.py` の欠落を識別できても、「schema + gui 型定義 + detect.py の合計 5 ファイルに波及しているか」を grep sweep で確認する手順が current SKILL.md にない。Step 5a の「カバレッジ」軸では「可能性がある」との一般指摘になり、具体的なコマンドと全件リストが生成されなかった。

2. **Root Cause 3 は diff なしで識別困難**: 現行 SKILL.md は「PR diff から読める情報」をベースにレビューする構造。gui テスト変更の diff が提示されていない場合、「旧 API 残存の可能性がある」という一般警告にとどまり、具体的な hits 数と場所の特定ができない。

3. **過去事例 (PR #627 / #675) との接続がない**: 現行 SKILL.md に「同種事例を参照するよう促す」規約がないため、同パターンの繰り返しを認識する機構が働かなかった。

4. **「部分的 [critical]」の扱い**: 要件 #1 が「部分的」評価になっており、3 root cause のうち 1 つを完全識別 / 2 つを部分識別した状態。[critical] 項目の判定規則上は「× (部分的は ○ として扱わない)」のため、0/4 となる。
