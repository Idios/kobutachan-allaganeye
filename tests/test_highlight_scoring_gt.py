"""L6 ストリークスコアリングの GT 突合ハーネス (#1049 作業項目 3、Q3-B)。

設計の正: `docs/superpowers/specs/2026-11-25-l6-streak-scoring-design.md` 5 節

GT は `tests/fixtures/highlights_gt/scoring_gt.json`（5.1 節の形式）。**裁定は
Idios の作業**なので、ファイルが無い間は理由付きで skip する。裁定が入れば
「窓 5 / 10 / 15 秒のどれが人手の順位と最も一致するか」と「Spearman が
しきい値以上か」を毎 PR の既定実行で検査するゲートになる。

入力は GT イベントの JSON (`tests/fixtures/indicators_gt/*.json`) だけで、
動画は開かない。そのため `slow` マーカーは付けない（5.4）。

ワークシート（裁定用の一覧）は `pytest -s tests/test_highlight_scoring_gt.py` で
標準出力に出る。GT ファイルが無いときの skip メッセージにも同じコマンドを載せる。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

import pytest

from allaganeye.highlights.scoring import (
    DEFAULT_WINDOW_SECONDS,
    ScoringEvent,
    group_streaks,
    score_events,
)

FIXTURES = Path(__file__).parent / "fixtures"
INDICATOR_GT_DIR = FIXTURES / "indicators_gt"
GT_FILE = FIXTURES / "highlights_gt" / "scoring_gt.json"

# 既定窓 (10 秒) を参照窓として採点し、広い窓は感度チェック用に併記する
# (窓の既定は Idios 判断 2026-11-26 で +-10 秒に確定。設計メモ 1 節 Q2)。
WINDOWS = (10.0, 15.0, 20.0)
# 段階は 3 値。
TIERS = (1, 2, 3)
# 強とみなす段階（precision@N の集計に使う）。
STRONG_TIER = max(TIERS)
# 合格線は**絶対値ではなく回帰ピン**（設計メモ 5.3 節 / 6 節）。
# 2026-11-26 の人手裁定 (Idios) に対する実測値で、品質の主張ではない。
# 同点構造による上限は 0.619 だが、重みの振り幅では 0.33 止まり (6.1 節)。
BASELINE_RHO = 0.231
RHO_TOLERANCE = 0.02
TOP_N = 10
# GT は表示終了時刻を持たないため `end = start`。スコアは `end` を使わない (4)。
WORKSHEET_COMMAND = "pytest -s tests/test_highlight_scoring_gt.py"


@dataclass(frozen=True)
class GtGroup:
    """参照窓で束ねた 1 グループと、人手の段階 (1=弱 / 2=中 / 3=強)。

    `tier` は裁定前は `None` (draft)。
    """

    tier: int | None
    events: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class GtCase:
    label: str
    source: str
    groups: tuple[GtGroup, ...]


@dataclass(frozen=True)
class ScoringGt:
    reference_window: float
    provenance: str
    cases: tuple[GtCase, ...]

    @property
    def group_count(self) -> int:
        return sum(len(case.groups) for case in self.cases)

    @property
    def pending_groups(self) -> int:
        """`tier` が未記入のグループ数。0 なら裁定済。"""
        return sum(
            1 for case in self.cases for group in case.groups if group.tier is None
        )

    @property
    def adjudicated(self) -> bool:
        return self.pending_groups == 0


def _load_case_events(path: Path) -> tuple[str, tuple[ScoringEvent, ...]]:
    """indicators の GT JSON から (`label`, イベント列) を読む。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError(f"{path.name}: events must be a non-empty list")
    events: list[ScoringEvent] = []
    seen: set[tuple[str, float]] = set()
    for index, raw in enumerate(raw_events):
        kind = raw.get("kind")
        start = raw.get("start")
        if kind not in ("ko", "assist"):
            raise ValueError(
                f"{path.name}: events[{index}] has unsupported kind {kind!r}"
            )
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            raise ValueError(f"{path.name}: events[{index}].start must be a number")
        if not math.isfinite(float(start)) or float(start) < 0:
            raise ValueError(
                f"{path.name}: events[{index}].start must be finite and >= 0"
            )
        key = (kind, round(float(start), 6))
        if key in seen:
            raise ValueError(f"{path.name}: duplicate event {key}")
        seen.add(key)
        # GT は表示終了時刻を持たない。スコアは start しか見ない (4)。
        events.append(ScoringEvent(kind=kind, start=float(start), end=float(start)))
    return str(payload["label"]), tuple(events)


