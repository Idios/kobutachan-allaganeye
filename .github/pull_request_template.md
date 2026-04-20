## 概要

<!-- 1-3 行でこの PR の目的を書いてください。Refs #123 の形で関連 issue を記載 -->

## 変更点

<!-- 主要な変更を箇条書きで。ファイル単位ではなく「何を・なぜ」 -->

## 受け入れ基準 / 確認項目 (Iron Law 1: 逐条検証)

<!--
元 issue の `## 受け入れ条件` を逐条コピーし、各項目に対応する diff / test を明示する。
`/enforce-acceptance-criteria` skill が機械的に検証するので、曖昧な記述は避ける。
スコープ外の項目も [x] にして理由を付記すること。
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

### 品質ゲート
- [ ] 全テスト通過 (`pytest`)
- [ ] Lint 通過 (`ruff check .` + `ruff format --check .`)
- [ ] 型チェック通過 (`pyright`)
- [ ] 関連ドキュメント更新 (`docs/cli-spec.md` / `docs/design-overview.md` / `README.md` 等) — 該当なしなら `[x]` + 理由付記
- [ ] **新規 CLI オプション追加時**: [`docs/output-spec.md`](../docs/output-spec.md) のマトリクス更新 (#405) — 該当なしなら `[x]` + 理由付記
- [ ] CLAUDE.md / `docs/l2-workflow.md` の更新要否確認 — 不要なら `[x]` + 理由付記
- [ ] 出力書式を変更した場合、`docs/cli-spec.md` の該当出力例も更新 (再発防止: #343 系)

## 関連

- Refs #
- Base branch: `develop-0.2.0`
- Session: <!-- 例: relaxed-mestorf-9807da -->

## 備考 (任意)

<!-- スコープ制限・既知の未対応事項・追加テスト依頼事項・スコープ外変更の理由と子 issue 番号など -->
