"""PR #1108 本文を「削除 / 参照への置き換え」で再構成する（F48 F50 F27）。"""

from __future__ import annotations

import pathlib

p = pathlib.Path("C:/Users/idios/AppData/Local/Temp/r5.md")
raw = p.read_text(encoding="utf-8")
COMMENT = "https://github.com/Idios/kobutachan-allaganeye/pull/1108#issuecomment-6763751945"

lines = raw.split("\n")


def rep_in(text: str, old: str, new: str) -> str:
    assert old in text, old[:80]
    return text.replace(old, new, 1)


t = raw

# F48①: §A の説明を削除し、事実だけ残す
t = rep_in(
    t,
    "- [x] 受け入れ条件を上記で逐条検証した — **元 issue は無い**（ユーザー直接依頼）。本文の `#N` はすべて、本 PR が起票・編集した issue か文脈上の参照であり**検証対象ではない**（レビュー指摘は `F48` 形式で表記している）。`review-pr` §A の発動条件（本文に `#N` が無いこと）は文言上は満たさないが、**§A の手順に準じて**本 PR 自身の受け入れ条件 5 件で判定した（`enforce-acceptance-criteria` の走査では元 issue は 0 件）。起票した #1106 / #1107 の受け入れ条件は各 issue 側に記載",
    "- [x] 受け入れ条件を上記で逐条検証した — **元 issue なし**（ユーザー直接依頼）。本文の issue 番号は本 PR が起票・編集した issue で、**検証対象ではない**。",
)

# F50②: 説明を削り、検査結果だけにする
t = rep_in(
    t,
    "- [x] docs / 識別子のリネーム時は §「doc 節参照健全性確認」 で grep し残骸ゼロ確認 — 層番号の旧表記を living doc 全域で grep して残存なしを確認（`reference-videos.md` / `design-overview.md` / `issue-policy.md` / `release-process.md` / `bug-report-guide.md`）。**節見出しの改称に伴う参照も grep し直し**、`release-process.md:281/285` の旧見出し名を新名に修正した。日付付き spec `2026-06-29-v030-l3-roadmap.md`（:94 / :119）に残る旧見出し名は、**日付付き spec の本文を書き換えない原則により残す**（対象外）",
    "- [x] docs / 識別子のリネーム時は §「doc 節参照健全性確認」 で grep し残骸ゼロ確認 — living doc の残骸ゼロ（日付付き spec `2026-06-29` の 2 箇所は履歴として残す）",
)

# Fable 行: 件数は 1 箇所だけにし、内訳は書かない
t = rep_in(
    t,
    "- [x] Fable 俯瞰レビュー (#945): **実施 (finding 52 件 / 消化 52 件 / 残 0 件)** （4 ラウンドの累計。Round 1 = 37 件、Round 2 = 新規 7 件 + 前回残り 15 件を再指摘、Round 3 = 新規 3 件 + 前回残り 5 件を再指摘、Round 4 = 新規 5 件 + 前回残り 1 件を再指摘）— CI の起動条件には非該当（test 1 行の変更で doc-only から外れる）だが、Idios 判断で Fable セッションに俯瞰レビューを依頼し、全件を反映した（§レビュー対応）。この起動条件の穴は #1109 で起票",
    f"- [x] Fable 俯瞰レビュー (#945): **実施 (finding 52 件 / 消化 52 件 / 残 0 件)** — CI の起動条件には非該当（test 1 行の変更で doc-only から外れる）だが、Idios 判断で Fable セッションに俯瞰レビューを依頼し、全件を反映した。記録は [レビュー対応]({COMMENT}) を参照。この起動条件の穴は #1109 で起票",
)

# 備考: ラウンド数を削除
t = rep_in(
    t,
    "- **Fable レビュー**: 本 PR は「文書・方針」の変更で推奨トリガーに該当する。CI の起動条件には非該当（test 1 行で doc-only から外れる）だが、Idios 判断で Fable セッションに依頼し **4 ラウンド**実施して全件反映した。起動条件の穴は #1109 で起票。",
    "- **Fable レビュー**: 本 PR は「文書・方針」の変更で推奨トリガーに該当する。CI の起動条件には非該当（test 1 行で doc-only から外れる）だが、Idios 判断で Fable セッションに依頼して全件反映した。起動条件の穴は #1109 で起票。",
)

# F27: Codex の記録を「事実だけ」に置き換える（行単位で差し替え）
lines = t.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("- [x] **Codex adversarial-review"))
end = next(i for i, l in enumerate(lines) if l.startswith("#### 関連ドキュメント"))
new_block = [
    "- [x] **Codex adversarial-review (Iron Law 6 Pre-flight Step 5)**: 実施（`codex-cli 0.167.0`）",
    "  - 実行履歴（HEAD → 結果）: `78aa619`（`--base develop-0.4.0`）→ 0 件 / `78aa619`（focus 付き）→ 0 件 / `754a916`（focus 付き）→ **P2 1 件**（`docs/issue-policy.md` の deferred 運用を §履歴 と §現在の運用 に分離して修正） / `b50a47b`（focus 付き）→ 0 件",
    "  - focus: 境界 × 不可逆操作のペア 0 件を明記し、文書整合の 4 観点を列挙",
    "  - 制約: Python 不在のため自動テスト未実行、`gh` 設定参照は権限で拒否（検証は当セッション実測で代替。Codex 自体は完走）",
    "",
]
lines[start:end] = new_block
t = "\n".join(lines)

# レビュー対応セクションを本文から外し、コメントへのポインタに置き換える
start = t.index("## レビュー対応 (Fable 俯瞰レビュー")
end = t.index("## 備考 (任意)")
t = (
    t[:start]
    + f"## レビュー対応\n\n記録は [コメント]({COMMENT}) にまとめた（本文には置かない — 本文の記述自体がレビュー対象になり、同じ事実が複数箇所に増えるのを避けるため）。\n\n"
    + t[end:]
)

p.write_text(t, encoding="utf-8")
print("ok")
