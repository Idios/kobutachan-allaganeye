"""VTuber timeline GT (P3, #895)。

GT (tests/baselines/v0.3.0/vtuber-gt/*.json) を `--vtuber` detect
と突合する。slow test は実 VOD 必須 (source dir は GT の source_env_var 経由)。
pure helper (apply_expected_merge / compare_detection_to_gt /
resolve_source_dir / validate_gt_document) は unit でも検証する。

PR #915 review 反映:

- F16: expected_merge_with_next の連鎖 (3 個以上) を silent に取りこぼさず畳む
- F17a: inclusive_slack_sec を GT 必須 field 化 (harness / 関数の silent
  default を廃止し、per-source に締める設計を実際に機能させる)
- F17b: source_size_bytes を slow gate で実ファイルと照合 (不一致は skip では
  なく fail。同名別ファイルで GT が silent にずれるのを防ぐ)
- F18: gyawa も env var 経路 (絶対 path 直書き廃止)。VOD 不在時の skip は
  ALLAGANEYE_VTUBER_GT_REQUIRE_ALL=1 で fail に格上げでき、
  「6 source gate が silent に 5 source へ縮退」を検出できる
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

_GT_DIR = Path(__file__).parent / "baselines" / "v0.3.0" / "vtuber-gt"

# source_dir_label -> (env var, default dir)。
# gyawa も他 5 source と同じく env var で切替可能にする (F18)。
_SOURCE_ROOTS: dict[str, tuple[str, str]] = {
    "vtuber-samples": ("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER", "E:/allaganeye-samples"),
    "gyawa_vatos": ("ALLAGANEYE_SAMPLE_VIDEO_DIR_GYAWA", "E:/videos/gyawa_vatos"),
}

# 受け入れ条件「6 source」の SSoT。GT が消えた / rename された場合に
# parametrize が空になって gate が 0 件で緑になる事故を検出する。
_EXPECTED_GT_STEMS = frozenset(
    {"gyawa", "kyuma", "meteor", "shikke", "shinryu", "shirurori"}
)

_REQUIRED_GT_FIELDS = (
    "source_file",
    "source_size_bytes",
    "source_dir_label",
    "source_env_var",
    "tolerance_sec",
    "inclusive_slack_sec",
    "matches",
)

_REQUIRED_MATCH_FIELDS = ("index", "start_time", "end_time", "type")

_REQUIRE_ALL_ENV = "ALLAGANEYE_VTUBER_GT_REQUIRE_ALL"

_FALSE_LITERALS = frozenset({"", "0", "false", "no", "off"})


def env_flag(environ: Mapping[str, str], name: str) -> bool:
    """env var の真偽解釈 (未設定 / 空 / 0 / false / no / off は False)。"""
    return environ.get(name, "").strip().lower() not in _FALSE_LITERALS


def apply_expected_merge(matches: list[dict]) -> list[dict]:
    """GT matches の expected_merge_with_next: true を適用して合成 GT match 列を返す。

    expected_merge_with_next=true の match は次の match と合成する:

    - start = 連鎖先頭 match の start_time
    - end = 連鎖末尾 match の end_time
    - index / その他 field = 連鎖先頭 match のもの
    - merged_indices = 合成に使った index 列 (合成が起きた entry にのみ付く)

    連鎖 (次 match にも flag がある) は**すべて 1 entry に畳む**。旧実装は
    `i += 2` で次 match の flag を読まずに飛ばしていたため、3 連鎖の注釈が
    silent に 2 entry へ化けて GT が実質書き換わっていた (PR #915 F16)。
    GT は検証の正なので silent な書換は許容しない。

    末尾 match に expected_merge_with_next=true が付いている場合は ValueError。
    """
    result: list[dict] = []
    i = 0
    n = len(matches)
    while i < n:
        head = matches[i]
        last = i
        while matches[last].get("expected_merge_with_next"):
            if last + 1 >= n:
                raise ValueError(
                    f"expected_merge_with_next=true on last match "
                    f"(index {matches[last]['index']}); annotation error"
                )
            last += 1
        merged = dict(head)
        if last > i:
            merged["end_time"] = matches[last]["end_time"]
            # 合成済み entry に flag を残すと「まだ merge 待ち」に見えるため落とす
            merged.pop("expected_merge_with_next", None)
            merged["merged_indices"] = [m["index"] for m in matches[i : last + 1]]
        result.append(merged)
        i = last + 1
    return result


def compare_detection_to_gt(
    detected: list[dict],
    gt_matches: list[dict],
    tolerance_sec: float,
    *,
    inclusive_slack_sec: float,
) -> dict:
    """segment と GT の 1:1 (overlap 最大対応)、非対称 tolerance gate 付き。

    製品 invariant = 「試合内容の損失ゼロ」を直接符号化する非対称判定:

    - 損失方向 (start が GT より遅い = 頭欠け / end が GT より早い = 尻切れ):
      tolerance_sec (15s) で厳格に判定する。
    - 余分方向 (start が GT より早い = ロビー混入 / end が GT より遅い = result
      混入): inclusive_slack_sec で bound する。

    inclusive_slack_sec は**必須 keyword** (default なし)。値は GT json の
    top-level `inclusive_slack_sec` から渡す。default を持たせると、GT json に
    field が無いまま全 source が暗黙値で走り「per-source に締める設計」が
    dead field 化する (PR #915 F17a の再発防止)。

    設計判断 (2026-07-22 Idios 承認): +-tolerance_sec の対称 gate では
    無害な余分方向が 7 周の改善でもゼロにならず、有害方向 (損失) のみ
    厳格化が製品 invariant (試合内容の損失ゼロ) に一致する。

    start_err = det_start - gt_start (正 = 遅い = 損失方向)
    end_err   = det_end   - gt_end   (負 = 早い = 損失方向)

    violations: 判定違反の cell リスト。各要素は dict:
      {"index": gt_index, "start_err": float, "end_err": float, "direction": str}
    direction は "start_loss" / "start_excess" / "end_loss" / "end_excess" の
    最初の違反方向 (複数違反時は start_loss 優先)。

    max_abs_error: 後方互換のため残す (asymmetric gate とは独立)。
    """
    unmatched_det = list(range(len(detected)))
    matched_pairs: list[tuple[int, int]] = []
    for gi, g in enumerate(gt_matches):
        best = None
        for di in unmatched_det:
            d = detected[di]
            ov = min(d["end_time"], g["end_time"]) - max(
                d["start_time"], g["start_time"]
            )
            if ov > 0 and (best is None or ov > best[1]):
                best = (di, ov)
        if best is not None:
            matched_pairs.append((gi, best[0]))
            unmatched_det.remove(best[0])
    missed = [
        g["index"]
        for gi, g in enumerate(gt_matches)
        if gi not in [p[0] for p in matched_pairs]
    ]
    spurious = [detected[di]["start_time"] for di in unmatched_det]
    errors = []
    violations = []
    for gi, di in matched_pairs:
        g, d = gt_matches[gi], detected[di]
        start_err = d["start_time"] - g["start_time"]
        end_err = d["end_time"] - g["end_time"]
        errors.append((g["index"], start_err, end_err))
        # 非対称判定: 損失方向 = tolerance_sec 厳格 / 余分方向 = inclusive_slack_sec bound
        direction = None
        if start_err > tolerance_sec:
            direction = "start_loss"
        elif start_err < -inclusive_slack_sec:
            direction = "start_excess"
        elif end_err < -tolerance_sec:
            direction = "end_loss"
        elif end_err > inclusive_slack_sec:
            direction = "end_excess"
        if direction is not None:
            violations.append(
                {
                    "index": g["index"],
                    "start_err": start_err,
                    "end_err": end_err,
                    "direction": direction,
                }
            )
    max_abs = max((max(abs(ds), abs(de)) for _, ds, de in errors), default=0.0)
    return {
        "matched": len(matched_pairs),
        "missed": missed,
        "spurious": spurious,
        "boundary_errors": errors,
        "max_abs_error": max_abs,
        "violations": violations,
    }


def resolve_source_dir(gt: Mapping[str, Any], environ: Mapping[str, str]) -> Path:
    """GT の source_dir_label / source_env_var から source dir を解決する。

    label ごとに (env var, default dir) を保持し、GT json の source_env_var が
    label の期待値と一致しなければ ValueError にする (絶対 path 直書き /
    source_env_var: null の再発を config drift として弾く、F18)。
    """
    label = gt.get("source_dir_label")
    if not isinstance(label, str) or label not in _SOURCE_ROOTS:
        raise ValueError(
            f"unknown source_dir_label {label!r}; known: {sorted(_SOURCE_ROOTS)}"
        )
    env_var, default_dir = _SOURCE_ROOTS[label]
    declared = gt.get("source_env_var")
    if declared != env_var:
        raise ValueError(
            f"source_env_var {declared!r} does not match source_dir_label "
            f"{label!r} (expected {env_var!r}); GT must be relocatable via env var"
        )
    return Path(environ.get(env_var) or default_dir)


def validate_gt_document(gt: Mapping[str, Any]) -> None:
    """GT json の schema / invariant を検証する (違反は ValueError)。

    GT は検証の正なので、harness が読む前提 (必須 field / 単調増加で非重複な
    match / 1-origin 連番 index / merge 注釈の妥当性) を明示的に gate する。
    """
    missing = [f for f in _REQUIRED_GT_FIELDS if f not in gt]
    if missing:
        raise ValueError(f"GT json missing required field(s): {missing}")

    source_file = gt["source_file"]
    if not isinstance(source_file, str) or not source_file.strip():
        raise ValueError(f"source_file must be a non-empty str, got {source_file!r}")

    size = gt["source_size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError(f"source_size_bytes must be a positive int, got {size!r}")

    for name in ("tolerance_sec", "inclusive_slack_sec"):
        value = gt[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"{name} must be a positive number, got {value!r}")

    # label / env var 整合 (環境非依存に検証したいので空 environ で解決する)
    resolve_source_dir(gt, {})

    matches = gt["matches"]
    if not isinstance(matches, list) or not matches:
        raise ValueError(f"matches must be a non-empty list, got {type(matches)}")
    prev_end: float | None = None
    for pos, m in enumerate(matches):
        if not isinstance(m, dict):
            raise ValueError(f"matches[{pos}] must be an object, got {m!r}")
        missing_keys = [k for k in _REQUIRED_MATCH_FIELDS if k not in m]
        if missing_keys:
            raise ValueError(f"matches[{pos}] missing field(s): {missing_keys}")
        if m["index"] != pos + 1:
            raise ValueError(
                f"matches[{pos}] index {m['index']!r} is not 1-origin sequential "
                f"(expected {pos + 1})"
            )
        start = float(m["start_time"])
        end = float(m["end_time"])
        if start >= end:
            raise ValueError(
                f"matches[{pos}] start_time {start} must be < end_time {end}"
            )
        if prev_end is not None and start <= prev_end:
            raise ValueError(
                f"matches[{pos}] start_time {start} overlaps previous end_time "
                f"{prev_end} (GT must be sorted and disjoint)"
            )
        prev_end = end
        flag = m.get("expected_merge_with_next", False)
        if not isinstance(flag, bool):
            raise ValueError(
                f"matches[{pos}] expected_merge_with_next must be bool, got {flag!r}"
            )
    # merge 注釈の妥当性 (末尾 flag 等) を fast test の段階で暴く
    apply_expected_merge(list(matches))


def require_gt_source(gt: Mapping[str, Any], environ: Mapping[str, str]) -> Path:
    """GT source VOD を解決し、size 照合まで済ませた Path を返す。

    - label / env var 不整合: ValueError (config drift)
    - VOD 不在: skip。ただし ALLAGANEYE_VTUBER_GT_REQUIRE_ALL が真なら fail
      (「6 source gate」が silent に 5 source へ縮退するのを検出、F18)
    - size 不一致: fail (skip にしない。SHA-256 台帳と別ファイルを掴んだまま
      GT が silent にずれるのを防ぐ、F17b)
    """
    video = resolve_source_dir(gt, environ) / gt["source_file"]
    if not video.is_file():
        msg = f"sample video not found: {video}"
        if env_flag(environ, _REQUIRE_ALL_ENV):
            pytest.fail(
                f"{msg} ({_REQUIRE_ALL_ENV} set; 6 source gate must not degrade)"
            )
        pytest.skip(msg)
    actual_size = video.stat().st_size
    expected_size = gt["source_size_bytes"]
    if actual_size != expected_size:
        pytest.fail(
            f"source size mismatch for {video}: actual {actual_size} != "
            f"GT source_size_bytes {expected_size}. GT は SHA-256 台帳の同一"
            f"ファイルを前提とする (別ファイルなら GT 再検証が必要)"
        )
    return video


def _gt_files():
    return sorted(_GT_DIR.glob("*.json")) if _GT_DIR.exists() else []


def _load_gt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestApplyExpectedMerge:
    def test_no_merge_flags(self):
        matches = [
            {"index": 1, "start_time": 100.0, "end_time": 500.0},
            {"index": 2, "start_time": 600.0, "end_time": 1000.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 2
        assert result[0]["start_time"] == 100.0
        assert result[1]["end_time"] == 1000.0
        assert "merged_indices" not in result[0]

    def test_merge_first_with_next(self):
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
            {"index": 2, "start_time": 600.0, "end_time": 1000.0},
            {"index": 3, "start_time": 1100.0, "end_time": 1500.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 2
        assert result[0]["start_time"] == 100.0
        assert result[0]["end_time"] == 1000.0
        assert result[0]["index"] == 1
        assert result[0]["merged_indices"] == [1, 2]
        assert result[1]["start_time"] == 1100.0

    def test_merge_preserves_original_fields(self):
        matches = [
            {
                "index": 7,
                "start_time": 7714.0,
                "end_time": 8753.0,
                "expected_merge_with_next": True,
                "notes": "test",
            },
            {"index": 8, "start_time": 8812.0, "end_time": 9767.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 1
        assert result[0]["start_time"] == 7714.0
        assert result[0]["end_time"] == 9767.0
        assert result[0]["notes"] == "test"

    def test_merged_entry_drops_flag(self):
        """合成後の entry に expected_merge_with_next を残さない。

        この green が見逃さないもの: flag が残ると「まだ merge 待ち」に見え、
        合成列を再度 apply_expected_merge に通したときに次 entry を巻き込む。
        """
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
            {"index": 2, "start_time": 600.0, "end_time": 1000.0},
            {"index": 3, "start_time": 1100.0, "end_time": 1500.0},
        ]
        once = apply_expected_merge(matches)
        assert "expected_merge_with_next" not in once[0]
        assert apply_expected_merge(once) == once

    def test_three_way_chain_folds_into_one(self):
        """3 連 merge 注釈は 1 entry に畳む (旧 i += 2 は 2 entry に化けた)。

        この green が見逃さないもの: 連鎖を silent に取りこぼす実装は
        len(result) == 2 / end_time == 1000.0 になり本 pin が赤になる (F16)。
        """
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
            {
                "index": 2,
                "start_time": 600.0,
                "end_time": 1000.0,
                "expected_merge_with_next": True,
            },
            {"index": 3, "start_time": 1100.0, "end_time": 1500.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 1
        assert result[0]["index"] == 1
        assert result[0]["start_time"] == 100.0
        assert result[0]["end_time"] == 1500.0
        assert result[0]["merged_indices"] == [1, 2, 3]

    def test_four_way_chain_then_independent_match(self):
        """4 連鎖 + 後続独立 match: 連鎖境界の復帰位置も pin する。"""
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 200.0,
                "expected_merge_with_next": True,
            },
            {
                "index": 2,
                "start_time": 300.0,
                "end_time": 400.0,
                "expected_merge_with_next": True,
            },
            {
                "index": 3,
                "start_time": 500.0,
                "end_time": 600.0,
                "expected_merge_with_next": True,
            },
            {"index": 4, "start_time": 700.0, "end_time": 800.0},
            {"index": 5, "start_time": 900.0, "end_time": 1000.0},
        ]
        result = apply_expected_merge(matches)
        assert [r["index"] for r in result] == [1, 5]
        assert result[0]["start_time"] == 100.0
        assert result[0]["end_time"] == 800.0
        assert result[0]["merged_indices"] == [1, 2, 3, 4]
        assert result[1]["start_time"] == 900.0
        assert result[1]["end_time"] == 1000.0

    def test_merge_last_match_raises(self):
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
        ]
        with pytest.raises(ValueError, match="last match"):
            apply_expected_merge(matches)

    def test_chain_reaching_last_match_raises(self):
        """連鎖の末尾が最終 match の場合も ValueError (silent に打ち切らない)。"""
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
            {
                "index": 2,
                "start_time": 600.0,
                "end_time": 1000.0,
                "expected_merge_with_next": True,
            },
        ]
        with pytest.raises(ValueError, match="index 2"):
            apply_expected_merge(matches)

    def test_empty_matches(self):
        assert apply_expected_merge([]) == []


class TestCompareUnit:
    def test_exact_match(self):
        det = [{"start_time": 100.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        assert r["matched"] == 1 and not r["missed"] and not r["spurious"]
        assert r["max_abs_error"] == 0.0

    def test_missed_and_spurious(self):
        det = [{"start_time": 2000.0, "end_time": 2400.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        assert r["missed"] == [1] and len(r["spurious"]) == 1

    def test_boundary_error_signs(self):
        det = [{"start_time": 90.0, "end_time": 520.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        (_, ds, de) = r["boundary_errors"][0]
        assert ds == -10.0 and de == 20.0

    def test_one_to_one_matching(self):
        # 1 が 2 GT を二重 match しない
        det = [{"start_time": 100.0, "end_time": 900.0}]
        gt = [
            {"index": 1, "start_time": 100.0, "end_time": 400.0},
            {"index": 2, "start_time": 500.0, "end_time": 900.0},
        ]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        assert r["matched"] == 1 and len(r["missed"]) == 1


class TestAsymmetricTolerance:
    """非対称 tolerance: 損失方向 tolerance_sec 厳格 / 余分方向 inclusive_slack_sec bound。

    設計判断 (2026-07-22 Idios 承認): +-15s 対称では無害な余分方向が
    7 周の改善でもゼロにならず、有害方向 (損失) のみ厳格化が
    製品 invariant (試合内容の損失ゼロ) に一致する。

    start_err = det_start - gt_start (正 = 遅い = 頭欠け = 損失方向)
    end_err = det_end - gt_end (負 = 早い = 尻切れ = 損失方向)
    """

    def test_loss_direction_start_16s_fails(self):
        """start が GT より 16s 遅い (頭欠け) -> tolerance=15s 超 -> violations あり。"""
        det = [{"start_time": 116.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        assert len(r["violations"]) == 1
        v = r["violations"][0]
        assert v["index"] == 1
        assert v["direction"] == "start_loss"
        assert v["start_err"] == pytest.approx(16.0)

    def test_excess_direction_start_250s_passes(self):
        """start が GT より 250s 早い (ロビー混入) -> inclusive_slack=300s 以内 -> violations なし。"""
        det = [{"start_time": -150.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        # start_err = -150 - 100 = -250 -> |excess|=250 < 300 -> pass
        assert not r["violations"]

    def test_excess_direction_start_301s_fails(self):
        """start が GT より 301s 早い -> inclusive_slack=300s 超 -> violations あり。"""
        det = [{"start_time": -201.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        # start_err = -201 - 100 = -301 -> excess 301 > 300 -> violation
        assert len(r["violations"]) == 1
        v = r["violations"][0]
        assert v["direction"] == "start_excess"

    def test_tighter_slack_is_actually_applied(self):
        """per-source に締めた slack が効く (GT の値が判定を動かすことの pin)。

        この green が見逃さないもの: inclusive_slack_sec を無視して定数
        300.0 で判定する実装は、同じ入力で violations なしになり赤になる。
        """
        det = [{"start_time": 40.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        assert not compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)[
            "violations"
        ]
        tight = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=30.0)
        assert [v["direction"] for v in tight["violations"]] == ["start_excess"]

    def test_inclusive_slack_has_no_silent_default(self):
        """inclusive_slack_sec 省略は TypeError (silent default の再導入防止、F17a)。

        この green が見逃さないもの: default が復活すると GT json の
        per-source 設定が dead field に戻り、全 source が暗黙値で走る。
        """
        fn: Callable[..., dict] = compare_detection_to_gt
        with pytest.raises(TypeError):
            fn([], [], 15.0)

    def test_violations_empty_on_exact_match(self):
        det = [{"start_time": 100.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        assert not r["violations"]

    def test_max_abs_error_still_present_for_backward_compat(self):
        """max_abs_error は後方互換で残る。"""
        det = [{"start_time": 90.0, "end_time": 520.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0, inclusive_slack_sec=300.0)
        assert "max_abs_error" in r
        assert r["max_abs_error"] == pytest.approx(20.0)


class TestEnvFlag:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
    def test_truthy(self, value):
        assert env_flag({_REQUIRE_ALL_ENV: value}, _REQUIRE_ALL_ENV)

    @pytest.mark.parametrize("value", ["", "0", "false", "No", "off"])
    def test_falsy(self, value):
        assert not env_flag({_REQUIRE_ALL_ENV: value}, _REQUIRE_ALL_ENV)

    def test_unset(self):
        assert not env_flag({}, _REQUIRE_ALL_ENV)


def _gt_stub(name: str = "clip.mp4", size: int = 3) -> dict:
    """unit test 用の最小 GT document (source dir は env var 経由で差し替える)。"""
    return {
        "source_file": name,
        "source_size_bytes": size,
        "source_dir_label": "vtuber-samples",
        "source_env_var": "ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER",
        "tolerance_sec": 15,
        "inclusive_slack_sec": 300.0,
        "matches": [
            {"index": 1, "start_time": 1.0, "end_time": 2.0, "type": "fl_match"}
        ],
    }


class TestResolveSourceDir:
    def test_env_var_overrides_default(self):
        gt = {
            "source_dir_label": "vtuber-samples",
            "source_env_var": "ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER",
        }
        env = {"ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER": "X:/override"}
        assert resolve_source_dir(gt, env) == Path("X:/override")

    def test_default_used_when_env_unset(self):
        gt = {
            "source_dir_label": "gyawa_vatos",
            "source_env_var": "ALLAGANEYE_SAMPLE_VIDEO_DIR_GYAWA",
        }
        assert resolve_source_dir(gt, {}) == Path("E:/videos/gyawa_vatos")

    def test_gyawa_honours_env_var(self):
        """gyawa も env var で切替できる (絶対 path 直書きの再発防止、F18)。

        この green が見逃さないもの: harness が label を見て
        Path("E:/videos/gyawa_vatos") を直書きする実装は override を
        無視するため本 pin が赤になる。
        """
        gt = {
            "source_dir_label": "gyawa_vatos",
            "source_env_var": "ALLAGANEYE_SAMPLE_VIDEO_DIR_GYAWA",
        }
        env = {"ALLAGANEYE_SAMPLE_VIDEO_DIR_GYAWA": "Y:/elsewhere"}
        assert resolve_source_dir(gt, env) == Path("Y:/elsewhere")

    def test_null_env_var_rejected(self):
        gt = {"source_dir_label": "gyawa_vatos", "source_env_var": None}
        with pytest.raises(ValueError, match="source_env_var"):
            resolve_source_dir(gt, {})

    def test_unknown_label_rejected(self):
        gt = {"source_dir_label": "mystery", "source_env_var": "SOMETHING"}
        with pytest.raises(ValueError, match="unknown source_dir_label"):
            resolve_source_dir(gt, {})


class TestRequireGtSource:
    """slow gate の VOD 解決 / size 照合の wiring を実 pytest outcome で検証する。

    この green が見逃さないもの: skip と fail の取り違え。verdict を返す
    純関数ではなく pytest.skip / pytest.fail を実際に投げる関数を pin して
    いるため、「不一致を skip で握り潰す」実装は赤になる (F17b / F18)。
    """

    def _env(self, tmp_path: Path, **extra: str) -> dict[str, str]:
        return {"ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER": str(tmp_path), **extra}

    def _no_skip(self, gt: Mapping[str, Any], environ: Mapping[str, str]) -> Path:
        """skip 縮退を AssertionError に変換して require_gt_source を呼ぶ。

        この green が見逃さないもの: fail の代わりに skip を投げる実装だと
        Skipped が pytest.raises を素通りして pin test 自体が「skipped」で
        報告され、赤にならない (skip は緑扱いなので silent 縮退が残る)。
        """
        try:
            return require_gt_source(gt, environ)
        except pytest.skip.Exception as exc:
            raise AssertionError(f"unexpected skip instead of fail: {exc}") from exc

    def test_returns_path_when_size_matches(self, tmp_path):
        (tmp_path / "clip.mp4").write_bytes(b"abc")
        gt = _gt_stub(size=3)
        assert self._no_skip(gt, self._env(tmp_path)) == tmp_path / "clip.mp4"

    def test_size_mismatch_fails_not_skips(self, tmp_path):
        (tmp_path / "clip.mp4").write_bytes(b"abcd")
        gt = _gt_stub(size=3)
        with pytest.raises(pytest.fail.Exception, match="source size mismatch"):
            self._no_skip(gt, self._env(tmp_path))

    def test_missing_video_skips_by_default(self, tmp_path):
        gt = _gt_stub()
        with pytest.raises(pytest.skip.Exception, match="sample video not found"):
            require_gt_source(gt, self._env(tmp_path))

    def test_missing_video_fails_when_require_all_set(self, tmp_path):
        gt = _gt_stub()
        env = self._env(tmp_path, **{_REQUIRE_ALL_ENV: "1"})
        with pytest.raises(pytest.fail.Exception, match="must not degrade"):
            self._no_skip(gt, env)


class TestGtCorpus:
    """GT ファイル群そのものを fast test で gate する。"""

    def test_expected_sources_present(self):
        """6 source 分の GT が揃っている。

        この green が見逃さないもの: GT dir ごと消えた / rename された場合、
        _gt_files() が空になり parametrize が 0 件で「緑」になる事故
        (silent な source 縮退、F18 と同型)。
        """
        assert _GT_DIR.is_dir(), f"GT dir missing: {_GT_DIR}"
        stems = {p.stem for p in _gt_files()}
        assert _EXPECTED_GT_STEMS <= stems, (
            f"missing GT source(s): {sorted(_EXPECTED_GT_STEMS - stems)}"
        )

    @pytest.mark.parametrize("gt_path", _gt_files(), ids=lambda p: p.stem)
    def test_gt_document_is_valid(self, gt_path):
        """必須 field / match invariant / merge 注釈を検証する。"""
        validate_gt_document(_load_gt(gt_path))

    @pytest.mark.parametrize("gt_path", _gt_files(), ids=lambda p: p.stem)
    def test_source_dir_is_env_switchable(self, gt_path):
        """全 GT が env var 経由で dir 切替できる (gyawa 含む、F18)。"""
        gt = _load_gt(gt_path)
        env_var, _default = _SOURCE_ROOTS[gt["source_dir_label"]]
        assert resolve_source_dir(gt, {env_var: "Z:/relocated"}) == Path("Z:/relocated")


class TestValidateGtDocument:
    def test_accepts_stub(self):
        validate_gt_document(_gt_stub())

    @pytest.mark.parametrize("field", _REQUIRED_GT_FIELDS)
    def test_missing_required_field_rejected(self, field):
        gt = _gt_stub()
        gt.pop(field)
        with pytest.raises(ValueError, match=field):
            validate_gt_document(gt)

    def test_zero_source_size_rejected(self):
        gt = _gt_stub()
        gt["source_size_bytes"] = 0
        with pytest.raises(ValueError, match="source_size_bytes"):
            validate_gt_document(gt)

    def test_non_positive_inclusive_slack_rejected(self):
        gt = _gt_stub()
        gt["inclusive_slack_sec"] = 0
        with pytest.raises(ValueError, match="inclusive_slack_sec"):
            validate_gt_document(gt)

    def test_overlapping_matches_rejected(self):
        gt = _gt_stub()
        gt["matches"] = [
            {"index": 1, "start_time": 0.0, "end_time": 100.0, "type": "fl_match"},
            {"index": 2, "start_time": 50.0, "end_time": 200.0, "type": "fl_match"},
        ]
        with pytest.raises(ValueError, match="overlaps"):
            validate_gt_document(gt)

    def test_non_sequential_index_rejected(self):
        gt = _gt_stub()
        gt["matches"] = [
            {"index": 3, "start_time": 0.0, "end_time": 100.0, "type": "fl_match"},
        ]
        with pytest.raises(ValueError, match="1-origin"):
            validate_gt_document(gt)

    def test_trailing_merge_flag_rejected(self):
        gt = _gt_stub()
        gt["matches"] = [
            {
                "index": 1,
                "start_time": 0.0,
                "end_time": 100.0,
                "type": "fl_match",
                "expected_merge_with_next": True,
            },
        ]
        with pytest.raises(ValueError, match="last match"):
            validate_gt_document(gt)

    def test_inverted_match_rejected(self):
        gt = _gt_stub()
        gt["matches"] = [
            {"index": 1, "start_time": 100.0, "end_time": 100.0, "type": "fl_match"},
        ]
        with pytest.raises(ValueError, match="must be <"):
            validate_gt_document(gt)


@pytest.mark.slow
@pytest.mark.slow_detect
@pytest.mark.parametrize("gt_path", _gt_files(), ids=lambda p: p.stem)
def test_vtuber_gt_match(gt_path, tmp_path):
    """VOD で --vtuber detect し GT と突合 (matched/missed/spurious + 非対称 tolerance)。"""
    gt = _load_gt(gt_path)
    validate_gt_document(gt)
    gt_matches = apply_expected_merge(gt["matches"])
    # dir 解決 (env var 経由) / 実在確認 / source_size_bytes 照合をまとめて実施
    video = require_gt_source(gt, os.environ)
    out = tmp_path / gt_path.stem
    env = {**os.environ, "PYTHONUTF8": "1", "ALLAGANEYE_INTEGRITY_SKIP": "1"}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "detect",
            str(video),
            "--vtuber",
            "--no-cache",
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        env=env,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    # 非対称 tolerance: GT json の必須 field をそのまま渡す (default fallback なし)
    result = compare_detection_to_gt(
        meta["matches"],
        gt_matches,
        float(gt["tolerance_sec"]),
        inclusive_slack_sec=float(gt["inclusive_slack_sec"]),
    )
    assert result["matched"] == len(gt_matches), result
    assert not result["missed"] and not result["spurious"], result
    # 非対称 gate: violations リストで per-cell 判定 (損失方向 tolerance_sec / 余分方向 inclusive_slack_sec)
    assert not result["violations"], result["violations"]
