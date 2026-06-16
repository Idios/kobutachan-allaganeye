# /release 要件チェックリスト (L-β β-3 改訂後 Iteration 0)

empirical-prompt-tuning §「ワークフロー 4. 両面評価」の精度算出・[critical] 付与ルールに従う。

## 判定規則

- **成功/失敗**: [critical] 項目が全て ○ のときのみ成功 (○)。1 つでも × or 部分的なら失敗 (×)
- **精度**: ○ = 1.0、× = 0、部分的 = 0.5

---

## シナリオ A (minor release v0.3.0)

モック: develop-0.3.0 ブランチで v0.3.0 release PR 作成。pyproject.toml = 0.3.0、受け入れゲート §共通項目 + §v0.3.0 (L3) 固有項目 を充足、deferred 0 件。

1. **[critical]** **A-1**: Step 0a (旧 Step 0) でレイヤーリリース受け入れゲートを §共通項目 + §v0.3.0 固有項目 を user 提示し各項目 ○ 確認
2. **[critical]** **A-2**: Step 0b で `gh issue list --label deferred --state open --limit 200` を実行し、件数 0 を検出して deferred 分類 (Step 0c) を skip (※not_planned 残タスク確認の要否は C-3 で検証)
3. **[critical]** **A-3**: 全ゲート通過後に Step 1 リリース準備に進む
4. minor release は `docs/release-process.md` §Patch release Track 構造 (A2) の適用対象外と判断
5. **[critical]** **A-5**: Step 3-2 の version bump 確認 grep に `--include='*.json'` を含め、`gui/src-tauri/tauri.conf.json` / `gui/package.json` のバージョン参照も対象にしている (#817 / P2-33。`*.py` / `*.toml` のみで `*.json` を落としていたら失格)

---

## シナリオ B (patch release v0.3.1、deferred 5 件 / うち 2 件は次 patch 吸収)

モック: deferred ラベル 5 件 (#374 #458 #743 #749 #756 を想定)。spec PR (Track 0) を起票。

1. **[critical]** **B-1**: Step 0b で `gh issue list --label deferred ... --limit 200` 全件取得
2. **[critical]** **B-2**: 件数 5 ≥ 3 のため、Step 0c 冒頭で Iron Law 2 bulk pre-check (サンプル 1 件 + 全件 OK / 個別調整 / やめる 3 択) を user に提示
3. **[critical]** **B-3**: 「個別調整」選択時、各 issue を 1 件ずつ AskUserQuestion で (a) 次 release 吸収 / (b) deferred 継続 / (c) close の 3 択分類
4. **[critical]** **B-4**: 分類結果を spec PR (Track 0) の §deferred 全件検証結果 table として保存
5. **[critical]** **B-5**: (a) 分類が `docs/release-process.md` §Patch release Track 構造 の Track B 吸収候補と関連付けされる
6. **[critical]** **B-6**: (a) 分類 issue 群の Track B PR / commit plan が無い場合、release PR 作成を block
7. **[critical]** **B-7**: Step 0c-2 で各 deferred issue の本文と直近コメントを関連 spec と突合し、鮮度切れ (本文が現状と矛盾) があれば分類前に `gh issue edit` での本文更新を提案している (#817 / P2-39)
8. **[critical]** **B-8**: Step 0c-2 でリリース区間の `wired in #N` / `Refs #N` 等が指す issue を確認し、`stateReason == "not_planned"` で close されているものは残タスクの行き先 (再起票要否) を確認している (#762 orphan 化の再発防止)

---

## シナリオ C (deferred 0 件 edge)

モック: deferred ラベル 0 件。ただしリリース区間のコードに `wired in #770` マーカーがあり、#770 は `stateReason == "not_planned"` で close 済み (残タスク行き先未確認)。

1. **[critical]** **C-1**: Step 0b で件数 0 を検出
2. **[critical]** **C-2**: deferred 分類 (Step 0c) と本文鮮度確認は skip して無駄な AskUserQuestion を発火しない
3. **[critical]** **C-3**: deferred 0 件でも Step 0c-2 の **not_planned 残タスク確認はリリース区間ベースで必ず実施**し、`wired in #770` の not_planned close を検出して残タスク行き先を確認している (#817 high finding 対策。deferred 0 で not_planned gate を迂回したら ×)

## Codex 統合 / 撤回 M8 関連 [critical] (全 scenario 共通)

1. **[critical]** **CDX-R-1**: `release-blocker` label は使用しない (M8 撤回確定、2026-05-17 D1)
2. **[critical]** **CDX-R-2**: Step 0b query は `--label "deferred"` のみ、`--label "release-blocker"` を含めない
