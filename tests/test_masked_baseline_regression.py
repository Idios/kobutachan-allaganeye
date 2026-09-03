"""masked 録画の baseline 回帰テスト (#925)。

slow + slow_detect マーカー: 実動画必須。`pytest -m slow` / `-m slow_detect` で実行し、
bare pytest からは addopts (`-m 'not slow and not baseline_regen'`) により除外される。
source は `ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER` (既定 `E:/allaganeye-samples`) 配下の
masked-obs-source (台帳 `tests/baselines/source-videos.sha256.json` 参照)。

v0.3.0 時点の masked 検出の根拠は PR #915 の 3 サンプル**不変性確認** (segment 数が
再実行間で一致) に留まり、出力の正しさは検証されていなかった。本 module は OBS
baseline (G1、`test_v030_baseline_regression.py`) と同形の **pin 済み baseline との
bit-exact 一致** で回帰を検証する。baseline は Idios が目視裁定した ground truth
(`tests/baselines/v0.3.0/masked-gt/*.json`) と一致することを確認して commit した
(正しさの根拠は masked-gt の provenance を参照)。baseline / GT の存在と schema は
fast の `test_masked_baseline_meta.py` が通常 CI で守る。
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_DIR = _REPO_ROOT / "tests" / "baselines" / "v0.3.0"
_COMPARE_SCRIPT = _REPO_ROOT / "scripts" / "compare-baseline.py"

_SOURCE_DIR_ENV = "ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER"
_DEFAULT_SOURCE_DIR = "E:/allaganeye-samples"

pytestmark = [pytest.mark.slow, pytest.mark.slow_detect]

# (label, source 相対 path, baseline metadata ファイル名)。
# source は tests/baselines/source-videos.sha256.json の masked-obs-source カテゴリ。
_MASKED_BASELINES = [
    (
        "masked-20260527",
        "20250527-29/20250527-29/2026-05-27 21-27-57.mkv",
        "masked-20260527.metadata.json",
    ),
    (
        "masked-20260529",
        "20250527-29/20250527-29/2026-05-29 20-58-34.mkv",
        "masked-20260529.metadata.json",
    ),
]

# 受け入れ条件「masked 録画 2 本以上」。fast の test_masked_baseline_meta.py が
# 存在を hard gate する (両ファイルで期待集合を一致させる)。


def _masked_source_dir() -> Path:
    """masked source dir を解決する。無ければ skip (release gate 環境でのみ実行)。"""
    import os

    env_path = Path(os.environ.get(_SOURCE_DIR_ENV) or _DEFAULT_SOURCE_DIR)
    if not env_path.is_dir():
        pytest.skip(f"sample video directory not found: {env_path}")
    return env_path


@pytest.mark.parametrize(
    "label,relpath,baseline_name",
    _MASKED_BASELINES,
    ids=[b[0] for b in _MASKED_BASELINES],
)
def test_masked_detect_matches_pinned_baseline(
    label, relpath, baseline_name, tmp_output_dir
) -> None:
    """masked 録画を detect し、pin 済み baseline と matches/gaps が完全一致 (#925)。

    G1 (OBS Class A) と同形。`--no-cache` で必ず実 detect する。video が無い
    環境では skip (release gate 環境のみで実行)。baseline は
    `test_masked_baseline_meta.py` が存在を保証する。
    """
    source_dir = _masked_source_dir()
    video = source_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    out_meta = tmp_output_dir / "metadata.json"
    cmd = [
        sys.executable,
        "-m",
        "allaganeye",
        "detect",
        str(video),
        "-o",
        str(tmp_output_dir),
        "--no-cache",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    assert result.returncode == 0, f"detect failed: {result.stderr}"
    assert out_meta.exists(), "metadata.json not produced"

    baseline_path = _BASELINE_DIR / baseline_name
    cmp = subprocess.run(
        [sys.executable, str(_COMPARE_SCRIPT), str(baseline_path), str(out_meta)],
        capture_output=True,
        text=True,
    )
    assert cmp.returncode == 0, (
        f"masked baseline diff for {label}: {cmp.stdout} {cmp.stderr}"
    )