def _case_events() -> dict[str, tuple[ScoringEvent, ...]]:
    cases: dict[str, tuple[ScoringEvent, ...]] = {}
    for path in sorted(INDICATOR_GT_DIR.glob("*.json")):
        label, events = _load_case_events(path)
        cases[label] = events
    if not cases:
        raise ValueError(f"no indicator GT fixtures found in {INDICATOR_GT_DIR}")
    return cases


def _event_key(event: ScoringEvent) -> tuple[str, float]:
    return (event.kind, round(event.start, 6))


def _worksheet(
    window: float = DEFAULT_WINDOW_SECONDS, *, with_score: bool = False
) -> str:
    """参照窓の全ストリークを、裁定用の Markdown 表にする (5.1)。

    `with_score=False` が既定。**スコア列はアンカリングになる**ので、人手の採点には
    出さない（モデルの値を見ながら採点すると GT がモデルに追随して循環する）。
    """
    header = "| case | start (s) | size | ko | assist | span (s) |"
    separator = "| --- | --- | --- | --- | --- | --- |"
    if with_score:
        header += " score |"
        separator += " --- |"
    header += " tier |"
    separator += " --- |"
    lines = [
        f"参照窓 {window:g} 秒のストリーク一覧（tier 列を 1=弱 / 2=中 / 3=強 で埋める）",
        "",
        header,
        separator,
    ]
    for label, events in _case_events().items():
        groups = sorted(group_streaks(events, window), key=lambda streak: streak.start)
        scored = {
            round(item.streak.start, 6): item.score
            for item in score_events(events, window_seconds=window)
        }
        for streak in groups:
            row = (
                f"| {label} | {streak.start:.2f} | {streak.size} | {streak.ko_count} | "
                f"{streak.assist_count} | {streak.span_seconds:.2f} |"
            )
            if with_score:
                row += f" {scored[round(streak.start, 6)]:.3f} |"
            lines.append(row + "  |")
    return "\n".join(lines)


