# v0.3.1 patch release Track 分割 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: 各 PR に着手する時点で `superpowers:writing-plans` を再度回し、その PR 単位の TDD ステップ計画を作ってから `superpowers:subagent-driven-development` で実行する。本計画は **PR 分割と順序制約の確定**までを担い、コードレベルのステップは持たない (2 層構成)。

**Goal:** v0.3.1 で作業する **32 issue を 18 PR に割り付け**、直列制約・ファイル衝突・実機スロットを事前に確定させて、Track A/B/C を安全に並列実行できる状態にする。関係する 36 issue の残り 4 件 (close のみ 1 / 別 repo 転記 1 / deferred 2) も本計画で行き先を確定させ、**「判断待ち」の未割り当てを 0 件にする**。

**Architecture:** [Track 0 spec](../specs/2026-08-05-v031-patch-design.md) の裁定 D1-D12 と根本原因 4 群 (G1-G4) に従う。base は全 PR `develop-0.3.1` (D4)。Track 0 は裁定のみで実装を持たず、skill / doc の実編集は Track B、CI job は Track C が担う。

**Tech Stack:** Python 3.11 / pytest / ruff / pyright、GitHub Actions (`ci.yml` / `pr-checklist.yml` / `security-audit.yml` / `release.yml`)、Node (`check-pr-checklist.js`)、PowerShell + Pester (`build-portable-zip.ps1`)、Tauri 2 + React 19 (GUI)。

## Global Constraints

spec から逐語で持ち込む。**全 PR の要件に暗黙で含まれる。**

- **base ブランチは `develop-0.3.1`** (spec D4)。`release/v0.3.1` 統合ブランチは使わない
- **機能追加を行わない** (Idios 指示)。CLI / GUI の新オプション・新画面は本 release の範囲外
- **cv2 は `opencv-python-headless>=4.8,<5`** (spec D8)。5.x 移行は #951 で deferred
- **CHANGELOG 見出し日付 = タグを打つ日 (JST)** (spec D6)
- **CHANGELOG への追記は `## [Unreleased]` 節へ** (spec D7)。Track A-C は version 見出しを触らない。確定は Track D
- **`docs/release-process.md` §共通項目 は patch にも適用する** (spec D5)
- **新規 spec / plan は markdownlint 対象**。commit 前に `bash scripts/check-markdownlint.sh --fix`。ただし `--fix` は行頭 `#NNN` を見出しに誤変換するので、issue 番号を行頭に置かない
- **PR merge とタグ push と `gh release create` は Idios 専任**。agent は実行しない
- **`git commit` の Co-Authored-By は `Claude Fable 5 <noreply@anthropic.com>`**
- **規約・ガードを新設する PR は G1-1 の 3 点セットを満たす**: ①発火点をファイルと行で指定 ②非実施時の 1 行記録義務 ③**発火側の red 実証** (違反を注入し exit code の生値を観測 + pin test 同梱)
- **gate を足す PR は「この gate が見ていない集合」を PR 本文と docstring に明示列挙する** (G2-0)
- **`.claude/skills/**` を触る PR のうち振る舞いを変えるものは EPT (empirical-prompt-tuning) を適用** (spec D11)。対象は PR-B3 / PR-B4 / PR-C4。文言のみの #856 は skip し根拠を PR 本文に明記
- PR 本文は machine-verified を `[x]`、machine-unverifiable を plain bullet `-` で書き分ける
- **`Closes` / `Fixes` / `Resolves` 禁止** (Iron Law 4)。`Refs #N` を使い、マージ後に手動 close

---

## PR 一覧と順序

```text
Track 0 (完了)  spec + 起票 #945-#953
      │
      ▼
Track A′ ── PR-A1 (#907)  ruff/pyright pin 先行 ★直列★
      │
      ├──────────────┬──────────────┐
      ▼              ▼              ▼
   Track A        Track B        Track C     (並列)
   PR-A2          PR-B1..B8      PR-C1..C7
      │              │              │
      └──────────────┴──────────────┘
                     ▼
              Track D ── PR-D1  version bump + CHANGELOG ★直列★
```

| PR | Track | issue | effort | 実機 | 依存 |
| --- | --- | --- | --- | --- | --- |
| PR-A1 | A′ | #907 | S | — | Track 0 完了後・**他すべてに先行** |
| PR-A2 | A | #916 #863 | L | — | PR-A1 |
| PR-B1 | B | #944 | L | **要** | — |
| PR-B2 | B | #920 #933 #952 | M | — | — |
| PR-B3 | B | #935 #856 #870 | L | — | — (EPT) |
| PR-B4 | B | #945 | M | — | **PR-C1** (EPT) |
| PR-B5 | B | #949 #922 | S | — | — |
| PR-B6 | B | #376 #906 #652 #658 | M | **要** | PR-A2 |
| PR-B7 | B | #864 | M | **要** | 他の detector 変更 PR と並列不可 |
| PR-B8 | B | #865 #913 #882 | S | 一部 | — |
| PR-C1 | C | #936 | M | — | — |
| PR-C2 | C | #947 #876 | M | — | — |
| PR-C3 | C | #946 | M | — | — |
| PR-C4 | C | #948 #918 | L | — | — (EPT) |
| PR-C5 | C | #950 #868 | M | — | PR-A2 (#868 は manifest 形が確定してから) |
| PR-C6 | C | #912 #910 | M | — | — |
| PR-C7 | C | #934 | L | — | — |
| PR-D1 | D | — | M | — | **全 PR マージ後** |

**PR を持たない 4 件**:

- **#923** — 実装済み。`docs/cli-spec.md:379` は既に「N 以下に絞る (上限のみ。実装は `slots[:N]` で、スロット数を増やすことはできない)」と正しく記述されている。**再検証して close するだけ** (`/close-issue`)
- **#326** — 別 repo (`Idios/idios-claudecode-tools`) へ転記して本 repo は close。転記は Idios が行う。**依存: PR-B3 + PR-B4 + PR-C4 の 3 本すべてのマージ後。** spec D12 の順序制約は「skill / hook / CLAUDE.md が固まってから」であり、これを担うのは #945 (PR-B4) / #935 #856 #870 (PR-B3) / **#918 (PR-C4 = Track C)** である。**「Track B 完了後」では #918 を取りこぼす** — #918 は `check_version_consistency.py:268` の `args.tag` 分岐を #948 と共有する都合で Track C へ移してあるため。転記先テンプレートが `/release` skill の旧版を写さないよう、PR-C4 のマージを待つこと
- **#951** — cv2 5.x 移行。**deferred (v0.3.1 範囲外)** のため本 release では作業なし
- **#953** — minimap 実行中の画面離脱で進捗表示を失う。**deferred (v0.3.1 範囲外、Idios 判断 2026-08-05)**。listener を画面遷移を跨いで保持するか復元するかは GUI の挙動変更であり、「機能追加は行わない」方針に照らして本 release では扱わない

