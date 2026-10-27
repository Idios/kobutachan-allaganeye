"""Tests for scripts/check_agent_migration_sweep.py (#1041/#1042 再発防止).

保護機構は不発でも green になるため、本テストは **違反を注入して exit code の
生値を観測する** 形で書く (`test_check_doc_code_refs.py` / `test_check_changelog_style.py`
と同じ規律)。正常系だけを見て「ガードがある」と判断しない。

本 file が特に固定するのは **scope** である:
- 検査対象 = living doc (`.md` / `.sh` の doc / skill / hook / AGENTS.md / README)。
- コードファイル (`.py` / `.js` / `.ts` / `.rs` / `.ps1` / `.yml`) は `_SCAN_EXTS` の
  allowlist (living doc のみ) により対象外。CHANGELOG、eval fixture
  (`.agents/skills/**/eval/**`)、`docs/superpowers/**` (dated 以外も含む)、
  archive、audits は対象外 (#1044)。
- GUI ソースは screenshot-freshness 回避のため対象外。
- `build-cache/` は build キャッシュ置き場のため対象外 (#1066)。
- コードコメントの旧参照は #1076 で追跡する (#1044 は未参照ファイルの削除が範囲)。
- `.claude/agents/**` は Claude Code 用のロール定義 (`model:` frontmatter が Claude
  エイリアスのみ) のため対象外 (旧 invocation 契約は #1068)。
- slash command の正規表現は path / branch 名の `/release` 等を誤検出しない
  (`(?<![a-z0-9._-])` + `(?![a-z0-9._-])` の前後境界)。
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_agent_migration_sweep.py"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
CI_YML_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

_spec = importlib.util.spec_from_file_location(
    "check_agent_migration_sweep", SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------
# regex: slash command 検出 vs path 誤検出
# --------------------------------------------------------------------------

# (label, text) -- いずれも「slash command を検出する」べき。
_SLASH_POSITIVE: list[tuple[str, str]] = [
    ("backtick", "実行時は `/review-pr` を呼ぶ"),
    ("space-wrapped", "-> /release [patch|minor|major] で bump"),
    ("leading", "/iterate-review <PR#> で処理"),
    ("paren", "(/scope-guard を呼ぶ)"),
]

# (label, text) -- いずれも「slash command と誤検出してはならない」。
_SLASH_NEGATIVE: list[tuple[str, str]] = [
    ("skill-dir-path", "参照: `.agents/skills/review-pr/SKILL.md`"),
    ("branch-name", "push run (`github.ref=refs/heads/release/vX`)"),
    ("url-path", "https://img.shields.io/github/v/release/Idios/x"),
    ("cargo-target", "# gui/src-tauri/target/release/allaganeye-gui.exe"),
]


# --------------------------------------------------------------------------
# regex: 主エージェント=Claude の旧表記 検出 vs 維持対象の誤検出 (#1066)
# --------------------------------------------------------------------------

# (label, text) -- いずれも「主エージェント=Claude の旧表記を検出する」べき。
_CLAUDE_AGENT_POSITIVE: list[tuple[str, str]] = [
    ("subject-ha", "Claude は自動的に段階を進め、要所で判断を仰ぐ"),
    ("subject-ga", "Claude が `gh` コマンドを発行する"),
    ("possessive-no", "ユーザーが Claude の判断を訂正した場合、蓄積する"),
    ("host-uchi", "Stage 1: Claude 内 fresh subagent が実装"),
    ("main", "Stage 2: controller (Claude main) が到達確認"),
    ("thinking-body", "superpowers subagent (Claude 思考体) と Codex"),
    ("code-fallback", "Claude Code fallback は同一 model の self-review に近い"),
    ("fallback-de", "(B) Claude fallback で push する"),
    ("fallback-ha", "Claude fallback は同一 model の self-review に近い"),
    ("fallback-slash", "(再試行 / Claude fallback / abort) 3 択"),
    ("paren-eq-plus", "エージェント (= Claude + 人間メンテナ Idios) が手動で実行する"),
    (
        "code-session-ugoku",
        "メンテナ (= Claude Code セッションで動くアシスタント) が受領する",
    ),
    ("code-no-plan", "Claude Code の plan モード (ExitPlanMode ツール) を活用し"),
    # tradeoff pin: 主語形は助詞のみで判定するため、維持対象の文脈でも検出される
    # (FP 側に倒す設計)。narrow 化が silent に入らないよう現挙動を pin する。
    (
        "claude-maintenance-context-tradeoff",
        "Claude が復旧したら再レビューを依頼する",
    ),
]

# (label, text) -- いずれも「誤検出してはならない」維持対象 (レビュー専用ツール / 製品名)。
_CLAUDE_AGENT_NEGATIVE: list[tuple[str, str]] = [
    (
        "claude-code",
        "Claude Code / Fable / Kimi Code は別途セッションを起動して利用する",
    ),
    ("claude-fable", "全体レビュー・相談は Claude Fable 最新に依頼する"),
    ("claude-sonnet", "中難度定型は Claude Sonnet 最新 / DeepSeek V4 Flash"),
    (
        "claude-design",
        "Claude Design (claude.ai/design) からエクスポートされた handoff bundle",
    ),
    (
        "fallback-notice",
        "> **Claude fallback notice**: 本成果物のレビューは Claude 不可のため DeepSeek が代行した",
    ),
    ("section-heading", "## Claude fallback（Claude レビュー不可時）"),
    (
        "claude-opus-fable",
        "Claude（Opus / Fable）復旧後に再レビューしてから merge する",
    ),
    ("codex-independent", "Codex 本体は Claude と独立である"),
    ("claude-kaifuku", "Claude 復旧後の再レビューを推奨する"),
    (
        "claude-review-noun",
        "Claude レビューが使えない状況で DeepSeek がレビューを代行した",
    ),
    ("claude-code-slash", "Claude Code のスラッシュコマンドは invoke 不可"),
    ("claude-code-subagent", "DeepSeek は Claude Code の subagent になれない"),
    ("claude-code-session-review", "別途 Claude Code セッションで review 依頼"),
    ("claude-ni-review", "Claude に再レビューを依頼する"),
    ("claude-no-review", "Claude のレビュー結果を突合する"),
    ("claude-no-rereview", "Claude の再レビューを推奨する"),
    ("claude-no-usage", "Claude の usage limit 時"),
    ("claude-no-permission", "Claude の permission prompt を表示する"),
    ("claude-no-session", "Claude のセッション起動"),
    ("claude-no-memory", "Claude の auto-memory"),
    ("claude-no-slash", "Claude のスラッシュコマンド"),
    # whitelist の残り 7 語 (#1066 Round 2)。whitelist は FP 抑制の唯一の契約なので、
    # 各語が実際に branch を抑止することを pin する。
    ("claude-no-kaifuku", "Claude の復旧を待つ"),
    ("claude-no-fuka", "Claude の不可時は DeepSeek が代行する"),
    ("claude-no-code-interpreter", "Claude の Code Interpreter を使う"),
    ("claude-no-fable", "Claude の Fable 最新版に依頼する"),
    ("claude-no-sonnet", "Claude の Sonnet 環境で実行する"),
    ("claude-no-opus", "Claude の Opus モデルを選ぶ"),
    ("claude-no-design", "Claude の Design 資料を参照する"),
]


@pytest.mark.parametrize(("label", "text"), _SLASH_POSITIVE, ids=lambda v: str(v)[:24])
def test_slash_command_is_detected(label: str, text: str) -> None:
    assert guard._SLASH_RE.search(text), f"{label} が slash command と見なされなかった"


@pytest.mark.parametrize(("label", "text"), _SLASH_NEGATIVE, ids=lambda v: str(v)[:24])
def test_path_like_slash_is_not_detected(label: str, text: str) -> None:
    assert guard._SLASH_RE.search(text) is None, (
        f"{label} が slash command と誤検出された: {guard._SLASH_RE.search(text)}"
    )


@pytest.mark.parametrize(
    ("label", "text"), _CLAUDE_AGENT_POSITIVE, ids=lambda v: str(v)[:24]
)
def test_claude_agent_old_term_is_detected(label: str, text: str) -> None:
    assert guard._CLAUDE_AGENT_RE.search(text), (
        f"{label} が主エージェント=Claude の旧表記と見なされなかった"
    )


@pytest.mark.parametrize(
    ("label", "text"), _CLAUDE_AGENT_NEGATIVE, ids=lambda v: str(v)[:24]
)
def test_kept_claude_term_is_not_detected(label: str, text: str) -> None:
    assert guard._CLAUDE_AGENT_RE.search(text) is None, (
        f"{label} が主エージェント=Claude の旧表記と誤検出された: "
        f"{guard._CLAUDE_AGENT_RE.search(text)}"
    )


def test_slash_skills_list_is_non_empty() -> None:
    assert guard._SLASH_SKILLS, "_SLASH_SKILLS が空"


def test_slash_skills_match_actual_skill_dirs() -> None:
    """`_SLASH_SKILLS` は `.agents/skills/` の実体と一致する (#1069)。

    dangling entry (`test-pr` のように実在しない skill) が検出対象に残ると、
    「その skill がある」と誤認させる。逆に実在する skill をリストに入れ忘れると、
    その slash 表記がすり抜ける。
    """
    skills_dir = REPO_ROOT / ".agents" / "skills"
    actual = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert set(guard._SLASH_SKILLS) == actual


def test_literal_terms_list_is_non_empty() -> None:
    assert guard._LITERAL_TERMS, "_LITERAL_TERMS が空"


def test_codex_old_terms_list_is_non_empty() -> None:
    assert guard._CODEX_OLD_TERMS, "_CODEX_OLD_TERMS が空 (#1043)"


def test_codex_old_terms_cover_invocation_contract() -> None:
    """Codex 呼び出し契約の旧表記 (companion script / plugin path / env var) を覆う。"""
    assert "codex-companion.mjs" in guard._CODEX_OLD_TERMS
    assert "CLAUDE_PLUGIN_ROOT" in guard._CODEX_OLD_TERMS
    assert ".claude/plugins" in guard._CODEX_OLD_TERMS


# --------------------------------------------------------------------------
# meta: 各分岐 / 各 literal に fixture があることを強制する (#1075)
#
# 向きの定義 (本 file で統一):
#   positive = 検出されるべき入力 / negative = 検出されてはならない入力。
# --------------------------------------------------------------------------

_CLAUDE_BRANCH_SAMPLES: dict[str, str] = {
    "subject": "Claude が `gh` コマンドを発行する",
    "ownership": "ユーザーが Claude の判断を訂正した場合",
    "code-fallback": "Claude Code fallback は同一 model の self-review",
    "fallback-particle": "Claude fallback で push する",
    "fallback-slash": "(再試行 / Claude fallback / abort) 3 択",
    "equals-plus": "エージェント (= Claude + 人間メンテナ Idios)",
    "code-session": "メンテナ (= Claude Code セッションで動くアシスタント)",
    "code-plan": "Claude Code の plan モードを活用する",
}


def test_every_claude_branch_has_a_sample() -> None:
    """分岐の追加・削除と sample の対応を pin する (片方だけ更新されると落ちる)。"""
    branches = {name for name, _ in guard._CLAUDE_AGENT_BRANCHES}
    assert branches == set(_CLAUDE_BRANCH_SAMPLES)


@pytest.mark.parametrize(
    ("name", "pattern"),
    guard._CLAUDE_AGENT_BRANCHES,
    ids=[name for name, _ in guard._CLAUDE_AGENT_BRANCHES],
)
def test_claude_branch_detects_its_sample(name: str, pattern: str) -> None:
    assert re.search(pattern, _CLAUDE_BRANCH_SAMPLES[name]), (
        f"{name} の sample が検出されない"
    )


@pytest.mark.parametrize(
    ("name", "pattern"),
    guard._CLAUDE_AGENT_BRANCHES,
    ids=[name for name, _ in guard._CLAUDE_AGENT_BRANCHES],
)
def test_claude_branch_removal_breaks_its_sample(name: str, pattern: str) -> None:
    """分岐を 1 つ外すと、その sample が検出されなくなる。

    これが無いと「sample が別の分岐にも当たっている」状態を見逃し、
    分岐を削除しても test が green のままになる。
    """
    reduced = [p for n, p in guard._CLAUDE_AGENT_BRANCHES if n != name]
    assert reduced, "全分岐を外すと検査が空になる"
    regex = re.compile("|".join(f"(?:{p})" for p in reduced))
    assert regex.search(_CLAUDE_BRANCH_SAMPLES[name]) is None, (
        f"{name} を外しても sample が検出される (= 他の分岐と重複している)"
    )


# literal 系 2 class の positive fixture。key は checker の list と完全一致させる。
_LITERAL_POSITIVE: dict[str, str] = {
    ".claude/skills": "旧 `.claude/skills` 配下を参照する",
    "CLAUDE.md": "`CLAUDE.md` に書かれている",
}
_CODEX_OLD_POSITIVE: dict[str, str] = {
    "codex-companion.mjs": "`codex-companion.mjs review` を実行する",
    "CLAUDE_PLUGIN_ROOT": "`CLAUDE_PLUGIN_ROOT` を参照する",
    ".claude/plugins": "`.claude/plugins/openai-codex` 配下",
}
_PLUGIN_OLD_POSITIVE: dict[str, str] = {
    "superpowers:": "`superpowers:brainstorming` を invoke する",
    "subagent-driven-development": "`subagent-driven-development` の Task 実装",
    "requesting-code-review": "`requesting-code-review` 相当を代行する",
    "systematic-debugging": "`systematic-debugging` 相当で調査する",
    "GPT-5.4": "Codex (GPT-5.4) の second opinion",
}

# negative = 置換後の正 / 無関係な正当参照 (検出されてはならない)。
# **class 単位で保持**し、各 class に 1 件以上あることを test が要求する
# (AGENTS.md の用語 sweep 完全性 checklist にある「positive / negative 両 fixture 必須」を
# negative 側でも機械検査する。iterate-review Round 2 の finding)。
_LITERAL_NEGATIVE_BY_CLASS: dict[str, list[tuple[str, str]]] = {
    "literal": [
        ("replacement-skills", "`.agents/skills/review-pr/SKILL.md`"),
        ("replacement-agents", "`AGENTS.md` を参照"),
        ("legit-claude-settings", "`.claude/settings.json` を編集"),
        ("legit-env", "`CLAUDE_PROJECT_DIR` を使う"),
    ],
    "codex-old": [
        ("new-cli", "`codex review --base <base>` を実行"),
    ],
    "plugin-old": [
        # 出典帰属 / 方式名としての言及は維持対象 (#1064)。bare 語で持つとここが誤検出になる
        ("superpowers-attribution", "`obra/superpowers` の pattern に倣う"),
        ("superpowers-parenthetical", "session-start.sh は superpowers 方式"),
        ("model-agnostic", "Codex は独立 model の second opinion"),
        # 上流 skill への帰属 URL は維持対象 (Codex adversarial-review の P2)
        (
            "upstream-skill-url",
            "https://github.com/obra/superpowers/tree/main/skills/systematic-debugging/SKILL.md",
        ),
        (
            "upstream-skill-url-branch-name",
            "[skill](https://github.com/obra/superpowers/tree/main/skills/requesting-code-review)",
        ),
        # scheme 無しの URL / repo 内 anchor も出典参照として維持する
        (
            "upstream-scheme-less-url",
            "github.com/obra/superpowers/tree/main/skills/systematic-debugging/SKILL.md を参照",
        ),
        ("internal-anchor", "docs/guide.md#systematic-debugging-section を見よ"),
        # markdown リンクの label が上流 skill 名の場合は出典帰属として許容する
        # (Round 1 Q2=(a) の「帰属は維持対象」と同方向。Round 5 の ambiguous をこの向きで確定)
        (
            "markdown-link-label-attribution",
            "[superpowers:brainstorming](https://github.com/obra/superpowers/tree/main/skills/brainstorming)",
        ),
    ],
}
_LITERAL_NEGATIVE: list[tuple[str, str]] = [
    item for items in _LITERAL_NEGATIVE_BY_CLASS.values() for item in items
]
# positive fixture を class 単位で束ねたもの (registry との一致を meta-test が要求する)。
_POSITIVE_BY_GROUP: dict[str, dict[str, str]] = {
    "literal": _LITERAL_POSITIVE,
    "codex-old": _CODEX_OLD_POSITIVE,
    "plugin-old": _PLUGIN_OLD_POSITIVE,
}
# registry を持たない語 list (slash command は regex で検査する。exclusion glob は
# 用語ではないため、いずれも対象外)。
_ALLOWED_UNREGISTERED_TERM_LISTS = {"_SLASH_SKILLS", "_EXCLUDED_GLOBS"}


def _literal_hits(text: str) -> list[str]:
    """checker と同じ判定で literal 一致を返す (registry 駆動。URL 除外を尊重)。"""
    hits: list[str] = []
    for terms, _label, strip_urls in guard._LITERAL_TERM_GROUPS.values():
        haystack = guard._URL_RE.sub("", text) if strip_urls else text
        hits += [t for t in terms if t in haystack]
    return hits


def test_literal_terms_have_positive_fixtures() -> None:
    assert set(_LITERAL_POSITIVE) == set(guard._LITERAL_TERMS)


def test_codex_old_terms_have_positive_fixtures() -> None:
    assert set(_CODEX_OLD_POSITIVE) == set(guard._CODEX_OLD_TERMS)


def test_plugin_old_terms_list_is_non_empty() -> None:
    assert guard._PLUGIN_OLD_TERMS, "_PLUGIN_OLD_TERMS が空 (#1064)"


def test_plugin_old_terms_have_positive_fixtures() -> None:
    assert set(_PLUGIN_OLD_POSITIVE) == set(guard._PLUGIN_OLD_TERMS)


def test_every_literal_class_has_negative_fixtures() -> None:
    """literal 系の各 class に positive / negative fixture がそろっている。

    checker の `_LITERAL_TERM_GROUPS` が literal 系 class の単一の正であるため、
    group を追加すると fixture （positive / negative 両方）を足すまで red になる。
    """
    groups = guard._LITERAL_TERM_GROUPS
    assert set(_POSITIVE_BY_GROUP) == set(groups), "新 class の positive fixture が無い"
    assert set(_LITERAL_NEGATIVE_BY_CLASS) == set(groups), (
        "新 class の negative fixture が無い"
    )
    for class_name, (terms, _label, _strip_urls) in groups.items():
        assert set(_POSITIVE_BY_GROUP[class_name]) == set(terms), (
            f"{class_name}: positive fixture が list と不一致"
        )
        assert _LITERAL_NEGATIVE_BY_CLASS[class_name], (
            f"{class_name}: negative fixture が空"
        )


@pytest.mark.parametrize(
    ("group", "term"),
    [
        (group, term)
        for group in _POSITIVE_BY_GROUP
        for term in _POSITIVE_BY_GROUP[group]
    ],
    ids=[
        f"{group}:{term}"
        for group in _POSITIVE_BY_GROUP
        for term in _POSITIVE_BY_GROUP[group]
    ],
)
def test_each_positive_fixture_is_detected_by_check_sweep(
    tmp_path: Path, group: str, term: str
) -> None:
    """positive fixture を **1 語ずつ** checker 本体 (check_sweep) に食わせて発火確認。

    `_literal_hits` は fixture 側の mirror であり、checker 本体が語を取り損ねても
    気付きにくい。group を一括で流すと 1 語の壊れが他の語で masking されるため、
    語単位で E2E 検証する (`term` は ids と可読性のため受け取る)。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        _POSITIVE_BY_GROUP[group][term] + "\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1, f"{group}:{term} が検出されない"


def test_registry_covers_all_term_lists() -> None:
    """`_LITERAL_TERM_GROUPS` に未登録の語 list を作らない。

    未登録の list は `check_sweep` から見えないため、fixture を要求する
    上記 test もすり抜ける。**命名規約に依存せず** `vars(guard)` の list[str]
    を全部走査し、登録漏れを red にする。
    """
    registered = {
        id(terms) for terms, _label, _strip_urls in guard._LITERAL_TERM_GROUPS.values()
    }
    unregistered = sorted(
        name
        for name, value in vars(guard).items()
        if isinstance(value, list)
        and value
        and all(isinstance(item, str) for item in value)
        and name not in _ALLOWED_UNREGISTERED_TERM_LISTS
        and id(value) not in registered
    )
    assert not unregistered, f"_LITERAL_TERM_GROUPS に未登録の語 list: {unregistered}"


@pytest.mark.parametrize(
    ("term", "text"), _LITERAL_POSITIVE.items(), ids=list(_LITERAL_POSITIVE)
)
def test_literal_positive_fixtures_are_detected(term: str, text: str) -> None:
    assert term in text, f"fixture 自体が term を含まない: {term}"
    assert _literal_hits(text) == [term], (
        f"検出結果が term 1 件でない: {_literal_hits(text)}"
    )


@pytest.mark.parametrize(
    ("term", "text"), _CODEX_OLD_POSITIVE.items(), ids=list(_CODEX_OLD_POSITIVE)
)
def test_codex_old_positive_fixtures_are_detected(term: str, text: str) -> None:
    assert term in text, f"fixture 自体が term を含まない: {term}"
    assert _literal_hits(text) == [term], (
        f"検出結果が term 1 件でない: {_literal_hits(text)}"
    )


@pytest.mark.parametrize(
    ("term", "text"), _PLUGIN_OLD_POSITIVE.items(), ids=list(_PLUGIN_OLD_POSITIVE)
)
def test_plugin_old_positive_fixtures_are_detected(term: str, text: str) -> None:
    assert term in text, f"fixture 自体が term を含まない: {term}"
    assert _literal_hits(text) == [term], (
        f"検出結果が term 1 件でない: {_literal_hits(text)}"
    )


@pytest.mark.parametrize(
    ("label", "text"), _LITERAL_NEGATIVE, ids=[label for label, _ in _LITERAL_NEGATIVE]
)
def test_literal_negative_fixtures_are_not_detected(label: str, text: str) -> None:
    assert _literal_hits(text) == [], f"{label} が誤検出された: {_literal_hits(text)}"


# --------------------------------------------------------------------------
# scope: 検査対象 (living doc) vs 除外 (historical / deferred)
# --------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> None:
    """最小の repo 骨格を作る (AGENTS.md が必須 anchor)。"""
    (tmp_path / "AGENTS.md").write_text("# Allagan Eye\n", encoding="utf-8")


def _run_repo_result(repo_root: Path) -> subprocess.CompletedProcess[str]:
    """checker を subprocess で起動し、exit code と stdout / stderr を返す。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _run_repo(repo_root: Path) -> int:
    return _run_repo_result(repo_root).returncode


def test_runtime_messages_are_pinned(tmp_path: Path) -> None:
    """実行時メッセージの header / hint 文言を pin する (#1066)。

    宣言 (docstring / `ci.yml` comment) と発火側の文言が乖離すると、違反時に
    保守者が誤った原因を読む。文言の revert が silent に通らないようにする。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "old.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    result = _run_repo_result(tmp_path)
    assert result.returncode == 1
    assert "旧用語残存 または 検査不能" in result.stderr
    assert "Zed + DeepSeek" in result.stderr
    # per-violation label と `.claude/agents/**` の帰属行 (#1068) も pin する
    assert "主エージェント=Claude の旧表記残存" in result.stderr
    assert "#1068" in result.stderr
    # hint の除外列挙も pin する (宣言側 drift を止める)
    assert "archive / audits" in result.stderr
    assert ".claude/agents/**" in result.stderr
    # 本 PR で hint に追加した除外列挙も pin する (宣言 spot の 1 つである以上、
    # 新規文言を assert なしで追加しない)
    assert "`_SCAN_EXTS` の allowlist が living doc のみを走査するため" in result.stderr
    assert (
        "`build-cache/` は build キャッシュ置き場のため対象外 (#1066)" in result.stderr
    )
    assert "コードコメントの旧参照は #1076 で追跡する" in result.stderr
    assert "「独立 model」へ置換すること (#1064)" in result.stderr


# 宣言の正 (#1073)。検出 class は 3 spot / exit code は 2 spot / 除外の帰属は 3 spot。
# runtime hint は `test_runtime_messages_are_pinned` が pin する。
# spot 間で表記を変えるときは、ここも同時に更新すること。
_DETECTION_CLASS_TOKENS = (
    "slash command",
    "旧 path",
    "主エージェント=Claude",
    "旧 invocation 契約",
    "Claude Code plugin 旧表記",
)
# 除外 class の帰属は「その class を名指しする bullet」単位で pin する
# (whole-file の部分一致だと、別行の同 token が帰属行の drift を mask する)
_ATTRIBUTION_RULES = (
    ("build-cache", "#1066"),
    (".claude/agents/", "#1068"),
)
_FORBIDDEN_IN_BULLET = (("screenshot-freshness", "#1044"),)


def _agents_declaration_section() -> str:
    """AGENTS.md の「用語 sweep 完全性 checklist」節の本文 (次の `## ` 見出しまで)。"""
    lines = AGENTS_PATH.read_text(encoding="utf-8").splitlines()
    start = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("## 用語 sweep 完全性 checklist")
    )
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _bullet_containing(lines: list[str], index: int) -> str:
    """`index` 行を含む箇条書き (直近の `- ` 始まりから次の `- ` まで) を返す。"""
    start = index
    while start > 0 and not lines[start].lstrip().startswith("- "):
        start -= 1
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("- "):
        end += 1
    return "\n".join(lines[start:end])


def _test_module_docstring() -> str:
    return (
        ast.get_docstring(ast.parse(Path(__file__).read_text(encoding="utf-8"))) or ""
    )


def test_declarations_are_consistent_across_spots() -> None:
    """宣言 spot 間の一致を pin する (#1073 / #1075 の一部前倒し)。

    人手レビューだけだと「1 spot ずつ直して次の spot が見つかる」ループが続く
    (PR #1077 で実測 14 findings 中 8 件が修正工程由来)。class 名 / exit code 語 /
    除外の帰属を機械検証し、この class を CI で閉じる。
    """
    # (1) 検出 class の宣言: 列挙行 / docstring / ci.yml の宣言コメントブロックに限定する。
    # whole-file の部分一致だと、別行に同 token がある場合に宣言行の drift を mask する。
    agents_section = _agents_declaration_section()
    class_lines = [ln for ln in agents_section.splitlines() if "5 class" in ln]
    assert len(class_lines) == 1, "AGENTS.md の class 列挙行が 1 行ではない"
    for token in _DETECTION_CLASS_TOKENS:
        assert token in class_lines[0], f"AGENTS.md: class 列挙行に無い: {token}"

    doc = guard.__doc__ or ""
    for token in _DETECTION_CLASS_TOKENS:
        assert token in doc, f"module docstring に無い: {token}"
    assert "検査不能 (fail-closed)" in doc, "module docstring に exit 1 の語が無い"

    ci_lines = CI_YML_PATH.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(ci_lines) if "用語 sweep 完全性 gate" in ln)
    # `exit 1 =` は他の job にも現れるため、宣言ブロックの開始以降で探す
    end = next(i for i, ln in enumerate(ci_lines[start:], start) if "exit 1 =" in ln)
    ci_block = "\n".join(ci_lines[start : end + 1])
    for token in _DETECTION_CLASS_TOKENS:
        assert token in ci_block, f"ci.yml: 宣言ブロックに無い: {token}"
    assert "検査不能 (fail-closed)" in ci_block, "ci.yml: exit 1 の語が無い"

    # exit code の語は上の 2 spot (docstring / ci.yml 宣言ブロック) で検査済み。

    # (2) 除外 class の帰属: 「その class を名指しする bullet」の中に issue 番号があること
    spots = (
        ("AGENTS.md", _agents_declaration_section()),
        ("checker docstring", guard.__doc__ or ""),
        ("test docstring", _test_module_docstring()),
    )
    for name, text in spots:
        # marker 自体の存在を要求する (bullet ごと削除されると bullet 検査が空振りする)
        for marker, _issue in _ATTRIBUTION_RULES:
            assert marker in text, f"{name}: 除外 class の宣言が無い: {marker}"
        for marker, _forbidden in _FORBIDDEN_IN_BULLET:
            assert marker in text, f"{name}: 除外 class の宣言が無い: {marker}"
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for marker, issue in _ATTRIBUTION_RULES:
                if marker in line:
                    bullet = _bullet_containing(lines, i)
                    assert issue in bullet, (
                        f"{name}: {marker} の bullet に {issue} が無い: {bullet.strip()}"
                    )
            for marker, forbidden in _FORBIDDEN_IN_BULLET:
                if marker in line:
                    bullet = _bullet_containing(lines, i)
                    assert forbidden not in bullet, (
                        f"{name}: {marker} の bullet に {forbidden} が混入: "
                        f"{bullet.strip()}"
                    )

    # (3) 履歴記録 / コードコメントの帰属は各 spot に存在すること (presence)
    for name, text in spots:
        for token in ("#1044", "#1076"):
            assert token in text, f"{name}: 帰属が無い: {token}"

    # `gui/**` の宣言は module docstring 内で 1 回だけ (重複行の再発防止)
    assert (guard.__doc__ or "").count("`gui/**` は GUI ソースのため") == 1


