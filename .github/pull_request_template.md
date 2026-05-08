## 概要

<!-- 1-3 行でこの PR の目的を書いてください。Refs #123 の形で関連 issue を記載 -->

## 変更点

<!-- 主要な変更を箇条書きで。ファイル単位ではなく「何を・なぜ」 -->

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
plain bullet `-` で記述する (validate-checklist は `[x]` 化を要求しない、CI ゲート増設なし)。
PR 作成前 Pre-flight 4 ステップ (`docs/l2-workflow.md` §「PR 作成 Pre-flight」参照):
1. `git fetch origin <base>` で base 最新化
2. `git log HEAD..origin/<base> --oneline` で取り込み未済 commit 列挙
3. 取り込み未済 commit が当 PR の `git diff --name-only origin/<base>` と path 交差するなら取り込み + 検証再実行
4. `gh pr list --search "<元issue#>" --state all` で並行 PR の有無確認
-->

- PR 作成時の base HEAD: `<sha>` (`git rev-parse origin/<base>` 出力)
- PR head の base 取り込み: 取り込み不要 (base 進行なし) / merge 済み (commit `<sha>`) / rebase 済み
- 直近マージ PR の影響: なし / [#N] (touched files 交差: `<path>` → 確認済み)
- 並行 PR 確認 (`gh pr list --search "<元issue#>" --state all`): なし / [#N] (理由: 別スコープ並走 / 重複なし)

#### Self-Test Report (machine-verified — 全件 `[x]` で validate-checklist 通過)

<!--
変更ファイル path に応じて該当する job のみ `[x]` 必須。
該当しない場合は `[x]` + 「N/A: <理由>」 を付記 (例: `[x] cargo check — N/A: gui/src-tauri/ 変更なし`)。
未実施の場合は `[ ]` のままで CI fail させる (Iron Law 6 違反として明示)。
-->

- [ ] `ruff check .` (python-core 変更時)
- [ ] `ruff format --check .` (python-core 変更時)
- [ ] `pyright` (python-core 変更時)
- [ ] `pytest` (python-core 変更時、slow 除外)
- [ ] `cd gui && npm run lint` (gui-frontend 変更時)
- [ ] `cd gui && npm run typecheck` (gui-frontend 変更時)
- [ ] `cd gui && npm test` (gui-frontend 変更時)
- [ ] `cd gui && npm run build` (gui-frontend 変更時)
- [ ] `cargo check --manifest-path gui/src-tauri/Cargo.toml` (gui-rust 変更時)
- [ ] `Invoke-Pester -Path scripts/tests/` (installer-pester 変更時、Windows 上で)

#### 関連ドキュメント / マトリクス更新

- [ ] 関連ドキュメント更新 (`docs/cli-spec.md` / `docs/design-overview.md` / `README.md` 等) — 該当なしなら `[x]` + 理由付記
- [ ] **新規 CLI オプション追加時**: [`docs/output-spec.md`](../docs/output-spec.md) のマトリクス更新 (#405) — 該当なしなら `[x]` + 理由付記
- [ ] CLAUDE.md / `docs/l2-workflow.md` の更新要否確認 — 不要なら `[x]` + 理由付記
- [ ] 出力書式を変更した場合、`docs/cli-spec.md` の該当出力例も更新 (再発防止: #343 系)
- [ ] docs / 識別子のリネーム時は `docs/l2-workflow.md` §「doc 節参照健全性確認」 で §「<旧名>」grep し残骸ゼロ確認

#### 実機検証 (machine-unverifiable — plain bullet で書く)

<!--
validate-checklist は plain bullet `-` を無視するため未実施でもブロックしない。
ただし「未実施」を握り潰しせず明示する: 「PR 提出時点では未実施 / レビュー時に実機確認」と書く。
該当 path 変更がない場合: 「- 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)」を 1 行書く。
-->

- (例) `pytest -m slow_gpu tests/test_gpu_detector.py` — PR 提出時点で実施済 (Windows + NVIDIA RTX 4070, ffmpeg 8.1, NVENC 動作確認)
- (例) `npm run tauri dev` で export 画面の H.264 再エンコード目視確認 — PR 提出時点では未実施 (レビュー時にユーザー確認依頼)
- (例) 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)

## 関連

- Refs #
- Base branch: `develop-0.2.0`
- Session: <!-- 例: relaxed-mestorf-9807da -->

## 備考 (任意)

<!-- スコープ制限・既知の未対応事項・追加テスト依頼事項・スコープ外変更の理由と子 issue 番号など -->
