# #879 metadata write 境界検証硬化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** metadata.json の optional field が present だが malformed なとき write 境界で検出し、GUI zod が reload できない metadata.json や mixed-snapshot cache payload が persist されないようにする。

**Architecture:** 3 層。(1) Rust `validate_metadata_for_write` に 4 optional field の present 時 shape 検証を zod mirror で追加。(2) CLI に `_sanitize_brightness_samples` を新設し `--from-metadata` preserve を硬化。(3) cache-hit の三重 file read を単一 read (`_load_cache_hit` + `CacheHit` dataclass) に統合し、`_load_cache` を廃止・全 caller 移行。

**Tech Stack:** Rust (serde_json::Value, tauri), Python 3 (dataclass, pytest), cargo test。

## Global Constraints

- spec: `docs/superpowers/specs/2026-07-22-issue-879-metadata-write-validation-hardening-design.md`。
- Rust 検証は **present 時のみ**。absent = Ok (全 optional)。unknown key は reject しない (zod passthrough/strip はどちらも reload 可能 = readable)。失敗は `AppError::new("parse.schema_invalid", msg).with_default_hint()`。
- Rust 検証は zod と **同じ緩さ/厳しさ**にする (数値 range・非空 str・null 許容・int-valued float 許容を zod と一致)。GUI reload が reject する payload だけを止める。
- CLI sanitize は `_sanitize_capture_regions` (`split_matches.py:2097`) と同 pattern: bool 排除・NaN/Inf reject・厳密 key set・malformed は `None` → omit + warning。
- cache-hit の file open は **1 回のみ**。boundaries と provenance (masked_fallback_used / capture_regions) は同一 parsed dict 由来。`_load_cache` は廃止し全 caller を `_load_cache_hit` に移行。
- 既存の隣接テストの assert を削除しない (append/migrate のみ)。base = `develop-0.3.0`、branch = `claude/issue-879-metadata-write-hardening`。Co-Authored-By: `Claude Fable 5 <noreply@anthropic.com>`。
- 各タスク完了時のコミットは `--no-gpg-sign`。編集は絶対パスで着弾。commit 前に `git symbolic-ref --short HEAD` == `claude/issue-879-metadata-write-hardening` を確認。

---

### Task 1: Rust — `validate_capture_region` 共通ヘルパ + `capture_regions` / `minimap_regions` 検証

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (`validate_metadata_for_write` の手前にヘルパ追加 + 関数末尾 `Ok(())` の前に wiring、tests mod にテスト追加)

**Interfaces:**

- Consumes: 既存 `AppError::new(code, msg).with_default_hint()`、`serde_json::Value`。
- Produces: `fn schema_invalid(msg: String) -> AppError` / `fn validate_capture_region(v: &Value, ctx: &str) -> Result<(), AppError>` / `fn validate_capture_regions(v: &Value) -> Result<(), AppError>` / `fn validate_minimap_regions(v: &Value) -> Result<(), AppError>`。

- [ ] **Step 1: Write the failing tests**

`gui/src-tauri/src/lib.rs` の `mod tests` 内 (`valid_metadata_payload` の後) に追加:

```rust
    #[test]
    fn write_validation_accepts_valid_capture_regions() {
        let mut p = valid_metadata_payload();
        p["capture_regions"] = json!({
            "coarse": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "confidence": 1.0, "source": "full_frame"},
            "segments": [{"time_range": [0.0, 100.0], "region": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5, "confidence": 0.9, "source": "scorebar"}}],
            "fallback_reason": null
        });
        assert!(validate_metadata_for_write(&p).is_ok());
    }

    #[test]
    fn write_validation_rejects_capture_region_coord_out_of_range() {
        let mut p = valid_metadata_payload();
        p["capture_regions"] = json!({
            "coarse": {"x": 1.5, "y": 0.0, "w": 1.0, "h": 1.0, "confidence": 1.0, "source": "full_frame"},
            "segments": [],
            "fallback_reason": null
        });
        let err = validate_metadata_for_write(&p).unwrap_err();
        assert_eq!(err.code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_rejects_capture_region_empty_source() {
        let mut p = valid_metadata_payload();
        p["capture_regions"] = json!({
            "coarse": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "confidence": 1.0, "source": ""},
            "segments": [],
            "fallback_reason": null
        });
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_rejects_segment_time_range_wrong_len() {
        let mut p = valid_metadata_payload();
        p["capture_regions"] = json!({
            "coarse": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "confidence": 1.0, "source": "full_frame"},
            "segments": [{"time_range": [0.0], "region": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5, "confidence": 0.9, "source": "scorebar"}}],
            "fallback_reason": null
        });
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_accepts_valid_minimap_regions() {
        let mut p = valid_metadata_payload();
        p["minimap_regions"] = json!([
            {"match_index": 1, "region": {"x": 0.8, "y": 0.8, "w": 0.15, "h": 0.15, "confidence": 1.0, "source": "user"}},
            {"match_index": 2.0, "region": {"x": 0.8, "y": 0.8, "w": 0.15, "h": 0.15, "confidence": 1.0, "source": "user"}}
        ]);
        assert!(validate_metadata_for_write(&p).is_ok());
    }

    #[test]
    fn write_validation_rejects_minimap_match_index_below_one() {
        let mut p = valid_metadata_payload();
        p["minimap_regions"] = json!([
            {"match_index": 0, "region": {"x": 0.8, "y": 0.8, "w": 0.15, "h": 0.15, "confidence": 1.0, "source": "user"}}
        ]);
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_capture_regions_absent_is_ok() {
        let p = valid_metadata_payload();
        assert!(validate_metadata_for_write(&p).is_ok());
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd gui/src-tauri && cargo test write_validation_ 2>&1 | tail -20`
Expected: 新テストのうち reject 系 (`rejects_...`) が FAIL (現状 optional field 非検証で Ok が返る)。accept/absent 系は PASS。

