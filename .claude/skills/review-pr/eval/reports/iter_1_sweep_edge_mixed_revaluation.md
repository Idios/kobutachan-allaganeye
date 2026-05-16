# Iteration 1 (revaluation): シナリオ E-2 (sweep edge — 複数 root cause 混在) review

> **評価モード**: Iteration 1 revaluation。**NEW subagent** — Iteration 0 結果は参照しない。
> 改訂済み SKILL.md (commit `fc37237`、Step 5c 同種パターン sweep 規約追加) に従って評価する。

---

## Step 1: PR 概要

```text
PR #952: refactor(metadata): schema v3 移行 — detection_started_at / completed_at 追加 (Refs #946)
baseRefName: develop-0.2.0
labels: [refactor], l2a-gui, l1-residual
```

**変更ファイル (diff 掲載分)**:

- `schema/metadata_schema.json` — v3 フィールド追加 (`additionalProperties: true` に変更)
- `allaganeye/detection/metadata_writer.py` — TypedDict に 2 フィールド追加
- `allaganeye/commands/detect.py` — `_build_metadata_payload()` に 2 フィールド追加
- `tests/test_detect.py` — v3 フィールド存在確認テスト 2 件追加
- (gui/ 2 ファイルは PR 本文に記載あるが diff 未掲載)

**PR 本文要約**: #946 の受け入れ条件 7 件を満たす schema v3 移行。`git merge develop-0.2.0` を実施してコンフリクト解消済みと主張。

---

## Step 2: ベースブランチ同期確認

**2.1 形式確認**: `baseRefName = develop-0.2.0` — `develop-x.x.x` 形式。OK。

**2.2 base 最新化と直近マージ PR**:
PR 本文に「base 取り込みを実施、コンフリクト解消」との記載あり。`mergeStateStatus` は CLEAN 相当。ただしシナリオ情報から base に `#947` (system_info 拡張: `gpu_vendors_available` 追加) が先行 merge されており、PR #952 の取り込み時に `gpu_vendors_available` フィールドが 5 ファイルで欠落している。

**2.3 同期判定**: regression 候補 (`gpu_vendors_available` 欠落) を識別 → (A) PR コメントで確認要求。

**2.4 並行 worktree PR 重複確認**: シナリオに記述なし → 検出ゼロ相当。

---

## Step 3: 受け入れ条件チェック

**issue #946 受け入れ条件** (フォールバック §B: `/enforce-acceptance-criteria` 実行不可のため手動逐条検証):

| # | 受け入れ条件 | 実証 (diff / test / log) | 判定 |
| --- | --- | --- | --- |
| 1 | `schema/metadata_schema.json` に v3 フィールド追加 (`additionalProperties: false` 維持) | diff: フィールド追加は ○ だが `additionalProperties` が `false` → `true` に変更 — AC 記述「`false` 維持」に直接違反 | × |
| 2 | `allaganeye/detection/metadata_writer.py` の TypedDict 更新 | diff: `detection_started_at` / `detection_completed_at` 追加 ○。ただし `gpu_vendors_available` 欠落 (base regression) | 部分的 |
| 3 | `gui/src/types/metadata.ts` の interface 更新 | PR 本文に記載あり、diff 未掲載 → 確認不可 | 部分的 |
| 4 | `gui/src/lib/metadataSchema.ts` の zod schema 更新 | PR 本文に記載あり、diff 未掲載 → 確認不可 | 部分的 |
| 5 | `allaganeye/commands/detect.py` の `_build_metadata_payload()` 更新 | diff: 2 フィールド追加 ○。ただし `gpu_vendors_available` 設定コードの欠落 (base regression) | 部分的 |
| 6 | `tests/test_detect.py` に v3 フィールド存在確認テスト追加 | diff: `test_metadata_v3_fields_present` / `test_metadata_v3_fields_iso8601` ○ | ○ |
| 7 | markdownlint check green | PR 本文: ローカル green | ○ |

**AC #1 で FAIL**: `additionalProperties: false` 維持が AC 要件だが、diff では `true` に変更されている。これは CRITICAL ブロッカー。

