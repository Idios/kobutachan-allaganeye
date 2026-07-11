"""probe 失敗縮退の統一契約型 (#824 spec §5.1)。

presence / capture_region / scorebar / detector から import される中立 module。
presence.py 所有にすると capture_region → presence の逆向き import で cycle に
なるため独立配置 (#824 §5.1 module 配置)。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PresenceState(Enum):
    """scorebar presence の tri-state。UNKNOWN = probe 失敗 (decode None / 例外)。

    ABSENT (観測に基づく不在) と UNKNOWN (観測不能) の暗黙同一視を型で禁止する。
    UNKNOWN → ABSENT への折り畳みは集約層のみが明示的な state 比較で行う (§5.2)。
    """

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PresenceSample:
    """One time-grid sample: scorebar presence state at ``time``.

    ``confidence`` is 0.0 for ABSENT / UNKNOWN.  意図的に ``present`` bool
    property を持たない (#824 §5.1: silent bool 化経路の禁止)。
    """

    time: float
    state: PresenceState
    confidence: float


class ProbeFailurePolicy(Enum):
    """集約層の probe 失敗方針 (#824 §5.2)。現時点の消費者は ISOLATE のみ。

    RAISE は将来の診断 harness / GT 突合用の speculative seam として定義だけ残す。
    """

    RAISE = "raise"
    ISOLATE = "isolate"
