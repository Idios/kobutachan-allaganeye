# tests/test_vtuber_timeline.py
"""Unit tests for the VTuber presence x motion timeline (V0-V2, spec 2026-07-17)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from allaganeye.video.capture_region import ScorebarLocalization
from allaganeye.video.vtuber_timeline import (
    GapProbe,
    TIMELINE_MAD_MIN,
    TIMELINE_PAIR_DT,
    TimelineProbe,
    _VT_ANCHOR_MIN_CONF,
    adjudicate_gap,
    detect_matches_timeline,
    resolve_vtuber_anchor,
    scan_timeline,
    segment_timeline,
)


def _probes(spec: str, stride: float = 10.0) -> list[TimelineProbe]:
    """Build probes from a compact string: M=match evidence, l=lobby(absent),
    f=frozen-present (present but band_mad < mad_min), u=unknown (decode fail)."""
    out: list[TimelineProbe] = []
    for i, ch in enumerate(spec):
        t = i * stride
        if ch == "M":
            out.append(TimelineProbe(t=t, present=True, band_mad=5.0))
        elif ch == "l":
            out.append(TimelineProbe(t=t, present=False, band_mad=8.0))
        elif ch == "f":
            out.append(TimelineProbe(t=t, present=True, band_mad=0.3))
        elif ch == "u":
            out.append(TimelineProbe(t=t, present=False, band_mad=None))
        else:  # pragma: no cover - guard for typos in test specs
            raise ValueError(ch)
    return out


class TestSegmentTimeline:
    def test_single_match_with_lobby_flanks(self):
        # 6 lobby / 40 match / 6 lobby probes (10s stride) -> one segment >= 300s
        probes = _probes("l" * 6 + "M" * 40 + "l" * 6)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 1
        assert segs[0]["type"] == "fl_match"
        # segment must cover the match core (window smoothing may extend edges)
        assert segs[0]["start"] <= 70.0
        assert segs[0]["end"] >= 440.0

    def test_short_island_dropped_by_duration_prior(self):
        # 20 probes (200s) of evidence < min_match_duration -> no segment
        probes = _probes("l" * 10 + "M" * 20 + "l" * 10)
        assert segment_timeline(probes, min_match_duration=300.0) == []

    def test_fn_dropout_bridged_by_window_quorum(self):
        # in-match presence FN run of 3 probes (30s) inside a long match is
        # bridged by the rolling window (>=2 of 9 evidence)
        probes = _probes("M" * 20 + "lll" + "M" * 20)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 1

    def test_long_absent_gap_splits_two_matches(self):
        # 200s absent gap (20 probes) -> two separate segments (PoC: true
        # boundaries show ~0% presence; window quorum cannot bridge 20 probes)
        probes = _probes("M" * 40 + "l" * 20 + "M" * 40)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 2

    def test_frozen_present_is_not_evidence(self):
        # replay/staging screens: present but frozen (band_mad < mad_min)
        # must not extend or create segments (PoC report section 7.4)
        probes = _probes("M" * 40 + "f" * 20 + "l" * 10 + "M" * 40)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 2
        # first segment must not absorb the frozen run's tail
        assert segs[0]["end"] <= 40 * 10.0 + 5 * 10.0

    def test_unknown_probes_are_not_evidence(self):
        probes = _probes("M" * 40 + "u" * 20 + "M" * 40)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 2

    def test_empty_input(self):
        assert segment_timeline([], min_match_duration=300.0) == []

    def test_mad_threshold_boundary(self):
        # band_mad exactly at threshold counts as evidence (>=)
        probes = [
            TimelineProbe(t=i * 10.0, present=True, band_mad=TIMELINE_MAD_MIN)
            for i in range(40)
        ]
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 1


class TestResolveVtuberAnchor:
    def _run(self, localize_results):
        """localize_from_rgb_bytes を順に localize_results を返す stub にして実行。"""
        raw = b"\x00" * (1920 * 1080 * 3)
        with (
            patch(
                "allaganeye.video.detector._probe_frame_rgb_hires",
                return_value=raw,
            ),
            patch(
                "allaganeye.video.capture_region.localize_from_rgb_bytes",
                side_effect=localize_results,
            ),
        ):
            return resolve_vtuber_anchor(Path("dummy.mp4"), duration_hint=3600.0)

    def test_onsal_grade_confidence_resolves(self):
        # conf 0.55-0.6 (masked の 0.7 filter では全滅する帯域) が通ること
        hit = ScorebarLocalization(532, 1147, 0, 45, 0.58)
        results = [hit] * 10 + [None] * 38
        anchor = self._run(results)
        assert anchor is not None
        assert anchor.y_top == 0

    def test_low_conf_hits_are_prefiltered(self):
        # conf < 0.5 のみ -> miss 扱いで anchor 不成立
        weak = ScorebarLocalization(532, 1147, 0, 45, _VT_ANCHOR_MIN_CONF - 0.1)
        anchor = self._run([weak] * 48)
        assert anchor is None

    def test_insufficient_hits(self):
        hit = ScorebarLocalization(532, 1147, 0, 45, 0.9)
        anchor = self._run([hit] * 4 + [None] * 44)  # < _VT_ANCHOR_MIN_HITS
        assert anchor is None

    def test_decode_failure_returns_none_gracefully(self, caplog):
        import logging

        with (
            patch(
                "allaganeye.video.detector._probe_frame_rgb_hires",
                return_value=None,
            ),
            caplog.at_level(logging.WARNING, logger="allaganeye.video.vtuber_timeline"),
        ):
            result = resolve_vtuber_anchor(Path("dummy.mp4"), duration_hint=3600.0)
        assert result is None
        # None は consensus miss 由来であること (例外握り潰し由来でないこと) を確認。
        # exception handler が発火すると "vtuber anchor consensus failed" が emit される。
        assert "vtuber anchor consensus failed" not in caplog.text


def _synthetic_frame(brightness: int) -> bytes:
    return bytes([brightness]) * (1920 * 1080 * 3)


class TestScanTimeline:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def test_probe_pair_computes_band_mad(self):
        # frame1=100, frame2=110 -> band MAD = 10 (band 領域も全画素同値のため)
        frames = {0.0: _synthetic_frame(100), TIMELINE_PAIR_DT: _synthetic_frame(110)}

        def fake_probe(video_path, t):
            return frames.get(t)

        with (
            patch(
                "allaganeye.video.detector._probe_frame_rgb_hires",
                side_effect=fake_probe,
            ),
            patch(
                "allaganeye.video.capture_region.localize_scorebar_at_anchor",
                return_value=self.ANCHOR,
            ),
        ):
            probes = scan_timeline(
                Path("dummy.mp4"), duration_hint=10.0, anchor=self.ANCHOR
            )
        assert len(probes) == 1
        assert probes[0].present is True
        assert probes[0].band_mad is not None
        assert abs(probes[0].band_mad - 10.0) < 0.01

    def test_decode_failure_yields_unknown_probe(self):
        with patch(
            "allaganeye.video.detector._probe_frame_rgb_hires", return_value=None
        ):
            probes = scan_timeline(
                Path("dummy.mp4"), duration_hint=30.0, anchor=self.ANCHOR
            )
        assert all(p.band_mad is None and p.present is False for p in probes)


class TestDetectMatchesTimeline:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _fake_scan(self, spec: str):
        return _probes(spec)

    def test_anchor_miss_returns_none(self):
        with patch(
            "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
            return_value=None,
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=3600.0, min_match_duration=300.0
                )
                is None
            )

    def test_success_returns_boundaries_and_region(self):
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=self._fake_scan("l" * 6 + "M" * 40 + "l" * 6),
            ),
        ):
            result = detect_matches_timeline(
                Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
            )
        assert result is not None
        boundaries, region_timeline = result
        assert len(boundaries) == 1
        assert region_timeline.coarse.source == "band"
        assert region_timeline.fallback_reason is None

    def test_majority_unknown_aborts_to_none(self):
        # 50% 超 decode 失敗 -> timeline を信頼せず None (縮退 floor)
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=self._fake_scan("M" * 10 + "u" * 42),
            ),
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
                )
                is None
            )

    def test_empty_segmentation_returns_none(self, caplog):
        # Codex R1 (high): anchor 成功 + UNKNOWN 過半未満でも segmentation が
        # 空なら None (= legacy band-crop へ縮退)。空 ([], region) を返すと
        # caller が authoritative 扱いし「現状より悪化しない」floor が破れる。
        import logging

        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                # 全 probe lobby (absent) -> evidence ゼロ -> segment ゼロ
                return_value=self._fake_scan("l" * 52),
            ),
            caplog.at_level(logging.WARNING, logger="allaganeye.video.vtuber_timeline"),
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
                )
                is None
            )
        assert "no segments" in caplog.text


def _gap_probes(spec: str, stride: float = 1.0) -> list[GapProbe]:
    """M=present+moving (in-match FN run), l=absent+moving (lobby),
    f=present+frozen (replay/result static), b=blackout (band_b ~0),
    u=unknown (decode failure)."""
    out: list[GapProbe] = []
    for i, ch in enumerate(spec):
        t = i * stride
        if ch == "M":
            out.append(GapProbe(t=t, present=True, band_mad=8.0, band_b=95.0))
        elif ch == "l":
            out.append(GapProbe(t=t, present=False, band_mad=6.0, band_b=110.0))
        elif ch == "f":
            out.append(GapProbe(t=t, present=True, band_mad=0.4, band_b=120.0))
        elif ch == "b":
            out.append(GapProbe(t=t, present=False, band_mad=2.0, band_b=5.0))
        elif ch == "u":
            out.append(GapProbe(t=t, present=False, band_mad=None, band_b=None))
        else:  # pragma: no cover
            raise ValueError(ch)
    return out


class TestAdjudicateGap:
    def test_fn_run_merges(self):
        # FN run: ~24% present + always moving -> merge
        probes = _gap_probes(("M" + "lll") * 60)  # 25% present, 240 probes
        assert adjudicate_gap(probes) == "merge"

    def test_true_lobby_is_boundary(self):
        # true lobby: present ~0.5% -> boundary
        probes = _gap_probes("l" * 100 + "M" + "l" * 99)  # 0.5%
        assert adjudicate_gap(probes) == "boundary"

    def test_blackout_marker_forces_boundary(self):
        # even with high rate, blackout marker forces boundary (positive marker priority)
        probes = _gap_probes("M" * 30 + "bbb" + "M" * 30)
        assert adjudicate_gap(probes) == "boundary"

    def test_frozen_run_forces_boundary(self):
        # replay/result: present but frozen run (>= FROZEN_RUN_MIN_PROBES)
        # -> boundary even at 33% rate
        probes = _gap_probes("f" * 15 + "l" * 30)
        assert adjudicate_gap(probes) == "boundary"

    def test_short_frozen_blip_does_not_force_boundary(self):
        # frozen run < FROZEN_RUN_MIN_PROBES: no marker -> falls through to rate
        probes = _gap_probes(("M" + "lll") * 20 + "fff" + ("M" + "lll") * 20)
        assert adjudicate_gap(probes) == "merge"

    def test_empty_or_all_unknown_is_boundary(self):
        # no evidence -> conservative boundary (do not merge without proof)
        assert adjudicate_gap([]) == "boundary"
        assert adjudicate_gap(_gap_probes("u" * 20)) == "boundary"

    def test_rate_threshold_boundary_case(self):
        # rate == merge_rate (10%) is merge (>= comparison)
        probes = _gap_probes(("M" + "l" * 9) * 20)  # exactly 10%
        assert adjudicate_gap(probes) == "merge"
