# tests/test_vtuber_timeline.py
"""Unit tests for the VTuber presence x motion timeline (V0-V2, spec 2026-07-17)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.video.capture_region import ScorebarLocalization
from allaganeye.video.detector import MatchBoundary
from allaganeye.video.vtuber_timeline import (
    EDGE_EXT_END_S,
    EDGE_EXT_S,
    FROZEN_MAX,
    GapProbe,
    SNAP_FLICKER_TOL,
    TIMELINE_MAD_MIN,
    TIMELINE_PAIR_DT,
    TimelineProbe,
    _VT_ANCHOR_MIN_CONF,
    _evidence_flags,
    _snap_end,
    _snap_start,
    _tolerant_runs,
    adjudicate_gap,
    detect_matches_timeline,
    probe_gap,
    refine_segments,
    resolve_vtuber_anchor,
    scan_timeline,
    segment_timeline,
    snap_segment_edges,
)  # BLACKOUT_ADJACENCY_S は Fix 2 (#895 P3 3周目) で撤廃済み
# END_FAR_RESCUE_S / INTRA_EVIDENCE_BEFORE_S / INTRA_EVIDENCE_AFTER_S は
# テスト内コメントで参照するが、アサートは数値リテラルで記述する


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

    def test_present_with_unknown_mad_is_not_evidence(self):
        # present=True でも band_mad=None (motion decode 失敗) は evidence にしない
        # (述語の band_mad is not None guard の直接 pin)
        probes = [
            TimelineProbe(t=i * 10.0, present=True, band_mad=None) for i in range(60)
        ]
        assert segment_timeline(probes, min_match_duration=300.0) == []


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
        # rate == merge_rate (15%) is merge (>= comparison)
        # 100 probes: present=15, absent=85 -> rate=15%
        probes = _gap_probes(("M" + "l" * 5) * 15 + "l" * 10)  # exactly 15/100=15%
        assert adjudicate_gap(probes) == "merge"


class TestEvidenceFlagsAndTolerantRuns:
    """Unit tests for _evidence_flags and _tolerant_runs helpers."""

    def test_evidence_flags_present_and_moving(self):
        # present=True AND band_mad >= FROZEN_MAX -> True
        probes = _gap_probes("M" * 3 + "l" * 2 + "f" * 2 + "u" * 1)
        flags = _evidence_flags(probes, frozen_max=FROZEN_MAX)
        assert flags == [True, True, True, False, False, False, False, False]

    def test_evidence_flags_frozen_present_is_false(self):
        # frozen-present (band_mad < FROZEN_MAX): evidence = False even if present
        probes = _gap_probes("f" * 5)
        flags = _evidence_flags(probes, frozen_max=FROZEN_MAX)
        assert all(f is False for f in flags)

    def test_evidence_flags_unknown_is_false(self):
        # UNKNOWN (band_mad=None): evidence = False
        probes = _gap_probes("u" * 4)
        flags = _evidence_flags(probes, frozen_max=FROZEN_MAX)
        assert all(f is False for f in flags)

    def test_tolerant_runs_no_gaps(self):
        flags = [True, True, True, False, False]
        runs = _tolerant_runs(flags, tol=SNAP_FLICKER_TOL)
        assert runs == [(0, 2)]

    def test_tolerant_runs_gap_within_tol(self):
        # gap of exactly tol False -> single merged run
        tol = 3
        flags = [True, True] + [False] * tol + [True, True]
        runs = _tolerant_runs(flags, tol=tol)
        assert len(runs) == 1
        assert runs[0] == (0, len(flags) - 1)

    def test_tolerant_runs_gap_exceeds_tol(self):
        # gap of tol+1 False -> two separate runs
        tol = 3
        flags = [True] + [False] * (tol + 1) + [True]
        runs = _tolerant_runs(flags, tol=tol)
        assert len(runs) == 2

    def test_tolerant_runs_empty(self):
        assert _tolerant_runs([], tol=SNAP_FLICKER_TOL) == []

    def test_tolerant_runs_all_false(self):
        assert _tolerant_runs([False] * 10, tol=SNAP_FLICKER_TOL) == []

    def test_tolerant_runs_unknown_mixed(self):
        # UNKNOWN maps to False in flags -> gaps consumed by tol
        probes = _gap_probes("M" * 5 + "u" * 3 + "M" * 5)
        flags = _evidence_flags(probes, frozen_max=FROZEN_MAX)
        # tol=10 can bridge 3 unknowns -> single run
        runs = _tolerant_runs(flags, tol=10)
        assert len(runs) == 1

    def test_tolerant_runs_tol_exactly_snap_flicker_tol(self):
        # gap of SNAP_FLICKER_TOL False -> merged (boundary case)
        flags = [True] + [False] * SNAP_FLICKER_TOL + [True]
        runs = _tolerant_runs(flags, tol=SNAP_FLICKER_TOL)
        assert len(runs) == 1


class TestSnapSegmentEdges:
    def test_blackout_snap_both_edges_with_adjacent_evidence(self):
        # P3 6周目 (Bug B 局所窓変更後): セマンティクス更新。
        # leading evidence (M*5, t=0-4) -> blackout (bb, t=5-6) -> absent (l*20, t=7-26)
        # -> blackout (bbb, t=27-29) -> trailing evidence (M*5, t=30-34)
        #
        # Priority 1 評価 (最後の in-range blackout run を探す):
        # brun1 (t=5-6): before 5s 窓 [0,5): t=4 (M) -> has_evidence_before=True
        #                after 10s 窓 [6,16]: t=7..16 (absent) -> has_evidence_after=False
        #                -> is_intra_match=False -> last_in_range=brun1
        # brun2 (t=27-29): before 5s 窓 [22,27): t=22..26 (absent) -> has_evidence_before=False
        #                   -> is_intra_match=False -> last_in_range=brun2
        # -> new_start = brun2 end t=29.0
        #
        # new_end = leading evidence run 末尾 (idx 4, t=4.0): evidence-only
        probes = _gap_probes("M" * 5 + "bb" + "l" * 20 + "bbb" + "M" * 5)
        new_end, new_start = snap_segment_edges(0.0, 35.0, probes)
        # end: leading evidence run 末尾 t=4 < mid=17.5 -> 4.0
        assert new_end == probes[4].t
        # start (Bug B 更新): trailing blackout bbb の before 5s 窓に evidence なし
        # -> guard 不発 -> priority 1 採用 -> t=29.0 (blackout bbb end)
        assert new_start == probes[29].t  # t=29.0
        assert new_end < new_start

    def test_blackout_after_mid_snaps_start_without_adjacent_evidence(self):
        # P3 4周目: "M"*5 + "l"*35 + "bb" + "l"*30: prev_end=0, next_start=72, mid=36
        # blackout (idx 40-41): evidence before (M*5) + no evidence after (l*30) ->
        # NOT intra-match (no evidence after) -> priority 1 採用 -> new_start=41.0
        # leading M (idx 0-4): leading run end=idx4, t=4 < mid=36 -> new_end=4.0
        probes = _gap_probes("M" * 5 + "l" * 35 + "bb" + "l" * 30)
        prev_end, next_start = 0.0, 72.0
        new_end, new_start = snap_segment_edges(prev_end, next_start, probes)
        # new_end: evidence run 末尾 t=4 < mid=36 -> 採用
        assert new_end == probes[4].t
        # new_start: blackout end t=41, evidence before (M*5) but no evidence after -> 採用
        assert new_start == probes[41].t

    def test_blackout_adjacent_new_start_snaps(self):
        # "l"*35 + "bb" + "M"*5: blackout (idx35-36) の後に evidence (M*5)
        # blackout に evidence before なし (l*35 は absent) -> not intra-match -> priority 1 採用
        # -> new_start = probes[36].t = 36.0 (blackout snap)
        probes = _gap_probes("l" * 35 + "bb" + "M" * 5)
        prev_end, next_start = 0.0, 42.0
        new_end, new_start = snap_segment_edges(prev_end, next_start, probes)
        # new_end: leading evidence run なし (最初の probe が l) -> prev_end 維持
        assert new_end == prev_end
        # new_start: blackout end t=36 (no evidence before) -> priority 1 採用
        assert new_start == probes[36].t

    def test_frozen_present_not_counted_as_evidence(self):
        # (c) frozen-present (replay/result) は evidence にならない
        # "f"*30 + "l"*20: gap 先頭が frozen -> leading evidence run なし
        probes = _gap_probes("f" * 30 + "l" * 20)
        prev_end, next_start = 0.0, 50.0
        new_end, new_start = snap_segment_edges(prev_end, next_start, probes)
        # frozen は evidence でない -> leading run なし -> new_end = prev_end
        assert new_end == prev_end
        assert new_start == next_start

    def test_flicker_bridged_by_tolerant_runs(self):
        # (d) flicker (<=SNAP_FLICKER_TOL probe の False gap) を跨いで run 結合
        # leading: "M"*5 (idx0-4) + "l"*tol (gap=tol<=tol -> merged) + "M"*5 (idx15-19)
        # -> 1 run (0, 19), end=idx19
        tol = SNAP_FLICKER_TOL
        probes = _gap_probes("M" * 5 + "l" * tol + "M" * 5 + "l" * 30 + "M" * 3)
        prev_end, next_start = 0.0, float(len(probes))
        new_end, _new_start = snap_segment_edges(prev_end, next_start, probes)
        # leading merged run end = idx (5 + tol + 5 - 1) = (5+10+5-1) = 19
        expected_leading_end = probes[5 + tol + 5 - 1].t
        assert new_end == expected_leading_end

    def test_all_absent_keeps_coarse_edges(self):
        # (e) 全 absent -> 粗い edge 維持
        probes = _gap_probes("l" * 20)
        assert snap_segment_edges(5.0, 25.0, probes) == (5.0, 25.0)
        assert snap_segment_edges(5.0, 25.0, []) == (5.0, 25.0)

    def test_crossed_edges_fall_back_to_coarse(self):
        # (f) snap 結果が交差 (new_end >= new_start) したら粗い edge へ縮退
        # 単一 present probe のみ: leading + trailing が同じ probe を指し交差
        probes = _gap_probes("M")
        new_end, new_start = snap_segment_edges(0.0, 1.0, probes)
        assert (new_end, new_start) == (0.0, 1.0)

    def test_presence_edge_snap_without_blackout(self):
        # blackout なし: leading evidence run 末尾 + trailing evidence run 先頭
        # "M"*8 + "l"*30 + "M"*6: leading run end=idx7, trailing run start=idx38
        probes = _gap_probes("M" * 8 + "l" * 30 + "M" * 6)
        new_end, new_start = snap_segment_edges(0.0, 44.0, probes)
        assert new_end == probes[7].t
        assert new_start == probes[38].t


class TestRefineSegments:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e) -> MatchBoundary:
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_fn_gap_merges_segments(self):
        # probe_gap が返す probes は絶対時刻 (prev_end=400 起点) で生成する。
        # central slice [400, 500] に probe が入るよう t0=355 から生成して shift する。
        segs = [self._seg(0, 400), self._seg(500, 900)]
        # gap: [355, 545) を 1s stride で probe -> 190 probes (t=355..544)
        # central [400, 500]: t=400..500 の 101 probe
        t0_ext = 355.0
        raw = _gap_probes(("M" + "lll") * 50)  # 200 probes, 25% present
        shifted = [
            GapProbe(
                t=t0_ext + i, present=p.present, band_mad=p.band_mad, band_b=p.band_b
            )
            for i, p in enumerate(raw[:190])
        ]
        with (
            patch(
                "allaganeye.video.vtuber_timeline.probe_gap",
                return_value=shifted,
            ),
            # _snap_outer_edges を identity mock: 端 snap の追加 probe_gap 呼び出しを
            # 隔離し、merge 裁定の contract のみを gate する
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert out == [self._seg(0, 900)]

    def test_true_boundary_snaps_edges(self):
        # P3 6周目 (Bug B 局所窓変更後): セマンティクス更新。
        # spec: "M" * 5 + "bb" + "l" * 20 + "M" * 3 (絶対時刻 t0=400)
        # idx 0-4 (t=400-404): M - leading evidence
        # idx 5-6 (t=405-406): blackout (bb)
        # idx 7-26 (t=407-426): absent (l)
        # idx 27-29 (t=427-429): M - trailing evidence
        #
        # snap_segment_edges(prev_end=400, next_start=500): mid=450
        # _snap_end (end side, evidence-only):
        #   leading run (idx 0-4), end t=404 < mid=450 -> new_end=404.0
        # _snap_start (start side, Bug B 局所窓):
        #   blackout (t=405-406):
        #     before 5s 窓 [400, 405): t=404 (M) -> has_evidence_before=True
        #     after 10s 窓 [406, 416]: t=407..416 (absent) -> has_evidence_after=False
        #     -> is_intra_match=False -> priority 1 採用
        #   -> new_start = t=406.0 (blackout end)
        t0 = 400
        gap = _gap_probes("M" * 5 + "bb" + "l" * 20 + "M" * 3, stride=1.0)
        gap = [
            GapProbe(
                t=p.t + t0, present=p.present, band_mad=p.band_mad, band_b=p.band_b
            )
            for p in gap
        ]
        with (
            patch("allaganeye.video.vtuber_timeline.probe_gap", return_value=gap) as pg,
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
        ):
            out = refine_segments(
                Path("d.mp4"), self.ANCHOR, [self._seg(0, 400), self._seg(500, 900)]
            )
        assert len(out) == 2
        # new_end: evidence run 末尾 t=404 < mid=450 -> 採用
        assert out[0]["end"] == 404.0
        # new_start (Bug B 更新): blackout (t=405-406) は after 10s 窓に evidence なし
        # -> guard 不発 -> priority 1 採用 -> t=406.0
        assert out[1]["start"] == 406.0
        # Fix 1: 裁定 probe (400,500) + snap probe (EDGE_EXT_END_S 拡張) = 2 回
        assert pg.call_count == 2

    def test_long_gap_probes_only_edge_windows(self):
        # gap > MERGE_GAP_MAX: 両端 60s 窓のみ probe (gap で 2 回) + 端 snap で 2 回 = 計 4 回
        segs = [self._seg(0, 400), self._seg(900, 1300)]
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            return_value=_gap_probes("l" * 60),
        ) as pg:
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert len(out) == 2
        # gap snap 2 回 + 端 snap (first start + last end) 2 回 = 4 回
        assert pg.call_count == 4

    def test_gap_probe_exception_keeps_v2_result(self):
        # per-gap 例外隔離: probe 失敗 gap は snap/merge なしで V2 のまま
        segs = [self._seg(0, 400), self._seg(500, 900)]
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            side_effect=RuntimeError("decode"),
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert out == segs

    def test_stats_counters(self):
        # probe は絶対時刻 (t0_ext=355 起点) で生成して central slice [400,500] に入れる
        segs = [self._seg(0, 400), self._seg(500, 900)]
        stats: dict = {}
        t0_ext = 355.0
        raw = _gap_probes(("M" + "lll") * 50)
        shifted = [
            GapProbe(
                t=t0_ext + i, present=p.present, band_mad=p.band_mad, band_b=p.band_b
            )
            for i, p in enumerate(raw[:190])
        ]
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            return_value=shifted,
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs, stats=stats)  # type: ignore[arg-type]
        assert stats["vtuber_gaps_tested"] == 1
        assert stats["vtuber_gaps_merged"] == 1

    def test_short_gap_probe_range(self):
        # Fix 1 (#895 P3 3周目): 短 gap に対して 2 回 probe_gap を呼ぶこと。
        # [0] = 裁定用 (拡張なし: prev_end=400, next_start=500)
        # [1] = snap 用 (end 側 EDGE_EXT_END_S 拡張: 400-120, 500+EDGE_EXT_S)
        # 端 snap 2 回を合わせ合計 4 回 (boundary -> peek probe なし)
        segs = [self._seg(0, 400), self._seg(500, 900)]
        captured_calls: list[dict] = []

        def _spy_probe_gap(vp, anchor, t0, t1, **kw):
            captured_calls.append({"t0": t0, "t1": t1})
            return _gap_probes("l" * max(1, int(t1 - t0)))  # boundary

        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            side_effect=_spy_probe_gap,
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # 合計 4 回: [0]=裁定, [1]=snap, [2]=first start snap, [3]=last end snap
        assert len(captured_calls) == 4
        adj_call = captured_calls[0]
        snap_call = captured_calls[1]
        # 裁定: 拡張なし
        assert adj_call["t0"] == pytest.approx(400.0)
        assert adj_call["t1"] == pytest.approx(500.0)
        # snap: end 側 EDGE_EXT_END_S=120s 拡張、start 側 EDGE_EXT_S=45s 拡張
        assert snap_call["t0"] == pytest.approx(max(0.0, 400.0 - EDGE_EXT_END_S))
        assert snap_call["t1"] == pytest.approx(500.0 + EDGE_EXT_S)

    def test_adjudicate_gap_receives_all_adjudication_probes(self):
        # Fix 1 (#895 P3 3周目): adjudicate_gap には probe_gap(prev_end, next_start) の
        # 全 probes が渡ること (拡張なし probe の全量 = P2 実装と bit-同一の入力)。
        # 裁定 probe は (prev_end=400, next_start=500) で呼ばれ t=[400, 500) の probes を返す。
        segs = [self._seg(0, 400), self._seg(500, 900)]
        # probe_gap を (400, 500) で呼ぶ -> 100 probes (t=400..499)
        adj_probes = [
            GapProbe(t=400.0 + i, present=False, band_mad=5.0, band_b=100.0)
            for i in range(100)
        ]

        adjudicate_calls: list[list[float]] = []

        real_adjudicate = __import__(
            "allaganeye.video.vtuber_timeline", fromlist=["adjudicate_gap"]
        ).adjudicate_gap

        def _spy_adjudicate(probes, **kw):
            adjudicate_calls.append([p.t for p in probes])
            return real_adjudicate(probes, **kw)

        def _spy_probe(vp, anchor, t0, t1, **kw):
            # 裁定呼び出し (t0=400, t1=500): adj_probes を返す
            # snap 呼び出し (拡張あり) / 端 snap: 空リストで境界変化なし
            if abs(t0 - 400.0) < 0.1 and abs(t1 - 500.0) < 0.1:
                return adj_probes
            return _gap_probes("l" * max(1, int(t1 - t0)))

        with (
            patch(
                "allaganeye.video.vtuber_timeline.probe_gap",
                side_effect=_spy_probe,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.adjudicate_gap",
                side_effect=_spy_adjudicate,
            ),
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        assert len(adjudicate_calls) == 1
        adj_ts = adjudicate_calls[0]
        # 裁定 probe は (400, 500): t in [400, 500) の全 probes
        assert len(adj_ts) == 100
        assert min(adj_ts) == pytest.approx(400.0)
        assert max(adj_ts) == pytest.approx(499.0)

    def test_long_gap_edge_windows_extended_by_edge_ext_s(self):
        # gap > MERGE_GAP_MAX の長 gap: head は [prev_end - EDGE_EXT_END_S, prev_end + 60]
        # tail は [next_start - 60, next_start + EDGE_EXT_S]
        # 2 パス化後: 第 1 パス (長 gap は probe なし) + 第 2 パス gap snap (2 回)
        #   + 端 snap (first start + last end) (2 回) = 計 4 回
        segs = [self._seg(0, 400), self._seg(900, 1300)]
        captured_calls: list[dict] = []

        def _spy_probe_gap(vp, anchor, t0, t1, **kw):
            captured_calls.append({"t0": t0, "t1": t1})
            return _gap_probes("l" * 60)

        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            side_effect=_spy_probe_gap,
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # 最初の 2 呼び出しが長 gap の head/tail snap
        assert len(captured_calls) == 4
        head_call = captured_calls[0]
        tail_call = captured_calls[1]
        # head: [prev_end - EDGE_EXT_END_S, prev_end + 60] (end 側 120s 拡張)
        assert head_call["t0"] == pytest.approx(max(0.0, 400.0 - EDGE_EXT_END_S))
        assert head_call["t1"] == pytest.approx(400.0 + 60.0)
        # tail: [next_start - 60, next_start + EDGE_EXT_S]
        assert tail_call["t0"] == pytest.approx(900.0 - 60.0)
        assert tail_call["t1"] == pytest.approx(900.0 + EDGE_EXT_S)


class TestRefineFix1TwoPassIsolation:
    """Fix 1 (#895 P3 2周目): 裁定と snap の 2 パス分離。
    snap で prev["end"] が前に動いても次 gap の裁定入力 (粗 edge 基準) が変わらないこと。
    """

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e) -> MatchBoundary:
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_snap_does_not_contaminate_next_gap_adjudication(self):
        """第 1 gap の snap で end が動いても、第 2 gap の裁定入力が
        粗 edge (original prev_end) 基準のままであること。

        Fix 1 (#895 P3 3周目) 後の呼び出し順:
        - seg0: [0, 400], seg1: [460, 900], seg2: [960, 1400]
        - gap1 裁定: probe_gap(400, 460) -> all absent -> boundary
        - gap1 snap: probe_gap(355, 505) -> snap 適用 (new_end 変化)
        - gap2 裁定: probe_gap(460, 960) -> 裁定 (粗 edge 基準で呼ばれること)
        - gap2 snap: probe_gap(415, 1005)

        adjudicate_gap への入力が [460, 960] 範囲のみであること (= 拡張なし) を
        spy で確認する (snap-contamination がない = Fix 1 の invariant)。
        """
        # gap1 裁定: t in [400, 460) -> 全 absent -> boundary
        # gap1 snap: t in [355, 505) -> 先頭 5 probe M (t=355-359) -> snap で new_end 変化

        # gap2 裁定: probe_gap(460, 960) で呼ばれる -> t in [460, 960) の probes
        # present rate 25% -> merge になる (gap2 boundary check の逆)
        # ここでは boundary にするために all-absent を返す
        # (目的: adjudicate_gap への入力 t 範囲のみを gate する)

        adjudicate_calls: list[list[float]] = []
        real_adjudicate = __import__(
            "allaganeye.video.vtuber_timeline", fromlist=["adjudicate_gap"]
        ).adjudicate_gap

        def _spy_adjudicate(probes, **kw):
            adjudicate_calls.append([p.t for p in probes])
            return real_adjudicate(probes, **kw)

        def _spy_probe_gap(vp, anchor, t0, t1, **kw):
            # 呼び出し範囲に応じた probes を生成 (t0 起点、1s stride)
            n = max(0, int(t1 - t0))
            # gap1 snap 窓 (355, 505): 先頭 5 probe を M -> snap で new_end が前に動く
            if abs(t0 - 355.0) < 0.1 and abs(t1 - 505.0) < 0.1:
                raw = _gap_probes("M" * 5 + "l" * (n - 5 if n > 5 else 0))
            else:
                raw = _gap_probes("l" * n)
            return [
                GapProbe(
                    t=t0 + i, present=p.present, band_mad=p.band_mad, band_b=p.band_b
                )
                for i, p in enumerate(raw)
            ]

        segs = [self._seg(0, 400), self._seg(460, 900), self._seg(960, 1400)]
        with (
            patch(
                "allaganeye.video.vtuber_timeline.probe_gap",
                side_effect=_spy_probe_gap,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.adjudicate_gap",
                side_effect=_spy_adjudicate,
            ),
            # 端 snap は隔離: Fix 1 の contract のみを gate する
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # adjudicate_gap は 2 gap 分呼ばれる
        assert len(adjudicate_calls) == 2
        # gap2 の adjudicate 入力は粗 edge 基準 [460, 960) のみ
        gap2_ts = adjudicate_calls[1]
        assert all(460.0 <= t < 960.0 for t in gap2_ts), (
            f"gap2 adjudicate received probes outside [460, 960): {gap2_ts[:5]}..."
        )
        # snap 後 edge より前の probe が含まれないこと (Fix 1 の invariant)
        assert not any(t < 460.0 for t in gap2_ts), (
            f"snap-contaminated probes found in gap2 adjudicate: {[t for t in gap2_ts if t < 460]}"
        )


class TestRefineFix2MidpointConstraint:
    """Fix 2 (#895 P3 2周目): snap_segment_edges の中点制約。
    trailing run が gap 前半にある -> new_start 不採用 (粗 edge 維持)。
    leading run が gap 後半にある -> new_end 不採用。
    """

    def test_trailing_run_in_gap_first_half_keeps_coarse_start(self):
        """trailing evidence run の先頭が mid より前 -> new_start = next_start 維持。
        gyawa M6 (-144s) / meteor M2 (-239s) 実測例の大外れ根絶。
        """
        # prev_end=0, next_start=200 -> mid=100
        # trailing evidence run 先頭: t=60 < mid=100 -> 不採用
        # "l"*60 + "M"*5 + "l"*135: trailing run 先頭 t=60
        probes = _gap_probes("l" * 60 + "M" * 5 + "l" * 135)
        _new_end, new_start = snap_segment_edges(0.0, 200.0, probes)
        # trailing run start t=60 < mid=100 -> new_start = next_start 維持
        assert new_start == 200.0

    def test_leading_run_in_gap_second_half_keeps_coarse_end(self):
        """leading evidence run の末尾が mid より後 -> new_end = prev_end 維持。"""
        # prev_end=0, next_start=200 -> mid=100
        # leading evidence run 末尾: t=150 > mid=100 -> 不採用
        # "l"*5 + "M"*150 + "l"*45: leading run 末尾 t=154 > mid=100
        probes = _gap_probes("l" * 5 + "M" * 150 + "l" * 45)
        new_end, _new_start = snap_segment_edges(0.0, 200.0, probes)
        # leading run end t=154 > mid=100 -> new_end = prev_end 維持
        assert new_end == 0.0

    def test_evidence_run_spanning_mid_accepts_respective_sides(self):
        """evidence run が mid を跨ぐとき: end 候補 < mid, start 候補 > mid -> 両採用。"""
        # prev_end=0, next_start=100 -> mid=50
        # "M"*40 + "l"*20 + "M"*40: leading run end t=39 < mid=50, trailing run start t=60 > mid=50
        probes = _gap_probes("M" * 40 + "l" * 20 + "M" * 40)
        new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        assert new_end == probes[39].t  # t=39 < mid=50 -> 採用
        assert new_start == probes[60].t  # t=60 > mid=50 -> 採用


class TestRefineFix3OuterEdgeSnap:
    """Fix 3 (#895 P3 2周目): 端 segment の snap (最初の start / 最後の end)。"""

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e) -> MatchBoundary:
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_first_start_probed(self):
        """refine_segments が最初の segment start 端 + 最後の end 端を probe すること。
        first start: [max(0, first_start - EDGE_EXT_S), first_start + 60]
        last end: [last_end - EDGE_EXT_END_S, last_end + EDGE_EXT_S] (120s 拡張)
        """
        segs = [self._seg(200, 600)]  # single segment (< 2 なので merge 裁定なし)
        captured_calls: list[dict] = []

        def _spy(vp, anchor, t0, t1, **kw):
            captured_calls.append({"t0": t0, "t1": t1})
            return _gap_probes("l" * 60)

        with patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        ts = [(c["t0"], c["t1"]) for c in captured_calls]
        first_start_call = (
            pytest.approx(max(0.0, 200.0 - EDGE_EXT_S)),
            pytest.approx(200.0 + 60.0),
        )
        # last end: [600 - EDGE_EXT_END_S, 600 + EDGE_EXT_S] = [480, 645]
        last_end_call = (
            pytest.approx(600.0 - EDGE_EXT_END_S),
            pytest.approx(600.0 + EDGE_EXT_S),
        )
        assert any(
            t0 == first_start_call[0] and t1 == first_start_call[1] for t0, t1 in ts
        ), f"first start probe not found: {ts}"
        assert any(
            t0 == last_end_call[0] and t1 == last_end_call[1] for t0, t1 in ts
        ), f"last end probe not found: {ts}"

    def test_first_start_snap_applied(self):
        """端 snap の start 側が適用されること。
        trailing evidence run が mid より後 -> first["start"] が更新される。
        """
        # first_start=200: t0=155, t1=260, mid=(155+260)/2=207.5
        # probes: t=155..259, trailing evidence run 先頭 t=220 > mid=207.5 -> 採用
        segs = [self._seg(200, 600)]
        call_idx = [0]

        def _spy(vp, anchor, t0, t1, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                # first start probe: all absent except trailing (t=220 相当 = idx 65 = 220-155)
                n = max(0, int(t1 - t0))
                raw = _gap_probes("l" * 65 + "M" * (n - 65) if n > 65 else "l" * n)
                return [
                    GapProbe(
                        t=t0 + i,
                        present=p.present,
                        band_mad=p.band_mad,
                        band_b=p.band_b,
                    )
                    for i, p in enumerate(raw)
                ]
            else:
                # last end probe: all absent -> no snap
                return _gap_probes("l" * 60)

        with patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # trailing run 先頭 t=155+65=220 > mid=207.5 -> snap 採用
        assert out[0]["start"] == pytest.approx(220.0)

    def test_last_end_snap_applied(self):
        """端 snap の end 側が適用されること。
        leading evidence run が mid より前 -> last["end"] が更新される。
        P3 4周目: end 窓 = [last_end - EDGE_EXT_END_S, last_end + EDGE_EXT_S]
                         = [600-120, 600+45] = [480, 645], mid=(480+645)/2=562.5
        """
        segs = [self._seg(200, 600)]
        call_idx = [0]

        def _spy(vp, anchor, t0, t1, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                # first start probe: all absent -> no snap
                return _gap_probes("l" * 60)
            else:
                # last end probe: window [480, 645), n=165
                # leading evidence (idx 0..40, t=480..520) end t=520 < mid=562.5 -> snap 採用
                n = max(0, int(t1 - t0))
                raw = _gap_probes("M" * min(41, n) + "l" * max(0, n - 41))
                return [
                    GapProbe(
                        t=t0 + i,
                        present=p.present,
                        band_mad=p.band_mad,
                        band_b=p.band_b,
                    )
                    for i, p in enumerate(raw)
                ]

        with patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # t0=480, leading run end idx=40, t=480+40=520 < mid=562.5 -> snap 採用
        assert out[0]["end"] == pytest.approx(520.0)

    def test_outer_snap_exception_keeps_coarse(self):
        """端 snap が例外を発生させても粗い edge を維持すること (per-gap 例外隔離と同等)。"""
        segs = [self._seg(200, 600)]

        def _raise(*a, **kw):
            raise RuntimeError("probe failure")

        with patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_raise):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # 例外でも粗い edge 維持
        assert out[0]["start"] == 200.0
        assert out[0]["end"] == 600.0


class TestProbeGap:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def test_probe_includes_band_brightness(self):
        def fake_probe(video_path, t):
            return _synthetic_frame(100)

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
            probes = probe_gap(Path("d.mp4"), self.ANCHOR, 10.0, 13.0)
        assert len(probes) == 3
        assert all(p.band_b is not None and abs(p.band_b - 100.0) < 0.5 for p in probes)
        assert all(p.present for p in probes)


class TestDetectMatchesTimelineV3V4:
    """Task 4: V3/V4 wiring, stats population, and low-confidence flag."""

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _run(self, scan_spec: str, stats=None):
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes(scan_spec),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: segs,
            ) as rs,
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=lambda vp, segs, a, w, st, d, **kw: segs,
            ) as vs,
        ):
            result = detect_matches_timeline(
                Path("d.mp4"),
                duration_hint=520.0,
                min_match_duration=300.0,
                stats=stats,
            )
        return result, rs, vs

    def test_v3_and_v4_are_wired(self):
        main_stats: dict = {}
        result, rs, vs = self._run("l" * 6 + "M" * 40 + "l" * 6, stats=main_stats)
        assert result is not None
        rs.assert_called_once()
        vs.assert_called_once()
        # stats pass-through wiring の positive gate (Round 4 #1):
        # refine_segments に main stats がそのまま (identity で) 渡ること
        assert rs.call_args.kwargs.get("stats") is main_stats

    def test_low_confidence_flag_for_long_segment(self, caplog):
        import logging

        stats: dict = {}
        # 200 probes = 2000s of continuous match -> exceeds 30min -> low-confidence warning
        with caplog.at_level(
            logging.WARNING, logger="allaganeye.video.vtuber_timeline"
        ):
            result, _, _ = self._run("M" * 200, stats=stats)
        assert result is not None
        assert stats.get("vtuber_low_confidence_segments") == 1
        assert "exceeds" in caplog.text or "low-confidence" in caplog.text

    def test_stats_populated(self):
        stats: dict = {}
        _, _, _ = self._run("l" * 6 + "M" * 40 + "l" * 6, stats=stats)
        assert stats["vtuber_timeline_probes"] == 52
        assert abs(stats["vtuber_anchor_confidence"] - 0.8) < 1e-9

    def test_v4_empty_after_validation_falls_back(self):
        # V4 that drops all segments should return None (empty authoritative forbidden)
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes("l" * 6 + "M" * 40 + "l" * 6),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=lambda vp, segs, a, w, st, d, **kw: [],
            ),
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
                )
                is None
            )


