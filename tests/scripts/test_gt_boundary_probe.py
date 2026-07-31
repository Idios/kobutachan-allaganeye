"""GT 注釈計測器 (gt_boundary_probe.py) の入力 validation guard のテスト.

計測器に追加した保護機構 -- label 正規表現 / out_dir 内包チェック / argv 個数 /
config 型 / `_runs` pin 照合 / sys.path prepend -- が「発火する側」で実際に
例外・exit code・WARNING を出すことを実証する (project 規約: 保護機構追加は
発火する側の red 実証まで。no-op のまま出荷させない)。

実動画は不要。probe を含む `analyze_edge` は monkeypatch で置換するため
slow マーカーは付けない。置換により「全 label を probe 開始前に検証する」
順序不変条件も同時に gate できる。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from allaganeye.video.capture_region import ScorebarLocalization

_SCRIPT = (
    Path(__file__).resolve().parent / "poc_vtuber_timeline" / "gt_boundary_probe.py"
)
_SPEC = importlib.util.spec_from_file_location("gt_boundary_probe", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]

_ANCHOR = "532,1147,0,45,0.8"


def _write_config(tmp_path: Path, config: object) -> Path:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    return cfg


def _arm(monkeypatch: pytest.MonkeyPatch, cfg: Path, out_dir: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["gt_boundary_probe.py", str(cfg), str(out_dir)])


def _never_probe(*args: object, **kwargs: object) -> dict:
    raise AssertionError("analyze_edge must not run: validation should reject first")


# --------------------------------------------------------------------------
# _resolve_out_path: label validation (layer 1 = regex, layer 2 = containment)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "../escape",
        "..",
        "sub/dir",
        "sub\\dir",
        "/etc/passwd",
        "C:/tmp/evil",
        "C:\\tmp\\evil",
        "",
        ".hidden",
        "_leading",
        "has space",
        "tab\tchar",
        None,
        123,
        ["kyuma"],
        {"label": "kyuma"},
    ],
)
def test_resolve_out_path_rejects_unsafe_label(tmp_path: Path, label: object) -> None:
    """絶対 path / 親参照 / separator / 非 str label は ValueError で弾かれる."""
    with pytest.raises(ValueError, match="unsafe or missing"):
        mod._resolve_out_path(tmp_path, label)


@pytest.mark.parametrize("label", ["kyuma", "meteor-2", "a.b_c", "S", "20260717"])
def test_resolve_out_path_accepts_safe_label(tmp_path: Path, label: str) -> None:
    out = mod._resolve_out_path(tmp_path, label)
    assert out.name == f"{label}_boundaries.json"
    assert out.parent == tmp_path.resolve()


def test_resolve_out_path_containment_fires_when_regex_is_holed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """layer 2 (out_dir 内包チェック) が layer 1 と独立に発火することの実証.

    regex を全許容に差し替えても escape が通らないことを確認する。両層を
    まとめて 1 テストで見ると「regex が効いているだけ」で green になり
    containment 側が no-op でも気付けないため、層ごとに分けて gate する。
    """
    monkeypatch.setattr(mod, "_SAFE_LABEL_RE", re.compile(r"^.*$"))
    with pytest.raises(ValueError, match="escapes out_dir"):
        mod._resolve_out_path(tmp_path, "../escape")


# --------------------------------------------------------------------------
# _check_runs_pin: pinned `_runs` vs production `_tolerant_runs`
# --------------------------------------------------------------------------


def test_check_runs_pin_agrees_with_production(capsys: pytest.CaptureFixture) -> None:
    """現行の production `_tolerant_runs` とは一致している (WARNING を出さない)."""
    assert mod._check_runs_pin() is True
    assert capsys.readouterr().err == ""


def test_check_runs_pin_reports_drift(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """production 側が変わったら False + provenance 記録を促す WARNING を出す."""
    from allaganeye.video import vtuber_timeline

    def drifted(flags: list[bool], tol: int = 0) -> list[tuple[int, int]]:
        return [(99, 99)]

    monkeypatch.setattr(vtuber_timeline, "_tolerant_runs", drifted)
    assert mod._check_runs_pin() is False
    err = capsys.readouterr().err
    assert "pin drifted" in err
    assert "Record this in the GT provenance" in err


def test_check_runs_pin_reports_missing_production_symbol(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """production 側が rename/削除されたら silent pass せず WARNING を出す."""
    from allaganeye.video import vtuber_timeline

    monkeypatch.delattr(vtuber_timeline, "_tolerant_runs")
    assert mod._check_runs_pin() is False
    assert "not importable" in capsys.readouterr().err


def test_runs_pin_tolerates_gaps_up_to_tol() -> None:
    """pin されている `_runs` の tolerance semantics 自体の unit."""
    flags = [True] + [False] * 2 + [True]
    assert mod._runs(flags, 2) == [(0, 3)]
    assert mod._runs(flags, 1) == [(0, 0), (3, 3)]
    assert mod._runs([], 10) == []
    assert mod._runs([False, False], 3) == []


# --------------------------------------------------------------------------
# main(): argv 個数 / config 型 / 検証順序
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["gt_boundary_probe.py"],
        ["gt_boundary_probe.py", "config.json"],
        ["gt_boundary_probe.py", "config.json", "out_dir", "extra"],
    ],
)
def test_main_rejects_wrong_argv_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, argv: list[str]
) -> None:
    """argv が 2 個ちょうどでなければ usage を出して exit code 2."""
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(mod, "analyze_edge", _never_probe)
    assert mod.main() == 2
    assert "usage: gt_boundary_probe.py" in capsys.readouterr().err


def test_main_rejects_non_list_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """config が list でなければ exit code 2、かつ out_dir を作らない."""
    cfg = _write_config(tmp_path, {"label": "kyuma"})
    out_dir = tmp_path / "out"
    _arm(monkeypatch, cfg, out_dir)
    monkeypatch.setattr(mod, "analyze_edge", _never_probe)
    assert mod.main() == 2
    assert "must be a list" in capsys.readouterr().err
    assert not out_dir.exists()


def test_main_rejects_non_dict_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list の要素が dict でなければ label 検証で ValueError."""
    cfg = _write_config(tmp_path, ["kyuma"])
    out_dir = tmp_path / "out"
    _arm(monkeypatch, cfg, out_dir)
    monkeypatch.setattr(mod, "analyze_edge", _never_probe)
    with pytest.raises(ValueError, match="unsafe or missing"):
        mod.main()


