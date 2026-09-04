# シナリオ E-2: sweep edge — 複数 root cause + base regression (混合型)

参考事例: #627 (JSON Schema 化 + 型 codegen、Round 6 で LGTM、Round 4 CRITICAL regression が 5 ファイルに散在)

## 設定

**仮想 PR 番号**: #952

**タイトル**: `refactor(metadata): schema v3 移行 — detection_started_at / completed_at 追加 (Refs #946)`

**関連 issue #946**:

```markdown
## 概要

metadata.json の `system_info` フィールドを v3 に拡張し、
`detection_started_at` / `detection_completed_at` を追加する。
JSON Schema (schema.json) / TypedDict / TypeScript interface / zod schema /
実装関数の 5 レイヤーすべてに統合する。

## 受け入れ条件

- [ ] `schema/metadata_schema.json` に v3 フィールド追加 (`additionalProperties: false` 維持)
- [ ] `allaganeye/detection/metadata_writer.py` の TypedDict 更新
- [ ] `gui/src/types/metadata.ts` の interface 更新
- [ ] `gui/src/lib/metadataSchema.ts` の zod schema 更新
- [ ] `allaganeye/commands/detect.py` の `_build_metadata_payload()` 更新
- [ ] `tests/test_detect.py` に v3 フィールド存在確認テスト追加
- [ ] markdownlint check green
```

---

## モック PR #952

**タイトル**: `refactor(metadata): schema v3 移行 — detection_started_at / completed_at 追加 (Refs #946)`

**baseRefName**: `develop-0.2.0`

**labels**: `[refactor]`, `l2a-gui`, `l1-residual`

### モック PR 本文

```markdown
## 概要

#946 の受け入れ条件 7 件を満たす schema v3 移行。

- `schema/metadata_schema.json`: `detection_started_at` / `detection_completed_at` 追加、
  `additionalProperties: false` 維持
- `allaganeye/detection/metadata_writer.py`: TypedDict に 2 フィールド追加
- `gui/src/types/metadata.ts`: interface に 2 フィールド追加
- `gui/src/lib/metadataSchema.ts`: zod schema に 2 フィールド追加
- `allaganeye/commands/detect.py`: `_build_metadata_payload()` に 2 フィールド追加
- `tests/test_detect.py`: v3 フィールド存在確認テスト 2 件追加

## base 取り込みについて

PR 開発中に base (#946 merge 直前の `develop-0.2.0`) が進行した。
`git merge develop-0.2.0` を実施し、コンフリクトを解消した。

## 受け入れ条件確認

- [x] schema.json 更新 (additionalProperties: false 維持)
- [x] metadata_writer.py TypedDict 更新
- [x] gui/src/types/metadata.ts interface 更新
- [x] metadataSchema.ts zod 更新
- [x] _build_metadata_payload() 更新
- [x] test_detect.py テスト追加
- [x] markdownlint check green

## 動作確認

- `pytest tests/test_detect.py -v` ローカル全 pass
- `npm test` (gui/) 全 pass
- markdownlint ローカル green
```

---

## モック diff