class TestV4StatsIsolation:
    """Fix 2: local_stats isolation + translate + pop-on-empty."""

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def test_v4_drop_translate_to_main_stats(self):
        """vtuber_v4_dropped は local_stats の masked_segments_dropped から
        translate される。main stats に masked_segments_dropped は残らない。"""

        # _validate_match_segments の side_effect: 渡された stats dict (local_stats) に
        # masked_segments_dropped を set し、入力 segs の subset を返す。
        def _fake_validate(vp, segs, a, w, local_st, d, **kw):
            local_st["masked_segments_dropped"] = 1
            return segs[:1] if len(segs) > 1 else segs

        main_stats: dict = {}
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes("l" * 6 + "M" * 40 + "l" * 6),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: [
                    *segs,
                    {"start": 600.0, "end": 1000.0, "type": "fl_match"},
                ],
            ),
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=_fake_validate,
            ),
        ):
            detect_matches_timeline(
                Path("d.mp4"),
                duration_hint=1100.0,
                min_match_duration=300.0,
                stats=main_stats,  # type: ignore[arg-type]
            )
        # translate: main_stats にキーが存在し値が 1
        assert main_stats.get("vtuber_v4_dropped") == 1
        # isolation: masked_segments_dropped は main_stats に漏れない
        assert "masked_segments_dropped" not in main_stats

    @staticmethod
    def _refine_writing_stats(vp, a, segs, **kw):
        st = kw.get("stats")
        if st is not None:
            st["vtuber_gaps_tested"] = 1
            st["vtuber_gaps_merged"] = 1
        return segs

    def test_v4_all_drop_pops_vtuber_keys_from_main_stats(self):
        """V4 全滅 None 縮退時に V2 以降で set した vtuber_* キーが main stats
        から除去されること。"""
        main_stats: dict = {}
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes("l" * 6 + "M" * 40 + "l" * 6),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                # V3 key も実際に書き込む mock: pop list の完全性 (4 key 全て) を
                # main_stats == {} assert で gate する (Round 3 finding #1)
                side_effect=self._refine_writing_stats,
            ),
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=lambda vp, segs, a, w, st, d, **kw: [],
            ),
        ):
            result = detect_matches_timeline(
                Path("d.mp4"),
                duration_hint=520.0,
                min_match_duration=300.0,
                stats=main_stats,  # type: ignore[arg-type]
            )
        assert result is None
        # 縮退 run の main stats に vtuber_* キーが一切残らないこと (Round 2 #1:
        # V4 統計 (v4_dropped / low_confidence) の書込は空チェック通過後のみ)
        assert not [k for k in main_stats if str(k).startswith("vtuber_")], main_stats
        assert main_stats == {}

    def test_v4_real_path_all_absent_returns_none(self):
        """real _validate_match_segments (on_all_drop='empty') 経由で全 probe
        ABSENT になると detect_matches_timeline が None を返す。
        resolve_vtuber_anchor / scan_timeline / refine_segments のみ mock し
        _validate_match_segments は本物を通す。"""
        # _probe_frame_rgb_hires: 有効 bytes (UNKNOWN にしない)
        # localize_from_rgb_bytes_at_anchor: None (ABSENT)
        raw_bytes = bytes(1920 * 1080 * 3)
        main_stats: dict = {}
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes("l" * 6 + "M" * 40 + "l" * 6),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
            patch(
                "allaganeye.video.detector._probe_frame_rgb_hires",
                return_value=raw_bytes,
            ),
            patch(
                "allaganeye.video.capture_region.localize_from_rgb_bytes_at_anchor",
                return_value=None,
            ),
        ):
            result = detect_matches_timeline(
                Path("d.mp4"),
                duration_hint=520.0,
                min_match_duration=300.0,
                stats=main_stats,  # type: ignore[arg-type]
            )
        # 全 probe ABSENT -> on_all_drop="empty" -> [] -> None 縮退
        assert result is None
        # pop 済み: vtuber_timeline_probes は main stats にない
        assert "vtuber_timeline_probes" not in main_stats
        # masked_segments_dropped は漏れない
        assert "masked_segments_dropped" not in main_stats