- [ ] **Step 3: Add helper functions**

`gui/src-tauri/src/lib.rs` の `fn validate_metadata_for_write` の**直前**に追加:

```rust
/// #879 -- shared AppError constructor for optional-field shape violations.
fn schema_invalid(msg: String) -> AppError {
    AppError::new("parse.schema_invalid", msg).with_default_hint()
}

/// #879 -- CaptureRegion shape (mirror zod CaptureRegionSchema): x/y/w/h/
/// confidence are numbers in [0,1]; source is a non-empty string. Shared by
/// capture_regions.coarse, capture_regions.segments[].region, and
/// minimap_regions[].region. Extra keys are allowed (zod strips them; the doc
/// stays readable).
fn validate_capture_region(v: &Value, ctx: &str) -> Result<(), AppError> {
    let obj = v
        .as_object()
        .ok_or_else(|| schema_invalid(format!("{ctx} must be an object")))?;
    for key in ["x", "y", "w", "h", "confidence"] {
        match obj.get(key).and_then(Value::as_f64) {
            Some(n) if (0.0..=1.0).contains(&n) => {}
            _ => return Err(schema_invalid(format!("{ctx}.{key} must be a number in [0,1]"))),
        }
    }
    match obj.get("source").and_then(Value::as_str) {
        Some(s) if !s.is_empty() => {}
        _ => return Err(schema_invalid(format!("{ctx}.source must be a non-empty string"))),
    }
    Ok(())
}

/// #879 -- capture_regions shape (mirror zod CaptureRegionsSchema).
fn validate_capture_regions(v: &Value) -> Result<(), AppError> {
    let obj = v
        .as_object()
        .ok_or_else(|| schema_invalid("metadata.capture_regions must be an object".into()))?;
    let coarse = obj
        .get("coarse")
        .ok_or_else(|| schema_invalid("metadata.capture_regions.coarse is required".into()))?;
    validate_capture_region(coarse, "metadata.capture_regions.coarse")?;
    let segments = obj
        .get("segments")
        .and_then(Value::as_array)
        .ok_or_else(|| schema_invalid("metadata.capture_regions.segments must be an array".into()))?;
    for (i, seg) in segments.iter().enumerate() {
        let so = seg.as_object().ok_or_else(|| {
            schema_invalid(format!("metadata.capture_regions.segments[{i}] must be an object"))
        })?;
        let tr = so.get("time_range").and_then(Value::as_array).ok_or_else(|| {
            schema_invalid(format!("metadata.capture_regions.segments[{i}].time_range must be an array"))
        })?;
        if tr.len() != 2 || !tr.iter().all(|t| matches!(t.as_f64(), Some(n) if n >= 0.0)) {
            return Err(schema_invalid(format!(
                "metadata.capture_regions.segments[{i}].time_range must be [n>=0, n>=0]"
            )));
        }
        let region = so.get("region").ok_or_else(|| {
            schema_invalid(format!("metadata.capture_regions.segments[{i}].region is required"))
        })?;
        validate_capture_region(region, &format!("metadata.capture_regions.segments[{i}].region"))?;
    }
    match obj.get("fallback_reason") {
        Some(Value::String(_)) | Some(Value::Null) => {}
        _ => {
            return Err(schema_invalid(
                "metadata.capture_regions.fallback_reason must be a string or null".into(),
            ))
        }
    }
    Ok(())
}

/// #879 -- minimap_regions shape (mirror zod array of MinimapRegionEntrySchema).
/// match_index mirrors z.number().int().min(1): accept int-valued floats (2.0)
/// as zod does, reject non-integers and < 1.
fn validate_minimap_regions(v: &Value) -> Result<(), AppError> {
    let arr = v
        .as_array()
        .ok_or_else(|| schema_invalid("metadata.minimap_regions must be an array".into()))?;
    for (i, entry) in arr.iter().enumerate() {
        let eo = entry.as_object().ok_or_else(|| {
            schema_invalid(format!("metadata.minimap_regions[{i}] must be an object"))
        })?;
        match eo.get("match_index").and_then(Value::as_f64) {
            Some(n) if n >= 1.0 && n.fract() == 0.0 => {}
            _ => {
                return Err(schema_invalid(format!(
                    "metadata.minimap_regions[{i}].match_index must be an integer >= 1"
                )))
            }
        }
        let region = eo.get("region").ok_or_else(|| {
            schema_invalid(format!("metadata.minimap_regions[{i}].region is required"))
        })?;
        validate_capture_region(region, &format!("metadata.minimap_regions[{i}].region"))?;
    }
    Ok(())
}
```