def test_clean_repo_passes(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.md").write_text(
        "# バージョニング\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_living_doc_slash_command_is_exit_1(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.md").write_text(
        "# バージョニング\n\n`/release` で bump する。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_old_path_is_exit_1(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n`.claude/skills/` を参照。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_codex_companion_is_exit_1(tmp_path: Path) -> None:
    """Codex 呼び出し契約の旧表記 (codex-companion.mjs) 残存は exit 1 (#1043)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n`codex-companion.mjs` を実行。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_claude_agent_old_term_is_exit_1(tmp_path: Path) -> None:
    """主エージェント=Claude の旧表記残存は exit 1 (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\nClaude は自動的に段階を進め、要所で判断を仰ぐ。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_plugin_old_term_is_exit_1(tmp_path: Path) -> None:
    """Claude Code plugin 旧表記の残存は exit 1 (#1064)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n`superpowers:brainstorming` を invoke する。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_old_term_after_fullwidth_bracket_is_exit_1(
    tmp_path: Path,
) -> None:
    """全角括弧で囲んだ URL の直後の旧用語も検出する (#1064、Round 3 finding)。

    日本語では `出典（https://example.com）によれば<旧用語>を使う` のように全角で URL を
    囲むため、打ち切り文字に全角の閉じ記号が無いと検出漏れになる。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n"
        "出典（https://github.com/obra/superpowers）によればsystematic-debuggingを使う。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_old_term_after_bare_url_is_exit_1(tmp_path: Path) -> None:
    """scheme 付き bare URL 直後 (非 ASCII 散文) の旧用語も検出する (#1064、Round 4)。

    URL の打ち切りを記号列挙にすると、日本語散文が続く場合に打ち切れず
    行末まで飲み込んで検出漏れになる。ASCII 肯定形で切り出すことを pin する。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n"
        "詳細はhttps://example.comを参照してsystematic-debuggingを実行する。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_canonical_slash_form_is_exit_1(tmp_path: Path) -> None:
    """plugin skill の canonical 呼び出し形 (`/superpowers:...`) も検出する。

    先頭スラッシュがあると scheme 無し URL 分岐にパスとして食われ、第 5 class の
    主語が素通りしていた (Round 5 finding)。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n`/superpowers:brainstorming` を起動する。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_upstream_skill_url_passes(tmp_path: Path) -> None:
    """上流 skill への帰属 URL は exit 0 (#1064、Codex adversarial-review の P2)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n"
        "https://github.com/obra/superpowers/tree/main/skills/systematic-debugging/SKILL.md\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 0


def test_living_doc_old_term_after_markdown_link_is_exit_1(tmp_path: Path) -> None:
    r"""URL 直後 (空白なし) の旧用語も検出する (#1064、Round 2 finding)。

    日本語散文は語間に空白を置かないため、URL を `\S+` で消費すると行末まで
    飲み込んで検出漏れになる。閉じ括弧 / 引用符で打ち切ることを E2E で pin する。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n"
        "[仕様](https://example.com/spec)に従い、`systematic-debugging` を実行する。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_kept_claude_terms_pass(tmp_path: Path) -> None:
    """維持対象 (Claude Code / Fable / Design / fallback notice) は exit 0 (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\nClaude Code / Claude Fable / Claude Design をレビュー専用とする。\n"
        "> **Claude fallback notice**: 本成果物のレビューは Claude 不可のため代行した。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 0


def test_hook_file_is_scanned(tmp_path: Path) -> None:
    """hook (session-start.sh) の slash 残存も検出する (Round 5 の再発事象)。"""
    _make_repo(tmp_path)
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "session-start.sh").write_text(
        "cat <<'EOF'\n- `/review-pr` 実行時は...\nEOF\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_changelog_is_excluded(tmp_path: Path) -> None:
    """CHANGELOG の旧 slash 表記は歴史記録 (既リリース節) なので対象外。"""
    _make_repo(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n- `/close-issue` skill 新設 (#594)\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_code_file_is_excluded(tmp_path: Path) -> None:
    """コードファイルのコメント旧参照は #1076 で追跡するため対象外。"""
    _make_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_version_consistency.py").write_text(
        "# `/release` の手元実行が壊れる。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_gui_source_is_excluded(tmp_path: Path) -> None:
    """`gui/**` 配下は `.md` でも検査対象外 (screenshot-freshness 回避)。"""
    _make_repo(tmp_path)
    (tmp_path / "gui" / "src").mkdir(parents=True)
    (tmp_path / "gui" / "src" / "README.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_docs_archive_is_excluded(tmp_path: Path) -> None:
    """`docs/archive/**` は履歴記録として検査対象外 (#1044)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs" / "archive" / "old.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_superpowers_dir_is_excluded(tmp_path: Path) -> None:
    """`docs/superpowers/**` は履歴記録 (dated plans / specs 含む) として対象外。"""
    _make_repo(tmp_path)
    plans = tmp_path / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True)
    (plans / "2026-01-01-old.md").write_text(
        "旧 `.claude/skills` 配下を参照する。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_audits_dir_is_excluded(tmp_path: Path) -> None:
    """`docs/audits/**` は当時の監査記録として対象外。"""
    _make_repo(tmp_path)
    audits = tmp_path / "docs" / "audits"
    audits.mkdir(parents=True)
    (audits / "2026-01-01-audit.md").write_text(
        "`CLAUDE.md` を参照する。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_build_cache_dir_is_skipped(tmp_path: Path) -> None:
    """`build-cache/` は Portable ZIP の build キャッシュ置き場なので検査対象外 (#1066)。

    red 実証の展開先は repo 外を推奨するが、repo 内に置かれた場合の false red を
    防ぐため `_SKIP_DIRS` で除外する。
    """
    _make_repo(tmp_path)
    (tmp_path / "build-cache" / "old").mkdir(parents=True)
    (tmp_path / "build-cache" / "old" / "old.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_claude_agents_dir_is_excluded(tmp_path: Path) -> None:
    """`.claude/agents/**` は Claude Code 用ロール定義なので除外する (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "role.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_eval_report_is_excluded(tmp_path: Path) -> None:
    """skill eval fixture の `.claude/skills` 参照は eval fixture 全体の除外により対象外。

    残置の追跡先は #1068。
    """
    _make_repo(tmp_path)
    (tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "reports").mkdir(
        parents=True
    )
    (
        tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "reports" / "r.md"
    ).write_text("# 対象 `.claude/skills/review-pr/SKILL.md`\n", encoding="utf-8")
    assert _run_repo(tmp_path) == 0


def test_eval_requirements_is_excluded(tmp_path: Path) -> None:
    """`.agents/skills/**/eval/**` は fixture 全体 (requirements.md 含む) を除外する (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / ".agents" / "skills" / "review-pr" / "eval").mkdir(parents=True)
    (
        tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "requirements.md"
    ).write_text("# 要件\n\nClaude は自動的に段階を進める。\n", encoding="utf-8")
    assert _run_repo(tmp_path) == 0


def test_undecodable_living_doc_is_exit_1(tmp_path: Path) -> None:
    """living doc (.md) が utf-8 decode 不能なら検査不能 = fail-closed (exit 1) (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bad.md").write_bytes(b"\xff\xfe\x00 broken")
    result = _run_repo_result(tmp_path)
    assert result.returncode == 1
    # 見出しが「旧用語残存」だけを原因として提示しない (検査不能も exit 1 の原因) (#1066)
    assert "bad.md: 検査不能" in result.stderr


def test_read_oserror_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """read 時の `OSError` も検査不能 = fail-closed で違反として扱う (#1066)。

    subprocess では `OSError` を再現しにくいため、本 file で唯一 in-process で
    `Path.read_text` を差し替えて分岐を pin する。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "unreadable.md").write_text("# ok\n", encoding="utf-8")

    original_read_text = Path.read_text

    def _fail_on_unreadable(self, *args, **kwargs):
        if self.name == "unreadable.md":
            raise OSError("simulated read failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _fail_on_unreadable)
    violations = guard.check_sweep(tmp_path)
    assert any("unreadable.md: 検査不能" in v for v in violations)


# --------------------------------------------------------------------------
# exit 2: 検査自体が壊れている
# --------------------------------------------------------------------------


def test_missing_agents_md_is_exit_2(tmp_path: Path) -> None:
    """anchor (AGENTS.md) 不在は「検査対象を特定できない」ので exit 2。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.md").write_text(
        "# バージョニング\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 2


# --------------------------------------------------------------------------
# 実物との統合
# --------------------------------------------------------------------------


def test_repo_sweep_passes() -> None:
    """repo の実 living doc が規約を満たす (CI が見るのと同じ経路)。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