class TestSnapSegmentEdgesContract:
    """P3 4周目: snap の物理規則 pin (end=evidence-only / start=blackout priority)。"""

    def test_blackout_before_evidence_uses_evidence_for_end_and_blackout_for_start(
        self,
    ):
        """P3 4周目: "M"*3 + "bb" + "l"*30, prev=0, next=35
        - end: evidence run end t=2 < mid=17.5 -> new_end=2.0 (evidence-only)
        - start: blackout (3,4), evidence before (M*3) but no evidence after -> not intra-match
          -> new_start = probes[4].t = 4.0
        - (2.0, 4.0): valid (2 < 4)
        """
        probes = _gap_probes("M" * 3 + "bb" + "l" * 30)
        prev_end, next_start = 0.0, 35.0
        new_end, new_start = snap_segment_edges(prev_end, next_start, probes)
        # end: evidence run 末尾 t=2 (blackout は使わない)
        assert new_end == probes[2].t  # t=2.0
        # start: blackout end t=4 (evidence before only, not intra-match)
        assert new_start == probes[4].t  # t=4.0

    def test_blackout_outside_lo_hi_range_not_adopted_for_start(self):
        """P3 4周目: probes の t が lo (prev_end) より小さい場合、
        blackout run end は (lo, hi] 条件外なので priority 1 に採用されない。
        "l"*5 + "bb" + "l"*5, prev_end=10, next_start=20:
        probes の t は 0-indexed (t=5,6) で lo=10 より小さい。
        (lo=10) < t_end=6 は偽 -> priority 1 不発 -> new_start=20.0 (coarse)
        """
        probes = _gap_probes("l" * 5 + "bb" + "l" * 5)
        # blackout t=5,6 but lo=10 -> t_end=6 not in (10, 20] -> no start snap
        new_end, new_start = snap_segment_edges(10.0, 20.0, probes)
        assert new_end == 10.0  # no evidence -> prev_end
        assert new_start == 20.0  # blackout t outside (lo, hi] -> coarse


