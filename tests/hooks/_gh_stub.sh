#!/usr/bin/env bash
# gh stub for session-start.sh / cleanup-claude-branches.sh tests. Reads the
# canned response from $GH_STUB_RESPONSE (literal string passed through) and an
# optional exit code from $GH_STUB_EXIT (default 0, used to simulate gh failure
# / network error for cleanup-claude-branches.sh #827 fallback tests).
# Usage in tests: configure PATH to put this file's parent first, name it `gh`.
echo "${GH_STUB_RESPONSE:-[]}"
exit "${GH_STUB_EXIT:-0}"
