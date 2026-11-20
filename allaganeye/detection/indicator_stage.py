"""KO / ASSIST 検出ステージ (#1141)。

`allaganeye indicators` (単体コマンド) と `allaganeye detect` / `split` の
`--indicators` (パイプライン統合) が共有する本体。**キャリブレーション
-> 走査 -> イベント列** までを担い、metadata.json への書き込みは呼び出し側に
残す。統合経路が境界検出の payload と同じ 1 回の atomic write に載せられる
ようにするため (#1141 受け入れ条件 2)、ここでは 1 バイトも書かない。

呼び出し側の責務:

* 入力 metadata の読み書き / CAS (`--expected-mtime`) / レポート出力
* ``notice`` コールバックの wire 形式への変換 (単体コマンドは
  ``{"type": "progress", ...}``、統合経路は ``ProgressEmitter`` の phase)
* 失敗時の扱い (単体コマンドは exit 4、統合経路は ``warnings`` に記録して続行)

設計上の注意:

* 走査は 0.1 秒刻み (`DEFAULT_INTERVAL`)。連続 KO の更新は 0.15-0.35 秒
  間隔なので、これより粗いと取りこぼす (実測 note 4-9)
* キャリブレーションは**試合区間の中のフレーム**で行う。戦意値ゲージは試合中
  しか出ないので、動画全体から等間隔に抜くと試合外を引いて合意が崩れる
* キャリブレーション不能は黙ってイベント 0 件にしない (例外で落とす)
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Literal

import numpy as np

from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    DetectionError,
    InputFileError,
    VideoProcessingError,
)
from allaganeye.video.frames import HwaccelSpec, iter_gray_frames, resolve_hwaccel
from allaganeye.video.indicator_scan import resolve_scan_workers, scan_detections
from allaganeye.video.indicators import (
    IndicatorEvent,
    IndicatorLayout,
    band_crop_rect,
    calibrate_layout,
    detect_indicator_patch,
    event_to_payload,
    group_detections,
    layout_from_bar_region,
    layout_from_payload,
    layout_to_payload,
    validate_layout_for_frame,
)
from allaganeye.video.refs import load_templates

__all__ = [
    "CALIBRATION_SAMPLES",
    "CLI_DEFAULT_INDICATORS",
    "DEFAULT_INTERVAL",
    "INDICATORS_FAILED_CODE",
    "MIN_INTERVAL",
    "PROGRESS_STEP_SECONDS",
    "IndicatorRun",
    "StageNotice",
    "attach_indicators",
    "calibration_timestamps",
    "detect_indicator_events",
    "resolve_indicator_layout",
    "reuse_indicators",
]

DEFAULT_INTERVAL = 0.1
"""走査間隔 (秒)。note 4-9 の「0.1 秒以下」を既定にする。"""

MIN_INTERVAL = 0.05
"""走査間隔の下限。20 Hz を超える走査は映像の情報量を増やさない。"""

CALIBRATION_SAMPLES = 6
"""キャリブレーションに使うフレーム数 (note 4-3 の 5-10 フレーム)。"""

PROGRESS_STEP_SECONDS = 30.0
"""進捗を出す動画時間の間隔。"""

INDICATORS_FAILED_CODE = "indicators_failed"
"""統合経路 (#1141) でインジケータ検出だけが失敗したときの warning code。"""

CLI_DEFAULT_INDICATORS = True
"""`detect` / `split` の `--indicators` の**既定値**。ここが SSoT (#1141)。

L4 は 0.4.0 の新機能で、ON でも既存ユーザーの行動を壊さない (metadata に
`events[]` が増えるだけ)。コストは 944 秒の録画で約 25 秒 / 2.8 時間で約 4.5 分
(`docs/testing-guide.md` の「KO / ASSIST 走査の実測」節)。

`run_detect` / `run_split` のキーワード引数は **False** を既定にしている
(テストや内部呼び出しが実フレームを読まずに済むように)。CLI はこの定数を
typer の既定値として渡す。"""


@dataclass(frozen=True)
class StageNotice:
    """走査の途中経過。呼び出し側が自分の wire 形式へ変換する。

    * ``kind="calibrating"`` -- 探索領域の自動解決を始めた (キャッシュ無し時のみ)
    * ``kind="layout"`` -- 探索領域が確定した (``layout`` に payload 形)
    * ``kind="progress"`` -- 走査の進捗 (``processed_s`` / ``total_s`` / ``eta_s``)

    ``eta_s`` の算出はここが SSoT (GUI は表示するだけ、#1140)。
    """

    kind: Literal["calibrating", "layout", "progress"]
    layout: dict[str, Any] | None = None
    processed_s: float | None = None
    total_s: float | None = None
    eta_s: float | None = None


@dataclass(frozen=True)
class IndicatorRun:
    """1 回の検出結果 (metadata に書く形)。"""

    layout: dict[str, Any]
    events: list[dict[str, Any]]
    recalibrated: bool = False
    interval: float = DEFAULT_INTERVAL


def calibration_timestamps(
    matches: list[dict[str, Any]],
    *,
    duration: float,
    samples: int = CALIBRATION_SAMPLES,
) -> list[float]:
    """Pick frame timestamps for calibration, preferring in-match moments.

    The battle-fervor gauge only renders during a match, so sampling the whole
    video uniformly pulls in lobby / loading frames where the anchor cannot
    match at all and the consensus collapses.

    Samples are distributed over the **total matched time**, not one per
    match: a recording split into per-match MP4s has exactly one match, and
    ``calibrate_layout`` needs at least two agreeing frames, so "one frame per
    match" would make every single-match file fail calibration.
    """
    usable = [
        match
        for match in matches
        if isinstance(match, dict)
        and isinstance(match.get("start_time"), (int, float))
        and isinstance(match.get("end_time"), (int, float))
        and float(match["end_time"]) > float(match["start_time"])
    ]
    if not usable:
        if duration <= 0:
            return []
        step = duration / (samples + 1)
        return [_inset(0.0, duration, step * (index + 1)) for index in range(samples)]

    spans = [(float(match["start_time"]), float(match["end_time"])) for match in usable]
    if len(spans) >= samples:
        stride = (len(spans) - 1) / (samples - 1) if samples > 1 else 0.0
        chosen = [spans[round(index * stride)] for index in range(samples)]
        return [_inset(start, end, (start + end) / 2) for start, end in chosen]

    total = sum(end - start for start, end in spans)
    timestamps: list[float] = []
    for index in range(samples):
        target = total * (index + 0.5) / samples
        offset = 0.0
        for start, end in spans:
            length = end - start
            if offset + length >= target:
                timestamps.append(_inset(start, end, start + (target - offset)))
                break
            offset += length
    return sorted(set(timestamps))


def _inset(start: float, end: float, timestamp: float, *, margin: float = 0.5) -> float:
    """内側に寄せる: 表示のフェード端や境界フレームを避ける。

    1 秒未満の短い区間では固定 0.5 秒の margin だと全サンプルが中点に潰れる
    (dedupe で 1 フレームになり、2 フレーム以上の合意を要求するキャリブレーションが
    失敗する)。区間長の 1/4 を上限にして、短い区間でも位置が分かれるようにする。
    """
    effective = min(margin, (end - start) / 4)
    return round(min(end - effective, max(start + effective, timestamp)), 3)


def resolve_indicator_layout(
    source: Path,
    payload: dict[str, Any],
    *,
    frame_size: tuple[int, int],
    duration: float,
) -> IndicatorLayout:
    """Calibrate from frames sampled inside the detected matches."""
    timestamps = calibration_timestamps(
        [match for match in payload.get("matches") or [] if isinstance(match, dict)],
        duration=duration,
    )
    frames = []
    for timestamp in timestamps:
        for _, frame in iter_gray_frames(
            source, fps=1.0, frame_size=frame_size, start=timestamp, duration=0.2
        ):
            frames.append(frame)
            break
    layout = calibrate_layout(frames)
    if layout is None:
        raise DetectionError(
            "インジケータの探索領域を解決できませんでした "
            f"({len(frames)} フレームの合意が取れず)。"
            "戦意値ゲージが映っていない録画か、HUD レイアウトが想定外の可能性があります。"
        )
    try:
        validate_layout_for_frame(
            layout, frame_width=frame_size[0], frame_height=frame_size[1]
        )
    except InputFileError as exc:
        # 合意で見つけたアンカーがフレーム端に寄っていて、帯域がはみ出すケース。
        # 入力 metadata の不正ではなく解決失敗なので exit 4 に寄せる。
        raise DetectionError(f"探索領域を解決できませんでした: {exc}") from exc
    return layout


def _match_index(matches: list[dict[str, Any]], timestamp: float) -> int | None:
    for match in matches:
        start = match.get("start_time")
        end = match.get("end_time")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if float(start) <= timestamp <= float(end):
            index = match.get("index")
            if isinstance(index, int):
                return index
    return None


def _event_payload(
    event: IndicatorEvent, matches: list[dict[str, Any]]
) -> dict[str, Any]:
    """内部イベントを wire 形式にする (`HighlightEvent`、#127)。"""
    return event_to_payload(event, match_index=_match_index(matches, event.start))


def _detection_tuple(
    patch: np.ndarray, layout: IndicatorLayout, templates: dict[str, np.ndarray]
) -> tuple[str | None, float]:
    """crop 済みバンド 1 枚を `group_detections` の入力形にする (#1140)。"""
    hit = detect_indicator_patch(patch, layout, templates)
    return (hit.kind, hit.score) if hit is not None else (None, 0.0)


def detect_indicator_events(
    source: Path,
    payload: dict[str, Any],
    *,
    frame_size: tuple[int, int],
    duration: float,
    codec: str | None = None,
    interval: float = DEFAULT_INTERVAL,
    gpu: bool = False,
    region: tuple[float, float, float, float] | None = None,
    recalibrate: bool = False,
    notice: Callable[[StageNotice], None] | None = None,
    progress: Callable[[str], None] | None = None,
    progress_step: float = PROGRESS_STEP_SECONDS,
) -> IndicatorRun:
    """キャリブレーション -> 走査 -> イベント列 (metadata には書かない)。

    ``region`` は自動キャリブレーションを skip する手動指定 (単体コマンドの
    ``--region``)。``payload["indicator_layout"]`` があれば再利用し、
    ``recalibrate`` で無視する。どちらも無ければ試合区間から再解決する。

    ``notice`` は**構造化**進捗 (GUI の wire 形式へ変換する材料)、``progress``
    は人が読む 1 行の診断 (どの経路で layout を決めたか / GPU が使えたか)。
    後者は単体コマンドの stderr 出力をそのまま維持するために分けている。

    GPU デコードは環境依存で落ちる (ドライバ / セッション数 / codec) ため、
    ``gpu=True`` で失敗したら **黙って CPU で 1 回だけ**やり直す (#1151)。
    """
    say = progress if progress is not None else _silent
    matches = [
        match for match in payload.get("matches") or [] if isinstance(match, dict)
    ]
    cached = payload.get("indicator_layout")
    was_recalibrated = False
    if region is not None:
        try:
            layout = layout_from_bar_region(*region)
        except ValueError as exc:
            raise ConfigValidationError(f"--region: {exc}") from exc
        validate_layout_for_frame(
            layout, frame_width=frame_size[0], frame_height=frame_size[1]
        )
        say("using --region (auto calibration skipped)")
    elif isinstance(cached, dict) and not recalibrate:
        layout = layout_from_payload(
            cached, frame_width=frame_size[0], frame_height=frame_size[1]
        )
        validate_layout_for_frame(
            layout, frame_width=frame_size[0], frame_height=frame_size[1]
        )
        say("reused indicator_layout from metadata.json")
    else:
        if notice is not None:
            notice(StageNotice(kind="calibrating"))
        say("resolving indicator layout ...")
        layout = resolve_indicator_layout(
            source, payload, frame_size=frame_size, duration=duration
        )
        was_recalibrated = True

    layout_payload = layout_to_payload(
        layout, frame_width=frame_size[0], frame_height=frame_size[1]
    )
    if notice is not None:
        notice(StageNotice(kind="layout", layout=layout_payload))

    # #1140: 走査はバンドだけを ffmpeg で crop して受け取る (転送量 2 MB -> 数十 KB)。
    # 切り出し座標は検出側 (`band_crop_rect`) と同じ関数から得るので、
    # フルフレーム経路と画素単位で一致する。
    band_crop = band_crop_rect(
        layout, frame_width=frame_size[0], frame_height=frame_size[1]
    )
    templates = load_templates()
    # #1151: ハードウェアデコードは opt-in。vendor 選択と decoder の対応は
    # gpu_detector の表を流用し、使えないときは黙って CPU に倒す。
    hwaccel = resolve_hwaccel(codec) if gpu else None
    if gpu and hwaccel is None:
        say("GPU decode unavailable (no supported GPU / codec); using CPU")
    elif hwaccel is not None:
        say(f"GPU decode enabled (vendor={hwaccel.vendor})")
    started_at = time.monotonic()

    def on_progress(scanned_s: float) -> None:
        """走査済み秒数から推定残り時間を出して通知する。"""
        if notice is None:
            return
        elapsed = time.monotonic() - started_at
        eta: float | None = None
        if scanned_s > 0 and duration > scanned_s:
            eta = elapsed * (duration - scanned_s) / scanned_s
        if eta is not None and not math.isfinite(eta):
            eta = None
        notice(
            StageNotice(
                kind="progress",
                processed_s=round(min(scanned_s, duration), 1),
                total_s=round(duration, 1),
                eta_s=round(eta, 1) if eta is not None else None,
            )
        )

    def scan(
        decoder_hwaccel: HwaccelSpec | None,
    ) -> list[tuple[float, str | None, float]]:
        return scan_detections(
            source,
            interval=interval,
            total=duration,
            frame_size=None,
            crop=band_crop,
            workers=resolve_scan_workers(),
            frames_factory=iter_gray_frames,
            detect=lambda frame: _detection_tuple(frame, layout, templates),
            on_progress=on_progress,
            progress_step=progress_step,
            hwaccel=decoder_hwaccel,
        )

    try:
        detections = scan(hwaccel)
    except VideoProcessingError as exc:
        # #1151: GPU デコードは環境依存で落ちる。ユーザーは「速くしたい」だけ
        # なので、黙って CPU で 1 回だけやり直す。
        if hwaccel is None:
            raise
        say(f"GPU decode failed ({exc}); falling back to CPU ...")
        detections = scan(None)

    events = group_detections(detections, max_gap=interval * 1.2, min_samples=2)
    return IndicatorRun(
        layout=layout_payload,
        events=[_event_payload(event, matches) for event in events],
        recalibrated=was_recalibrated,
        interval=interval,
    )


_INDICATOR_LAYOUT_KEYS = frozenset(
    {"anchor_x", "anchor_y", "scale", "support", "confidence", "source"}
)
"""`$defs/IndicatorLayout` の required 6 キー (= additionalProperties:false)。"""


def _sanitize_indicator_layout(value: object) -> dict[str, Any] | None:
    """`indicator_layout` の preserve sanitizer (#1141)。

    `--from-metadata` は再検知しないので元 metadata の値をそのまま新ファイルに
    書くが、手編集された `indicator_layout: {}` のような値を通すと GUI の zod
    (`IndicatorLayoutSchema`) が **metadata.json 全体を** 拒否し、健全な境界
    結果まで読めなくなる。`_sanitize_capture_regions` と同じ純 Python 検査
    (jsonschema の runtime 依存は追加しない) で、スキーマ
    `$defs/IndicatorLayout` (additionalProperties:false / required 6 keys) を
    写す。完全に妥当なときだけ dict を返す。
    """
    if not isinstance(value, dict):
        return None
    if set(value.keys()) != _INDICATOR_LAYOUT_KEYS:
        return None
    if not _is_finite_json(value):
        return None
    for key in ("anchor_x", "anchor_y", "confidence"):
        number = _finite_number(value.get(key))
        if number is None or not 0.0 <= number <= 1.0:
            return None
    scale = _finite_number(value.get("scale"))
    if scale is None or scale <= 0.0:
        return None
    support = _integral_number(value.get("support"))
    if support is None or support < 1:
        return None
    source = value.get("source")
    if not isinstance(source, str) or not source:
        return None
    sanitized = dict(value)
    # `6.0` のような整数値 float は schema (`integer`) / GUI zod (`.int()`) とも
    # 通るので int に正規化して返す (codex review 2026-11-18 P2)。
    sanitized["support"] = support
    return sanitized


def _sanitize_highlight_events(value: object) -> list[dict[str, Any]] | None:
    """`events` の preserve sanitizer (#1141)。

    壊れた 1 件 (例: `{}`) をそのまま新ファイルに書くと GUI が metadata.json
    全体を読めなくなるため、**スキーマの required を満たす要素だけを残す**。
    全部落ちたら None (キー自体を書かない = 未検出と同じ形)。

    残す条件は `$defs/HighlightEvent` の required 6 フィールド
    (`signal_id` / `timestamp` / `end` / `score` / `evidence` / `match_index`) を
    満たすこと。`clip_start` / `clip_end` は optional なので値の形だけ見る。
    """
    if not isinstance(value, list):
        return None
    kept: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        signal_id = entry.get("signal_id")
        if not isinstance(signal_id, str) or not signal_id:
            continue
        timestamp = _finite_number(entry.get("timestamp"))
        end = _finite_number(entry.get("end"))
        score = _finite_number(entry.get("score"))
        if timestamp is None or end is None or score is None:
            continue
        if timestamp < 0 or end < 0 or not 0.0 <= score <= 1.0:
            continue
        if not isinstance(entry.get("evidence"), dict):
            continue
        # `match_index` は required (明示 null は許容) なので、**キーの存在**と
        # 値の検査を分ける (codex review 2026-11-18 P2)。
        if "match_index" not in entry:
            continue
        match_index = entry["match_index"]
        if match_index is not None:
            normalized = _integral_number(match_index)
            if normalized is None or normalized < 1:
                continue
            match_index = normalized
        # `clip_start` / `clip_end` は optional だが、あるなら有限かつ >= 0 の
        # 数値でなければならない (null / 負値は schema / zod が拒否する)。
        bounds_ok = True
        for key in ("clip_start", "clip_end"):
            if key not in entry:
                continue
            bound = _finite_number(entry[key])
            if bound is None or bound < 0:
                bounds_ok = False
                break
        if not bounds_ok:
            continue
        # `evidence` や未知キーの**入れ子**に NaN / Infinity が残ると、
        # `json.dumps` が非標準 token を再 emit して GUI の strict reader が
        # metadata.json 全体を拒否する (codex review 2026-11-18 P2)。
        if not _is_finite_json(entry):
            continue
        kept.append({**entry, "match_index": match_index})
    return kept or None


def _is_finite_json(value: object, *, depth: int = 0) -> bool:
    """NaN / Infinity を含まない JSON 値か (dict / list を再帰的に検査)。

    `read_metadata` は Python の `json.loads` なので NaN / Infinity を受理するが、
    `write_metadata_atomic` は `allow_nan=True` でそのまま再 emit する。GUI の
    strict reader (serde_json / JSON.parse) は metadata.json **全体**を拒否する
    ため、preserve 経路で塞ぐ (#1141 codex review P2)。

    `depth` の上限は手編集で作られた極端に深い構造での再帰爆発を避けるため
    (`json.loads` は循環を作れないので、これで十分)。
    """
    if depth > 32:
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(
            _is_finite_json(key, depth=depth + 1)
            and _is_finite_json(item, depth=depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_is_finite_json(item, depth=depth + 1) for item in value)
    return True


def _integral_number(value: object) -> int | None:
    """整数値の数値なら int を返す (bool / 非整数 / NaN / Infinity は None)。

    JSON Schema の `integer` は小数部 0 の数値 (`1.0`) も受けるので、Python で
    float になる値も整数として受理する (schema 妥当な値を preserve で落とさない)。
    """
    number = _finite_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _finite_number(value: object) -> float | None:
    """有限実数なら float を返す (bool と NaN / Infinity は None)。

    `json.dumps` は allow_nan=True で非標準 token を再 emit し、strict reader
    (GUI serde_json / JSON.parse) が metadata.json 全体を reject するため、
    NaN / Infinity は sanitize 側で塞ぐ (`_sanitize_capture_regions` と同じ理由)。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def reuse_indicators(
    payload: dict[str, Any],
    *,
    video: Path,
    metadata_path: Path,
) -> int | None:
    """既存 ``metadata.json`` の KO / ASSIST 検出結果を再利用する (#1141)。

    検知キャッシュ (``.detection_cache.json``) が hit したとき、境界検出と同じ
    「前回と同じ動画・同じ出力先」であることは分かっている。その場合に限り、
    前回の ``metadata.json`` に書かれた ``indicator_layout`` / ``events[]`` を
    そのまま引き継ぎ、数分かかる走査を省く。

    再利用するのは **次のすべてを満たすときだけ**（怪しければ走査し直す）:

    * 既存 metadata.json が読める（``schema_version`` が解釈可能）
    * ``source`` が今回の動画と同じ実体（``abspath`` 比較）
    * ``indicator_layout`` / ``events`` が schema 妥当（sanitizer を通る）

    戻り値は再利用したイベント件数。再利用しなかったときは ``None``
    （呼び出し側は通常どおり走査する）。
    """
    from allaganeye.detection.metadata_writer import read_metadata

    if not metadata_path.is_file():
        return None
    try:
        previous = read_metadata(metadata_path)
    except AllaganEyeError:
        # 壊れた / 新しい schema の metadata は根拠にしない（走査し直す）。
        return None
    previous_source = previous.get("source")
    if not isinstance(previous_source, str) or not previous_source:
        return None
    if os.path.abspath(previous_source) != os.path.abspath(video):
        return None
    layout = _sanitize_indicator_layout(previous.get("indicator_layout"))
    events = _sanitize_highlight_events(previous.get("events"))
    if layout is None or events is None:
        return None
    payload["indicator_layout"] = layout
    payload["events"] = events
    return len(events)


def _silent(_message: str) -> None:
    """既定の ``progress`` (何もしない)。"""


def attach_indicators(
    payload: dict[str, Any],
    *,
    source: Path,
    frame_size: tuple[int, int],
    duration: float,
    codec: str | None = None,
    gpu: bool = False,
    interval: float = DEFAULT_INTERVAL,
    notice: Callable[[StageNotice], None] | None = None,
    progress: Callable[[str], None] | None = None,
    progress_step: float = PROGRESS_STEP_SECONDS,
) -> dict[str, Any] | None:
    """`payload` に `indicator_layout` / `events` を足す (#1141)。

    境界検出の payload をそのまま受け取り、その場で書き換える。呼び出し側は
    これを `write_metadata_atomic` の**前**に呼ぶことで、境界と KO / ASSIST が
    **1 回の atomic write** に載る (2 プロセス分割による write-back CAS 競合と
    ffprobe の二重実行を避ける)。

    検出に失敗しても境界の結果は失わない (受け入れ条件 3): 例外は握って
    `warnings[]` に `indicators_failed` を積み、その warning を返す。
    境界検出そのものの成否が exit code を決める。
    """
    try:
        run = detect_indicator_events(
            source,
            payload,
            frame_size=frame_size,
            duration=duration,
            codec=codec,
            interval=interval,
            gpu=gpu,
            notice=notice,
            progress=progress,
            progress_step=progress_step,
        )
    except AllaganEyeError as exc:
        # `AllaganEyeError` = アプリが想定した失敗 (キャリブレーション不能 / ffmpeg
        # 失敗 / metadata 不整合)。想定外の例外は握らずに落とす (バグを隠さない)。
        warning: dict[str, Any] = {
            "code": INDICATORS_FAILED_CODE,
            "severity": "warn",
            "context": {"error": str(exc)},
        }
        warnings = payload.get("warnings")
        if isinstance(warnings, list):
            warnings.append(warning)
        else:
            payload["warnings"] = [warning]
        return warning
    payload["indicator_layout"] = run.layout
    # #127: イベントは全件置換 (検出条件が変われば集合ごと変わる)。fresh な
    # detect / split の payload には events が無いので、引き継ぎ対象も無い。
    payload["events"] = run.events
    return None
