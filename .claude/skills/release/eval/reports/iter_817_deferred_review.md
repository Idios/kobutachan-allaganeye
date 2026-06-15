# release empirical-prompt-tuning (#817 deferred 鮮度/not_planned 確認 + json grep)

mizchi protocol: <https://github.com/mizchi/skills/blob/main/meta/empirical-prompt-tuning/SKILL-ja.md> §ワークフロー 4 両面評価。fresh subagent (sonnet) を iteration ごとに新規 dispatch。

## 変更概要

- Step 0c-2 新設: deferred 本文鮮度突合 (`gh issue edit` 提案) + not_planned close 残タスク検出 (`wired in #N` grep → `stateReason` 確認)
- Step 3-2 version bump grep に `--include='*.json'` 追加 (tauri.conf.json / package.json)
- 新規 [critical]: A-5 (json grep) / B-7 (鮮度) / B-8 (not_planned)

## Iteration table

| iter | 変更 | scenario A | scenario B | 新規不明瞭点 |
| --- | --- | --- | --- | --- |
| 1 | Step 0c-2 + json grep 追加後 | ○ (A-5 ○、全 [critical] ○) | ○ (B-7/B-8 ○、全 [critical] ○) | A: 2 (Step 1 欠番=pre-existing / `git add` が json 非 stage), B: 3 (0c-2 実行順序 / 全件OK時適用 / not_planned grep concrete 欠如) |
| 2 | iter1 reflection 反映 (0c-2 実行順序+全件OK注記 / not_planned concrete grep / `git add` json 注記) | ○ (全 [critical] ○) | ○ (全 [critical] ○、不明瞭点ゼロ) | A: 1 (not_planned が deferred=0 時走るか) + pre-existing Step 1 欠番 / B: 0 |
| 2 後 polish | not_planned は deferred 件数独立で 0 件時も実施、と 1 行明確化 | — | — | (A の in-scope 点を解消) |

## 構造化 reflection (iter1 → iter2 で潰した点)

- **Issue**: 0c-2 の実行順序が bulk pre-check 前後で曖昧 / **Cause**: 「分類の前に」だけで bulk 3 択との順序未明示 / **General Fix Rule**: 新 sub-step は既存 step 群との実行順序を明示する → 「実行順序」見出しで先行実施 + 全件 OK でも省略しない を明記
- **Issue**: not_planned マーカー探索範囲が未規定 / **Cause**: concrete コマンド不在 / **General Fix Rule**: 探索系手順は `git log .. -p | grep` レベルの concrete 例を添える → grep + `gh issue view --json stateReason` の 2 コマンド例を追加
- **Issue**: `git add pyproject.toml` 単体だと *.json bump が非 stage / **Cause**: grep 拡張と commit 例の不整合 / **General Fix Rule**: 確認 grep を広げたら stage 例も同期 → `git add` にコメント + json 例追加

## scope 外 (deferred)

- **Step 0b「件数 0 → Step 1 へ skip」の Step 1 欠番**: pre-existing (本 #817 の変更と無関係、Step 番号は 0a/0b/0c/2/3 で Step 1 が存在しない)。N2 scope 外のため本 PR では修正せず別途処理 (PR 本文备考に記載)

## 収束判定

全 [critical] (A-5/B-7/B-8 + 既存) が iter1/iter2 とも ○。iter1 の細部不明瞭点は iter2 で解消 (scenario B は不明瞭点ゼロ)、scenario A の in-scope 残点 (not_planned×deferred0) は iter2 後 1 行 polish で解消。**構造的欠陥 (新 step / grep 不在) は解消**したため mizchi 収束条件「構造的欠陥解消時点での打ち切り可」に基づき収束。pre-existing Step 1 欠番は deferred。
