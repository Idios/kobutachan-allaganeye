# docs/knowledge

セッション横断で再利用する調査結果・トラブルシュート・判断の記録を置く（`docs/l2-workflow.md` §Memory 階層化 の L3）。

## 何を置くか

- 複数セッションで再利用する汎用知見（同じ調査を繰り返さないための記録）
- 環境依存のトラブルシュート（OS / ffmpeg / GPU / エディタごとの挙動と回避策）
- 外部ツール（`codex` CLI / Zed / GitHub Actions）の実測メモ

## 何を置かないか

- 特定 issue / PR の作業中状態（それは issue / PR に書く）
- 判断の途中経過（結論だけを置く。経緯は `docs/superpowers/specs/**` に残す）
- 既に正が決まっている規約（`AGENTS.md` / `docs/l2-workflow.md` が正。ここには置かない）

## 命名

`<topic>.md`（例: `codex-cli-invocation.md` / `windows-path-pitfalls.md`）。日付接頭辞は付けない（更新される living な記録のため）。
