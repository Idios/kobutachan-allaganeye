# Issue #786: release.yml phantom run 修正 設計

> **Status**: design (brainstorming 確定、writing-plans 待ち)
> **作成**: 2026-05-19 / session `brave-heisenberg-5730dd`
> **対象 issue**: [#786](https://github.com/Idios/kobutachan-allaganeye/issues/786)
> **関連 issue / PR**: [#752](https://github.com/Idios/kobutachan-allaganeye/issues/752) (受け入れ条件未実証), [PR #785](https://github.com/Idios/kobutachan-allaganeye/pull/785) (post-merge plan Step 1 未達)
> **上位 plan**: なし (単独 bug issue、本 session で scope 拡張)

## 概要

`develop-0.3.0` への push で `.github/workflows/release.yml` が phantom run (jobs=0, conclusion=failure) になり、`build-windows` job が実行されない問題を修正する。Codex `/codex:rescue` による独立調査で root cause が判明: `shell: ${{ matrix.shell }}` が GitHub Actions schema-invalid (= `jobs.<job_id>.steps[*].shell` field は matrix context をサポートしない)。

修正は `defaults.run.shell: ${{ matrix.shell }}` を build-windows job 直下に置き、各 step の `shell: ${{ matrix.shell }}` 行 (9 箇所) を削除する最小変更 (Option A2)。matrix.shell 構造 + #737 dual-shell 検証能力を維持。

修復後の CI で build-windows が動作することを以て、PR #785 post-merge plan Step 1 (PyInstaller frozen build + smoke Lv A/B/integrity exit 7 + baseline.json artifact) の empirical 検証を完遂し、#752 受け入れ条件 (file count reduction ≥ 80%) を実測再確認する。

## 背景

### 観測事実

- develop-0.3.0 への 8 連続 push (`c3ea76d` 〜 `6e00fe05`) で release.yml が `conclusion=failure` / `jobs_count=0` / `name=".github/workflows/release.yml"` (= name field 取得失敗)
- GitHub Actions 自身の診断: "This run likely failed because of a workflow file issue."
- 同 commit の ci.yml は success (= GitHub Actions 基盤は正常)
- workflow_dispatch (`gh workflow run release.yml --ref ...`) も rejected
- YAML syntax は Python `yaml.safe_load` で valid (= raw YAML は文法上正しい)
- 最後の成功: 2026-05-17T00:08:55Z (`7e4f7a6`)
- 最初の失敗: 2026-05-17T08:38:24Z (`85ef748` = PR #775 merge commit)

### 影響範囲

- **PR #785** (#752 PyInstaller --onedir 移行): post-merge plan Step 1 が未達
  - PyInstaller `--onedir` frozen build on Windows runner (build 成功 / 出力構造)
  - CI smoke Lv A (`allaganeye.bat --version` exit 0 + 'allaganeye' marker)
  - CI smoke Lv B (`allaganeye.bat detect tests/fixtures/smoke_3s.mp4` exit 0 or 4)
  - CI smoke integrity-fall-through (`_internal/allaganeye/audio/refs/fanfare.npz` 削除 → exit 7)
  - `allaganeye-baseline-v0.3.0` artifact (real file count metric for #752 Before/After)
- **issue #752** (Portable ZIP file 数削減): 受け入れ条件「file count reduction ≥ 80%」が実測未確定
- **v0.3.0 release**: `build-windows` validation が動かない状態は release blocker 相当

### Root Cause (Codex rescue 確定)

Codex `/codex:rescue` (2026-05-19、Claude session `brave-heisenberg-5730dd`) による独立調査で以下を確定:

1. **develop-0.3.0 release.yml に `shell: ${{ matrix.shell }}` が 9 箇所**
   (L155, 160, 170, 176, 183, 198, 222, 252, 308)
2. **GitHub Actions 公式 context availability table**: `jobs.<job_id>.steps[*].shell` field は **matrix context をサポートしない**
   - 利用可能な step field: `if`, `name`, `env`, `run`, `continue-on-error`, `timeout-minutes`, `with`, `working-directory` のみ
   - 参照: <https://docs.github.com/en/actions/learn-github-actions/contexts>
3. 結果: workflow 起動前の schema validation 段階で `Unrecognized named-value: 'matrix'` で reject → jobs_count=0 / conclusion=failure として記録
4. **副次効果**: workflow_dispatch も同じ理由で reject される。main release.yml の構造 / paths filter / default branch trigger evaluation は **無関係** (PR #775 R3-1 訂正の「main paths filter で gating」仮説は誤り)

### 元方針との差分

本 issue 受領時の初期方針は「develop-0.3.0 期間中の phantom run を許容、main merge で自然解消」だったが、Codex finding で **main merge でも直らない** ことが判明:

- v0.3.0 release タイミングで develop-0.3.0 → main merge → main の release.yml も matrix.shell 構造に置換 → main 側でも phantom run
- v0.3.0 release blocker 化 risk が顕在化
- 結果として本 issue scope を「release.yml 修正 PR 作成 + #785 post-merge plan Step 1 検証 + #752 metric 反映」の **一気通貫** に拡張 (Idios 確認 2026-05-19)

## 設計

### Fix method: Option A2 (defaults.run.shell に移動)

GitHub Actions docs により `jobs.<job_id>.defaults.run` は matrix context 参照可。step.shell の代わりに `defaults.run.shell` を使うことで matrix.shell 構造を保ったまま schema valid にできる。

#### 修正前 (develop-0.3.0 現行、抜粋)

```yaml
jobs:
  build-windows:
    needs: version-check
    runs-on: windows-latest
    strategy:
      fail-fast: false
      matrix:
        shell: [pwsh, powershell]
    name: build-windows (${{ matrix.shell }})
    env:
      ALLAGANEYE_BUILD_CACHE_DIR: ${{ github.workspace }}/build-cache
    steps:
      - uses: actions/checkout@v4
      # ... uses 系 step は shell 不要
      - name: Install GUI dependencies (#570)
        shell: ${{ matrix.shell }}        # ← schema invalid
        working-directory: gui
        run: npm ci --no-audit --no-fund
      - name: Build Tauri GUI binary (#570)
        shell: ${{ matrix.shell }}        # ← schema invalid
        working-directory: gui
        run: npm run tauri build
      # ... 計 9 箇所
```

#### 修正後 (Option A2)

```yaml
jobs:
  build-windows:
    needs: version-check
    runs-on: windows-latest
    strategy:
      fail-fast: false
      matrix:
        shell: [pwsh, powershell]
    name: build-windows (${{ matrix.shell }})
    defaults:
      run:
        shell: ${{ matrix.shell }}        # ← matrix context 参照可 (公式 docs 確認済)
    env:
      ALLAGANEYE_BUILD_CACHE_DIR: ${{ github.workspace }}/build-cache
    steps:
      - uses: actions/checkout@v4
      # ... uses 系 step は shell 不要
      - name: Install GUI dependencies (#570)
        working-directory: gui            # ← shell: 行削除
        run: npm ci --no-audit --no-fund
      - name: Build Tauri GUI binary (#570)
        working-directory: gui            # ← shell: 行削除
        run: npm run tauri build
      # ... 9 箇所すべてで shell: 行削除
```

#### 触らない部分

- **version-check job の `Resolve and verify version` step (L80-100)**: `shell: bash` 固定 (ubuntu-latest 上で意図的 bash 指定)。`defaults.run.shell` は build-windows job 配下にのみ追加し、他 job に波及しない
- **release job の `Create release archive` / `Extract release notes from CHANGELOG` step (L408-417)**: `shell: bash` 固定 (ubuntu-latest 上で bash 指定)

### 修復後の作業フロー (一気通貫)

```text
[Phase 1: release.yml 修正 PR]
 ├ 1. release.yml に defaults.run.shell 追加 + 9 箇所の shell: 行削除
 ├ 2. local YAML syntax check (Python yaml.safe_load)
 ├ 3. Iron Law 6 Pre-flight Step 0-4 + Step 5 /codex:adversarial-review
 ├ 4. PR 作成 (base=develop-0.3.0)
 │     - PR の pull_request trigger で release.yml が build-windows job を含めて実行されることを CI 上で empirical 確認
 │     - artifact (allaganeye-baseline-v0.3.0 / allaganeye-windows-v0.3.0) が generate されるか確認
 ├ 5. /iterate-review でレビュー fix ループ自走
 └ 6. CI 全 pass を待って merge
       - merge 後 develop-0.3.0 への push trigger で再度 release.yml が success することを確認

[Phase 2: PR #785 post-merge plan Step 1 検証]
 ├ 7. develop-0.3.0 への push trigger で生成された baseline.json artifact を `gh run download` で取得
 ├ 8. baseline.json から file count metric を抽出
 ├ 9. PR #785 に「## Empirical Validation Report」comment 投稿
 │     - 5 検証結果 (frozen build / Verify GUI bundled / baseline / Lv A / Lv B / integrity exit 7) を逐条
 │     - Before/After table: file count (#752 元 ZIP 値 vs PyInstaller frozen 値、reduction %)
 └ 10. #752 受け入れ条件再検証 (file count reduction ≥ 80%?)

[Phase 3: issue close]
 ├ 11. /close-issue #752 を起動 (Pass なら正式 close、Fail なら follow-up issue 起票)
 └ 12. /close-issue #786 を起動 (本 issue 受け入れ条件検証 → close)
```

### Components / 触る file

| File | 修正内容 | 想定 diff |
| --- | --- | --- |
| `.github/workflows/release.yml` | build-windows job に `defaults.run.shell: ${{ matrix.shell }}` 追加 + 各 step の `shell: ${{ matrix.shell }}` 行 9 箇所削除 | +3 / -9 = -6 net line |

それ以外の file (scripts / source code / docs) は touch しない。

### Data flow

修正後の release.yml で build-windows job が動いた場合:

1. push (develop-0.3.0) / pull_request / workflow_dispatch / release tag いずれかが trigger
2. version-check job (ubuntu) → pwsh / powershell 2 matrix で build-windows (windows-latest) 並列実行
3. PyInstaller --onedir で frozen build → `build/portable/allaganeye-v<version>/` payload 生成
4. `Verify allaganeye-gui.exe is bundled` (Test-Path check)
5. `Measure Portable ZIP baseline (#752)` (pwsh matrix のみ、pull_request / tags push / workflow_dispatch で実行) → `baseline.json` 生成
6. `Smoke test Lv A / Lv B / integrity` (pull_request / tags push / workflow_dispatch で実行)
7. `upload-artifact` (pwsh matrix のみ、pull_request / tags push で実行) → `allaganeye-windows-v<version>` (payload) + `allaganeye-baseline-v<version>` (baseline.json)
8. release job (release tag push 時のみ) → archive 作成 + GitHub Release 作成

### Error handling

- 修正後の CI で build-windows が **再度 phantom run** → Codex finding が誤りまたは別の root cause。再調査 (本 spec §Root Cause を見直し、別 H5+ hypothesis を立てる)
- 修正後の CI で build-windows が **fail (実 job runtime fail)** → individual step の修正 (本 issue scope 内 or 別 issue 起票、Idios 判断)
- baseline.json から file count を抽出して **≥ 80% reduction を満たさない** → #752 受け入れ条件再評価。Idios 判断で wontfix / lower target / 追加最適化 issue 起票
- PyInstaller frozen build 自体が **fail** → 新 P0 bug issue 起票 (release blocker)
- Smoke Lv A/B/integrity が **fail** → 新 P0 bug issue 起票 (release blocker)

### Testing

- 本 issue 自体に **新規 test code はなし** (release.yml の YAML 構造変更のみ、scripts / source code 不変)
- 修正の動作確認 = CI 上の build-windows job 成功 (jobs_count > 0 / conclusion=success / artifact 生成) で empirical 検証
- 既存 test (pytest / installer-pester / GUI test / lint 各種) は touch しないため regression リスクは release.yml 限定

## 受け入れ条件

本 issue 受け入れ条件は元 issue 本文「修正方針」+ scope 拡張 (Idios 2026-05-19 確認) を集約:

- [ ] **release.yml 修正**: `defaults.run.shell: ${{ matrix.shell }}` 追加 + 各 step の `shell: ${{ matrix.shell }}` 行 9 箇所削除
- [ ] **YAML syntax check 通過**: Python `yaml.safe_load` で valid (可能なら `actionlint` でも valid)
- [ ] **CI 上で build-windows job 実行成功**: pull_request trigger および merge 後の push (develop-0.3.0) trigger 両方で確認 (jobs_count > 0 / conclusion=success)
- [ ] **artifact 生成**: `allaganeye-windows-v0.3.0` (payload) + `allaganeye-baseline-v0.3.0` (baseline.json) 両方が generate される
- [ ] **PR #785 post-merge plan Step 1 完遂**:
  - PyInstaller --onedir frozen build 成功 (Verify GUI bundled pass)
  - Smoke Lv A pass (`allaganeye.bat --version` exit 0 + 'allaganeye' marker)
  - Smoke Lv B pass (`allaganeye.bat detect` exit 0 or 4)
  - Smoke integrity-fall-through pass (fanfare.npz 削除 → exit 7)
- [ ] **#752 metric 反映**: baseline.json から file count を抽出して **PR #785 に post-merge comment として Empirical Validation Report + Before/After table 投稿** (merged PR の本文編集ではなく comment で記録)
- [ ] **#752 受け入れ条件再検証**: file count reduction ≥ 80% を実測確認 (Pass なら `/close-issue #752`)

## Out of scope (本 issue で触らない、別 issue 候補)

- **main release.yml の先行 backport (元 Option A)**: 本 issue で develop-0.3.0 release.yml を fix すれば、v0.3.0 release タイミングの develop-0.3.0 → main merge で自然に main へ反映される。Codex finding により main の paths filter / default branch trigger evaluation は phantom run と無関係であることが確定したため、先行 backport PR は作らない
- **#737 PS 5.1 silent regression 検知の強化**: 既に develop-0.3.0 で実装済 (matrix.shell dual)。本 issue では schema invalid を fix するのみで機能は維持
- **release.yml 全体構造の整理 / 簡素化**: scope creep。別 issue で
- **GitHub Actions schema-level validation の CI 追加 (actionlint 等)**: 本 issue 修正と並行で価値高いが scope creep。別 issue 候補 (本 issue close コメントで follow-up suggestion として記載)
- **PR #775 R3-1 訂正の修正 (= 「main paths filter で gating」仮説は誤りだった旨を doc 化)**: scope creep。別 issue で l2-workflow.md や PR #775 retrospective に反映

## References

- [issue #786 本文](https://github.com/Idios/kobutachan-allaganeye/issues/786)
- [PR #775 (release.yml に matrix.shell を導入した PR、本 bug を生んだ)](https://github.com/Idios/kobutachan-allaganeye/pull/775)
- [PR #737 (M1 dual-shell matrix in release.yml の元 issue)](https://github.com/Idios/kobutachan-allaganeye/pull/737)
- [PR #785 (post-merge plan Step 1 未達 PR、本 issue が unblock 対象)](https://github.com/Idios/kobutachan-allaganeye/pull/785)
- [issue #752 (Portable ZIP file 数削減、acceptance criteria 未実証)](https://github.com/Idios/kobutachan-allaganeye/issues/752)
- [GitHub Actions docs: contexts and context availability](https://docs.github.com/en/actions/learn-github-actions/contexts)
- [failed run 例 (#26065950820, 2026-05-19 develop-0.3.0)](https://github.com/Idios/kobutachan-allaganeye/actions/runs/26065950820)
- Codex rescue session (2026-05-19、本 session 内に集約、agentId `a9a21c7545477c99c`)