class TestAdjudicateGapUnknownDenominator:
    """Fix 4(c): unknown probe が present rate 分母に入らない pin."""

    def test_unknown_excluded_from_rate_denominator(self):
        """u (unknown) probe が rate 分母から除外されること。
        u を含む構成で valid のみで rate を計算したとき merge になる例。
        MERGE_RATE=0.15 後: rate=15% (boundary 境界値) で確認する。"""
        # valid: M*15 + l*85 = 15% present -> merge (>= 0.15)
        probes_no_u = _gap_probes("M" * 15 + "l" * 85)
        # u を追加: valid は 100 のまま、rate = 15/100 = 15% -> merge
        # u が分母に入ると rate = 15/150 = 10% < 15% -> boundary (誤)
        probes_with_u = _gap_probes("M" * 15 + "l" * 85 + "u" * 50)
        assert adjudicate_gap(probes_no_u) == "merge"
        # u が分母から除外されると rate = 15 / 100 = 15% -> merge (正)
        assert adjudicate_gap(probes_with_u) == "merge"


class TestFix1AdjudicationProbeNoExtension:
    """Fix 1 (#895 P3 3周目): 裁定 probe は拡張なし (prev_end, next_start) で取得。
    snap probe は別途拡張あり (EDGE_EXT_S) で取得する。
    """

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e) -> MatchBoundary:
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_first_pass_probe_has_no_extension(self):
        """第 1 パス (裁定) probe が (prev_end, next_start) で呼ばれること。
        拡張なし = EDGE_EXT_S は含まれない。
        """
        segs = [self._seg(0, 400), self._seg(500, 900)]
        captured_calls: list[dict] = []

        def _spy(vp, anchor, t0, t1, **kw):
            captured_calls.append({"t0": t0, "t1": t1})
            return _gap_probes("l" * max(1, int(t1 - t0)))

        with (
            patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy),
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # 最初の呼び出しが裁定用 probe: 拡張なし (prev_end=400, next_start=500)
        assert len(captured_calls) >= 1
        first = captured_calls[0]
        assert first["t0"] == pytest.approx(400.0), (
            f"adjudication probe t0 should be prev_end=400.0, got {first['t0']}"
        )
        assert first["t1"] == pytest.approx(500.0), (
            f"adjudication probe t1 should be next_start=500.0, got {first['t1']}"
        )

    def test_adjudicate_receives_all_probes_not_slice(self):
        """adjudicate_gap には probe_gap の全 probes が渡ること (slice なし)。
        Fix 1 後: (prev_end, next_start) で取得した全 probes を渡す。
        """
        segs = [self._seg(0, 400), self._seg(500, 900)]
        # probe_gap を (400, 500) で呼ぶ -> 100 probes (t=400..499)
        adjudicate_calls: list[list[float]] = []
        real_adjudicate = __import__(
            "allaganeye.video.vtuber_timeline", fromlist=["adjudicate_gap"]
        ).adjudicate_gap

        def _spy_adjudicate(probes, **kw):
            adjudicate_calls.append([p.t for p in probes])
            return real_adjudicate(probes, **kw)

        adj_probes = [
            GapProbe(t=400.0 + i, present=False, band_mad=5.0, band_b=100.0)
            for i in range(100)
        ]

        def _spy_probe(vp, anchor, t0, t1, **kw):
            return [p for p in adj_probes if t0 <= p.t < t1]

        with (
            patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy_probe),
            patch(
                "allaganeye.video.vtuber_timeline.adjudicate_gap",
                side_effect=_spy_adjudicate,
            ),
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        assert len(adjudicate_calls) == 1
        ts = adjudicate_calls[0]
        # 裁定 probe は (400, 500): t in [400, 500) の全 probes
        assert len(ts) == 100
        assert min(ts) == pytest.approx(400.0)
        assert max(ts) == pytest.approx(499.0)

    def test_second_pass_snap_probe_uses_extension(self):
        """第 2 パス (snap) probe は拡張あり (end 側 EDGE_EXT_END_S) で取得すること。"""
        segs = [self._seg(0, 400), self._seg(500, 900)]
        captured_calls: list[dict] = []

        def _spy(vp, anchor, t0, t1, **kw):
            captured_calls.append({"t0": t0, "t1": t1})
            return _gap_probes("l" * max(1, int(t1 - t0)))

        with (
            patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy),
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs)

        # 2 回呼ばれる: [0]=裁定 (no ext), [1]=snap (end 側 EDGE_EXT_END_S 拡張)
        assert len(captured_calls) == 2
        snap_call = captured_calls[1]
        # end 側: EDGE_EXT_END_S=120s 拡張 (旧 EDGE_EXT_S=45s から変更)
        assert snap_call["t0"] == pytest.approx(max(0.0, 400.0 - EDGE_EXT_END_S))
        assert snap_call["t1"] == pytest.approx(500.0 + EDGE_EXT_S)


