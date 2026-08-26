"""``metadata.schema.json`` の散文契約と path sandbox の pin test (#934).

PR #930 で修正した 3 件のバグ (出力パス表示の相対化 / ``--name-pattern`` の sandbox
欠落 / metadata ``source`` の相対パス書き込み) は、いずれも「散文でしか書かれていない
契約」に依存していたために作り込まれた。契約の正を散文からテストへ移し、レビュアの
注意力に依存しないようにする。

要因分析 (session ``pensive-satoshi-3397b0``) の F6「機械可読ファイルの中の散文が最も
強く偽の安心を生む」/ F7「標準 fixture がきれいな入力しか供給しない」に対応する。

**検査しているのは下記 :data:`PROSE_CONTRACTS` の 9 件だけで、これ以外は未検査である。**
意図的に検査しないと判断したものは :data:`UNCHECKED_PROSE` に理由付きで列挙してある
(空白を「検査した結果ゼロ」と読み違えないため)。

issue #934 は対象を「7 件」と書いているが、実際に棚卸しすると **9 件**になった:

* ``detection-window-ordered`` (completed >= started) -- ``detection_completed_at`` の
  description が **書式の主張 (ISO 8601 UTC) と順序の主張 (elapsed = completed - started)
  の 2 つ**を 1 文に抱えている。フィールド単位で数えると 1 件、契約単位では 2 件。片方だけ
  検査して「completed_at は検査済み」とすると順序の主張が無検査のまま残るので分けた
* ``warnings-always-emitted`` -- 下記の sweep で見つけた棚卸し漏れ

**棚卸し漏れへの対策**: 「棚卸しが人手だから漏れは構造的に検査外」で終わらせず、
:func:`test_no_unclassified_contract_prose` が schema 全体を走査し、契約を示唆する語
(:data:`CONTRACT_SIGNAL_WORDS`) を含む description が :data:`PROSE_CONTRACTS` か
:data:`UNCHECKED_PROSE` のどちらかに必ず現れることを強制する。schema に契約めいた散文を
足して分類し忘れたら red になる。**ただしこれは完全性の保証ではない** -- signal word に
引っかからない言い回しの契約は依然として検査外で、そこがこの gate の限界である
(実際、この sweep を入れた時点で未分類が 10 件見つかった)。

もう 1 つの false-green 対策が :func:`test_fixture_is_not_vacuous` である。契約の checker は
``matches`` / ``gaps`` / ``output_file`` を走査するループを含むので、fixture が痩せると
「正常系は通る」側が空ループで緑になる。実際、当初の fixture は ``gaps=[]`` で
``gap-interval-ordered`` が 1 度も比較していなかった。

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
    _output_file_field,
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


def _check_warnings_always_emitted(payload: dict[str, Any]) -> None:
    _require(
        isinstance(payload.get("warnings"), list),
        "warnings-always-emitted",
        "New writers always emit a warnings array (possibly empty); "
        f"got {payload.get('warnings')!r}",
    )


def _violate_warnings_always_emitted(payload: dict[str, Any]) -> None:
    del payload["warnings"]


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
    ProseContract(
        id="warnings-always-emitted",
        schema_pointer=("properties", "warnings"),
        statement="New writers always emit an array (possibly empty)",
        check=_check_warnings_always_emitted,
        violate=_violate_warnings_always_emitted,
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
    ("properties", "minimap_regions"): (
        "「Missing entry for a match = not cropped」「Field absent = minimap crop never ran」は"
        "**不在の意味付け**であり、違反状態を構成できない (不在は常に valid)"
    ),
    ("$defs", "DetectionParams", "properties", "vtuber"): (
        "「the VTuber path never auto-triggers, so request equals resolved」は"
        "detector の振る舞いについての主張で、payload 単体からは検証できない。"
        "pin するなら detector 側のテストになるので本ファイルの守備範囲外"
    ),
    ("$defs", "Match"): (
        "「JSON Schema is the strict writer contract / reader-side passthrough は zod」は"
        "schema と zod の分担の説明。writer 側は additionalProperties: false が既に機械化しており、"
        "reader 側 (zod passthrough) は gui/src の TS テストの守備範囲"
    ),
    ("$defs", "MetadataWarning"): (
        "「readers must accept unknown codes」は **reader の義務**であり、"
        "writer が出す payload では違反状態を構成できない"
    ),
    ("$defs", "CaptureRegion", "properties", "source"): (
        "「Documented values」+「Free string: readers must accept unknown values」= "
        "意図的な open enum。閉じた集合として検査すると将来の detector 追加で false-red になる"
    ),
    ("$defs", "CaptureRegions"): (
        "coarse がどの検出器由来かの説明 (OBS は FULL_FRAME 等) は検出経路の記述であり、"
        "payload の形の契約ではない。検出経路の pin は tests/test_capture_region.py 側"
    ),
    (): (
        "root の description は「refine 系の意味制約は zod / InputFileError が持つ」という"
        "**分担の宣言**。そこで名指しされている制約 (end_time >= start_time 等) は"
        "PROSE_CONTRACTS 側で個別に検査しているので、root 自体は再検査しない"
    ),
    ("properties", "gaps"): (
        "「>= 5 minutes」は producer 側の閾値 (min_gap=300.0) であり、正は detector の"
        "gap 抽出とそのテスト。payload から再 assert すると同じ閾値が 2 箇所になる"
    ),
    ("$defs", "Gap"): ("properties/gaps と同一の主張 (min_gap=300.0) の再掲。同上"),
    ("$defs", "Match", "properties", "start_time"): (
        "「>= 0」は minimum: 0 で JSON Schema 側が既に機械化済み。散文ではない"
    ),
}

#: 散文が契約を含むことを示唆する語。この語を含む description は
#: :data:`PROSE_CONTRACTS` か :data:`UNCHECKED_PROSE` のどちらかに必ず現れねばならない
#: (:func:`test_no_unclassified_contract_prose`)。
#: ``>=`` は単語境界を持たないので regex ではなく部分文字列で照合する。
CONTRACT_SIGNAL_WORDS: tuple[str, ...] = (
    "absolute",
    "relative",
    "must ",
    "always ",
    "never ",
    ">=",
    "iso 8601",
    "utc",
)


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
        # **production と同じ形**を渡す。``split_video`` は ``output_dir / match_NNN.mp4``
        # を返すのであって、bare filename ではない。ここで bare を渡すと
        # output-file-relative の checker が「既に整形済みの入力」しか見ず、writer が
        # ディレクトリ付き / 絶対パスを書いても緑のままになる (Codex adversarial-review
        # [high]、要因分析 F7 の「きれいな入力しか供給しない fixture」そのもの)。
        output_files=[tmp_path / "match_001.mp4", tmp_path / "match_002.mp4"],
        # gaps を空にすると gap-interval-ordered の「正常系は通る」側が空ループになり、
        # 何も検査しないまま緑になる (vacuous pass)。非空を渡し、下の
        # _assert_fixture_is_not_vacuous でその前提が将来も崩れないよう固定する。
        gaps=[{"start": 1200.0, "end": 1500.0, "duration": 300.0}],
        system_info=system_info,
    )
    return dict(payload)


# ---------------------------------------------------------------------------
# 棚卸しが schema と乖離していないか
# ---------------------------------------------------------------------------


def test_fixture_is_not_vacuous(tmp_path: Path) -> None:
    """fixture が各 checker の走査対象を **実際に持っている** ことを固定する。

    契約の checker は ``matches`` / ``gaps`` / ``output_file`` を走査するループを含む。
    走査対象が空だと checker は 1 度も比較せずに return し、「正常系は通る」側のテストが
    **何も検査しないまま緑**になる (vacuous pass)。fixture の内容は将来の編集で簡単に
    痩せるので、痩せた瞬間にここで落ちるようにしておく。

    実際、当初の fixture は ``gaps=[]`` で gap-interval-ordered が空ループだった。
    """
    payload = _build_payload(tmp_path)
    assert payload["matches"], "matches が空だと match 系 checker が空ループになる"
    assert payload["gaps"], "gaps が空だと gap-interval-ordered が空ループになる"
    assert all("output_file" in m for m in payload["matches"]), (
        "output_file が無いと output-file-relative が continue で素通りする"
    )
    for field in ("detected_at", "detection_started_at", "detection_completed_at"):
        assert field in payload, (
            f"{field} が無いと UTC checker が早期 return して何も検査しない"
        )


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


def _iter_descriptions(
    node: Any, pointer: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], str]]:
    out: list[tuple[tuple[str, ...], str]] = []
    if isinstance(node, dict):
        description = node.get("description")
        if isinstance(description, str):
            out.append((pointer, description))
        for key, value in node.items():
            if key != "description":
                out.extend(_iter_descriptions(value, (*pointer, key)))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.extend(_iter_descriptions(value, (*pointer, str(i))))
    return out


def test_no_unclassified_contract_prose() -> None:
    """契約を示唆する語を含む description が、必ずどちらかに分類されている。

    棚卸しが人手であること自体は消せないが、**漏れを人手のままにしない**ことはできる。
    schema に契約めいた散文を足したのに :data:`PROSE_CONTRACTS` にも
    :data:`UNCHECKED_PROSE` にも入れなかったら、ここで落ちる。

    これは「棚卸しが完全である」ことの保証ではない。:data:`CONTRACT_SIGNAL_WORDS` に
    引っかからない言い回しの契約は依然として検査外であり、**それがこの gate の限界**である。
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    classified = {c.schema_pointer for c in PROSE_CONTRACTS} | set(UNCHECKED_PROSE)
    unclassified: list[str] = []
    for pointer, description in _iter_descriptions(schema):
        lowered = description.lower()
        if not any(word in lowered for word in CONTRACT_SIGNAL_WORDS):
            continue
        if pointer in classified:
            continue
        unclassified.append(f"{'/'.join(pointer) or '<root>'}: {description[:100]}")
    assert not unclassified, (
        "契約を示唆する散文が棚卸しにも「検査しない」判断にも入っていない:\n"
        + "\n".join(f"- {u}" for u in unclassified)
        + "\nPROSE_CONTRACTS に追加するか、UNCHECKED_PROSE に理由付きで記録すること。"
    )


