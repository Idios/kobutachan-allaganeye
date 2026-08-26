"""``metadata.schema.json`` の散文契約と path sandbox の pin test (#934).

PR #930 で修正した 3 件のバグ (出力パス表示の相対化 / ``--name-pattern`` の sandbox
欠落 / metadata ``source`` の相対パス書き込み) は、いずれも「散文でしか書かれていない
契約」に依存していたために作り込まれた。契約の正を散文からテストへ移し、レビュアの
注意力に依存しないようにする。

要因分析 (session ``pensive-satoshi-3397b0``) の F6「機械可読ファイルの中の散文が最も
強く偽の安心を生む」/ F7「標準 fixture がきれいな入力しか供給しない」に対応する。

**棚卸ししたのは下記 :data:`PROSE_CONTRACTS` の 8 件だけで、これ以外は未検査である。**
意図的に検査しないと判断したものは :data:`UNCHECKED_PROSE` に理由付きで列挙してある
(空白を「検査した結果ゼロ」と読み違えないため)。棚卸し自体が人手なので、棚卸し漏れは
構造的に検査外である。

issue #934 は対象を「7 件」と書いているが、実際に棚卸しすると **8 件**になった。増えた
1 件は ``detection-window-ordered`` (completed >= started) で、``detection_completed_at``
の description が **書式の主張 (ISO 8601 UTC) と順序の主張 (elapsed = completed - started)
の 2 つ**を 1 文に抱えているため、フィールド単位で数えると 1 件、契約単位で数えると 2 件に
なる。片方だけ検査して「completed_at は検査済み」とすると順序の主張が無検査のまま残るので、
契約単位で分けた。

ISO 8601 の 3 件を ``format`` + ``format_assertion`` で schema 側へ機械化できるかは
issue の作業項目だったので実測した。結論は **入れない**:

* ``"format": "date-time"`` を 3 フィールドへ追加して ``scripts/codegen/generate.py --py``
  を回すと ``allaganeye/metadata_types.py`` の差分は **ゼロ** (TypedDict は変わらない)
* ただし CI (``.github/workflows/ci.yml``) は ``gui/src/types/metadata.generated.ts`` の
  drift も検査しており、TS 生成物への影響は別途再生成して確かめる必要がある
* 何より **RFC 3339 の ``date-time`` は任意のオフセットを許すため、契約の「UTC」半分を
  表現できない** (``2026-04-28T09:00:00+09:00`` は format 的に valid)。schema へ入れても
  pin test は依然として必要になる
* さらに ``format`` は既定で annotation 扱いであり、assert させるには全 validator を
  ``FORMAT_CHECKER`` 付きに変える必要がある (別の振る舞い変更)

「何も assert しない宣言を機械可読ファイルへ足す」のは本 issue が潰そうとしている
アンチパターンそのものなので、契約は下記の pin test 側に置く。
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from collections.abc import Callable
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.split_matches import (
    _build_metadata_payload,
    _build_system_info,
)
from allaganeye.config import SplitConfig
from allaganeye.exceptions import ConfigValidationError
from allaganeye.export.pool import ExportMatch, resolve_export_output_path
from allaganeye.export.schema import ExportSummary
from allaganeye.video.detector import MatchBoundary

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "metadata.schema.json"
IS_WINDOWS = os.name == "nt"

runner = CliRunner()


class ContractViolation(AssertionError):
    """散文契約の違反。``contract_id`` でどの契約が落ちたかを一意に示す。"""

    def __init__(self, contract_id: str, detail: str) -> None:
        super().__init__(f"[{contract_id}] {detail}")
        self.contract_id = contract_id


@dataclass(frozen=True)
class ProseContract:
    """JSON Schema で表現できない散文契約 1 件。

    ``schema_pointer`` は契約の出典 (schema 内の位置)。テストが pointer の解決可能性を
    検査するので、schema 側でフィールドが消えたり改名されたら棚卸しが stale になった
    ことに気付ける。
    """

    id: str
    schema_pointer: tuple[str, ...]
    statement: str
    check: Callable[[dict[str, Any]], None]
    violate: Callable[[dict[str, Any]], None]


_UTC_ISO8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _require(condition: bool, contract_id: str, detail: str) -> None:
    if not condition:
        raise ContractViolation(contract_id, detail)


def _check_source_absolute(payload: dict[str, Any]) -> None:
    value = payload["source"]
    _require(
        isinstance(value, str) and os.path.isabs(value),
        "source-absolute",
        f"source must be an absolute path, got {value!r}",
    )


def _check_utc_timestamp(
    field: str, contract_id: str
) -> Callable[[dict[str, Any]], None]:
    def _check(payload: dict[str, Any]) -> None:
        if field not in payload:  # optional field: absence is contractually allowed
            return
        value = payload[field]
        _require(
            isinstance(value, str) and bool(_UTC_ISO8601.match(value)),
            contract_id,
            f"{field} must be an ISO 8601 UTC timestamp ending in 'Z', got {value!r}",
        )

    return _check


def _check_completed_not_before_started(payload: dict[str, Any]) -> None:
    started = payload.get("detection_started_at")
    completed = payload.get("detection_completed_at")
    if not isinstance(started, str) or not isinstance(completed, str):
        return
    _require(
        _parse_utc(completed) >= _parse_utc(started),
        "detection-window-ordered",
        f"detection_completed_at ({completed}) precedes "
        f"detection_started_at ({started}); GUI shows elapsed = completed - started",
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check_match_interval_ordered(payload: dict[str, Any]) -> None:
    for match in payload["matches"]:
        _require(
            match["end_time"] >= match["start_time"],
            "match-interval-ordered",
            f"match #{match['index']} has end_time {match['end_time']} "
            f"< start_time {match['start_time']}",
        )


def _check_gap_interval_ordered(payload: dict[str, Any]) -> None:
    for i, gap in enumerate(payload["gaps"]):
        _require(
            gap["end_time"] >= gap["start_time"],
            "gap-interval-ordered",
            f"gap[{i}] has end_time {gap['end_time']} < start_time {gap['start_time']}",
        )


def _check_output_file_relative(payload: dict[str, Any]) -> None:
    for match in payload["matches"]:
        value = match.get("output_file")
        if value is None:
            continue
        _require(
            not os.path.isabs(value) and not _has_separator(value),
            "output-file-relative",
            f"output_file must be a bare filename relative to the metadata.json "
            f"directory, got {value!r}",
        )


def _has_separator(value: str) -> bool:
    # ``\`` は POSIX では正当な文字だが、metadata.json は Windows で生成されたものを
    # 別 OS が読む可能性があるので、両方の区切りを拒否する。
    return "/" in value or "\\" in value


def _violate_source_absolute(payload: dict[str, Any]) -> None:
    payload["source"] = "videos/sample.mkv"


def _violate_timestamp(field: str) -> Callable[[dict[str, Any]], None]:
    def _violate(payload: dict[str, Any]) -> None:
        # RFC 3339 の date-time としては valid だが UTC ではない = ``format`` では
        # 捕まえられない形を選ぶ (schema 機械化では不十分である実証を兼ねる)。
        payload[field] = "2026-04-28T09:00:00+09:00"

    return _violate


def _violate_completed_before_started(payload: dict[str, Any]) -> None:
    payload["detection_started_at"] = "2026-04-28T00:01:30Z"
    payload["detection_completed_at"] = "2026-04-28T00:00:00Z"


def _violate_match_interval(payload: dict[str, Any]) -> None:
    payload["matches"][0]["end_time"] = payload["matches"][0]["start_time"] - 1.0


def _violate_gap_interval(payload: dict[str, Any]) -> None:
    payload["gaps"] = [
        {
            "start_time": 1200.0,
            "end_time": 900.0,
            "start_display": "20:00",
            "end_display": "15:00",
            "duration": 300.0,
            "duration_display": "5m0s",
        }
    ]


def _violate_output_file_relative(payload: dict[str, Any]) -> None:
    payload["matches"][0]["output_file"] = "../escaped.mp4"


#: 棚卸しした散文契約。**これ以外は未検査** (:data:`UNCHECKED_PROSE` も参照)。
PROSE_CONTRACTS: tuple[ProseContract, ...] = (
    ProseContract(
        id="source-absolute",
        schema_pointer=("properties", "source"),
        statement="Absolute path of the source video file",
        check=_check_source_absolute,
        violate=_violate_source_absolute,
    ),
    ProseContract(
        id="detected-at-utc",
        schema_pointer=("properties", "detected_at"),
        statement="ISO 8601 UTC timestamp of when detection ran",
        check=_check_utc_timestamp("detected_at", "detected-at-utc"),
        violate=_violate_timestamp("detected_at"),
    ),
    ProseContract(
        id="detection-started-at-utc",
        schema_pointer=("properties", "detection_started_at"),
        statement="ISO 8601 UTC wall-clock timestamp captured at the start",
        check=_check_utc_timestamp("detection_started_at", "detection-started-at-utc"),
        violate=_violate_timestamp("detection_started_at"),
    ),
    ProseContract(
        id="detection-completed-at-utc",
        schema_pointer=("properties", "detection_completed_at"),
        statement="ISO 8601 UTC wall-clock timestamp captured immediately before write",
        check=_check_utc_timestamp(
            "detection_completed_at", "detection-completed-at-utc"
        ),
        violate=_violate_timestamp("detection_completed_at"),
    ),
    ProseContract(
        id="detection-window-ordered",
        schema_pointer=("properties", "detection_completed_at"),
        statement="GUI CompleteScreen displays elapsed = completed - started",
        check=_check_completed_not_before_started,
        violate=_violate_completed_before_started,
    ),
    ProseContract(
        id="match-interval-ordered",
        schema_pointer=("$defs", "Match", "properties", "end_time"),
        statement="end_time >= start_time; constraint enforced at runtime",
        check=_check_match_interval_ordered,
        violate=_violate_match_interval,
    ),
    ProseContract(
        id="gap-interval-ordered",
        schema_pointer=("$defs", "Gap", "properties", "end_time"),
        statement="Gap end (>= start_time; constraint enforced at runtime)",
        check=_check_gap_interval_ordered,
        violate=_violate_gap_interval,
    ),
    ProseContract(
        id="output-file-relative",
        schema_pointer=("$defs", "Match", "properties", "output_file"),
        statement="MP4 filename relative to the metadata.json directory",
        check=_check_output_file_relative,
        violate=_violate_output_file_relative,
    ),
)

#: 散文だが **意図的に検査しない** もの。空白を「検査した結果ゼロ」と読み違えないため
#: 理由付きで残す。
UNCHECKED_PROSE: dict[tuple[str, ...], str] = {
    ("properties", "source_duration_display"): (
        "表示書式 (HH:MM:SS / MM:SS) は _format_timestamp の単体テストが直接持っている。"
        "payload 側で再検査すると同じ主張が 2 箇所になる"
    ),
    ("$defs", "Match", "properties", "index"): (
        "1-based ordinal。builder が enumerate(start=1) で生成しており、"
        "順序性は test_metadata_types.py の schema validation (minimum: 1) が押さえる"
    ),
    ("$defs", "Match", "properties", "duration"): (
        "duration == end_time - start_time は builder 内で計算しており、"
        "payload から再計算して突き合わせても builder の式を写すだけになる"
    ),
    ("properties", "schema_version"): (
        "const: '1' で JSON Schema 側が既に機械化済み。散文ではない"
    ),
    ("properties", "capture_regions"): (
        "「Missing entry for a match = not cropped」は不在の意味付けであり、"
        "違反状態を構成できない (不在は常に valid)"
    ),
}


def _resolve_pointer(
    schema: dict[str, Any], pointer: tuple[str, ...]
) -> dict[str, Any]:
    node: Any = schema
    for key in pointer:
        assert key in node, f"schema pointer {'/'.join(pointer)} broke at {key!r}"
        node = node[key]
    return node


def assert_prose_contracts(payload: dict[str, Any]) -> None:
    """棚卸しした散文契約をすべて検査する。最初の違反で :class:`ContractViolation`。"""
    for contract in PROSE_CONTRACTS:
        contract.check(payload)


def _build_payload(tmp_path: Path) -> dict[str, Any]:
    """実 writer (``_build_metadata_payload``) の出力を得る。動画入力は要らない。

    conformance を「CLI 実出力を schema に通す」形で書くと動画入力が必要になり
    ``slow`` marker で default ``pytest`` から外れて独立軸にならない (#934 対応方針)。
    detection を mock した writer 関数の出力を対象にする。
    """
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 60.0, "end": 1200.0, "type": "fl_match"},
        {"start": 1500.0, "end": 2400.0, "type": "unknown"},
    ]
    with patch("allaganeye.system_info.get_gpu_info_lines", return_value=[]):
        system_info = _build_system_info(available_vendors=[], vendor_used=None)
    payload = _build_metadata_payload(
        video_path=tmp_path / "sample.mkv",
        source_duration=7200.0,
        source_fps=60.0,
        detected_at="2026-04-28T00:00:00Z",
        detection_started_at="2026-04-28T00:00:00Z",
        detection_completed_at="2026-04-28T00:01:30Z",
        effective_interval=2.0,
        config=config,
        boundaries=boundaries,
        output_files=[Path("match_001.mp4"), Path("match_002.mp4")],
        gaps=[],
        system_info=system_info,
    )
    return dict(payload)


# ---------------------------------------------------------------------------
# 棚卸しが schema と乖離していないか
# ---------------------------------------------------------------------------


def test_every_contract_pointer_resolves_in_the_schema() -> None:
    """契約の出典が schema に実在する (改名・削除で棚卸しが stale になったら落ちる)。"""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for contract in PROSE_CONTRACTS:
        node = _resolve_pointer(schema, contract.schema_pointer)
        assert "description" in node, (
            f"{contract.id}: {'/'.join(contract.schema_pointer)} に description が無い"
        )


def test_every_unchecked_pointer_resolves_in_the_schema() -> None:
    """「検査しない」判断の対象も実在を確かめる (消えたフィールドの言い訳を残さない)。"""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for pointer in UNCHECKED_PROSE:
        _resolve_pointer(schema, pointer)


def test_contract_ids_are_unique() -> None:
    ids = [c.id for c in PROSE_CONTRACTS]
    assert len(ids) == len(set(ids)), f"contract id が重複している: {ids}"


def test_inventory_size_is_pinned() -> None:
    """棚卸しの件数を固定する。

    増減させるときは module docstring の「8 件」も同時に直すこと。数だけ動いて散文が
    据え置かれると、doc が「棚卸し済み」と主張する範囲と実体が静かにズレる。
    """
    assert len(PROSE_CONTRACTS) == 8, [c.id for c in PROSE_CONTRACTS]


# ---------------------------------------------------------------------------
# 発火実証: 契約ごとに違反を注入して、その契約が落ちることを見る
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract", PROSE_CONTRACTS, ids=lambda c: c.id)
def test_contract_fires_on_injected_violation(
    contract: ProseContract, tmp_path: Path
) -> None:
    """違反を注入したら **その契約が** 落ちる。

    「どれかが落ちた」では不足である。別の契約が巻き添えで落ちているだけなら、
    当の契約は永久に無検査のまま緑になりうる (#844 で摘出された false-green の型)。
    """
    payload = _build_payload(tmp_path)
    assert_prose_contracts(payload)  # 前提: 注入前は通る

    violated = copy.deepcopy(payload)
    contract.violate(violated)

    with pytest.raises(ContractViolation) as excinfo:
        assert_prose_contracts(violated)
    assert excinfo.value.contract_id == contract.id, (
        f"{contract.id} の違反を注入したのに {excinfo.value.contract_id} が落ちた"
    )


@pytest.mark.parametrize("contract", PROSE_CONTRACTS, ids=lambda c: c.id)
def test_contract_checker_passes_on_clean_payload(
    contract: ProseContract, tmp_path: Path
) -> None:
    """checker 単体が正常な payload を落とさない (false-red を防ぐ)。"""
    contract.check(_build_payload(tmp_path))


def test_real_writer_output_satisfies_every_prose_contract(tmp_path: Path) -> None:
    """実 writer の出力が 7 件すべてを満たす。

    これが #372 (metadata.json と cache の source パス形式統一) の解消状態を pin する
    場所でもある -- ``source-absolute`` 契約が writer 出力に対して常に成立する。
    """
    assert_prose_contracts(_build_payload(tmp_path))


def test_writer_absolutizes_a_relative_argv_source(tmp_path: Path, monkeypatch) -> None:
    """相対 argv を渡しても ``source`` は絶対で書かれる (#372 / #930 B2 の pin)。

    これが本 issue の起点になった round-trip 破綻の直接原因だった。``tmp_path`` は常に
    絶対なので、標準の fixture をそのまま使うと「きれいな入力しか通らない」テストになり、
    相対 argv という汚い入力が一度も踏まれない (要因分析 F7)。
    """
    monkeypatch.chdir(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with patch("allaganeye.system_info.get_gpu_info_lines", return_value=[]):
        system_info = _build_system_info(available_vendors=[], vendor_used=None)
    payload = _build_metadata_payload(
        video_path=Path("sample.mkv"),  # cwd 相対の argv 値
        source_duration=100.0,
        source_fps=60.0,
        detected_at="2026-04-28T00:00:00Z",
        detection_started_at="2026-04-28T00:00:00Z",
        detection_completed_at="2026-04-28T00:00:01Z",
        effective_interval=2.0,
        config=config,
        boundaries=[{"start": 0.0, "end": 60.0, "type": "fl_match"}],
        output_files=[Path("match_001.mp4")],
        gaps=[],
        system_info=system_info,
    )
    assert os.path.isabs(payload["source"]), payload["source"]
    assert_prose_contracts(dict(payload))


def test_source_absolute_contract_would_catch_the_930_regression(
    tmp_path: Path,
) -> None:
    """#930 以前の書き方 (argv をそのまま永続化) を再現したら落ちる。

    「契約は書いてあるが誰も検査していない」状態に戻ったことを検出できる、が要点。
    """
    payload = _build_payload(tmp_path)
    payload["source"] = "sample.mkv"  # pre-#930 の書き方
    with pytest.raises(ContractViolation) as excinfo:
        assert_prose_contracts(payload)
    assert excinfo.value.contract_id == "source-absolute"


# ---------------------------------------------------------------------------
# path sandbox を「汚い入力」で固める (P1-2)
# ---------------------------------------------------------------------------


def _export_match() -> ExportMatch:
    return ExportMatch(index=1, start=0.0, end=10.0, type_label="fl_match")


#: 出力ディレクトリの外へ出る / 書込先として不正なパターン。exit 5 (ConfigValidationError)。
DIRTY_PATTERNS_REJECTED: tuple[tuple[str, str], ...] = (
    ("parent-traversal", "../victim.mp4"),
    ("nested-parent-traversal", "sub/../../victim.mp4"),
    ("backslash-traversal", "..\\victim.mp4"),
    ("empty-string", ""),
    ("dot-only", "."),
)


@pytest.mark.parametrize(
    ("label", "pattern"),
    DIRTY_PATTERNS_REJECTED,
    ids=[p[0] for p in DIRTY_PATTERNS_REJECTED],
)
def test_resolver_rejects_dirty_pattern(
    label: str, pattern: str, tmp_path: Path
) -> None:
    """汚い入力が exit 5 相当 (:class:`ConfigValidationError`) で弾かれる。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    with pytest.raises(ConfigValidationError):
        resolve_export_output_path(
            _export_match(), pattern, output_dir=out_dir, source_video=source
        )


def test_resolver_rejects_absolute_pattern(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    victim = tmp_path / "victim.mp4"
    with pytest.raises(ConfigValidationError):
        resolve_export_output_path(
            _export_match(), str(victim), output_dir=out_dir, source_video=source
        )


@pytest.mark.skipif(not IS_WINDOWS, reason="drive-relative パスは Windows 固有の構文")
def test_resolver_rejects_drive_relative_pattern(tmp_path: Path) -> None:
    """``E:foo`` は「E: ドライブの current directory 相対」であって出力先の中ではない。

    CI (ubuntu) では skip されるため、**この経路は Windows でしか検証されない**。
    POSIX では ``E:foo`` は単なるファイル名で、出力先の中に留まるのが正しい挙動である。
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    drive = str(out_dir)[0]
    other = "D" if drive.upper() != "D" else "C"
    with pytest.raises(ConfigValidationError):
        resolve_export_output_path(
            _export_match(),
            f"{other}:victim.mp4",
            output_dir=out_dir,
            source_video=source,
        )


def test_resolver_rejects_pattern_hitting_source_video(tmp_path: Path) -> None:
    """出力が原本へ着弾する形は拒否される (書きながら読むと原本が壊れる)。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = out_dir / "sample.mkv"
    source.write_bytes(b"SRC")
    with pytest.raises(ConfigValidationError):
        resolve_export_output_path(
            _export_match(), "sample.mkv", output_dir=out_dir, source_video=source
        )
    assert source.read_bytes() == b"SRC"


def test_resolver_allows_non_ascii_filename(tmp_path: Path) -> None:
    """非 ASCII のファイル名は **正当** なので通す。

    issue #934 の作業項目は「``..`` / 絶対 / drive-relative / 空文字 / 非 ASCII を渡して
    exit 5 で拒否されることを pin する」と書いているが、非 ASCII をそのまま拒否側に
    倒すのは誤りである。日本語のファイル名は普通に valid で、拒否すれば利用者から見た
    regression になる。ここでは「非 ASCII は通る / 非 ASCII でも脱出は防ぐ」を pin し、
    後者を下のテストで見る。
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    resolved = resolve_export_output_path(
        _export_match(), "試合_{idx:03}.mp4", output_dir=out_dir, source_video=source
    )
    assert resolved.parent == out_dir
    assert "試合" in resolved.name


def test_resolver_rejects_non_ascii_pattern_that_escapes(tmp_path: Path) -> None:
    """非 ASCII を含んでいても、出力先の外へ出る形は拒否される。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    with pytest.raises(ConfigValidationError):
        resolve_export_output_path(
            _export_match(), "../試合.mp4", output_dir=out_dir, source_video=source
        )


def test_dirty_pattern_check_does_not_depend_on_tmp_path_being_absolute(
    tmp_path: Path, monkeypatch
) -> None:
    """出力先を **相対パス** で渡しても sandbox が効く。

    ``tmp_path`` が常に絶対であることに寄りかかったテストは「きれいな入力しか通らない」
    (要因分析 F7)。cwd を移して相対の output_dir を渡し、同じ拒否が起きることを見る。
    """
    (tmp_path / "out").mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigValidationError):
        resolve_export_output_path(
            _export_match(),
            "../victim.mp4",
            output_dir=Path("out"),  # 相対
            source_video=Path("sample.mkv"),  # 相対
        )


# ---------------------------------------------------------------------------
# CLI 境界 (export / minimap) -- 汚い入力が exit 5 で止まり原本が無傷
# ---------------------------------------------------------------------------


def _sandbox_metadata(tmp_path: Path) -> Path:
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SOURCE")
    payload = {
        "schema_version": "1",
        "source": str(source),
        "source_duration": 100.0,
        "source_duration_display": "01:40",
        "detected_at": "2026-04-28T00:00:00Z",
        "detection_params": {
            "sample_interval": 2.0,
            "blackout_threshold": 15,
            "min_match_duration": 60,
            "min_blackout_duration": 1.5,
            "no_audio": False,
            "use_gpu": None,
            "workers": None,
        },
        "matches": [
            {
                "index": 1,
                "start_time": 0.0,
                "end_time": 60.0,
                "start_display": "00:00",
                "end_display": "01:00",
                "duration": 60.0,
                "duration_display": "1m0s",
                "type": "fl_match",
            }
        ],
        "gaps": [],
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def app() -> typer.Typer:
    from allaganeye.cli import app as cli_app

    return cli_app


@pytest.mark.parametrize(
    "pattern",
    ["../victim.mp4", "", "sub/../../victim.mp4"],
    ids=["parent-traversal", "empty-string", "nested-parent-traversal"],
)
def test_export_cli_rejects_dirty_name_pattern(
    app: typer.Typer, tmp_path: Path, pattern: str
) -> None:
    metadata_path = _sandbox_metadata(tmp_path)
    victim = tmp_path / "victim.mp4"
    victim.write_bytes(b"VICTIM")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path / "outdir"),
            "--codec",
            "copy",
            "--name-pattern",
            pattern,
            "--quiet",
        ],
    )
    assert result.exit_code == 5, result.output
    # exit 5 だけを見ると、metadata が読めない等の別理由で落ちても緑になる。
    # 拒否したのが name-pattern の sandbox であることまで確かめる。
    assert "--name-pattern" in result.output, result.output
    assert victim.read_bytes() == b"VICTIM"
    assert "Traceback" not in result.output


def test_export_cli_accepts_clean_name_pattern(
    app: typer.Typer, tmp_path: Path
) -> None:
    """上の拒否テストが「常に exit 5」で緑になっていないことの対。

    正常な pattern では sandbox を通過する (通過後に ffmpeg 起動まで行かないよう
    export_matches を mock する)。
    """
    metadata_path = _sandbox_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path / "outdir"),
                "--codec",
                "copy",
                "--name-pattern",
                "match_{idx:03}.mp4",
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_export.assert_called_once()
