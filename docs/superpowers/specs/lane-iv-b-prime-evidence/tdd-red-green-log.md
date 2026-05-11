# TDD red×3 verification log (Lane IV-b' #692)

Spec: docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md §3.4

各 red ケースで `docs/tauri-commands.md` を一時的に sed で書き換え、`bash .github/scripts/check-error-hint-drift.sh` が exit 1 (drift detected) を返すことを実証する。検証後すべて revert し、最終的に `git diff --quiet docs/tauri-commands.md` exit 0 (差分なし) を確認した。

## red 1: 文言変更

- 対象: `io.file_not_found` の hint cell
- sed pattern: `s/パスを確認するか/パスを再確認するか/`
- 想定: `io.file_not_found` の hint 文字列の中の「パスを確認するか」を「パスを再確認するか」に書き換える
- 結果: `check-error-hint-drift.sh` exit 1。diff 出力で `io.file_not_found` の hint が docs 側のみ変化していることが明示された
- revert: `mv docs/tauri-commands.md.bak docs/tauri-commands.md` で復元、`check-error-hint-drift.sh` が `OK: ... 24 entries in sync` で exit 0 に戻ったことを確認

## red 2: or-pattern code 削除

- 対象: or-pattern 行 `` | `io.would_block` / `io.timed_out` | ... | ``
- sed pattern: ``s/`io.would_block` \/ `io.timed_out`/`io.would_block`/``
- 想定: docs 側から `io.timed_out` を削除 (or-pattern の片方が消える)
- 結果: `check-error-hint-drift.sh` exit 1。diff 出力で `io.timed_out\tI/O 処理が...` 行が Rust side にのみ存在し docs side に欠落していることが明示された (TAB は実 TAB 文字)
- revert: 復元後 `OK: ... 24 entries in sync` exit 0 で green を確認

## red 3: None sentinel 変更

- 対象: `subprocess.cancelled` の hint cell (現状 `(hint なし: ユーザー操作によるキャンセルは UI 側で十分な情報を出す)`)
- sed pattern: `s/(hint なし: ユーザー操作.*)/キャンセルされました/` (regex `.*` が cell の閉じカッコまで一致して全体を `キャンセルされました` で置換)
- 想定: docs 側で sentinel `(hint なし: ...)` が消え、実文言が入る
- 結果: `check-error-hint-drift.sh` exit 1。diff 出力で `subprocess.cancelled` の hint が `<<NONE>>` (Rust side、`=> None,` arm 由来) vs `キャンセルされました` (docs side) で mismatch であることが明示された
- revert: 復元後 `OK: ... 24 entries in sync` exit 0 で green を確認

## green (3 ケース完了後の最終 verify)

- 3 red ケースの revert 後、`bash .github/scripts/check-error-hint-drift.sh` が `OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync (24 entries)` を出力し exit 0
- `git diff --quiet docs/tauri-commands.md` が exit 0 (差分なし、完全 revert)
- `docs/tauri-commands.md.bak` が残存していないことを確認

## 再現手順 (将来の作業者向け)

検証を再実行したい場合は本 log の各 red ケースに記載した sed pattern をそのまま適用すれば再現できる。手順:

1. `git diff --quiet docs/tauri-commands.md` で事前 clean 確認
2. 該当 red ケースの sed コマンドを `-i.bak` 付きで実行
3. `bash .github/scripts/check-error-hint-drift.sh` で exit 1 を確認
4. `mv docs/tauri-commands.md.bak docs/tauri-commands.md` で revert
5. `bash .github/scripts/check-error-hint-drift.sh` で exit 0 を確認
