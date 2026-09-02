"""masked baseline corpus のメタ検証 (fast、#925)。

slow の回帰 gate (`test_masked_baseline_regression.py`) は実動画必須のため通常 CI から
deselect される。baseline / GT ファイルの欠落や schema 破損は **この fast test が常に
CI で守る** (vtuber GT harness の `_EXPECTED_GT_STEMS` guard と同じ「parametrize が空で
緑になる事故」の防止)。slow gate はファイル存在を前提にできる。
"""

import json
from pathlib import Path

_BASELINE_DIR = (
    Path(__file__).resolve().parent.parent / "tests" / "baselines" / "v0.3.0"
)
_GT_DIR = _BASELINE_DIR / "masked-gt"

# test_masked_baseline_regression.py の _EXPECTED_BASELINE_STEMS と一致させること
# (masked 録画 2 本 = 受け入れ条件)。追加以降は両ファイルの集合を同時に更新する。
_EXPECTED_STEMS = frozenset({"masked-20260527", "masked-20260529"})

_GT_REQUIRED_FIELDS = (
    "source_file",
    "source_size_bytes",
    "source_dir_label",
    "source_env_var",
    "detect_command",
    "masked_fallback_used",
    "adjudicated_at",
    "adjudicated_by",
    "matches",
)


def test_masked_baseline_set_is_complete() -> None:
    """baseline metadata + GT が期待集合どおり存在する (欠落は構造エラー)。

    slow gate は parametrize が空だと 0 件で緑になるため、ファイル存在をこちらで
    hard gate する (split baseline #992 と同じ「silent 縮退」防止)。
    """
    baseline_stems = {
        p.name.removesuffix(".metadata.json")
        for p in _BASELINE_DIR.glob("masked-*.metadata.json")
    }
    assert baseline_stems == _EXPECTED_STEMS, (
        f"masked baseline が期待集合と不一致: {sorted(baseline_stems)} != "
        f"{sorted(_EXPECTED_STEMS)}"
    )
    gt_stems = {p.stem for p in _GT_DIR.glob("masked-*.json")}
    assert gt_stems == _EXPECTED_STEMS, (
        f"masked GT が期待集合と不一致: {sorted(gt_stems)} != {sorted(_EXPECTED_STEMS)}"
    )


def test_masked_gt_documents_are_valid() -> None:
    """GT json の schema / invariant を検証する (目視裁定の記録としての正)。"""
    for stem in sorted(_EXPECTED_STEMS):
        gt = json.loads((_GT_DIR / f"{stem}.json").read_text(encoding="utf-8"))
        missing = [f for f in _GT_REQUIRED_FIELDS if not gt.get(f)]
        assert not missing, f"{stem}.json: 必須 field 欠落/空: {missing}"
        assert gt["source_size_bytes"] > 0, f"{stem}.json: source_size_bytes"
        matches = gt["matches"]
        assert isinstance(matches, list) and matches, f"{stem}.json: matches empty"
        prev_end = None
        for pos, m in enumerate(matches):
            assert m["index"] == pos + 1, f"{stem}.json: index 不連続 (pos {pos})"
            start, end = float(m["start_time"]), float(m["end_time"])
            assert start < end, f"{stem}.json: match {pos} 反転"
            if prev_end is not None:
                assert start > prev_end, f"{stem}.json: match {pos} が前 match と重複"
            prev_end = end


def test_masked_baseline_matches_gt_counts() -> None:
    """pin baseline の matches 数 == GT matches 数 (baseline と目視裁定の対応)。

    bit-exact gate は baseline との一致のみを見るため、baseline 自体が GT と食い違う
    (例: 目視裁定後に検出を変えたのに baseline を更新し忘れた) と slow gate は緑のまま
    正しさの根拠が腐る。ここで count を束ねて腐りを検出する。
    """
    for stem in sorted(_EXPECTED_STEMS):
        meta = json.loads(
            (_BASELINE_DIR / f"{stem}.metadata.json").read_text(encoding="utf-8")
        )
        gt = json.loads((_GT_DIR / f"{stem}.json").read_text(encoding="utf-8"))
        assert len(meta["matches"]) == len(gt["matches"]), (
            f"{stem}: baseline matches {len(meta['matches'])} != GT {len(gt['matches'])}"
        )