class TestFix2BlackoutMidpointOnly:
    """P3 4周目: _snap_start は blackout run end を無条件採用 (中点制約なし)。
    end 側は evidence-only (_snap_end)。in-match guard (前後 evidence) で瞬断除外。
    """

    def test_blackout_end_snap_no_longer_applies(self):
        """(a) P3 4周目: end 側は evidence-only。blackout が中点より前にあっても
        new_end は採用されない (end snap は証拠 run のみ)。
        """
        # prev_end=0, next_start=200
        # "l"*80 + "bb" + "l"*120: evidence なし -> new_end = prev_end = 0.0
        # blackout run end t=81 -> _snap_start が new_start=81.0 に採用
        probes = _gap_probes("l" * 80 + "bb" + "l" * 120)
        new_end, new_start = snap_segment_edges(0.0, 200.0, probes)
        # end: evidence なし -> prev_end 維持
        assert new_end == 0.0
        # start: blackout end t=81, no evidence before -> new_start=81.0
        assert new_start == probes[81].t  # t=81.0

    def test_blackout_start_snap_without_adjacent_evidence(self):
        """(b) blackout run end は中点制約なしで new_start に採用。
        P3 4周目: midpoint constraint 撤廃 (shikke M6 型対応)。
        """
        # prev_end=0, next_start=200
        # "l"*120 + "bb" + "l"*80: blackout end t=121, no evidence before/after
        probes = _gap_probes("l" * 120 + "bb" + "l" * 80)
        new_end, new_start = snap_segment_edges(0.0, 200.0, probes)
        assert new_end == 0.0  # leading evidence なし -> prev_end 維持
        assert new_start == probes[121].t  # t=121.0 (no midpoint constraint)

    def test_blackout_start_snap_before_mid_is_still_adopted(self):
        """(c) P3 4周目: mid より前の blackout run end でも new_start に無条件採用。
        shikke M6 型: mid=100、blackout end t=41 (mid より前) でも採用される。
        """
        # prev_end=0, next_start=200 -> mid=100
        # "l"*30 + "bb" + "l"*168: blackout end t=31 < mid=100
        # P3 4周目: 中点制約なし -> new_start=31.0
        probes = _gap_probes("l" * 30 + "bb" + "l" * 168)
        _new_end, new_start = snap_segment_edges(0.0, 200.0, probes)
        # 中点制約なし -> blackout end t=31 が採用される
        assert new_start == probes[31].t  # t=31.0

    def test_multiple_blackout_runs_start_uses_last_in_range(self):
        """(d) 複数 blackout run のうち start 側は最後の run end を採用。"""
        # prev_end=0, next_start=200
        # "l"*120 + "bb" + "l"*40 + "bb" + "l"*36:
        # blackout 1 end t=121, blackout 2 end t=163
        # -> 最後 (t=163) を採用
        probes = _gap_probes("l" * 120 + "bb" + "l" * 40 + "bb" + "l" * 36)
        _new_end, new_start = snap_segment_edges(0.0, 200.0, probes)
        assert new_start == probes[163].t  # 最後の blackout run end

    def test_intra_match_blackout_skipped_for_start(self):
        """(e) in-match guard: 前後に evidence がある blackout run は start 候補にならない。
        shinryu M5 型: 試合中の瞬断 blackout -> evidence fallback へ。
        """
        # prev_end=0, next_start=100
        # "M"*20 + "bb" + "M"*10 + "l"*68:
        # blackout (20,21): evidence before (M*20) AND after (M*10) -> intra-match -> skip
        # priority 3: trailing evidence (M*20 + bridge + M*10) = run (0,31), start t=0 < mid=50
        # -> trailing run start t=0 NOT > mid=50 -> not adopted -> new_start=100.0
        probes = _gap_probes("M" * 20 + "bb" + "M" * 10 + "l" * 68)
        new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        # start: intra-match guard fires, fallback evidence run start t=0 < mid -> not adopted
        assert new_start == 100.0  # coarse edge maintained
        # end: evidence run end t=31 < mid=50 -> adopted
        assert new_end == probes[31].t  # t=31.0


