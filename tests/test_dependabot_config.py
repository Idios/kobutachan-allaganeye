"""Guard test: dependabot の PR を開発ブランチに出す (#1052-#1061 棚卸, 2026-10-30).

`main` は保護ブランチで、リリース時の `release/vX.Y.Z` から `main` へのマージで
しか更新されない (docs/release-process.md)。`target-branch` を書かないと
dependabot は既定ブランチ (`main`) に PR を出すため、bump が `develop-*` に
入らないまま main と develop でバージョンが割れ、次のリリースで古い値に戻る。
2026-10 の棚卸では 10 件すべてが `main` 向けだった。

## この gate が見ていない集合

- **どの `develop-*` を指すかは固定しない。** ブランチ名はリリースごとに変わる
  ため値を pin すると config と本テストの 2 箇所を毎回直すことになる。見るのは
  「`target-branch` があり、保護ブランチを指していない」ことまでである。
- **dependabot が実際にそのブランチへ PR を出すかは検査しない。** GitHub 側の
  解釈結果を CI から読む手段が無いため、config の静的検査に留める。
- **security updates (脆弱性起点の自動 PR) は本 config の対象外**で、repo 設定側の
  機能である。本テストは version updates の config だけを見る。
"""

from __future__ import annotations

import pathlib

import yaml

_CONFIG = pathlib.Path(__file__).resolve().parents[1] / ".github" / "dependabot.yml"
_PROTECTED = {"main", "master"}
_DEV_PREFIX = "develop-"


def _updates() -> list[dict[str, object]]:
    data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    return data["updates"]


def test_updates_is_not_empty() -> None:
    """updates が空だと後段の検査が空振りして緑になる。"""
    assert _updates(), "dependabot.yml に updates が無い"


def test_every_ecosystem_targets_a_development_branch() -> None:
    """全 ecosystem に target-branch があり、保護ブランチを指していないこと。"""
    problems: list[str] = []
    for entry in _updates():
        ecosystem = entry.get("package-ecosystem", "<unknown>")
        target = entry.get("target-branch")
        if target is None:
            problems.append(
                f"{ecosystem}: target-branch が無い (既定ブランチ main に出る)"
            )
        elif str(target) in _PROTECTED:
            problems.append(
                f"{ecosystem}: target-branch が保護ブランチを指している: {target}"
            )
        elif not str(target).startswith(_DEV_PREFIX):
            problems.append(f"{ecosystem}: target-branch が develop-* でない: {target}")
    assert not problems, "\n".join(problems)