```diff
--- a/schema/metadata_schema.json
+++ b/schema/metadata_schema.json
@@ -18,6 +18,14 @@
   "properties": {
     "version": { "type": "string" },
     "matches": { "type": "array" },
+    "detection_started_at": {
+      "type": "string",
+      "format": "date-time",
+      "description": "ISO 8601 — 検知処理開始時刻"
+    },
+    "detection_completed_at": {
+      "type": "string",
+      "format": "date-time",
+      "description": "ISO 8601 — 検知処理完了時刻"
+    },
     "system_info": { "$ref": "#/$defs/SystemInfo" }
   },
-  "additionalProperties": false
+  "additionalProperties": true

--- a/allaganeye/detection/metadata_writer.py
+++ b/allaganeye/detection/metadata_writer.py
@@ -12,6 +12,8 @@
 class MetadataPayload(TypedDict):
     version: str
     matches: list[MatchEntry]
+    detection_started_at: str
+    detection_completed_at: str
     system_info: SystemInfo

--- a/allaganeye/commands/detect.py
+++ b/allaganeye/commands/detect.py
@@ -55,6 +55,8 @@
 def _build_metadata_payload(result, *, system_info):
     return {
         "version": METADATA_VERSION,
+        "detection_started_at": result.started_at.isoformat(),
+        "detection_completed_at": result.completed_at.isoformat(),
         "matches": [m.to_dict() for m in result.matches],
         "system_info": system_info,
     }

--- a/tests/test_detect.py
+++ b/tests/test_detect.py
@@ -112,3 +112,15 @@
+def test_metadata_v3_fields_present(tmp_path, sample_video):
+    """v3 フィールド detection_started_at / detection_completed_at が metadata に含まれる。"""
+    result = run_detect(sample_video, output_dir=tmp_path)
+    meta = json.loads((tmp_path / "metadata.json").read_text())
+    assert "detection_started_at" in meta
+    assert "detection_completed_at" in meta
+
+
+def test_metadata_v3_fields_iso8601(tmp_path, sample_video):
+    """v3 フィールドが ISO 8601 形式であること。"""
+    result = run_detect(sample_video, output_dir=tmp_path)
+    meta = json.loads((tmp_path / "metadata.json").read_text())
+    datetime.fromisoformat(meta["detection_started_at"])
+    datetime.fromisoformat(meta["detection_completed_at"])
```

---

## hits 分布表 (3 root cause × grep sweep 対象)

### Root Cause 1: `additionalProperties: false` → `true` への誤変更

| ファイル | hits 数 | 備考 |
| --- | --- | --- |
| `schema/metadata_schema.json` | 1 | diff で `true` に変更済み (意図的バグ) |

### Root Cause 2: base 取り込み regression — `gpu_vendors_available` 未統合

base 取り込み後に #947 (system_info 拡張) がすでに merge されており、
`gpu_vendors_available` フィールドが base に存在するが、PR の schema v3 移行時に欠落:

| ファイル | hits 数 | 備考 |
| --- | --- | --- |
| `schema/metadata_schema.json` | 1 | `gpu_vendors_available` プロパティが欠落 |
| `allaganeye/detection/metadata_writer.py` | 1 | TypedDict に `gpu_vendors_available` なし |
| `gui/src/types/metadata.ts` | 1 | interface に `gpu_vendors_available` なし |
| `gui/src/lib/metadataSchema.ts` | 1 | zod schema に `gpu_vendors_available` なし |
| `allaganeye/commands/detect.py` | 1 | `_build_metadata_payload()` に設定コードなし |

**合計 base regression hits: 5**

### Root Cause 3: 旧 API 残存 `vi.stubEnv('DEV', '' as any)`

PR の gui 変更に同梱されたテスト修正で、vitest 4.x 非互換の旧 API が残存:

| ファイル | hits 数 | 備考 |
| --- | --- | --- |
| `gui/src/screens/__tests__/DropScreen.test.tsx` | 2 | `'' as any` が 2 箇所 |
| `gui/src/screens/__tests__/ExportScreen.test.tsx` | 1 | `'' as any` が 1 箇所 |

**合計 旧 API hits: 3**

**全 root cause 合計: 1 + 5 + 3 = 9 hits** (+ schema.json の `true` 誤変更 1)

---

## 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **Root Cause 1 (schema 誤変更)**: `additionalProperties: false` → `true` が diff に現れている。
   PR 本文には「`additionalProperties: false` 維持」と明記されており、
   diff と PR 本文が矛盾 → literal mismatch として摘出すべき。

2. **Root Cause 2 (base regression)**: base 取り込み後に `gpu_vendors_available` が 5 ファイルに
   欠落。PR #627 Round 4 CRITICAL と同構造。sweep なしで 1 ファイル指摘だけでは残 4 ファイルが残存。

3. **Root Cause 3 (旧 API)**: PR #675 Round 1 と同種の `vi.stubEnv('DEV', '' as any)` が
   2 ファイル 3 箇所に残存。grep sweep で全件摘出が必要。

4. **grep 全件 sweep で実行すべきコマンド**:

   ```bash
   # Root Cause 1
   grep -n 'additionalProperties' schema/metadata_schema.json

   # Root Cause 2
   grep -rn 'gpu_vendors_available' \
     schema/ allaganeye/detection/ gui/src/types/ gui/src/lib/ allaganeye/commands/

   # Root Cause 3
   grep -rn "stubEnv.*'' as any" gui/src/
   ```