**内訳の確認 (割り付け漏れゼロの根拠):** v0.3.1 で作業する issue は **32 件**で、すべて PR-A1〜PR-D1 のいずれかに属する。残る 4 件の内訳は上記のとおり — close のみ 1 (#923) / 別 repo 転記 1 (#326) / deferred 2 (#951 #953)。合計 36 件。**「判断待ち」の未割り当ては 0 件。**

---

## Task PR-A1: ruff / pyright の pin 先行 ★直列・最初★

**issue:** #907 (#916 から切り出し)

**なぜ単独で先行させるか:** lint ツールの版が変わると `ruff format --check .` の結果が **repo 全体で**変わる。Track B / C を並列で走らせている最中に pin を変えると、先行 PR が rebase 時に一斉に赤化する (memory `feedback_ruff_version_drift_md_codeblocks` / `feedback_ruff_format_whole_repo_gate`)。**この PR がマージされるまで他 Track を着手しない。**

**Files:**

- Modify: `pyproject.toml:35-36` (`ruff>=0.4` / `pyright>=1.1` に上限を付与)
- Modify: `docs/developer-setup.md:205` (`pip install -e ".[dev]"` の記述) と同 306-310 (ゲート手順) に「CI と同一版で検証する」旨 + 再 install 手順
- 参照: `scripts/check-markdownlint.sh:22` の `CLI2_VERSION="0.22.1"  # CI のバンドル version と揃える` — markdownlint が既に同型を解いている先例

**Interfaces:**

- Produces: pin された ruff / pyright の版。PR-A2 の `constraints.txt` はこれを取り込む

**受け入れゲート:**

- [ ] `ruff check .` / `ruff format --check .` / `pyright` / `pytest` が緑 (**touched-only ではなく repo 全体**)
- [ ] `pyproject.toml` の ruff / pyright に上限が付いている
- [ ] `docs/developer-setup.md` に再 install 手順が書かれている

**着手時に確認すること:** worktree venv に **pyright が install されていない** (実測)。つまりローカルの型検査は実質存在せず CI だけが型を見ている。pin だけでは直らないので doc への再 install 手順追記が実質必須。

---

## Task PR-A2: 依存 pin の constraints 方針本体

**issue:** #916 (#863 を統合)

**Files:**

- Modify: `pyproject.toml:10-22` (runtime) — `opencv-python-headless>=4.8` に **`,<5` を付与** (D8)、`typer` / `click` の暫定コメント (`:11-16`) を恒久方針へ書き換え
- Modify: `pyproject.toml:33-40` (dev extras) — `rich` / `datamodel-code-generator` / `black` / `isort` を明示宣言 + 上限
- Create: `constraints.txt` (repo 直下。`scripts/installer/requirements-pyinstaller.txt` の冒頭 pin 方針コメント形式を踏襲)
- Modify: `.github/workflows/ci.yml:69` と `:106` — `pip install -e ".[dev]"` → `-c constraints.txt` 付き
- Modify: `.github/workflows/ci.yml:29-30` と `:101-102` — `cache-dependency-path` に `constraints.txt` を追加
- Modify: `docs/l2-workflow.md:983-1009` §外部依存規約 — **pip / pyproject の行を新設** (現在 npm・cargo・binary tarball の行はあるが Python 依存の行が無いのが根本欠落)
- Modify: `docs/developer-setup.md:205`

**Interfaces:**

- Consumes: PR-A1 が pin した ruff / pyright の版
- Produces: `constraints.txt` — PR-C5 (#868) の pip-audit / dependency-review が読む manifest 形

**判断が要る点 (着手時に Idios へ確認):** `scripts/build-portable-zip.ps1:473` の `pip install $RepoRoot --no-cache-dir` に constraints を効かせるか。効かせないと「CI が検証した cv2」と「ZIP に同梱される cv2」が別物という **#916 と同型の穴が配布側に残る** (spec §8.2 O-4)。

**受け入れゲート:**

- [ ] `pip install -e ".[dev]" -c constraints.txt` がローカルと CI の両方で解決する
- [ ] cv2 が 4.x に解決される (`python -c "import cv2; print(cv2.__version__)"` で 4.x を確認)
- [ ] codegen gate (`ci.yml:71-79`) が緑 — dcg + black + isort を固定したことで整形の ping-pong が止まっていること
- [ ] `ruff check .` / `ruff format --check .` / `pyright` / `pytest` 緑

**実機検証:** D8 (cv2 4.x 固定) により **不要**。5.x を選んでいたら GT / bit-exact baseline の再取得が必要だった。

---

## Task PR-B1: 出荷物の誤り 2 件 + 再発防止 CI ★Track B 最優先★

**issue:** #944 / spec §5.2 G2-2・G2-3

**Files:**

- Modify: `scripts/build-portable-zip.ps1:172` の `Format-ReadmeContent` (L232-245 のコマンド例が `split` / `--dry-run` / `--version` の 3 行のみ)
- Modify: `image/03-complete.png` (再撮影。`scripts/capture-readme-screens.mjs` = vite dev + Playwright + sample metadata)
- Create: `scripts/check_feature_announcement.py`
- Create: `scripts/check_screenshot_freshness.py`
- Modify: `.github/workflows/ci.yml` — 既存 `doc-tauri-commands-drift` (`:221`) の直下に job 追加
- Modify: `scripts/capture-readme-screens.mjs` — capture マップを JSON へ切り出し (2 者が同じ表を読む形にする)
- Modify: `README.md` / `docs/quickstart.md` (機能告知)

**#944 本文の読み替え (必須):** issue §5 は「コマンド一覧の正は `allaganeye/cli.py` の `@app.command` 登録とする」と書いているが、**この実装では今回漏れた 2 機能がちょうど検査対象外になる**。`cli.py` の `@app.command` は `:65` / `:292` / `:480` の 3 つ (`split` / `detect` / `debug-brightness`) のみで、`minimap` (`commands/minimap.py:46`) と `export` (`commands/export.py:69`) は `cli.py:650-656` の `register(app)` 経由である。**正は typer runtime registry (`typer.main.get_command(app).commands` を列挙し `hidden=True` を除外) を使う。**

**スクショ陳腐化の実装制約 (必須):** 素朴な `git log -1 --format=%ct` 比較は **squash merge で全滅する**。実測で `image/03-complete.png` の blob は `9544ebe` (2026-05-18) と `aefcb8c` (2026-08-04) で同一 (`96d87e63980cca8caf17b411a1db654aadedcbca`) だが、commit timestamp 比較は 08-04 を返して緑になる。**blob hash の変化点を辿る実装が必須。**

**この gate が見ていない集合 (PR 本文と docstring に明記):**

- キーワード 1 回出現 = 告知とみなすため、README.md の索引リンクや折りたたみ内に `minimap` が 1 度出るだけで pass する
- SSoT 側が人手書式依存 — CHANGELOG の太字にし忘れた機能は機能名集合から消えて検査が黙る (新機能ほど漏れやすい)
- フラグ単位の機能 (`--masked` / `--vtuber` / `--keep-trailing`) は CLI サブコマンド粒度では原理的に捕まらない
- 画面 tsx を触らない子コンポーネント側の変更 (例: `MatchThumb` へのバッジ追加) はスクショ検査の依存に入れ忘れると素通り
- 撮り直した画像が正しい画面・正しい状態を写しているかは検査しない

**受け入れゲート (spec §7.2 の発火実証を含む):**

- [ ] 生成された `README.txt` に minimap / masked / vtuber / export 並列が列挙されている
- [ ] `image/03-complete.png` に「⬦ ミニマップ切抜き」ボタンが写っている
- [ ] SSoT から機能名を 1 件抜いて `check_feature_announcement.py` が **exit 1**、抽出を壊して **exit 2** (fail-closed) — exit code の生値で観測
- [ ] blob 同一・commit 日時のみ新しいケースでスクショ検査が **赤になる** (squash merge の false-green を潰した証拠)
- [ ] `npm run lint` / `typecheck` / `test` / `build` / `cargo check` (GUI を触るため)

**実機検証: 要。** GUI スクショの撮り直し。memory `project_gui_verification_cache_seed` の detection cache seed 手法で短縮できる。

**未検証の残件:** `03-complete.png` に post_match バッジが写っていないのが #805 Phase 2 未反映によるものか、sample metadata に `post_match: true` の match が含まれないだけかが切り分けられていない。撮り直し前に `capture-readme-screens.mjs` が読む sample metadata を 1 回 grep して決着させる。

---

## Task PR-B2: doc 記述 3 件 (output-spec matrix / doc 監査残 / Release body)

**issue:** #920 #933 #952

**まとめる理由:** #920 と #933 は `docs/output-spec.md` の matrix v2 (`:88-113`) という**同一の表**を触る (spec §6.3)。#952 は CHANGELOG の記述を読者視点へ再構成するもので、同じ「doc 記述の質」カテゴリ。

**Files:**

- Modify: `docs/output-spec.md:88-113` — masked / vtuber 系 verbose 出力 4 行を追加し、default / `-v` / `-q` / `--dry-run` / `-v --dry-run` / `-q --dry-run` / `-v -q` の各列を実装のガード条件と逐条突合 (#920)
- Modify: `docs/output-spec.md` — disk 空き容量 warning 行 (#933 §B)
- Modify: `.github/workflows/security-audit.yml:92` の `npm audit --audit-level=high` 閾値の採否判断を記録 (#933 §A)
- Modify: `docs/release-process.md` — **CHANGELOG Added entry の記述規約**を新設 (#952)。「利用者向けの使い方 2-3 行 + spec へのリンク。アルゴリズム段階名・内部識別子 (V0-V4 / quorum / anchor / presence 等) は spec 側に置き CHANGELOG には出さない」
- Modify: `CHANGELOG.md` — `## [Unreleased]` 節を新設し、以降の v0.3.1 entry は上記規約に従って書く (D7)

**#952 の背景:** `scripts/extract_release_notes.py` が CHANGELOG から Release body を生成するため、CHANGELOG の書き方がそのまま GitHub Release の本文になる。v0.3.0 では V0-V4 / quorum / anchor / presence といった内部用語が並び、読者 (FF14 プレイヤー) に届いていなかった (Fable 俯瞰レビュー 2026-08-03 の指摘)。

**v0.3.0 節は書き換えない (Idios 判断 2026-08-05):** D7 の判断理由は「**既リリース済み節を触らせない**」であり、v0.3.0 の Release body は既に公開済みで CHANGELOG を直しても再生成しない限り変わらない。`docs/l2-workflow.md:199` (#854 R2) が dated 記録の遡及書き換えを禁じているのと同じ原則を適用し、**v0.3.0 節は歴史記録として残す**。#952 が生むのは**規約と、それを適用した v0.3.1 の entry** である。

**受け入れゲート:**

- [ ] matrix v2 の各行が実装のガード条件と 1 対 1 で対応している (逐条引用を PR 本文に)
- [ ] `docs/release-process.md` に CHANGELOG Added entry の記述規約がある
- [ ] `CHANGELOG.md` に `## [Unreleased]` 節が存在し、Track A-C の各 PR がそこへ追記できる状態になっている
- [ ] **v0.3.0 節の diff が 0 行** (`git diff origin/develop-0.3.1 -- CHANGELOG.md` に v0.3.0 節の変更が含まれないこと)
- [ ] `bash scripts/check-markdownlint.sh` が 0 error

---

## Task PR-B3: レビュー・ゲート規約 + skill 文言 + triage 入力規約 (EPT)

**issue:** #935 #856 #870

**まとめる理由:** 3 件とも `docs/l2-workflow.md` を触り、#935 P2-1 と #856 item3 は **`:171-185` の同一コードフェンス**を書き換える (spec §6.3)。別 PR にすると確実にコンフリクトする。

**Files:**

- Modify: `docs/l2-workflow.md:178-181` — 固定 focus 3 bullet を「本 PR が新設した外部入力境界 (CLI option / metadata field / GUI 自由入力 / 環境変数) と、それが到達する不可逆操作 (上書き/削除/truncate) を列挙して focus に含める」へ **置換** (#935 P2-1、追加ではなく置換)
- Modify: `.claude/skills/review-pr/eval/requirements.md:173` (P-2) — **#935 P2-1 と同時に置換しないと EPT eval が旧規約を pin して次の skill 改修で復活する**
- Modify: `.claude/skills/review-pr/SKILL.md:341-351` §5c — 「横断クラス root cause は diff 外も対象」「mirror 元を参照する実装を書く/見つけたら mirror 元自身の検証状況を確認する」(#935 P2-2)
- Modify: `docs/l2-workflow.md:334-338` §実機検証 trigger 表 §結果記録 — 手動ゲートの異常観測記録規約 (#935 P2-3)。**`docs/release-process.md` には置かない** (リリース 1 回に 1 度しか読まれず形骸化するため)
- Modify: `docs/output-spec.md:201-` — 「ユーザーに提示するパスは解決済み絶対パス」(#935 P2-4)
- Modify: `CLAUDE.md` — destructive write boundary audit 4 問を **独立 h2 節**として追加 (#935 P3-1。`### バグ修正時の方針` 配下は禁止)
- Modify: `.claude/skills/iterate-review/SKILL.md:63` / `eval/requirements.md:96` / `docs/l2-workflow.md:911` — 「Round summary comment (Step 4)」→「Final summary comment (Step 4)」(#856 item1、3 箇所同時)
- Modify: `.claude/skills/review-pr/SKILL.md:252-268` — Codex fail fallback で step 2 が step 3/4 に優先することを逐語で明示 (#856 item2)
- Modify: `docs/l2-workflow.md:175` — `CLAUDE_PLUGIN_ROOT` の `<version>` に「実行直前に `ls` で実パス解決する」1 行 (#856 item3)
- Modify: `.claude/skills/review-pr/SKILL.md:266` / `eval/requirements.md:158` (I-2) — 「(Codex 用 focus 文字列を流用)」が tier 1 `codex-companion.mjs review` (focus positional を reject) と矛盾する点を解消 (#856 item4)
- Modify: `docs/l2-workflow.md:524-532` §タスク発見 — triage 入力 **4 系統** を実行可能なコマンド付きで明文化 (#870)
- Modify: `docs/issue-policy.md:306-` §7 — #870 の節へ相互参照

**#935 本文の事実誤認 2 件 (実装時に読み替える):**

1. P2-2 の「/review-pr §5c の sweep は当該 PR の diff 内に scope され」は不正確。`review-pr/SKILL.md:345` は既に「repo 全体から hits を抽出」と書いている。実際の欠落は (i) sweep の trigger が「文字列パターンとして表現できる root cause」に限定されていること (破壊操作の述語 / 外部入力の検証 / パス解決規則のような**意味クラス**の sweep が未定義) (ii) mirror 元検証の規約が repo 全体で不在
2. 「released path に入った」も不正確。PR #930 は v0.3.0 タグの**前**に `release/v0.3.0` へ merge されており、欠陥は公開リリースには載っていない。手動ゲート M1 が異常 (パス表示) を観測して発覚した — この事実は P2-3 の根拠をむしろ強める (観測はされたが pass 記録された)

**#870 の acceptance 実証に使える現存違反:** `docs/detection-map.md:140` は今なお「legacy fps filter path (cruft、**別 issue で撤去**)」と番号なしで書かれている。実際には #864 が起票済みだが `grep -n 864 docs/detection-map.md` は 0 hit。入力系統 (4) が検出すべき違反が現在も残っている。

**EPT: 適用する** (spec D11、判断基準の変更を伴うため)。`docs/l2-workflow.md` §skill 改修ワークフロー に従い fresh subagent dispatch + 構造化 reflection を 2 consecutive clears まで回し、結果を PR の Self-Test Report に記録する。

**受け入れゲート:**

- [ ] `grep -rn "Round summary comment"` の living-doc hit が 0 件 (dated plans/specs は対象外)
- [ ] `docs/l2-workflow.md` に triage 入力 4 系統が実行可能なコマンド付きで存在する
- [ ] `CLAUDE.md` の destructive write boundary audit が **h2 独立節**として存在する (`### バグ修正時の方針` 配下ではない)
- [ ] `review-pr/eval/requirements.md:173` (P-2) が #935 P2-1 と同一内容へ更新されている
- [ ] EPT の 2 consecutive clears を PR の Self-Test Report に記録した
- [ ] `bash scripts/check-markdownlint.sh` 0 error

---

## Task PR-B4: fable-consult の発火点新設 + allaganeye- prefix 改名 (EPT)

**issue:** #945 / spec §5.1 G1-2

**依存:** **PR-C1 (#936) の後。** Self-Test Report に Fable 欄を足しても、`check-pr-checklist.js` の scope 拡大が入るまで未記入で CI red にならず、発火実証ができない。

**Files:**

- Modify: `.claude/skills/release/SKILL.md` — Step 0a (`:22-32`) の直後・Step 0b の前に **Step 0a-2「リリース俯瞰レビュー (fable-consult) 必須」** を新設
- Modify: `.claude/skills/review-pr/SKILL.md:234-248` — doc-only PR / spec doc 新規追加 PR での起動条件を追加 (既存 optional Codex review と同形式)
- Rename: `.claude/agents/fable-consult.md` → `.claude/agents/allaganeye-fable-consult.md`
- Modify: `CLAUDE.md:365` (対応表) / `CLAUDE.md:372` (推奨トリガー地点節)
- Modify: `docs/superpowers/specs/2026-07-14-per-use-case-model-routing-design.md:229,231` — **書き換えではなく**「本条項は 2026-08-05 spec G1-2 / #945 で消化済み」の 1 行注記を添える
- Modify: `.github/pull_request_template.md:72-90` — Self-Test Report に Fable 起動欄

**改名 sweep の範囲 (spec §7.3 で確定):** `docs/l2-workflow.md:199` (#854 R2) が「実行済み dated plans/specs 内の表記は historical record であり遡及書き換えを行わない。living doc = CLAUDE.md / l2-workflow / skill / hook / 現行 roadmap のみが整合対象」と定めている。**改名するのは `CLAUDE.md` / `.claude/agents/` / `.claude/skills/` のみ**、`docs/superpowers/{plans,specs}/` は対象外。

**false-green の制約 (skill 本文にも明記する):** `/release` Step 0a は「達成 / 未達成 / **該当なし**」の 3 択である (`.claude/skills/release/SKILL.md:27` 実測)。Step 0a-2 を単に足しただけでは「該当なし」で通過できる。**finding 件数と消化件数の数値記入を required にしない限り no-op。** 出力形式を次のいずれかに固定する:

- 実施: `fable 俯瞰レビュー: 実施 (finding N 件 / 消化 M 件 / 残 K 件 → Track D PR 本文へ転記)` — N / M / K は必須の数値
- 非実施: `fable 俯瞰レビュー: 非実施 (理由: <1 行>)`

**EPT: 適用する** (spec D11)。

**受け入れゲート:**

- [ ] `grep -rn "allaganeye-fable-consult" .claude/skills/` が `release` と `review-pr` の両方で hit する
- [ ] `.claude/agents/fable-consult.md` が存在せず `allaganeye-fable-consult.md` が存在する
- [ ] `grep -rn "fable-consult" CLAUDE.md .claude/` の全 hit が新名を指す (旧名 0 件)
- [ ] Self-Test Report の Fable 欄を未記入にして `validate-checklist` が **red になることを exit code の生値で実証**
- [ ] EPT の 2 consecutive clears を記録した

**着手時の注意:** 新規 agent 定義はセッション開始時にロードされる (memory `project_agents_load_at_session_start`)。改名したセッションでは `allaganeye-fable-consult` を `subagent_type` に指定できない。動作確認は fresh session で行う。

---

## Task PR-B5: Codex review 出力を読む規定 + workflow_dispatch 記述の訂正

**issue:** #949 #922

**Files:**

- Modify: `docs/l2-workflow.md:872-893` §Codex fallback の擬似コード — `result.stdout` / `result.stderr` 依存から **job log 読み**へ改訂
- Modify: `docs/l2-workflow.md:193` — 「`--background` + `run_in_background` で非同期化可」を「review / adversarial-review は常に foreground blocking。非同期化フラグは受理されるが無視される (openai-codex 1.0.4 時点)」へ訂正
- Modify: `.claude/skills/review-pr/SKILL.md` Step 5a (`:236` の直後) / `.claude/skills/iterate-review/SKILL.md` (`:63` の Codex fallback 注記の隣) — job log を読む手順を step 化
- Modify: `docs/release-process.md:80` (+ `:206`) — workflow_dispatch では ZIP artifact が上がらない実態に合わせる (#922)
- Modify: memory `project_codex_adversarial_review_direct_invocation` — `--background` が動くという記述の訂正

**背景 (原因帰属の訂正):** 「出力が末尾しか残らない」のではない。**全文は永続化されている** — `<CLAUDE_PLUGIN_DATA>/state/<slug>-<hash>/jobs/<jobId>.log` に "Final output" として rendered 全文が append される (`tracked-jobs.mjs:179`、実ファイル確認済み)。欠けているのは**読む規定**。新しい保存機構は作らない。

**副次発見の裏取り:** `review` / `adversarial-review` の `--background` と `--wait` は両方 silent no-op。`handleReviewCommand` (`codex-companion.mjs:709`) は無条件に `runForegroundCommand` を呼び、`--background` は `:685` で宣言されるだけで読み出しは `handleTask` (`:758`) のみ。

**耐久性リスク (PR 本文に明記):** plugin 内部実装 (`state.mjs` の path 規約 / `tracked-jobs.mjs` の "Final output" ブロック名 / `state.mjs:13` の `MAX_JOBS = 50` による剪定) への依存が発生し、plugin の version up で silent に壊れる。version 併記 (openai-codex 1.0.4 時点) で緩和する。

**#922 の判断 (着手時に Idios へ確認):** doc を実態に合わせるか、`release.yml` 側を doc に合わせるか (spec §8.2 O-3)。前者なら Track B のまま、後者なら Track C へ移す。

**受け入れゲート:**

- [ ] `docs/l2-workflow.md:193` の `--background` 記述が訂正されている
- [ ] `/review-pr` と `/iterate-review` の両方に job log を読む step がある
- [ ] `docs/release-process.md` の workflow_dispatch 記述が実態と一致する (実際に dispatch して artifact の有無を確認、または release.yml の該当条件を逐条引用)
- [ ] `bash scripts/check-markdownlint.sh` 0 error

---

## Task PR-B6: Python 小修正 4 件

**issue:** #376 #906 #652 #658

**依存:** **PR-A2 の後。** #376 と #863 (PR-A2) は `docs/cli-spec.md:625` の同一行を触る (spec §6.3)。

**Files:**

- Modify: `allaganeye/cli.py:53-55` — `typer.Option("--version", "-V", ...)` に `"-v"` を追加 (#376)
- Modify: `docs/cli-spec.md:17` (グローバルオプション表) と `:611-635` (出力例。`-v` を追加すると `Error: No such option: -v` の例が `-e` 等に変わる)
- Modify: `allaganeye/commands/split_matches.py:2251` — `_capture_regions_from_cache_data(data: dict)` に `*, cache_path: Path | None = None` を追加し `:2284-2287` の warning に復元 (#906)
- Modify: `allaganeye/cli.py` — stdout 書き込みを `allaganeye/detection/progress_emitter.py:92-99` の既存 precedent (`except (OSError, ValueError): pass`) と同じ形で保護 (#652)
- Create: `tests/test_subprocess_encoding_guard.py` — `tests/test_ascii_guard.py:47-48` の `_PROJECT_ROOT` / `_SRC_DIR` パターンを雛形に `allaganeye/**/*.py` を `ast.walk` で走査 (#658)

**#376 の設計論点 (実装時に必ず確認):** サブコマンド側では `-v` が既に verbose である。**トップレベル parser 限定で衝突しない形**になっているかを実測で確認する — `allaganeye -v` が version を出し、`allaganeye split <video> -v` が verbose として動くこと。両方を CLI smoke で観測して PR 本文に貼る。

**#652 の実機検証:** verbose split を実際に `| head` 経由で実行してクラッシュしないことを確認する (mock では再現しない)。

**受け入れゲート:**

- [ ] `allaganeye -v` が version を出力する
- [ ] `allaganeye split <video> -v` が verbose として動作する (トップレベルとサブコマンドで `-v` の意味が衝突していない)
- [ ] `allaganeye split <video> -v | head -5` が OSError 22 を出さない (**実機**)
- [ ] cache corruption warning に `cache_path` が含まれる
- [ ] `tests/test_subprocess_encoding_guard.py` が `encoding=` を欠いた `subprocess.run(text=True)` を注入すると **fail する** (発火実証)
- [ ] `ruff check .` / `ruff format --check .` / `pyright` / `pytest` 緑

---

## Task PR-B7: detect legacy fps filter path の撤去 ★実機 baseline gate★

**issue:** #864

**並列制約:** **他の `detector.py` / `gpu_detector.py` 変更 PR と並列させない。** baseline gate の帰属が曖昧になる。他 Track が落ち着いてから着手し、detect の baseline gate をまとめて 1 回回す (GPU 検証回数の面で有利)。

**Files:**

- Modify: `allaganeye/video/detector.py:2576-2600` (`_use_legacy_fps_filter()`) と前置コメント (`:2568-2574`)
- Modify: `allaganeye/video/detector.py:1446-1520` (`_decode_chunk_cpu_legacy`)
- Modify: `allaganeye/video/gpu_detector.py` の対応箇所
- Modify: `CLAUDE.md` — `ALLAGANEYE_DETECT_FPS_FILTER=1` の記述 (transitional と書かれている箇所) を削除
- Modify: `docs/detection-map.md:61,140` — 「別 issue で撤去」「v0.3.x で削除予定」を実態に合わせる (**#870 の acceptance 実証にも使える**)
- Modify: `docs/testing-guide.md` §baseline drift の判定 / `docs/video-processing.md` §ffmpeg fps filter の version 依存制約

**着手前に必須:** `grep -rn "ALLAGANEYE_DETECT_FPS_FILTER"` で参照箇所を**全件列挙**し、PR 本文に貼る。

**受け入れゲート:**

- [ ] `grep -rn "ALLAGANEYE_DETECT_FPS_FILTER"` が 0 hit (テストの negative assertion を除く)
- [ ] **detect baseline gate が緑** (`pytest -m slow_detect`)。実行前後の HEAD / tree / blob を guard として記録する (memory `feedback_worktree_branch_flip_invalidates_gates`)
- [ ] `ruff check .` / `ruff format --check .` / `pyright` / `pytest` 緑

**実行方法:** 長時間 GPU job は `Start-Process -WindowStyle Hidden` で独立起動する (memory `feedback_long_gpu_job_detached_execution`。harness の background Bash は無人放置でセッション死と共に kill される)。worktree CLI は `ALLAGANEYE_INTEGRITY_SKIP=1` が必要。

---

## Task PR-B8: doc SSoT 3 件 (AUDIO_FROZEN / scorebar 定数表 / 検証データ台帳)

**issue:** #865 #913 #882

**Files:**

- Modify: `allaganeye/audio/__init__.py:48` 付近のコメント + `CLAUDE.md` §音声昇格 — **「凍結継続」を明文化** (#865、Idios 合意済み)
- Modify: `docs/scorebar-detection-design.md:69-73` (「閾値の根拠」3 行) と `:109-117` (「閾値定数 (V2 動的検出)」7 行) — 各行を (a) 参照化 / (b) 現状維持 / (c) 仕様主張と実測記録 に分類し、**rationale 列のみ残して実装を正にする** (#913)
- Modify: `tests/baselines/source-videos.sha256.json` 周辺の doc — 第 3 系統の台帳照合結果 (#882)

**#913 の注意:** issue 本文は突合先を `scorebar.py` と誤記している。**実際の定数は `detector.py` 側**にある。

**#882 の分担:** **物理作業 (ハード選定・購入・コピー) は Idios 本人。** agent 側は台帳 (`tests/baselines/source-videos.sha256.json` = 48 file / 632.1 GiB) の照合と doc 更新のみ。物理作業を release 判定から外す (spec §8.1 R-6)。

**受け入れゲート:**

- [ ] `CLAUDE.md` に AUDIO_FROZEN の凍結継続方針が明文化されている
- [ ] `docs/scorebar-detection-design.md` の定数表から実装値の複製が消え、rationale 列が残っている
- [ ] 台帳の照合結果が doc に記録されている
- [ ] `bash scripts/check-markdownlint.sh` 0 error

---

## Task PR-C1: Self-Test Report の CI 強制

**issue:** #936 / spec §5.1 G1-4

**PR-B4 (#945) の前提。** これがないと Fable 欄の発火実証ができない。

**Files:**

- Modify: `.github/scripts/check-pr-checklist.js:26` — `stripped.split(/^##\s+/m)` → `/^#{2,4}\s+/m`
- Modify: `.github/scripts/check-pr-checklist.js:31` — heading filter に `Self-Test Report` を **prefix match** で追加
- Modify: `.github/scripts/check-pr-checklist.test.js:45` — pin test を反転

**3 点セットで初めて発火する (これを外すと no-op):**

1. `split` を `/^#{2,4}\s+/m` へ緩める
2. heading filter に `Self-Test Report` を **prefix match** で追加 — 実際の heading は `#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)` と括弧書きが付くため `\s*$` の完全一致では拾えない
3. pin test の反転

**実測で再現確認済み:** 受け入れ条件を `[x]` で埋め `#### Self-Test Report` に `- [ ]` を 3 件置いた本文を `countAcceptanceCriteriaCheckboxes` に渡すと `{"unchecked":0,"checked":1,"hasAnySection":true}` を返し **CI pass** する。

**blast radius (D9):** テンプレートの `- [ ]` は実測で計 22 box (受け入れ条件 2 / Iron Law 1 が 2 / Iron Law 3 が 2 / Iron Law 4 が 1 / Self-Test Report 10 / 関連ドキュメント 5)。split を緩めても heading filter が完全一致のままなので、**Iron Law 1/3/4 と関連ドキュメントの 4 群・10 box はカウント対象にならない**。新規に required になるのは **Self-Test Report の 10 box のみ**。`## 受け入れ条件` 節内に h3/h4 は無いので既存 gate の縮小も起きない。

**文書側:** (a) を採るので `docs/l2-workflow.md` L140 / L287 / L345 / L349 / L353 / L359 / L362 と `.github/pull_request_template.md` L72 / L77 / L78 の主張は**正しくなる**ため書き換え不要。正しい記述 (`template` L58 / L103 / L106、`l2-workflow.md:208`) は事実なので触らない。

**#935 との相互作用:** (a) を採ると `docs/l2-workflow.md:287` の「(C) 強制 skip (Self-Test Report の `[ ]` を残し validate-checklist で fail させる)」が**初めて実際に CI red を生む経路**になる。PR-B3 の #935 P2-3 と作用が重なるので、両 PR の内容を相互参照する。

**受け入れゲート:**

- [ ] Self-Test Report に `- [ ]` を 1 件残した PR body で `check-pr-checklist.js` が **非ゼロ exit** (実注入で確認)
- [ ] Iron Law 1/3/4 群に `- [ ]` を残しても pass することを **pin test で固定** (D9 の範囲を回帰から守る)
- [ ] 括弧書き付き heading が prefix match で拾われることを test で固定
- [ ] `node --test` (`.github/workflows/check-pr-checklist-test.yml`) が緑

---

## Task PR-C2: CI trigger の穴 + required status checks + Pester retry

**issue:** #947 #876

**まとめる理由:** 両方 `.github/workflows/ci.yml` を触る。

**Files:**

- Modify: `.github/workflows/ci.yml:13` — `pull_request.branches` に `release/*` を追加。**`push.branches` (`:11`) は触らない**
- Modify: `.github/workflows/markdownlint.yml:5` — 同様
- Modify: `.github/workflows/ci.yml:264-282` — `installer-pester` job の "Install Pester v5" step (`:269-274`) に retry (#876)
- Modify: `docs/release-process.md:90` — ruleset で required status checks を強制した旨を追記して SSoT 化
- GitHub 設定 (repo 外): `refs/heads/main` + `refs/heads/release/*` に required_status_checks を ruleset で宣言 (python / gui-frontend / gui-rust / installer-pester / markdownlint)

**二重起動の検証結果 (PR 本文に転記):** `pull_request.branches` のみに追加する限り**二重起動は発生しない**。`push.branches` にも足すと、`release/*` → main の PR は release ブランチの生存期間ずっと open なので同一 commit に対し push run (`github.ref=refs/heads/release/vX`) と pull_request run (`github.ref=refs/pull/N/merge`) の 2 本が起動する。concurrency group は `ci-${{ github.workflow }}-${{ github.ref }}` (`ci.yml:18`) で ref を含むため**別 group となり dedupe されない**。windows runner を含む full CI が丸ごと 2 倍走る。

**順序:** ci.yml 修正 → required status checks の順で入れる。逆にすると check が never-reported のままマージ不能になる。

**この gate が見ていない集合 (必須記載):**

- **v0.3.1 では 1 度も発火しない。** D4 により `release/*` base の PR が存在しないため、これは次の minor release のための予防措置である
- #876 の Pester retry は**正常時に永久に不発**

**受け入れゲート (発火実証):**

- [ ] base=`release/*` の**捨て PR を 1 本作り**、`ci.yml` が起動することを確認 (**これが唯一の red 実証手段**)。確認後にその PR を close
- [ ] 同一 commit に対し push run と pull_request run が二重に走っていないことを Actions 画面で確認
- [ ] 存在しないモジュール名を流して Pester retry が**発火する**ことを確認 (#876)
- [ ] required status checks を設定した後、通常の PR がマージ可能なままであること

---

## Task PR-C3: Pre-flight 鮮度の機械検証

**issue:** #946 / spec §5.4 G4-1

**Files:**

- Modify: `.github/pull_request_template.md:55-70` §ベース同期確認 — 宣言フィールド 2 件を追加 (`Pre-flight 時点の同 issue open PR` / `同 base open PR`)
- Create: `.github/scripts/check-preflight-freshness.js`
- Modify: `.github/workflows/pr-checklist.yml` — job を追加。`permissions: pull-requests: read` を明示宣言する (現在 `permissions:` ブロック自体が無い)
- Modify: `docs/l2-workflow.md:208` — 「plain bullet は CI ゲート増設なし」を改訂
- Modify: `.github/pull_request_template.md:58` — 同趣旨のコメントも同時改訂

**設計制約 (最重要。落とすと実装者が OID 比較だけ入れて「対策済み」にする):** PR #939 の 66 分間、`release/v0.3.0` の HEAD は **1 度も動いていない** (#930/#931/#932 の merge は 12:34 UTC、次は #938 の 14:21 UTC)。**「base OID 一致比較」は本件に対し false-green。** 検出できるのは **open-PR 集合の再サンプリング**のみ。

**配置先の制約:** `ci.yml` に置くと `pull_request: branches: [main, "develop-*"]` (`:12-13`) の filter で `release/*` base の PR では **1 job も起動せず完全な no-op** になる。**必ず branch filter を持たない `pr-checklist.yml` (`on: pull_request: types: [opened, edited, synchronize]`) 側に置く。**

**この gate が見ていない集合 (必須記載):**

- 宣言フィールドは自己申告なので後から書けば緑になる。ただし宣言した時点で見落としでは無くなるので、握り潰しには PR body の改竄が必要 = **監査可能**
- `GITHUB_TOKEN` の権限や rate limit で `gh pr list` が落ちた場合、fail-open にすると常時 no-op、fail-closed にすると network 不調で全 PR がブロックされる。**fail-closed + 明示的な retry** を採る
- `Refs` 記法の揺れ (`Refs #862` / `#862` / issue 番号を持たない release PR) で search key を取り違えると偽陽性・偽陰性の両方が出る

**hook 案を採らない理由 (PR 本文に転記):** `PreToolUse` で `gh pr create` を intercept する案には bypass が 4 経路ある — `ALLAGANEYE_PREUSE_BYPASS=1` (`preuse.py:77`) / `settings.local.json` の `pretooluse_gate: false` (`:334`) / `tool_name != "Bash"` の無条件 allow (`:426`、gh MCP / web UI / `gh api` POST 経由) / OID 比較の false-green。

**受け入れゲート:**

- [ ] 宣言に無い open PR を作って job が **fail する** (exit code の生値で観測)
- [ ] 宣言集合と実集合が一致するケースで green (false-red が出ない)
- [ ] `gh pr list` 失敗時に fail-closed になることを test で固定
- [ ] job が `pr-checklist.yml` にあり `ci.yml` には無い
- [ ] 検査が open-PR 集合の差分で行われ、base OID 一致比較**のみ**の実装になっていない

---

## Task PR-C4: CHANGELOG 見出し日付の規約と検査 + /release 手順 (EPT)

**issue:** #948 #918

**まとめる理由:** #918 item3 (バンプ方向チェック) と #948 は `scripts/check_version_consistency.py:268` の**同じ `args.tag` 分岐**に新フラグと検証を追加する (spec §6.3、実測確認済み)。

**Files:**

- Modify: `docs/release-process.md:67-81` §タグ運用 — 「CHANGELOG 見出し日付 = タグを打つ日 (JST)」を 1 行で定義 (D6)
- Modify: `docs/release-process.md:92` — §共通項目 のチェックリスト項目を「対象バージョンセクションが存在 (日付 = タグ打ち日 JST / 主要変更点 / breaking changes)」へ具体化
- Modify: `docs/release-process.md:85,87` — 「各 minor リリース」「全 minor リリース」を「各リリース (minor / patch)」へ (**D5。これを先にやらないと patch の v0.3.1 で §共通項目 が 1 度も読まれない**)
- Modify: `scripts/check_version_consistency.py` — `_check_changelog_heading(repo_root, expected_version, reference_date)` を追加。`--tag` 指定時のみ発火。`--changelog-date-from <ISO8601>` を CLI 引数で受ける
- Modify: `.github/workflows/release.yml:98-106` — `${{ github.event.head_commit.timestamp }}` を渡す
- Modify: `scripts/extract_release_notes.py:13` — regex を日付必須へ厳格化
- Create: `tests/scripts/test_extract_release_notes.py` (現在この script には対応テストが存在しない)
- Modify: `tests/scripts/test_check_version_consistency.py` — 赤テスト先行 + TZ の pin test
- Modify: `.claude/skills/release/SKILL.md:199-205` — §タグ打ち・GitHub Release 作成 の直前に「見出し日付を当日に更新して commit する」手順を追加 (**現在 skill 全体で `changelog` の grep hit が 0 件**で、`docs/release-process.md:81` の「skill は CHANGELOG 更新の支援に使う」が実体を伴っていない乖離も同時に解消)
- Modify: `.claude/skills/release/SKILL.md:109-111` — `develop-<新バージョン>` の作成タイミングを明記 (#918 item1)
- Modify: `.claude/skills/release/SKILL.md` — dangling Step 1 参照の解消 (#918 item2)、`:205` の廃止済み手順 (#918 item4)
- Modify: `.claude/skills/release/eval/requirements.md:18` — **A-5 が廃止済み手順を pin しているため同時更新が必須**
- Modify: `.claude/skills/release/eval/requirements.md:24` — シナリオ B が「patch release v0.3.1、deferred 5 件」を前提にしている (実際は 64 件)。**更新しないと次の EPT で旧前提が復活する** (spec §8.2 O-7)

**タイムゾーンが最大リスク:** GitHub Actions runner は既定 UTC。**過去 4 タグ中 2 件 (v0.1.1 02:55 JST / v0.2.1 08:43 JST) で JST 日付と UTC 日付が 1 日ずれる。** naive 実装は 50% の確率で false-red を出し、リリース当日にタグを打ち直す羽目になる。

- 比較前に `zoneinfo` で `Asia/Tokyo` へ**明示変換**する。ハードコードした TZ を docstring と `docs/release-process.md` に規約として明記
- **JST 深夜値を流して赤/緑の両方を観測する pin test を同梱する**

**Track D の critical path:** 本ガードは Track D で初めて発火する。TZ バグがあると**リリース当日に直列最後の PR が止まる** (spec §8.1 R-2)。

**未検証の前提 (実装時に決着):** annotated tag object の `taggerdate` が `version-check` job (`release.yml:87` の `actions/checkout@v4`、既定 `fetch-depth: 1`) の checkout 後に読めるか (spec §8.2 O-6)。読めない場合は `github.event.head_commit.timestamp` が唯一の基準日になる。

**EPT: 適用する** (`/release` skill の手順変更を伴うため)。

**受け入れゲート:**

- [ ] `docs/release-process.md` §タグ運用 に日付規約が 1 行で存在する
- [ ] `docs/release-process.md:85,87` が「各リリース (minor / patch)」になっている
- [ ] 偽の日付を注入して `check_version_consistency.py --tag` が **非ゼロ exit** (exit code の生値で観測)
- [ ] **JST 深夜 (00:00-09:00 JST) のタグ timestamp で false-red が出ない**ことを pin test で確認
- [ ] `tests/scripts/test_extract_release_notes.py` が存在し、日付なし CHANGELOG で `SystemExit` することを assert
- [ ] `.claude/skills/release/eval/requirements.md` の A-5 とシナリオ B が更新されている
- [ ] EPT の 2 consecutive clears を記録した

---

## Task PR-C5: security 再チェック gate + Python manifest の paths 追加

**issue:** #950 #868

**依存:** PR-A2 の後 (#868 は pip-audit / dependency-review が読む manifest の形が確定してから配線する)。

**Files:**

- Modify: `.github/workflows/security-audit.yml:5-11` — `pull_request.paths` に `pyproject.toml` (+ `constraints.txt`) を追加
- Modify: `.github/workflows/security-audit.yml:3-11` — `schedule: cron` を追加
- Modify: `.claude/skills/release/SKILL.md` — Step 3 とタグ打ちの間に security 再チェック Step を挿入
- Modify: `docs/release-process.md:87-93` §共通項目 — security 項目を 1 行追加 (現在ゼロ)
- Modify: `docs/ci-security-audit.md` — dependabot.yml の導入可否と根拠 / 見送る場合の手動 bump 周期

**#868 の本当の穴 (issue 本文に書かれていない):** `security-audit.yml` の `pull_request.paths` は `gui/src-tauri/Cargo.lock` / `Cargo.toml` / `gui/package-lock.json` / `gui/package.json` / `security-audit.yml` の 5 つだけで **`pyproject.toml` が入っていない**。Python 依存だけを変更する PR ではこの workflow 自体が起動せず、pip の advisory は PR 段階でまったく検査されていない。**この 1 行の抜けを塞ぐのが最小コストの決着。**

**headroom 検出器は作らない (PR 本文に理由を明記):** undici の新規 5 件の範囲は `>= 7.0.0, < 7.29.0` なので「境界ちょうどだから再 open した」という因果は成立しない。7.28.0 に余裕があっても該当した。さらに undici 7.29.0 / vite 8.0.16 / serde_with 3.21.0 は**現在 3 件とも headroom ゼロ**で上げ先が物理的に存在せず、fail 型にすると導入初日から解消不能な恒久 red になる。

**実装前に決着が必要 (spec §8.2 O-1):** `gh api "repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=all&per_page=100"` が HTTP 200 + 空配列を返す理由 (token に `security_events` scope が無いのか、release merge 後に全件 close されたのか)。**再チェック Step がこの API に依拠するため、切り分けてから実装する。**

**この gate が見ていない集合 (必須記載):**

- 再チェックからタグ push までの窓は 0 にできない (実測 約 7 時間)
- Dependabot alert は既定ブランチしか scan しないため release 期間中は stale な状態を読む
- cron 間隔以内でしか検知できない (daily なら最悪 24h 遅延)

**受け入れゲート:**

- [ ] `pyproject.toml` だけを変更する PR で `security-audit.yml` が起動する (**実際にそういう PR を作って確認**)
- [ ] `docs/release-process.md` §共通項目 に security 項目がある
- [ ] `/release` にタグ打ち直前の再チェック Step がある
- [ ] dependabot.yml の導入可否が根拠付きで `docs/ci-security-audit.md` に記録されている

---

## Task PR-C6: doc → code 参照 guard の統合

**issue:** #912 #910

**まとめる理由:** 両者とも「doc → code 参照が silent に壊れるのを CI で検知する」同型の guard。**1 script / 1 job にまとめると重複が減る** (順序制約はない)。

**Files:**

- Create: `scripts/check_doc_code_refs.py` (両者を統合)
- Modify: `.github/workflows/ci.yml` — 既存 doc drift job 群 (`:221` / `:244`) の隣に job 追加
- Modify: `docs/system-architecture.md:72` — GUI→CLI 網羅宣言に enforcement を紐づける (#912)
- Modify: `docs/ui-interaction-spec.md` — 残りの参照 guard 対象 (#910)

**#910 の状況 (着手前に確認):** **AC-1 (行番号 anchor の全廃) は PR #932 で完了済み。** v0.3.0 tip の `docs/ui-interaction-spec.md` に `.tsx:NNN` 系 anchor は 0 件、`#L<行番号>` fragment も 0 件で、`[File.tsx]` 形式の名前参照に置き換わっている。**残りは参照 guard の CI 化のみ。** #944 との順序制約も不要 (実測で確認済み)。

**この gate が見ていない集合:** 参照先が存在することしか見ず、記述内容の正しさは見ない。

**受け入れゲート:**

- [ ] doc から存在しない symbol / file を参照する行を注入して job が **fail する** (発火実証)
- [ ] `docs/system-architecture.md:72` の網羅宣言が CI で検査されている
- [ ] `ruff check .` / `ruff format --check .` / `pyright` / `pytest` 緑

---

## Task PR-C7: path / schema 契約の機械検査化

**issue:** #934 / spec §5.2 G2-5

**Files:**

- Modify: `schemas/metadata.schema.json` — 「JSON Schema で表現できない散文契約」を実測で 7 件棚卸し (`:23` source=絶対パス / `:43` detected_at / `:48` detection_started_at / `:53` 等)
- Create: 契約検査のテスト
- Modify: `docs/output-spec.md:201-` — 「ユーザーに提示するパスは解決済み絶対パス」の契約記述 (PR-B3 の #935 P2-4 と重複するので **PR-B3 側に寄せ、本 PR では検査のみ**)

**#372 との関係:** #372 (metadata.json と cache の source パス形式統一) は前セッションで close 済み。**本 PR はその解消状態を pin する場所でもある。**

**この gate が見ていない集合:** 散文契約の棚卸しが人手なので、棚卸し漏れは構造的に検査外。棚卸しした 7 件を docstring に列挙し、「これ以外は未検査」と明記する。

**受け入れゲート:**

- [ ] 7 件の散文契約それぞれについて、違反する metadata を注入してテストが **fail する** (発火実証)
- [ ] #372 が解消した状態 (source パス形式の統一) が pin されている
- [ ] `ruff check .` / `ruff format --check .` / `pyright` / `pytest` 緑

---

## Task PR-D1: version bump + CHANGELOG 確定 ★直列・最後★

**依存:** **全 PR マージ後。**

**Files (6 ファイル 7 フィールド、正は `scripts/check_version_consistency.py:62-100` の `VERSION_LOCATIONS`):**

| path | フィールド |
| --- | --- |
| `pyproject.toml` | `project.version` |
| `gui/src-tauri/tauri.conf.json` | `version` |
| `gui/src-tauri/Cargo.toml` | `package.version` |
| `gui/package.json` | `version` |
| `gui/package-lock.json` | `version` と `packages[""].version` (**2 フィールド**) |
| `gui/src-tauri/Cargo.lock` | `[[package]] name="allaganeye-gui"` の `version` |

- Modify: `CHANGELOG.md` — `## [Unreleased]` を `## [0.3.1] - <タグ打ち日 JST>` へ確定 (D6 / D7)

**注意:** `.claude/skills/release/SKILL.md:133` が「一括置換禁止・ピンポイント編集」を明記している。

**critical path:** Track D は `check_version_consistency.py --tag` を必ず通るため、**PR-C4 で入れた CHANGELOG 日付ガードと #918 item3 のバンプ方向チェックの両方が Track D の critical path 上にある**。PR-C4 の TZ pin test が緑であることを Track D 着手前に再確認する。

**受け入れゲート:**

- [ ] `python scripts/check_version_consistency.py` が exit 0
- [ ] `python scripts/check_version_consistency.py --tag v0.3.1` が exit 0
- [ ] CHANGELOG `## [0.3.1] - YYYY-MM-DD` の日付がタグ打ち日 (JST) と一致
- [ ] spec §7.2 の発火実証リスト 8 項目が全て消化済み (各 PR の本文にリンク)
- [ ] `/release` Step 0a の受け入れゲートが全項目「達成」

---

## 実機・長時間検証スロット表

Idios の実機は 1 台なので、**Track が違っても物理的に直列**。

| 順 | PR | 検証内容 | 目安 |
| --- | --- | --- | --- |
| 1 | PR-B1 | GUI スクショ撮り直し (`capture-readme-screens.mjs`) | 短時間。cache seed で短縮可 |
| 2 | PR-B6 | `allaganeye split -v \| head` の pipe 経由 CLI smoke | 数分 |
| 3 | PR-B7 | detect baseline gate (`pytest -m slow_detect`) | **数時間。detached 実行必須** |
| — | PR-B8 | #882 の物理作業 (ハード選定・購入・コピー) | **Idios 本人。release 判定から外す** |

PR-B7 は他の `detector.py` 変更 PR と並列させない。**PR-B6 と PR-B7 を同一スロットにまとめると GPU 検証回数を 1 回減らせる。**

---

## 並列度の上限

**PR merge は Idios 専任** (memory `feedback_pr_merge_idios_only`、deny ルールで物理ブロック済み)。Track A / B / C を並列で走らせても merge は 1 人の直列作業になる。同時 open PR は **4-5 本**を上限の目安にする。

---

## 関連

- spec: [`2026-08-05-v031-patch-design.md`](../specs/2026-08-05-v031-patch-design.md)
- Track 構造: [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- 前例: [v0.2.1 Track 0 spec](../specs/2026-05-17-v020-v021-retro-codex-integration-design.md) (4 Lane / 約 14 PR)
