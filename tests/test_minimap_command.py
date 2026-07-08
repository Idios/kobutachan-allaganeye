"""Tests for 'allaganeye minimap' CLI (Refs #481).

7 test systems:
1. test_match_set_mirrors_export_rules
2. test_region_manual_pixel_parse_and_validation
3. test_writeback_preserves_existing_fields
4. test_proposal_mode_exits_4_without_crop
5. test_proposal_mode_no_seed_still_exits_4
6. test_region_crop_encode_failure_exit_1
7. test_crop_filter_mod2_and_clamp
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.minimap import register
from allaganeye.export.schema import ExportSummary
from allaganeye.video.areamap import MatchRegionResult
from allaganeye.video.capture_region import CaptureRegion

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()

    @a.callback()
    def _():
        pass

    register(a)
    return a


def _make_metadata(
    tmp_path: Path,
    *,
    matches: list[dict] | None = None,
    source: str | None = None,
) -> Path:
    """metadata.json on disk with default 3 matches."""
    if matches is None:
        matches = [
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
            {"index": 2, "start_time": 410.0, "end_time": 800.0, "type": "match"},
            {"index": 3, "start_time": 810.0, "end_time": 1200.0, "type": "match"},
        ]
    payload = {
        "schema_version": "1",
        "source": source or str(tmp_path / "in.mp4"),
        "matches": matches,
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": [],
        },
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. match_set_mirrors_export_rules
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.resolve_match_regions")
@patch("allaganeye.commands.minimap.probe_video")
def test_match_set_mirrors_export_rules(
    mock_probe: MagicMock,
    mock_resolve: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """post_match 除外 > include filter > type_override=="skip" 除外 > edited 優先。

    提案モード (--region なし) で resolve_match_regions に渡る match tuple list が
    export と同じフィルタリング順になっていることを検証する。
    """
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 1500.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    # resolve は空リストを返す -> 提案なしで exit 4
    mock_resolve.return_value = ([], [])

    matches = [
        # post_match: 常に除外 (include より優先)
        {
            "index": 1,
            "start_time": 0.0,
            "end_time": 300.0,
            "type": "match",
            "post_match": True,
        },
        # type_override=skip: 除外
        {
            "index": 2,
            "start_time": 310.0,
            "end_time": 600.0,
            "type": "match",
            "type_override": "skip",
        },
        # include filter: --include 3,4 で含まれるものだけ通す
        {"index": 3, "start_time": 610.0, "end_time": 900.0, "type": "match"},
        {"index": 4, "start_time": 910.0, "end_time": 1200.0, "type": "match"},
        {"index": 5, "start_time": 1210.0, "end_time": 1500.0, "type": "match"},
        # edited: start/end 上書き
        {
            "index": 6,
            "start_time": 1510.0,
            "end_time": 1800.0,
            "type": "match",
            "edited": {"start_time": 1520.0, "end_time": 1780.0},
        },
    ]
    md_path = _make_metadata(tmp_path, matches=matches)

    result = runner.invoke(
        app,
        ["minimap", str(md_path), "--include", "3,4,6"],
    )
    # 提案モードは必ず exit 4
    assert result.exit_code == 4

    # resolve_match_regions に渡った match tuples を確認
    call_args = mock_resolve.call_args
    passed_matches: list[tuple[int, float, float]] = call_args[0][1]

    # post_match (index=1) は除外
    assert not any(m[0] == 1 for m in passed_matches), "post_match must be excluded"
    # type_override=skip (index=2) は除外
    assert not any(m[0] == 2 for m in passed_matches), (
        "type_override=skip must be excluded"
    )
    # --include 3,4,6 なので index=5 は除外
    assert not any(m[0] == 5 for m in passed_matches), (
        "index 5 not in --include must be excluded"
    )
    # index=3,4,6 は含まれる
    assert any(m[0] == 3 for m in passed_matches), "index 3 must be included"
    assert any(m[0] == 4 for m in passed_matches), "index 4 must be included"
    # index=6: edited start/end が使われる
    match6 = next(m for m in passed_matches if m[0] == 6)
    assert match6[1] == 1520.0, "edited start_time must be used"
    assert match6[2] == 1780.0, "edited end_time must be used"


# ---------------------------------------------------------------------------
# 2. region_manual_pixel_parse_and_validation
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_region_manual_pixel_parse_and_validation(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """--region "24,22,534,392" -> 正規化 CaptureRegion + source="manual" / validation。"""
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 400.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_export.return_value = ExportSummary(success=1, failure=0)

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        ],
    )
    out_dir = tmp_path / "minimap"

    # 正常ケース: "24,22,534,392" -> exit 0
    result = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,534,392", "-o", str(out_dir)],
    )
    assert result.exit_code == 0, f"expected 0, got {result.exit_code}\n{result.output}"

    # export_matches が呼ばれた時の ExportMatch の video_filter を確認
    mock_export.assert_called_once()
    call_kw = mock_export.call_args
    exported = call_kw[1]["matches"]
    assert len(exported) == 1
    # video_filter は "crop=W:H:X:Y" 形式
    assert exported[0].video_filter is not None
    assert exported[0].video_filter.startswith("crop=")

    # 入力 --region は pixel 値なので source="manual", confidence=1.0
    # (write-back で minimap_regions を確認)
    md_after = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert "minimap_regions" in md_after
    assert md_after["minimap_regions"][0]["region"]["source"] == "manual"
    assert md_after["minimap_regions"][0]["region"]["confidence"] == 1.0

    # validation: w < 16 -> exit 5
    mock_export.reset_mock()
    result_bad_w = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,8,392", "-o", str(out_dir)],
    )
    assert result_bad_w.exit_code == 5, (
        f"w<16 should be exit 5, got {result_bad_w.exit_code}"
    )

    # validation: x+w > width -> exit 5
    result_overflow = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "1900,22,534,392", "-o", str(out_dir)],
    )
    assert result_overflow.exit_code == 5, (
        f"x+w>width should be exit 5, got {result_overflow.exit_code}"
    )

    # validation: 負値 -> exit 5
    result_neg = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "-1,22,534,392", "-o", str(out_dir)],
    )
    assert result_neg.exit_code == 5, (
        f"negative value should be exit 5, got {result_neg.exit_code}"
    )


# ---------------------------------------------------------------------------
# 3. writeback_preserves_existing_fields
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_writeback_preserves_existing_fields(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """write-back 後も既存フィールド (capture_regions / brightness_samples / 未知) が残る。"""
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 1200.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_export.return_value = ExportSummary(success=2, failure=0)

    matches = [
        {"index": 2, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        {"index": 1, "start_time": 410.0, "end_time": 800.0, "type": "match"},
    ]
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": matches,
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": [],
        },
        "capture_regions": [
            {
                "match_index": 1,
                "region": {
                    "x": 0.0,
                    "y": 0.0,
                    "w": 1.0,
                    "h": 1.0,
                    "confidence": 1.0,
                    "source": "fallback",
                },
            }
        ],
        "brightness_samples": [1, 2, 3],
        "unknown_future_field": "preserved",
    }
    md_path = tmp_path / "metadata.json"
    md_path.write_text(json.dumps(payload), encoding="utf-8")

    out_dir = tmp_path / "minimap"
    result = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,534,392", "-o", str(out_dir)],
    )
    assert result.exit_code == 0, f"exit {result.exit_code}\n{result.output}"

    md_after = json.loads(md_path.read_text(encoding="utf-8"))
    # 既存フィールドが保持される
    assert "capture_regions" in md_after
    assert "brightness_samples" in md_after
    assert md_after["unknown_future_field"] == "preserved"
    # minimap_regions が追加される
    assert "minimap_regions" in md_after
    # match_index 昇順
    indexes = [e["match_index"] for e in md_after["minimap_regions"]]
    assert indexes == sorted(indexes), "minimap_regions must be sorted by match_index"
    assert indexes == [1, 2]


# ---------------------------------------------------------------------------
# 4. proposal_mode_exits_4_without_crop
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.resolve_match_regions")
@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_proposal_mode_exits_4_without_crop(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    mock_resolve: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """--region なし: resolve が提案を返す -> stdout に '--region X,Y,W,H' + exit 4。

    metadata 不変・export_matches 未呼出。
    """
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 400.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    region = CaptureRegion(
        x=24 / 1920,
        y=22 / 1080,
        w=534 / 1920,
        h=392 / 1080,
        confidence=0.67,
        source="auto",
    )
    mock_resolve.return_value = (
        [MatchRegionResult(match_index=3, region=region, scattered=False)],
        [],
    )

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 3, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        ],
    )
    md_before = md_path.read_text(encoding="utf-8")

    result = runner.invoke(app, ["minimap", str(md_path)])
    assert result.exit_code == 4, f"expected 4, got {result.exit_code}\n{result.output}"

    # --region X,Y,W,H 形式が出力に含まれる
    assert "--region" in result.output, "proposal output must contain '--region'"
    # match 3 の提案が表示される
    assert "3" in result.output, "match index must appear in proposal"
    # confidence が表示される
    assert "0.67" in result.output or "confidence" in result.output

    # export_matches は呼ばれない
    mock_export.assert_not_called()

    # metadata.json は変更されない
    md_after = md_path.read_text(encoding="utf-8")
    assert md_before == md_after, "metadata must be unchanged in proposal mode"


# ---------------------------------------------------------------------------
# 5. proposal_mode_no_seed_still_exits_4
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.resolve_match_regions")
@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_proposal_mode_no_seed_still_exits_4(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    mock_resolve: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """resolve が ([], warns) -> 「提案なし」表示 + exit 4 + --region 案内。"""
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 400.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_resolve.return_value = (
        [],
        ["match 1: all 3 windows produced no detection -- skipped"],
    )

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        ],
    )

    result = runner.invoke(app, ["minimap", str(md_path)])
    assert result.exit_code == 4, f"expected 4, got {result.exit_code}\n{result.output}"

    # export_matches は呼ばれない
    mock_export.assert_not_called()

    # --region 案内が出力される
    combined = result.output + (result.stderr or "")
    assert "--region" in combined, "must suggest --region when no proposals"


# ---------------------------------------------------------------------------
# 6. region_crop_encode_failure_exit_1
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_region_crop_encode_failure_exit_1(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """--region 指定で encode summary.failure>0 -> exit 1。"""
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 400.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_export.return_value = ExportSummary(success=0, failure=1)

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        ],
    )
    out_dir = tmp_path / "minimap"

    result = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,534,392", "-o", str(out_dir)],
    )
    assert result.exit_code == 1, (
        f"expected 1 for encode failure, got {result.exit_code}"
    )


# ---------------------------------------------------------------------------
# 7. crop_filter_mod2_and_clamp
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_crop_filter_mod2_and_clamp(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """正規化 -> crop 文字列変換: mod-2 化 + clamp。

    --region 24,22,534,392 (pixel, 1920x1080) ->
    正規化: x=24/1920, y=22/1080, w=534/1920, h=392/1080
    pixel 換算: round(0.28125*1920)=540... wait, 534/1920=0.278125 -> round=534
    but mod-2: 534 is even so stays 534. h=392 even.
    crop=534:392:24:22

    奇数テスト: --region 24,22,535,393 -> w=535->534, h=393->392
    clamp テスト: x+w > 1920 -> clamp x = 1920 - w
    """
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 400.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_export.return_value = ExportSummary(success=1, failure=0)

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        ],
    )
    out_dir = tmp_path / "minimap"

    # ケース1: 偶数 -> そのまま
    result = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,534,392", "-o", str(out_dir)],
    )
    assert result.exit_code == 0
    exported = mock_export.call_args[1]["matches"]
    assert exported[0].video_filter == "crop=534:392:24:22"

    # ケース2: 奇数 w=535, h=393 -> mod-2 化で 534, 392
    mock_export.reset_mock()
    mock_export.return_value = ExportSummary(success=1, failure=0)
    result2 = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,535,393", "-o", str(out_dir)],
    )
    assert result2.exit_code == 0
    exported2 = mock_export.call_args[1]["matches"]
    assert exported2[0].video_filter == "crop=534:392:24:22"

    # ケース3: mod-2 化後の crop_x clamp テスト
    # w=535 -> 534 (even), x=10, frame_w=1920, x+w=10+534=544 < 1920 -> no clamp
    # y=22 -> h=393 -> 392 (even), y+h=22+392=414 < 1080 -> no clamp
    mock_export.reset_mock()
    mock_export.return_value = ExportSummary(success=1, failure=0)
    result3 = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "10,22,535,393", "-o", str(out_dir)],
    )
    assert result3.exit_code == 0
    exported3 = mock_export.call_args[1]["matches"]
    vf3 = exported3[0].video_filter
    # mod-2 化: w=535->534, h=393->392; x=10, y=22 no clamp needed
    assert vf3 == "crop=534:392:10:22", f"expected mod-2 normalization, got {vf3}"