- [ ] **Step 4: Wire into `validate_metadata_for_write`**

`fn validate_metadata_for_write` の末尾、gaps ループの後・`Ok(())` の前に追加:

```rust
    // #879 -- optional field shape validation (present only, mirror zod).
    if let Some(cr) = obj.get("capture_regions") {
        validate_capture_regions(cr)?;
    }
    if let Some(mr) = obj.get("minimap_regions") {
        validate_minimap_regions(mr)?;
    }

    Ok(())
```

(既存の `Ok(())` を上記ブロックで置換する。)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd gui/src-tauri && cargo test write_validation_ 2>&1 | tail -20`
Expected: 新テスト全 PASS。

- [ ] **Step 6: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit --no-gpg-sign -m "feat(#879): Rust write-validation for capture_regions/minimap_regions

Refs #879

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Rust — `system_info` / `brightness_samples` 検証

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (ヘルパ 2 つ追加 + wiring 2 行追加、tests 追加)

**Interfaces:**

- Consumes: `schema_invalid` (Task 1)。
- Produces: `fn validate_system_info(v: &Value) -> Result<(), AppError>` / `fn validate_brightness_samples(v: &Value) -> Result<(), AppError>`。

- [ ] **Step 1: Write the failing tests**

`mod tests` に追加:

```rust
    #[test]
    fn write_validation_accepts_valid_system_info() {
        let mut p = valid_metadata_payload();
        p["system_info"] = json!({
            "gpu_vendors_available": ["nvidia"],
            "gpu_vendor_used": "nvidia",
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": ["NVIDIA RTX 5090 (32GB VRAM)"]
        });
        assert!(validate_metadata_for_write(&p).is_ok());
    }

    #[test]
    fn write_validation_accepts_system_info_null_vendor_used_no_gpu() {
        let mut p = valid_metadata_payload();
        p["system_info"] = json!({
            "gpu_vendors_available": [],
            "gpu_vendor_used": null,
            "vendor_preference": ["nvidia"]
        });
        assert!(validate_metadata_for_write(&p).is_ok());
    }

    #[test]
    fn write_validation_rejects_system_info_nonstring_vendor() {
        let mut p = valid_metadata_payload();
        p["system_info"] = json!({
            "gpu_vendors_available": [1],
            "gpu_vendor_used": null,
            "vendor_preference": []
        });
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_rejects_system_info_missing_vendor_used_key() {
        let mut p = valid_metadata_payload();
        p["system_info"] = json!({
            "gpu_vendors_available": [],
            "vendor_preference": []
        });
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_accepts_valid_brightness_samples() {
        let mut p = valid_metadata_payload();
        p["brightness_samples"] = json!({"interval_s": 2.0, "values": [0.0, 128.0, 255.0]});
        assert!(validate_metadata_for_write(&p).is_ok());
    }

    #[test]
    fn write_validation_rejects_brightness_samples_nonpositive_interval() {
        let mut p = valid_metadata_payload();
        p["brightness_samples"] = json!({"interval_s": 0.0, "values": [1.0]});
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }

    #[test]
    fn write_validation_rejects_brightness_samples_value_out_of_range() {
        let mut p = valid_metadata_payload();
        p["brightness_samples"] = json!({"interval_s": 2.0, "values": [300.0]});
        assert_eq!(validate_metadata_for_write(&p).unwrap_err().code, "parse.schema_invalid");
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd gui/src-tauri && cargo test write_validation_ 2>&1 | tail -20`
Expected: reject 系が FAIL (未検証)、accept 系は PASS。

- [ ] **Step 3: Add helper functions**

Task 1 で追加した `validate_minimap_regions` の後に追加:

```rust
/// #879 -- system_info shape (mirror zod SystemInfoSchema). gpu_vendors_available
/// / vendor_preference are required string arrays; gpu_vendor_used is a required
/// string-or-null; gpu is an optional string array.
fn validate_system_info(v: &Value) -> Result<(), AppError> {
    let obj = v
        .as_object()
        .ok_or_else(|| schema_invalid("metadata.system_info must be an object".into()))?;
    let is_string_array = |val: Option<&Value>| {
        matches!(val, Some(Value::Array(a)) if a.iter().all(Value::is_string))
    };
    for key in ["gpu_vendors_available", "vendor_preference"] {
        if !is_string_array(obj.get(key)) {
            return Err(schema_invalid(format!(
                "metadata.system_info.{key} must be an array of strings"
            )));
        }
    }
    match obj.get("gpu_vendor_used") {
        Some(Value::String(_)) | Some(Value::Null) => {}
        _ => {
            return Err(schema_invalid(
                "metadata.system_info.gpu_vendor_used must be a string or null".into(),
            ))
        }
    }
    if obj.contains_key("gpu") && !is_string_array(obj.get("gpu")) {
        return Err(schema_invalid(
            "metadata.system_info.gpu must be an array of strings".into(),
        ));
    }
    Ok(())
}

/// #879 -- brightness_samples shape (mirror zod BrightnessSamplesSchema):
/// interval_s is a positive number; values is an array of numbers in [0,255].
fn validate_brightness_samples(v: &Value) -> Result<(), AppError> {
    let obj = v
        .as_object()
        .ok_or_else(|| schema_invalid("metadata.brightness_samples must be an object".into()))?;
    match obj.get("interval_s").and_then(Value::as_f64) {
        Some(n) if n > 0.0 => {}
        _ => {
            return Err(schema_invalid(
                "metadata.brightness_samples.interval_s must be a positive number".into(),
            ))
        }
    }
    match obj.get("values") {
        Some(Value::Array(a))
            if a.iter().all(|x| matches!(x.as_f64(), Some(n) if (0.0..=255.0).contains(&n))) => {}
        _ => {
            return Err(schema_invalid(
                "metadata.brightness_samples.values must be an array of numbers in [0,255]".into(),
            ))
        }
    }
    Ok(())
}
```

- [ ] **Step 4: Wire into `validate_metadata_for_write`**

Task 1 で追加した optional ブロックに 2 行足す (最終形):

```rust
    // #879 -- optional field shape validation (present only, mirror zod).
    if let Some(si) = obj.get("system_info") {
        validate_system_info(si)?;
    }
    if let Some(bs) = obj.get("brightness_samples") {
        validate_brightness_samples(bs)?;
    }
    if let Some(cr) = obj.get("capture_regions") {
        validate_capture_regions(cr)?;
    }
    if let Some(mr) = obj.get("minimap_regions") {
        validate_minimap_regions(mr)?;
    }

    Ok(())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd gui/src-tauri && cargo test write_validation_ 2>&1 | tail -20`
Expected: 新テスト全 PASS。

- [ ] **Step 6: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit --no-gpg-sign -m "feat(#879): Rust write-validation for system_info/brightness_samples

Refs #879

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CLI — `_sanitize_brightness_samples` + preserve 硬化

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (`_sanitize_capture_regions` 付近に sanitizer 追加、L479-484 の preserve を置換)
- Test: `tests/test_split_matches.py`

**Interfaces:**

- Consumes: 既存 `math`, `cast`, `BrightnessSamples` (import 済み)。
- Produces: `def _sanitize_brightness_samples(value: object) -> "BrightnessSamples | None"`。

- [ ] **Step 1: Write the failing tests**

`tests/test_split_matches.py` の末尾に追加:

```python
# --- _sanitize_brightness_samples (#879) ---


def test_sanitize_brightness_samples_accepts_valid():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    value = {"interval_s": 2.0, "values": [0.0, 128.0, 255.0]}
    assert _sanitize_brightness_samples(value) == value


def test_sanitize_brightness_samples_rejects_extra_key():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 2.0, "values": [], "x": 1}) is None


def test_sanitize_brightness_samples_rejects_nonpositive_interval():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 0.0, "values": [1.0]}) is None


