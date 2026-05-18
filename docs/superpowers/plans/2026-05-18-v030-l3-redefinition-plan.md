# v0.3.0 L3 Redefinition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the v0.3.0 L3 redefinition organizational work — update layer documentation across 7 files, reorganize 28 GitHub issues (8 v0.3.0 inclusion + 20 cascading rename), and provision baseline preparation infrastructure (compare script + ground truth metadata + 2 child issues) — to enable the v0.3.0 = 新 L3 implementation phase to start.

**Architecture:** This plan implements the organizational reforms defined in [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](../specs/2026-05-18-v030-l3-redefinition-design.md) Sections 4-9. The plan does **NOT** implement Pillar 3 (perf) or Pillar 1+2 (input adapt) technical work — those are explicitly deferred to child-issue-level brainstorms (spec §10 Out of scope). Tasks are grouped into 4 waves: (A) documentation updates, (B) issue reorganization via `gh` CLI, (C) baseline infrastructure (script + JSON), (D) Phase 1 prep child issue creation. Waves A/C/D produce code or doc deltas committed to git; Wave B produces GitHub state changes only (no commits).

**Tech Stack:**
- Markdown (docs editing — primary deliverable)
- `gh` CLI 2.x (issue rename + label management; user is authenticated)
- Python 3.11+ (compare-baseline.py with pytest TDD)
- JSON (ground truth metadata, baseline output format)

---

## File Structure

### Files modified

| Path | Wave | Responsibility |
|---|---|---|
| `CLAUDE.md` | A1 | §段階的アーキテクチャ layer table (Primary spec table) |
| `docs/design-overview.md` | A2 | §段階的アーキテクチャ ASCII art + L3 (new) 节 + 旧 L3 移動 |
| `docs/release-process.md` | A3 | Layer-to-version mapping table + L6 拡張 section + バージョン別検証テーマ |
| `README.md` | A4 | Remove §ロードマップ table (lines 43-53) |
| `docs/cli-spec.md` | A5 | Update incidental L3 reference (L205) |
| `docs/reference-videos.md` | A6 | Update L3 OCR references (L11, L16) |
| `docs/issue-policy.md` | A7 | Add §2/§8 v0.3.0 運用ルール (`deferred` 外し = active scope, title prefix `[type] L3:`) |
| `docs/testing-guide.md` | A8 | Add §「v0.3.0 L3 work 用 regression baseline」 |

### Files created

| Path | Wave | Responsibility |
|---|---|---|
| `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` | C1 | VTuber 5 試合 ground truth metadata (spec §8.6) |
| `scripts/compare-baseline.py` | C2 | metadata.json bit-exact 比較スクリプト (excludes `detected_at`) |
| `tests/scripts/test_compare_baseline.py` | C2 | pytest TDD tests for compare-baseline |

### Files NOT touched (explicit decisions)

| Path | Reason |
|---|---|
| `docs/l2-workflow.md` | "L3" mentions at L538-540 refer to memory tier (`docs/knowledge/*.md`), NOT architecture layer. Skip. |
| `docs/ui-interaction-spec.md` | No actual L3 (architecture layer) reference. `L997` matched a TSX line number (`L399`), false positive. Skip. |
| `docs/superpowers/specs/*.md` (28 existing) | Time-series context preservation (spec §4.1, §9.4). Body unchanged. |
| `docs/superpowers/plans/*.md` (existing) | Same as above. |

---

## PR Organization (L2 workflow integration)

| PR | Scope | Wave(s) | Title (draft) | base |
|---|---|---|---|---|
| PR 1 | v0.3.0 L3 redefinition doc realignment | Wave A | `docs(v0.3.0): L3 redefinition layer table + docs realignment` | `develop-0.3.0` |
| PR 2 | Baseline preparation infrastructure | Wave C | `feat(tests): v0.3.0 baseline regression infrastructure (compare-baseline + ground truth)` | `develop-0.3.0` |

Wave B (GitHub issue operations) and Wave D (child issue creation) are **GitHub state only** — no PR. They are executed via `gh` CLI after PR 1 merges (so renamed titles reference the new doc state correctly).

**Iron Law 6 Pre-flight** is required for both PRs (project rule from `.claude/hooks/session-start.sh`). Step 0 hard gate + Step 1 base sync + Step 2 incoming commits + Step 3 file intersection + Step 4 parallel PR re-check + Step 5 `/codex:adversarial-review` (focus: Iron Law 3 scope creep, doc consistency).

**`/codex:adversarial-review` focus 文字列 (PR 1):**

> Verify no scope creep beyond v0.3.0 L3 redefinition doc realignment per spec 2026-05-18-v030-l3-redefinition-design.md §9. Check: (i) Iron Law 3 — only L3-redefinition-related doc changes, no incidental refactors. (ii) layer table consistency across CLAUDE.md / design-overview.md / release-process.md (same 7-layer scheme). (iii) §4.1 文脈保存ルール — no `[type] L4 (former L3):` chain edits. (iv) #753 / past L3 PRs root cause not regressing.

**`/codex:adversarial-review` focus 文字列 (PR 2):**

> Verify TDD discipline in compare-baseline.py (test before implementation), no scope creep beyond metadata bit-exact comparison per spec §8.2, JSON schema matches §8.6 ground truth example, normalize logic correctly drops `detected_at`.

---

## Wave A: Documentation Updates

### Task A1: Update CLAUDE.md §段階的アーキテクチャ

**Files:**
- Modify: `CLAUDE.md` (§段階的アーキテクチャ table block)

- [ ] **Step 1: Read existing layer table block in CLAUDE.md**

Use Read tool on `CLAUDE.md` to confirm current layer table. Expected: §段階的アーキテクチャ with "コアレイヤー（L1〜L5）" subtable and "拡張レイヤー（L6、暫定）" subtable.

- [ ] **Step 2: Replace layer table with new 7-layer scheme**

Use Edit tool. Replace the entire §段階的アーキテクチャ block with:

```markdown
### 段階的アーキテクチャ

**コアレイヤー（L1〜L6）**

| レイヤー | 処理 | 技術 | 状態 |
| --- | --- | --- | --- |
| L1: 試合分割 | 暗転検知で試合単位に分割 | FFmpeg（検知+分割） | **リリース済み** (v0.1.0-preview 2026-04-17, v0.1.1 2026-04-20) |
| L2: 配布・統合 | GUI + ゼロ環境構築配布 | Tauri 2.x + React 19 + TS | **開発中** |
| L3 (new): 配信形式対応 + 性能改善 | VTuber 動画対応 / ミニマップ切抜き / export 並列・ZIP size・detect 高速化・GUI responsiveness | OpenCV / template matching / NVENC・QSV・AMF / Tauri | **開発中** (v0.3.0 target) |
| L4 (former L3): メタデータ化 | キルログ・音声・チャットをタイムスタンプ化 | Tesseract / Whisper | 未着手 |
| L5 (former L4): 価値評価 | 抽出データを ML が判定 | ローカル ML（scikit-learn 等） | 未着手 |
| L6 (former L5): 自動編集 | 判定に基づき動画切り出し・投稿提案 | MoviePy / FFmpeg | 未着手 |

**拡張レイヤー（L7、暫定）**

| レイヤー | 処理 | 状態 |
| --- | --- | --- |
| L7 (former L6): プライバシー・精密分割 | プレイヤー名ぼかし、再エンコード分割 | 計画中 |
```

(L1/L2 rows are preserved verbatim from current CLAUDE.md to avoid Iron Law 3 scope creep — only L3-L7 rows are introduced/renamed/shifted. L2 status update from `**開発中**` to "リリース済み" is out of scope; track separately if needed.)

