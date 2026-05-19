# issue #789 / #790 release.yml doc 整合性 + retrospective 追補 設計書

作成: 2026-05-19 / focused-ritchie-804caa

## 1. 背景

PR #788 (`fix(workflow): #786 release.yml phantom run を defaults.run.shell で解消`) の `/iterate-review` Round 1 で挙がった 2 件の deferred finding を、それぞれ別 issue (#789 / #790) として起票し、本 PR で bundled 対応する。両 issue とも doc only / P3-low / 機能影響ゼロ。

- **#789** `[doc] release.yml の shell 指定戦略を実装内コメントで明示化`
  - 起源: PR #788 Round 1 Finding 2
  - 課題: `build-windows` job が `defaults.run.shell: ${{ matrix.shell }}` を使い、`version-check` / `release` job が step 個別 `shell: bash` を使う、という使い分けに実装内コメントが無い。将来の編集者が PR #788 履歴を遡らないと理由を読み解けない
- **#790** `[doc] PR #775 R3-1 訂正の知見更新 (#786 で root cause 判明)`
  - 起源: PR #788 Round 1 Finding 4
  - 課題: PR #775 期間中に出した「main paths filter で gating」R3-1 訂正仮説が誤りだったことが PR #786 → #788 で確定したが、`release.yml` L28-34 inline コメントと retrospective spec doc に retrospective 記録が残っていない。将来 phantom run 類似事象が発生した時に誤った原因仮説を辿るリスク

## 2. 範囲・非範囲

### 範囲

