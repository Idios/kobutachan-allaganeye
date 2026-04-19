"""PreToolUse gate for risky / bulk operations (#401).

Intercepts a small set of ``gh`` / bulk operations and forces Claude to
escalate to the user before proceeding.  Designed to backstop the docs
rules (#399 / #400) when Claude would otherwise independently run:

- ``gh issue create`` 3+ times within 60 seconds (bulk Issue 起票)
- ``gh pr merge`` (PR マージ)
- ``gh issue close`` (Issue クローズ)
- ``gh issue edit ... --add-label deferred`` 2+ times within 60 seconds

Exit code 2 asks Claude Code to show the stderr message to the user and
pause; Claude then asks for confirmation before proceeding.

## Contract

- Reads a Claude Code PreToolUse JSON event from stdin.  Only Bash tool
  calls are gated; every other tool is allowed unconditionally (exit 0).
- State: ``.claude/state/recent_ops.json`` records ``[{"cmd", "ts"}]``
  for bulk-pattern timing.  Entries older than ``_BULK_WINDOW_SEC`` are
  discarded on every read.
- Config: ``.claude/settings.local.json`` may set
  ``"pretooluse_gate": false`` to globally disable the gate (default:
  enabled).  Category-specific switches are deliberately out of scope
  (YAGNI, per #401 確定方針).
- Thresholds (``_BULK_THRESHOLD``, ``_BULK_WINDOW_SEC``) are module-level
  constants; override is out of scope for this initial implementation.

Windows dev note: invoked as ``python .claude/hooks/preuse.py`` by the
settings.json hook entry.  No Windows-specific shebang trickery -- the
interpreter is whatever the running shell uses.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------

_BULK_THRESHOLD: int = 3
"""Number of matching commands within the window that triggers 'bulk' gating."""

_BULK_WINDOW_SEC: float = 60.0
"""Sliding window for bulk detection (seconds)."""

_DEFERRED_BULK_THRESHOLD: int = 2
"""deferred ラベル付与は 2 件以上 / 60s で gate (issue body より低い閾値)."""


# Gated command patterns.  Each entry:
#   ``pattern``: regex matched against the stripped Bash command
#   ``mode``: "always" = gate every invocation; "bulk" = gate when the
#       count within the sliding window hits the threshold
#   ``threshold``: override of _BULK_THRESHOLD for this pattern
#   ``message``: shown to the user (stderr) on gate activation
_GATED_PATTERNS: dict[str, dict[str, object]] = {
    "issue_create_bulk": {
        "pattern": re.compile(r"^gh\s+issue\s+create\b"),
        "mode": "bulk",
        "threshold": _BULK_THRESHOLD,
        "message": (
            "60 秒以内に 3 件以上の Issue 起票を検知しました。\n"
            "bulk 操作前にサンプル 1 件を提示してユーザー確認を取る運用 "
            "(#399 C / #400 D) に沿って、続行前に確認を取ってください。"
        ),
    },
    "pr_merge": {
        "pattern": re.compile(r"^gh\s+pr\s+merge\b"),
        "mode": "always",
        "threshold": 1,
        "message": (
            "PR マージ操作です。テスト完了 / レビュー完了 / ユーザー承認を "
            "確認しましたか?  #400 のマトリクスでは PR マージは常に確認必須です。"
        ),
    },
    "issue_close": {
        "pattern": re.compile(r"^gh\s+issue\s+close\b"),
        "mode": "always",
        "threshold": 1,
        "message": (
            "Issue クローズ操作です。実動画再現確認 / 副作用 Issue 起票 / "
            "ユーザー承認を行いましたか?  #400 のマトリクスで Issue クローズは "
            "常に確認必須です。"
        ),
    },
    "deferred_label_bulk": {
        "pattern": re.compile(r"^gh\s+issue\s+edit\b[^\n]*--add-label[^\n]*deferred"),
        "mode": "bulk",
        "threshold": _DEFERRED_BULK_THRESHOLD,
        "message": (
            "60 秒以内に 2 件以上の deferred ラベル付与を検知しました。\n"
            "判定基準 (scope / 優先度) をユーザー確認してから続行してください "
            "(#400 マトリクス: deferred 付与は確認必須)。"
        ),
    },
}


# ---------------------------------------------------------------
# Paths
# ---------------------------------------------------------------


def _project_root() -> Path:
    """Directory of the project (``$CLAUDE_PROJECT_DIR``-equivalent)."""
    # Hook lives at ``.claude/hooks/preuse.py``; project root is 2 parents up.
    return Path(__file__).resolve().parent.parent.parent


def _state_path() -> Path:
    return _project_root() / ".claude" / "state" / "recent_ops.json"


def _settings_local_path() -> Path:
    return _project_root() / ".claude" / "settings.local.json"


# ---------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------


def _read_recent_ops(path: Path, now: float) -> list[dict]:
    """Return recent ops within the bulk window, silently dropping older."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        # Permission / corruption: fail open so business is not blocked.
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Corrupt state file: fail open and rewrite on next append.
        return []

    if not isinstance(data, list):
        return []

    cutoff = now - _BULK_WINDOW_SEC
    return [
        entry
        for entry in data
        if isinstance(entry, dict)
        and "cmd" in entry
        and "ts" in entry
        and isinstance(entry["ts"], (int, float))
        and entry["ts"] >= cutoff
    ]