- [ ] **Step 3: Verify diff**

Run: `git diff CLAUDE.md`
Expected: replacement of layer table block only. No other lines changed.

- [ ] **Step 4: Commit**

```powershell
git add CLAUDE.md
git commit -m @'
docs(v0.3.0): update CLAUDE.md layer table for L3 redefinition

旧 L3 (OCR/Whisper) を L4 (former L3) に繰り下げ、新 L3 = VTuber+minimap+perf
を v0.3.0 target として layer table に反映。下流も 1 段スライド (L4→L5, L5→L6,
L6→L7)。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A2: Update docs/design-overview.md ASCII art + L3 (new) 节

**Files:**
- Modify: `docs/design-overview.md` (§段階的アーキテクチャ ASCII block, lines ~11-41; plus 旧 L3 references throughout if any)

- [ ] **Step 1: Read existing ASCII layer block**

Read `docs/design-overview.md` lines 1-50. Confirm §段階的アーキテクチャ ASCII art currently shows L1-L6 with L3=メタデータ化, L4=価値評価, L5=自動編集, L6=プライバシー.

- [ ] **Step 2: Replace ASCII art with new 7-layer scheme**

Use Edit tool. Replace ASCII block (between the opening ` ```text ` and closing ` ``` `) with:

```text
┌─────────────────────────────────────────────────┐
│  L1: 試合分割                                     │
│  入力: OBS録画 (MP4/MKV)                          │
│  処理: ffmpeg 暗転検知 → FFmpeg 無劣化分割          │
│  出力: 試合ごとの MP4 + metadata.json              │
├─────────────────────────────────────────────────┤
│  L2: 配布・統合（開発中）                            │
│  GUI サポート + ゼロ環境構築配布                     │
├─────────────────────────────────────────────────┤
│  L3 (new): 配信形式対応 + 性能改善（v0.3.0 target）  │
│  入力: L1/L2 で扱う OBS 録画 + VTuber 配信動画       │
│  処理: VTuber game capture 検出 / minimap 切抜き    │
│        export 並列化 / ZIP size / detect 高速化     │
│  出力: 既存 metadata.json 拡張 + minimap artifact   │
├─────────────────────────────────────────────────┤
│  L4 (former L3): メタデータ化（将来）                │
│  入力: L1 出力の試合動画                           │
│  処理: OCR (キルログ) + 音声認識 (VC/SE)           │
│  出力: タイムスタンプ付きイベントデータ              │
├─────────────────────────────────────────────────┤
│  L5 (former L4): 価値評価（将来）                   │
│  入力: L4 のイベントデータ                         │
│  処理: ローカル ML による投稿価値判定               │
│  出力: スコア + 推奨アクション                      │
├─────────────────────────────────────────────────┤
│  L6 (former L5): 自動編集（将来）                   │
│  入力: L5 の判定結果 + L1 の動画                   │
│  処理: MoviePy/FFmpeg で切り出し + サムネイル生成   │
│  出力: 投稿用動画 + メタデータ + 投稿提案           │
├─────────────────────────────────────────────────┤
│  L7 (former L6): プライバシー・精密分割（拡張）       │
│  プレイヤー名ぼかし、再エンコード分割モード          │
└─────────────────────────────────────────────────┘
```

- [ ] **Step 3: Update L6 referent below ASCII to L7**

Find the line `> L6 は暫定計画。詳細は ...` and update to `> L7 (former L6) は暫定計画。詳細は ...`.

- [ ] **Step 4: Update §ML モデル対応（将来: L4）heading**

Find the §「ML モデル対応（将来: L4）」section heading and update to `## ML モデル対応（将来: L5 (former L4)）`. Update body if it references L4 explicitly.

- [ ] **Step 5: Verify diff**

Run: `git diff docs/design-overview.md`
Expected: ASCII block replacement + 2-3 line updates. No other content changed.

- [ ] **Step 6: Commit**

```powershell
git add docs/design-overview.md
git commit -m @'
docs(v0.3.0): update design-overview layer ASCII for L3 redefinition

§段階的アーキテクチャ ASCII を 7 layer 構成に書き換え。新 L3 = 配信形式対応+性能改善
を v0.3.0 target で挿入、旧 L3 (OCR/Whisper) は L4 (former L3)、以降 1 段スライド。
ML model 言及 (旧 L4 → 新 L5) も更新。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A3: Update docs/release-process.md layer/version mapping

**Files:**
- Modify: `docs/release-process.md` (lines ~7, 13-15, 24-32, 110-112)

- [ ] **Step 1: Read sections to be modified**

Read `docs/release-process.md` lines 1-40, then 100-120.

Confirm:
- L7: `### コアレイヤー（L1〜L5）` heading
- L13-15: L3/L4/L5 rows in layer-to-version table
- L24-32: 拡張レイヤー (L6) section
- L26: "L3〜L5 の開発で..." sentence
- L32: "L5 リリース時に..." sentence
- L110-112: バージョン別検証テーマ table

- [ ] **Step 2: Update §コアレイヤー heading and table**

Edit `### コアレイヤー（L1〜L5）` → `### コアレイヤー（L1〜L6）`.

Replace the 3 L3-L5 rows (current lines 13-15) with 4 new rows for L3 (new) and L4-L6 (former L3-L5). **L1 and L2 rows are preserved unchanged** (lines ~11-12, scope-preserving):

```markdown
| L3 (new): 配信形式対応 + 性能改善 | 0.3.0 | `v0.3.0` | TBD |
| L4 (former L3): メタデータ化 | 0.4.0 | `v0.4.0` | TBD |
| L5 (former L4): 価値評価 | 0.5.0 | `v0.5.0` | TBD |
| L6 (former L5): 自動編集 | 0.6.0 | `v0.6.0` | TBD |
```

(Note: original release dates `2026-05-03/10/17` were aspirational and the schedule slid with v0.2.x retro. `TBD` reflects this.)

- [ ] **Step 3: Update §拡張レイヤー heading and content**

Edit `### 拡張レイヤー（L6）` → `### 拡張レイヤー（L7）`.

Edit `L2 完了後の拡張フェーズ。L3〜L5 の開発で新たな課題が判明した場合、スコープを見直す。`
→ `L2 完了後の拡張フェーズ。L3 (new)〜L6 (former L5) の開発で新たな課題が判明した場合、スコープを見直す。`

Edit the L6 row in 拡張レイヤー table:
```markdown
| L7 (former L6): プライバシー・精密分割 | 0.7.0 | `v0.7.0` | TBD | プレイヤー名ぼかし (#63)、再エンコード分割 (#28) |
```

Edit `> L6 は暫定計画。L5 リリース時に deferred issue を全件レビューし、スコープを確定する。`
→ `> L7 (former L6) は暫定計画。L6 (former L5) リリース時に deferred issue を全件レビューし、スコープを確定する。`

- [ ] **Step 4: Update §バージョン別検証テーマ (L110-112)**

Edit:
```markdown
| v0.3.0 | L3 (new): 配信形式対応 + 性能改善 | VTuber baseline 検知 ground truth 一致、export 並列で encoder 出力 visual spot check、Portable ZIP 起動回帰 |
| v0.4.0 | L4 (former L3): メタデータ化 | キルログ OCR / 音声認識統合の精度ベンチ、metadata schema 拡張の互換性検証 |
| v0.5.0 | L5 (former L4): 価値評価 | ローカル ML model 評価指標、サンプル動画群での評価分布 |
| v0.6.0 | L6 (former L5): 自動編集 | クリップ生成成功率、投稿提案の妥当性レビュー |
```

