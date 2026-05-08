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


def test_check_detects_missing_file(tmp_path: Path) -> None:
    """check() raises IntegrityError listing missing path."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "absent.bin", "size": 100, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)

    ctx = exc_info.value.context
    assert ctx["missing"] == ["absent.bin"]
    assert ctx["size_mismatch"] == []


def test_check_aggregates_multiple_missing(tmp_path: Path) -> None:
    """check() reports every missing entry, not just the first."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [
                    {"path": "a.bin", "size": 1, "tolerance_bytes": 0},
                    {"path": "b.bin", "size": 1, "tolerance_bytes": 0},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)

    assert sorted(exc_info.value.context["missing"]) == ["a.bin", "b.bin"]


def test_check_detects_size_mismatch_outside_tolerance(tmp_path: Path) -> None:
    """check() reports size_mismatch for files whose size differs > tolerance_bytes."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "tiny.bin"
    target.write_bytes(b"x" * 50)  # actual 50, expected 100, tolerance 0 -> fail

    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "tiny.bin", "size": 100, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)

    sm = exc_info.value.context["size_mismatch"]
    assert len(sm) == 1
    assert sm[0]["path"] == "tiny.bin"
    assert sm[0]["expected"] == 100
    assert sm[0]["actual"] == 50


def test_check_passes_within_tolerance(tmp_path: Path) -> None:
    """check() accepts size within tolerance_bytes window."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "buffered.bin"
    target.write_bytes(b"x" * 105)  # actual 105, expected 100, tolerance 10 -> pass

    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "buffered.bin", "size": 100, "tolerance_bytes": 10}],
            }
        ),
        encoding="utf-8",
    )

    # Should not raise
    assert check(manifest, install_dir=install) is None


def test_check_tolerance_default_zero(tmp_path: Path) -> None:
    """tolerance_bytes is treated as 0 when absent from the entry."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    target = install / "exact.bin"
    target.write_bytes(b"x" * 100)

    manifest = install / "integrity-manifest.json"
    # entry omits tolerance_bytes
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "exact.bin", "size": 100}],
            }
        ),
        encoding="utf-8",
    )

    # exact match -> pass
    assert check(manifest, install_dir=install) is None


def test_check_skips_when_env_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ALLAGANEYE_INTEGRITY_SKIP=1 makes check() a no-op even with missing manifest."""
    from allaganeye.integrity import check

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")

    # Manifest does not exist; without env this would raise.
    fake_manifest = tmp_path / "no-such.json"
    fake_install = tmp_path / "fake-install"

    assert check(fake_manifest, install_dir=fake_install) is None


def test_check_does_not_skip_when_env_set_to_other_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only literal '1' triggers skip; '0' / 'false' / unset run the check."""
    from allaganeye.integrity import check

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "0")

    fake_manifest = tmp_path / "no-such.json"

    with pytest.raises(IntegrityError):
        check(fake_manifest, install_dir=tmp_path)


def test_log_written_on_failure(tmp_path: Path) -> None:
    """check() failure appends a record to <install dir>/logs/error-YYYYMMDD.log."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "absent.bin", "size": 100, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError):
        check(manifest, install_dir=install)

    logs_dir = install / "logs"
    assert logs_dir.exists()
    log_files = list(logs_dir.glob("error-*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "integrity check failed" in content
    assert '"absent.bin"' in content  # JSON-encoded path inside the record


def test_log_silent_fail_when_dir_creation_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log write failure does not change the modal/exit code path (silent fail)."""
    import allaganeye.integrity as integ
    from allaganeye.integrity import check

    def boom(*_args, **_kwargs):
        raise PermissionError("readonly install dir")

    monkeypatch.setattr(integ, "_write_log", boom)

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-05-08T00:00:00Z",
                "files": [{"path": "absent.bin", "size": 1, "tolerance_bytes": 0}],
            }
        ),
        encoding="utf-8",
    )

    # check() must still raise IntegrityError even when _write_log explodes.
    with pytest.raises(IntegrityError):
        check(manifest, install_dir=install)
