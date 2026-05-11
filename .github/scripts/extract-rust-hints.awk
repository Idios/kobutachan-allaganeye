#!/usr/bin/env -S awk -f
# Extract (code, hint_normalized) pairs from
# gui/src-tauri/src/error.rs::default_hint_for_code match arms.
#
# Output format: <code>\t<hint_normalized>
#   - code: from string literal "code" in the arm's left side
#   - hint: from Some("...") string literal, whitespace-collapsed to single space
#   - or-pattern ("a" | "b" => Some(...)) emits one row per code
#   - None entries (=> None,) emit <<NONE>> as the hint
#   - catch-all (_ => None,) is skipped (no quoted code literal)
#
# Approach: accumulate fn body into a single buffer (newlines -> space),
# then scan with regex for each match arm and emit pairs.

BEGIN {
    in_fn = 0
    buf = ""
}

/^fn default_hint_for_code/ {
    in_fn = 1
    next
}

in_fn && /^\}/ {
    in_fn = 0
}

in_fn {
    buf = buf " " $0
}

END {
    while (match(buf, /"[a-zA-Z0-9_.]+"([[:space:]]*\|[[:space:]]*"[a-zA-Z0-9_.]+")*[[:space:]]*=>[[:space:]]*(Some\([[:space:]]*"[^"]*"[[:space:]]*\)|None)[[:space:]]*,/)) {
        arm = substr(buf, RSTART, RLENGTH)
        buf = substr(buf, RSTART + RLENGTH)
        process_arm(arm)
    }
}

function process_arm(arm,    sep_idx, left, right, hint, code, raw) {
    sep_idx = index(arm, "=>")
    if (sep_idx == 0) return
    left = substr(arm, 1, sep_idx - 1)
    right = substr(arm, sep_idx + 2)

    if (right ~ /None/) {
        hint = "<<NONE>>"
    } else {
        if (!match(right, /Some\([[:space:]]*"[^"]*"[[:space:]]*\)/)) return
        raw = substr(right, RSTART, RLENGTH)
        sub(/^Some\([[:space:]]*"/, "", raw)
        sub(/"[[:space:]]*\)$/, "", raw)
        hint = raw
        gsub(/[[:space:]]+/, " ", hint)
        sub(/^ /, "", hint)
        sub(/ $/, "", hint)
    }

    while (match(left, /"[a-zA-Z0-9_.]+"/)) {
        code = substr(left, RSTART + 1, RLENGTH - 2)
        print code "\t" hint
        left = substr(left, RSTART + RLENGTH)
    }
}