- [ ] **Step 5: Verify diff**

Run: `git diff docs/release-process.md`
Expected: only above sections changed. No other lines.

- [ ] **Step 6: Commit**

```powershell
git add docs/release-process.md
git commit -m @'
docs(v0.3.0): update release-process layer/version map for L3 redefinition

コアレイヤー (L1〜L6) / 拡張レイヤー (L7) に番号書き換え。v0.3.0 = 新 L3
(配信形式対応+性能改善)、以降スライドで L4-L7 を former 表記で記述。
バージョン別検証テーマ table も新 mapping に追従。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A4: Remove README.md §ロードマップ

**Files:**
- Modify: `README.md` (lines 43-53)

- [ ] **Step 1: Read README.md lines 40-57**

Use Read tool on README.md offset=40, limit=20.

Confirm L43-L53 contains `## ロードマップ` heading + table + trailing blank line.

- [ ] **Step 2: Delete §ロードマップ section**

Use Edit tool. Delete:

```markdown
## ロードマップ

| フェーズ | 機能 | 状態 |
| --- | --- | --- |
| L1 | 試合分割 | リリース済み (v0.1.1) |
| L2 | 配布・統合 (GUI + インストーラ + guard) | 開発中 |
| L3 | メタデータ化（OCR・音声認識） | 予定 |
| L4 | 投稿価値の自動評価 | 予定 |
| L5 | ハイライト自動編集 | 予定 |
| L6 | プライバシー・精密分割 | 計画中 |

```

Replace with empty string (the trailing blank line lines up §ライセンス correctly).

- [ ] **Step 3: Verify diff**

Run: `git diff README.md`
Expected: removal of 11-12 lines (heading + table + blank line). §ライセンス should now follow §ドキュメント directly.

- [ ] **Step 4: Verify markdown structure**

Run: `bash scripts/check-markdownlint.sh`
Expected: no markdownlint errors for README.md.

- [ ] **Step 5: Commit**

```powershell
git add README.md
git commit -m @'
docs(v0.3.0): remove README.md §ロードマップ (delegated to CLAUDE.md + design-overview.md)

§ロードマップ は CLAUDE.md / docs/design-overview.md と内容重複。§ドキュメント (L23-L41)
で design-overview.md へ link 案内済みのため、本 README からは削除し layer 詳細の単一情報源
を CLAUDE.md / design-overview.md に集約する。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §9.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A5: Update docs/cli-spec.md L205 incidental L3 reference

**Files:**
- Modify: `docs/cli-spec.md` (line 205 area)

- [ ] **Step 1: Read line 205 context**

Read `docs/cli-spec.md` offset=195, limit=20.

Confirm L205: `分割結果の機械可読な記録。外部ツールやスクリプトから参照可能。L3（メタデータ化）パイプラインの入力として使用予定。L3 未着手のため、フィールド構造は暫定であり破壊的変更の可能性がある。`

- [ ] **Step 2: Replace L3 references**

Use Edit tool. Replace:

```text
L3（メタデータ化）パイプラインの入力として使用予定。L3 未着手のため、フィールド構造は暫定であり破壊的変更の可能性がある。
```

with:

```text
L4 (former L3, メタデータ化) パイプラインの入力として使用予定。L4 未着手のため、フィールド構造は暫定であり破壊的変更の可能性がある。
```

- [ ] **Step 3: Verify diff + commit**

```powershell
git diff docs/cli-spec.md
git add docs/cli-spec.md
git commit -m @'
docs(v0.3.0): update cli-spec L3→L4 (former L3) reference

metadata.json 暫定性に関する記述で L3 を新番号 L4 (former L3) に更新。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §9.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A6: Update docs/reference-videos.md L3 OCR references

**Files:**
- Modify: `docs/reference-videos.md` (lines 11, 16)

- [ ] **Step 1: Read lines 1-30**

Read `docs/reference-videos.md` offset=1, limit=30.

Confirm:
- L11: `試合中の UI 要素（スコアボード、ミニマップ、キルログ等）の位置や見た目を把握するための資料。L1（暗転検知）・L3（OCR）の設計に直接役立つ。`
- L16: `... L3 OCR 対象の理解に有用 |`

- [ ] **Step 2: Replace L3 references**

Use Edit tool with `replace_all=false`:

Edit 1:
- old: `L1（暗転検知）・L3（OCR）の設計に直接役立つ`
- new: `L1（暗転検知）・L3 (new) (VTuber UI 適応)・L4 (former L3, OCR) の設計に直接役立つ`

Edit 2:
- old: `L3 OCR 対象の理解に有用`
- new: `L4 (former L3) OCR 対象の理解に有用`

- [ ] **Step 3: Verify diff + commit**

```powershell
git diff docs/reference-videos.md
git add docs/reference-videos.md
git commit -m @'
docs(v0.3.0): update reference-videos L3 references for layer shift

スコアボード / ミニマップ / キルログ資料の用途説明で L3 を分割:
- VTuber UI 適応 → L3 (new) 用途を追記
- OCR → L4 (former L3) に番号更新

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §9.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A7: Add v0.3.0 運用ルール to docs/issue-policy.md

**Files:**
- Modify: `docs/issue-policy.md` (§2 スコープラベル, §8 deferred ラベルの運用)

- [ ] **Step 1: Read §2 スコープラベル section**

Read `docs/issue-policy.md` offset=30, limit=30. Confirm §2 contains スコープラベル一覧.

- [ ] **Step 2: Add v0.3.0 title prefix convention after スコープラベル list**

Use Edit tool. After the existing スコープラベル table (last row), insert:

```markdown

#### v0.3.0 新 L3 work の title prefix 規約

v0.3.0 (= 新 L3) work では **新規 layer label を追加しない**。issue title prefix で識別する:

```text
[type] L3: <要約>                                    ← 新 L3 (VTuber+minimap+perf, v0.3.0 target)
[type] L4 (former L3): <要約>                        ← 旧 L3 (OCR/Whisper), L4 にスライド
[type] L5 (former L4): <要約>                        ← 旧 L4 (ML)
[type] L6 (former L5): <要約>                        ← 旧 L5 (auto edit)
[type] L7 (former L6): <要約>                        ← 旧 L6 (privacy)
```