def test_sanitize_brightness_samples_rejects_bool_interval():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": True, "values": [1.0]}) is None


def test_sanitize_brightness_samples_rejects_value_out_of_range():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 2.0, "values": [256.0]}) is None


def test_sanitize_brightness_samples_rejects_nan_value():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 2.0, "values": [float("nan")]}) is None


def test_sanitize_brightness_samples_rejects_values_not_list():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 2.0, "values": "abc"}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_split_matches.py -k sanitize_brightness_samples -v`
Expected: FAIL (`ImportError: cannot import name '_sanitize_brightness_samples'`)

- [ ] **Step 3: Add the sanitizer**

`allaganeye/commands/split_matches.py` の `_sanitize_capture_regions` の**直前** (L2097 手前) に追加:

```python
_BRIGHTNESS_SAMPLES_KEYS = frozenset({"interval_s", "values"})


def _sanitize_brightness_samples(value: object) -> "BrightnessSamples | None":
    """Structural sanitizer for a BrightnessSamples payload from metadata.json.

    Mirrors BrightnessSamplesSchema (gui/src/types/metadata.schema.ts) with a
    pure-Python check. Returns the value cast to BrightnessSamples when fully
    valid, else None. Same contract/style as ``_sanitize_capture_regions``:
    bool は数値として拒否、NaN / +-Infinity は reject (``json.dumps`` allow_nan
    が非標準 token を emit し GUI serde_json / JSON.parse が全体 reject するため)。

    - value は key が厳密に {interval_s, values} の dict。
    - interval_s は有限実数 (int/float、bool 排除) で > 0。
    - values は list で各要素が有限実数 (bool 排除) かつ 0 <= v <= 255。
    """
    if not isinstance(value, dict):
        return None
    if set(value.keys()) != _BRIGHTNESS_SAMPLES_KEYS:
        return None
    interval_s = value.get("interval_s")
    if (
        isinstance(interval_s, bool)
        or not isinstance(interval_s, (int, float))
        or not math.isfinite(interval_s)
        or interval_s <= 0
    ):
        return None
    values = value.get("values")
    if not isinstance(values, list):
        return None
    for v in values:
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not (0.0 <= v <= 255.0)
        ):
            return None
    return cast("BrightnessSamples", value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_split_matches.py -k sanitize_brightness_samples -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Wire into the preserve path + add a preserve test**

`allaganeye/commands/split_matches.py` の L479-484 を置換:

```python
    old_brightness_samples = payload.get("brightness_samples")
    preserve_brightness_samples: BrightnessSamples | None = _sanitize_brightness_samples(
        old_brightness_samples
    )
    if old_brightness_samples is not None and preserve_brightness_samples is None:
        logger.warning(
            "Dropping malformed brightness_samples from metadata "
            "(corrupted or hand-edited value)"
        )
```

`tests/test_split_matches.py` に preserve テストを追加 (末尾):

```python
def test_prepare_from_metadata_drops_malformed_brightness_samples(caplog):
    """--from-metadata preserve が malformed brightness_samples を omit + warn する (#879)."""
    from allaganeye.commands import split_matches

    payload = {"brightness_samples": {"interval_s": -1.0, "values": [999.0]}}
    with caplog.at_level("WARNING"):
        result = split_matches._sanitize_brightness_samples(payload["brightness_samples"])
    assert result is None
```

- [ ] **Step 6: Run tests + typecheck**

Run: `pytest tests/test_split_matches.py -k "sanitize_brightness_samples or drops_malformed_brightness" -v`
Expected: PASS。
Run: `python -m pyright allaganeye/commands/split_matches.py 2>&1 | tail -3`
Expected: 0 errors。

- [ ] **Step 7: Commit**

```bash
git add allaganeye/commands/split_matches.py tests/test_split_matches.py
git commit --no-gpg-sign -m "feat(#879): _sanitize_brightness_samples + harden --from-metadata preserve

Refs #879

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: cache — `CacheHit` + `_load_cache_hit` (additive、single read)

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (dict-parser 抽出 + `CacheHit` + `_load_cache_hit` 追加。既存 `_load_cache` / path 版 `_read_cached_*` は残す)
- Test: `tests/test_split_matches.py`

**Interfaces:**

- Consumes: 既存 `_sanitize_capture_regions`, `RegionTimeline`, `FULL_FRAME`, `_CACHE_VERSION`, `_MASKED_ALGO_VERSION`, `_VTUBER_ALGO_VERSION`, `MatchBoundary`, `SplitConfig`。
- Produces: `def _masked_fallback_from_cache_data(data: dict) -> bool` / `def _capture_regions_from_cache_data(data: dict) -> "CaptureRegions | None"` / `@dataclass(frozen=True) class CacheHit` (fields: `boundaries: list[MatchBoundary]`, `masked_fallback_used: bool`, `capture_regions: "CaptureRegions | None"`) / `def _load_cache_hit(cache_path, video_path, effective_interval, config) -> "CacheHit | None"`。

- [ ] **Step 1: Write the failing tests**

`tests/test_split_matches.py` の末尾に追加 (既存の cache テストの fixture パターンに合わせ、`tmp_path` に本物のキャッシュを書いて検証):

```python
def _write_cache(tmp_path, video_path, *, interval=2.0, extra=None):
    """Minimal valid detection cache matching _load_cache_hit's key checks."""
    import json as _json

    from allaganeye.commands import split_matches

    stat = video_path.stat()
    data = {
        "cache_version": split_matches._CACHE_VERSION,
        "source": str(video_path.resolve()),
        "source_size": stat.st_size,
        "source_mtime": stat.st_mtime,
        "params": {
            "sample_interval": interval,
            "blackout_threshold": 15.0,
            "min_match_duration": 300.0,
            "min_blackout_duration": 3.0,
            "no_audio": False,
        },
        "boundaries": [[0.0, 100.0]],
    }
    if extra:
        data.update(extra)
    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(_json.dumps(data), encoding="utf-8")
    return cache_path


def _cache_config(tmp_path):
    from allaganeye.commands.split_matches import SplitConfig

    return SplitConfig(output_dir=tmp_path)


def test_load_cache_hit_reads_file_once(tmp_path, monkeypatch):
    """三重 read 解消の pin: cache-hit で read_text は 1 回だけ (#879)."""
    from allaganeye.commands import split_matches

    video = tmp_path / "v.mkv"
    video.write_bytes(b"x" * 10)
    cache_path = _write_cache(tmp_path, video, extra={"masked_fallback_used": True})

    calls = {"n": 0}
    real_read = split_matches.Path.read_text

    def counting_read(self, *a, **k):
        if self == cache_path:
            calls["n"] += 1
        return real_read(self, *a, **k)

    monkeypatch.setattr(split_matches.Path, "read_text", counting_read)
    hit = split_matches._load_cache_hit(cache_path, video, 2.0, _cache_config(tmp_path))
    assert hit is not None
    assert hit.boundaries == [[0.0, 100.0]]
    assert hit.masked_fallback_used is True
    assert calls["n"] == 1


def test_load_cache_hit_miss_returns_none(tmp_path):
    from allaganeye.commands import split_matches

    video = tmp_path / "v.mkv"
    video.write_bytes(b"x" * 10)
    cache_path = _write_cache(tmp_path, video)
    # interval mismatch -> miss
    assert split_matches._load_cache_hit(cache_path, video, 999.0, _cache_config(tmp_path)) is None


def test_load_cache_hit_synthesizes_legacy_full_frame(tmp_path):
    """pre-#810 legacy cache (capture_regions 欠落, vtuber/masked off) は FULL_FRAME 合成 (#879 保持)."""
    from allaganeye.commands import split_matches
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    video = tmp_path / "v.mkv"
    video.write_bytes(b"x" * 10)
    cache_path = _write_cache(tmp_path, video)
    hit = split_matches._load_cache_hit(cache_path, video, 2.0, _cache_config(tmp_path))
    assert hit is not None
    assert hit.capture_regions == RegionTimeline(coarse=FULL_FRAME).to_dict()


def test_capture_regions_from_cache_data_pure(tmp_path):
    from allaganeye.commands import split_matches

    valid = {
        "coarse": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "confidence": 1.0, "source": "full_frame"},
        "segments": [],
        "fallback_reason": None,
    }
    data = {"capture_regions": valid}
    assert split_matches._capture_regions_from_cache_data(data) == valid


