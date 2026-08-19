"""Tests for scripts/check_screenshot_freshness.py (#944).

本 gate は「README のスクショが GUI の現状を写しているか」を見る。**git 履歴を
一切使わない**のが設計の核で、その理由は実測に基づく。

* `actions/checkout@v4` は既定 `fetch-depth: 1` で、本 repo のどの workflow も
  `fetch-depth` を設定していない。depth-1 の clone では `git log -- <path>` が
  **全ファイルについて同じ 1 commit** を返すため、commit 日時比較も blob 変化点
  の追跡も **無条件 green** になる (2026-08-20 実測)。
* 仮に `fetch-depth: 0` にしても、v0.3.0 の squash merge (`aefcb8c`) が
  `image/03-complete.png` と `gui/src/screens/MinimapScreen.tsx` の blob 変化点を
  **同一 commit に潰している**ため、実際にスクショが陳腐化している今日でも
  blob ベースの比較は green を返す (同日実測)。

したがって照合対象は **source の内容ハッシュ** であり、git ではない。本テストは
その性質 (履歴非依存 / 内容依存 / 穴があれば fail-closed) を固定する。

exit code の生値を観測する規律は `tests/scripts/test_check_doc_code_refs.py` と同じ。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "check_screenshot_freshness.py"

_spec = importlib.util.spec_from_file_location(
    "check_screenshot_freshness", SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------
# 合成 repo を組み立てるヘルパ
# --------------------------------------------------------------------------


def _build_repo(
    tmp_path: Path,
    *,
    sources: dict[str, str] | None = None,
    screenshots: list[str] | None = None,
    declared: list[str] | None = None,
    source_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    digest: str | None = None,
) -> Path:
    """最小構成の repo を作る。`digest=None` なら正しい digest を書き込む。"""
    root = tmp_path / "repo"
    (root / "gui" / "src").mkdir(parents=True, exist_ok=True)
    (root / "image").mkdir(parents=True, exist_ok=True)

    sources = (
        sources if sources is not None else {"gui/src/App.tsx": "export const A = 1;\n"}
    )
    for rel, text in sources.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    screenshots = screenshots if screenshots is not None else ["01-drop.png"]
    for name in screenshots:
        (root / "image" / name).write_bytes(b"\x89PNG\r\n\x1a\n fake")

    manifest = {
        "screenshots": [
            {"file": name, "screen": name.split("-", 1)[1].removesuffix(".png")}
            for name in (declared if declared is not None else screenshots)
        ],
        "sources": source_globs if source_globs is not None else ["gui/src/**/*.tsx"],
        "source_exclude": exclude_globs if exclude_globs is not None else [],
        "sources_sha256": digest or "",
    }
    manifest_path = root / "image" / "screenshot-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if digest is None:
        # 実際の `--update` 経路を通す (source hash と PNG hash の両方が入る)。
        result = _run(root, "--update")
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    return root


# --------------------------------------------------------------------------
# digest の性質
# --------------------------------------------------------------------------


def test_digest_is_stable_for_identical_content(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    manifest = guard.load_manifest(root)
    first = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    second = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    assert first == second


def test_digest_changes_when_a_source_file_changes(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    manifest = guard.load_manifest(root)
    before = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    (root / "gui" / "src" / "App.tsx").write_text(
        "export const A = 2;\n", encoding="utf-8"
    )
    after = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    assert before != after


def test_digest_is_line_ending_agnostic(tmp_path: Path) -> None:
    """CRLF と LF で digest が変わってはいけない。

    本 repo は `core.autocrlf=true` を使うため、Windows の作業ツリーは CRLF、
    ubuntu runner の checkout は LF になる。改行をそのまま hash に含めると
    **手元で緑・CI で赤**が常に起きる (PR #976 の初回 CI で実際に発生)。
    同じ事故は #612 / #816 でも起きており、`.gitattributes` に対症の
    `eol=lf` が積まれている。ここでは hash 側を改行非依存にして根を断つ。
    """
    root = _build_repo(tmp_path)
    manifest = guard.load_manifest(root)
    app = root / "gui" / "src" / "App.tsx"

    app.write_bytes(b"export const A = 1;\nexport const B = 2;\n")
    lf_digest = guard.compute_digest(root, guard.resolve_sources(root, manifest))

    app.write_bytes(b"export const A = 1;\r\nexport const B = 2;\r\n")
    crlf_digest = guard.compute_digest(root, guard.resolve_sources(root, manifest))

    assert lf_digest == crlf_digest


def test_digest_changes_when_a_source_file_is_renamed(tmp_path: Path) -> None:
    """内容が同じでも path が変われば digest は変わる (rename も再撮影の対象)。"""
    root = _build_repo(tmp_path)
    manifest = guard.load_manifest(root)
    before = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    (root / "gui" / "src" / "App.tsx").rename(root / "gui" / "src" / "Root.tsx")
    after = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    assert before != after


def test_digest_changes_when_a_new_source_file_appears(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    manifest = guard.load_manifest(root)
    before = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    (root / "gui" / "src" / "Extra.tsx").write_text(
        "export const B = 1;\n", encoding="utf-8"
    )
    after = guard.compute_digest(root, guard.resolve_sources(root, manifest))
    assert before != after


# --------------------------------------------------------------------------
# drift (exit 1)
# --------------------------------------------------------------------------


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-root", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_freshly_generated_manifest_is_green(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    assert _run(root).returncode == 0


def test_changing_a_gui_source_turns_the_guard_red(tmp_path: Path) -> None:
    """発火実証: source を変えて再撮影しなければ exit 1 (生値で観測)。"""
    root = _build_repo(tmp_path)
    (root / "gui" / "src" / "App.tsx").write_text(
        "export const A = 999;\n", encoding="utf-8"
    )
    result = _run(root)
    assert result.returncode == 1, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_editing_a_committed_screenshot_without_update_turns_the_guard_red(
    tmp_path: Path,
) -> None:
    """commit 済み PNG が後から差し替わったら赤にする (tamper-evidence)。

    Codex adversarial-review 2026-08-20 の指摘への対応。source hash だけでは
    「真っ黒な PNG を commit する」事故を検知できなかった。manifest が各 PNG の
    sha256 も持つことで、**撮影後に画像が変わった**ことは検知できるようになる。

    ただしこれは「その PNG が現在の GUI を写しているか」の証明ではない
    (`--update` は人間の申告を信じる)。射程の限界は checker の docstring 参照。
    """
    root = _build_repo(tmp_path)
    (root / "image" / "01-drop.png").write_bytes(b"\x89PNG\r\n\x1a\n TAMPERED")
    result = _run(root)
    assert result.returncode == 1, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_real_manifest_records_a_hash_for_every_screenshot() -> None:
    manifest = guard.load_manifest(REPO_ROOT)
    for entry in manifest["screenshots"]:
        assert entry.get("sha256"), f"{entry['file']} に sha256 が無い"


def test_update_flag_makes_a_red_manifest_green_again(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    (root / "gui" / "src" / "App.tsx").write_text(
        "export const A = 999;\n", encoding="utf-8"
    )
    assert _run(root).returncode == 1
    assert _run(root, "--update").returncode == 0
    assert _run(root).returncode == 0


# --------------------------------------------------------------------------
# fail-closed (exit 2)
# --------------------------------------------------------------------------


def test_missing_manifest_is_structural(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    (root / "image" / "screenshot-manifest.json").unlink()
    assert _run(root).returncode == 2


def test_malformed_manifest_is_structural(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    (root / "image" / "screenshot-manifest.json").write_text(
        "{ not json", encoding="utf-8"
    )
    assert _run(root).returncode == 2


def test_source_glob_matching_nothing_is_structural(tmp_path: Path) -> None:
    """「0 件と 0 件が一致した」で緑を返さない。

    glob が rename で腐ると走査対象が空になり、内容ハッシュは空文字列同士で
    一致して **永久に緑**になる。これは最も危険な false-green なので構造エラー。
    """
    root = _build_repo(tmp_path, source_globs=["gui/src/**/*.vue"], digest="deadbeef")
    assert _run(root).returncode == 2


def test_source_glob_escaping_repo_root_is_structural(tmp_path: Path) -> None:
    """repo 外へ出る glob は落とす。

    `compute_digest` は `relative_to(repo_root)` を呼ぶため、repo 外のパスが
    混ざると素の ValueError で落ちる (exit code が 1 でも 2 でもない形)。
    走査範囲は repo 内に閉じているという前提を明示的に検査する。
    """
    root = _build_repo(tmp_path, source_globs=["../**/*.tsx"], digest="deadbeef")
    assert _run(root).returncode == 2


def test_absolute_source_glob_is_structural(tmp_path: Path) -> None:
    root = _build_repo(tmp_path, source_globs=["/etc/**/*.conf"], digest="deadbeef")
    assert _run(root).returncode == 2


def test_screenshot_filename_escaping_image_dir_is_structural(tmp_path: Path) -> None:
    """manifest の `file` は image/ 直下のファイル名でなければならない。

    この値は `scripts/capture-readme-screens.mjs` が
    `resolve(IMAGE_DIR, file)` に渡して **PNG を書き込む** 先になる。
    `../../x.png` は image/ の外を指し、既存ファイルを上書きしうる
    (node の `path.resolve` で実測)。checker 側で先に落として、壊れた
    manifest が撮影側の書き込み経路へ届かないようにする。
    """
    root = _build_repo(tmp_path, screenshots=["01-drop.png"], digest="deadbeef")
    manifest_path = root / "image" / "screenshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["screenshots"] = [{"file": "../../evil.png", "screen": "drop"}]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert _run(root).returncode == 2


def test_declared_screenshot_missing_on_disk_is_structural(tmp_path: Path) -> None:
    root = _build_repo(
        tmp_path,
        screenshots=["01-drop.png"],
        declared=["01-drop.png", "09-ghost.png"],
        digest="deadbeef",
    )
    assert _run(root).returncode == 2


def test_undeclared_screenshot_on_disk_is_structural(tmp_path: Path) -> None:
    """image/ に増えたスクショが manifest に無ければ落とす。

    宣言し忘れたスクショは「誰も鮮度を見ていない」状態になるため。
    """
    root = _build_repo(
        tmp_path,
        screenshots=["01-drop.png", "06-minimap.png"],
        declared=["01-drop.png"],
        digest="deadbeef",
    )
    assert _run(root).returncode == 2


def test_stale_exclude_pattern_is_structural(tmp_path: Path) -> None:
    """何にもマッチしない除外パターンは腐った宣言なので落とす。

    digest を明示するのは、`_build_repo` の digest 自動計算が同じ検査を先に
    踏んで helper 側で落ちるのを避けるため (検査対象は subprocess の exit code)。
    """
    root = _build_repo(
        tmp_path, exclude_globs=["gui/src/**/*.test.tsx"], digest="deadbeef"
    )
    assert _run(root).returncode == 2


def test_uncovered_gui_source_file_is_structural(tmp_path: Path) -> None:
    """glob が拾わない拡張子の visual source が現れたら落とす (穴を作らせない)。

    `sources` を `*.tsx` だけにしたまま `.css` を足す、といった取りこぼしが
    **黙って検査対象外**になるのを防ぐ。
    """
    root = _build_repo(tmp_path)
    (root / "gui" / "src" / "theme.css").write_text(
        ":root { --a: 1px; }\n", encoding="utf-8"
    )
    result = _run(root)
    assert result.returncode == 2, f"stdout={result.stdout}\nstderr={result.stderr}"


# --------------------------------------------------------------------------
# 実 repo に対する end-to-end
# --------------------------------------------------------------------------


def test_real_repo_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_real_manifest_declares_every_committed_screenshot() -> None:
    """capture script と checker が同じ表を読んでいることの固定 (#944 の再発防止 CI)。"""
    manifest = guard.load_manifest(REPO_ROOT)
    declared = {entry["file"] for entry in manifest["screenshots"]}
    on_disk = {p.name for p in (REPO_ROOT / "image").glob("[0-9][0-9]-*.png")}
    assert declared == on_disk