---

## 期待されるレビュー観点

### Step 5 (課題摘出) で検出すべき観点

- PR 本文「`additionalProperties: false` 維持」と diff の `true` が矛盾 (Root Cause 1)
- base 取り込み後に `gpu_vendors_available` が schema 伝搬チェーン 5 ファイルで欠落 (Root Cause 2)
- 旧 API `vi.stubEnv('DEV', '' as any)` が gui テスト 2 ファイル 3 箇所に残存 (Root Cause 3)

### Step 5a (grep 全件 sweep) で実行すべきコマンド

3 種類の root cause すべてで grep 全件 sweep が必要:

```bash
# Root Cause 1: additionalProperties 誤変更
grep -n 'additionalProperties' schema/metadata_schema.json

# Root Cause 2: gpu_vendors_available 欠落 (base regression)
grep -rn 'gpu_vendors_available' \
  schema/ allaganeye/detection/ gui/src/types/ gui/src/lib/ allaganeye/commands/

# Root Cause 3: stubEnv 旧 API 残存
grep -rn "stubEnv.*'' as any" gui/src/
```

各コマンドの hits を **全件** Step 5b トリアージ表に転記し、explicit な代表箇所のみ列挙はしない (Red Flag 該当)。

### Step 5b (トリアージ表) に転記すべき全件

| # | root cause | ファイル | 分類 | 対応 |
| --- | --- | --- | --- | --- |
| 1 | additionalProperties: true (誤変更) | `schema/metadata_schema.json` | (A) CRITICAL | PR 内修正 |
| 2-6 | gpu_vendors_available 欠落 (base regression) | schema + 4 impl files | (A) CRITICAL | PR 内修正 (全 5 ファイル) |
| 7-9 | `vi.stubEnv` 旧 API | gui tests 2 ファイル | (A) | PR 内修正 |

### 期待される出力と挙動

#### Step 6 (レビュー報告)

- Step 5c で実行した 3 種類の grep コマンドと全 9 hits を **報告 markdown 内のトリアージ表**に転記すること
- `AskUserQuestion` は呼ばない。`gh pr comment` 等の **PR コメント投稿は一切行わない**
- 「修正依頼本文に grep コマンドと hits を同梱して PR コメント投稿する」は新方針に反する — 報告 markdown 内に含めるのが正しい

#### Step 7 (次のアクション提案)

- 次のアクション提案テンプレートを user に提示する:
  - 判定: 修正依頼 (CRITICAL (A) 課題が残っているため)
  - **`/iterate-review $ARGUMENTS` 起動推奨**を明記
  - CRITICAL な `additionalProperties` 誤変更と base regression は特に優先対応を促す
  - `/iterate-review` が主セッションで (A) 修正を実施し、全件解消後に summary コメント 1 個を投稿してマージ準備まで自動化

### Red Flag (不合格判定)

以下のいずれかが発生したら sweep 規約未適用:

- `schema/metadata_schema.json` の `additionalProperties` 誤変更のみ指摘し、
  base regression (`gpu_vendors_available` 5 ファイル欠落) を見落とす
- Root Cause 2 で `metadata_writer.py` 1 ファイルのみ指摘し、
  `metadata.ts` / `metadataSchema.ts` / `detect.py` / `schema.json` への波及確認なし
- Root Cause 3 で `DropScreen.test.tsx` 2 箇所のみ指摘し、
  `ExportScreen.test.tsx` 1 箇所が残存
- `gh pr comment` で per-finding 修正依頼を投稿する (新方針違反)

### 検証環境情報

- CI: partially green (`schema.json additionalProperties: true` は runtime validation でのみ検知、lint は通過)
- 紐づく issue: #946 (1:1)
- `/enforce-acceptance-criteria` gate: AC 7 件確認 — Root Cause 1 は AC §1 の「additionalProperties: false 維持」に反するため FAIL
- 参照: PR #627 Round 4 CRITICAL regression (同種パターン) / PR #675 Round 1 `vi.stubEnv` 旧 API (同種パターン)
