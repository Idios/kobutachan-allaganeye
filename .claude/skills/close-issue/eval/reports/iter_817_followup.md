# close-issue empirical-prompt-tuning (#817 番号なし follow-up 宣言チェック追加)

mizchi protocol: <https://github.com/mizchi/skills/blob/main/meta/empirical-prompt-tuning/SKILL-ja.md> §ワークフロー 4 両面評価。fresh subagent (sonnet) を iteration ごとに新規 dispatch (自己再読禁止)。

## 変更概要

Step 5b に「follow-up 宣言の起票漏れ確認 (番号なし、#817 / audit P2-39)」を追加。クローズ対象 PR の本文**およびレビューコメント**に行き先 issue 番号を伴わない follow-up 宣言があれば未追跡残タスクとして (B) 起票提案する。新規 [critical] item 11 を scenario A に追加 (mock: PR #921 レビューコメントに「guard 側で追って対応」)。

## Iteration table

| iter | 変更 | scenario A 成功 | accuracy | 体感 steps | 新規不明瞭点 |
| --- | --- | --- | --- | --- | --- |
| 1 | Step 5b follow-up 節追加後 | ○ (11/11 [critical] ○) | 100% | Read 1 + gh 6 相当 | 0 |
| 2 | (無変更、別 fresh subagent で再評価) | ○ (11/11 [critical] ○) | 100% | Read 1 + gh 6 相当 | 0 |
| 3 | Codex medium 対応 (over-fire 抑制: actionable 限定 + benign 除外 3 条件 + item 12 追加) | ○ (item 11 actionable 発火 ○ / item 12 benign 非発火 ○) | 100% | Read 1 相当 | 0 |

## 構造化 reflection

- iter1/iter2 とも新規不明瞭点ゼロ。item 11 の検出は Step 5b「番号不在こそが死角の証拠」「レビューコメント (`gh pr view --comments`) を明示的に検索対象」記述が一貫して導いた
- 既存 item 1-10 に regression なし (追加は Step 5b 末尾への append のため非破壊)

## 収束判定

iter1 + iter2 で 2 consecutive clears 達成後、Pre-flight Step 5 の Codex adversarial-review が medium「follow-up 検出が benign コメントに過剰発火しうる」を摘出。iter3 で over-fire 抑制 (actionable 未解決の約束に限定 + 解決済み/外部 tracker URL/例示の 3 除外条件 + benign 非発火 item 12) を適用し、actionable 発火と benign 非発火の両立を fresh subagent で確認 (新規不明瞭点ゼロ)。**収束** (Codex finding 解消込み)。
