# markdownlint guide

`docs/` 配下の markdown 編集時に踏みやすい lint violation と、`.markdownlint-cli2.yaml` の ignore パターンの規約。

## このドキュメントの位置付け

以下の経路から参照される。違反 fix で迷ったとき、ignore pattern を新規追加するとき、glob semantics を再確認したいときに引く:

- `.markdownlint-cli2.yaml` の header comment
- `scripts/check-markdownlint.sh` の lint failure 時 stderr hint
- `CLAUDE.md` §コマンド の markdownlint 行直下
- `/review-pr` skill Step 5b トリアージ (L-β で追加予定)
- `/iterate-review` skill Step 2.4 (L-β で追加予定)

## ローカル実行

```bash
# 全 .md チェック (CI と同じパターン)
bash scripts/check-markdownlint.sh

# 変更 file 限定で fix を試す
npx --yes markdownlint-cli2 --fix <path>...
```

CI: `.github/workflows/markdownlint.yml` (paths filter `**/*.md`)。

## ignore パターン規約

`.markdownlint-cli2.yaml` の `ignores` に追加するときは **`**/<name>/**` 形式** で書く。1 階層 path 直書きは禁止 (例えば `node_modules/` 単独では nested `gui/node_modules/` に効かない)。

### 現在の ignores (2026-05 時点)

| パターン | 由来 PR / 理由 |
| --- | --- |
| `**/node_modules/**` | nested node_modules (gui/) を含めて exclude (#700 PR #717) |
| `**/dist/**` | vite build output (gui/dist/) |
| `**/build/**` | PowerShell installer build output (#723 PR #724) |
| `**/.venv/**` | Python venv |
| `**/kobutachan_allaganeye.egg-info/**` | pip install -e . の egg-info |
| `**/build-cache/**` | CI cache extracted artifacts |

新規 build / cache dir が増えたら早めに `**/<name>/**` 形式で追加する。1 階層パターン (例: `dist/**`) は nested ケース (例: `gui/dist/**`) を捕捉しないため避ける。

## 典型的な lint violation (発火しやすい上位 3 ルール)

### MD028 no-blanks-blockquote

連続する `> ...` blockquote 間に空行があると「同一 blockquote 内の blank line」と判定されてエラー。

**Fix**: `>` のみの行 (空 blockquote 行) で連結する。

```text
> **Note A**: ...
>
> **Note B**: ...
```

### MD056 table-column-count + MD060 table-column-style

table cell の inline code に `|` (例: `` `AppError|null` ``) があると、code span を無視して table separator として parse され、cell 数 mismatch エラー。

**Fix**: `\|` で escape (例: `` `AppError\|null` ``)。GFM の table parser は `\|` を escape として認識、render 時に backslash を消費して `|` 表示。backtick 内でも escape 適用。

TypeScript 型 (`Foo|null`、`A|B` 等) を含む table cell は最初から `\|` で書く。

### MD060 table-column-style "compact"

separator 行 (`| --- | --- |`) と data 行 (`| col1 | col2 |`) の pipe 周りスペースを統一する。1 つの table 内で混ぜると compact-style violation。

**Fix**: 全行で `| ... | ... |` (前後にスペース) 形式に揃える。`|---|---|` 形式は data 行が `| col |` の場合に MD060 違反になる。

## history (発生 PR と修正)

- PR #494 / #500-502: 初期導入時 MD022/MD024/MD028-32/MD038/MD040/MD041/MD036 を整理 (`docs/` 配下を一掃)
- PR #717: nested `gui/node_modules/**/*.md` を ignore に追加 (#700 修正)
- PR #724: `build/**` を ignore に追加 (#723 修正)
- PR #709: TS 型を含む table cell (`*ErrorState: AppError|null` 等) で MD028 / MD056+MD060 4 errors 発生 → escape 修正
- PR #746: brainstorming sweep 漏れで dangling reference fix の Phase D が発生 (markdownlint 自体は別件)

## 関連

- `.markdownlint-cli2.yaml` — ignore + enabled rules の本体
- `scripts/check-markdownlint.sh` — ローカル全件チェック script
- [DavidAnson/markdownlint-cli2 README](https://github.com/DavidAnson/markdownlint-cli2) — 上流ドキュメント
