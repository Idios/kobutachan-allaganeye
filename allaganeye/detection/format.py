"""Shared format helpers for the detection pipeline (#463).

These were previously private to ``commands.split_matches``; extraction lets
the new ``detect`` command and ``split --from-metadata`` use the same
timestamp / duration / ISO formatting.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    """Format duration as e.g. '14m02s' or '1h05m'."""
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def format_hms(seconds: float) -> str:
    """Format seconds as zero-padded ``hh:mm:ss`` (#127).

    L4 のイベント / クリップ範囲は録画全体の時刻で読む (試合相対は自分で引く) ため、
    時を省く ``MM:SS`` 形式 (:func:`format_timestamp`) ではなくこちらを使う。
    1 秒未満は切り捨てる (保存値は 0.01 秒精度のまま)。
    """
    total = int(max(0.0, seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_indicator_summary(events: Sequence[Mapping[str, object]]) -> str:
    """KO / ASSIST イベント数の 1 行サマリ (#1141)。

    ``indicators`` コマンドの summary と、``detect`` / ``split`` に統合した
    ステージの完了行の**両方**がここを使う (件数の数え方を 1 か所にする)。
    未知の ``signal_id`` は KO / ASSIST のどちらにも数えない。
    """
    ko = sum(1 for event in events if event.get("signal_id") == "ko_indicator")
    assist = sum(1 for event in events if event.get("signal_id") == "assist_indicator")
    return f"KO: {ko} / ASSIST: {assist} ({len(events)} intervals)"


def iso_utc_now() -> str:
    """UTC timestamp in ISO 8601 with 'Z' suffix, e.g. '2026-04-19T12:34:56Z'.

    Used for metadata.json ``detected_at`` / ``detection_started_at`` /
    ``detection_completed_at`` (#370 / #586). Second precision keeps the
    string human-readable without losing practical reproducibility.
    """
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
