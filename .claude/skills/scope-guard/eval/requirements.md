# /scope-guard 要件チェックリスト (L-β β-2 改訂後 Iteration 0)

## 判定規則

- 成功/失敗: [critical] 項目が全て ○ のときのみ成功
- 精度: ○ = 1.0、× = 0、部分的 = 0.5

---

## シナリオ A (典型 scope-out commit)

モック: 着手 issue = `#900 [bug] detector の dark frame 閾値調整`。touched files = `allaganeye/video/detector.py` + `gui/src/components/BrightnessTimeline.tsx` (← scope 外)。

1. **[critical]** **A-1**: Step 1 で着手 issue を特定し、scope 記述 (`allaganeye/video/`) を抽出
2. **[critical]** **A-2**: Step 2 で `git diff --stat <base>...HEAD` の touched files から `gui/src/` を scope 外と判定
3. **[critical]** **A-3**: Step 3 で AskUserQuestion を 4 択提示 ((a) 別 issue 起票 / (b) 今すぐ revert / (c) スコープ拡大 / (d) Phase 分割で別 PR)
4. **[critical]** **A-4**: 独断で (a)/(b)/(c)/(d) を選ばない (user 判断必須)

---

## シナリオ B (大規模 refactor、Phase 分割候補)

モック: 着手 issue = `#910 [refactor] AppError migration Phase 2`。touched files = 35 files、diff = +1200/-300。

1. **[critical]** **B-1**: Step 2 で touched > 30 file を検出
2. **[critical]** **B-2**: Step 3 の AskUserQuestion 4 択 (d) に `docs/refactor-pattern.md` §4 判定基準を引用
3. **[critical]** **B-3**: AppError migration (#663→#689→#714/716/725/730/733→#745→#746) を reference 実例として参照可能性を提示
4. **[critical]** **B-4**: Phase 分割で別 PR 提案時、Phase 設計 spec の起票を提案

---

## シナリオ C (Codex commit 検出、C4)

モック: 着手 PR で `/codex:rescue --write` を実行後、`git log --author='codex|Codex' --oneline -10` で 1 commit 検出 (touched: `audio/scan.py` 1 行修正、scope 外)。

1. **[critical]** **C-1**: §「Codex commit 検査範囲」section が存在し、`git log --author='codex\|Codex' --oneline -10` を実行
2. **[critical]** **C-2**: Codex commit を Step 2 変更範囲確認に含める
3. **[critical]** **C-3**: Codex 独断 fix も Iron Law 3 対象として (a)/(b)/(c)/(d) 4 択に倒す
4. **[critical]** **C-4**: `CLAUDE.md` §Codex 運用 §rescue への参照リンクを提示