def test_main_validates_every_label_before_any_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2 件目の label が不正なら 1 件目の probe も走らせない (順序不変条件).

    数十分かかる probe の後に失敗させない、かつ不正 config で部分出力を
    残さないことを gate する。`analyze_edge` は呼ばれたら即失敗する stub。
    """
    cfg = _write_config(
        tmp_path,
        [
            {"label": "good", "video": "a.mkv", "anchor": _ANCHOR, "edges": [10]},
            {"label": "../evil", "video": "b.mkv", "anchor": _ANCHOR, "edges": [10]},
        ],
    )
    out_dir = tmp_path / "out"
    _arm(monkeypatch, cfg, out_dir)
    monkeypatch.setattr(mod, "analyze_edge", _never_probe)
    with pytest.raises(ValueError, match="unsafe or missing"):
        mod.main()
    assert list(out_dir.glob("*.json")) == []


def test_main_writes_one_json_per_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """happy path: 検証を通れば label ごとに 1 JSON を書き exit code 0."""
    calls: list[tuple[str, ScorebarLocalization, float]] = []

    def fake_analyze(video: Path, anchor: ScorebarLocalization, edge: float) -> dict:
        calls.append((Path(video).name, anchor, edge))
        return {"edge": edge, "collapse": None}

    monkeypatch.setattr(mod, "analyze_edge", fake_analyze)
    cfg = _write_config(
        tmp_path,
        [
            {
                "label": "kyuma",
                "video": "E:/samples/kyuma.mkv",
                "anchor": _ANCHOR,
                "edges": [20, 820],
            }
        ],
    )
    out_dir = tmp_path / "out"
    _arm(monkeypatch, cfg, out_dir)

    assert mod.main() == 0

    written = json.loads(
        (out_dir / "kyuma_boundaries.json").read_text(encoding="utf-8")
    )
    assert written["label"] == "kyuma"
    assert [e["edge"] for e in written["edges"]] == [20.0, 820.0]
    assert [c[0] for c in calls] == ["kyuma.mkv", "kyuma.mkv"]
    anchor = calls[0][1]
    assert (
        anchor.x_left,
        anchor.x_right,
        anchor.y_top,
        anchor.y_bottom,
        anchor.confidence,
    ) == (532, 1147, 0, 45, 0.8)


# --------------------------------------------------------------------------
# sys.path direction pin
# --------------------------------------------------------------------------


def test_script_prepends_repo_root_to_sys_path() -> None:
    """sys.path 操作は insert(0, ...) 形でなければならない (append は不可).

    append だと allaganeye が site-packages に install された環境で install 版が
    先に解決され、計測器が repo 版ではないコードを silent に測ってしまう。

    この green は何を見逃すか: source 形の pin なので「insert(0) しているが
    渡す path が repo root でない」ケースは別途 args 検証で見る。逆に
    実行時の sys.path[0] を assert する形は pytest 自身が rootdir を先頭に
    入れるため常に green (false-green) になるので採らない。
    """
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    forms: list[tuple[str, list[ast.expr]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "path"
            and isinstance(target.value, ast.Name)
            and target.value.id == "sys"
        ):
            forms.append((node.func.attr, node.args))

    assert forms, "instrument no longer touches sys.path (pin is stale)"
    for attr, args in forms:
        assert attr == "insert", f"sys.path.{attr}() found: use sys.path.insert(0, ...)"
        assert isinstance(args[0], ast.Constant) and args[0].value == 0, (
            "sys.path.insert must prepend at index 0"
        )
        assert "parents[3]" in ast.unparse(args[1]), (
            "sys.path.insert must add the repo root (parents[3] of the script)"
        )