class TestV4DropTranslatePin:
    """Fix 4(a): vtuber_v4_dropped translate + isolation の直接 pin."""

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def test_translate_pin(self):
        """_validate_match_segments に渡す local_stats に masked_segments_dropped=1
        が set されたとき、main stats の vtuber_v4_dropped=1 かつ
        masked_segments_dropped が main stats にないことを assert。"""

        def _fake_validate(vp, segs, a, w, local_st, d, **kw):
            local_st["masked_segments_dropped"] = 1
            return segs[:1]

        main_stats: dict = {}
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes("l" * 6 + "M" * 40 + "l" * 6),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: [
                    *segs,
                    {"start": 600.0, "end": 1000.0, "type": "fl_match"},
                ],
            ),
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=_fake_validate,
            ),
        ):
            detect_matches_timeline(
                Path("d.mp4"),
                duration_hint=1100.0,
                min_match_duration=300.0,
                stats=main_stats,  # type: ignore[arg-type]
            )
        assert main_stats["vtuber_v4_dropped"] == 1
        assert "masked_segments_dropped" not in main_stats


# ---------------------------------------------------------------------------
# Task 4d: 物理規則 snap 再設計 + blackout-peek unmerge + MERGE_RATE 0.15
# ---------------------------------------------------------------------------


class TestSnapStartBlackoutUnconditional:
    """_snap_start (via snap_segment_edges): blackout run end in (lo, hi] -> 無条件採用。
    shikke M6 型: 粗 gap 中央近傍にある blackout run end が中点制約なしで採用される。
    """

    def test_blackout_run_end_at_mid_adopted_unconditionally(self):
        """blackout run end が gap の中点ちょうどにあるとき旧中点制約なら棄却されるが
        新規則では無条件採用される (start snap)。
        prev_end=0, next_start=100 -> mid=50
        probes: "l"*40 + "bb" + "l"*58: blackout idx 40-41, run end t=41
        t=41 は mid=50 より前。旧規則: new_start = run 末尾 t=41 < mid -> 棄却。
        新規則: (lo, hi] 内の最後の blackout run end -> new_start = t=41 (無条件)。
        """
        probes = _gap_probes("l" * 40 + "bb" + "l" * 58)
        _new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        # 新規則: blackout run end t=41 は (lo=0, hi=100] 内 -> new_start=41.0
        assert new_start == probes[41].t  # t=41.0

    def test_blackout_run_end_exactly_at_prev_end_not_adopted(self):
        """blackout run end が lo (prev_end) ちょうど = 境界外 -> 採用しない (lo exclusive)。
        probes: "b" + "l"*99: blackout idx 0 のみ, run end t=0.0
        t=0.0 は lo=0.0 と等しい -> (lo, hi] に含まれない -> new_start 維持。
        """
        probes = _gap_probes("b" + "l" * 99)
        _new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        # blackout run end t=0.0 == lo -> not in (0.0, 100.0] -> not adopted
        assert new_start == 100.0


class TestSnapEndEvidenceOnly:
    """_snap_end (via snap_segment_edges): end side uses evidence run ONLY (no blackout).
    shinryu M5 型: in-match blackout (2 probe) が gap 内にあっても evidence run 末尾が
    end として採用される (blackout に引っ張られない)。
    """

    def test_end_ignores_in_match_blackout_uses_evidence_run(self):
        """evidence run が in-match blackout を tol で跨いで継続するとき、
        end = run 末尾 (collapse 位置)。blackout probe が end snap を引き寄せない。
        prev_end=0, next_start=100, mid=50
        leading evidence: M*20 + "bb" (in-match blackout) + M*10: run tol=10 で結合し end=31
        leading run end t=31 < mid=50 -> 採用。
        """
        # M*20 + bb + M*10 (total 32): tol=10 >= 2 -> 1 run, end=idx31
        probes = _gap_probes("M" * 20 + "bb" + "M" * 10 + "l" * 68)
        new_end, _new_start = snap_segment_edges(0.0, 100.0, probes)
        # evidence run end = idx 31 (t=31.0) < mid=50 -> new_end=31.0
        # blackout が new_end を引き寄せない (end side は evidence only)
        assert new_end == probes[31].t  # t=31.0 (evidence run end, not blackout t=20)

    def test_end_midpoint_constraint_still_applies(self):
        """end snap の中点制約は維持: leading run end > mid -> 不採用。"""
        # prev_end=0, next_start=100, mid=50
        # "l"*5 + "M"*70 + "l"*25: leading run end=idx74, t=74 > mid=50 -> 不採用
        probes = _gap_probes("l" * 5 + "M" * 70 + "l" * 25)
        new_end, _new_start = snap_segment_edges(0.0, 100.0, probes)
        assert new_end == 0.0  # 中点制約で不採用 -> prev_end 維持


class TestSnapExtProbeWindow120s:
    """shinryu M3 型: collapse が粗 end より 80s 前。拡張窓 120s で end が collapse へ snap。"""

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e) -> MatchBoundary:
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_end_snap_captures_collapse_80s_before_coarse_end(self):
        """snap probe 窓が 120s に拡大されることで、coarse end より 80s 前の
        collapse (evidence run 末尾) が end として採用される。

        seg=[0, 400]: coarse end=400。collapse は t=320 (= 400-80)。
        旧窓 (60s): [340, 460] -> collapse t=320 は窓外 -> 採用不能。
        新窓 (120s): [280, 460] -> collapse t=320 は窓内 -> 採用可能。
        """
        from allaganeye.video.vtuber_timeline import EDGE_EXT_END_S

        captured: list[dict] = []

        def _spy(vp, anchor, t0, t1, **kw):
            captured.append({"t0": t0, "t1": t1})
            # last end probe: generate probes for [280, 460)
            n = max(0, int(t1 - t0))
            # leading evidence: t=280..320 (40 probe, idx 0-40), then absent
            raw = _gap_probes("M" * 41 + "l" * (n - 41 if n > 41 else 0))
            return [
                GapProbe(
                    t=t0 + i, present=p.present, band_mad=p.band_mad, band_b=p.band_b
                )
                for i, p in enumerate(raw)
            ]

        with patch("allaganeye.video.vtuber_timeline.probe_gap", side_effect=_spy):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, [self._seg(0, 400)])

        # 最後の end probe 窓: [400 - EDGE_EXT_END_S, 400 + EDGE_EXT_S]
        last_end_calls = [
            c for c in captured if abs(c["t1"] - (400.0 + EDGE_EXT_S)) < 0.1
        ]
        assert last_end_calls, f"end snap probe not found: {captured}"
        call = last_end_calls[0]
        # 窓左端は EDGE_EXT_END_S (120s) 分巻き戻る
        assert call["t0"] == pytest.approx(400.0 - EDGE_EXT_END_S)
        # collapse t=280+40=320 < mid=(280+445)/2=362.5 -> 採用
        assert out[0]["end"] == pytest.approx(320.0)


