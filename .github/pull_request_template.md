## 期待値 (あるべき姿)

<!--
2-4 文。この PR がマージされた後にコードベース or 動作がどうあるべきか + なぜ目指すか。
関連 issue ある場合は内容を簡潔に inline 記載 (issue を辿らせない原則)。
詳細は元 issue へ link 参照可、本文と issue 本文の重複は受容。
-->

## 現状 (修正前)

<!--
2-4 文。PR 作成時点でどうなっているか + 期待値とのギャップ。
-->

## 修正内容 (現状 → 期待値)

<!--
bullet list。何をしたか、必要なら file path:line で具体化。
「現状 → 期待値 のギャップを埋める」視点で書く。
関連 issue は `Refs #123` の形で記載 (Closes / Fixes / Resolves キーワード禁止 = Iron Law 4)。
-->

## 受け入れ条件

<!--
Iron Law 1: 逐条検証
元 issue の `## 受け入れ条件` を逐条コピーし、各項目に対応する diff / test を明示する。
`/enforce-acceptance-criteria` skill が機械的に検証するので、曖昧な記述は避ける。
スコープ外の項目も [x] にして理由を付記すること。
heading 名は `pr-checklist.yml` workflow の section-aware regex と完全一致させる必要があるため変更不可
(`.github/scripts/check-pr-checklist.js` 参照)。
-->

- [ ] (条件 1 を逐条記入) — 対応 diff: `<file:lines>` / 対応 test: `<test_*.py::test_*>`
- [ ] (条件 2 を逐条記入) — 対応 diff: ... / 対応 test: ...

## PR チェックリスト (Iron Law 遵守確認)

### Iron Law 1: 受け入れ条件検証

- [ ] 元 issue の `## 受け入れ条件` を上記で逐条検証した (または受け入れ条件がない issue であることを確認)
- [ ] UI/出力変更の場合、実サンプル (CLI 出力・スクリーンショット) を本文に添付した

### Iron Law 3: スコープ遵守 (scope-guard)

- [ ] 変更ファイルがすべて元 issue のスコープ内であることを確認した (`git diff --stat` で確認)
- [ ] スコープ外変更がある場合、その理由と対応する子 issue 番号を「## 備考」に記載した

### Iron Law 4: クローズキーワード禁止

- [ ] 本文・コミットメッセージに `Closes` / `Fixes` / `Resolves` キーワードが含まれていない (issue クローズは手動)

### Iron Law 6: PR 作成前検証

#### ベース同期確認 (Pre-flight、`docs/l2-workflow.md` §「PR 作成 Pre-flight」)