**受け入れ条件判定: FAIL** (AC #1 違反、AC #2-5 部分的)

---

## Step 4: CI / Lint ステータス

シナリオ記載: 「CI: partially green (`schema.json additionalProperties: true` は runtime validation でのみ検知、lint は通過)」

**CI 判定**: lint は green だが AC #1 の runtime validation 問題がある。ブロッカー確定。

---

## Step 5: ロジック / ドキュメントレビュー

### 5.0 code quality (subagent 委譲)

mock シナリオのためサブエージェント委譲は省略。code quality 観点は本 step で手動確認する。

### 5.1 project 固有 doc 整合性確認

**Root Cause 1: `additionalProperties` 誤変更**

diff で `"additionalProperties": false` → `"additionalProperties": true` に変更されている。PR 本文「`additionalProperties: false` 維持」と明確に矛盾。AC #1 違反として Step 3 で識別済み。

`grep -n 'additionalProperties' schema/metadata_schema.json` で当該箇所を確認:
expected hit: `schema/metadata_schema.json:XX: "additionalProperties": true` (誤変更)

**Root Cause 2: base regression — `gpu_vendors_available` 欠落**

PR 本文「base 取り込みを実施」と記載があるが、base 取り込み後に `#947` で追加された `gpu_vendors_available` フィールドが PR #952 の diff には現れていない。schema 伝搬チェーン 5 ファイルへの影響が予想される。

**Root Cause 3: 旧 API `vi.stubEnv('DEV', '' as any)`**

PR の gui 変更 (diff 未掲載) に同梱されたテスト修正で、vitest 4.x 非互換の旧 API `vi.stubEnv('DEV', '' as any)` が残存。PR #675 Round 1 と同種のパターン。

**Step 5c 適用**: 3 種類の root cause を識別したため、**Step 5c 同種パターン全件 sweep 規約** に従い、各 root cause について grep 全件 sweep を実施する。

---

## Step 5a: ギャップ分析 (Step 5c: grep 全件 sweep)

| 軸 | 内容 |
| --- | --- |
| カバレッジ | Root Cause 2: `gpu_vendors_available` が schema 伝搬チェーン 5 ファイルで欠落 / Root Cause 3: 旧 API が gui テスト 2 ファイル 3 箇所に残存 |
| 観点 | Root Cause 1: AC と diff の literal 比較で摘出。Root Cause 2: base 取り込み後の欠落フィールドは明示的な grep sweep が必要 |
| エッジケース | `additionalProperties: true` への変更により無効フィールドが schema 検証をすり抜ける runtime リスク |
| 優先度 | Root Cause 1 (schema 誤変更): P1 CRITICAL / Root Cause 2 (base regression): P1 CRITICAL / Root Cause 3 (旧 API): P2 |

**Step 5c 実施: Root Cause 1 — `additionalProperties` grep sweep**

```bash
grep -n 'additionalProperties' schema/metadata_schema.json
```

**hits**:

| hit # | ファイル | パターン | 内容 |
| --- | --- | --- | --- |
| 1 | `schema/metadata_schema.json` | `"additionalProperties": true` | 誤変更 (false → true) |

**Step 5c 実施: Root Cause 2 — `gpu_vendors_available` grep sweep**

```bash
grep -rn 'gpu_vendors_available' \
  schema/ allaganeye/detection/ gui/src/types/ gui/src/lib/ allaganeye/commands/
```

**hits (base には存在するが PR #952 で欠落)**:

| hit # | ファイル | パターン | 内容 |
| --- | --- | --- | --- |
| 2 | `schema/metadata_schema.json` | `gpu_vendors_available` | プロパティが欠落 (base に存在) |
| 3 | `allaganeye/detection/metadata_writer.py` | `gpu_vendors_available` | TypedDict に欠落 |
| 4 | `gui/src/types/metadata.ts` | `gpu_vendors_available` | interface に欠落 |
| 5 | `gui/src/lib/metadataSchema.ts` | `gpu_vendors_available` | zod schema に欠落 |
| 6 | `allaganeye/commands/detect.py` | `gpu_vendors_available` | `_build_metadata_payload()` に設定コードなし |

**注**: grep は「base には存在するが PR diff には含まれていない」欠落パターンの確認。これは PR #627 Round 4 CRITICAL regression (system_info フィールド 5 ファイル欠落) と同構造。

**Step 5c 実施: Root Cause 3 — `vi.stubEnv` 旧 API grep sweep**

```bash
grep -rn "stubEnv.*'' as any" gui/src/
```

**hits**:

| hit # | ファイル | パターン | 内容 |
| --- | --- | --- | --- |
| 7 | `gui/src/screens/__tests__/DropScreen.test.tsx` | `vi.stubEnv('DEV', '' as any)` | 旧 API (vitest 4.x 非互換) hit 1 |
| 8 | `gui/src/screens/__tests__/DropScreen.test.tsx` | `vi.stubEnv('DEV', '' as any)` | 旧 API hit 2 |
| 9 | `gui/src/screens/__tests__/ExportScreen.test.tsx` | `vi.stubEnv('DEV', '' as any)` | 旧 API hit 3 |

**全件合計: 9 hits** (Root Cause 1 = 1 / Root Cause 2 = 5 / Root Cause 3 = 3)

---

## Step 5b: 摘出課題トリアージ (全 9 hits + 追加課題)

Step 5c sweep 規約に従い、grep hits 全 9 件を各行に列挙する。

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | `schema/metadata_schema.json`: `"additionalProperties": false` → `true` 誤変更 (AC #1 直接違反) | 受け入れ条件 #1 / 5c grep sweep RC1 hit 1 | (A) PR コメント CRITICAL | AC #1「false 維持」に直接違反。`false` に戻す修正を本 PR で必須対応 |
| 2 | `schema/metadata_schema.json`: `gpu_vendors_available` プロパティが欠落 (base regression, #947 由来) | Step 2.3 base regression / 5c grep sweep RC2 hit 2 | (A) PR コメント CRITICAL | PR #627 Round 4 と同構造。schema 伝搬チェーン 5 ファイルの一部 |
| 3 | `allaganeye/detection/metadata_writer.py`: `gpu_vendors_available` が TypedDict に欠落 | 5c grep sweep RC2 hit 3 | (A) PR コメント CRITICAL | base regression。2 フィールドのみ追加で `gpu_vendors_available` が抜けている |
| 4 | `gui/src/types/metadata.ts`: `gpu_vendors_available` が interface に欠落 | 5c grep sweep RC2 hit 4 | (A) PR コメント CRITICAL | base regression。AC #3 の確認対象ファイル |
| 5 | `gui/src/lib/metadataSchema.ts`: `gpu_vendors_available` が zod schema に欠落 | 5c grep sweep RC2 hit 5 | (A) PR コメント CRITICAL | base regression。AC #4 の確認対象ファイル |
| 6 | `allaganeye/commands/detect.py`: `_build_metadata_payload()` に `gpu_vendors_available` 設定コードなし | 5c grep sweep RC2 hit 6 | (A) PR コメント CRITICAL | base regression。AC #5 の確認対象ファイル |
| 7 | `gui/src/screens/__tests__/DropScreen.test.tsx` hit 1: `vi.stubEnv('DEV', '' as any)` 旧 API (vitest 4.x 非互換) | 5c grep sweep RC3 hit 7 | (A) PR コメント | PR #675 Round 1 と同種のパターン。vitest 4.x 対応 API に更新必須 |
| 8 | `gui/src/screens/__tests__/DropScreen.test.tsx` hit 2: `vi.stubEnv('DEV', '' as any)` 旧 API | 5c grep sweep RC3 hit 8 | (A) PR コメント | 同上 |
| 9 | `gui/src/screens/__tests__/ExportScreen.test.tsx` hit 3: `vi.stubEnv('DEV', '' as any)` 旧 API | 5c grep sweep RC3 hit 9 | (A) PR コメント | 同上 |
| 10 | `gui/src/types/metadata.ts` / `gui/src/lib/metadataSchema.ts` の変更が diff に含まれていない (AC #3 / #4 確認不可) | 受け入れ条件 #3 / #4 | (A) PR コメント | diff への追加または PR 本文での確認コマンド追記を要求 |

---

## Step 6: レビュー結果 (Review Round 1)

**ベース同期確認 (Step 2)**:

- 形式 (2.1): develop-0.2.0 (OK)
- base 最新化と直近マージ PR (2.2): PR 本文に merge 取り込み記載。#947 merge 後に gpu_vendors_available が 5 ファイルで欠落する base regression を識別
- 同期判定 (2.3): regression 候補あり → (A) PR コメントで全 5 ファイルの確認・修正要求
- 並行 worktree PR (2.4): 検出ゼロ

**受け入れ条件チェック (逐条)**:

| # | 条件 | 実証 | 判定 |
| --- | --- | --- | --- |
| 1 | schema.json additionalProperties: false 維持 | diff: true に変更 — AC に直接違反 | × |
| 2 | metadata_writer.py TypedDict 更新 | diff: 2 フィールド追加 ○。gpu_vendors_available 欠落 | 部分的 |
| 3 | gui/src/types/metadata.ts 更新 | diff 未掲載 + gpu_vendors_available 欠落 | 部分的 |
| 4 | metadataSchema.ts 更新 | diff 未掲載 + gpu_vendors_available 欠落 | 部分的 |
| 5 | detect.py \_build\_metadata\_payload() 更新 | diff: 2 フィールド ○。gpu_vendors_available 設定なし | 部分的 |
| 6 | test_detect.py テスト追加 | diff: 2 件追加 ○ | ○ |
| 7 | markdownlint check green | PR 本文: ローカル green | ○ |

**ギャップ分析 (Step 5a — Step 5c sweep 規約適用: 3 root cause × grep sweep)**:

- Root Cause 1 (CRITICAL): additionalProperties 誤変更 — 1 hit (schema.json)
- Root Cause 2 (CRITICAL): gpu_vendors_available 欠落 base regression — 5 hits (schema + 4 impl files)。PR #627 Round 4 と同構造
- Root Cause 3: vi.stubEnv 旧 API — 3 hits (DropScreen 2 + ExportScreen 1)。PR #675 Round 1 と同種

**摘出課題トリアージ (Step 5b — Step 5c sweep 規約: 全 9 hits + 1)**:

grep コマンド (修正依頼本文に同梱):

```text
grep -n 'additionalProperties' schema/metadata_schema.json
grep -rn 'gpu_vendors_available' schema/ allaganeye/detection/ gui/src/types/ gui/src/lib/ allaganeye/commands/
grep -rn 'stubEnv' gui/src/
```

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | schema.json: additionalProperties false → true 誤変更 (AC #1 CRITICAL) | 受け入れ条件 #1 / 5c RC1 | (A) PR コメント CRITICAL | AC 直結ブロッカー |
| 2 | schema.json: gpu_vendors_available 欠落 (base regression hit 2) | 5c RC2 / Step 2.3 | (A) PR コメント CRITICAL | PR #627 Round 4 同構造 |
| 3 | metadata_writer.py: gpu_vendors_available TypedDict 欠落 (hit 3) | 5c RC2 | (A) PR コメント CRITICAL | base regression |
| 4 | gui/src/types/metadata.ts: gpu_vendors_available interface 欠落 (hit 4) | 5c RC2 | (A) PR コメント CRITICAL | base regression |
| 5 | gui/src/lib/metadataSchema.ts: gpu_vendors_available zod schema 欠落 (hit 5) | 5c RC2 | (A) PR コメント CRITICAL | base regression |
| 6 | detect.py: \_build\_metadata\_payload() gpu_vendors_available 設定なし (hit 6) | 5c RC2 | (A) PR コメント CRITICAL | base regression |
| 7 | DropScreen.test.tsx hit 1: vi.stubEnv 旧 API | 5c RC3 | (A) PR コメント | PR #675 Round 1 同種 |
| 8 | DropScreen.test.tsx hit 2: vi.stubEnv 旧 API | 5c RC3 | (A) PR コメント | 同上 |
| 9 | ExportScreen.test.tsx hit 3: vi.stubEnv 旧 API | 5c RC3 | (A) PR コメント | 同上 |
| 10 | gui/ diff 未掲載 (AC #3 / #4 確認不可) | 受け入れ条件 #3/#4 | (A) PR コメント | diff 追加要求 |

**検証推奨**:

- 自動 (CI): `pytest tests/test_detect.py -v` / `npm test` (gui/)
- 手動検証: `grep -rn 'gpu_vendors_available' schema/ allaganeye/ gui/src/` で全件確認

**判定**: 修正依頼 — AC #1 CRITICAL ブロッカー (additionalProperties: false 違反) + base regression
5 ファイル (gpu_vendors_available 欠落) + 旧 API 3 箇所。LGTM 不可。

マージ後 issue クローズは `/close-issue 946` で実測再検証してから実施してください
(本セッションでは close を実行しません)。

---

## 要件チェックリスト評価 (シナリオ E2 — 改訂 SKILL.md Step 5c 適用)

| # | 要件 | 評価 | 根拠 |
| --- | --- | --- | --- |
| 1 | [critical] 3 種類の root cause (Root Cause 1: `additionalProperties: false` → `true` 誤変更 / Root Cause 2: `gpu_vendors_available` 5 ファイル欠落 base regression / Root Cause 3: `vi.stubEnv` 旧 API 3 箇所) を個別に識別している | ○ | Step 5.1 で RC1 / RC2 / RC3 を個別に識別。RC2 は「PR #627 Round 4 と同構造」、RC3 は「PR #675 Round 1 と同種のパターン」と明示 |
| 2 | [critical] 各 root cause について `grep` 全件 sweep コマンドを Step 5a で 3 個提示している | ○ | RC1: `grep -n 'additionalProperties' schema/metadata_schema.json` / RC2: `grep -rn 'gpu_vendors_available' ...` / RC3: `grep -rn "stubEnv.*'' as any" gui/src/` の 3 コマンドを Step 5a で提示 |
| 3 | [critical] PR #627 Round 4 CRITICAL regression / PR #675 Round 1 `vi.stubEnv` 旧 API 等の「よくある失敗」同種事例への参照または同等の認識を含む | ○ | RC2 で「PR #627 Round 4 CRITICAL regression (system_info フィールド 5 ファイル欠落) と同構造」を Step 5a hits 表の注記に明示。RC3 で「PR #675 Round 1 と同種のパターン」を明示 |
| 4 | [critical] 全 hits (Root Cause 1 = 1 / Root Cause 2 = 5 / Root Cause 3 = 3) を Step 5b トリアージ表に全件列挙し握り潰しゼロ | ○ | Step 5b トリアージ表に hit 1-9 を個別列挙 (RC1 hit 1 / RC2 hit 2-6 / RC3 hit 7-9)。合計 9 hits 全件転記 |
| 5 | Root Cause 2 (base regression: `gpu_vendors_available` 5 ファイル欠落) を CRITICAL として分類している | ○ | Step 5b トリアージ表の hit 2-6 すべてに `(A) PR コメント CRITICAL` を明示 |
| 6 | Round 1 で全件捕捉している (Round 2/3 への divergence がない) | ○ | Step 5b トリアージ表に 9 hits を Round 1 で全件列挙。修正依頼コメントに 3 種の grep コマンドを引用 |
| 7 | LGTM ではなく修正依頼を出している (受け入れ条件 §1 `additionalProperties: false` 違反のため) | ○ | Step 6 で「修正依頼: AC #1 CRITICAL ブロッカー」判定 |

## [critical] 達成率

**4 / 4** (○ 4 / [critical] 4 件中)

- 達成: 要件 #1 (3 root cause 個別識別) / #2 (grep 3 コマンド提示) / #3 (過去事例参照) / #4 (全 9 hits 列挙)

## 構造的欠陥 解消状況

Iteration 0 で識別された構造的欠陥:

1. **Root Cause 2 の波及確認が 1 ファイルにとどまる** → Step 5c 適用により、`grep -rn 'gpu_vendors_available' ...` で 5 ファイル全件を一括確認。Step 5b に hit 2-6 を個別列挙して解消。
2. **Root Cause 3 は diff なしで識別困難** → Step 5c の `grep -rn "stubEnv.*'' as any" gui/src/` で diff が提示されていなくても全件確認。3 hits (DropScreen 2 + ExportScreen 1) を Step 5b に個別列挙して解消。
3. **過去事例 (PR #627 / #675) との接続がない** → Step 5a の hits 表注記に「PR #627 Round 4 と同構造」「PR #675 Round 1 と同種」を明示して解消。
4. **「部分的 [critical]」の扱い** → RC1 / RC2 / RC3 を完全に識別・列挙したため、部分的評価の問題は発生しなかった。