class TestBlackoutPeekOverride:
    """shirurori 型: rate > 0.15 の merge 判定 gap でも後半 or peek に
    blackout run があれば boundary に override + stats 加算。
    """

    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e) -> MatchBoundary:
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_backhal_blackout_overrides_merge(self):
        """adj_probes の後半分に blackout run がある場合、adjudicate_gap は priority 1 で
        "boundary" を返す (blackout は adj_probes 内にあれば直接検知される)。
        このテストは: adj_probes に blackout なし (rate 高 -> merge) + 後半 adj 無 + peek に
        blackout -> peek override が発火するケースを gate する。
        shirurori 型: gap 末尾直後 (next_start 〜 next_start+45s) に zone-in blackout。
        stats["vtuber_merge_overridden"] が 1 加算される。
        """
        segs = [self._seg(0, 100), self._seg(200, 400)]
        stats: dict = {}

        # gap=[100,200]: adj_probes に blackout なし、rate 高い (merge 候補)
        adj_probes = [
            GapProbe(t=100.0 + i, present=True, band_mad=8.0, band_b=90.0)
            for i in range(100)  # 100% present, no blackout -> adjudicate_gap = "merge"
        ]
        # peek=[200, 245]: blackout run at t=200,201
        peek_probes = [
            GapProbe(t=200.0 + i, present=False, band_mad=2.0, band_b=5.0)
            for i in range(2)  # zone-in blackout run
        ] + [
            GapProbe(t=202.0 + i, present=True, band_mad=8.0, band_b=90.0)
            for i in range(3)  # match start evidence
        ]

        call_count = [0]

        def _spy_probe(vp, anchor, t0, t1, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return adj_probes  # adjudication: merge (high rate, no blackout)
            if abs(t0 - 200.0) < 0.5:
                return peek_probes  # peek reveals zone-in blackout
            return []  # snap probe: no change

        with (
            patch(
                "allaganeye.video.vtuber_timeline.probe_gap",
                side_effect=_spy_probe,
            ),
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, s, **kw: s,
            ),
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs, stats=stats)  # type: ignore[arg-type]

        # peek override: boundary (2 segments maintained)
        assert len(out) == 2
        assert stats.get("vtuber_merge_overridden", 0) == 1

    def test_peek_blackout_overrides_merge_when_backhal_clean(self):
        """adj_probes の後半にブラックアウトなし + peek probe に blackout run があれば
        boundary に override。peek probe の range が (next_start, next_start + EDGE_EXT_S)
        であることを assert。
        """
        segs = [self._seg(0, 100), self._seg(200, 400)]
        stats: dict = {}

        # gap=[100,200]: adj_probes 全て in-match (高 rate, no blackout)
        adj_probes = [
            GapProbe(t=100.0 + i, present=True, band_mad=8.0, band_b=90.0)
            for i in range(100)
        ]

        peek_calls: list[dict] = []

        def _spy_probe(vp, anchor, t0, t1, **kw):
            if abs(t0 - 100.0) < 0.5 and abs(t1 - 200.0) < 0.5:
                return adj_probes
            if t0 >= 199.0:  # peek range
                peek_calls.append({"t0": t0, "t1": t1})
                # peek に blackout run を返す
                return [
                    GapProbe(t=t0 + i, present=False, band_mad=2.0, band_b=5.0)
                    for i in range(2)
                ] + [
                    GapProbe(t=t0 + 2 + i, present=False, band_mad=5.0, band_b=90.0)
                    for i in range(3)
                ]
            return []

        with (
            patch(
                "allaganeye.video.vtuber_timeline.probe_gap",
                side_effect=_spy_probe,
            ),
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, s, **kw: s,
            ),
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs, stats=stats)  # type: ignore[arg-type]

        # peek override: boundary
        assert len(out) == 2
        assert stats.get("vtuber_merge_overridden", 0) == 1
        # peek range: (next_start, next_start + EDGE_EXT_S)
        assert peek_calls, "peek probe_gap was not called"
        assert peek_calls[0]["t0"] == pytest.approx(200.0)

    def test_no_blackout_in_backhal_or_peek_merges(self):
        """後半 + peek に blackout なし -> merge 確定 (override されない)。"""
        segs = [self._seg(0, 100), self._seg(200, 400)]
        stats: dict = {}

        adj_probes = [
            GapProbe(t=100.0 + i, present=True, band_mad=8.0, band_b=90.0)
            for i in range(100)
        ]

        def _spy_probe(vp, anchor, t0, t1, **kw):
            if abs(t0 - 100.0) < 0.5 and abs(t1 - 200.0) < 0.5:
                return adj_probes
            # peek: no blackout
            return [
                GapProbe(t=t0 + i, present=False, band_mad=5.0, band_b=90.0)
                for i in range(max(0, int(t1 - t0)))
            ]

        with (
            patch(
                "allaganeye.video.vtuber_timeline.probe_gap",
                side_effect=_spy_probe,
            ),
            patch(
                "allaganeye.video.vtuber_timeline._snap_outer_edges",
                side_effect=lambda vp, a, s, **kw: s,
            ),
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs, stats=stats)  # type: ignore[arg-type]

        # no override: merged into 1
        assert len(out) == 1
        assert stats.get("vtuber_merge_overridden", 0) == 0


class TestMergeRate015:
    """meteor 型: rate 0.13 の gap が MERGE_RATE=0.15 で boundary になる。"""

    def test_rate_0137_is_boundary_with_new_threshold(self):
        """rate < 0.15 は boundary (旧 0.10 なら merge だった)。
        meteor 実測 rate 0.137: valid=175, present=24 -> rate=13.7%。
        """
        # 175 probes: present=24, absent=151 -> rate=24/175=0.137
        valid = [
            GapProbe(t=float(i), present=True, band_mad=5.0, band_b=80.0)
            for i in range(24)
        ] + [
            GapProbe(t=float(24 + i), present=False, band_mad=5.0, band_b=80.0)
            for i in range(151)
        ]
        # rate=13.7% < 0.15 -> boundary
        assert adjudicate_gap(valid) == "boundary"

    def test_rate_exactly_015_is_merge(self):
        """rate == 0.15 (境界値) は merge (>= 比較)。"""
        # 100 probes: present=15, absent=85 -> rate=15%
        valid = [
            GapProbe(t=float(i), present=True, band_mad=5.0, band_b=80.0)
            for i in range(15)
        ] + [
            GapProbe(t=float(15 + i), present=False, band_mad=5.0, band_b=80.0)
            for i in range(85)
        ]
        assert adjudicate_gap(valid) == "merge"

    def test_rate_010_was_merge_now_boundary(self):
        """rate 10% は旧閾値 (0.10) なら merge だが新閾値 (0.15) では boundary。"""
        # 100 probes: present=10 -> rate=10%
        valid = [
            GapProbe(t=float(i), present=True, band_mad=5.0, band_b=80.0)
            for i in range(10)
        ] + [
            GapProbe(t=float(10 + i), present=False, band_mad=5.0, band_b=80.0)
            for i in range(90)
        ]
        # rate=10% < 0.15 -> boundary (旧: merge)
        assert adjudicate_gap(valid) == "boundary"


class TestSnapStartPriorityOrder:
    """_snap_start の優先順 1 > 2 > 3。"""

    def test_priority1_blackout_in_lo_hi_wins_over_evidence(self):
        """優先順 1: (lo, hi] 内の最後の blackout run end が evidence run より優先。
        blackout run end と evidence run 先頭が両方存在するとき blackout が勝つ。
        prev_end=0, next_start=100, mid=50
        "l"*40 + "bb" + "M"*58: blackout idx40-41 (end t=41), trailing evidence t=43..100
        優先順 1: blackout run end t=41 -> new_start=41
        優先順 3 (evidence fallback): trailing run 先頭 t=43 > mid=50? いや t=43 < mid=50 -> 不採用
        """
        probes = _gap_probes("l" * 40 + "bb" + "M" * 58)
        _new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        # 優先順 1: blackout run end t=41 -> new_start=41.0
        assert new_start == probes[41].t

    def test_priority2_blackout_after_hi_is_used_when_none_in_lo_hi(self):
        """優先順 2: (hi, ext_hi] 内の最初の blackout run を使う。
        snap_segment_edges は ext_hi パラメータを持たないため、
        このケースは refine_segments 経由で probe_gap の拡張範囲に含まれる。
        ここでは snap_segment_edges レベルで: (lo, hi] 内に blackout なし + evidence なし
        -> new_start = next_start 維持 (= priority 2 は _snap_start 内の処理、
        probes 範囲内では (hi, ext_hi] は含まれないため None になるケース)。
        """
        # all absent: no blackout in (0, 100], no evidence -> priority 4: None -> coarse
        probes = _gap_probes("l" * 100)
        _new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        assert new_start == 100.0  # コース edge 維持

    def test_priority3_evidence_fallback_with_midpoint_constraint(self):
        """優先順 3: blackout run なし + trailing evidence run の先頭 > mid -> 採用。"""
        # "l"*60 + "M"*40: trailing run 先頭 t=60 > mid=50 -> 採用
        probes = _gap_probes("l" * 60 + "M" * 40)
        _new_end, new_start = snap_segment_edges(0.0, 100.0, probes)
        assert new_start == probes[60].t  # t=60 > mid=50 -> 採用


# ---------------------------------------------------------------------------
# Round 6: Bug A / Bug B / Bug C / V2 hard-gap break
# ---------------------------------------------------------------------------


class TestBugAExtHiPropagation:
    """Bug A: snap_segment_edges の内側 gap path が ext_hi を _snap_start に渡す。
    (hi, ext_hi] 内の blackout run が Priority 2 で採用されること。
    shirurori M3 -23 実測原因: blackout が粗 gap の外側にある場合の救済。
    """

    def test_inner_gap_ext_hi_adopts_blackout_outside_hi(self):
        """_snap_start に ext_hi を渡すと (hi, ext_hi] の blackout が priority 2 で採用される。
        prev_end=0, next_start=60, ext_hi=60+45=105
        probes: t=[0, 104] (105 probe): t=0..60 absent, t=61,62 blackout, t=63..104 absent
        -> (0, 60] に blackout run end なし -> priority 1 不発
        -> ext_hi=105: (60, 105] に blackout run end t=62 -> priority 2 採用
        """
        probes = _gap_probes("l" * 61 + "bb" + "l" * 42)  # 105 probes
        assert len(probes) == 105
        # ext_hi を明示して _snap_start を直接呼ぶ
        result = _snap_start(probes, 0.0, 60.0, ext_hi=60.0 + EDGE_EXT_S)
        # priority 2: blackout run end t=62 in (60, 105] -> adopted
        assert result == probes[62].t  # t=62.0

    def test_inner_gap_no_ext_hi_blackout_outside_hi_not_adopted(self):
        """ext_hi=None のとき (hi, ...] の blackout は採用されない (Bug A 旧挙動確認)。"""
        probes = _gap_probes("l" * 61 + "bb" + "l" * 42)
        # ext_hi=None -> priority 2 スキップ -> priority 3: trailing run なし -> None
        result = _snap_start(probes, 0.0, 60.0, ext_hi=None)
        assert result is None  # ext_hi なしでは採用されない

    def test_snap_segment_edges_passes_ext_hi_correctly(self):
        """snap_segment_edges(ext_hi=next_start+EDGE_EXT_S) を明示すると
        (hi, ext_hi] の blackout が new_start に snap する。
        """
        # hi=50, ext_hi=50+EDGE_EXT_S=95
        # probes: t=0..94, blackout at t=51,52 (= hi+1, hi+2)
        probes = _gap_probes("l" * 51 + "bb" + "l" * 42)  # 95 probes
        _new_end, new_start = snap_segment_edges(
            0.0, 50.0, probes, ext_hi=50.0 + EDGE_EXT_S
        )
        # (0, 50] に blackout なし -> priority 1 不発
        # ext_hi=95: (50, 95] に blackout run end t=52 -> priority 2
        assert new_start == probes[52].t  # t=52.0


