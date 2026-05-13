#!/usr/bin/env bash
# format-cleanup-log.sh — Pretty-print cleanup NDJSON events from stdin or file.
#
# Usage:
#   scripts/cleanup-worktrees.sh --apply | scripts/format-cleanup-log.sh
#   scripts/format-cleanup-log.sh < .claude/state/stop-hook.log
#
# Requires: jq (preferred) or python3 (fallback).
# Without either, falls back to plain echo of stdin.
#
# Output format (one line per NDJSON event):
#   [cleanup-worktrees] removed foo
#   [cleanup-worktrees] kept bar (reason: not-empty)
#   [cleanup-worktrees] summary: 1 removed / 1 kept / 2 total

set -u

_PY_FORMATTER='
import sys, json
files = sys.argv[1:]
if files:
    lines_iter = (l for f in files for l in open(f))
else:
    lines_iter = sys.stdin
for line in lines_iter:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    script = obj.get("script", "?")
    event  = obj.get("event",  "?")
    name   = obj.get("name")
    reason = obj.get("reason")
    if event == "start":
        print("[{}] start (apply={})".format(script, str(obj.get("apply", False)).lower()))
    elif event == "summary":
        deleted = obj.get("deleted")
        removed = obj.get("removed", 0)
        kept    = obj.get("kept",    0)
        total   = obj.get("total",   0)
        if deleted is not None:
            print("[{}] summary: {} deleted / {} kept / {} total".format(script, deleted, kept, total))
        else:
            print("[{}] summary: {} removed / {} kept / {} total".format(script, removed, kept, total))
    elif event == "error":
        print("[{}] error: {}".format(script, obj.get("message", "?")))
    elif reason:
        print("[{}] {} {} (reason: {})".format(script, event, name, reason))
    elif name:
        print("[{}] {} {}".format(script, event, name))
    else:
        print("[{}] {}".format(script, event))
'

if command -v jq >/dev/null 2>&1; then
  jq -r '
    if .event == "start" then
      "[\(.script)] start (apply=\(.apply))"
    elif .event == "summary" then
      if .deleted then
        "[\(.script)] summary: \(.deleted) deleted / \(.kept // 0) kept / \(.total) total"
      else
        "[\(.script)] summary: \(.removed // 0) removed / \(.kept // 0) kept / \(.total) total"
      end
    elif .event == "error" then
      "[\(.script)] error: \(.message)"
    elif .reason then
      "[\(.script)] \(.event) \(.name) (reason: \(.reason))"
    elif .name then
      "[\(.script)] \(.event) \(.name)"
    else
      "[\(.script)] \(.event)"
    end
  ' "$@"
elif command -v python3 >/dev/null 2>&1; then
  python3 -c "${_PY_FORMATTER}" "$@"
else
  # No jq and no python3: pass NDJSON through as-is
  cat "$@"
fi
