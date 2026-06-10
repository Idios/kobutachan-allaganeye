# Audit Remediation Wave 1 — Phase 0 + PR G1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **注記 (2026-06-10 /iterate-review Round 3)**: 本 plan は point-in-time の実行 artifact。G1 実装確定の正は spec §G1 と `tests/conftest.py` / `tests/test_marker_conventions.py` を参照のこと (review round での強化により本 plan のコードサンプルから乖離あり: hook の tryfirst 付与 / エラーメッセージの複数行化 + ASCII 化 / 手動 red 実証の pytester 統合テスト置換)。

**Goal:** Wave 1 の起点を作る — 監査対応 issue 7 本の起票 + issue アクション 2 件 (Phase 0) と、最初の PR である G1 (slow マーカー配線修正 + 規約 enforcement、spec/監査レポート同梱コミット) を完成させる。

**Architecture:** Phase 0 は gh 操作のみ (Iron Law 2 の AskUserQuestion ゲート付き、controller = 主セッションで実行)。G1 は (1) マーカー違反 2 ファイルの修正 → (2) 「`slow_*` サブマーカー ⇒ `slow` 必須」契約を pytest collection hook で機械化 (TDD)、の順で 1 branch / 1 PR。G2〜N3 の残り 7 PR は本 plan のスコープ外で、各着手時に個別 plan を作成する (spec §Wave 1 詳細に設計・AC 確定済み)。

**Tech Stack:** gh CLI (Git Bash、日本語本文は HEREDOC + `--body-file -`)、pytest (collection hook / marker)、ruff / pyright。

**参照 (必読):**

- spec: `docs/superpowers/specs/2026-06-10-audit-remediation-design.md` (§Wave 1 詳細 / §新規 issue 起票一覧)
- findings: `docs/audits/2026-06-10-full-audit.md` (P1-3 が G1 の対象)
- issue 書式: `docs/issue-policy.md` §2-3 (テンプレート・ラベル・40 字タイトル・`作成:` 行)
- PR 規約: `docs/l2-workflow.md` §PR 作成 Pre-flight / §Self-Test Report 規約

**前提条件 / 事実 (2026-06-10 時点の実測):**

- working tree clean (audit red test は `stash@{0}` 退避済み)、branch `develop-0.3.0`
- `docs/audits/2026-06-10-full-audit.md` と `docs/superpowers/specs/2026-06-10-audit-remediation-design.md` は**未コミットで存在する** (本 PR で同梱コミット — 決定事項 (b))
- マーカー違反の全量: `tests/test_v030_baseline_regression.py` (4 テスト、`slow_detect` 単独) / `tests/test_scorebar_regression.py:297-299` `TestPerformance` と `:412-414` `TestNoResolutionCompat` (`slow_detect`+`baseline_regen`、`slow` なし)。`tests/test_integration.py` は `pytestmark = pytest.mark.slow` (L27) で適合済み
- `tests/conftest.py` に `pytest_collection_modifyitems` は未定義 (新設して衝突しない)
- `tests/__init__.py` が存在するため `from tests.conftest import ...` が可能
- session-id: 本 plan の作業では `audit-w1-20260610` を使う

**spec からの設計確定 1 件 (G1):** spec §G1 は「conftest の `_ffmpeg_interval` cooldown を `slow_*` にも拡張」としていたが、enforcement hook が「`slow_*` ⇒ `slow`」を collection 時に強制するため、`get_closest_marker("slow")` のままで不変条件が成立する。**cooldown 拡張は実装しない** (YAGNI)。Task 9 で spec 側にこの確定を追記する。

---

## File Structure

| 区分 | path | 責務 |
| --- | --- | --- |
| Create | `tests/test_marker_conventions.py` | enforcement helper の純関数ユニットテスト |
| Modify | `tests/test_v030_baseline_regression.py` | docstring 訂正 + module pytestmark 化 (slow + slow_detect) |
| Modify | `tests/test_scorebar_regression.py` | 2 class に `@pytest.mark.slow` 追加 |
| Modify | `tests/conftest.py` | `slow_submarker_violations()` 純関数 + `pytest_collection_modifyitems` hook |
| Modify | `docs/superpowers/specs/2026-06-10-audit-remediation-design.md` | G1 cooldown 拡張の不要化を追記 |
| Commit only | `docs/audits/2026-06-10-full-audit.md` / 上記 spec | 既に内容完成、本 PR の先頭 commit で追加 |