def test_masked_fallback_from_cache_data_pure():
    from allaganeye.commands import split_matches

    assert split_matches._masked_fallback_from_cache_data({"masked_fallback_used": True}) is True
    assert split_matches._masked_fallback_from_cache_data({}) is False
```

(`SplitConfig` の必須引数が上記より多い場合は既存テストの config fixture に倣って補うこと。`FULL_FRAME` / `RegionTimeline` の import 元は `_read_cached_capture_regions` と同じ。)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_split_matches.py -k "load_cache_hit or from_cache_data" -v`
Expected: FAIL (`AttributeError: ... has no attribute '_load_cache_hit'` 等)

- [ ] **Step 3: Extract dict-parsers + add CacheHit + _load_cache_hit**

`allaganeye/commands/split_matches.py`:

(a) 現 `_read_cached_masked_fallback` (L2079-2089) の本体を dict-parser に抽出し、path 版は delegate に変更:

```python
def _masked_fallback_from_cache_data(data: dict) -> bool:
    """Pure parser: resolved masked fallback flag from an already-parsed cache dict (#879)."""
    return bool(data.get("masked_fallback_used", False))


def _read_cached_masked_fallback(cache_path: Path) -> bool:
    """cache-hit 経路用: cache に記録された resolved masked fallback を読む。

    読めない / 欠落時は False (標準 path 扱い)。cache key の一部ではないため
    `_load_cache` とは独立に読む (#821)。
    """
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return _masked_fallback_from_cache_data(data)
```

