"""slow_* サブマーカー規約 guard のユニットテスト (audit 2026-06-10 P1-3 再発防止).

enforcement 本体は tests/conftest.py の pytest_collection_modifyitems。
ここではその純関数 slow_submarker_violations() を検証する。
"""

from tests.conftest import slow_submarker_violations


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