def test_inventory_size_is_pinned() -> None:
    """棚卸しの件数を固定する。

    増減させるときは module docstring の「8 件」も同時に直すこと。数だけ動いて散文が
    据え置かれると、doc が「棚卸し済み」と主張する範囲と実体が静かにズレる。
    """
    assert len(PROSE_CONTRACTS) == 9, [c.id for c in PROSE_CONTRACTS]


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


def test_output_file_field_normalizes_every_producer_shape(tmp_path: Path) -> None:
    """2 つの producer が渡す形をすべて「metadata.json からの相対」へ揃える (#934)。

    ``split`` は ``split_video`` の戻り値 (``output_dir / match_NNN.mp4``、``-o`` が
    絶対なら絶対) を渡し、``detect`` は bare な placeholder を渡す。素の ``as_posix``
    では前者だけがディレクトリ付き / 絶対になり、**同じフィールドが producer によって
    別の意味になる**。
    """
    out_dir = tmp_path / "out"
    assert _output_file_field(out_dir / "match_001.mp4", out_dir) == "match_001.mp4"
    assert _output_file_field(Path("out/match_001.mp4"), Path("out")) == "match_001.mp4"
    assert (
        _output_file_field(Path("./out/match_001.mp4"), Path("./out"))
        == "match_001.mp4"
    )
    # detect の placeholder は既に output_dir 相対。cwd に再アンカーしない。
    assert _output_file_field(Path("match_001.mp4"), Path("out")) == "match_001.mp4"