class TestBugBIntraMatchGuardLocal:
    """Bug B: _snap_start の in-match guard を局所窓 (before 5s / after 10s) に変更。
    120s 広窓の先頭にある前試合 evidence が guard を誤発火させない。
    """

    def test_zone_in_blackout_adopted_when_prev_evidence_is_far(self):
        """前試合 evidence が blackout run より 90s+ 前にある場合、
        局所窓 5s 以内に evidence がなければ in-match guard は不発 -> blackout 採用。
        shikke M6 型: 直前 90s 無 evidence の zone-in blackout が採用される。
        stride=1s で probes[0..89]=evidence (90s 分), probes[90..109]=absent (20s),
        probes[110,111]=blackout, probes[112..119]=absent
        blackout run 先頭 t=110 の before 5s 窓 = [105, 110): t=105..109 はすべて absent
        -> has_evidence_before = False -> guard 不発 -> blackout end t=111 採用
        """
        # 90 evidence + 20 absent + 2 blackout + 8 absent = 120 probes
        probes = _gap_probes("M" * 90 + "l" * 20 + "bb" + "l" * 8)
        assert len(probes) == 120
        # lo=0, hi=120 (probes 全体を (lo, hi] に収める)
        result = _snap_start(probes, 0.0, 120.0, ext_hi=None)
        # blackout end t=111: before 5s に evidence なし -> guard 不発 -> 採用
        assert result == probes[111].t  # t=111.0

    def test_shinryu_type_intra_match_blackout_excluded(self):
        """shinryu 型瞬断: 直前 1s + 直後 8s に evidence -> guard 発火 -> 除外。
        before_s=5: blackout run 先頭 t=5 の before 窓 [0, 5): t=4 に evidence -> 成立
        after_s=10: blackout run 末尾 t=6 の after 窓 (6, 16]: t=7 に evidence -> 成立
        -> 両方成立 -> is_intra_match -> skip
        """
        # t=0..3: evidence(4), t=4: evidence, t=5,6: blackout, t=7..14: evidence(8), t=15..99: absent
        probes = _gap_probes("M" * 5 + "bb" + "M" * 8 + "l" * 85)
        assert len(probes) == 100
        result = _snap_start(probes, 0.0, 100.0, ext_hi=None)
        # blackout は intra-match -> skip。trailing evidence run (M*8): run 先頭 t=7
        # priority 3: trailing run (先頭 t=7, mid=50): t=7 < mid=50 -> 不採用 -> None
        # -> fallback: no priority fires -> None
        assert result is None

    def test_shirurori_type_before_6s_outside_window_adopted(self):
        """shirurori 型: 直前 6s に result 余韻 evidence が存在しても
        before 窓 5s 内には入らない -> has_evidence_before=False -> guard 不発 -> 採用。
        probes stride=1s:
        t=0..99: absent (100s), t=100: evidence (1 probe, "M"), t=101..105: absent (5s gap),
        t=106,107: blackout, t=108..119: absent
        blackout run 先頭 t=106 の before 窓 [101, 106): t=101..105 は absent
        -> has_evidence_before = False -> guard 不発 -> blackout end t=107 採用
        """
        probes = _gap_probes("l" * 100 + "M" + "l" * 5 + "bb" + "l" * 12)
        assert len(probes) == 120
        result = _snap_start(probes, 0.0, 120.0, ext_hi=None)
        # blackout end t=107: before 窓内に evidence なし -> 採用
        assert result == probes[107].t  # t=107.0

    def test_intra_evidence_after_boundary_10s(self):
        """after 窓が 10s であることを直接確認:
        blackout 直後 9s に evidence -> has_evidence_after=True (10s 窓内)
        -> before 側も成立すれば guard 発火。
        before=1s (成立): after=9s (成立 <=10s) -> intra-match -> excluded。
        """
        # t=0..2: evidence (3s = before 1s), t=3,4: blackout, t=5..13: evidence (9s = after 9s)
        probes = _gap_probes("M" * 3 + "bb" + "M" * 9 + "l" * 84)
        result = _snap_start(probes, 0.0, 100.0, ext_hi=None)
        # before: t=2 is 1s before blackout[0]=t=3 -> within 5s -> True
        # after: t=5 is 1s after blackout[1]=t=4 -> within 10s -> True -> intra-match
        assert result is None  # guard fires, trailing evidence run start < mid -> None

    def test_intra_evidence_after_boundary_11s_is_not_guard(self):
        """after 窓 10s 境界: blackout 直後 11s に初めて evidence -> has_evidence_after=False
        -> guard 不発 -> blackout 採用。
        """
        # t=0..2: evidence, t=3,4: blackout, t=5..15: absent (11s gap), t=16: evidence
        probes = _gap_probes("M" * 3 + "bb" + "l" * 11 + "M" + "l" * 83)
        result = _snap_start(probes, 0.0, 100.0, ext_hi=None)
        # after 窓: blackout end t=4, after 10s -> (4, 14]: t=5..14 はすべて absent
        # -> has_evidence_after = False -> guard 不発 -> blackout end t=4 採用
        assert result == probes[4].t  # t=4.0


class TestBugCSnapEndDropoutRescue:
    """Bug C: _snap_end の leading run dropout 救済 (END_FAR_RESCUE_S=60s)。
    kyuma M6 -91 / meteor M5 -98 型: Onsal 明滅で leading run が粗 end の 60s 超前に終端。
    後続 3+ probe run が lo-60s 以内にあれば候補を置換する。
    """

    def test_rescue_applied_when_leading_run_ends_far_before_lo(self):
        """leading run が lo-90s に終端 + 後続 3+ probe run が lo-10s に終端 -> 救済。
        probes stride=1s: lo=120, hi=240, mid=180
        t=0..9: evidence (leading, idx 0-9, t=0..9)
        t=10..109: absent (100s gap)
        t=110..113: evidence run (len=4 >=3, t=110..113), run end t=113 < mid=180 かつ t >= lo-60=60
        -> rescue: candidate が 113 に置換 < mid=180 -> 採用
        """
        probes = _gap_probes("M" * 10 + "l" * 100 + "M" * 4 + "l" * 106)
        assert len(probes) == 220
        lo, hi = 120.0, 240.0
        result = _snap_end(probes, lo, hi)
        # leading run end t=9 << lo-60=60 -> rescue triggered
        # rescue candidate: t=113 (run end) < mid=180 and t >= 60 -> adopted
        assert result == probes[113].t  # t=113.0

    def test_shinryu_m3_type_no_rescue_leading_adopted(self):
        """shinryu M3 型: leading run end が lo-41s (= lo-60s 以内) -> 直接採用 (rescue 不発)。
        probes stride=1s: lo=80, hi=180, mid=130
        t=0..39: evidence (leading, end t=39, lo-80+39=lo-41=41 ... 実際 t=39 = lo-41)
        -> lo - END_FAR_RESCUE_S = 80-60=20 -> t=39 >= 20 -> 60s 以内 -> 直接採用 (rescue 不要)
        """
        lo, hi = 80.0, 180.0
        # mid = (lo + hi) / 2.0 = 130 (used in comment only)
        probes = _gap_probes("M" * 40 + "l" * 60 + "M" + "l" * 19)  # 120 probes
        # leading end t=39, lo-60=20, t=39 >= 20 -> not "far" -> leading 採用
        result = _snap_end(probes, lo, hi)
        # leading run end t=39 < mid=130 -> adopted (no rescue)
        assert result == probes[39].t  # t=39.0

    def test_rescue_not_applied_when_subsequent_run_too_short(self):
        """後続 run が 2 probe (< 3) のみ -> rescue 不発 -> leading run 採用。"""
        # leading run end t=9 << lo-60 -> rescue triggered, but subsequent run len=2
        probes = _gap_probes("M" * 10 + "l" * 100 + "M" * 2 + "l" * 108)
        lo, hi = 120.0, 240.0
        result = _snap_end(probes, lo, hi)
        # subsequent run len=2 < 3 -> not eligible -> rescue fails -> leading t=9 adopted
        # BUT t=9 < lo-60=60 -> "far" -> rescue triggered but no eligible run -> None or leading?
        # spec: rescue fails -> leading candidate still used if < mid
        # t=9 < mid=180 -> adopt leading (rescue fails, no replacement)
        assert result == probes[9].t  # t=9.0 (leading, rescue fails)

    def test_rescue_not_applied_when_subsequent_run_after_mid(self):
        """後続 run 末尾が mid 以降 -> rescue 対象外 -> leading run 採用。"""
        # leading end t=9, lo=80, hi=240, mid=160
        # subsequent run: t=170..173 (run end t=173 >= mid=160) -> not eligible
        lo, hi = 80.0, 240.0
        probes = _gap_probes("M" * 10 + "l" * 160 + "M" * 4 + "l" * 66)
        result = _snap_end(probes, lo, hi)
        # subsequent run end t=173 >= mid=160 -> not eligible -> leading t=9 adopted
        assert result == probes[9].t  # t=9.0

    def test_rescue_not_applied_when_subsequent_run_too_far_from_lo(self):
        """後続 run 末尾が lo-END_FAR_RESCUE_S 未満 -> rescue 対象外 (60s 超) -> leading 採用。"""
        # leading end t=5, lo=120, hi=240, lo-60=60
        # subsequent run: t=50..53 (run end t=53 < lo-60=60) -> not eligible
        lo, hi = 120.0, 240.0
        probes = _gap_probes("M" * 6 + "l" * 44 + "M" * 4 + "l" * 166)
        result = _snap_end(probes, lo, hi)
        # subsequent run end t=53 < lo-60=60 -> not eligible -> leading t=5 adopted
        assert result == probes[5].t  # t=5.0
