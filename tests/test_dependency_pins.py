"""Guard test: 依存 pin が実際に効いていることを検査する (#916 / #863).

## なぜ pytest に置くか

#916 が問題にしているのは「CI とローカルで別の版が使われている」こと自体である。
CI step に置くとローカルで発火しないため、問題を検出できない。ローカルで
`pytest` を回した時点で乖離が出る場所に置く。

## なぜ constraints.txt だけでは足りないか

pip の constraints file は **「どの版を入れるか」を決めるだけで install を
トリガーしない**。依存グラフに現れない名前を書いても pip は無言で無視する
(unused constraint を検出するコードパスが pip に存在しない)。つまり
constraints.txt の行が依存グラフから外れて no-op 化しても、CI は緑のまま通る。
本テストが「各 `==` 行が実際にその版で解決されたか」を実測で突き合わせる。

## この gate が見ていない集合

- **`-c constraints.txt` を渡さずに install した環境**では、本テストは
  「pin と違う版が入っている」ことを検出するが、**なぜ違うのか** (constraints を
  渡し忘れたのか、pin 値が古いのか) は区別しない。
- **resolver 到達性は検査していない。** 見ているのは
  `importlib.metadata.version()` = 「今この環境に何が入っているか」だけである。
  ある pin が依存グラフから外れて no-op 化しても、**使い回しのローカル venv には
  その版のまま残る** (pip は不要になった依存を自動削除しない) ため、ローカルでは
  緑のままになりうる。これを落とすのは **CI のまっさらな環境**で、そこでは
  install されず `PackageNotFoundError` として検出される。
  つまり本テストの no-op 検出は **CI との組み合わせで成立する**。
- **`[build-system] requires` の setuptools** は検査対象外。`-c` は PEP 517 の
  分離ビルド環境に伝播しないため constraints では固定できない (既知の残余)。
- **pip 自身の版**は検査しない (`--upgrade pip` が CI / 配布 build にある)。
- **第三者が `pip install kobutachan-allaganeye` した環境**は検査対象外。
  constraints.txt は本 repo の再現環境専用で、PyPI 経由の install には効かない。
- 版が一致していても **wheel のビルド差** (同一 upstream 版の別ビルド) は
  検出しない。opencv についてのみ headless / 非 headless を個別に検査する。
- `cv2.getBuildInformation()` の `GUI:` 行は **書式が変われば false-red になる**。
  cv2 は constraints.txt で exact pin してあるため書式は意図的な bump 以外で
  動かない。bump 手順 (docs/developer-setup.md の 9 章) に本行の再確認を含めてある。
"""

from __future__ import annotations

import importlib.metadata
import pathlib
import re
import tomllib

import pytest

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"
_CONSTRAINTS = _PROJECT_ROOT / "constraints.txt"
_WORKFLOW_DIR = _PROJECT_ROOT / ".github" / "workflows"

# `name==version` 行のみを拾う。`>=` 等の範囲行は「再現環境の pin」ではないので
# 対象外にする (constraints.txt には exact pin だけを書く運用)。
_PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([A-Za-z0-9.!+*-]+)\s*$")

_REINSTALL_HINT = (
    'pip install -e ".[dev]" -c constraints.txt --upgrade (repo 直下で実行すること)'
)

# **pin されていること自体**を要求するパッケージ。
#
# これが無いと、constraints.txt から行を消しても「残った行は一致している」ので
# テストは緑のまま = 保護範囲が静かに縮む。版そのものは constraints.txt が唯一の
# 正で、本表は「どのカテゴリを pin し続けるか」という契約だけを持つ (版は複製しない)。
#
# 意図的に減らす場合は本表も同時に編集すること (= 意識的な判断になる)。
_REQUIRED_PINS = {
    # 検出出力に効く。動かすと bit-exact baseline の再取得が要る。
    "opencv-python-headless",
    "numpy",
    "scipy",
    # codegen gate (ci.yml) の生成物の整形を決める。
    "datamodel-code-generator",
    "black",
    "isort",
    # CLI help 出力の整形に効く。
    "rich",
}