def test_output_file_field_does_not_shorten_out_of_tree_paths(tmp_path: Path) -> None:
    """``output_dir`` の外は basename へ縮めない。

    縮めると「存在しない兄弟ファイル」を指す値になり、読み手からは正常に見える。
    CLI からは到達しない枝だが、縮める実装に変えられたらここで落ちる。
    """
    out_dir = tmp_path / "out"
    outside = tmp_path / "elsewhere" / "match_001.mp4"
    result = _output_file_field(outside, out_dir)
    assert result != "match_001.mp4"
    assert ".." in result, result


def test_output_file_field_survives_cross_drive_relpath_failure(tmp_path: Path) -> None:
    """``os.path.relpath`` の ValueError (Windows の異ドライブ) で落ちない。

    この分岐は CLI からは到達しない (``split_video`` は ``output_dir`` からパスを組む)
    が、ここが走る時点で **MP4 は既にディスク上にある**。metadata の書き込みで例外を
    上げると分割結果ごと失う。``relpath`` を直接 monkeypatch して発火させるので、
    Windows でなくても検証できる (実ドライブに依存すると ubuntu CI で skip になる)。
    """
    out_dir = tmp_path / "out"
    target = tmp_path / "match_001.mp4"

    def _raise(*_args: object, **_kwargs: object) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    with patch("allaganeye.commands.split_matches.os.path.relpath", _raise):
        result = _output_file_field(target, out_dir)
    assert result == target.as_posix()