def _load_gt(path: Path = GT_FILE) -> ScoringGt:
    """GT を読み、壊れた点は**収集時に落とす**（fail-open にしない）。"""
    payload = json.loads(path.read_text(encoding="utf-8"))

    reference = payload.get("reference_window_seconds")
    if isinstance(reference, bool) or not isinstance(reference, (int, float)):
        raise ValueError("reference_window_seconds must be a number")
    reference = float(reference)
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("reference_window_seconds must be finite and > 0")
    if reference != min(WINDOWS):
        raise ValueError(
            f"reference_window_seconds must be {min(WINDOWS):g} (got {reference:g})"
        )

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("cases must be a non-empty list")

    cases: list[GtCase] = []
    seen_labels: set[str] = set()
    for case_index, raw_case in enumerate(raw_cases):
        label = raw_case.get("label")
        source = raw_case.get("source")
        if not isinstance(label, str) or not label:
            raise ValueError(f"cases[{case_index}].label must be a non-empty string")
        if label in seen_labels:
            raise ValueError(f"duplicate case label {label!r}")
        seen_labels.add(label)
        if not isinstance(source, str) or not source:
            raise ValueError(f"cases[{case_index}].source must be a non-empty string")
        raw_groups = raw_case.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            raise ValueError(f"{label}: groups must be a non-empty list")
        groups = []
        for group_index, raw_group in enumerate(raw_groups):
            tier = raw_group.get("tier")
            if tier is not None and (isinstance(tier, bool) or tier not in TIERS):
                raise ValueError(
                    f"{label}: groups[{group_index}].tier must be one of {TIERS} or null"
                )
            raw_events = raw_group.get("events")
            if not isinstance(raw_events, list) or not raw_events:
                raise ValueError(
                    f"{label}: groups[{group_index}].events must be non-empty"
                )
            events = []
            for event_index, raw_event in enumerate(raw_events):
                kind = raw_event.get("kind")
                start = raw_event.get("start")
                if kind not in ("ko", "assist"):
                    raise ValueError(
                        f"{label}: groups[{group_index}].events[{event_index}] "
                        f"has unsupported kind {kind!r}"
                    )
                if isinstance(start, bool) or not isinstance(start, (int, float)):
                    raise ValueError(
                        f"{label}: groups[{group_index}].events[{event_index}].start "
                        f"must be a number"
                    )
                events.append((kind, round(float(start), 6)))
            if len(set(events)) != len(events):
                raise ValueError(f"{label}: groups[{group_index}] has duplicate events")
            groups.append(
                GtGroup(tier=None if tier is None else int(tier), events=tuple(events))
            )
        cases.append(GtCase(label=label, source=source, groups=tuple(groups)))

    known = _case_events()
    for case in cases:
        if case.label not in known:
            raise ValueError(f"case {case.label!r} has no indicator GT fixture")
        listed = {event for group in case.groups for event in group.events}
        actual = {_event_key(event) for event in known[case.label]}
        if listed != actual:
            missing = sorted(actual - listed)
            extra = sorted(listed - actual)
            raise ValueError(
                f"{case.label}: group events do not match the indicator GT "
                f"(missing={missing}, extra={extra})"
            )

    return ScoringGt(
        reference_window=reference,
        provenance=str(payload.get("provenance", "")),
        cases=tuple(cases),
    )


def _require_gt(*, require_adjudicated: bool = False) -> ScoringGt:
    if not GT_FILE.is_file():
        pytest.skip(
            f"GT 裁定が未投入: {GT_FILE} が無い。"
            f"ワークシートは `{WORKSHEET_COMMAND}` で生成できる "
            "(設計メモ 5.1 節 / Q3-B の裁定は Idios の作業)"
        )
    gt = _load_gt()
    if require_adjudicated and not gt.adjudicated:
        pytest.skip(
            f"tier 未記入が {gt.pending_groups} 件残っている（draft 状態）。"
            f"`{GT_FILE}` の各 group の `tier` を 1=弱 / 2=中 / 3=強 で埋めると有効になる "
            f"(一覧は `{WORKSHEET_COMMAND}`、画像は "
            "`python scripts/highlights_gt_sheets.py`)"
        )
    return gt


def _ranks(values: Sequence[float]) -> list[float]:
    """同点に平均順位を与える (Spearman の tie 補正)。"""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while (
            end + 1 < len(order) and values[order[end + 1]] == values[order[position]]
        ):
            end += 1
        average = (position + end) / 2 + 1
        for slot in range(position, end + 1):
            ranks[order[slot]] = average
        position = end + 1
    return ranks


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("pearson requires two sequences of the same length >= 2")
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        # 片方が完全な同点だと相関は定義できない。0 を返して「識別力なし」を表す。
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    return _pearson(_ranks(xs), _ranks(ys))


def _ceiling_rho(scores: Sequence[float], tiers: Sequence[float]) -> float:
    """到達可能な上限の rho。

    スコアが同点の項目は、どんなスコア式でも分離できない。そこで**同点グループの
    並び順だけを最良に選べる**としたときの rho を上限とする。Spearman は
    グループの平均 tier 順位でグループを並べたときに最大になるので、その順に
    x の平均順位を割り当てて相関を取る（グループ内の段階の割れは上限を下げる）。
    """
    tier_ranks = _ranks(tiers)
    grouped: dict[float, list[int]] = {}
    for index, score in enumerate(scores):
        grouped.setdefault(score, []).append(index)
    order = sorted(
        grouped,
        key=lambda score: (
            sum(tier_ranks[i] for i in grouped[score]) / len(grouped[score])
        ),
    )
    x_ranks = [0.0] * len(scores)
    position = 0
    for score in order:
        members = grouped[score]
        end = position + len(members)
        average = (position + end + 1) / 2
        for index in members:
            x_ranks[index] = average
        position = end
    return _pearson(x_ranks, tier_ranks)


