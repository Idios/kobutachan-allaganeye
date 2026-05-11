#!/usr/bin/env bash
# Check drift between gui/src-tauri/src/error.rs::default_hint_for_code
# and docs/tauri-commands.md §「AppError default hint mapping」 table.
#
# Source of truth: error.rs (docstring states "本 fn が source of truth、docs は mirror")
# Mirror:          docs/tauri-commands.md
# Both must agree on (code, hint) pairs after normalization.
#
# Exit codes:
#   0 — no drift detected
#   1 — drift detected (or input files missing)
#
# Refs: https://github.com/Idios/kobutachan-allaganeye/issues/692

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RUST_FILE="${RUST_FILE:-$REPO_ROOT/gui/src-tauri/src/error.rs}"
DOC_FILE="${DOC_FILE:-$REPO_ROOT/docs/tauri-commands.md}"

if [[ ! -f "$RUST_FILE" ]]; then
    echo "ERROR: Rust source not found: $RUST_FILE" >&2
    exit 1
fi
if [[ ! -f "$DOC_FILE" ]]; then
    echo "ERROR: Docs file not found: $DOC_FILE" >&2
    exit 1
fi

RUST_PAIRS=$(awk -f "$SCRIPT_DIR/extract-rust-hints.awk" "$RUST_FILE" | sort)
DOC_PAIRS=$(awk -f "$SCRIPT_DIR/extract-doc-hints.awk" "$DOC_FILE" | sort)

if diff -u <(echo "$RUST_PAIRS") <(echo "$DOC_PAIRS") > /dev/null; then
    echo "OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync ($(echo "$RUST_PAIRS" | wc -l) entries)"
    exit 0
fi

cat >&2 <<'EOF'

ERROR: error.rs ↔ docs/tauri-commands.md hint drift detected.

Source of truth: gui/src-tauri/src/error.rs::default_hint_for_code
Mirror:          docs/tauri-commands.md §「AppError default hint mapping」 table

Both must be updated in the same PR. See docs/tauri-commands.md docstring +
gui/src-tauri/src/error.rs::default_hint_for_code docstring for the contract.

Diff (- = error.rs side, + = docs side):
EOF
diff -u <(echo "$RUST_PAIRS") <(echo "$DOC_PAIRS") >&2 || true
exit 1