def _pyproject_requirements() -> list[str]:
    """pyproject.toml の runtime dependencies を返す."""
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def _find_requirement(name: str) -> str:
    """dependencies から name の requirement 行を 1 件返す."""
    for req in _pyproject_requirements():
        # "opencv-python-headless>=4.8,<5" -> 先頭の識別子部分で照合する
        head = re.split(r"[<>=!~\[; ]", req, maxsplit=1)[0].strip()
        if head == name:
            return req
    raise AssertionError(f"{name} が pyproject.toml の dependencies に無い")


def test_opencv_requirement_has_upper_bound() -> None:
    """cv2 の requirement に上限指定があること (#916 D8).

    上限が無いと新 major (5.x) が CI と配布物へ無検証で流入する。実測で
    `>=4.8` は 5.0.0.93 に解決していた。上限そのものが消えることを防ぐ。
    """
    req = _find_requirement("opencv-python-headless")
    assert "<" in req, (
        f"opencv-python-headless の requirement に上限が無い: {req!r}\n"
        "上限を外すと新 major が無検証で流入する (#916 / 裁定 D8)。\n"
        "5.x 移行は #951 (deferred) で扱う。"
    )


def _constraints_pins() -> list[tuple[str, str]]:
    """constraints.txt の `name==version` 行を [(name, version)] で返す."""
    pins: list[tuple[str, str]] = []
    for raw in _CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _PIN_RE.match(line)
        assert m is not None, (
            f"constraints.txt に exact pin 以外の行がある: {line!r}\n"
            "constraints.txt には `name==version` だけを書く運用にしている "
            "(範囲行は pin として機能せず、本テストの検査対象から静かに外れるため)。"
        )
        pins.append((m.group(1), m.group(2)))
    return pins


def test_constraints_file_exists() -> None:
    """constraints.txt が repo 直下に存在すること (#916).

    pyproject の範囲宣言だけでは repo の再現環境にならない。実測で
    `opencv-python-headless>=4.8,<5` は 4.14.0.94 に解決する。
    """
    assert _CONSTRAINTS.is_file(), (
        f"{_CONSTRAINTS} が無い。\n"
        "pyproject の範囲宣言だけでは CI / ローカル / 配布物の版が揃わない (#916)。"
    )


def test_required_packages_are_still_pinned() -> None:
    """保護対象のパッケージが constraints.txt から消えていないこと.

    版の一致だけを見ていると、行を削除したときに「残った行は一致している」ので
    緑のまま通り、保護範囲が静かに縮む。削除を検出するのが本テスト。
    """
    pinned = {name for name, _ in _constraints_pins()}
    missing = sorted(_REQUIRED_PINS - pinned)
    assert not missing, (
        "constraints.txt から pin が消えている: " + ", ".join(missing) + "\n"
        "これらは検出出力 / codegen 出力 / CLI 整形に効くため exact pin を維持する。\n"
        "意図的に外す場合は tests/test_dependency_pins.py の _REQUIRED_PINS も\n"
        "同時に編集すること (無言で保護範囲が縮むのを防ぐため)。"
    )


def test_constraints_pins_match_installed_versions() -> None:
    """constraints.txt の各 pin が実際にその版で解決されていること.

    **これが本テストの中核。** pip の constraints file は install を
    トリガーしないため、行が依存グラフから外れて no-op 化しても pip は
    無言で通す。「pin したつもり」の false-green を潰す。
    """
    pins = _constraints_pins()
    assert pins, "constraints.txt に exact pin が 1 件も無い"

    mismatches: list[str] = []
    for name, want in pins:
        try:
            got = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(
                f"  {name}: constraints は =={want} だが **install されていない** "
                "(依存グラフから外れて pin が no-op 化している)"
            )
            continue
        if got != want:
            mismatches.append(
                f"  {name}: constraints は =={want} だが install は {got}"
            )

    assert not mismatches, (
        "constraints.txt の pin が実環境と一致しない:\n"
        + "\n".join(mismatches)
        + f"\n\n復旧: {_REINSTALL_HINT}"
    )


