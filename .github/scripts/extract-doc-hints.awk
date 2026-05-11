#!/usr/bin/env -S awk -f
# Extract (code, hint_normalized) pairs from
# docs/tauri-commands.md §「AppError default hint mapping」 table rows.
#
# Output format: <code>\t<hint_normalized>
#   - code: from `code` (backtick-wrapped) in the first cell; cell may contain
#     multiple codes separated by " / " (e.g. `io.would_block` / `io.timed_out`)
#   - hint: second cell, whitespace-collapsed to single space
#   - None entry: hint cell starts with "(hint なし:" → <<NONE>> sentinel
#
# Approach: state-machine on lines. Enter target section when seeing
# "## AppError default hint mapping" header, exit on next "## " header or EOF.
# Inside section, parse rows that start with "| `".

BEGIN {
    in_section = 0
}

# Enter target section
/^## AppError default hint mapping/ {
    in_section = 1
    next
}

# Exit on next ## heading (other than entering line)
in_section && /^## / {
    in_section = 0
}

# Parse table row: | `code` ... | hint |
in_section && /^\| `/ {
    process_row($0)
}

function process_row(line,    code_cell, hint_cell, codes, code, hint, pipe_idx, second_pipe_idx, third_pipe_idx, rest, rest2) {
    pipe_idx = index(line, "|")
    if (pipe_idx != 1) return  # row must start with |
    rest = substr(line, 2)
    second_pipe_idx = index(rest, "|")
    if (second_pipe_idx == 0) return
    code_cell = substr(rest, 1, second_pipe_idx - 1)
    rest2 = substr(rest, second_pipe_idx + 1)
    third_pipe_idx = index(rest2, "|")
    if (third_pipe_idx == 0) {
        hint_cell = rest2
    } else {
        hint_cell = substr(rest2, 1, third_pipe_idx - 1)
    }

    gsub(/^[[:space:]]+|[[:space:]]+$/, "", hint_cell)
    if (hint_cell ~ /^\(hint なし:/) {
        hint = "<<NONE>>"
    } else {
        hint = hint_cell
        gsub(/[[:space:]]+/, " ", hint)
        sub(/^ /, "", hint)
        sub(/ $/, "", hint)
    }

    while (match(code_cell, /`[a-zA-Z0-9_.]+`/)) {
        code = substr(code_cell, RSTART + 1, RLENGTH - 2)
        print code "\t" hint
        code_cell = substr(code_cell, RSTART + RLENGTH)
    }
}