---

## Phase 0: issue 起票 + issue アクション

> Phase 0 は AskUserQuestion を使うため**主セッション (controller) で実行する** (subagent に出さない)。

### Task 1: Iron Law 2 確認ゲート

**Files:** なし (対話のみ)

- [ ] **Step 1: 起票対象 7 件の表を提示して確認を取る**

AskUserQuestion で以下を提示する。質問 1: spec §新規 issue 起票一覧の **行 1〜7** (G1/G2/G3/G5/N1/N2/N3) を、Task 2 の本文サンプル (G1 の body 全文を例示) とともに「全件 OK / 個別調整 / やめる」の 3 択で確認。質問 2: #805 への優先度 label を「P2-medium を今付与し、deferred は G4 マージ後 (段階 2 持ち越し確定時) に付与 (Recommended)」「P1-high (v0.3.0 ゲート扱い)」「label なし継続」の 3 択で確認。

- [ ] **Step 2: 回答を記録**

「個別調整」の場合は調整内容を反映してから Task 2 へ。「やめる」なら Phase 0 を中断し Idios の指示を仰ぐ。

### Task 2: 7 issue の起票

**Files:** なし (gh のみ)。すべて `--assignee "Idios"`。各 body 末尾に `作成: audit-w1-20260610`。

- [ ] **Step 1: G1 issue を起票し番号を捕捉**

```bash
G1=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[bug] v0.3.0 baseline regression が slow マーカー規約から漏れている" \
  --label "bug" --label "P1-high" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
`tests/test_v030_baseline_regression.py` の 4 テストが `slow_detect` 単独付与のため、testing-guide.md の「slow はサブマーカーのスーパーセット」契約に違反し、documented コマンドのどれからも実行されない。

## 該当コード
- `tests/test_v030_baseline_regression.py:28,62,143,181` (`@pytest.mark.slow_detect` 単独)
- `tests/test_scorebar_regression.py:297-299,412-414` (同型違反: `slow_detect`+`baseline_regen` のみ)
- `pyproject.toml:53` (addopts `-m 'not slow and not baseline_regen'`)

## 問題
(a) `ALLAGANEYE_SAMPLE_VIDEO_DIR` が設定された環境では bare `pytest` が数時間級の実動画 detect を実行する。(b) `pytest -m slow` / `pytest -m "slow or baseline_regen"` は v030 baseline を deselect するため、bit-exact gate を「回したつもりで回っていない」。(c) conftest の GPU cooldown (`slow` のみ参照) も効かない。詳細: docs/audits/2026-06-10-full-audit.md P1-3。

## 修正方針
module pytestmark 化 (`[pytest.mark.slow, pytest.mark.slow_detect]`) + scorebar_regression 2 class へ `slow` 追加 + 「slow_* ⇒ slow」を pytest collection hook で機械的に強制する (再発防止)。設計: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §G1。

作成: audit-w1-20260610
EOF
)
echo "G1=#$G1"
```

Expected: `G1=#<番号>` が出力される (以降の Task で `$G1` を参照するため、番号を控える)。

- [ ] **Step 2: G2 issue を起票**

```bash
G2=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[bug] GUI: detect 中断がプロセスを kill しない" \
  --label "bug" --label "P1-high" --label "l2a-gui" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
DetectingScreen の「中断」は phase 遷移のみで `kill_tracked_processes` を呼ばず、Python detect + 最大 32 本の ffmpeg が走り続ける。drop 画面から同一動画への二重 detect も起動できる。

## 該当コード
- `gui/src/screens/DetectingScreen.tsx:314-321` (コメント「Real ffmpeg kill ships in #523's PR」のまま #523/#756 後も未配線)
- `gui/src/__tests__/flow.integration.test.tsx:334` (describe 名が「detecting cancel triggers kill_tracked_processes」だが中身はウィンドウ close 経路)

## 問題
中断後もリソースを消費し続け、二重 detect で同一 output dir へ 2 プロセスが書き込みうる。detect イベントに run 識別子がなく、新画面が旧 run のイベントを拾いうる。詳細: docs/audits/2026-06-10-full-audit.md P1-1。

## 修正方針
cancelling phase で `kill_tracked_processes` を invoke してから CANCEL_CONFIRMED。detect イベントへ run id を付与し越境イベントを遮断。誤名テストを実態に合わせて修正。設計: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §G2。実機 Tauri 検証が必要 (Iron Law 6)。

作成: audit-w1-20260610
EOF
)
echo "G2=#$G2"
```