def _precision_at(scores: Sequence[float], tiers: Sequence[float], n: int) -> float:
    """上位 n 件のうち強 tier の割合 (L7 は上位 N 件しか使わない)。"""
    order = sorted(range(len(scores)), key=lambda index: -scores[index])[:n]
    if not order:
        return 0.0
    return sum(1 for index in order if tiers[index] == STRONG_TIER) / len(order)


def _strong_share(tiers: Sequence[float]) -> float:
    """母集団における強 tier の割合 (precision@N の基準線)。"""
    return sum(1 for tier in tiers if tier == STRONG_TIER) / len(tiers)


def _model_scores_by_streak(
    events: Sequence[ScoringEvent], window: float
) -> dict[tuple[str, float], float]:
    """ストリークの先頭イベントで引けるスコア表。"""
    return {
        _event_key(item.streak.events[0]): item.score
        for item in score_events(events, window_seconds=window)
    }


def _streak_of(
    events: Sequence[ScoringEvent], window: float, key: tuple[str, float]
) -> tuple[str, float]:
    """イベントが属するストリークの先頭イベントを返す (窓の拡大で必ず一意)。"""
    for streak in group_streaks(events, window):
        if any(_event_key(event) == key for event in streak.events):
            return _event_key(streak.events[0])
    raise AssertionError(f"event {key} not found in any streak")


def _reference_tiers_by_window(
    gt: ScoringGt, window: float, *, aggregate: str
) -> tuple[list[float], list[float]]:
    """窓 `window` の (モデルスコア, 参照段階) を全 case 分返す (5.2)。"""
    known = _case_events()
    scores: list[float] = []
    tiers: list[float] = []
    for case in gt.cases:
        events = known[case.label]
        score_by_streak = _model_scores_by_streak(events, window)
        collected: dict[tuple[str, float], list[int]] = {}
        for group in case.groups:
            if group.tier is None:
                raise AssertionError(
                    f"{case.label}: unadjudicated group reached the scoring path"
                )
            anchor = _streak_of(events, window, group.events[0])
            for event in group.events:
                if _streak_of(events, window, event) != anchor:
                    raise AssertionError(
                        f"{case.label}: reference group split at window {window:g} "
                        "(reference window must be the minimum)"
                    )
            collected.setdefault(anchor, []).append(group.tier)
        for anchor, group_tiers in collected.items():
            if aggregate == "max":
                tier = float(max(group_tiers))
            elif aggregate == "mean":
                tier = sum(group_tiers) / len(group_tiers)
            else:  # pragma: no cover - 呼び出し側の取り違え
                raise ValueError(f"unknown aggregate {aggregate!r}")
            scores.append(score_by_streak[anchor])
            tiers.append(tier)
    return scores, tiers


def _rhos(gt: ScoringGt) -> dict[float, float]:
    """窓ごとの Spearman (max 集約)。"""
    return {
        window: _spearman(*_reference_tiers_by_window(gt, window, aggregate="max"))
        for window in WINDOWS
    }


