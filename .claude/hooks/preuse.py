"""PreToolUse gate for risky / bulk operations (#401, #559).

Intercepts a small set of ``gh`` / bulk operations and forces the user
to approve before proceeding.  Designed to backstop the docs rules
(#399 / #400) when Claude would otherwise independently run:

- ``gh issue create`` 3+ times within 60 seconds (bulk Issue 起票)
- ``gh pr merge`` (PR マージ)
- ``gh issue close`` 3+ times within 60 seconds (bulk Issue クローズ, #485)
- ``gh issue edit ... --add-label deferred`` 2+ times within 60 seconds

On match, the hook emits a Claude Code PreToolUse JSON output with
``hookSpecificOutput.permissionDecision = "ask"``, which triggers the
standard permission prompt.  The user answers allow / deny in the UI
and the command runs (or is cancelled) in the same tool invocation --
no retry with a prefix is needed (#559 migration from exit-code 2).

## Bypass after explicit approval (#485 / PR #491 review)

Retained as an escape hatch for environments where the permission
prompt is unavailable (non-interactive runs, older Claude Code builds).
Claude can prefix the command with ``ALLAGANEYE_PREUSE_BYPASS=1`` to
skip the gate entirely for that single invocation:

    ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 123

The prefix is stripped and the underlying command is recorded to state
normally, so bulk counters remain accurate for the next non-bypassed
command.  Every bypass is logged to stderr for audit.

## Contract

- Reads a Claude Code PreToolUse JSON event from stdin.  Only Bash tool
  calls are gated; every other tool is allowed unconditionally (exit 0).
- Gate activation: exit 0 + stdout JSON with ``permissionDecision: "ask"``
  so Claude Code surfaces an allow / deny prompt to the user.  The matched
  command is NOT written to ``recent_ops.json`` because the hook cannot
  observe the user's answer (#513 hygiene preserved: ghost entries would
  inflate bulk counters).
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

_BYPASS_PREFIX: re.Pattern[str] = re.compile(r"^ALLAGANEYE_PREUSE_BYPASS=1\s+")
"""User-approved one-shot bypass prefix (#485 / PR #491 review).

When Claude re-runs a command that was just blocked and the user has
already approved it, prefixing the command with this env-var assignment
skips the gate for that single invocation.  The prefix is stripped and
the underlying command is recorded to state normally, so subsequent
unbypass-prefixed commands continue to be counted toward bulk windows.
"""


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
    "issue_close_bulk": {
        "pattern": re.compile(r"^gh\s+issue\s+close\b"),
        "mode": "bulk",
        "threshold": _BULK_THRESHOLD,
        "message": (
            "60 秒以内に 3 件以上の Issue クローズを検知しました。\n"
            "bulk 操作前にサンプル 1 件を提示してユーザー確認を取る運用 "
            "(#399 C / #400 D) に沿って、続行前に確認を取ってください。\n"
            "単発 close は Claude 側の AskUserQuestion 等での個別確認を前提に許可 (#485)。"
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
# Permission prompt output (#559)
# ---------------------------------------------------------------


def _emit_ask(key: str, message: str, command: str) -> None:
    """Emit a PreToolUse ``permissionDecision: "ask"`` payload on stdout.

    Claude Code reads this JSON (while exit code stays 0) and surfaces
    the standard allow / deny permission prompt to the user with
    ``permissionDecisionReason`` as the body text.

    The reason string is intentionally verbose (Iron Law context +
    command preview) so the prompt is self-contained for the user --
    they should not need to scroll the transcript to understand why
    they're being asked.
    """
    reason = (
        f"[{key}] {message}\n"
        "Claude Code permission prompt で allow / deny を選んでください。\n"
        "allow 時のみコマンドが 1 回だけ実行されます (state は allow 後の"
        " PostToolUse 経路でなく、次回 PreToolUse の pass 時に記録されます)。\n"
        f"Detected command: {command.strip()[:400]}"
    )
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    # Advanced JSON output must be on stdout (Claude Code hooks spec).
    # A single line keeps the payload obvious in hook logs.
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


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

    # User-approved one-shot bypass (#485 / PR #491 review).
    # Prefix is explicit in the Bash tool log (auditable); the underlying
    # command is recorded to state so the next non-bypassed command still
    # sees accurate bulk counts.
    bypass_match = _BYPASS_PREFIX.match(command)
    if bypass_match:
        stripped = command[bypass_match.end() :]
        print(
            "[preuse:bypass] ALLAGANEYE_PREUSE_BYPASS=1 "
            "で承認済み実行として gate を bypass しました。\n"
            f"Command: {stripped.strip()[:400]}",
            file=sys.stderr,
        )
        _append_op(state_path, stripped.strip(), now)
        return 0

    recent = _read_recent_ops(state_path, now)

    # Pattern 判定 (candidate の command を recent に含めずに判定)
    key, message = _classify(command, recent)

    if key is not None:
        # ask された時点では state に記録しない (#513 + #559).
        # 実行されるかはユーザーの allow / deny 回答次第で、hook からは
        # 観測できない。deny された ghost 実行を bulk counter に入れると、
        # 閾値を永続的に超えて ask が連発する不具合になるので、state に
        # 載せるのは bypass / pass ルートに限定する (実測主義、#513 維持)。
        #
        # stderr には audit 用の log を残し、stdout には Claude Code の
        # permission prompt 用 JSON を出力して exit 0 で終了する。
        assert message is not None  # _classify 契約: key != None のとき message も非 None
        print(
            f"[preuse:{key}] ask -> user permission prompt\n"
            f"Command: {command.strip()[:400]}",
            file=sys.stderr,
        )
        _emit_ask(key, message, command)
        return 0

    # Block / ask 通過時のみ state に記録 (bulk カウント用).
    _append_op(state_path, command.strip(), now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