def test_split_and_detect_agree_on_output_file_shape(tmp_path: Path) -> None:
    """絶対 ``-o`` の split と detect の placeholder が同じ形になる。

    #934 の起点。修正前は detect が ``match_001.mp4``、``split -o E:/out`` が
    ``E:/out/match_001.mp4`` を書いており、同じフィールドの意味が producer 依存だった。
    """
    out_dir = tmp_path / "out"
    split_shape = _output_file_field(out_dir / "match_001.mp4", out_dir)
    detect_shape = _output_file_field(Path("match_001.mp4"), out_dir)
    assert split_shape == detect_shape == "match_001.mp4"


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


def test_backslash_traversal_never_escapes_the_output_dir(tmp_path: Path) -> None:
    """``..\\victim.mp4`` は **どのプラットフォームでも出力先の外へ出ない**。

    ``\\`` は Windows では区切りだが POSIX では正当なファイル名文字なので、
    「常に exit 5」は正しい期待値ではない (POSIX では 1 個の変な名前のファイルとして
    output_dir の中に留まるのが正しい)。プラットフォームで期待値を分けて skip すると、
    Python の CI job は ubuntu なので **この経路は CI で一度も検証されない**
    (既存の ``test_pool_rejects_backslash_traversal_pattern`` がその形)。

    そこで期待値を「拒否される」ではなく **不変条件**「拒否されるか、さもなくば
    output_dir の中に留まる」として書く。両プラットフォームで実行でき、どちらでも
    脱出を許さないことを実際に確かめられる。
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    victim = tmp_path / "victim.mp4"
    victim.write_bytes(b"VICTIM")
    try:
        resolved = resolve_export_output_path(
            _export_match(), "..\\victim.mp4", output_dir=out_dir, source_video=source
        )
    except ConfigValidationError:
        return  # Windows: 区切りとして解釈され脱出扱いで拒否される
    assert resolved.resolve().is_relative_to(out_dir.resolve()), resolved
    assert victim.read_bytes() == b"VICTIM"


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


def test_drive_relative_pattern_never_escapes_the_output_dir(tmp_path: Path) -> None:
    """``D:victim.mp4`` は「D: ドライブの current directory 相対」= 出力先の外。

    backslash と同じ理由でプラットフォームごとに期待値が違う (POSIX では ``:`` は
    正当なファイル名文字なので、単に変な名前のファイルとして中に留まるのが正しい)。
    ここでも「拒否される」ではなく不変条件「拒否されるか、さもなくば output_dir の中に
    留まる」を assert し、**skip せずに両プラットフォームで走らせる**。

    **限界を明記しておく**: Python の CI job は ubuntu なので、CI 上で実際に踏まれるのは
    「POSIX では脱出しない」側だけである。Windows 固有の drive-relative 解決が将来壊れても
    CI は緑のままになる。この経路は現状 Windows のローカル実行でしか検証されない。
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    source = tmp_path / "sample.mkv"
    source.write_bytes(b"SRC")
    drive = str(out_dir)[0]
    other = "D" if drive.upper() != "D" else "C"
    try:
        resolved = resolve_export_output_path(
            _export_match(),
            f"{other}:victim.mp4",
            output_dir=out_dir,
            source_video=source,
        )
    except ConfigValidationError:
        return  # Windows: drive-relative として解決され脱出扱いで拒否される
    assert resolved.resolve().is_relative_to(out_dir.resolve()), resolved


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