def _rho_table(gt: ScoringGt) -> str:
    lines = [
        "| window (s) | n | rho | 上限 rho | precision@10 | 母集団 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for window in WINDOWS:
        scores, tiers = _reference_tiers_by_window(gt, window, aggregate="max")
        lines.append(
            f"| {window:g} | {len(scores)} | {_spearman(scores, tiers):+.3f} | "
            f"{_ceiling_rho(scores, tiers):.3f} | "
            f"{_precision_at(scores, tiers, TOP_N):.2f} | "
            f"{_strong_share(tiers):.2f} |"
        )
    return "\n".join(lines)


def test_worksheet_covers_every_reference_streak() -> None:
    """裁定用ワークシートが参照窓の全ストリークを含む (GT 未投入でも回る)。"""
    worksheet = _worksheet()
    rows = [
        line
        for line in worksheet.splitlines()
        if line.startswith("| ") and "---" not in line
    ]
    # ヘッダ行を除いた件数が、参照窓のストリーク総数と一致する。
    expected = sum(
        len(group_streaks(events, DEFAULT_WINDOW_SECONDS))
        for events in _case_events().values()
    )
    assert len(rows) - 1 == expected
    assert expected > 0
    print(worksheet)  # `-s` で一覧を確認できる


def test_spearman_handles_ties_and_extremes() -> None:
    """Spearman 実装の性質 (同点平均順位・完全一致・完全逆転)。"""
    assert _spearman([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert _spearman([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    # 27 件の同点塊があっても 0 除算しない。
    assert math.isfinite(_spearman([0.372] * 5, [1.0, 2.0, 3.0, 1.0, 2.0]))
    # 片側が完全な同点なら「識別力なし」の 0。
    assert _spearman([0.5] * 4, [1.0, 2.0, 3.0, 1.0]) == 0.0


def test_gt_file_is_well_formed() -> None:
    """GT が形式・イベント集合・参照窓の整合を満たす (5.1)。"""
    gt = _require_gt()
    known = _case_events()
    assert gt.reference_window == min(WINDOWS)
    assert gt.group_count > 0
    assert {case.label for case in gt.cases} <= set(known)


def test_reference_groups_match_group_streaks() -> None:
    """参照グループが実装の束ね結果と一致する (GT とコードのドリフト検出)。"""
    gt = _require_gt()
    known = _case_events()
    for case in gt.cases:
        expected = [
            tuple(sorted(_event_key(event) for event in streak.events))
            for streak in group_streaks(known[case.label], gt.reference_window)
        ]
        actual = [tuple(sorted(group.events)) for group in case.groups]
        assert sorted(actual) == sorted(expected), (
            f"{case.label}: GT groups drifted from group_streaks() at "
            f"{gt.reference_window:g}s\nGT={sorted(actual)}\nimpl={sorted(expected)}"
        )


def test_default_window_is_not_worse_than_the_recorded_baseline() -> None:
    """既定窓で人手と正相関し、記録した baseline を下回らない（回帰ゲート）。

    絶対値の合格線（当初の 0.60）を使わないのは、上限が同点構造で 0.619 に
    抑えられ、重みの振り幅では 0.33 までしか届かないため（設計メモ 5.3 / 6.1 節）。
    数値の意味は表を読んで判断する。
    """
    gt = _require_gt(require_adjudicated=True)
    table = _rho_table(gt)
    print(table)
    reference = gt.reference_window
    assert reference == DEFAULT_WINDOW_SECONDS
    scores, tiers = _reference_tiers_by_window(gt, reference, aggregate="max")
    rho = _spearman(scores, tiers)
    assert rho > 0, f"Spearman {rho:+.3f} is not positive at {reference:g}s\n{table}"
    assert rho >= BASELINE_RHO - RHO_TOLERANCE, (
        f"Spearman {rho:+.3f} < baseline {BASELINE_RHO:+.3f} - {RHO_TOLERANCE}\n{table}"
    )
    # 上限は実測以上でなければならない（集計の取り違え検出）。
    assert _ceiling_rho(scores, tiers) >= rho - 1e-9


def test_mean_aggregate_tracks_merged_groups() -> None:
    """max は最良の瞬間、mean は平均。広い窓で段階が割れると両者はずれる。"""
    gt = _require_gt(require_adjudicated=True)
    diverged = False
    for window in WINDOWS:
        scores, tiers = _reference_tiers_by_window(gt, window, aggregate="mean")
        assert len(scores) == len(tiers)
        assert all(math.isfinite(score) for score in scores)
        _, max_tiers = _reference_tiers_by_window(gt, window, aggregate="max")
        assert all(mean <= peak for mean, peak in zip(tiers, max_tiers, strict=True))
        diverged |= tiers != max_tiers
    assert diverged, (
        "参照グループが window 内で混ざらない = GT の粒度が窓に対して細かすぎる"
    )


# --- 合成 GT: 人手裁定を待たずに Spearman 経路を実試験する -------------------


def _write_synthetic_gt(
    tmp_path: Path, *, low: float = 0.4, high: float = 0.55, reverse: bool = False
) -> Path:
    """スコアから機械的に tier を作った GT (人手裁定の代用)。

    **ゲートの経路 (ロード・窓写像・Spearman) を今のうちに実行するためだけ**の
    もので、精度の根拠にはならない。tier がスコアの単調関数なら高い相関が出る
    はずで、写像の取り違え (窓を跨いだグループの取りこぼし等) を検出できる。
    しきい値は既定窓でのスコア分布のおよそ三分位 (設計メモ 6 節)。
    """

    def tier_of_score(score: float) -> int:
        tier = 3 if score >= high else 2 if score >= low else 1
        return 4 - tier if reverse else tier

    cases = []
    for label, events in _case_events().items():
        scored = sorted(
            (
                (item.streak, item.score)
                for item in score_events(events, window_seconds=DEFAULT_WINDOW_SECONDS)
            ),
            key=lambda pair: pair[0].start,
        )
        cases.append(
            {
                "label": label,
                "source": "synthetic",
                "groups": [
                    {
                        "tier": tier_of_score(score),
                        "events": [
                            {"kind": event.kind, "start": round(event.start, 6)}
                            for event in streak.events
                        ],
                    }
                    for streak, score in scored
                ],
            }
        )
    payload = {
        "reference_window_seconds": DEFAULT_WINDOW_SECONDS,
        "provenance": "synthetic (テスト専用。人手裁定の代用にはならない)",
        "cases": cases,
    }
    path = tmp_path / "scoring_gt.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_synthetic_gt_runs_the_full_gate_path(tmp_path: Path) -> None:
    """合成 GT でロード -> 窓写像 -> Spearman が一貫して動く (単調なら高相関)。"""
    gt = _load_gt(_write_synthetic_gt(tmp_path))
    known = _case_events()
    assert gt.adjudicated
    assert gt.pending_groups == 0
    assert gt.group_count == sum(
        len(group_streaks(events, DEFAULT_WINDOW_SECONDS)) for events in known.values()
    )
    scores, tiers = _reference_tiers_by_window(
        gt, DEFAULT_WINDOW_SECONDS, aggregate="max"
    )
    assert len(scores) == gt.group_count
    # tier はスコアの階段関数なので、同点 (同一 tier 内の異なるスコア) の分だけ下がる。
    assert _spearman(scores, tiers) > 0.9
    # 窓を広げても正の相関を保つ（写像でグループを取りこぼしていない）。
    assert all(rho > 0.3 for rho in _rhos(gt).values())


def test_synthetic_reversed_gt_fails_the_threshold(tmp_path: Path) -> None:
    """逆順の GT では rho < 0 になりゲートを満たさない（ゲートの red 実証）。"""
    gt = _load_gt(_write_synthetic_gt(tmp_path, reverse=True))
    rhos = _rhos(gt)
    assert rhos[DEFAULT_WINDOW_SECONDS] < 0
    assert rhos[DEFAULT_WINDOW_SECONDS] < BASELINE_RHO - RHO_TOLERANCE


def test_synthetic_mean_aggregate_diverges_from_max(tmp_path: Path) -> None:
    """広い窓で段階が割れると mean 集約は max 集約より小さくなる。"""
    gt = _load_gt(_write_synthetic_gt(tmp_path))
    diverged = False
    for window in WINDOWS:
        _, mean_tiers = _reference_tiers_by_window(gt, window, aggregate="mean")
        _, max_tiers = _reference_tiers_by_window(gt, window, aggregate="max")
        assert all(
            mean <= peak for mean, peak in zip(mean_tiers, max_tiers, strict=True)
        )
        diverged |= mean_tiers != max_tiers
    assert diverged
