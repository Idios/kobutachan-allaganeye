# Declaration Catalog

同一の事実が 2 spot 以上に現れるものの台帳。各行は「SSoT 1 箇所 + 複製 spot + 強制モード」を宣言する。**正は本表**で、強制の実装は `scripts/check_declarations.py`、id 集合の pin は `tests/scripts/test_check_declarations.py`。

## 規約

- 行を追加するときは `mode` を必ず 1 つ選ぶ。`prose-only` は「機械検証しない」ことの**明示**であり、理由を備考に書く
- `gate` は `none` / `ci:<job>[:<step 名 substring>]` / `script:<path>::<func>` のいずれか。複数は `+` で連ねる
- `status` は `active` (gate 実装済み) か `planned:<phase>` (未実装。phase は実装計画の PR 番号)
- **行を消すと検査は緑のまま**になる (未登録クラスは drift ではない)。消失は test の id 集合 pin が検出する

## 台帳

| id | 事実 | SSoT | 複製 spot | mode | gate | status |
| --- | --- | --- | --- | --- | --- | --- |
| exit-codes | exit code と実装の対応 | allaganeye/exceptions.py | AGENTS.md | checked | script:scripts/check_declarations.py::check_exit_codes | active |
| cli-options | サブコマンドの option 集合 | allaganeye/cli.py | docs/cli-spec.md | checked | script:scripts/check_declarations.py::check_cli_options | active |
| tauri-commands | #[tauri::command] の関数集合 | gui/src-tauri/src/lib.rs | docs/tauri-commands.md | checked | ci:doc-tauri-commands-drift | active |
| iron-law | Iron Law 6 条 + Red Flags 本文 | AGENTS.md | .claude/hooks/session-start.sh | runtime-extract | script:scripts/check_declarations.py::check_iron_law_mirror | active |
| bulk-threshold | bulk 操作の閾値 3 件 / 60s | .claude/hooks/preuse.py | docs/l2-workflow.md, AGENTS.md | checked | script:scripts/check_declarations.py::check_bulk_threshold | active |
| required-checks | required status checks 8 件 | docs/release-process.md | .github/workflows/ci.yml, .github/workflows/markdownlint.yml, .github/workflows/pr-checklist.yml | checked | script:scripts/check_declarations.py::check_required_checks | active |
| line-refs | living doc の行番号参照禁止 | docs/coding-conventions.md | AGENTS.md, docs/*.md, .agents/skills/*/SKILL.md, .claude/agents/*.md | checked | script:scripts/check_declarations.py::check_line_refs | active |
| path-refs | backtick path 参照の解決 | docs/coding-conventions.md | AGENTS.md, docs/*.md, .agents/skills/*/SKILL.md, .claude/agents/*.md | checked | script:scripts/check_declarations.py::check_path_refs | active |
| metadata-schema | metadata.json スキーマ | schemas/metadata.schema.json | allaganeye/metadata_types.py, gui/src/types/metadata.generated.ts | generated | ci:python:Verify generated metadata_types.py is up to date + ci:gui-frontend:Verify generated metadata.generated.ts is up to date | active |
| version-locations | バージョン保持箇所 | scripts/check_version_consistency.py | docs/versioning.md | checked | ci:version-check | active |
| error-hints | Tauri error と hint の対応 | gui/src-tauri/src/error.rs | docs/tauri-commands.md | checked | ci:doc-error-hint-drift | active |
| shipped-commands | 出荷サブコマンド集合 | allaganeye/cli.py | README.md, docs/quickstart.md | checked | ci:feature-announcement | active |
| model-routing | 用途別モデル割当 | AGENTS.md | docs/l2-workflow.md, .claude/agents/ | prose-only | none | active |
| gui-screens | GUI 画面数 6 | gui/src/screens | AGENTS.md, docs/gui-development.md, docs/ui-architecture.md, docs/ui-interaction-spec.md | prose-only | none | active |
| detection-modules | allaganeye モジュール一覧 | allaganeye | AGENTS.md | prose-only | none | active |
| codex-invocation | codex CLI の focus 渡し方 (`--base` と `[PROMPT]` の併用不可 / PROMPT 単独形式) | docs/l2-workflow.md | .agents/skills/review-pr/SKILL.md, .agents/skills/iterate-review/SKILL.md | prose-only | none | active |

## 備考

### mirror から外した spot (Phase 2 の判断)

- **`exit-codes`**: `docs/cli-spec.md` の per-command Exit Codes 表は「そのコマンドの挙動」の記述であり、全体表 (AGENTS.md) とは事実の粒度が違う。全部を機械突合すると散文まで縛るため、**AGENTS.md の全体表のみ**を検査対象にした。`output-spec.md` / `metadata-spec.md` の code 言及も同様に文脈記述
- **`tauri-commands-agents`**: 行を削除した。`AGENTS.md` の command 列挙をやめて [`docs/tauri-commands.md`](tauri-commands.md) へのポインタにしたため、複製そのものが消えた (#818 の「複製せずリンク」)。行の削除は test の id 集合 pin が検出する

### runtime-extract の理由

- `iron-law`: hook (`.claude/hooks/session-start.sh`) は本文を持たず、`AGENTS.md` §Iron Law を `awk` で切り出して注入する。複製を持たないことが gate の検査対象。`AGENTS.md` が無い場合は stderr に警告し、他の注入は継続する

### prose-only の理由

- `model-routing`: モデル名は外部サービス側の名称で、repo 内に機械可読な正が無い。**再確認トリガー**: モデルの追加・廃止 / ルーティング表の行追加・削除 / Zed の `spawn_agent` 仕様変更。変更時は `AGENTS.md` §モデルルーティング を起点に手動照合する
- `gui-screens`: 画面数はディレクトリから数えられるが、doc 側の「6 画面」は文脈付きの主張で、機械抽出すると誤検出が多い。**再確認トリガー**: `gui/src/screens/` への画面追加・削除。追加・削除時に ls して確認する
- `detection-modules`: `AGENTS.md` §モジュール構成 は索引であり、`detection/*` は行内で列挙される。完全一致を強制すると索引の自由度を失う。**再確認トリガー**: `allaganeye/` への module 追加・削除・rename。`scripts/check_doc_code_refs.py` の symbol 検査が rename を拾う
- `codex-invocation`: 検証対象は **外部 CLI (`codex`) の受理仕様**であり、CI に `codex` を持ち込まない方針のため機械検証しない。**再実測トリガー**: `codex` CLI を version up したとき / `codex review --help` の `[PROMPT]`・`--base` の記述が変わったとき。実測記録は `docs/l2-workflow.md` §Step 5 の invocation path の注記 (日付・version 付き)
