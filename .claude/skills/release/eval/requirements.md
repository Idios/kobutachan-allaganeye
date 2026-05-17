# /release 要件チェックリスト (L-β β-3 改訂後 Iteration 0)

empirical-prompt-tuning §「ワークフロー 4. 両面評価」の精度算出・[critical] 付与ルールに従う。

## 判定規則

- **成功/失敗**: [critical] 項目が全て ○ のときのみ成功 (○)。1 つでも × or 部分的なら失敗 (×)
- **精度**: ○ = 1.0、× = 0、部分的 = 0.5

---

## シナリオ A (minor release v0.3.0)

モック: develop-0.3.0 ブランチで v0.3.0 release PR 作成。pyproject.toml = 0.3.0、受け入れゲート §共通項目 + §v0.3.0 (L3) 固有項目 を充足、deferred 0 件。

1. **[critical]** **A-1**: Step 0a (旧 Step 0) でレイヤーリリース受け入れゲートを §共通項目 + §v0.3.0 固有項目 を user 提示し各項目 ○ 確認
2. **[critical]** **A-2**: Step 0b で `gh issue list --label deferred --state open --limit 200` を実行し、件数 0 を検出して Step 0c skip
3. **[critical]** **A-3**: 全ゲート通過後に Step 1 リリース準備に進む
4. minor release は `docs/release-process.md` §Patch release Track 構造 (A2) の適用対象外と判断

---

## シナリオ B (patch release v0.3.1、deferred 5 件 / うち 2 件は次 patch 吸収)

モック: deferred ラベル 5 件 (#374 #458 #743 #749 #756 を想定)。spec PR (Track 0) を起票。

1. **[critical]** **B-1**: Step 0b で `gh issue list --label deferred ... --limit 200` 全件取得
2. **[critical]** **B-2**: 件数 5 ≥ 3 のため、Step 0c 冒頭で Iron Law 2 bulk pre-check (サンプル 1 件 + 全件 OK / 個別調整 / やめる 3 択) を user に提示
3. **[critical]** **B-3**: 「個別調整」選択時、各 issue を 1 件ずつ AskUserQuestion で (a) 次 release 吸収 / (b) deferred 継続 / (c) close の 3 択分類
4. **[critical]** **B-4**: 分類結果を spec PR (Track 0) の §deferred 全件検証結果 table として保存
5. **[critical]** **B-5**: (a) 分類が `docs/release-process.md` §Patch release Track 構造 の Track B 吸収候補と関連付けされる
6. **[critical]** **B-6**: (a) 分類 issue 群の Track B PR / commit plan が無い場合、release PR 作成を block

---

## シナリオ C (deferred 0 件 edge)

モック: deferred ラベル 0 件。

1. **[critical]** **C-1**: Step 0b で件数 0 を検出
2. **[critical]** **C-2**: Step 0c を skip して Step 1 に進む (無駄な AskUserQuestion を発火しない)

## Codex 統合 / 撤回 M8 関連 [critical] (全 scenario 共通)

1. **[critical]** **CDX-R-1**: `release-blocker` label は使用しない (M8 撤回確定、2026-05-17 D1)
2. **[critical]** **CDX-R-2**: Step 0b query は `--label "deferred"` のみ、`--label "release-blocker"` を含めない
