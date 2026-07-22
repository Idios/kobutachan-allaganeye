# #879 metadata.json optional field write 境界検証硬化 設計 (2026-07-22)

> **Status**: design (approved by Idios via brainstorming, 2026-07-22)
> **Issue**: #879 (task) / 出自: PR #877 codex adversarial-review F2 (Idios 確定 2026-07-07)
> **Base**: develop-0.3.0 (v0.3.0 scope、「#860 も含め全 quality 消化後に release」方針)
> **由来**: session `l3-residual-plan` brainstorming で Idios が PR 分割 (1 PR) / minimap_regions 包含 (4 field 完全 mirror) を確定

## 1. 背景 / 問題

metadata.json / .detection_cache.json の optional field が present だが malformed なとき、write 境界で検出されず persist され、GUI zod が reload できない metadata.json や、boundaries と provenance が別 snapshot の cache payload が生成されうる (codex adversarial-review F2)。3 つの死角がある:

| # | 層 | 現状 | 死角 |
| --- | --- | --- | --- |
| 1 | Rust `validate_metadata_for_write` (`gui/src-tauri/src/lib.rs:945`) | required field + match/gap boundaries のみ zod mirror | optional field (system_info / brightness_samples / capture_regions / minimap_regions) の shape 非検証 → present + malformed が素通りして persist → GUI reload 時に初めて zod reject (診断コスト高) |
| 2 | CLI brightness_samples preserve (`split_matches.py` `--from-metadata`, L479-482) | `isinstance(dict)` チェックのみ | interval_s / values の shape 非検証 → malformed brightness_samples が新 metadata.json に混入 |
| 3 | cache read (`detect.py:146-149` / `split_matches.py:186-187`) | `_load_cache` (boundaries) + `_read_cached_masked_fallback` + `_read_cached_capture_regions` の**三重 file open** | 3 read の間に外部書換があると、検証済み boundaries と別 snapshot の provenance (masked_fallback_used / capture_regions) が結合されうる (#821 の `masked_fallback_used` 導入時からの pre-existing クラス) |

### ユーザー影響

手編集・破損した metadata.json / .detection_cache.json 経由で、GUI が読めない metadata.json が silent に生成されうる。発生時の診断コストが高い (write 側でなく read 側で初めて故障が見える)。

## 2. 確定スコープ (brainstorming)

| 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- |
| PR 分割 | 1 PR / 2 PR (write 検証 + cache refactor) | **1 PR** | issue 単位を保ち close が単純。diff 中規模見込み (refactor-pattern の 30 file/1000 line 基準未満) |
| Rust 検証対象 | 3 field (issue literal) / 4 field 完全 mirror | **4 field (minimap_regions 含む)** | 同クラスの検証欠落 (minimap_regions だけ素通り) を残さず zod と対称。Idios full 硬化選好 (`feedback_released_ipc_validation_scope`) |

## 3. Layer 1 — Rust optional shape 検証

`validate_metadata_for_write` (`gui/src-tauri/src/lib.rs`) に 4 optional field の **present 時 shape 検証**を追加。absent は OK (全 optional)、unknown key は passthrough 維持 (zod `.passthrough()` と同じく既知 optional のみ検証)。失敗は既存 `schema_err`（`parse.schema_invalid`）。apply_changes が backup/write の前に reject するため、GUI は既存 error path (ConflictModal ではない)。

### 3.1 共通ヘルパ

```rust
/// CaptureRegion shape (mirror zod CaptureRegionSchema): x/y/w/h/confidence
/// are numbers in [0,1], source is a non-empty string. Used by
/// capture_regions.coarse, capture_regions.segments[].region, and
/// minimap_regions[].region.
fn validate_capture_region(v: &Value, ctx: &str) -> Result<(), AppError>;
```

- coord 5 key は `Value::as_f64` で数値かつ `0.0..=1.0`、`source` は `as_str` で非空。zod は key 過不足を厳密化しないが (`z.object` は extra key を strip して valid 扱い)、**readable であることが契約**なので Rust 側は「必要 key が正しい型で present」を検証 (extra key は許容 = zod strip 相当で reload 可能)。

### 3.2 各 field (present 時のみ)

- `system_info` (object): `gpu_vendors_available` = string 配列、`gpu_vendor_used` = string または null、`vendor_preference` = string 配列。`gpu` は present なら string 配列。
- `brightness_samples` (object): `interval_s` = 正の有限数、`values` = 各要素が `0.0..=255.0` の数値配列。
- `capture_regions` (object): `coarse` = Region、`segments` = 配列で各要素 `time_range` = 長さ 2 の各 `>= 0` 有限数配列 + `region` = Region、`fallback_reason` = string または null。
- `minimap_regions` (array): 各要素 `match_index` = 1 以上の整数、`region` = Region。

### 3.3 zod mirror の粒度

zod `SystemInfoSchema` は `gpu_vendors_available: z.array(z.string())` 等を要求する。Rust は「present かつ型不一致」を reject し、GUI reload と同じ判定にする。**purpose = GUI zod が reject する payload を write 前に止める**ため、zod より緩くも厳しくもしない (数値 range・非空 str・null 許容を zod と一致させる)。

## 4. Layer 2 — CLI brightness_samples sanitize

`allaganeye/commands/split_matches.py` に `_sanitize_brightness_samples(value) -> BrightnessSamples | None` を `_sanitize_capture_regions` (L2097) 同型で新設:

- `value` が dict で key が厳密に `{interval_s, values}`。
- `interval_s`: bool 排除の有限実数 (int/float) かつ `> 0`。
- `values`: list で各要素が bool 排除の有限実数かつ `0.0 <= v <= 255.0` (NaN/Inf reject — `_sanitize_capture_regions` の R3-1 と同理由: `json.dumps(allow_nan=True)` が非標準 token を emit し GUI serde_json が全体 reject する)。
- 全 valid で `cast("BrightnessSamples", value)`、else `None`。

`--from-metadata` preserve (現 L479-482 の `isinstance(dict)` 判定) を `_sanitize_brightness_samples` に置換。malformed → omit + warning (capture_regions F1 と同 pattern、`sanitize_warnings` #805 と同 philosophy)。

## 5. Layer 3 — cache 単一 read

cache-hit で file を **1 回だけ** open し、boundaries と provenance を同一 parsed dict から取り出す。

### 5.1 新 API

```python
@dataclass(frozen=True)
class CacheHit:
    boundaries: list[...]                 # 現 _load_cache の戻り値型
    masked_fallback_used: bool
    capture_regions: "CaptureRegions | None"

def _load_cache_hit(cache_path, video_path, interval, config) -> "CacheHit | None":
    """cache を 1 回 read し、key 検証 + boundaries + provenance を同一 snapshot
    から返す。cache miss / key 不一致は None。"""
```

- `_load_cache_hit` は file を 1 回 read → parsed `data: dict` を得て、(a) 現 `_load_cache` の cache key 検証 (source/mtime/params)、(b) boundaries 抽出、(c) `masked_fallback_used` / `capture_regions` 抽出を同一 dict から行う。
- `_read_cached_masked_fallback` / `_read_cached_capture_regions` を **file 再 open せず parsed `data: dict`（+ 必要な params）を受ける純関数**にシグネチャ変更。legacy 合成ロジック (params.vtuber==False && masked_fallback_used==False → FULL_FRAME、round-2 codex 裁定) は保持。
- `_load_cache` は **boundary-only の既存 caller / テスト用**に `_load_cache_hit(...)` の `.boundaries` を返す薄い wrapper として残す (後方互換、file read は 1 回)。

### 5.2 call site 移行

- `detect.py:146-149`: `boundaries = _load_cache(...)` → `_load_cache_hit(...)` 1 回に統合し `.boundaries` / `.masked_fallback_used` / `.capture_regions` を使う。
- `split_matches.py:186-187`: 同様に単一 read に移行。
- 結果、**検証済み boundaries と provenance は構造的に必ず同一 snapshot** (mixed-snapshot 不能)。

## 6. テスト方針 (TDD, Red-Green)

### Rust (`gui/src-tauri/src/lib.rs` tests)

- 4 optional field それぞれ: present + valid → Ok、present + malformed (型不一致 / range 外 / 非空 str 違反 / null 不許容箇所に null) → Err(parse.schema_invalid)、absent → Ok。
- `validate_capture_region` を coarse / segments[].region / minimap_regions[].region で共用する分岐カバー。
- zod 対称 pin: zod schema にある制約 (0-1 range / >=1 int / positive 等) を逐条で 1 ケースずつ。

### CLI (`tests/test_split_matches.py` 相当)

- `_sanitize_brightness_samples`: valid / key 過不足 / interval_s <=0 / bool / NaN / values 範囲外 / values 非 list → 期待の pass/None。
- preserve 経路: malformed brightness_samples 入力 → 新 metadata から omit + warning 出力。

### cache (`tests/test_split_matches.py` / `tests/test_detect.py` 相当)

- `_load_cache_hit` が cache-hit で `read_text` を **1 回だけ** 呼ぶ (mock call_count == 1) — 三重 read 解消の pin。
- boundaries + provenance が同一 dict 由来 (mock で 2 回目以降の read 内容を変えても結果が最初の snapshot に一致)。
- legacy 合成保持 (vtuber==False && masked_fallback_used==False の pre-#810 cache → FULL_FRAME 合成)。
- `_read_cached_masked_fallback` / `_read_cached_capture_regions` を dict 引数純関数として単体テスト。

## 7. 実機検証 (Iron Law 6)

released path (GUI Tauri `apply_changes` write 境界 + CLI cache 経路)。着手完了後に Idios へ `AskUserQuestion` で:

- GUI: 正常 metadata.json の load → 編集 → apply が従来どおり通る (regression 無し)。malformed optional field を手で仕込んだ metadata.json を apply しようとすると schema_err で拒否される。
- CLI: cache-hit の detect / split --from-metadata が従来どおり動作 (provenance = masked_fallback_used / capture_regions が正しく引き継がれる)。

## 8. スコープ外

- unknown-key の厳格化 (additionalProperties:false 相当)。zod は passthrough なので現状維持。
- brightness_samples 以外の CLI preserve 経路の追加 sanitize (system_info 等は CLI 側で writer が構築するため malformed preserve 経路が無い)。

## 9. 参照

- issue: #879 / 出自: PR #877 codex adversarial-review F2
- 関連: #814 (apply_changes write-side guard) / #821 (masked_fallback_used) / #810 (capture_regions) / #877 (`_sanitize_capture_regions` F1)
- zod schema: `gui/src/types/metadata.schema.ts` (SystemInfoSchema / BrightnessSamplesSchema / CaptureRegionsSchema / MinimapRegionEntrySchema)
- 既存 sanitizer: `_sanitize_capture_regions` (`allaganeye/commands/split_matches.py:2097`) / `sanitize_warnings` (`allaganeye/detection/warnings.py`)
- memory: `feedback_released_ipc_validation_scope` (full 硬化選好) / `feedback_partial_rerun_writeback_merge` (run 跨ぎ state 死角) / `feedback_superpowers_docs_markdownlint` (spec/plan は commit 前 markdownlint --fix)