- [ ] **Step 3: G3 issue を起票**

```bash
G3=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[bug] GUI: OUT<IN を apply でき metadata が読込不能になる" \
  --label "bug" --label "P1-high" --label "l2a-gui" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
境界編集で `end_time < start_time` を無検証で metadata.json に書き込め、次回 load が zod refine で reject → load エラーは UI のどこにも表示されず「No metadata」の空画面になり、GUI 内に復旧手段がない。

## 該当コード
- `gui/src/screens/PreviewScreen.tsx` (nudge / TC 入力 / FrameStrip に相互クランプなし)
- `gui/src/state/metadataStore.ts:152-176` (`normalizeForPersistence` が start/end 素通し)、`:163-173` (`*_display` を旧値コピー)、`:280` (`loadErrorState` を表示する UI なし)
- `gui/src/types/metadata.schema.ts:29-31` (load 側 refine)

## 問題
「不正書き込み → 読込拒否 → 無言の空画面」の三段連鎖 (audit P1-2 + P2-13 + P2-17)。apply 後は display 文字列も数値と矛盾したまま永続化される。詳細: docs/audits/2026-06-10-full-audit.md。

## 修正方針
UI 相互クランプ + apply 前 validation + Rust `apply_changes` の schema guard (多層防御)。loadErrorState の表示先を配線。normalize 時に display を `utils/time.ts` で再生成。設計: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §G3。実機 Tauri 検証が必要。

作成: audit-w1-20260610
EOF
)
echo "G3=#$G3"
```

- [ ] **Step 4: G5 issue を起票**

```bash
G5=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[doc] cli-spec / CLAUDE.md の P1 級 drift 修正" \
  --label "doc" --label "P1-high" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
一次仕様書に実害級の誤り 3 点: export index 基数 / gpu-vendor intel「実装予定」/ CLAUDE.md 音声昇格 (frozen 未反映)。

## 対象箇所
1. `docs/cli-spec.md:353-354` — `--include`/`--exclude` を「0 始まり」と記載
2. `docs/cli-spec.md:56` — `intel` は「exit 5 (#550 で実装予定)」と記載
3. `CLAUDE.md` §検知アルゴリズム「音声昇格」+ §コマンド `--no-audio` 注釈 + `audio/refs/` 行

## 誤記内容 / 矛盾内容
| 現状の記載 | 正 |
| --- | --- |
| include/exclude は 0 始まり | 実装は metadata の 1 始まり `index` と照合 (`allaganeye/commands/export.py:149`、GUI も 1 始まりを送信) |
| intel は exit 5 (実装予定) | #550/#582 で実装済み (`allaganeye/cli.py:130-139`) |
| 音声昇格が動作する (デフォルト有効) | `AUDIO_FROZEN: Final[bool] = True` (#327) で常にスキップ。`fanfare.npz` 記載も `war_room.npz` (#306) 未反映 |

## 対応方針
P1 級 3 点のみ最小修正 (P2 doc drift は W6 で SSoT 規約適用とセット)。詳細: docs/audits/2026-06-10-full-audit.md P1-5/6/7、設計: spec §G5。

作成: audit-w1-20260610
EOF
)
echo "G5=#$G5"
```

- [ ] **Step 5: N1 issue を起票**

```bash
N1=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[task] CI guard: sh test 配線 + branch pin の develop-* 化" \
  --label "task" --label "P2-medium" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
CI 未配線の test harness と develop-0.2.0 固定 pin 2 件を解消し、stale worktree 掃除を実施する。

## 期待値 (あるべき姿)
`tests/scripts/test_*.sh` 3 本が CI で実行され、cleanup script と checklist-test workflow が現行 develop branch (develop-*) に追従する。N1 マージ後に stale worktree 9 本が安全手順 (dry-run → Iron Law 2 確認 → apply) で掃除される。

## 現状
`scripts/cleanup-claude-branches.sh:94` と `.github/workflows/check-pr-checklist-test.yml:10` が develop-0.2.0 固定のため、merged branch が掃除されず (実害: v0.2.x 期の stale worktree 9 本が残存)、develop-0.3.0 への push で checklist-test が走らない。sh test 3 本は CI 参照ゼロ。

## ユーザー影響・重要性
ユーザー直接影響なし、開発インフラの腐敗防止 + 再発防止基盤。

## 確認項目 / 作業項目
- [ ] ci.yml に `tests/scripts/test_*.sh` 3 本の実行 step を追加
- [ ] check-pr-checklist-test.yml の push trigger を `develop-*` 化
- [ ] cleanup-claude-branches.sh の merged 判定を `origin/develop-*` 走査に一般化
- [ ] マージ後: branches → worktrees の 2 段 dry-run → Iron Law 2 確認 → apply (spec §N1 マージ後アクション)

## 対応方針
設計: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §N1。GitHub Actions の既知の罠は memory/feedback 既録テンプレに従う。

作成: audit-w1-20260610
EOF
)
echo "N1=#$N1"
```