<!--
plain bullet `-` で記述する (validate-checklist は `[x]` 化を要求しない)。
ただし **下 2 行の宣言フィールドは `check-preflight-freshness` job が機械検査する** (#946)。
plain bullet だから CI 対象外、ではない。未記入・placeholder 放置は fail-closed で red になる。
PR 作成前 Pre-flight 4 ステップ (`docs/l2-workflow.md` §「PR 作成 Pre-flight」参照):
1. `git fetch origin <base>` で base 最新化
2. `git log HEAD..origin/<base> --oneline` で取り込み未済 commit 列挙
3. 取り込み未済 commit が当 PR の `git diff --name-only origin/<base>` と path 交差するなら取り込み + 検証再実行
4. `gh pr list --search "<元issue#>" --state all` で並行 PR の有無確認
(Refs #635) checkbox convention: PR 本文では Self-Test Report (machine-verified) のみ [x] 必須、本節のような Pre-flight / 実機検証は plain bullet `-` を使う
-->

- PR 作成時の base HEAD: `<sha>` (`git rev-parse origin/<base>` 出力)
- PR head の base 取り込み: 取り込み不要 (base 進行なし) / merge 済み (commit `<sha>`) / rebase 済み
- 直近マージ PR の影響: なし / [#N] (touched files 交差: `<path>` → 確認済み)
- 並行 PR 確認 (`gh pr list --search "<元issue#>" --state all`): なし / [#N] (理由: 別スコープ並走 / 重複なし)

<!--
下 2 行は Step 0 / Step 4 で **実際に観測した open PR 集合**をそのまま書き写す欄で、
CI が PR 作成時点 (T0) の集合を再サンプリングして差分を取る (#946)。
上の「並行 PR 確認」行との分担: あちらは `--state all` の結果に対する**判断**
(別スコープ並走 / 重複なし) を書く欄、こちらは判断前の**生の観測結果**を書く欄。
重複記入ではなく、判断の入力と出力を分けている。
書式: `#938, #940` (無ければ `なし`)。`[#N,...]` を残したまま提出すると red になる。
-->

- Pre-flight 時点の同 issue open PR: [#N,...] (または なし)
- Pre-flight 時点の同 base open PR: [#N,...] (または なし)

#### Self-Test Report (machine-verified — 全件 `[x]` で validate-checklist 通過)

<!--
変更ファイル path に応じて該当する job のみ `[x]` 必須。
該当しない場合は `[x]` + 「N/A: <理由>」 を付記 (例: `[x] cargo check — N/A: gui/src-tauri/ 変更なし`)。
未実施の場合は `[ ]` のままで CI fail させる (Iron Law 6 違反として明示)。
(Refs #635) checkbox convention: 本節は machine-verified 限定なので全件 [x]、未実施は [ ] のまま CI fail させて自覚を促す。詳細は docs/l2-workflow.md §「Self-Test Report 規約」

Fable 俯瞰レビュー (#945) の起動条件 — 次のいずれかに該当したら「実施」:
  (a) doc-only PR (docs/** / *.md のみで code file 変更ゼロ)
  (b) docs/superpowers/specs/** または docs/superpowers/plans/** への新規ファイル追加を含む
該当時は「実施 (finding N 件 / 消化 M 件 / 残 K 件)」を **実数で** 記入する (N/M/K のままは CI red)。
非該当時は「非実施 (理由: 2 条件のどちらに非該当か)」。
起動条件は CI が変更ファイル一覧と突き合わせて検査する — 該当 PR で「非実施」と書くと red。
詳細は .claude/skills/review-pr/SKILL.md §「optional 俯瞰レビュー」
-->

- [ ] `ruff check .` (python-core 変更時)
- [ ] `ruff format --check .` (python-core 変更時)
- [ ] `pyright --pythonpath <repo root の .venv の python>` (python-core 変更時。`--pythonpath` 省略は false-red、#974)
- [ ] `pytest` (python-core 変更時、slow 除外)
- [ ] `cd gui && npm run lint` (gui-frontend 変更時)
- [ ] `cd gui && npm run typecheck` (gui-frontend 変更時)
- [ ] `cd gui && npm test` (gui-frontend 変更時)
- [ ] `cd gui && npm run build` (gui-frontend 変更時)
- [ ] `cargo check --manifest-path gui/src-tauri/Cargo.toml` (gui-rust 変更時)
- [ ] `Invoke-Pester -Path scripts/tests/` (installer-pester 変更時、Windows 上で)
- [ ] Fable 俯瞰レビュー (#945): <上のコメントの起動条件を見て「実施 (finding N 件 / 消化 M 件 / 残 K 件)」または「非実施 (理由: ...)」に置き換える>

#### 関連ドキュメント / マトリクス更新

- [ ] 関連ドキュメント更新 (`docs/cli-spec.md` / `docs/design-overview.md` / `README.md` 等) — 該当なしなら `[x]` + 理由付記
- [ ] **新規 CLI オプション追加時**: [`docs/output-spec.md`](../docs/output-spec.md) のマトリクス更新 (#405) — 該当なしなら `[x]` + 理由付記
- [ ] CLAUDE.md / `docs/l2-workflow.md` の更新要否確認 — 不要なら `[x]` + 理由付記
- [ ] 出力書式を変更した場合、`docs/cli-spec.md` の該当出力例も更新 (再発防止: #343 系)
- [ ] docs / 識別子のリネーム時は `docs/l2-workflow.md` §「doc 節参照健全性確認」 で §「<旧名>」grep し残骸ゼロ確認
- [ ] **CHANGELOG entry の要否を判断した** ([`docs/release-process.md`](../docs/release-process.md) §CHANGELOG entry の記述規約) — 利用者から見た振る舞いが変わる変更なら `## [Unreleased]` へ追記。内部専用なら本文に `CHANGELOG entry: 不要 (内部専用 — <CI ガード / 開発 doc / skill / テスト / 版 pin>)` を 1 行残す

#### 実機検証 (machine-unverifiable — plain bullet で書く)

<!--
validate-checklist は plain bullet `-` を無視するため未実施でもブロックしない。
ただし「未実施」を握り潰しせず明示する: 「PR 提出時点では未実施 / レビュー時に実機確認」と書く。
該当 path 変更がない場合: 「- 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)」を 1 行書く。
(Refs #635) checkbox convention: 本節は machine-unverifiable なので plain bullet `-` (checkbox なし)。CI validate-checklist は本節を無視
-->

- (例) `pytest -m slow_gpu tests/test_gpu_detector.py` — PR 提出時点で実施済 (Windows + NVIDIA RTX 4070, ffmpeg 8.1, NVENC 動作確認)
- (例) `npm run tauri dev` で export 画面の H.264 再エンコード目視確認 — PR 提出時点では未実施 (レビュー時にユーザー確認依頼)
- (例) 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)

## 関連

- Refs #
- Base branch: `develop-x.y.z` <!-- 現行の開発 branch に置換 -->
- Session: <!-- 例: relaxed-mestorf-9807da -->

## 備考 (任意)

<!-- スコープ制限・既知の未対応事項・追加テスト依頼事項・スコープ外変更の理由と子 issue 番号など -->
