"""2 回目レビュー (#3 #19 #20 #26 #37 #42 #44) の issue 本文修正。"""

from __future__ import annotations

import pathlib

TMP = pathlib.Path("C:/Users/idios/AppData/Local/Temp")
SPEC_PERMALINK = (
    "https://github.com/Idios/kobutachan-allaganeye/blob/"
    "1804fe8830cdcb6b6ef0fb538301608375c70996/docs/superpowers/specs/"
    "2026-09-10-l4l6-highlight-signal-model-design.md"
)


def load(n: int) -> str:
    return (TMP / f"r2-{n}.md").read_text(encoding="utf-8")


def save(n: int, t: str) -> None:
    (TMP / f"r2-{n}.md").write_text(t, encoding="utf-8")


def rep(t: str, old: str, new: str) -> str:
    assert old in t, old[:60]
    return t.replace(old, new, 1)


# --- #3: 「旧 L5」を期間表記に ---
for n in (1046, 1049):
    t = load(n)
    t = rep(
        t,
        "- レイヤー再編: **L5（OBS プラグイン統合）** の挿入に伴い、旧 L5（価値評価）は **L6**、旧 L6（自動編集）は **L7** になった（`AGENTS.md` §段階的アーキテクチャ）。",
        "- レイヤー再編: **L5（OBS プラグイン統合）** の挿入に伴い、**2026-05-18〜11-10 の L5（価値評価）→ L6**、**同 L6（自動編集）→ L7** になった（`AGENTS.md` §段階的アーキテクチャ）。",
    )
    save(n, t)

# --- #19 / #20: #127 の記述を実装に合わせる ---
t = load(127)
t = rep(
    t,
    "- [ ] `HighlightEvent` のフィールド定義（種別 / 時刻 / 確信度 / **出所（どの検出器か）** / 位置情報）。spec §5.1 の `Signal.detect()` の戻り値と一致させる",
    "- [ ] `HighlightEvent` のフィールド定義。**spec §5.1 の `Signal.detect()` の戻り値と語彙を揃える**（spec は `signal_id` を持つ。種別と出所はその 1 項目に集約できるかを検討する。spec に無いフィールドを足す場合は spec との差分を明記する）",
)
t = rep(
    t,
    "- [ ] 出力先の決定（metadata.json 拡張 or 別 artifact）と `schema_version` の扱い",
    "- [ ] 出力先の決定（metadata.json 拡張 or 別 artifact）と `schema_version` の扱い。**実行時検証は無い**（`jsonschema` は dev 依存）ため、schema は「書込み時に強制される」のではなく「違反を検出できる」ものとして設計する",
)
t = rep(
    t,
    "- [ ] `schemas/**` → TypedDict の codegen 経路（#612）に載せるかの判断。**metadata.json に同居させる場合は必須**（`schemas/metadata.schema.json` は root が `additionalProperties: false` のため、schema を変えないと書き込めない）",
    "- [ ] `schemas/**` → TypedDict の codegen 経路（#612）に載せるかの判断。**metadata.json に同居させる場合は必須**（`schemas/metadata.schema.json` は root が `additionalProperties: false` のため、schema を変えないと**schema 違反になる**）",
)
t = rep(
    t,
    "- [ ] **書き戻し経路**: GUI の［適用］は metadata を読み直して許可リストで組み直すため、未知フィールドは保存時に落ちる（#805 の post_match と同じ経路）。新しい項目を GUI 経由で保持できるかを確認する",
    "- [ ] **書き戻し経路**: GUI の［適用］は root 直下を保持しつつ **match 単位の項目を許可リストで組み直す**ため、**match 単位の未知フィールドは保存時に落ちる**（#805 の post_match と同じ経路）。新しい項目を GUI 経由で保持できるかを確認する",
)
save(127, t)

# --- #26: #140 に層番号注記 / #151 に帰結を追記 ---
t = load(140)
t = rep(
    t,
    "本 issue はその前提で読み替える。\n",
    "本 issue はその前提で読み替える。\n\n"
    "- **層番号の注記**: 本文の「L5（切り出し+サムネ）」は**起票当時の番号**を指す。現在の L5 は OBS プラグイン統合で、切り出し・サムネイルは **L7（自動編集）** にあたる（`AGENTS.md` §段階的アーキテクチャ）。\n",
)
save(140, t)

t = load(151)
t = rep(
    t,
    "本 issue はその前提で読み替える。\n",
    "本 issue はその前提で読み替える。\n\n"
    "- **帰結**: 初期信号（KO / ASSIST インジケータ）は**映像のみ**で判定するため、録画に音声トラックが無いこと自体は検出を妨げない。本リスクが効くのは**将来の音声信号**（VC / SE）を追加する段になってからであり、その時点で再評価する。\n",
)
save(151, t)

# --- #37: #135 の作成行を「更新」に / #1106 の spec リンクを permalink に ---
t = load(135)
t = rep(t, "作成: salty-maple", "更新: salty-maple")
save(135, t)

t = load(1106)
t = rep(
    t,
    "設計の正: [`docs/superpowers/specs/2026-09-10-l4l6-highlight-signal-model-design.md`](../blob/develop-0.4.0/docs/superpowers/specs/2026-09-10-l4l6-highlight-signal-model-design.md)",
    f"設計の正: [`2026-09-10-l4l6-highlight-signal-model-design.md` (permalink)]({SPEC_PERMALINK})",
)
save(1106, t)

# --- #42: #136 / #137 に層番号注記 ---
NOTE = (
    "## 層番号の注記 (2026-11-10)\n\n"
    "本文の層番号は**起票当時の番号**である。2026-11-10 に **L5（OBS プラグイン統合）** を挿入したため、"
    "価値評価は **L6**、自動編集（切り出し・サムネイル・投稿提案）は **L7** になった（`AGENTS.md` §段階的アーキテクチャ）。"
    "本 issue の内容はそのまま **L7** に属する。\n\n---\n\n"
)
for n in (136, 137):
    t = load(n)
    assert "## 層番号の注記 (2026-11-10)" not in t
    save(n, NOTE + t)

# --- #44: #1109 に作成行 + 発見元の誤り修正 ---
t = load(1109)
t = rep(t, "（finding 16）", "（ambiguous_judgments 16）")
if "作成: salty-maple" not in t:
    t = t.rstrip() + "\n\n---\n\n作成: salty-maple\n"
save(1109, t)

print("ok")