(b) 現 `_read_cached_capture_regions` (L2182-2223) の「data 取得後」の本体を dict-parser に抽出し、path 版は delegate に変更 (既存 docstring/synthesis ロジックはそのまま dict-parser 側へ):

```python
def _capture_regions_from_cache_data(data: dict) -> "CaptureRegions | None":
    """Pure parser: capture region timeline from an already-parsed cache dict (#810/#879).

    (元 _read_cached_capture_regions の synthesis ロジックをそのまま移設:
    present は sanitize、absent+non-vtuber+non-masked は FULL_FRAME 合成、
    それ以外は None。)
    """
    cached = data.get("capture_regions")
    if cached is not None:
        sanitized = _sanitize_capture_regions(cached)
        if sanitized is None:
            logger.warning(
                "Dropping malformed capture_regions from cache "
                "(corrupted or hand-edited cache value -- region unknown)"
            )
        return sanitized
    params = data.get("params", {})
    if not params.get("vtuber", False) and not data.get("masked_fallback_used", False):
        return cast("CaptureRegions", RegionTimeline(coarse=FULL_FRAME).to_dict())
    return None


def _read_cached_capture_regions(cache_path: Path) -> "CaptureRegions | None":
    """cache-hit 経路用: cache に記録された capture region timeline を読む (#810)."""
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _capture_regions_from_cache_data(data)
```

(c) `_load_cache` (L2226) の**直後**に `CacheHit` + `_load_cache_hit` を追加。`_load_cache_hit` は `_load_cache` の key 検証ロジックを丸ごと持ち (file を 1 回 read)、boundaries 取得後に dict-parser で provenance を同一 `data` から取る:

```python
@dataclass(frozen=True)
class CacheHit:
    """Single-read cache-hit result: boundaries + provenance from one snapshot (#879)."""

    boundaries: list[MatchBoundary]
    masked_fallback_used: bool
    capture_regions: "CaptureRegions | None"


def _load_cache_hit(
    cache_path: Path,
    video_path: Path,
    effective_interval: float,
    config: SplitConfig,
) -> "CacheHit | None":
    """Load + validate cache, returning boundaries and provenance from ONE read (#879).

    三重 file open (旧: _load_cache + _read_cached_masked_fallback +
    _read_cached_capture_regions) を単一 read に統合し、検証済み boundaries と
    provenance が必ず同一 snapshot 由来になるようにする (codex F2)。
    """
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("Detection cache unreadable: %s", cache_path)
        return None

    # --- key validation (identical to _load_cache) ---
    if data.get("cache_version") != _CACHE_VERSION:
        return None
    resolved = video_path.resolve()
    if data.get("source") != str(resolved):
        return None
    try:
        stat = resolved.stat()
    except OSError:
        return None
    if data.get("source_size") != stat.st_size:
        return None
    if data.get("source_mtime") != stat.st_mtime:
        return None
    params = data.get("params", {})
    if (
        params.get("sample_interval") != effective_interval
        or params.get("blackout_threshold") != config.blackout_threshold
        or params.get("min_match_duration") != config.min_match_duration
        or params.get("min_blackout_duration") != config.min_blackout_duration
        or params.get("no_audio") != config.no_audio
        or params.get("vtuber", False) != config.vtuber
        or params.get("masked", False) != config.masked
        or params.get("keep_trailing", False) != config.keep_trailing
    ):
        return None
    _raw_cached_algo = params.get("masked_algo", 1)
    try:
        cached_algo = int(_raw_cached_algo)
    except (ValueError, TypeError):
        cached_algo = -1
    masked_affected = (
        data.get("masked_fallback_used", False)
        or params.get("masked", False)
        or config.masked
    )
    if masked_affected and cached_algo != _MASKED_ALGO_VERSION:
        return None
    _raw_cached_vtuber_algo = params.get("vtuber_algo", 1)
    try:
        cached_vtuber_algo = int(_raw_cached_vtuber_algo)
    except (ValueError, TypeError):
        cached_vtuber_algo = -1
    vtuber_affected = params.get("vtuber", False) or config.vtuber
    if vtuber_affected and cached_vtuber_algo != _VTUBER_ALGO_VERSION:
        return None

    boundaries = data.get("boundaries")
    if not isinstance(boundaries, list):
        return None

    return CacheHit(
        boundaries=boundaries,
        masked_fallback_used=_masked_fallback_from_cache_data(data),
        capture_regions=_capture_regions_from_cache_data(data),
    )
```

(`dataclass` の import が無ければファイル先頭の import 群に `from dataclasses import dataclass` を追加。既存有無を確認して重複追加しない。)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_split_matches.py -k "load_cache_hit or from_cache_data" -v`
Expected: PASS。
Run: `pytest tests/test_split_matches.py -q 2>&1 | tail -5`
Expected: 既存テストも全 PASS (path 版 `_read_cached_*` は delegate で挙動不変)。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/commands/split_matches.py tests/test_split_matches.py
git commit --no-gpg-sign -m "feat(#879): CacheHit + _load_cache_hit single-read (additive)

Refs #879

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: cache — 全 caller 移行 + `_load_cache` / path 版 `_read_cached_*` 廃止

**Files:**

- Modify: `allaganeye/commands/detect.py` (L37 import, L146-149 call site)
- Modify: `allaganeye/commands/split_matches.py` (L138-140 + L186-187 call site、`_load_cache` / path 版 `_read_cached_*` 削除)
- Test: `tests/test_detect.py` / `tests/test_split_matches.py` (直接呼び出し・patch を `_load_cache_hit` / dict-parser に移行)

**Interfaces:**

- Consumes: `_load_cache_hit`, `CacheHit`, `_masked_fallback_from_cache_data`, `_capture_regions_from_cache_data` (Task 4)。
- Produces: なし (`_load_cache` / path 版 `_read_cached_masked_fallback` / path 版 `_read_cached_capture_regions` を削除)。

- [ ] **Step 1: Migrate `detect.py` call site**

`allaganeye/commands/detect.py` の import (L37-40 付近) から `_load_cache` / `_read_cached_masked_fallback` / `_read_cached_capture_regions` を削り `_load_cache_hit` を足す。L145-149 を置換:

```python
    if not config.no_cache:
        hit = _load_cache_hit(cache_path, video_path, effective_interval, config)
        if hit is not None:
            boundaries = hit.boundaries
            masked_fallback_used = hit.masked_fallback_used
            captured_region = hit.capture_regions
            if show and verbose:
                _display_cache_hit_params(cache_path, config)
            if show:
                _display_results(boundaries, metadata, video_path, verbose, cached=True)
            if json_mode and progress_emitter is not None:
                progress_emitter.emit("cache_hit", boundaries=len(boundaries))
```

- [ ] **Step 2: Migrate `split_matches.py` call site**

`allaganeye/commands/split_matches.py` の L138-140 を単一 read に置換し、L186-187 の `_read_cached_*(cache_path)` を先頭 `hit` から取るよう変更:

```python
    if not config.no_cache:
        hit = _load_cache_hit(cache_path, video_path, effective_interval, config)
        if hit is not None:
            boundaries = hit.boundaries
            ...  # (既存の cache-hit ブロックはそのまま)
```

そして `_split_and_write_metadata(...)` 呼び出しの引数を:

```python
                masked_fallback_used=hit.masked_fallback_used,
                capture_regions=hit.capture_regions,