- [ ] **Step 6: N2 issue を起票**

```bash
N2=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[task] skill 改修: 追跡切れ防止チェックの追加" \
  --label "task" --label "P2-medium" --label "l2-workflow" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
監査で検出した「closed 側から open 側への参照切れ」3 類型 (audit 横断所見 4) を skill 改修で構造的に防ぐ。

## 期待値 (あるべき姿)
/close-issue がクローズ前に PR 本文の「別 issue で追跡予定」宣言の行き先実在を確認し、/release の deferred レビューが issue 本文鮮度と not_planned close の残タスクを検出する。version bump grep が tauri.conf.json / package.json も拾う。skills 内 broken link 14 件が解消されている。

## 現状
PR #811 の guard repo follow-up 未起票、#762 not_planned close による残タスク orphan 化、versioning.md「pyproject.toml のみ」前提の bump grep、`.claude/skills/*/SKILL.md` の `../../docs/` リンク 14 件 (1 階層不足) が放置されている。

## ユーザー影響・重要性
開発プロセスの再発防止基盤 (issue 追跡の死角解消)。

## 確認項目 / 作業項目
- [ ] close-issue: 「別 issue で追跡」宣言の行き先確認 step を追加
- [ ] release: deferred レビューに本文鮮度 + not_planned 残タスク確認を追加、bump grep に *.json を追加
- [ ] skills の `../../docs/` → `../../../docs/` 一括修正 (14 件)
- [ ] empirical-prompt-tuning protocol で検証し Self-Test Report に記録

## 対応方針
設計: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §N2。skill 改修 PR 規約 (CLAUDE.md §skill 改修ワークフロー) に従う。

作成: audit-w1-20260610
EOF
)
echo "N2=#$N2"
```

- [ ] **Step 7: N3 issue を起票**

```bash
N3=$(gh issue create --repo Idios/kobutachan-allaganeye \
  --title "[doc] doc SSoT 規約の明文化 + release gate 追記" \
  --label "doc" --label "P2-medium" --assignee "Idios" \
  --body-file - <<'EOF' | grep -oE '[0-9]+$'
## 概要
「同じ仕様値を複数 doc に書かない (正 1 箇所 + 参照リンク)」規約の明文化と、release checklist への監査 P1 ゲート追記。W6 (doc 一括再同期) の前提。

## 対象箇所
- `docs/coding-conventions.md` (または適切な既存 doc — 追加前に `grep -n '^## '` で全 section を確認し重複回避)
- `docs/release-process.md` (リリース前チェック)

## 誤記内容 / 矛盾内容
規約不在の実害: workers 上限「24」が 6 doc 7 箇所に複製されたまま実装 (32) と drift (audit P2-25)。同型 drift が P2-26〜28 等で反復。

## 対応方針
SSoT 規約 (仕様値の正は cli-spec / metadata-spec / 実装 docstring のいずれか 1 箇所、他はリンク。CLAUDE.md は索引として要約可・数値は出典リンク併記) を規約化し、release-process に「監査 P1 (spec Wave 1) 全クローズ確認」を追記。設計: spec §N3。

作成: audit-w1-20260610
EOF
)
echo "N3=#$N3"
```

- [ ] **Step 8: 起票結果の検証**

```bash
gh issue list --repo Idios/kobutachan-allaganeye --search "audit-w1-20260610" --state open
```

Expected: 7 件 (G1/G2/G3/G5/N1/N2/N3) が列挙される。番号一覧を spec §新規 issue 起票一覧の各行末尾に `→ #N` 形式で追記する (Task 9 の spec 編集と同時でよい)。

### Task 3: #809 受け入れ条件追記

**Files:** なし (gh のみ)

- [ ] **Step 1: 既存 body を取得して追記版を作る**

```bash
gh issue view 809 --repo Idios/kobutachan-allaganeye --json body --jq .body > /tmp/809-body.md
cat >> /tmp/809-body.md <<'EOF'

## 受け入れ条件追記 (2026-06-10 audit P1-8)

wiring 順序依存の構造リスク対策 (詳細: docs/audits/2026-06-10-full-audit.md P1-8):

- [ ] scorebar 局在化 consumer (P2) を本 issue の wiring と同時または先行して導入する
- [ ] 上記が間に合わない場合でも、region != FULL_FRAME 時は `_drop_post_match_trailing` を無効化する gate を入れる (full-frame 前提の scorebar probe 群が VTuber layout で系統的 False を返し、全暗転 non_fl 化 + trailing drop 誤爆の複合事故になるため)
- [ ] `tests/detection_cache.py` の `_CACHE_SENSITIVE_FILES` に `capture_region.py` を追加する
EOF
```

- [ ] **Step 2: body を更新し確認**

```bash
gh issue edit 809 --repo Idios/kobutachan-allaganeye --body-file /tmp/809-body.md
gh issue view 809 --repo Idios/kobutachan-allaganeye --json body --jq .body | tail -8
```

Expected: 追記した 3 checkbox が表示される。

### Task 4: #805 triage コメント + label

**Files:** なし (gh のみ)

- [ ] **Step 1: triage コメントを投稿**

```bash
gh issue comment 805 --repo Idios/kobutachan-allaganeye --body-file - <<'EOF'
triage (2026-06-10 監査対応、spec: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §G4):

- **段階 1 (v0.3.0 で実施)**: trailing drop の warnings[] 記録 (`post_match_trailing_dropped` + start/end context) + escape hatch `--keep-trailing`。本 issue に紐づく PR として提出する
- **段階 2 (本 issue で継続)**: 非破壊化 (NotRequired フラグ方式)。#373 (末尾打ち切り情報の metadata 記録) と schema 設計を統合検討
- audio corroboration 案 (audit P2-1) は `AUDIO_FROZEN=True` の間 no-op のため見送り。#327 解凍時に再評価

作成: audit-w1-20260610
EOF
```

- [ ] **Step 2: label を付与 (Task 1 質問 2 の回答に従う)**

```bash
# Recommended 回答の場合:
gh issue edit 805 --repo Idios/kobutachan-allaganeye --add-label "P2-medium"
gh issue view 805 --repo Idios/kobutachan-allaganeye --json labels --jq '[.labels[].name]'
```

Expected: `["risk","P2-medium"]` (deferred は G4 マージ後・段階 2 持ち越し確定時に付与)。

---

## PR G1: slow マーカー配線修正 + 規約 enforcement

> ここからはコード作業。subagent 実行可。元 issue は Task 2 Step 1 の `$G1`。

### Task 5: branch 作成 + spec / 監査レポートの同梱コミット

**Files:**

- Add: `docs/audits/2026-06-10-full-audit.md` (作成済み・未コミット)
- Add: `docs/superpowers/specs/2026-06-10-audit-remediation-design.md` (作成済み・未コミット)
- Add: `docs/superpowers/plans/2026-06-10-audit-w1-phase0-g1.md` (本 plan、作成済み・未コミット)

- [ ] **Step 1: clean 確認と branch 作成**

```bash
cd /e/projects/kobutachan-tools/kobutachan-allaganeye
git status --short   # 出力が docs/ の untracked 3 件 (audit / spec / 本 plan) のみであること
git fetch origin develop-0.3.0
git checkout -b claude/audit-w1-g1 origin/develop-0.3.0
```

Expected: branch `claude/audit-w1-g1` が最新 base から作成される。

- [ ] **Step 2: docs を commit (決定事項 (b))**

```bash
git add docs/audits/2026-06-10-full-audit.md docs/superpowers/specs/2026-06-10-audit-remediation-design.md docs/superpowers/plans/2026-06-10-audit-w1-phase0-g1.md
git commit -m "doc: 2026-06-10 全体監査レポートと remediation 設計 spec を追加 (#${G1})

Wave 1 最初の PR に同梱する決定 (spec §決定事項 option b) に従い、
監査 findings の恒久記録 (P1-1..8 / P2-1..40 / P3) と対策プログラム設計を commit する。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: commit 成功。docs/ のみの単一 scope commit (preuse hook 適合)。

### Task 6: マーカー違反の修正 (red → green を collect-only で実証)

**Files:**

- Modify: `tests/test_v030_baseline_regression.py:1-28,62,143,181`
- Modify: `tests/test_scorebar_regression.py:297-299,412-414`

- [ ] **Step 1: 現状の誤配線を記録 (= failing 状態の実証)**

```bash
python -m pytest --collect-only -q -m slow 2>&1 | grep -c "test_v030_baseline_regression" || true
python -m pytest --collect-only -q 2>&1 | grep -c "test_v030_baseline_regression" || true
```

Expected: 1 行目 `0` (slow で選ばれない = バグ)、2 行目 `0` 以外 (bare pytest に紛れ込む = バグ。`ALLAGANEYE_SAMPLE_VIDEO_DIR` 未設定でも collection には載る)。

- [ ] **Step 2: test_v030_baseline_regression.py を module pytestmark 化**

docstring 3 行目の誤認記述を訂正し、module pytestmark を追加、4 箇所の単独 decorator を削除する。

```python
# 冒頭 (L1-5) を以下に置換:
"""v0.3.0 baseline regression tests (#576 S7.2 / S9.2).

slow + slow_detect マーカー: 実動画必須。`pytest -m slow` / `-m slow_detect` で実行し、
bare pytest からは addopts (`-m 'not slow and not baseline_regen'`) により除外される。
Idios 環境または ALLAGANEYE_SAMPLE_VIDEO_DIR が設定されたマシンで実行。
"""
```

```python
# import 群の直後 (現 L13 `import pytest` の後、`_REPO_ROOT = ...` の前) に追加:
pytestmark = [pytest.mark.slow, pytest.mark.slow_detect]
```

L28, L62, L143, L181 の `@pytest.mark.slow_detect` 行を 4 箇所とも削除する (module pytestmark に集約)。

- [ ] **Step 3: test_scorebar_regression.py の 2 class に slow を追加**

```python
# L297-299 (TestPerformance):
@pytest.mark.slow
@pytest.mark.slow_detect
@pytest.mark.baseline_regen
class TestPerformance:
```

```python
# L412-414 (TestNoResolutionCompat):
@pytest.mark.slow
@pytest.mark.slow_detect
@pytest.mark.baseline_regen
class TestNoResolutionCompat:
```

(いずれも既存 2 decorator の上に `@pytest.mark.slow` を 1 行追加するだけ)

- [ ] **Step 4: 選択が反転したことを検証**

```bash
python -m pytest --collect-only -q -m slow 2>&1 | grep -c "test_v030_baseline_regression"
python -m pytest --collect-only -q 2>&1 | grep -c "test_v030_baseline_regression" || true
python -m pytest --collect-only -q -m slow 2>&1 | grep -c "TestPerformance"
```

Expected: 1 行目 `0` 以外 (slow で選ばれる)、2 行目 `0` (bare から除外)、3 行目 `0` 以外。

- [ ] **Step 5: Commit**

```bash
git add tests/test_v030_baseline_regression.py tests/test_scorebar_regression.py
git commit -m "fix(test): v0.3.0 baseline と scorebar regression を slow マーカー契約に整合 (#${G1})

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 7: enforcement helper (TDD)

**Files:**

- Create: `tests/test_marker_conventions.py`
- Modify: `tests/conftest.py` (末尾に追加)

- [ ] **Step 1: failing unit test を書く**

`tests/test_marker_conventions.py` を新規作成:

```python
"""slow_* サブマーカー規約 guard のユニットテスト (audit 2026-06-10 P1-3 再発防止).

enforcement 本体は tests/conftest.py の pytest_collection_modifyitems。
ここではその純関数 slow_submarker_violations() を検証する。
"""

from tests.conftest import slow_submarker_violations


def test_detects_submarker_without_slow():
    mapping = {
        "tests/test_x.py::test_a": {"slow_detect"},
        "tests/test_x.py::test_b": {"slow_detect", "baseline_regen"},
    }
    assert slow_submarker_violations(mapping) == [
        "tests/test_x.py::test_a",
        "tests/test_x.py::test_b",
    ]


def test_accepts_submarker_with_slow():
    mapping = {
        "tests/test_x.py::test_a": {"slow", "slow_detect"},
        "tests/test_x.py::test_b": {"slow", "slow_gpu", "baseline_regen"},
    }
    assert slow_submarker_violations(mapping) == []


def test_ignores_unrelated_markers():
    mapping = {
        "tests/test_x.py::test_a": {"parametrize"},
        "tests/test_x.py::test_b": set(),
        "tests/test_x.py::test_c": {"slow"},
    }
    assert slow_submarker_violations(mapping) == []
```

- [ ] **Step 2: fail を確認**

```bash
python -m pytest tests/test_marker_conventions.py -v
```

Expected: FAIL (`ImportError: cannot import name 'slow_submarker_violations'`)。

- [ ] **Step 3: 実装 (純関数 + collection hook)**

`tests/conftest.py` の末尾に追加:

```python
_SLOW_SUBMARKERS = frozenset({"slow_probe", "slow_detect", "slow_pipeline", "slow_gpu"})


def slow_submarker_violations(marker_names_by_nodeid: dict[str, set[str]]) -> list[str]:
    """slow_* サブマーカーを持つのに slow を持たない nodeid を返す.

    testing-guide.md の「slow はサブマーカーのスーパーセット」契約を機械化する
    (audit 2026-06-10 P1-3: 違反すると documented コマンドから test が漏れる)。
    """
    return sorted(
        nodeid
        for nodeid, names in marker_names_by_nodeid.items()
        if names & _SLOW_SUBMARKERS and "slow" not in names
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """collection 時に slow マーカー契約違反を即エラーにする (deselect より前に全 item を検査)."""
    mapping = {item.nodeid: {m.name for m in item.iter_markers()} for item in items}
    violations = slow_submarker_violations(mapping)
    if violations:
        raise pytest.UsageError(
            "slow_* submarker without 'slow' (testing-guide.md の slow スーパーセット契約違反): "
            + ", ".join(violations)
        )
```

- [ ] **Step 4: pass + 全体 collection の無違反を確認**

```bash
python -m pytest tests/test_marker_conventions.py -v
python -m pytest --collect-only -q > /dev/null && echo COLLECT_OK
```

Expected: 3 件 PASS / `COLLECT_OK` (違反が残っていれば UsageError で非ゼロ exit)。

- [ ] **Step 5: guard が実際に効くことを一時違反で実証 (手動 red)**

`tests/test_scorebar_regression.py` の L297 `@pytest.mark.slow` を一時的に削除して:

```bash
python -m pytest --collect-only -q 2>&1 | tail -3
git checkout -- tests/test_scorebar_regression.py
```

Expected: `UsageError: slow_* submarker without 'slow' ... TestPerformance` を含むエラーで非ゼロ exit → その後 `git checkout` で復元。

- [ ] **Step 6: Commit**

```bash
git add tests/test_marker_conventions.py tests/conftest.py
git commit -m "test: slow_* サブマーカー単独付与を collection 時に拒否する規約 guard を追加 (#${G1})

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 8: 全体検証 (Iron Law 6 path 別チェック)

**Files:** なし

- [ ] **Step 1: Python 系チェックを全部回す**

```bash
ruff check . && ruff format --check . && pyright && python -m pytest
```

Expected: すべて pass。bare pytest は fast suite のみ実行 (v030 baseline は除外済み)、かつ collection hook が全 item を検査して green。

- [ ] **Step 2: マーカー選択マトリクスの最終確認**

```bash
python -m pytest --collect-only -q -m slow 2>&1 | grep -c "test_v030_baseline_regression"
python -m pytest --collect-only -q -m "slow or baseline_regen" 2>&1 | grep -c "test_v030_baseline_regression"
python -m pytest --collect-only -q -m slow_detect 2>&1 | grep -c "test_v030_baseline_regression"
```

Expected: 3 行とも `0` 以外 (documented な 3 コマンドすべてで gate が回る)。

### Task 9: spec への確定事項追記

**Files:**

- Modify: `docs/superpowers/specs/2026-06-10-audit-remediation-design.md` §G1

- [ ] **Step 1: cooldown 拡張の不要化を spec に反映**

§G1 の設計 bullet `conftest の \`_ffmpeg_interval\` cooldown の発動条件を \`slow\` に加えて \`slow_*\` サブマーカーにも拡張` を以下に置換:

```text
conftest の `_ffmpeg_interval` cooldown は現行 (`slow` のみ参照) を維持する — enforcement hook が「slow_* ⇒ slow」を collection 時に強制するため、拡張は冗長 (2026-06-10 plan で確定)
```

あわせて §新規 issue 起票一覧の行 1〜7 の末尾に Phase 0 で得た実番号 (`→ #N`) を追記する。

- [ ] **Step 2: lint + Commit**

```bash
bash scripts/check-markdownlint.sh 2>&1 | grep "2026-06-10-audit-remediation-design" || echo LINT_OK
git add docs/superpowers/specs/2026-06-10-audit-remediation-design.md
git commit -m "doc: spec に G1 cooldown 確定と issue 実番号を反映 (#${G1})

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: `LINT_OK` (violation 出力なし) → commit 成功。

### Task 10: PR 作成 (Iron Law 6 Pre-flight)

**Files:** なし

- [ ] **Step 1: Pre-flight Step 0 (ハードゲート)**

```bash
gh pr list --repo Idios/kobutachan-allaganeye --search "${G1}" --state open
```

Expected: 0 件 (既存 PR があれば STOP して Idios に確認)。

- [ ] **Step 2: Pre-flight Step 1-3 (base 同期確認)**

```bash
git fetch origin develop-0.3.0
git log HEAD..origin/develop-0.3.0 --oneline
```

Expected: 出力 0 行。出力がある場合は取り込み commit の touched files と本 PR (tests/conftest.py 等) の交差を確認し、交差すれば rebase + 再検証。

- [ ] **Step 3: Pre-flight Step 4 (並行 PR 重複再確認)**

```bash
gh pr list --repo Idios/kobutachan-allaganeye --search "${G1}" --state all
```

Expected: 0 件。

- [ ] **Step 4: Pre-flight Step 5 (Codex adversarial-review)**

`/codex:adversarial-review` を invoke する。focus: 「pytest collection hook の追加が既存 test 選択を変えないか / pytestmark 化による marker 意味の変化 / Iron Law 3 (scope creep) / docs 同梱 commit の妥当性」。Codex CLI が fail した場合は superpowers `requesting-code-review` subagent に fallback し、PR 本文に Codex fallback notice を必須記載 (CLAUDE.md §Token 枯渇時の fallback)。

- [ ] **Step 5: push + PR 作成**

```bash
git push -u origin claude/audit-w1-g1
gh pr create --repo Idios/kobutachan-allaganeye --base develop-0.3.0 \
  --title "fix(test): v0.3.0 baseline の slow マーカー配線修正 + 規約 guard (Refs #${G1})" \
  --body-file - <<EOF
## 概要
audit P1-3 対応 (Refs #${G1})。spec: docs/superpowers/specs/2026-06-10-audit-remediation-design.md §G1。
監査レポート + remediation spec を先頭 commit で同梱 (決定事項 option b、docs と tests の 2 scope を含むが per-commit では単一 scope)。

## 変更内容
- 監査レポート / remediation spec の追加 (docs)
- test_v030_baseline_regression.py: module pytestmark 化 (slow + slow_detect) + docstring 訂正
- test_scorebar_regression.py: TestPerformance / TestNoResolutionCompat に slow 追加
- tests/conftest.py: slow_* ⇒ slow 契約の collection-time enforcement (+ 純関数 unit test)

## Self-Test Report
- [x] ruff check . / ruff format --check . / pyright / pytest 全 pass
- [x] collect-only マトリクス: -m slow / -m "slow or baseline_regen" / -m slow_detect すべてで v030 baseline が select、bare pytest では deselect
- [x] enforcement の実効性: slow を一時除去すると UsageError で collection が fail することを確認
- 実動画での slow 実行は本 PR では不要 (マーカー配線のみ、テスト本体・検知ロジック無変更)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 6: issue へ完了コメント + 後続**

```bash
gh issue comment ${G1} --repo Idios/kobutachan-allaganeye \
  --body "完了: audit-w1-20260610 → PR #<上で得た PR 番号>。マーカー配線修正 + enforcement 追加。"
```

PR 作成後は `/iterate-review <PR#>` で review-fix ループへ。マージ後のクローズは `/close-issue ${G1}` (Iron Law 4)。

---

## 後続 (本 plan のスコープ外、順序のみ)

G1 マージ後、spec §Wave 1 の残り 7 PR を just-in-time plan で進める。推奨順: **G5 (doc、最小) → N1 (CI guard → マージ後 worktree 掃除) → N3 (SSoT 規約、W6 の前提) → G4 (#805 段階 1、G1 の gate で検証) → G2 / G3 (GUI、実機検証依頼) → N2 (skill、empirical-prompt-tuning)**。各 plan 作成時に本 plan と同様に対象ファイルを実測してから書く。
