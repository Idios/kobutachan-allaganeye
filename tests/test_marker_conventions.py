"""slow_* サブマーカー規約 guard のテスト (audit 2026-06-10 P1-3 再発防止).

enforcement 本体は tests/conftest.py の pytest_collection_modifyitems。
純関数 slow_submarker_violations() の unit、_SLOW_SUBMARKERS と pyproject.toml
の同期 pin、pytester による hook 統合 (tryfirst 挙動) を検証する。
"""

import tomllib
from pathlib import Path

import pytest

from tests.conftest import _SLOW_SUBMARKERS, slow_submarker_violations

pytest_plugins = ["pytester"]


def test_detects_submarker_without_slow():
    mapping = {
        "tests/test_x.py::test_a": {"slow_detect"},
        "tests/test_x.py::test_b": {"slow_detect", "baseline_regen"},
    }
    assert slow_submarker_violations(mapping) == [
        "tests/test_x.py::test_a",
        "tests/test_x.py::test_b",
    ]


def test_accepts_submarker_with_slow():
    mapping = {
        "tests/test_x.py::test_a": {"slow", "slow_detect"},
        "tests/test_x.py::test_b": {"slow", "slow_gpu", "baseline_regen"},
    }
    assert slow_submarker_violations(mapping) == []


def test_ignores_unrelated_markers():
    mapping = {
        "tests/test_x.py::test_a": {"parametrize"},
        "tests/test_x.py::test_b": set(),
        "tests/test_x.py::test_c": {"slow"},
    }
    assert slow_submarker_violations(mapping) == []


def test_submarker_set_matches_pyproject():
    """_SLOW_SUBMARKERS が pyproject.toml の markers 登録と drift していないことを pin する."""
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    declared = {
        m.split(":")[0].strip()
        for m in pyproject["tool"]["pytest"]["ini_options"]["markers"]
    }
    assert {name for name in declared if name.startswith("slow_")} == set(
        _SLOW_SUBMARKERS
    )


def test_guard_fires_before_addopts_deselection(pytester: pytest.Pytester) -> None:
    """tryfirst 化の核心挙動を pin する (#812 回帰防止).

    addopts の -m deselection で除外される違反 (slow_detect+baseline_regen で
    slow 欠落) でも、guard が deselection より前に全 item を検査して
    UsageError (exit 4) で fail することを隔離環境で検証する。
    """
    pytester.makeini(
        """
        [pytest]
        addopts = -m 'not slow and not baseline_regen'
        markers =
            slow: superset marker
            slow_detect: detection submarker
            baseline_regen: baseline regeneration only
        """
    )
    pytester.makeconftest("from tests.conftest import pytest_collection_modifyitems\n")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.slow_detect
        @pytest.mark.baseline_regen
        def test_violating():
            pass
        """
    )
    result = pytester.runpytest("--collect-only", "-q")
    assert result.ret == 4
    result.stderr.fnmatch_lines(["*slow_* submarker without 'slow'*"])
