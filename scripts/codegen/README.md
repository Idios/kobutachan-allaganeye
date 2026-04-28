# scripts/codegen/

`metadata.json` の機械可読の正である [`schemas/metadata.schema.json`](../../schemas/metadata.schema.json) (draft-2020-12) から、言語別の型定義を自動生成する codegen エントリポイント。

派生 issue: [#612](https://github.com/Idios/kobutachan-allaganeye/issues/612) (方針確定 issue: [#556](https://github.com/Idios/kobutachan-allaganeye/issues/556))

## 生成対象

| 言語 | 出力ファイル | ツール |
|---|---|---|
| Python | [`allaganeye/metadata_types.py`](../../allaganeye/metadata_types.py) | `datamodel-code-generator` (TypedDict) |
| TypeScript | [`gui/src/types/metadata.generated.ts`](../../gui/src/types/metadata.generated.ts) | `json-schema-to-typescript` |

Rust 側 (`gui/src-tauri/src/lib.rs`) は `serde_json::Value` で passthrough し、本 codegen の対象外。

## 使い方

```bash
python scripts/codegen/generate.py        # 両言語生成
python scripts/codegen/generate.py --py   # Python のみ
python scripts/codegen/generate.py --ts   # TypeScript のみ
```

TypeScript 単独は `gui/` 配下で `npm run generate-types` でも実行可能。

## ワークフロー

1. **JSON Schema 編集**: `schemas/metadata.schema.json` のフィールドを追加・変更
2. **再生成**: `python scripts/codegen/generate.py` で両出力を更新
3. **doc 同期**: 必要に応じて [`docs/metadata-spec.md`](../../docs/metadata-spec.md) (人間可読の正) を更新
4. **zod 同期**: [`gui/src/types/metadata.schema.ts`](../../gui/src/types/metadata.schema.ts) の zod schema を JSON Schema と同じ field set に保つ。CI の `zod-schema-integrity.test.ts` がドリフトを検出する
5. **commit**: 生成物 (`metadata.generated.ts` / `metadata_types.py`) を必ず commit する。CI は `git diff --exit-code` で差分があれば fail する

詳細な編集ガイドは [`docs/l2-workflow.md`](../../docs/l2-workflow.md) §schema 編集ワークフロー を参照。

## CI

`.github/workflows/ci.yml`:

- `python` ジョブ: `python scripts/codegen/generate.py --py` 実行 → `git diff --exit-code allaganeye/metadata_types.py`
- `gui-frontend` ジョブ: `python scripts/codegen/generate.py --ts` 実行 → `git diff --exit-code gui/src/types/metadata.generated.ts`

差分が検出されたら "JSON Schema を編集したら `python scripts/codegen/generate.py` を再実行して commit してください" のメッセージで build fail。

## トラブルシューティング

- **改行差分**: Windows ↔ Linux で CRLF/LF が混ざると CI で diff 発生 → `.gitattributes` で `text eol=lf` 強制済み
- **datamodel-code-generator が見つからない**: `pip install -e ".[dev]"` で dev deps を入れ直す
- **json-schema-to-typescript が見つからない**: `cd gui && npm install` で dev deps を入れ直す
- **Python orchestrator から TS 生成失敗**: `node` が PATH にあるか確認 (`gui-frontend` CI ジョブは `actions/setup-node@v4` で導入済み、ローカルは Node 22+ 推奨)
