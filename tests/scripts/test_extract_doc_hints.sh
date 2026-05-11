#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AWK_FILE="$SCRIPT_DIR/.github/scripts/extract-doc-hints.awk"
FIXTURE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-tauri-commands.md"
EXPECTED="$SCRIPT_DIR/tests/fixtures/error-hints/expected-doc.tsv"

if [[ ! -f "$AWK_FILE" ]]; then
  echo "FAIL: awk script not found: $AWK_FILE" >&2
  exit 1
fi

actual=$(awk -f "$AWK_FILE" "$FIXTURE" | sort)
expected=$(sort "$EXPECTED")

if [[ "$actual" == "$expected" ]]; then
  echo "PASS: extract-doc-hints.awk matches expected"
  exit 0
else
  echo "FAIL: drift detected"
  diff -u <(echo "$expected") <(echo "$actual")
  exit 1
fi
