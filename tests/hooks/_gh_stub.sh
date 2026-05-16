#!/usr/bin/env bash
# gh stub for session-start.sh tests. Reads the canned response from
# $GH_STUB_RESPONSE env var (literal string passed through).
# Usage in tests: configure PATH to put this file's parent first, name it `gh`.
echo "${GH_STUB_RESPONSE:-[]}"
