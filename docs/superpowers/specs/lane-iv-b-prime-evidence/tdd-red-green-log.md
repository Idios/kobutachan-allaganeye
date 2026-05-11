# TDD red×3 verification log (Lane IV-b' #692)

Spec: docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md §3.4

## red 1: 文言変更

- 変更: `io.file_not_found` hint cell を「パスを確認」→「パスを再確認」
- 結果: exit 1、diff 出力で文言 mismatch を明示

## red 2: or-pattern code 削除

- 変更: docs から `io.timed_out` を削除 (or-pattern を `io.would_block` のみに)
- 結果: exit 1、`+ io.timed_out\t...` 行が docs side に欠落

## red 3: None sentinel 変更

- 変更: `subprocess.cancelled` の cell を `(hint なし: ...)` → 「キャンセルされました」
- 結果: exit 1、Rust side `<<NONE>>` vs docs side 実文言 mismatch

## green (revert 後)

- すべての revert 後で `OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync (24 entries)`
- `git diff --quiet docs/tauri-commands.md` exit 0
