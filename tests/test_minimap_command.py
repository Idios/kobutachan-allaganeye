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

import allaganeye.commands.minimap as minimap_mod
from allaganeye.cli import app as _cli_app
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


@patch("allaganeye.commands.minimap.resolve_match_regions")
@patch("allaganeye.commands.minimap.probe_video")
def test_proposal_mode_resolve_error_exit_3(
    mock_probe: MagicMock,
    mock_resolve: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """提案モード: resolve が VideoProcessingError を raise -> exit 3。"""
    from allaganeye.exceptions import VideoProcessingError

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
    mock_resolve.side_effect = VideoProcessingError(
        "Cannot probe frame at this timestamp"
    )

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
        ],
    )

    result = runner.invoke(app, ["minimap", str(md_path)])
    assert result.exit_code == 3, (
        f"expected 3 for VideoProcessingError, got {result.exit_code}"
    )


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
    # write-back must survive encode failure
    md_after = json.loads(md_path.read_text(encoding="utf-8"))
    assert "minimap_regions" in md_after, "write-back must survive encode failure"


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_region_crop_cancelled_exit_130(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """--region 指定で encode cancelled=True -> exit 130。"""
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
    mock_export.return_value = ExportSummary(success=0, failure=0, cancelled=True)

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
    assert result.exit_code == 130, (
        f"expected 130 for cancelled encode, got {result.exit_code}"
    )
    # write-back must survive encode cancellation
    md_after = json.loads(md_path.read_text(encoding="utf-8"))
    assert "minimap_regions" in md_after, "write-back must survive encode failure"


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
    # write-back: 偶数なので mod-2 前後で変わらず
    md_after = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    mr = md_after["minimap_regions"][0]["region"]
    assert mr["w"] == 534 / 1920, f"expected w={534 / 1920}, got {mr['w']}"
    assert mr["h"] == 392 / 1080, f"expected h={392 / 1080}, got {mr['h']}"

    # ケース2: 奇数 w=535, h=393 -> mod-2 化で 534, 392
    # write-back 後の metadata に記録される値は mod-2 後の値
    mock_export.reset_mock()
    mock_export.return_value = ExportSummary(success=1, failure=0)
    result2 = runner.invoke(
        app,
        ["minimap", str(md_path), "--region", "24,22,535,393", "-o", str(out_dir)],
    )
    assert result2.exit_code == 0
    exported2 = mock_export.call_args[1]["matches"]
    assert exported2[0].video_filter == "crop=534:392:24:22"
    # write-back: 奇数入力 535, 393 -> mod-2 適用後 534, 392 が記録される
    md_after2 = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    mr2 = md_after2["minimap_regions"][0]["region"]
    expected_w = 534 / 1920
    expected_h = 392 / 1080
    assert mr2["w"] == expected_w, (
        f"奇数 w=535 の mod-2 化: 期待値 {expected_w}, 実績 {mr2['w']}"
    )
    assert mr2["h"] == expected_h, (
        f"奇数 h=393 の mod-2 化: 期待値 {expected_h}, 実績 {mr2['h']}"
    )

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


# ---------------------------------------------------------------------------
# 8. Finding 1 [high]: partial re-run must merge with existing minimap_regions
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_partial_rerun_merges_existing_minimap_regions(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """--include 2 の部分再実行で match 1,3 の既存 entry が保全される。

    現行実装は filtered_tuples のみから minimap_regions を再構築するため、
    対象外 match の entry が消える (Finding 1 [high])。
    修正後: match_index merge で保全 + 対象 match は新 region で上書き + 昇順 sort。
    """
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
    mock_export.return_value = ExportSummary(success=1, failure=0)

    # 既存 minimap_regions: match 1,2,3 が既に crop 済み
    existing_region = {
        "x": 0.01,
        "y": 0.02,
        "w": 0.277,
        "h": 0.362,
        "confidence": 1.0,
        "source": "manual",
    }
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
            {"index": 2, "start_time": 410.0, "end_time": 800.0, "type": "match"},
            {"index": 3, "start_time": 810.0, "end_time": 1200.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": [],
        },
        "minimap_regions": [
            {"match_index": 1, "region": existing_region},
            {"match_index": 2, "region": existing_region},
            {"match_index": 3, "region": existing_region},
        ],
    }
    md_path = tmp_path / "metadata.json"
    md_path.write_text(json.dumps(payload), encoding="utf-8")
    md_bytes_before = md_path.read_bytes()

    out_dir = tmp_path / "minimap"

    # --include 2 で match 2 のみ再実行 (新しい region 座標)
    result = runner.invoke(
        app,
        [
            "minimap",
            str(md_path),
            "--region",
            "100,50,400,300",  # 別の region
            "--include",
            "2",
            "-o",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0, f"exit {result.exit_code}\n{result.output}"

    md_after = json.loads(md_path.read_text(encoding="utf-8"))
    regions = md_after.get("minimap_regions", [])

    # match 1,2,3 の 3 entry が残っている
    indexes = sorted(e["match_index"] for e in regions)
    assert indexes == [1, 2, 3], (
        f"対象外 match 1,3 が保全されるべきだが minimap_regions={regions}"
    )

    # match 1,3 は既存 region のまま (不変)
    entry1 = next(e for e in regions if e["match_index"] == 1)
    entry3 = next(e for e in regions if e["match_index"] == 3)
    assert entry1["region"] == existing_region, "match 1 は変更されるべきでない"
    assert entry3["region"] == existing_region, "match 3 は変更されるべきでない"

    # match 2 は新 region (100,50,400,300 -> mod-2 後 400,300)
    entry2 = next(e for e in regions if e["match_index"] == 2)
    new_w = 400 - (400 % 2)  # 400 (even)
    new_h = 300 - (300 % 2)  # 300 (even)
    assert abs(entry2["region"]["w"] - new_w / 1920) < 1e-6, (
        f"match 2 の w が更新されていない: {entry2['region']}"
    )
    assert abs(entry2["region"]["h"] - new_h / 1080) < 1e-6, (
        f"match 2 の h が更新されていない: {entry2['region']}"
    )

    # 昇順 sort 確認
    raw_indexes = [e["match_index"] for e in regions]
    assert raw_indexes == sorted(raw_indexes), "minimap_regions は match_index 昇順"

    _ = md_bytes_before  # used to confirm test was checking a changed file


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_partial_rerun_preserves_malformed_entries(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """malformed entry (dict でない / match_index 欠落) は黙って捨てずに保全される。"""
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 800.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_export.return_value = ExportSummary(success=1, failure=0)

    existing_region = {
        "x": 0.01,
        "y": 0.02,
        "w": 0.277,
        "h": 0.362,
        "confidence": 1.0,
        "source": "manual",
    }
    # malformed: dict でない (文字列) と、match_index が欠落した dict
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
            {"index": 2, "start_time": 410.0, "end_time": 800.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": [],
        },
        "minimap_regions": [
            {"match_index": 1, "region": existing_region},
            "not_a_dict",  # malformed: dict でない
            {"region": existing_region},  # malformed: match_index 欠落
        ],
    }
    md_path = tmp_path / "metadata.json"
    md_path.write_text(json.dumps(payload), encoding="utf-8")

    out_dir = tmp_path / "minimap"

    # --include 2 で match 2 のみ再実行
    result = runner.invoke(
        app,
        [
            "minimap",
            str(md_path),
            "--region",
            "24,22,534,392",
            "--include",
            "2",
            "-o",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0, f"exit {result.exit_code}\n{result.output}"

    md_after = json.loads(md_path.read_text(encoding="utf-8"))
    regions = md_after.get("minimap_regions", [])

    # match 1 の正常 entry は保全される
    assert any(isinstance(e, dict) and e.get("match_index") == 1 for e in regions), (
        "match 1 の正常 entry が保全されていない"
    )

    # match 2 の新 entry が追加される
    assert any(isinstance(e, dict) and e.get("match_index") == 2 for e in regions), (
        "match 2 の新 entry が追加されていない"
    )

    # malformed entries も保全される (round-trip 哲学)
    has_not_a_dict = any(e == "not_a_dict" for e in regions)
    has_no_match_index = any(
        isinstance(e, dict) and "match_index" not in e for e in regions
    )
    assert has_not_a_dict, "malformed string entry が消えている"
    assert has_no_match_index, "match_index 欠落 dict entry が消えている"


# ---------------------------------------------------------------------------
# 9. Finding 2 [medium]: preflight before write-back
# ---------------------------------------------------------------------------


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_collision_preflight_before_writeback(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """filename 衝突 (exit 5) が write-back より前に発火 -> metadata 不変。"""
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 800.0,
        "fps": 60.0,
        "fps_num": 60,
        "fps_den": 1,
        "codec": "h264",
        "audio_codec": None,
    }
    mock_export.return_value = ExportSummary(success=2, failure=0)

    md_path = _make_metadata(
        tmp_path,
        matches=[
            {"index": 1, "start_time": 10.0, "end_time": 400.0, "type": "match"},
            {"index": 2, "start_time": 410.0, "end_time": 800.0, "type": "match"},
        ],
    )
    md_bytes_before = md_path.read_bytes()
    out_dir = tmp_path / "minimap"

    # {idx} を含まない name-pattern -> 2 match で衝突発生 -> exit 5
    result = runner.invoke(
        app,
        [
            "minimap",
            str(md_path),
            "--region",
            "24,22,534,392",
            "--name-pattern",
            "minimap_fixed.mp4",  # idx なし -> collision
            "-o",
            str(out_dir),
        ],
    )
    assert result.exit_code == 5, (
        f"name collision should be exit 5, got {result.exit_code}\n{result.output}"
    )

    # metadata は不変 (byte 比較)
    md_bytes_after = md_path.read_bytes()
    assert md_bytes_before == md_bytes_after, (
        "preflight 失敗なのに metadata が書き換わっている (Finding 2)"
    )
    # export_matches は呼ばれない
    mock_export.assert_not_called()


@patch("allaganeye.commands.minimap.export_matches")
@patch("allaganeye.commands.minimap.probe_video")
def test_mkdir_failure_preflight_before_writeback(
    mock_probe: MagicMock,
    mock_export: MagicMock,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    """output dir mkdir 失敗 -> 非0 exit + metadata 不変 (Finding 2)。"""
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
    md_bytes_before = md_path.read_bytes()
    out_dir = tmp_path / "minimap"

    with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
        result = runner.invoke(
            app,
            [
                "minimap",
                str(md_path),
                "--region",
                "24,22,534,392",
                "-o",
                str(out_dir),
            ],
        )

    # OSError -> exit 1 (厳密に 1、raw OSError 素通りでない)
    assert result.exit_code == 1, (
        f"mkdir failure should exit exactly 1, got {result.exit_code}"
    )

    # raw OSError ではなく typer.Exit でラップされている (素通り防止)
    # raw OSError なら result.exception が OSError；ラップなら None / SystemExit
    if result.exception is not None:
        assert not isinstance(result.exception, OSError), (
            f"mkdir failure should be wrapped in typer.Exit, got raw {type(result.exception).__name__}"
        )

    # stderr / stdout に traceback 文字列なし (clean な契約)
    output = result.stdout + result.stderr
    assert "Traceback" not in output, (
        f"mkdir failure should not have traceback in output:\n{output}"
    )

    # metadata は不変 (Finding 2: mkdir より前に write してはならない)
    md_bytes_after = md_path.read_bytes()
    assert md_bytes_before == md_bytes_after, (
        "mkdir 失敗前に metadata が書き換わっている (Finding 2)"
    )
    # export_matches は呼ばれない
    mock_export.assert_not_called()


# ---------------------------------------------------------------------------
# 11. minimap crop --json wire mode (#893)
# ---------------------------------------------------------------------------


def _write_metadata(tmp_path: Path, source: Path) -> Path:
    meta = {
        "schema_version": "1",
        "source": str(source),
        "matches": [
            {"index": 1, "type": "fl_match", "start_time": 60.0, "end_time": 120.0},
        ],
    }
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(meta), encoding="utf-8")
    return p


def test_minimap_json_emits_ndjson_result_and_summary(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)

    # Stub probe (frame size) and export_matches (encode) so no ffmpeg runs.
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    def fake_export_matches(*, matches, progress_cb, **kwargs):
        from allaganeye.export.schema import ProgressEvent

        for m in matches:
            progress_cb(
                ProgressEvent.result(
                    match_index=m.index,
                    output_path=Path("out") / f"{m.index:03}.mp4",
                    duration_ms=1000,
                    encoder_used="libx264",
                )
            )
        return ExportSummary(
            success=len(matches), failure=0, skipped=0, cancelled=False
        )

    monkeypatch.setattr(minimap_mod, "export_matches", fake_export_matches)

    result = runner.invoke(
        _cli_app,
        ["minimap", str(meta_path), "--region", "10,20,300,400", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    types = [ln["type"] for ln in lines]
    assert "result" in types
    assert types[-1] == "summary"
    assert lines[-1]["success"] == 1


# ---------------------------------------------------------------------------
# 12. minimap --expected-mtime CAS guard (#893)
# ---------------------------------------------------------------------------


def test_minimap_proposal_json_emits_proposal_lines_exit4(tmp_path, monkeypatch, app):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    class _Region:
        x, y, w, h, confidence = 0.01, 0.02, 0.15, 0.20, 0.9

    class _MR:
        match_index = 1
        region = _Region()
        scattered = False

    monkeypatch.setattr(
        minimap_mod,
        "resolve_match_regions",
        lambda source, tuples: ([_MR()], []),
    )

    result = runner.invoke(app, ["minimap", str(meta_path), "--json"])
    assert result.exit_code == 4, result.stdout
    lines = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    prop = [ln for ln in lines if ln["type"] == "proposal"]
    assert prop and prop[0]["match_index"] == 1
    # normalized region -> pixel ints at 1920x1080
    assert prop[0]["region"] == {"x": 19, "y": 22, "w": 288, "h": 216}


def test_minimap_proposal_json_none_region_emits_null_region_exit4(
    tmp_path, monkeypatch, app
):
    """--json 提案モード: mr.region is None の match は region: null を emit し exit 4。

    Refs #893: spec section 5.2 requires region:null when no region detected.
    Rust parser is null-capable; unconditional r.x/.y/.w/.h access would raise
    AttributeError if region is None.
    """
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    class _MRNone:
        match_index = 1
        region = None  # None region: no detection for this match
        scattered = False

    monkeypatch.setattr(
        minimap_mod,
        "resolve_match_regions",
        lambda source, tuples: ([_MRNone()], []),
    )

    result = runner.invoke(app, ["minimap", str(meta_path), "--json"])
    assert result.exit_code == 4, result.stdout
    lines = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    prop = [ln for ln in lines if ln["type"] == "proposal"]
    assert prop, f"expected at least one proposal line, got lines={lines}"
    assert prop[0]["match_index"] == 1
    # region must be null (None) when no detection
    assert prop[0]["region"] is None, (
        f"expected region=null for None-region match, got {prop[0]['region']}"
    )


def test_minimap_expected_mtime_conflict_aborts_without_write(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )
    wrote = {"called": False}
    monkeypatch.setattr(
        minimap_mod,
        "write_metadata_atomic",
        lambda p, payload: wrote.__setitem__("called", True),
    )
    # export_matches must never run when the CAS aborts.
    monkeypatch.setattr(
        minimap_mod,
        "export_matches",
        lambda **k: (_ for _ in ()).throw(AssertionError("encode ran on conflict")),
    )
    # Pass a stale expected mtime (0) -> current mtime differs -> conflict.
    result = runner.invoke(
        _cli_app,
        [
            "minimap",
            str(meta_path),
            "--region",
            "10,20,300,400",
            "--json",
            "--expected-mtime",
            "0",
        ],
    )
    assert result.exit_code == 6, result.stdout
    assert wrote["called"] is False


def test_minimap_expected_mtime_match_writes(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        minimap_mod,
        "export_matches",
        lambda **k: ExportSummary(success=1, failure=0, skipped=0, cancelled=False),
    )
    current_ms = meta_path.stat().st_mtime_ns // 1_000_000
    result = runner.invoke(
        _cli_app,
        [
            "minimap",
            str(meta_path),
            "--region",
            "10,20,300,400",
            "--json",
            "--expected-mtime",
            str(current_ms),
        ],
    )
    assert result.exit_code == 0, result.stdout
    written = json.loads(meta_path.read_text(encoding="utf-8"))
    assert written["minimap_regions"][0]["match_index"] == 1


# ---------------------------------------------------------------------------
# 13. --exclude option mirrors Rust/GUI contract (#893 HIGH fix)
# ---------------------------------------------------------------------------


def _write_metadata_2matches(tmp_path: Path, source: Path) -> Path:
    """metadata.json with 2 matches for --exclude tests."""
    meta = {
        "schema_version": "1",
        "source": str(source),
        "matches": [
            {"index": 1, "type": "fl_match", "start_time": 60.0, "end_time": 120.0},
            {"index": 2, "type": "fl_match", "start_time": 180.0, "end_time": 240.0},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": [],
        },
    }
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(meta), encoding="utf-8")
    return p


def test_exclude_crop_mode_skips_excluded_match(tmp_path, monkeypatch):
    """--exclude 2 in crop mode: only match 1 reaches export_matches; exit 0.

    RED: currently fails with exit 2 (usage error 'No such option: --exclude').
    GREEN: after adding --exclude to minimap CLI, match index 2 is absent.
    """
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata_2matches(tmp_path, source)

    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    captured: list = []

    def fake_export_matches(*, matches, progress_cb, **kwargs):
        captured.extend(matches)
        return ExportSummary(
            success=len(matches), failure=0, skipped=0, cancelled=False
        )

    monkeypatch.setattr(minimap_mod, "export_matches", fake_export_matches)

    result = runner.invoke(
        _cli_app,
        [
            "minimap",
            str(meta_path),
            "--region",
            "10,20,300,400",
            "--json",
            "--exclude",
            "2",
        ],
    )
    assert result.exit_code == 0, (
        f"expected exit 0 with --exclude 2, got {result.exit_code}\nstdout={result.stdout}"
    )
    passed_indexes = [m.index for m in captured]
    assert 2 not in passed_indexes, (
        f"match index 2 should be excluded but was passed to export_matches: {passed_indexes}"
    )
    assert 1 in passed_indexes, (
        f"match index 1 should be included but was absent: {passed_indexes}"
    )


def test_proposal_plaintext_none_region_exits4_no_traceback(tmp_path, monkeypatch, app):
    """plain-text 提案モード: mr.region is None の match は exit 4 + 案内メッセージ。

    RED: plain-text path が r.x 等を直接参照するため AttributeError が発生 (exit 1)。
    GREEN: None guard 追加後は exit 4 + 「領域を自動検出できませんでした」メッセージ。
    No traceback must appear.

    Refs #893 (symmetry with --json None-region guard).
    """
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    class _MRNone:
        match_index = 1
        region = None  # None region: no detection for this match
        scattered = False

    monkeypatch.setattr(
        minimap_mod,
        "resolve_match_regions",
        lambda source, tuples: ([_MRNone()], []),
    )

    # plain-text mode: NO --json flag
    result = runner.invoke(app, ["minimap", str(meta_path)])
    assert result.exit_code == 4, (
        f"expected exit 4 for None-region plain-text proposal, "
        f"got {result.exit_code}\nstdout={result.output}"
    )
    # 案内メッセージが出力される
    assert "領域を自動検出できませんでした" in result.output, (
        f"expected guidance message in output, got:\n{result.output}"
    )
    # トレースバックは出ない
    assert "Traceback" not in result.output, (
        f"plain-text None-region must not raise traceback:\n{result.output}"
    )
    assert "AttributeError" not in result.output, (
        f"plain-text None-region must not raise AttributeError:\n{result.output}"
    )


def test_exclude_proposal_mode_skips_excluded_match(tmp_path, monkeypatch, app):
    """--exclude 1 in proposal mode: resolve_match_regions receives only match 2; exit 4.

    RED: currently fails with exit 2 (usage error 'No such option: --exclude').
    GREEN: after adding --exclude, match 1 is absent from tuples passed to resolve.
    """
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata_2matches(tmp_path, source)

    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    received_tuples: list = []

    def fake_resolve(source_video, match_tuples):
        received_tuples.extend(match_tuples)
        return ([], [])

    monkeypatch.setattr(minimap_mod, "resolve_match_regions", fake_resolve)

    result = runner.invoke(
        app,
        ["minimap", str(meta_path), "--json", "--exclude", "1"],
    )
    assert result.exit_code == 4, (
        f"proposal mode should exit 4 with --exclude 1, got {result.exit_code}\nstdout={result.stdout}"
    )
    passed_indexes = [t[0] for t in received_tuples]
    assert 1 not in passed_indexes, (
        f"match index 1 should be excluded but was passed to resolve: {passed_indexes}"
    )
    assert 2 in passed_indexes, (
        f"match index 2 should be included but was absent: {passed_indexes}"
    )
