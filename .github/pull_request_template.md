## 概要

<!-- 1-3 行でこの PR の目的を書いてください。Refs #123 の形で関連 issue を記載 -->

## 変更点

<!-- 主要な変更を箇条書きで。ファイル単位ではなく「何を・なぜ」 -->

## 受け入れ基準 / 確認項目

<!-- issue の受け入れ基準をコピーし、[x] で状態を示す。スコープ外の項目も [x] にして理由を付記 -->

- [ ]
- [ ]

## PR チェックリスト

- [ ] 全テスト通過 (`pytest`)
- [ ] Lint 通過 (`ruff check .` + `ruff format --check .`)
- [ ] 型チェック通過 (`pyright`)
- [ ] 関連ドキュメント更新 (`docs/cli-spec.md` / `docs/design-overview.md` / `README.md` 等) — 該当なしなら `[x]` + 理由付記
- [ ] **新規 CLI オプション追加時**: [`docs/output-spec.md`](../docs/output-spec.md) のマトリクス更新 (#405 受け入れ基準) — 該当なしなら `[x]` + 理由付記
- [ ] CLAUDE.md の更新要否確認 — 不要なら `[x]` + 理由付記
- [ ] 出力書式を変更した場合、`docs/cli-spec.md` の該当出力例も更新 (再発防止: #343 系の「出力例なし」問題対策)

## 関連

- Refs #
- Base branch: `develop-0.2.0`
- Session: <!-- 例: relaxed-mestorf-9807da -->

## 備考 (任意)

<!-- スコープ制限・既知の未対応事項・追加テスト依頼事項など -->