詳細は [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §5 を参照。
```

- [ ] **Step 3: Read §8 deferred ラベルの運用 section**

Read `docs/issue-policy.md` offset=305, limit=30. Confirm §8 contains `### deferred ラベルの運用`.

- [ ] **Step 4: Add v0.3.0 deferred-removal rule**

Use Edit tool. After the existing `### deferred ラベルの運用` paragraph, insert:

```markdown

#### v0.3.0 期間中の運用 (2026-05-18 以降)

**`deferred` ラベルを外す = v0.3.0 (新 L3) で必須対応** と扱う:

- v0.3.0 着手対象に選定された issue: `deferred` を外す
- それ以外の issue (旧 L3 = L4 へ繰り下げ、旧 L4-L6 等): `deferred` を維持
- 検索: v0.3.0 アクティブセット = `is:open -label:deferred`

詳細は [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §5.2 を参照。
```

- [ ] **Step 5: Verify diff + commit**

```powershell
git diff docs/issue-policy.md
git add docs/issue-policy.md
git commit -m @'
docs(v0.3.0): add issue-policy v0.3.0 운営 rules

§2 スコープラベル に title prefix [type] L3:/[type] L4 (former L3): 規約を追加。
§8 deferred ラベルの運用 に「deferred 外し = v0.3.0 必須対応」ルールを追加。
両方とも spec 2026-05-18-v030-l3-redefinition-design.md §5 を参照。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §9.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A8: Add v0.3.0 baseline section to docs/testing-guide.md

**Files:**
- Modify: `docs/testing-guide.md` (insert new section after §baseline drift の判定, around L160)

- [ ] **Step 1: Locate insertion point**

Read `docs/testing-guide.md` offset=155, limit=30. Confirm §baseline drift の判定 section ends.

- [ ] **Step 2: Insert new section**

Use Edit tool. After the last paragraph of §baseline drift の判定 (typically the `### 事例` block or end of file), insert:

```markdown

## v0.3.0 L3 work 用 regression baseline

v0.3.0 (= 新 L3) の Pillar 3 (perf 改善) と Phase 2b (scorebar ROI 適応) は既存 detect / export パイプラインを touch するため、改修前後で検知結果 + 書出し結果に regression がないことを **bit-exact baseline 比較** で保証する。

§baseline drift の判定 (ffmpeg version 依存差異) とは別軸で、**同一 ffmpeg version での実装変更 regression** を見る。

### baseline 動画セット (2 系統)

| 系統 | 動画 | 役割 |
|---|---|---|
| OBS baseline | ALLAGANEYE_SAMPLE_VIDEO_DIR 配下の代表 OBS 録画 (Phase 1 child issue で N 本選定) | 正常検知可能な録画で改修後 regression なし保証 |
| VTuber primary benchmark | `E:\videos\gyawa_vatos\2772549129-...mp4` (7.5 GB, gyawa 提供 2026-05-18) | Phase 2 input adapt の primary test target + Pillar 3 robustness 検証 |

### baseline 定義

| 項目 | 内容 | 比較方法 |
|---|---|---|
| 検知結果 | `metadata.json` の `matches` (`index` / `start_time` / `end_time` / `duration` / `type` / `output_file`) + `gaps` | bit-exact (JSON canonical 比較)。`detected_at` は除外 |
| 書出し結果 (split) | 試合 MP4 のファイルサイズ + SHA-256 hash | byte-exact (`-c copy` 無劣化のため決定論的) |
| 書出し結果 (export GUI) | encoder/version 依存で byte-exact 不可 | ffprobe メタデータ (長さ・解像度・fps・codec) + 任意 1 フレーム抽出 spot check |

### 配置規約

```text
tests/baselines/v0.3.0/
├── vtuber-primary-ground-truth.json     # VTuber 5 試合 ground truth (spec §8.6)
├── <obs-baseline-N>.metadata.json       # 改修前 detect 結果 snapshot
└── <obs-baseline-N>.split.json          # 改修前 split MP4 sizes + SHA-256
```

動画本体は repo に commit しない。metadata snapshot のみ commit。

### 比較スクリプト

```powershell
python scripts/compare-baseline.py tests/baselines/v0.3.0/<video>.metadata.json output/<video>/metadata.json
# exit 0 = match, exit 1 = diff detected
```

詳細仕様は [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8 を参照。
```

- [ ] **Step 3: Verify markdown structure**

Run: `bash scripts/check-markdownlint.sh`
Expected: no markdownlint errors for `docs/testing-guide.md`.

- [ ] **Step 4: Commit**

```powershell
git add docs/testing-guide.md
git commit -m @'
docs(v0.3.0): add testing-guide §v0.3.0 L3 work 用 regression baseline

bit-exact baseline 比較規約を新 section として追加。OBS baseline + VTuber primary
benchmark の 2 系統、metadata.json bit-exact + MP4 byte-exact + export ffprobe spot
check の 3 段、tests/baselines/v0.3.0/ 配置規約を明文化。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §8

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task A9: Create PR 1 (Wave A bundled)

**Files:** No file changes (PR creation only)

- [ ] **Step 1: Run Iron Law 6 Pre-flight**

Per `.claude/hooks/session-start.sh` and `docs/l2-workflow.md §PR 作成 Pre-flight`:

```powershell
# Step 0 hard gate
gh pr list --search "v030-l3-redefinition" --state open

# Step 1 base sync
git fetch origin develop-0.3.0

# Step 2 incoming commits
git log HEAD..origin/develop-0.3.0 --oneline

# Step 3 touched files
git diff --name-only origin/develop-0.3.0..HEAD

# Step 4 parallel PR re-check
gh pr list --search "v030-l3-redefinition" --state all
```

Expected: Step 0 hard gate returns 0 PR (no conflict).

- [ ] **Step 2: Run automatic checks for Markdown changes**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations.

(Note: this is a docs-only PR. Python `ruff check` / `pytest` / GUI checks are not required per `docs/l2-workflow.md §PR 作成 path 別自動チェック` — Python and GUI paths are not touched.)

- [ ] **Step 3: Run /codex:adversarial-review (Step 5)**

Invoke `/codex:adversarial-review` with focus:

> Verify no scope creep beyond v0.3.0 L3 redefinition doc realignment per spec 2026-05-18-v030-l3-redefinition-design.md §9. Check: (i) Iron Law 3 — only L3-redefinition-related doc changes, no incidental refactors. (ii) layer table consistency across CLAUDE.md / design-overview.md / release-process.md (same 7-layer scheme). (iii) §4.1 文脈保存ルール — no `[type] L4 (former L3):` chain edits. (iv) #753 / past L3 PRs root cause not regressing.

Address any findings before creating PR (apply in-PR fixes per (A) PR 内修正優先 規約).

- [ ] **Step 4: Push branch and create PR**

```powershell
git push -u origin claude/elegant-euler-9d8bba
gh pr create --base develop-0.3.0 --title "docs(v0.3.0): L3 redefinition layer table + docs realignment" --body-file -
```

PR body (passed via stdin as `--body-file -`):

```markdown
## Summary

- 新 L3 = 配信形式対応 + 性能改善 (VTuber+minimap+perf) を v0.3.0 target として layer table に挿入。旧 L3 (OCR/Whisper) は L4 (former L3) に 1 段スライド、下流も L5/L6/L7 へ繰り下げ
- 7 doc を更新: CLAUDE.md / docs/design-overview.md / docs/release-process.md / README.md / docs/cli-spec.md / docs/reference-videos.md / docs/issue-policy.md / docs/testing-guide.md
- `docs/issue-policy.md` に v0.3.0 期間中の運用ルールを追加 (`deferred` 外し = active scope, title prefix [type] L3:)
- `docs/testing-guide.md` に bit-exact baseline 比較規約 (v0.3.0 L3 work 用) を追加

## Test plan

- [x] `bash scripts/check-markdownlint.sh` — 0 violations
- [x] layer table 整合確認 (CLAUDE.md / design-overview.md / release-process.md の 7-layer 一致)
- [x] README.md §ロードマップ 削除後の §ドキュメント → §ライセンス 流れ正常
- [x] `git diff` で意図外変更が無いことを確認
- machine-unverifiable:
- [ ] reviewer 目視: §4.1 文脈保存ルールの遵守 (旧 spec / plan は本文不変)
- [ ] reviewer 目視: 各 doc の番号変更が全部位で一貫している

spec: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 5: Return PR URL**

Capture and display the PR URL.

---

## Wave B: Issue Reorganization (bulk, AskUserQuestion gate)

> **Order constraint:** Execute Wave B **after PR 1 merges**. Renaming issues before doc PR merge would create dangling references (titles reference "L3" with new meaning while docs still describe old meaning).

### Task B1: AskUserQuestion bulk operation pre-confirmation

**Files:** No file changes (Iron Law 2 confirmation gate)

- [ ] **Step 1: Build sample preview**

Construct sample rename preview using #753 (1 issue):

```text
Before: [task] L3 (new) キックオフ: VTuber 配信動画対応 + minimap 切抜き
After:  [task] L3: VTuber + minimap キックオフ (parent issue)
Label change: remove `deferred`
```

- [ ] **Step 2: Invoke AskUserQuestion**

```jsonc
{
  "question": "28 件の issue 一括操作 (deferred 外し 8 件 + title rename 28 件) を実行します。サンプル (#753): \n\nBefore: [task] L3 (new) キックオフ: VTuber 配信動画対応 + minimap 切抜き\nAfter:  [task] L3: VTuber + minimap キックオフ (parent issue)\nLabel change: remove `deferred`\n\nどう進めますか?",
  "header": "Bulk issue ops",
  "multiSelect": false,
  "options": [
    {"label": "全件 OK (Recommended)", "description": "spec §6 の inclusion mapping / rename map 通り 28 件をまとめて実行"},
    {"label": "個別調整", "description": "1 件ずつ確認しながら実行 (時間かかる)"},
    {"label": "やめる", "description": "Wave B を中止"}
  ]
}
```

- [ ] **Step 3: Branch on response**

- "全件 OK" → proceed to B2
- "個別調整" → execute B2-B7 with `--confirm` interactive prompt per issue
- "やめる" → mark Wave B as skipped, jump to Wave C

---

### Task B2: Pillar 1+2 v0.3.0 inclusion (3 issues)

**Files:** No file changes

- [ ] **Step 1: Update #753 (parent)**

```powershell
gh issue edit 753 --remove-label deferred --title "[task] L3: VTuber + minimap キックオフ (parent issue)"
```

- [ ] **Step 2: Update #481 (minimap)**

```powershell
gh issue edit 481 --remove-label deferred --remove-label P3-low --add-label P2-medium --title "[enhancement] L3: minimap 切抜き機能"
```

- [ ] **Step 3: Update #480 (scorebar ROI)**

```powershell
gh issue edit 480 --remove-label deferred --remove-label P3-low --add-label P2-medium --title "[task] L3: VTuber 配信動画対応 (scorebar ROI 適応化)"
```

- [ ] **Step 4: Verify**

```powershell
gh issue list -l "P2-medium" --search "L3:" --state open
```

Expected: at least these 3 issues listed with new titles, no `deferred`.

---

### Task B3: Pillar 3 v0.3.0 inclusion (5 issues)

**Files:** No file changes

- [ ] **Step 1: #761 NVENC parallel export**

```powershell
gh issue edit 761 --remove-label deferred --title "[task] L3: NVENC 並列 export 基盤化"
```

- [ ] **Step 2: #762 multi-vendor parallel export**

```powershell
gh issue edit 762 --remove-label deferred --title "[task] L3: multi-vendor 並列 export (dGPU+iGPU)"
```

- [ ] **Step 3: #752 Portable ZIP file count**

```powershell
gh issue edit 752 --remove-label deferred --remove-label P3-low --add-label P2-medium --title "[task] L3: Portable ZIP file 数削減"
```

- [ ] **Step 4: #576 detect fps filter**

```powershell
gh issue edit 576 --remove-label deferred --remove-label P3-low --add-label P2-medium --title "[refactor] L3: detect fps filter 廃止 (CPU 律速改善)"
```

- [ ] **Step 5: #670 GUI HTTP server**

```powershell
gh issue edit 670 --remove-label deferred --remove-label P3-low --add-label P2-medium --title "[task] L3: GUI 動画 HTTP server 改善 (responsiveness)"
```

- [ ] **Step 6: Verify**

```powershell
gh issue list --state open --search "is:open -label:deferred" --json number,title,labels
```

Expected: 8 issues total (#753, #481, #480, #761, #762, #752, #576, #670). All `deferred`-free.

---

### Task B4: Cascading L3 → L4 (former L3) rename (11 issues)

**Files:** No file changes

Issues: #125, #126, #127, #128, #129, #130, #139, #140, #150, #151, #152

- [ ] **Step 1: For each issue, read current title and apply former-L3 prefix**

For each # in [125, 126, 127, 128, 129, 130, 139, 140, 150, 151, 152]:

```powershell
# Read current title
$current = gh issue view <#> --json title --jq '.title'

# Rename: replace "L3:" or "L3-L5:" or "L3 " etc. with "L4 (former L3)"
# Mechanical pattern: prepend "L4 (former L3): " after [type] prefix, drop existing L3 marker
gh issue edit <#> --title "<new-title>"
```

Per-issue title transformations:

| # | Before (current) | After |
|---|---|---|
| 125 | `[task] L3: Tesseract OCR によるキルログ抽出` | `[task] L4 (former L3): Tesseract OCR によるキルログ抽出` |
| 126 | `[task] L3: Whisper による音声認識・SE 検出` | `[task] L4 (former L3): Whisper による音声認識・SE 検出` |
| 127 | `[task] L3: イベントデータ出力フォーマットの設計` | `[task] L4 (former L3): イベントデータ出力フォーマットの設計` |
| 128 | `[risk] L3: OCR 精度 — ゲーム独自フォントの認識リスク` | `[risk] L4 (former L3): OCR 精度 — ゲーム独自フォントの認識リスク` |
| 129 | `[risk] L3: Whisper ローカル実行の処理時間・リソース消費` | `[risk] L4 (former L3): Whisper ローカル実行の処理時間・リソース消費` |
| 130 | `[task] L3: 外部依存の追加と環境構築手順の整備` | `[task] L4 (former L3): 外部依存の追加と環境構築手順の整備` |
| 139 | `[question] L3-L5 の end-to-end パイプライン設計` | `[question] L4-L6 (former L3-L5) の end-to-end パイプライン設計` |
| 140 | `[risk] L3-L5: 全体処理時間の見積もりとユーザー体験` | `[risk] L4-L6 (former L3-L5): 全体処理時間の見積もりとユーザー体験` |
| 150 | `[risk] L3: openai-whisper の PyTorch 依存によるインストールサイズ肥大化` | `[risk] L4 (former L3): openai-whisper の PyTorch 依存によるインストールサイズ肥大化` |
| 151 | `[risk] L3: OBS 録画に音声トラックが存在しない場合の処理` | `[risk] L4 (former L3): OBS 録画に音声トラックが存在しない場合の処理` |
| 152 | `[risk] L3: Tesseract 日本語言語パックの別途インストール要件` | `[risk] L4 (former L3): Tesseract 日本語言語パックの別途インストール要件` |

Execute each `gh issue edit <#> --title "<new>"` per row. Keep `deferred` label unchanged.

- [ ] **Step 2: Verify**

```powershell
gh issue list --state open --search "L4 (former L3)" --json number,title | ConvertFrom-Json | Format-Table number,title
```

Expected: 11 issues listed.

---

### Task B5: Cascading L4 → L5 (former L4) rename (4 issues)

**Files:** No file changes

Issues: #131, #132, #133, #134

- [ ] **Step 1: Rename per table**

| # | Before | After |
|---|---|---|
| 131 | `[task] [LLM拡張] LLM プラグインアーキテクチャの設計` | `[task] L5 (former L4) [LLM拡張]: LLM プラグインアーキテクチャの設計` |
| 132 | `[task] [LLM拡張] 投稿価値の評価基準定義` | `[task] L5 (former L4) [LLM拡張]: 投稿価値の評価基準定義` |
| 133 | `[risk] [LLM拡張] API コスト管理 — LLM 呼び出しの費用見積もり` | `[risk] L5 (former L4) [LLM拡張]: API コスト管理 — LLM 呼び出しの費用見積もり` |
| 134 | `[task] [LLM拡張] API キー管理とセキュリティ` | `[task] L5 (former L4) [LLM拡張]: API キー管理とセキュリティ` |

Note: these issues didn't have explicit "L4" in title (they're under [LLM拡張] umbrella per labels). Adding `L5 (former L4)` makes the layer mapping explicit.

```powershell
gh issue edit 131 --title "[task] L5 (former L4) [LLM拡張]: LLM プラグインアーキテクチャの設計"
gh issue edit 132 --title "[task] L5 (former L4) [LLM拡張]: 投稿価値の評価基準定義"
gh issue edit 133 --title "[risk] L5 (former L4) [LLM拡張]: API コスト管理 — LLM 呼び出しの費用見積もり"
gh issue edit 134 --title "[task] L5 (former L4) [LLM拡張]: API キー管理とセキュリティ"
```

- [ ] **Step 2: Verify**

```powershell
gh issue list --state open --search "L5 (former L4)" --json number,title
```

Expected: 4 issues listed.

---

### Task B6: Cascading L5 → L6 (former L5) rename (3 issues)

**Files:** No file changes

Issues: #135, #136, #137

- [ ] **Step 1: Rename per table**

| # | Before | After |
|---|---|---|
| 135 | `[task] L5: ハイライトクリップ自動切り出し` | `[task] L6 (former L5): ハイライトクリップ自動切り出し` |
| 136 | `[task] L5: サムネイル自動生成` | `[task] L6 (former L5): サムネイル自動生成` |
| 137 | `[task] L5: 投稿提案の出力設計` | `[task] L6 (former L5): 投稿提案の出力設計` |

```powershell
gh issue edit 135 --title "[task] L6 (former L5): ハイライトクリップ自動切り出し"
gh issue edit 136 --title "[task] L6 (former L5): サムネイル自動生成"
gh issue edit 137 --title "[task] L6 (former L5): 投稿提案の出力設計"
```

- [ ] **Step 2: Verify**

```powershell
gh issue list --state open --search "L6 (former L5)" --json number,title
```

Expected: 3 issues listed.

---

### Task B7: Cascading L6 → L7 (former L6) rename (2 issues)

**Files:** No file changes

Issues: #63, #28

- [ ] **Step 1: Read current titles**

```powershell
gh issue view 63 --json title
gh issue view 28 --json title
```

The titles may not contain explicit "L6" — they're in 拡張レイヤー context per `docs/release-process.md`. Add L7 prefix:

| # | Before | After |
|---|---|---|
| 63 | `[task] プレイヤー名ぼかし機能の検討・実装` | `[task] L7 (former L6): プレイヤー名ぼかし機能の検討・実装` |
| 28 | `[task] --precise フラグ（再エンコード分割モード）の追加` | `[task] L7 (former L6): --precise フラグ（再エンコード分割モード）の追加` |

```powershell
gh issue edit 63 --title "[task] L7 (former L6): プレイヤー名ぼかし機能の検討・実装"
gh issue edit 28 --title "[task] L7 (former L6): --precise フラグ（再エンコード分割モード）の追加"
```

- [ ] **Step 2: Verify**

```powershell
gh issue list --state open --search "L7 (former L6)" --json number,title
```

Expected: 2 issues listed.

- [ ] **Step 3: Final Wave B verification**

```powershell
# Total v0.3.0 active set (should be 8 + the 2 child issues from Wave D once created)
gh issue list --state open --search "is:open -label:deferred" --json number,title

# Total renamed deferred set (should be 11+4+3+2 = 20)
gh issue list --state open --search "former L" --json number,title | ConvertFrom-Json | Measure-Object -Property number
```

Expected:
- active set: 8 issues (Pillar 1+2: 3, Pillar 3: 5)
- former-L set: 20 issues

---

## Wave C: Baseline Infrastructure

### Task C1: Create ground truth JSON for VTuber primary benchmark

**Files:**
- Create: `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json`

- [ ] **Step 1: Create tests/baselines/v0.3.0/ directory**

```powershell
New-Item -ItemType Directory -Force -Path tests/baselines/v0.3.0
```

- [ ] **Step 2: Write ground truth JSON**

Create `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` with content:

```json
{
  "source_file": "2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4",
  "source_size_bytes": 7554775607,
  "source_dir_label": "gyawa_vatos",
  "ground_truth_provider": "user (manual)",
  "ground_truth_provided_at": "2026-05-18",
  "tolerance_sec": 10,
  "matches": [
    {"index": 1, "start_time": 1433, "end_time": 2361, "duration": 928, "type": "fl_match"},
    {"index": 2, "start_time": 2624, "end_time": 3635, "duration": 1011, "type": "fl_match"},
    {"index": 3, "start_time": 4253, "end_time": 5242, "duration": 989, "type": "fl_match"},
    {"index": 4, "start_time": 5684, "end_time": 6379, "duration": 695, "type": "fl_match"},
    {"index": 5, "start_time": 6609, "end_time": 7537, "duration": 928, "type": "fl_match"}
  ]
}
```

- [ ] **Step 3: Validate JSON syntax**

```powershell
python -c "import json; json.load(open('tests/baselines/v0.3.0/vtuber-primary-ground-truth.json', encoding='utf-8'))"
```

Expected: no exception.

- [ ] **Step 4: Verify duration arithmetic**

```powershell
python -c "
import json
gt = json.load(open('tests/baselines/v0.3.0/vtuber-primary-ground-truth.json', encoding='utf-8'))
for m in gt['matches']:
    assert m['end_time'] - m['start_time'] == m['duration'], f'duration mismatch for index {m[\"index\"]}'
print('All durations consistent.')
"
```

Expected output: `All durations consistent.`

- [ ] **Step 5: Commit**

```powershell
git add tests/baselines/v0.3.0/vtuber-primary-ground-truth.json
git commit -m @'
test(v0.3.0): add VTuber primary benchmark ground truth (5 matches)

gyawa 提供の 7.5GB MP4 (2772549129-151803977-...) の試合 5 件の ground truth metadata。
user 手動検証済み (2026-05-18)、tolerance ±10s。動画本体は repo に含めず metadata のみ。

Phase 2b (scorebar ROI 適応) 完了判定の baseline、Phase 1 (Pillar 3) では現状検知結果
との bit-exact 比較 baseline として使用。

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §8.6

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task C2: Implement scripts/compare-baseline.py with TDD

**Files:**
- Create: `tests/scripts/__init__.py` (if not exists)
- Create: `tests/scripts/test_compare_baseline.py`
- Create: `scripts/compare-baseline.py`

- [ ] **Step 1: Check tests/scripts/ exists**

```powershell
Test-Path tests/scripts
```

If false, create:

```powershell
New-Item -ItemType Directory -Force -Path tests/scripts
New-Item -ItemType File -Path tests/scripts/__init__.py
```

- [ ] **Step 2: Write failing test for normalize_metadata (drops detected_at)**

Create `tests/scripts/test_compare_baseline.py`:

```python
"""Tests for scripts/compare-baseline.py (v0.3.0 L3 baseline comparison)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Import the module under test (scripts/ is at repo root, not a package)
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "compare_baseline", SCRIPTS_DIR / "compare-baseline.py"
)
compare_baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_baseline)


def test_normalize_drops_detected_at():
    """normalize_metadata must remove `detected_at` field for comparability."""
    raw = {
        "source": "video.mp4",
        "detected_at": "2026-05-18T12:34:56Z",
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }
    result = compare_baseline.normalize_metadata(raw)
    assert "detected_at" not in result
    assert result["source"] == "video.mp4"
    assert result["matches"] == raw["matches"]
```

- [ ] **Step 3: Run test to verify it fails (module not found)**

```powershell
pytest tests/scripts/test_compare_baseline.py::test_normalize_drops_detected_at -v
```

Expected: FAIL with `FileNotFoundError` or `ModuleNotFoundError` (compare-baseline.py doesn't exist yet).

- [ ] **Step 4: Implement minimal compare-baseline.py**

Create `scripts/compare-baseline.py`:

```python
"""Compare detection result JSON files for regression testing.

Compares metadata.json files (baseline vs current) bit-exactly after dropping
the time-varying `detected_at` field. Used for v0.3.0 L3 Pillar 3 (perf) and
Phase 2b (scorebar ROI) regression detection.

Usage:
    python scripts/compare-baseline.py <baseline.json> <current.json>

Exit codes:
    0: bit-exact match
    1: any difference detected
    2: file load error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def normalize_metadata(raw: dict) -> dict:
    """Return a copy of `raw` with the time-varying `detected_at` field removed."""
    result = dict(raw)
    result.pop("detected_at", None)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    args = parser.parse_args(argv)

    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        current = json.loads(args.current.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    norm_baseline = normalize_metadata(baseline)
    norm_current = normalize_metadata(current)

    if norm_baseline == norm_current:
        print("MATCH: baseline and current are bit-exact (excluding detected_at).")
        return 0

    print("DIFF: baseline and current differ.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run test to verify it passes**

```powershell
pytest tests/scripts/test_compare_baseline.py::test_normalize_drops_detected_at -v
```

Expected: PASS.

- [ ] **Step 6: Write failing test for compare identical match → exit 0**

Append to `tests/scripts/test_compare_baseline.py`:

```python
def test_main_returns_0_on_identical_metadata(tmp_path: Path):
    """main() must return 0 when baseline and current are identical (modulo detected_at)."""
    baseline = {
        "source": "video.mp4",
        "detected_at": "2026-01-01T00:00:00Z",
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }
    current = {
        "source": "video.mp4",
        "detected_at": "2026-05-18T12:34:56Z",  # different timestamp
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    exit_code = compare_baseline.main([str(baseline_path), str(current_path)])
    assert exit_code == 0
```

- [ ] **Step 7: Run test (should pass with current implementation)**

```powershell
pytest tests/scripts/test_compare_baseline.py -v
```

Expected: 2 PASS.

- [ ] **Step 8: Write failing test for diff detection → exit 1**

Append:

```python
def test_main_returns_1_on_match_diff(tmp_path: Path):
    """main() must return 1 when match list differs."""
    baseline = {
        "source": "video.mp4",
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }
    current = {
        "source": "video.mp4",
        "matches": [{"index": 1, "start_time": 5, "end_time": 100}],  # start_time shifted
    }

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    exit_code = compare_baseline.main([str(baseline_path), str(current_path)])
    assert exit_code == 1
```

- [ ] **Step 9: Run test**

```powershell
pytest tests/scripts/test_compare_baseline.py -v
```

Expected: 3 PASS.

- [ ] **Step 10: Write failing test for file load error → exit 2**

Append:

```python
def test_main_returns_2_on_missing_file(tmp_path: Path):
    """main() must return 2 when baseline file doesn't exist."""
    nonexistent = tmp_path / "nope.json"
    current = tmp_path / "current.json"
    current.write_text("{}", encoding="utf-8")

    exit_code = compare_baseline.main([str(nonexistent), str(current)])
    assert exit_code == 2


def test_main_returns_2_on_invalid_json(tmp_path: Path):
    """main() must return 2 when JSON parse fails."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text("{}", encoding="utf-8")

    exit_code = compare_baseline.main([str(bad), str(good)])
    assert exit_code == 2
```

- [ ] **Step 11: Run all tests**

```powershell
pytest tests/scripts/test_compare_baseline.py -v
```

Expected: 5 PASS.

- [ ] **Step 12: Run repo-wide lint + type check**

```powershell
ruff check scripts/compare-baseline.py tests/scripts/
ruff format --check scripts/compare-baseline.py tests/scripts/
pyright scripts/compare-baseline.py
```

Expected: 0 violations / 0 errors.

If pyright complains about `compare-baseline.py` filename (hyphenated), it may resist the importlib trick — verify by running tests, since pytest is the source of truth.

- [ ] **Step 13: Commit**

```powershell
git add scripts/compare-baseline.py tests/scripts/__init__.py tests/scripts/test_compare_baseline.py
git commit -m @'
feat(tests): add scripts/compare-baseline.py for v0.3.0 L3 baseline comparison

metadata.json bit-exact 比較 (detected_at 除外) で Pillar 3 (perf) と Phase 2b
(scorebar ROI 適応) の regression 検出に使用。

- normalize_metadata: detected_at 削除
- main: bit-exact 比較で exit 0 / 1 / 2 (load error)
- TDD で 5 test 追加 (normalize / identical / diff / missing / invalid JSON)

spec: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md §8.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

### Task C3: Create PR 2 (Wave C bundled)

**Files:** No file changes (PR creation only)

- [ ] **Step 1: Run Iron Law 6 Pre-flight**

Per project rule:

```powershell
gh pr list --search "baseline regression" --state open
git fetch origin develop-0.3.0
git log HEAD..origin/develop-0.3.0 --oneline
git diff --name-only origin/develop-0.3.0..HEAD
gh pr list --search "baseline regression" --state all
```

Expected: Step 0 hard gate returns 0 PR (no conflict).

- [ ] **Step 2: Run automatic checks**

```powershell
ruff check .
ruff format --check .
pyright
pytest tests/scripts/test_compare_baseline.py -v
bash scripts/check-markdownlint.sh
```

Expected: all pass.

(GUI checks `npm run lint` / `typecheck` / `test` / `build` / `cargo check` are NOT required — `gui/` is not touched per `docs/l2-workflow.md §PR 作成 path 別自動チェック`.)

- [ ] **Step 3: Run /codex:adversarial-review**

Invoke `/codex:adversarial-review` with focus:

> Verify TDD discipline in compare-baseline.py (test before implementation), no scope creep beyond metadata bit-exact comparison per spec 2026-05-18-v030-l3-redefinition-design.md §8.2, JSON schema matches §8.6 ground truth example, normalize logic correctly drops `detected_at`.

Address findings in-PR.

- [ ] **Step 4: Push (if not pushed by PR 1) and create PR**

```powershell
git push -u origin claude/elegant-euler-9d8bba   # may be no-op if already pushed
gh pr create --base develop-0.3.0 --title "feat(tests): v0.3.0 baseline regression infrastructure (compare-baseline + ground truth)" --body-file -
```

PR body (`--body-file -` reading from stdin):

```markdown
## Summary

- `scripts/compare-baseline.py` を新規追加 (metadata.json bit-exact 比較、`detected_at` 除外)
- `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` を追加 (gyawa 提供 VTuber 動画の 5 試合 ground truth)
- `tests/scripts/test_compare_baseline.py` で TDD 5 test (normalize / identical / diff / missing / invalid JSON)

Phase 1 (Pillar 3) Wave 1a (#576 detect 改修) 着手前の必須インフラ。Phase 2b (scorebar ROI 適応) でも使用。

## Test plan

- [x] `pytest tests/scripts/test_compare_baseline.py -v` — 5 pass
- [x] `ruff check .` / `ruff format --check .` / `pyright` — 0 violations
- [x] `bash scripts/check-markdownlint.sh` — 0 violations
- [x] ground truth JSON の duration 整合性 (end - start == duration) を Python 検証
- machine-unverifiable:
- [ ] reviewer 目視: compare-baseline.py の API 設計が後続 Wave (#576 等) で必要十分か

spec: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 5: Return PR URL**

---

## Wave D: Phase 1 Prep Child Issue Creation

> **Order constraint:** Execute Wave D after Wave B (the `[type] L3:` title prefix convention must be active so child issues follow it).

### Task D1: Create child issue for OBS baseline selection

**Files:** No file changes

- [ ] **Step 1: Create issue**

```powershell
gh issue create --title "[task] L3: Phase 1 prep (i) OBS baseline 動画セット選定" --body-file -
```

Issue body (passed via stdin):

```markdown
## 概要

v0.3.0 Pillar 3 (perf) と Phase 2b (scorebar ROI 適応) の regression 検出用 baseline 動画セットから、OBS 録画系を N 本選定する (VTuber 動画は別途 #753 系で扱う)。

## 背景

[`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](../docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8.7 Phase 1 着手前準備 (i)。

Phase 1 Wave 1a (#576 detect fps filter 廃止) を含む全 perf 改修 PR の Self-Test Report で「baseline diff 0」を `[x]` で証明するために使用する。

## 確認項目 / 作業項目

- [ ] `ALLAGANEYE_SAMPLE_VIDEO_DIR` 配下から候補を列挙 (MKV / MP4)
- [ ] 各候補の特性を整理 (動画長 / codec / 解像度 / 試合数 / 既知の検出 quirk)
- [ ] N 本選定の基準確定 (サイズ・代表性・再現性)
- [ ] 選定リストを `tests/baselines/v0.3.0/README.md` (新規) に commit
- [ ] 選定理由を本 issue にコメント記録

## 対応方針

選定のみ。実際の baseline 生成は次 issue (Phase 1 prep (ii)) で実行。

## 関連

- spec: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](../docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8.7
- 後続: Phase 1 prep (ii) baseline 生成
```

- [ ] **Step 2: Verify**

```powershell
gh issue list --state open --search "Phase 1 prep (i)" --json number,title
```

Expected: 1 issue listed, no `deferred` label, title starts with `[task] L3:`.

---

### Task D2: Create child issue for baseline generation execution

**Files:** No file changes

- [ ] **Step 1: Create issue**

```powershell
gh issue create --title "[task] L3: Phase 1 prep (ii) 改修前 baseline 検知結果 + split 書出し生成" --body-file -
```

Issue body:

```markdown
## 概要

Phase 1 prep (i) で選定した OBS baseline 動画セット + VTuber primary benchmark に対して、**現状 (Pillar 3 改修前) の検知結果 + split 書出し結果** を生成し `tests/baselines/v0.3.0/` 配下に commit する。

## 背景

[`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](../docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8.7 Phase 1 着手前準備 (ii)。

Phase 1 Wave 1a (#576) 等の各 PR で `scripts/compare-baseline.py` による bit-exact 一致検証を行うための reference data。

## 前提

- Phase 1 prep (i) (OBS baseline 動画セット選定) 完了
- `develop-0.3.0` ブランチが #576 等の Pillar 3 改修を含まない状態 (= 改修前)

## 確認項目 / 作業項目

- [ ] 各 baseline 動画で `allaganeye detect <video>` を実行
- [ ] 出力 `metadata.json` を `tests/baselines/v0.3.0/<label>.metadata.json` に保存
- [ ] 各 baseline 動画で `allaganeye split --from-metadata <metadata.json>` を実行
- [ ] 生成された MP4 のファイルサイズ + SHA-256 hash を `tests/baselines/v0.3.0/<label>.split.json` に保存 (新規 schema、本 issue で確定)
- [ ] `scripts/compare-baseline.py <baseline.json> <baseline.json>` が exit 0 を返すことを smoke test
- [ ] commit + (必要なら) PR 作成

## 対応方針

検出パラメータは default (`--no-cache` 付きで run)。生成時間は動画長 × N 本に比例するため、時間バジェット要確認。

## 関連

- spec: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](../docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8.7
- 前提: Phase 1 prep (i) 動画セット選定
- 後続: #576 detect fps filter 廃止 (Phase 1 Wave 1a)
```

- [ ] **Step 2: Verify**

```powershell
gh issue list --state open --search "Phase 1 prep (ii)" --json number,title
```

Expected: 1 issue listed, no `deferred` label.

- [ ] **Step 3: Final Wave D verification**

```powershell
gh issue list --state open --search "is:open -label:deferred" --json number,title | ConvertFrom-Json | Measure-Object
```

Expected: 10 issues (Wave B 8 + Wave D 2 = 10 active v0.3.0 issues).

---

## Plan Self-Review Checklist

Run this checklist after writing the plan, before handing off to execution.

### Spec coverage

For each section of [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](../specs/2026-05-18-v030-l3-redefinition-design.md), confirm a task implements it:

- [x] §3 新 L3 定義 (3 pillars) — described in plan Goal/Architecture, implemented via doc updates A1-A2
- [x] §4 Layer shift map — A1 (CLAUDE.md), A2 (design-overview.md), A3 (release-process.md)
- [x] §5 Label/Title convention — A7 (issue-policy.md additions)
- [x] §6 Issue inclusion mapping — Wave B (B2-B7)
- [x] §6.5 Iron Law 2 bulk gate — B1 AskUserQuestion
- [x] §7 Implementation phase order — out of scope for this plan (deferred to per-pillar child brainstorms)
- [x] §8 Baseline regression — A8 (testing-guide section), C1 (ground truth), C2 (compare-baseline.py), D1+D2 (child issues for actual baseline generation)
- [x] §9 Documents update list — Wave A (8 doc tasks A1-A8)
- [x] §10 Out of scope — explicitly mirrored in plan Architecture paragraph
- [x] §11 Open questions — left as open (resolved at execution time or in follow-up)

### Placeholder scan

- [x] No "TBD" / "TODO" / "implement later" in task steps
- [x] No "Add appropriate error handling" — error handling is concrete (exit 2 for load error)
- [x] No "Write tests for the above" without showing the test code — all test code is inline
- [x] No "Similar to Task N" — each task is self-contained

### Type consistency

- [x] `compare_baseline.normalize_metadata` signature (`dict -> dict`) consistent across tests and impl
- [x] `compare_baseline.main` signature (`list[str] | None -> int`) consistent across tests and impl
- [x] Exit codes (0/1/2) consistent in script docstring, tests, and impl

### Architecture alignment

- [x] Plan deliberately does NOT implement Pillar 3 perf work (e.g., #576 fps filter changes) — those are spec §10 Out of scope
- [x] Plan deliberately does NOT implement Phase 2 work — same
- [x] Plan creates child issues for Phase 1 prep (i)/(ii) for human/agent to execute later, since baseline generation is environment-dependent (requires actual video files)

---

## Execution Notes

**Recommended ordering:**

1. Wave A (doc updates) → PR 1 created and merged
2. Wave B (issue ops via gh CLI) — after PR 1 merges, so doc state matches new title meanings
3. Wave C (baseline infra) → PR 2 created and merged
4. Wave D (child issue creation) — last, references newly-introduced conventions

Waves A and C can be developed in parallel (independent files), but PR 1 should merge before Wave B to keep doc/title meaning consistent.

**Time budget rough estimate:**

- Wave A: 90-120 min (8 docs + PR + Codex review + merge wait)
- Wave B: 30-45 min (28 gh issue edit calls + verify)
- Wave C: 60-90 min (TDD 5 tests + PR + Codex review + merge wait)
- Wave D: 15-20 min (2 issue create + verify)

Total: ~4-5 hours of focused work, depending on Codex turnaround.
