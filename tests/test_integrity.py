"""Tests for allaganeye.integrity (#668).

Bundled file integrity check used by both:
- the CLI ``--version`` callback (production path)
- the Tauri release-build startup hook (mirror logic in Rust)
"""

import json
from pathlib import Path

import pytest

from allaganeye.exceptions import IntegrityError
from allaganeye.integrity import load_manifest


def test_load_manifest_parses_valid_json(tmp_path: Path) -> None:
    """load_manifest returns the parsed JSON when valid."""
    manifest = tmp_path / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {"path": "ffmpeg/ffmpeg.exe", "size": 100, "tolerance_bytes": 0}
                ],
            }
        ),
        encoding="utf-8",
    )

    data = load_manifest(manifest)

    assert data["version"] == 1
    assert data["files"][0]["path"] == "ffmpeg/ffmpeg.exe"


def test_load_manifest_raises_when_missing(tmp_path: Path) -> None:
    """Missing manifest -> IntegrityError with helpful context."""
    missing = tmp_path / "no-such.json"

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(missing)

    assert "not found" in str(exc_info.value)
    assert exc_info.value.context["manifest_path"] == str(missing)


def test_load_manifest_raises_on_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON -> IntegrityError with json_error context."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(bad)

    assert "invalid JSON" in str(exc_info.value)
    assert "json_error" in exc_info.value.context


def test_load_manifest_raises_when_files_key_missing(tmp_path: Path) -> None:
    """JSON without `files` key -> IntegrityError."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(bad)

    assert "files" in str(exc_info.value)


def test_resolve_install_dir_from_package_init(tmp_path: Path) -> None:
    """_resolve_install_dir walks 3 levels up from package __init__.

    Portable ZIP layout: <install dir>/lib/allaganeye/__init__.py
    """
    from allaganeye.integrity import _resolve_install_dir

    init_path = tmp_path / "lib" / "allaganeye" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    init_path.write_text("", encoding="utf-8")

    assert _resolve_install_dir(init_path) == tmp_path


def test_default_manifest_path_under_install_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_default_manifest_path returns <install dir>/integrity-manifest.json.

    Patches the module-level Path-from-__file__ resolution so the test is
    independent of where pytest finds the actual package.
    """
    import allaganeye.integrity as integ

    fake_init = tmp_path / "lib" / "allaganeye" / "__init__.py"
    fake_init.parent.mkdir(parents=True)
    fake_init.write_text("", encoding="utf-8")
    monkeypatch.setattr(integ, "_PACKAGE_INIT", fake_init)

    assert integ._default_manifest_path() == tmp_path / "integrity-manifest.json"


def test_check_happy_path_returns_none(tmp_path: Path) -> None:
    """check() with all manifest entries present and exact size returns None."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "ffmpeg" / "ffmpeg.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * 100)

    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {
                        "path": "ffmpeg/ffmpeg.exe",
                        "size": 100,
                        "tolerance_bytes": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # Expected: returns None, does not raise
    assert check(manifest, install_dir=install) is None