1. `.github/workflows/release.yml` L28-34 R3-1 訂正 inline comment 末尾に retrospective note (3-4 行) を追加 (#790)
2. `.github/workflows/release.yml` build-windows job の `defaults.run.shell` 直上に shell 戦略コメント (5 行) を追加 (#789)
3. `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` に新規 section §9「v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)」を追加 (~30-40 行、§8「関連リンク」の前に挿入) (#790)
4. (任意 / PR 外) `C:\Users\idios\.claude\projects\.../memory/feedback_github_actions_step_shell_matrix.md` を新規作成 + MEMORY.md に index 行追記 (#790)

### 非範囲

- `release.yml` の機能変更 (jobs / steps / triggers / matrix 構造の変更は一切無し)
- `version-check` / `release` job の `shell: bash` step (L82 / L403 / L410) への touch
- `docs/l2-workflow.md` への lesson 追記 (grep で関連記述 0 件、本 issue scope 外。横展開教訓を doc 化したい場合は別 issue で起票)
- `CLAUDE.md` への lesson 追記 (同上、別 issue 対象)
- Python / GUI / cargo / installer 機能 file の touch
- 機能テスト追加 (doc only のため不要)
- memory file の git commit (memory は project tree 外、PR 外で別操作)

## 3. 設計

### 3.1 アーキテクチャ概要

doc-only PR。物理 file touch:

| File | 内容 | issue | 行数増減 |
| --- | --- | --- | --- |
| `.github/workflows/release.yml` (L28-34 末尾) | R3-1 訂正 inline comment に retrospective note 追加 | #790 | +3-4 行 |
| `.github/workflows/release.yml` (L112 直前) | build-windows shell 戦略コメント追加 | #789 | +5-6 行 |
| `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` (§9 新設) | post-spec retrospective section | #790 | +30-40 行 |
| memory `feedback_github_actions_step_shell_matrix.md` (新規) + MEMORY.md (1 行) | shell × matrix 不互換 lesson learned (PR 外) | #790 任意 | +20 行 / +1 行 |

機能 file (`allaganeye/**`, `gui/**`, `scripts/**`) は **一切 touch しない**。

### 3.2 release.yml #790 用 retrospective note (L28-34 末尾追記)

現状 L28-34 (= PR #775 / PR #788 から不変):

```yaml
  # R3-1 訂正 (重要): R2 fix の empirical 検証は **post-merge (develop-0.3.0 → main
  # 反映) 以降の future push で初めて可能**。本 PR 期間中は GitHub Actions が
  # `push.paths` filter を default branch (main) の workflow 定義で評価する known
  # behavior により、main の release.yml が旧 paths filter を保持している間は claude/*
  # push の phantom run 作成は継続する (commit 2d17747 push 自体が phantom run
  # 25985396510 を作成した事実で実証)。defense-in-depth `if:` 条件は phantom run の
  # 0 jobs 維持 (= conclusion=failure だが functional 影響ゼロ) を担保。
```

直下に retrospective note 追加 (修正案):

```yaml
  #
  # Retrospective (issue #786 / PR #788): 上記 R3-1 訂正の「main paths filter で
  # gating」仮説は **誤り** だった。真の root cause = `shell: ${{ matrix.shell }}` が
  # GitHub Actions schema-invalid (`jobs.<job_id>.steps[*].shell` field は matrix
  # context をサポートしない、公式 context availability table 参照)。Codex
  # /codex:rescue (agentId a9a21c7545477c99c) で独立調査により確定。PR #788 で
  # `build-windows.defaults.run.shell: ${{ matrix.shell }}` 移行 + step 個別
  # `shell: ${{ matrix.shell }}` 削除 (9 箇所) により解消。R2 fix の paths filter
  # 撤去自体は別目的 (push trigger を strict 判定にして無関係 path push の run 抑止)
  # で benefit があるため維持しているが、phantom run の真因ではなかった。詳細は
  # PR #786 / #788 / docs/superpowers/specs/2026-05-17-...-design.md §9 を参照。
```

設計判断:

- 既存 L28-34 を **書き換えない**。"訂正の訂正" として末尾追記することで、PR #775 期間中の R3-1 仮説と PR #788 post-merge の真因確定の **両方を時系列で残す**
- R2 fix (paths filter 撤去) は別目的 (strict trigger) で残す。retrospective note でその文脈を明示
- agentId / PR 番号 / spec doc §9 への cross-reference を含め、横展開教訓を辿れるようにする

### 3.3 release.yml #789 用 shell 戦略コメント (L112 直前に挿入)

現状 L102-117 (PR #788 で確定した form):

```yaml
  build-windows:
    needs: version-check
    runs-on: windows-latest
    # M1 (Refs spec L-α, Refs #737): PS 7+ (pwsh) と PS 5.1 (powershell) を dual matrix で実行。
    # PS 5.1 silent regression (F1 #729 BOM 系) を CI で検出する。
    # upload-artifact は pwsh のみ (matrix.shell == 'pwsh' で gate)、PS 5.1 は smoke-test 専用。
    strategy:
      fail-fast: false
      matrix:
        shell: [pwsh, powershell]
    name: build-windows (${{ matrix.shell }})
    defaults:
      run:
        shell: ${{ matrix.shell }}
```

L112 (`name: build-windows (${{ matrix.shell }})`) と L113 (`defaults:`) の間に 5-6 行コメント挿入 (実際の release.yml では 4 空白インデント):

```yaml
    name: build-windows (${{ matrix.shell }})
    # build-windows job は matrix.shell (pwsh / powershell dual matrix) を
    # `defaults.run.shell` 経由で適用する。GitHub Actions schema 仕様で
    # `jobs.<job_id>.steps[*].shell` field は matrix context をサポートしない
    # ため (PR #788 / issue #786 で確定)、step 個別の `shell:` 指定では matrix.shell
    # を展開できない。`defaults.run.shell` field は matrix context 参照可能。
    # version-check / release job は ubuntu-latest 上で意図的に `shell: bash`
    # を step 個別指定しているが、これは shell variation 不要なため。
    defaults:
      run:
        shell: ${{ matrix.shell }}
```

設計判断:

- 既存 L106-108 (M1 dual-matrix の理由コメント) と **別 block** で配置。M1 dual-matrix は「なぜ pwsh と powershell の両方走らせるか」、本 block は「なぜ defaults.run で matrix.shell を展開するか」と関心が違う
- 「step 個別の `shell:` 指定では展開できない理由」を schema 仕様レベルで明示し、`version-check` / `release` job の `shell: bash` literal 残存の理由 (= ubuntu-latest 上で shell variation 不要) も同時に説明

### 3.4 retrospective spec doc §9 追補 (~30-40 行)

挿入位置: `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` の **末尾** (現状 L612 が file 末尾、L599 が「## 8. 関連リンク」見出し) に新規 section `## 9. v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)` を追加。§8 の **後ろ** = spec doc 最後尾に配置することで、time series 順 (本来の spec → 関連リンク → post-spec retrospective) で読める構造を維持。

content (本 spec doc の §3.4 として参照):

```markdown
## 9. v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)

本節は本 spec doc 確定 (2026-05-17) 後に PR #775 → issue #786 → PR #788 の
ループで判明した release.yml phantom run の真因と、本 spec doc の Risk Register
(§7.1) R3 とは独立した「R3-1 訂正の訂正」を retrospective として記録する。

### 9.1 経緯

- PR #775 (本 spec doc を produce した PR) で release.yml の paths filter 撤去 (R2 fix)
  + 各 job entry に `if:` gating を追加 (Round 1 Finding 3 fix)
- PR #775 期間中 (`/iterate-review` Round 2 → Round 3) に「`push.paths` filter は
  default branch (main) の workflow 定義で評価される known behavior があるため、
  R2 fix の empirical 検証は post-merge 以降の future push でしかできない」と R3-1 訂正
- PR #775 merge 後 develop-0.3.0 で 8 連続 phantom run (`conclusion=failure` /
  `jobs_count=0` / 診断 "This run likely failed because of a workflow file issue.")
- issue #786 で Codex `/codex:rescue` (session `brave-heisenberg-5730dd`、
  agentId `a9a21c7545477c99c`) が真因を独立調査で確定

### 9.2 真因 (Codex finding)

`shell: ${{ matrix.shell }}` が GitHub Actions schema-invalid。`jobs.<job_id>.steps[*].shell`
field は matrix context をサポートしない (公式 [context availability table](https://docs.github.com/en/actions/learn-github-actions/contexts))。
workflow 起動前 schema validation で `Unrecognized named-value: 'matrix'` reject
→ jobs=0 / conclusion=failure となる。R3-1 訂正の「main paths filter で gating」
仮説とは無関係で、main の paths filter 残存とは独立した workflow schema 違反だった。

### 9.3 修正 (PR #788)

`build-windows` job 直下に `defaults.run.shell: ${{ matrix.shell }}` を追加し
(`jobs.<job_id>.defaults.run` field は matrix context 参照可能)、各 step 個別の
`shell: ${{ matrix.shell }}` 行を削除 (9 箇所)。matrix.shell 構造と #737 dual-shell
検証能力 (PS 5.1 silent regression 検知) を維持。`version-check` / `release` job の
`shell: bash` step 3 件は ubuntu-latest 上の意図的 bash 指定で touch しない。

### 9.4 spec doc への implication

- §7.1 R3 (Codex 独断 fix の risk) と本節 R3-1 訂正は **別物**。R3 は本 spec doc が
  対象とする risk、R3-1 訂正は PR #775 review process 中に生まれた誤った仮説で
  本 spec doc 範囲外
- 本節は PR #775 → #786 → #788 のループで得た「workflow schema 違反 phantom run」の
  empirical 知見を spec doc 末尾に追補することで、将来同種事象 (phantom run /
  jobs_count=0 / schema-invalid 仮説) が再発した時に正しい原因仮説を辿れるようにする
- 横展開教訓: workflow YAML で `${{ matrix.* }}` を含む field は GitHub Actions
  公式 context availability table を必ず確認する。step level `shell` は不可、
  job level `defaults.run.shell` は可、`env` block は両方可、等

### 9.5 関連

- 起源 PR: PR #775 (R3-1 訂正の元)
- 真因確定 issue: #786
- 真因修正 PR: #788
- doc 整合性 issue: #789 / #790 (本節 + release.yml inline comment retrospective note)
- Codex rescue session: `brave-heisenberg-5730dd` / agentId `a9a21c7545477c99c`
- GitHub Actions context availability: <https://docs.github.com/en/actions/learn-github-actions/contexts>
```

設計判断:

- 既存 §8「関連リンク」を最後尾に残さず §9 を **後ろに追加**。spec doc は時系列で読まれる前提なので、retrospective が末尾にある方が "post-spec 追補" として自然
- §7.1 Risk Register R3 と R3-1 訂正は **明確に別物** と §9.4 で書き分け。R3 = "Codex 独断 fix の risk" (本 spec が対象とする risk)、R3-1 訂正 = "PR #775 review 中の paths filter 仮説" (本 spec doc 範囲外の review artifact)。同じ「R3」prefix を使うことによる混乱を排除
- 横展開教訓を §9.4 に含め、本 lesson が単発 incident に留まらず future workflow YAML 編集にも効くようにする

### 3.5 memory file (任意、PR 外)

CLAUDE.md「Memory 活用 (ユーザー訂正の蓄積)」項目で奨励される lessons learned 蓄積。技術的 lesson は厳密には「ユーザー訂正」ではないが、CLAUDE.md「バグ修正時の方針」§ encoding boundary audit checklist と同様、横展開教訓として有用。

新規 file: `C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_github_actions_step_shell_matrix.md`

```markdown
---
name: GitHub Actions step.shell × matrix context 不互換
description: `${{ matrix.* }}` を step 個別 shell field で使うと schema-invalid で phantom run 化する。job level defaults.run.shell を使う
type: feedback
---

GitHub Actions workflow YAML で `jobs.<job_id>.steps[*].shell` field は matrix
context をサポートしない。`shell: ${{ matrix.shell }}` と書くと workflow 起動前
schema validation で reject されて `conclusion=failure` / `jobs_count=0` の
phantom run が記録される (診断: "This run likely failed because of a workflow file issue.")。

**Why**: 公式 [context availability table](https://docs.github.com/en/actions/learn-github-actions/contexts)
で `jobs.<job_id>.steps[*].shell` は matrix unsupported と明記。default branch
の workflow 定義で evaluate される known behavior と相まって、main paths filter
仮説等の二次原因と誤認しやすい (PR #775 R3-1 訂正で実際に誤推定した)。

**How to apply**: matrix context を shell に展開したい時は `jobs.<job_id>.defaults.run.shell`
を使う。step level の `shell:` field は literal 値 (`bash` / `pwsh` / `powershell` 等)
のみ。phantom run / jobs_count=0 / startup_failure を観測したら、まず
`${{ matrix.* }}` を step level field で使っていないか workflow YAML を grep する。

確定: Codex `/codex:rescue` agentId `a9a21c7545477c99c` / PR #786 #788 / 2026-05-19。
```

MEMORY.md 末尾追記 (1 行):

```markdown
- [GitHub Actions step.shell × matrix 不互換](feedback_github_actions_step_shell_matrix.md) — `${{ matrix.* }}` を step shell で使うと phantom run 化。defaults.run.shell に逃がす
```

設計判断: memory は本 PR の commit には **含めない** (project git tree 外、ユーザー個別 memory)。PR merge とは独立した task として別操作で実施。本 spec doc に手順だけ記載。

## 4. データフロー / エラーハンドリング / テスト戦略

doc-only PR のため:

- **データフロー**: 該当なし
- **エラーハンドリング**: 該当なし
- **テスト戦略**: 機能テスト追加なし。検証は §5 の machine check のみ

## 5. 検証方針 (CI / local)

### 5.1 PR 作成前 local check

| check | 期待値 | 根拠 |
| --- | --- | --- |
| `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8').read())"` | YAML OK (例外なし) | YAML 構文を不正にしないか |
| `grep -nE 'defaults:\|shell: \\\${{ matrix' .github/workflows/release.yml` | 2 行 (defaults / shell)、PR #788 から不変 | comment 追加で structural drift しないか |
| `grep -n 'shell: bash' .github/workflows/release.yml` | 3 件 (L82 / L403 / L410)、不変 | 意図的 bash step に touch していないか |
| `bash scripts/check-markdownlint.sh` | 0 errors | spec doc 追補が markdownlint 違反を増やさないか |
| `git diff --stat origin/develop-0.3.0..HEAD` | 2 files changed (release.yml + spec doc)、追加 ~40-50 行 | scope creep していないか |

Python / GUI / Rust / cargo の機能 check は **不要** (doc only、CLAUDE.md「PR 作成 path 別自動チェック」の docs-only branch 該当)。

### 5.2 PR 作成時 CI 検証

pull_request trigger で release.yml に対する自動 validation:

- GitHub Actions schema validation: workflow が `conclusion=success` で受理されること (= 新たな schema violation を導入していないこと、PR #788 で実証済の構造を維持)
- `build-windows (pwsh)` / `build-windows (powershell)` が両方 pass (PR #788 と同じ挙動、retrospective の comment 追加で structural break しないことの実証)

### 5.3 実機検証 trigger 表

CLAUDE.md 「実機検証 trigger 表」に該当する path (`gpu_detector.py` / `audio/*.py` / `video/detector.py` / `gui/src-tauri/**`) は **一切 touch しない**。AskUserQuestion での実機検証依頼は **不要**。

## 6. 受け入れ基準

### 6.1 issue #789

- [ ] `.github/workflows/release.yml` build-windows job の `defaults.run.shell` 直上に shell 戦略コメントが 5-6 行で挿入されている
- [ ] コメントは「step 個別 `shell:` field が matrix context unsupported」「`defaults.run.shell` で展開可能」「version-check / release の `shell: bash` literal は ubuntu 上で shell variation 不要のため」を明記している
- [ ] PR #788 / issue #786 への back-reference を含む
- [ ] 既存 L106-108 (M1 dual-matrix の理由コメント) は touch されていない

### 6.2 issue #790

- [ ] `.github/workflows/release.yml` L28-34 の R3-1 訂正 inline comment 直下に retrospective note が追記されている (既存 R3-1 訂正 comment は **書き換えない**)
- [ ] retrospective note は「R3-1 訂正の main paths filter 仮説は誤り」「真因 = `shell: ${{ matrix.shell }}` が schema-invalid」「PR #788 で `defaults.run.shell` に移行して解消」「R2 fix の paths filter 撤去は別目的で維持」を明記
- [ ] Codex rescue agentId / PR #786 / #788 / spec doc §9 への cross-reference を含む
- [ ] `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` に新規 §9「v0.2.x 系 release.yml phantom run retrospective (post-spec 追補)」が `## 8. 関連リンク` の **後ろ** に追加されている
- [ ] §9 が経緯 / 真因 / 修正 / spec doc への implication / 関連 リンクの 5 subsection 構成 (§9.1-§9.5)
- [ ] §9.4 で §7.1 Risk Register R3 と R3-1 訂正が **別物** である旨を明記
- [ ] (任意 / PR 外) memory `feedback_github_actions_step_shell_matrix.md` 新規作成 + MEMORY.md index 1 行追記

### 6.3 共通

- [ ] 機能 file (`allaganeye/**`, `gui/**`, `scripts/**`) の touch なし
- [ ] `version-check` / `release` job の `shell: bash` step (L82 / L403 / L410) の touch なし
- [ ] PR 作成前 local check (§5.1) 全 pass
- [ ] Iron Law 6 Pre-flight Step 0-5 全 pass
- [ ] (A) PR 内修正優先で `/iterate-review` 完走

## 7. リスクとオープン点

### 7.1 リスク

| ID | リスク | 影響度 | 対策 |
| --- | --- | --- | --- |
| R1 | release.yml YAML 構文を破壊する (コメント挿入位置誤り) | 中 (CI 全 fail) | §5.1 の `yaml.safe_load` check で PR 作成前に検出 |
| R2 | retrospective note が既存 R3-1 訂正 comment を上書きしてしまう | 低 (情報損失) | 「既存 comment 末尾に追記、書き換え禁止」を §3.2 / §6.2 で明示。Edit tool で `old_string` を既存 comment 末尾行のみに限定 |
| R3 | spec doc §9 追加で markdownlint 違反 | 低 (CI fail) | §5.1 の markdownlint check で PR 作成前に検出 |
| R4 | shell 戦略コメント追加で M1 dual-matrix の既存 comment との重複 / 矛盾 | 低 (読者混乱) | 「関心が違う別 block として隣接配置」を §3.3 で明示。M1 = "なぜ 2 shell"、本 block = "なぜ defaults.run で展開" と役割を分離 |
| R5 | scope creep (l2-workflow.md / CLAUDE.md にも lesson 追加) | 中 (Iron Law 3 違反) | §2 非範囲で l2-workflow.md / CLAUDE.md touch 禁止を明記。横展開希望の場合は別 issue 起票 |

### 7.2 オープン点

なし (Idios approval 済)。

## 8. 関連リンク

- 起源 PR: [PR #788](https://github.com/Idios/kobutachan-allaganeye/pull/788) (release.yml phantom run fix、本 issue 群の deferred 元)
- 関連 issue: [#789](https://github.com/Idios/kobutachan-allaganeye/issues/789) / [#790](https://github.com/Idios/kobutachan-allaganeye/issues/790)
- 真因確定 PR: [PR #786](https://github.com/Idios/kobutachan-allaganeye/issues/786)
- 起源 spec doc: `docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md`
- Codex rescue session: `brave-heisenberg-5730dd` / agentId `a9a21c7545477c99c`
- GitHub Actions context availability: <https://docs.github.com/en/actions/learn-github-actions/contexts>