def _append_op(path: Path, cmd: str, now: float) -> list[dict]:
    """Append ``cmd`` at ``now`` and return the pruned window."""
    entries = _read_recent_ops(path, now)
    entries.append({"cmd": cmd, "ts": now})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        # Can't persist: best-effort, fail open.
        pass
    return entries


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------


def _gate_enabled() -> bool:
    """Return False when the user explicitly disabled the gate.

    Default: enabled.  We only respect the settings.local.json value when
    it's a proper bool; missing keys / parse failures keep the gate on
    (fail-safe for the "Claude shouldn't accidentally run wild" direction).
    """
    path = _settings_local_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return True
    except OSError:
        return True

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return True

    value = data.get("pretooluse_gate") if isinstance(data, dict) else None
    if isinstance(value, bool):
        return value
    return True


# ---------------------------------------------------------------
# Classification
# ---------------------------------------------------------------


def _classify(cmd: str, recent: list[dict]) -> tuple[str | None, str | None]:
    """Return (pattern_key, message) when the command should be gated.

    Bulk patterns count the current command toward the threshold, so the
    caller must *not* re-insert ``cmd`` into ``recent`` before classify.
    """
    stripped = cmd.strip()
    for key, spec in _GATED_PATTERNS.items():
        pattern: re.Pattern[str] = spec["pattern"]  # type: ignore[assignment]
        if not pattern.search(stripped):
            continue
        mode = spec["mode"]
        message = spec["message"]  # type: ignore[assignment]
        if mode == "always":
            return key, str(message)
        if mode == "bulk":
            threshold = int(spec["threshold"])  # type: ignore[arg-type]
            prior = sum(1 for e in recent if pattern.search(str(e.get("cmd", ""))))
            if prior + 1 >= threshold:
                return key, str(message)
    return None, None


# ---------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------


def main() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        # Unknown payload shape: don't block.
        return 0

    if not isinstance(event, dict):
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input", {})
    if tool_name != "Bash" or not isinstance(tool_input, dict):
        return 0

    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return 0

    if not _gate_enabled():
        return 0

    state_path = _state_path()
    now = time.time()
    recent = _read_recent_ops(state_path, now)

    # Pattern 判定 (candidate の command を recent に含めずに判定)
    key, message = _classify(command, recent)

    # Bulk カウント目的で今回の command を state に記録.
    # 常時 gate と bulk gate のどちらでも、state は更新する (後続判定の
    # ために今回のコマンドも履歴に入れる).
    _append_op(state_path, command.strip(), now)

    if key is not None:
        print(
            f"[preuse:{key}] {message}\nDetected command: {command.strip()[:400]}",
            file=sys.stderr,
        )
        # Exit code 2 = block with error surfaced to Claude (PreToolUse
        # hook convention).  Claude will pause and escalate to the user.
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
