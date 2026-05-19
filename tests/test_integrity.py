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
    """_resolve_install_dir walks 3 levels up from package __init__ in dev / legacy mode.

    Dev mode (``pip install -e .``) and pre-#752 Portable ZIP layout:
    ``<install dir>/lib/allaganeye/__init__.py``. v0.3.0+ PyInstaller frozen
    layout uses the ``sys.frozen`` branch instead (covered by
    ``test_resolve_install_dir_frozen_mode_uses_sys_executable``).
    """
    from allaganeye.integrity import _resolve_install_dir

    init_path = tmp_path / "lib" / "allaganeye" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    init_path.write_text("", encoding="utf-8")

    assert _resolve_install_dir(init_path) == tmp_path


def test_default_manifest_path_under_install_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_default_manifest_path returns <install dir>/integrity-manifest.json (dev / legacy path).

    Patches the module-level Path-from-__file__ resolution so the test is
    independent of where pytest finds the actual package. Exercises the
    legacy ``<install dir>/lib/allaganeye/__init__.py`` layout; v0.3.0+
    PyInstaller frozen layout is covered by the frozen-mode test.
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


def test_log_written_when_manifest_missing(tmp_path: Path) -> None:
    """check() writes log even when integrity-manifest.json itself is missing.

    PR #702 review (#1): Rust check_install_dir_with_paths logs manifest
    corruption as missing=[manifest_path]. Python must mirror so bug-report
    flow gives a consistent "attach logs/error-YYYYMMDD.log" instruction
    regardless of failure path.
    """
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    missing_manifest = install / "integrity-manifest.json"
    # File is absent: load_manifest will raise IntegrityError(not found)

    with pytest.raises(IntegrityError) as exc_info:
        check(missing_manifest, install_dir=install)
    assert "not found" in str(exc_info.value)

    log_files = list((install / "logs").glob("error-*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "integrity check failed" in content
    # Log encodes path via json.dumps so Windows backslashes become \\.
    # Basename containment is enough proof the manifest path is logged.
    assert missing_manifest.name in content


def test_log_written_when_manifest_invalid_json(tmp_path: Path) -> None:
    """check() writes log when integrity-manifest.json is malformed JSON."""
    from allaganeye.integrity import check

    install = tmp_path / "install"
    install.mkdir()
    manifest = install / "integrity-manifest.json"
    manifest.write_text("not json", encoding="utf-8")

    with pytest.raises(IntegrityError) as exc_info:
        check(manifest, install_dir=install)
    assert "invalid JSON" in str(exc_info.value)

    log_files = list((install / "logs").glob("error-*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    # JSON-encoded path: basename containment is the cross-platform assertion.
    assert manifest.name in content


def test_load_manifest_raises_on_bom_prefixed_json(tmp_path: Path) -> None:
    """BOM-prefixed manifest -> IntegrityError (#729 latent bug pin).

    scripts/build-portable-zip.ps1 used Set-Content -Encoding UTF8 which
    emits UTF-8 with BOM on Windows PowerShell 5.1 (PS 6.0+ emits BOM-less).
    json.loads rejects the leading U+FEFF as `Unexpected UTF-8 BOM`. The
    build script was fixed in #729 to emit BOM-less UTF-8 via
    [IO.File]::WriteAllText regardless of PS version. This test pins the
    Python read side's BOM rejection behavior so that a future accidental
    regression in the build script gets caught at pytest time in addition
    to the Pester / Rust layers.

    Detected during #729 root cause analysis (CLAUDE.md セクション バグ修正時の方針:
    同種バグの横展開チェック). The Python integrity check would also have
    failed on BOM-prefixed manifest, but CI smoke (release.yml shell: pwsh)
    never produced BOM-prefixed manifest so the failure path was untested.
    """
    bad = tmp_path / "bom.json"
    bad.write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"version": 1, "files": []}).encode("utf-8")
    )

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(bad)

    assert "invalid JSON" in str(exc_info.value)
    assert "json_error" in exc_info.value.context
    # JSONDecodeError の message に "BOM" が含まれることまでは assert しない
    # (Python version 差で文言が変わる可能性があるため、failure category だけ pin)


def test_resolve_install_dir_frozen_mode_uses_sys_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In PyInstaller frozen mode (#752), install dir derives from sys.executable.

    Layout: <install dir>/allaganeye/allaganeye.exe -> install dir = parent.parent.
    The path passed to ``_resolve_install_dir`` (the package __init__ path) is
    *ignored* in frozen mode because PyInstaller puts the .py files inside
    library.zip and __file__ no longer points at a real disk location.
    """
    import sys

    from allaganeye.integrity import _resolve_install_dir

    fake_install = tmp_path / "install"
    fake_exe = fake_install / "allaganeye" / "allaganeye.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_text("", encoding="utf-8")

    # Simulate PyInstaller frozen launcher.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    # __init__ path is ignored in frozen mode; pass any dummy value.
    dummy_init = tmp_path / "ignored" / "__init__.py"

    assert _resolve_install_dir(dummy_init) == fake_install


def test_resolve_install_dir_dev_mode_unchanged_when_sys_frozen_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In dev / legacy mode (sys.frozen unset), existing path resolution stays.

    Regression guard for #752 to ensure the new sys.frozen branch does not
    change behavior when sys.frozen is False or missing.
    """
    import sys

    from allaganeye.integrity import _resolve_install_dir

    # Ensure sys.frozen is not set (the production CPython interpreter).
    monkeypatch.delattr(sys, "frozen", raising=False)

    init_path = tmp_path / "lib" / "allaganeye" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    init_path.write_text("", encoding="utf-8")

    assert _resolve_install_dir(init_path) == tmp_path