```

に変更 (`_read_cached_masked_fallback(cache_path)` / `_read_cached_capture_regions(cache_path)` を除去)。

- [ ] **Step 3: Remove `_load_cache` and path-based `_read_cached_*`**

`allaganeye/commands/split_matches.py` から `def _load_cache(...)` (L2226-2323)、path 版 `def _read_cached_masked_fallback(cache_path: Path)`、path 版 `def _read_cached_capture_regions(cache_path: Path)` を削除。dict-parser (`_masked_fallback_from_cache_data` / `_capture_regions_from_cache_data`) と `_load_cache_hit` / `CacheHit` は残す。

- [ ] **Step 4: Migrate the tests**

`tests/test_split_matches.py` / `tests/test_detect.py` の以下を機械的に移行:

- `_load_cache(...)` 直接呼び出し / `monkeypatch`/`patch(... "_load_cache")` → `_load_cache_hit(...)`。戻り値 boundaries を見るテストは `_load_cache_hit(...).boundaries` (miss は `is None`)。
- `_read_cached_masked_fallback(path)` / `_read_cached_capture_regions(path)` の直接呼び出し → dict を渡す `_masked_fallback_from_cache_data(data)` / `_capture_regions_from_cache_data(data)`。cache-hit provenance を検証するテストは `_load_cache_hit(...).masked_fallback_used` / `.capture_regions` を見る。

移行漏れは import エラー / AttributeError で顕在化する。全 refs を grep で洗う: `grep -n "_load_cache\b\|_read_cached_masked_fallback\|_read_cached_capture_regions" tests/test_split_matches.py tests/test_detect.py`。

- [ ] **Step 5: Run the full affected suites**

Run: `pytest tests/test_split_matches.py tests/test_detect.py -q 2>&1 | tail -8`
Expected: 全 PASS。
Run: `grep -rn "_load_cache\b\|_read_cached_masked_fallback\|_read_cached_capture_regions" allaganeye/ --include=*.py | grep -v pycache`
Expected: 出力なし (旧 API の残存 caller ゼロ)。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/commands/detect.py allaganeye/commands/split_matches.py tests/test_detect.py tests/test_split_matches.py
git commit --no-gpg-sign -m "refactor(#879): migrate all callers to _load_cache_hit, drop _load_cache

Refs #879

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 全体ゲート + 実機検証依頼

**Files:** なし (検証のみ)

- [ ] **Step 1: Python gate**

Run: `python -m ruff check . && python -m ruff format --check allaganeye/commands/split_matches.py allaganeye/commands/detect.py && python -m pyright allaganeye/commands/split_matches.py allaganeye/commands/detect.py 2>&1 | tail -3`
Expected: clean / 0 errors。

- [ ] **Step 2: Python full suite**

Run: `python -m pytest -q -p no:cacheprovider 2>&1 | tail -5`
Expected: 全 PASS (既存 + 新規)。

- [ ] **Step 3: Rust gate**

Run: `cd gui/src-tauri && cargo test 2>&1 | tail -8 && cargo check 2>&1 | tail -3`
Expected: 全 PASS / clean。

- [ ] **Step 4: markdownlint (spec/plan doc)**

Run: `bash scripts/check-markdownlint.sh 2>&1 | tail -2`
Expected: 0 error (違反あれば `--fix` して commit)。

- [ ] **Step 5: 実機検証依頼 (Iron Law 6)**

controller が Idios に `AskUserQuestion` で依頼 (released path、GUI Tauri + CLI cache):

- GUI: 正常 metadata.json の load → 編集 → apply が従来どおり通る (regression 無し)。malformed optional field (例: `brightness_samples.values` に 300) を手で仕込んだ metadata.json を apply しようとすると `parse.schema_invalid` で拒否される。
- CLI: cache-hit の detect / split --from-metadata が従来どおり動作し、`masked_fallback_used` / `capture_regions` が正しく引き継がれる (cache seed で確認可)。

## Self-Review

**1. Spec coverage:**

- spec §3 (Rust 4-field) → Task 1 (capture_regions/minimap_regions + `validate_capture_region`) + Task 2 (system_info/brightness_samples)。✓
- spec §3.1 共通 `validate_capture_region` → Task 1。✓
- spec §3.3 zod mirror 粒度 (int-valued float / null 許容 / range) → Task 1 minimap match_index `fract()==0`、Task 2 gpu_vendor_used null 許容。✓
- spec §4 CLI sanitize + preserve → Task 3。✓
- spec §5 cache single-read + `_load_cache` 廃止 + 全 caller 移行 → Task 4 (additive) + Task 5 (migrate/remove)。✓
- spec §6 テスト (read_text 1 回 pin / mixed-snapshot 不能 / legacy 合成 / dict-parser 単体) → Task 4 tests。✓
- spec §7 実機検証 → Task 6 Step 5。✓

**2. Placeholder scan:** "TBD"/"handle edge cases"/"similar to" なし。全 code step に完全コード。Task 5 のテスト移行は「機械的移行 + grep で洗う」= 具体手順あり。✓

**3. Type consistency:** `CacheHit(boundaries, masked_fallback_used, capture_regions)` を Task 4 定義・Task 5 消費で一貫。`_load_cache_hit` シグネチャ (cache_path, video_path, effective_interval, config) を Task 4/5 一貫。`_masked_fallback_from_cache_data` / `_capture_regions_from_cache_data` を Task 4 定義・Task 5 test 移行で一貫。`schema_invalid` を Task 1 定義・Task 2 再利用。✓
