#!/usr/bin/env bash
# Integration test: check-error-hint-drift.sh against fixture files.
# Fixtures are designed to match (expected pairs identical), so the
# script should exit 0.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export RUST_FILE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-error.rs"
export DOC_FILE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-tauri-commands.md"

if bash "$SCRIPT_DIR/.github/scripts/check-error-hint-drift.sh"; then
    echo "PASS: fixtures match"
    exit 0
else
    echo "FAIL: fixtures should match but drift detected" >&2
    exit 1
fi