def _workflow_pip_install_lines() -> list[tuple[pathlib.Path, int, str]]:
    """全 workflow から `pip install` 行を [(path, lineno, 行本文)] で返す.

    行ベースの走査である。YAML の `run:` は literal scalar なので中身は素の
    シェルスクリプトであり、行単位で見るのが実態に合う。行頭 / 行末のシェル
    コメントは落とす。
    """
    hits: list[tuple[pathlib.Path, int, str]] = []
    for path in sorted(_WORKFLOW_DIR.glob("*.yml")) + sorted(
        _WORKFLOW_DIR.glob("*.yaml")
    ):
        for lineno, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            # 行末コメントを落とす (空白 + # 以降)。URL の fragment 等は
            # 直前に空白が無いので誤除去しない。
            line = re.sub(r"(^|\s)#.*$", "", raw).strip()
            if not line:
                continue
            if re.search(r"\bpip\s+install\b", line):
                hits.append((path, lineno, line))
    return hits


def test_all_workflow_pip_installs_use_constraints() -> None:
    """全 workflow の package install が `-c constraints.txt` を通ること.

    `ci.yml` だけを直しても、別 workflow に未 constrained な install が残ると
    「CI の依存解決は constraints を通る」という主張が成立しない。**新しい
    workflow を足したときにも効く**ように、ファイルを列挙して検査する。

    pip 自身の self-upgrade (`pip install --upgrade pip`) だけは対象外
    (pip の版は固定していない。既知の残余)。
    """
    hits = _workflow_pip_install_lines()
    assert hits, "workflow に pip install が 1 行も見つからない (走査が壊れている)"

    violations: list[str] = []
    for path, lineno, line in hits:
        if re.search(r"install\s+--upgrade\s+pip\b", line):
            continue  # pip 自身の更新は対象外
        if "-c constraints.txt" not in line:
            violations.append(f"  {path.as_posix()}:{lineno}: {line}")

    assert not violations, (
        "constraints を通さない pip install が workflow に残っている:\n"
        + "\n".join(violations)
        + "\n\npackage を入れる pip install には `-c constraints.txt` を付けること (#916)。\n"
        "pip 自身の更新 (`pip install --upgrade pip`) だけが対象外。"
    )


def test_non_headless_opencv_is_not_installed() -> None:
    """非 headless の opencv-python が同居していないこと.

    両 wheel は同じ `cv2` パッケージを提供し、実測で **49 ファイル
    (`cv2.pyd` を含む) を共有**する。同居すると後から install した側が
    ファイルを上書きするため、宣言ではなく install 順で `import cv2` の
    実体が決まる。`cv2.__version__` だけを見ても両者を区別できない。
    """
    try:
        version = importlib.metadata.version("opencv-python")
    except importlib.metadata.PackageNotFoundError:
        return  # 期待どおり

    pytest.fail(
        f"非 headless の opencv-python ({version}) が install されている。\n"
        "headless と `cv2.pyd` を共有するため、import される cv2 の実体が\n"
        "install 順で決まってしまう (#916)。\n"
        "**片方だけ uninstall すると共有ファイルが消えて import が壊れる。**\n"
        "復旧: pip uninstall -y opencv-python opencv-python-headless\n"
        '        -> python -c "import cv2" が ModuleNotFoundError になるのを確認\n'
        f"        -> {_REINSTALL_HINT}"
    )


def test_cv2_is_headless_build() -> None:
    """import される cv2 の実体が headless ビルドであること.

    distribution metadata (前テスト) だけでは「どちらのファイルが勝ったか」
    まではわからないため、cv2 本体に聞く。
    """
    import cv2

    gui_lines = [
        line
        for line in cv2.getBuildInformation().splitlines()
        if line.strip().startswith("GUI")
    ]
    assert gui_lines, (
        "cv2.getBuildInformation() に GUI 行が見つからない。\n"
        "cv2 の出力書式が変わった可能性がある (本 repo は cv2 を exact pin して\n"
        "いるため、意図的な bump 以外では起きない)。bump 手順は\n"
        "docs/developer-setup.md の 9 章を参照し、本 assert を実出力に合わせて更新すること。"
    )
    assert "NONE" in gui_lines[0], (
        f"cv2 が headless ビルドではない: {gui_lines[0].strip()!r}\n"
        "非 headless の opencv-python がファイルを上書きしている可能性がある。\n"
        f"復旧: {_REINSTALL_HINT}"
    )
