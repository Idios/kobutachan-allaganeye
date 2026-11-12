"""reword ループ防止規約の発火点 pin (#1112).

`docs/l2-workflow.md` の (A) PR 内修正優先 規約 にある reword 抑制条項は、#1094 で docs だけに
入り、review 系 skill から一度も参照されていなかった。そのため PR #1108 では 4 ラウンド
連続で「前ラウンドの修正文そのもの」への指摘が再発した (新規 finding 15 件中 10 件)。

規約の**適用**は機械化できない (自然言語の判断)。本テストが見るのは **発火点 (参照行) の
存在** だけである。範囲を過大に主張しないため、ここで断言できるのは「規約の所在と適用語を
同一行に含む行が skill にある」ことまでで、「規約に従ったか」ではない。

判定語を 2 語だけにすると、`reword (A) PR 内修正優先` のような飾り行でも通ってしまう
(Codex adversarial-review [P2])。そのため **SSoT の path / 適用語 / reword の 3 語を同一行に
要求** し、path が実在することまで確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
L2_WORKFLOW = REPO_ROOT / "docs" / "l2-workflow.md"
SKILLS = (
    REPO_ROOT / ".agents" / "skills" / "review-pr" / "SKILL.md",
    REPO_ROOT / ".agents" / "skills" / "iterate-review" / "SKILL.md",
)

# 規約本文 (SSoT) の判定語。表現を変えるときは l2-workflow 側と同時に更新する。
RULE_MARKER = "削除 / SSoT へのポインタ化"
# 発火点の判定語。参照行は 3 語すべてを同一行に含む必要がある。
FIRING_TOKENS = ("docs/l2-workflow.md", "reword", "削除")


def firing_point_lines(text: str) -> list[str]:
    """発火点とみなせる行 (SSoT path / 適用語 / reword を同一行に含む行) を返す。"""
    return [line for line in text.splitlines() if all(t in line for t in FIRING_TOKENS)]


def test_l2_workflow_holds_the_rule() -> None:
    """規約本文が SSoT に存在する (SSoT が空になっていない)。"""
    text = L2_WORKFLOW.read_text(encoding="utf-8")
    assert RULE_MARKER in text, (
        f"`{RULE_MARKER}` が docs/l2-workflow.md に無い。"
        " (A) PR 内修正優先 規約 の reword 抑制条項が削除された可能性がある (#1112)"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skill_reaches_the_rule(skill: Path) -> None:
    """review 系 skill から規約へ到達できる (発火点が存在する)。"""
    text = skill.read_text(encoding="utf-8")
    rel = skill.relative_to(REPO_ROOT).as_posix()
    assert firing_point_lines(text), (
        f"{rel} に reword 抑制規約への発火点が無い。参照行は "
        f"{' と '.join(FIRING_TOKENS)} を同一行に含める必要がある (#1112)"
    )


def test_negative_fixtures_are_not_counted() -> None:
    """飾り行・部分的な行を発火点と誤認しない (Codex [P2] の negative 側)。"""
    assert firing_point_lines("reword (A) PR 内修正優先") == []
    assert firing_point_lines("reword より削除を選ぶ。") == []
    assert (
        firing_point_lines("[docs/l2-workflow.md](docs/l2-workflow.md) を参照。") == []
    )


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_reference_removal_is_detected(skill: Path) -> None:
    """red 実証: 発火点の行を落としたテキストは検出される (no-op でない)。"""
    text = skill.read_text(encoding="utf-8")
    hits = firing_point_lines(text)
    kept = [line for line in text.splitlines() if line not in hits]
    assert firing_point_lines("\n".join(kept)) == [], (
        f"{skill.parent.name} の発火点を除去しても検出できない = pin が no-op"
    )


def test_link_removal_within_the_line_is_detected() -> None:
    """red 実証: 行は残したまま SSoT への参照だけを消すと検出される。"""
    for skill in SKILLS:
        hits = firing_point_lines(skill.read_text(encoding="utf-8"))
        assert hits, f"{skill.parent.name} に発火点が無い"
        stripped = [line.replace("docs/l2-workflow.md", "規約") for line in hits]
        assert firing_point_lines("\n".join(stripped)) == [], (
            f"{skill.parent.name}: 一覧だけ残して参照を消しても通ってしまう"
        )


def test_referenced_sso_exists() -> None:
    """参照先の path が実在する (リンク切れを発火点として数えない)。"""
    assert L2_WORKFLOW.is_file(), f"{L2_WORKFLOW} が存在しない"
