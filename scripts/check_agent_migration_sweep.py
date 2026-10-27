#!/usr/bin/env python3
"""Check the Claude Code → Zed+DeepSeek agent migration sweep is complete (#1041/#1042).

Detects "old terminology" — **5 class**: slash command / 旧 path・旧 filename /
主エージェント=Claude 表記 / Codex 旧 invocation 契約 (#1043) /
Claude Code plugin 旧表記 (#1064) — that remains in
**living docs**, to prevent the incomplete-sweep recurrence seen in PR #1051
Round 4/5 (session-start.sh / docs/versioning.md に slash 残存を個別に拾う事象)。

再発防止の設計意図:
- 用語 sweep は「まとめて置換」だけでは漏れる (対象ファイルの取りこぼし)。
  本 check は **旧用語が living doc に残っていれば fail** するため、sweep の
  完全性を CI で担保する。

検査対象 = living doc のみ (`docs/l2-workflow.md` §「歴史記録の扱い」#854 R2 の
整合対象と同一方針):
  - 拡張子 `.md` / `.sh` のファイル (docs / skill / hook / AGENTS.md / README)。
  - コードファイル (`.py` / `.js` / `.ts` / `.rs` / `.ps1` / `.yml` 等) は対象外。
    コードコメントの旧参照 (GUI ソースの `CLAUDE.md` / `// … /iterate-review Round N`
    等) は #1076 で追跡する (棚卸 #1044 は未参照ファイルの削除が範囲で、
    コードコメントの修正を含まない)。
  - 履歴記録 (`CHANGELOG.md` / eval fixture (`.agents/skills/**/eval/**`) /
    `docs/superpowers/**` (dated 以外の記録も含む) / `docs/archive/**` /
    `docs/audits/**`) も対象外。
  - `gui/**` は GUI ソースのため `.md` でも対象外 (screenshot-freshness 回避)。
  - `build-cache/` は Portable ZIP の build キャッシュ置き場 (`.gitignore` 済) の
    ため対象外 (#1066)。
  - `.claude/agents/**` は Claude Code 用のロール定義 (frontmatter の `model:` が
    Claude エイリアスのみ) で用語 sweep の対象外。旧 Codex invocation 契約は
    #1068 で追跡する。

exit code: 0 = clean / 1 = 旧用語残存 (sweep 未完了) または 検査不能 (fail-closed)
         / 2 = 検査自体が壊れている。
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_STRUCTURAL = 2

# --------------------------------------------------------------------------
# 旧用語 (migration target の old 側)
# --------------------------------------------------------------------------

# slash command (Claude Code) → Zed skill name / CLI。
# `(?<![a-z0-9._-])` + `(?![a-z0-9._-])` で「前後が path/単語文字でない」ことを要求し、
# `.agents/skills/review-pr/SKILL.md` (path 中の /review-pr) や
# `refs/heads/release/vX` (branch 名) を誤検出しない。
_SLASH_SKILLS = [
    "review-pr",
    "iterate-review",
    "release",
    "scope-guard",
    "close-issue",
    "create-task",
    "enforce-acceptance-criteria",
]
_SLASH_RE = re.compile(
    r"(?<![a-z0-9._-])/(" + "|".join(_SLASH_SKILLS) + r")(?![a-z0-9._-])"
)

# 旧 path / 旧 filename (literal 一致)
_LITERAL_TERMS = [
    ".claude/skills",
    "CLAUDE.md",
]

# Codex 呼び出し契約の旧表記 (#1043 で追加)。Claude Code の companion script
# (`codex-companion.mjs`) / plugin path (`.claude/plugins`) / env var
# (`CLAUDE_PLUGIN_ROOT`) は `.claude/` 廃止 (#1041/#1042) により dead 化。
# living doc では `codex` CLI 直呼び (§Codex 運用、AGENTS.md) が正。
_CODEX_OLD_TERMS = [
    "codex-companion.mjs",
    "CLAUDE_PLUGIN_ROOT",
    ".claude/plugins",
]

# Claude Code plugin 旧表記 + 旧モデル名 (#1064)。plugin skill 名は本 repo に存在せず
# (`spawn_agent` / 主エージェント直接レビューが正)、旧モデル名は living doc で版を
# 固定せず「独立 model」と書く。
#
# `superpowers:` は **コロン込み** で持つ: `obra/superpowers` への出典帰属リンクと
# 「(superpowers 方式)」は維持対象 (plugin 呼び出しではなく帰属表現) のため、
# bare 語で持つと誤検出する (negative fixture `superpowers-attribution` /
# `superpowers-parenthetical` で pin)。
#
# 旧モデル名は一般の model 版固定検出 (例: `GPT-\d`) を行わず、sweep で実際に
# 残っていた版名のみ literal で持つ (汎用 regex は正式名称の記述まで巻き込むため)。
#
# 上流 skill への **出典帰属 URL** (`https://github.com/obra/superpowers/tree/main/
# skills/<name>/SKILL.md` 等) は維持対象のため、URL 内の一致は判定から除外する
# (`_URL_RE`)。`.claude/skills` 等の repo 内 path とは違い、これら 4 語は上流の
# 正当な名称でもあるため (Codex adversarial-review [P2])。
_PLUGIN_OLD_TERMS = [
    "superpowers:",
    "subagent-driven-development",
    "requesting-code-review",
    "systematic-debugging",
    "GPT-5.4",
]

# 帰属 URL / path / anchor の判定からの除外に使う (上記 `_PLUGIN_OLD_TERMS` のみに適用する)。
#
# **打ち切り文字の列挙ではなく、URL / path に使われる ASCII 文字の肯定形で切り出す**:
# 列挙方式だと、`https://example.comを参照して<旧用語>を使う` のように URL 直後に
# 日本語散文が続く場合に打ち切り文字が現れず、行末まで飲み込んで検出漏れになる
# (iterate-review Round 2 / Round 3 / Round 4 の finding)。ASCII 肯定形なら
# 非 ASCII で自動的に止まるため、全角括弧・句読点を個別に列挙する必要がない。
#
# 2 番目の分岐は **scheme 無しの URL / repo 内 path / anchor** を拾う
# (`github.com/.../SKILL.md` / `docs/guide.md#<旧用語>`)。いずれも上流・内部への
# 出典参照で、operational instruction ではない。
#
# ただし **`.` か `#` を含むことを要求**する: これが無いと
# `/superpowers:brainstorming` のような **plugin skill の canonical 呼び出し形** が
# パスと誤認されて消え、第 5 class の主語が素通りする (Round 5 finding)。
# `GPT-5.4` は `/` を持たないため影響を受けない。
_URL_CHARS = r"A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%"
_URL_RE = re.compile(
    rf"(?:https?://|www\.)[{_URL_CHARS}]+"
    rf"|(?=[{_URL_CHARS}]*[.#])[{_URL_CHARS}]*/[{_URL_CHARS}]+"
)

# literal 系 class の **単一の正**。key は test の positive / negative fixture の key と
# 一致することを meta-test が要求する (`_LITERAL_TERM_GROUPS` に group を足すと、
# fixture を足すまで test が red になる)。
# value = (旧用語 list, 違反ラベル, URL 内の一致を無視するか)。
_LITERAL_TERM_GROUPS: dict[str, tuple[list[str], str, bool]] = {
    "literal": (_LITERAL_TERMS, "旧表記残存", False),
    "codex-old": (_CODEX_OLD_TERMS, "Codex 呼び出し契約の旧表記残存", False),
    "plugin-old": (_PLUGIN_OLD_TERMS, "Claude Code plugin 旧表記残存", True),
}

# 主エージェント=Claude の旧表記 (#1066)。運用は Zed + DeepSeek が主エージェントへ
# 反転済 (#1043) なので、living doc に「Claude を主エージェントとして扱う」表記が
# 残っていれば fail させる。維持対象 ("Claude Code" / "Claude Fable/Sonnet/Opus" /
# "Claude Design" / "Claude fallback notice" / 節見出し "Claude fallback（...）") を
# 誤検出しないよう、`の` + 名詞は whitelist で除外する。
#
# **tradeoff (意図的)**: 主語形 (`Claude は/が/内/main/思考体`) は助詞だけで判定する
# ため、維持対象の文脈でも成立しうる (例: "Claude が復旧したら再レビューを依頼する")。
# これは **FP 側に倒す** 設計で、文脈依存の narrow 化はしない (人手 sweep に委ねる
# 方針と衝突するため)。現挙動は test の `claude-maintenance-context-tradeoff` で pin。
_CLAUDE_AGENT_BRANCHES: list[tuple[str, str]] = [
    # 主語 / ホスト
    ("subject", r"Claude\s*(?:は|が|内|main|思考体)"),
    # 所有 "の" は維持対象 (Claude のレビュー / permission prompt 等) を negative lookahead で
    # 除外し、主エージェント所有 (Claude の判断 / 責務 等) のみ拾う。whitelist 方式のため、
    # 維持対象の「の + 名詞」を新たに living doc に書く場合は本リストへ追加する
    # (未追加だと FP で CI red になる)。
    (
        "ownership",
        r"Claude\s*の(?!\s*(?:レビュー|再レビュー|usage|復旧|不可|Code|Fable|Sonnet|Opus|Design|permission|セッション|auto-memory|スラッシュコマンド))",
    ),
    (
        "code-fallback",
        r"Claude\s+Code\s+fallback",
    ),  # C6 fallback 実行者を Claude Code とする旧表記
    (
        "fallback-particle",
        r"Claude\s+fallback\s+(?:で|は)",
    ),  # 実行者を Claude とする旧表記
    ("fallback-slash", r"/\s*Claude\s+fallback"),  # 選択肢 "… / Claude fallback / …"
    (
        "equals-plus",
        r"=\s*Claude\s*\+",
    ),  # "エージェント (= Claude + 人間メンテナ Idios)"
    (
        "code-session",
        r"Claude\s+Code\s+セッションで動く",
    ),  # "Claude Code セッションで動くアシスタント"
    ("code-plan", r"Claude\s+Code\s+の\s*plan"),  # "Claude Code の plan モード"
]

# 分岐を list で持ち、regex はそこから組み立てる (#1075)。test が「各分岐に positive
# fixture があること」と「分岐を 1 つ外すと検出されなくなること」を pin できる。
_CLAUDE_AGENT_RE = re.compile(
    "|".join(f"(?:{pattern})" for _, pattern in _CLAUDE_AGENT_BRANCHES)
)

# 検出網の制約 (意図的): 上記 regex は **分離可能な旧 idiom のみ** を対象とする。
# "Claude Code の X" のように文脈依存で維持対象と衝突する形 (X = レビュー専用ツールの
# 機能か主エージェントの行為か) は regex では判別できないため CI では担保せず、
# **人手 sweep + Fable 俯瞰レビューに委ねる**。例: リスト "Claude Code / Codex / ..." に
# 主エージェントが欠ける形 / "Claude に再レビューを依頼する" のような維持対象文。
# これらは #1066 PR で人手 sweep により 0 件を確認済。

# --------------------------------------------------------------------------
# 検査対象と除外
# --------------------------------------------------------------------------

# living doc = doc / skill / hook のみ (コードファイルの旧参照は #1076 へ)
_SCAN_EXTS = {".md", ".sh"}

_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "build-cache",
    "dist",
    "target",
    "output",
    ".mypy_cache",
}

# historical record / deferred: 遡及書き換えしない (棚卸 #1044 / 歴史記録 #854 R2)
#
# NOTE: `.agents/skills/**/eval/**` は eval **fixture 全体**を除外する (dated `reports/`
# だけでなく `requirements.md` / `scenario_*.md` も含む)。これらは特定時点の評価基準 /
# シナリオを固定する記録で、**用語 sweep の対象外** (旧用語が当時の文脈で意味を持つため
# 遡及置換しない)。ただし **skill の契約自体が変わった場合は eval の妥当性を保つため
# fixture の期待値を更新する** (例: PR #1071 で `review-pr/eval/requirements.md` の I-5 を
# 「Claude fallback」→「DeepSeek fallback / abort」へ更新)。fixture 内に残る旧 Codex 契約
# 等の残置は #1068 / #1069 で別途追跡する。
_EXCLUDED_GLOBS = [
    "CHANGELOG.md",
    ".claude/agents/**",
    ".agents/skills/**/eval/**",
    "docs/superpowers/**",
    "docs/archive/**",
    "docs/audits/**",
    "gui/**",
]


def _is_excluded(rel: Path) -> bool:
    rel_s = rel.as_posix()
    return any(fnmatch.fnmatch(rel_s, g) for g in _EXCLUDED_GLOBS)


def _iter_living_docs(repo_root: Path):
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        parts = rel.parts
        if any(part in _SKIP_DIRS for part in parts):
            continue
        if path.suffix.lower() not in _SCAN_EXTS:
            continue
        if _is_excluded(rel):
            continue
        yield path, rel


def check_sweep(repo_root: Path) -> list[str]:
    """Return human-readable violations.

    2 形式ある: 旧用語残存は "path:line: text"、fail-closed (decode / 読取不能) は
    "path: 検査不能 (...)" (行番号を持たない)。
    """
    violations: list[str] = []
    for path, rel in _iter_living_docs(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            # living doc (.md / .sh) が decode / 読取不能 = 検査不能。sweep 完全性 gate と
            # して fail-open にしない (未検査 file を「違反なし」と混同しない)。
            violations.append(
                f"{rel}: 検査不能 (utf-8 decode / 読取失敗: {exc})。"
                "sweep gate は fail-closed のため違反として扱う"
            )
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            # 帰属 URL 内の上流 skill 名は維持対象 (operational instruction ではない)。
            line_without_urls = _URL_RE.sub("", line)
            if _SLASH_RE.search(line):
                violations.append(f"{rel}:{lineno}: slash command 残存: {line.strip()}")
            if _CLAUDE_AGENT_RE.search(line):
                violations.append(
                    f"{rel}:{lineno}: 主エージェント=Claude の旧表記残存: "
                    f"{line.strip()}"
                )
            for terms, label, strip_urls in _LITERAL_TERM_GROUPS.values():
                haystack = line_without_urls if strip_urls else line
                for term in terms:
                    if term in haystack:
                        violations.append(
                            f"{rel}:{lineno}: {label} ({term}): {line.strip()}"
                        )
    return violations


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="検査対象の repo ルート (既定: 本 script の 1 つ上)",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    if not (repo_root / "AGENTS.md").exists():
        print(
            "ERROR: 検査自体が壊れている: AGENTS.md が見つからない "
            f"(repo root が誤っている?: {repo_root})",
            file=sys.stderr,
        )
        return EXIT_STRUCTURAL

    violations = check_sweep(repo_root)

    if violations:
        print(
            "ERROR: agent migration sweep が未完了 "
            "(旧用語残存 または 検査不能 (fail-closed))。\n",
            file=sys.stderr,
        )
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "\nslash command は skill 名へ、`.claude/skills` は `.agents/skills` へ、"
            "`CLAUDE.md` は `AGENTS.md` へ置換すること。\n"
            "`codex-companion.mjs` / `CLAUDE_PLUGIN_ROOT` / `.claude/plugins` は "
            "`codex` CLI 直呼び (§Codex 運用) へ置換すること (#1043)。\n"
            "主エージェント=Claude の旧表記は `Zed + DeepSeek` (または `主エージェント`) "
            "へ置換すること (#1066)。\n"
            "Claude Code plugin 旧表記 (plugin 固有名 / 旧モデル名) は `spawn_agent` / "
            "主エージェント直接レビュー / 「独立 model」へ置換すること (#1064)。\n"
            "コードファイルは検査対象外 (`_SCAN_EXTS` の allowlist が living doc のみを"
            "走査するため)。CHANGELOG / eval fixture / `docs/superpowers/**` / "
            "archive / audits は対象外 (#1044)。`gui/**` は GUI ソースのため対象外 "
            "(screenshot-freshness 回避)。`build-cache/` は build キャッシュ置き場の"
            "ため対象外 (#1066)。コードコメントの旧参照は #1076 で追跡する。\n"
            "`.claude/agents/**` は Claude Code 用ロール定義のため対象外 "
            "(旧 invocation 契約は #1068)。",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    print("OK: agent migration sweep は完了 (旧用語の living doc 残存なし)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
