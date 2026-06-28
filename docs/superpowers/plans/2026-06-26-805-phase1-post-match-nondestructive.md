# #805 段階2 Phase 1 (Python/CLI core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** post-match trailing segment の不可逆削除 (`_drop_post_match_trailing` の `segments[:-1]`) を非破壊フラグ (`post_match: true` on Match、default split 除外・metadata 保持) に置換し、silent-loss クラスを構造的に消滅させる (Phase 1 = Python/CLI core)。

**Architecture:** 設計 spec [`docs/superpowers/specs/2026-06-26-issue-805-post-match-nondestructive-design.md`](../specs/2026-06-26-issue-805-post-match-nondestructive-design.md) が SSoT。task は **green-preserving 順** で並ぶ: schema を先に緩めて (post_match 受容) → split flow が post_match boundary を扱える (no-op) → detector が flag を立てる → warning unwire + cache bump。**全 task で MATCH MP4 出力は bit-exact** (post_match は旧=削除 / 新=flag 除外 で常に MP4 化されない)。

**Tech Stack:** Python (pytest / pyright / ruff) / JSON Schema + `scripts/codegen/generate.py` (datamodel-code-generator + json-schema-to-typescript, #612) / GUI zod (vitest) / Tauri。

---

## 確定設計 (spec §4、Idios 2026-06-26)

- flag = `post_match: bool` NotRequired on `Match`。`output_file` を required→NotRequired (default 除外 post_match は MP4 無し)。
- `--keep-trailing` = **B 現状維持** (probe を skip → flag 立たず無印通常 match として split)。cache key (keep_trailing) 不変。
- warning `post_match_trailing_dropped` = **W1 emission 停止** (flag が代替、code は registry 残置)。
- `_CACHE_VERSION` 3→4 bump (detection 出力 shape 変化、[[feedback_detection_flag_cache_key]])。
- #373 は実装しない (schema 互換のみ)。GUI 表示差分化・export 除外は Phase 2。

## File Structure (Phase 1)

| ファイル | 変更 |
| --- | --- |
| `schemas/metadata.schema.json` | `$defs/Match`: `post_match` 追加 (NotRequired) / `output_file` を required から除外 |
| `allaganeye/metadata_types.py` (生成) | codegen 再生成 (`post_match: NotRequired[bool]` / `output_file: NotRequired[str]`) |
| `gui/src/types/metadata.generated.ts` (生成) | codegen 再生成 |
| `gui/src/types/metadata.schema.ts` | zod `MatchSchema`: `post_match` optional / `output_file` optional |
| `allaganeye/video/detector.py` | `MatchBoundary` に `post_match: NotRequired[bool]` / `_drop_post_match_trailing`→`_flag_post_match_trailing` (flag 化, callback param 除去) / 呼出 652 |
| `allaganeye/commands/split_matches.py` | `_split_and_write_metadata` active/post_match 分離 / `_build_metadata_payload` post_match 搬送 / warning unwire / `_CACHE_VERSION` 3→4 |
| `allaganeye/commands/detect.py` | warning unwire / detect payload の post_match 搬送 |
| `allaganeye/detection/warnings.py` | `build_warnings` の `trailing_drops` param 除去 / code を deprecated 残置 |
| `docs/metadata-spec.md` | Match 表 (post_match / output_file NotRequired) / warnings 表 / 将来拡張 |
| `gui/src/screens/CompleteScreen.tsx` / `PreviewScreen.tsx` | no-crash guard (output_file undefined を graceful 処理) |

テスト: `tests/test_metadata_schema.py` / `tests/test_split_matches.py` / `tests/test_detector.py` / `tests/test_detect.py` / `tests/test_warnings.py` / `tests/test_split_from_metadata.py` / `tests/test_cli.py` / `gui/src/.../*.test.ts(x)`。

---

## Task 1: schema + codegen + GUI zod (post_match / output_file NotRequired)

**Files:**

- Modify: `schemas/metadata.schema.json` (`$defs/Match`, lines 146-208)
- Regenerate: `allaganeye/metadata_types.py`, `gui/src/types/metadata.generated.ts`
- Modify: `gui/src/types/metadata.schema.ts` (`MatchSchema`)
- Test: `tests/test_metadata_schema.py`, `gui/src/types/__tests__/zod-schema-integrity.test.ts`

- [ ] **Step 1: 失敗するテスト (schema が post_match Match を valid と判定)**

`tests/test_metadata_schema.py` に追加 (既存の jsonschema validate ヘルパに倣う):

```python
def test_match_post_match_flag_without_output_file_validates():
    # post_match segment は MP4 無し = output_file 欠落でも valid
    match = {
        "index": 2,
        "start_time": 100.0,
        "end_time": 500.0,
        "start_display": "1:40",
        "end_display": "8:20",
        "duration": 400.0,
        "duration_display": "6m40s",
        "type": "unknown",
        "post_match": True,
    }
    _validate_match(match)  # 既存ヘルパ。無ければ jsonschema.validate(match, MATCH_SCHEMA)


def test_match_without_output_file_and_without_post_match_validates():
    # output_file が NotRequired になったので欠落しても schema 上 valid
    # (実運用では通常 match は必ず output_file を持つが、schema は緩い)
    match = {
        "index": 1, "start_time": 0.0, "end_time": 600.0,
        "start_display": "0:00", "end_display": "10:00",
        "duration": 600.0, "duration_display": "10m0s", "type": "fl_match",
    }
    _validate_match(match)
```

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_metadata_schema.py::test_match_post_match_flag_without_output_file_validates -v`
Expected: FAIL (`additionalProperties` で post_match 拒否 + output_file required 違反)。

- [ ] **Step 3: schema 編集**

`schemas/metadata.schema.json` `$defs/Match`:

1. `required` 配列 (151-161) から `"output_file"` を削除。
2. `properties` (162-208) に追加:

```json
        "post_match": {
          "description": "True when this segment is a post-match trailing run (#805 段階2). Non-destructive flag: excluded from default split output but retained in metadata. Absent / false = normal match.",
          "type": "boolean"
        }
```

`additionalProperties: false` は維持。

- [ ] **Step 4: codegen 再生成**

Run: `python scripts/codegen/generate.py`
Expected: `allaganeye/metadata_types.py` の `Match` に `post_match: NotRequired[bool]` + `output_file: NotRequired[str]`。`gui/src/types/metadata.generated.ts` 更新。差分を確認 (生成物以外を触っていないこと)。

- [ ] **Step 5: GUI zod 更新**

`gui/src/types/metadata.schema.ts` の `MatchSchema` (spec §5.2、現状 lines 22-40 付近):

- `output_file: z.string()...` を `.optional()` に。
- `post_match: z.boolean().optional(),` を追加。

- [ ] **Step 6: テスト pass + 全体 green**

Run: `pytest tests/test_metadata_schema.py -v`
Expected: PASS。
Run: `cd gui && npm test -- zod-schema-integrity && npm run typecheck`
Expected: integrity test PASS (schema↔zod 一致)、tsc clean。
Run: `pytest -q && ruff check . && ruff format --check . && pyright`
Expected: 全 green (まだ behavior 変化なし)。

- [ ] **Step 7: Commit**

```bash
git add schemas/metadata.schema.json allaganeye/metadata_types.py gui/src/types/metadata.generated.ts gui/src/types/metadata.schema.ts tests/test_metadata_schema.py
git commit -F - <<'EOF'
feat(schema): #805 Match に post_match NotRequired + output_file 緩和 (Refs #805)

post-match 非破壊フラグ受容のため $defs/Match に post_match: boolean を追加し
output_file を required から外す。codegen 再生成 + GUI zod 同期 (integrity green)。
behavior 変化なし (schema 緩和のみ)。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Task 2: split flow が post_match boundary を扱う (除外 + metadata 搬送、no-op)

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (`_split_and_write_metadata` 1287-1372 / `_build_metadata_payload` 1375-1494)
- Test: `tests/test_split_matches.py`

この task はまだ detector が flag を立てないので **実 detection では no-op** (post_match boundary が来ない)。合成 boundary でロジックを TDD する。

- [ ] **Step 1: 失敗するテスト (post_match boundary は split されず metadata に output_file 無しで残る)**

`tests/test_split_matches.py` に追加 (既存の `_build_metadata_payload` テストに倣う):

```python
def test_build_metadata_payload_post_match_excluded_from_outputs():
    active = [{"start": 0.0, "end": 600.0, "type": "fl_match"}]
    post_match = [{"start": 600.0, "end": 700.0, "type": "unknown", "post_match": True}]
    output_files = [Path("match_001.mp4")]  # active 分のみ
    payload = _build_metadata_payload(
        # ... 既存テストの必須 kwargs を流用 ...
        boundaries=active,
        post_match_boundaries=post_match,
        output_files=output_files,
        # ...
    )
    matches = payload["matches"]
    assert len(matches) == 2
    assert matches[0]["index"] == 1 and matches[0]["output_file"] == "match_001.mp4"
    assert "post_match" not in matches[0]
    assert matches[1]["index"] == 2 and matches[1].get("post_match") is True
    assert "output_file" not in matches[1]  # MP4 無し
```

(`_split_and_write_metadata` の active/post_match 分離 + `split_video` への active 渡しは別テストで: post_match boundary を含む boundaries を渡し、`split_video` の呼出引数が active のみであることを mock で assert。)

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_split_matches.py::test_build_metadata_payload_post_match_excluded_from_outputs -v`
Expected: FAIL (`_build_metadata_payload` に `post_match_boundaries` param が無い)。

- [ ] **Step 3: `_build_metadata_payload` に post_match 搬送を実装**

`split_matches.py:1385` の signature に `post_match_boundaries: list[MatchBoundary] = [],` を追加 (`boundaries` の直後)。`matches` 構築 (1457-1474) を以下に置換:

```python
        "matches": [
            {
                "index": i + 1,
                "start_time": b["start"],
                "end_time": b["end"],
                "start_display": _format_timestamp(b["start"]),
                "end_display": _format_timestamp(b["end"]),
                "duration": b["end"] - b["start"],
                "duration_display": _format_duration(b["end"] - b["start"]),
                "type": "fl_match" if b.get("type") == "fl_match" else "unknown",
                "output_file": f.as_posix(),
            }
            for i, (b, f) in enumerate(zip(boundaries, output_files, strict=True))
        ]
        + [
            {
                "index": len(boundaries) + j + 1,
                "start_time": b["start"],
                "end_time": b["end"],
                "start_display": _format_timestamp(b["start"]),
                "end_display": _format_timestamp(b["end"]),
                "duration": b["end"] - b["start"],
                "duration_display": _format_duration(b["end"] - b["start"]),
                "type": "fl_match" if b.get("type") == "fl_match" else "unknown",
                "post_match": True,
            }
            for j, b in enumerate(post_match_boundaries)
        ],
```

(post_match match は `output_file` キーを持たない = NotRequired。`Match` TypedDict が Task 1 で許容済み。)

- [ ] **Step 4: `_split_and_write_metadata` で active/post_match を分離**

`split_matches.py:1325-1365` の `split_video` 呼出前に分離を挿入し、`split_video` に active のみ、`_build_metadata_payload` に両方を渡す:

```python
    active_boundaries = [b for b in boundaries if not b.get("post_match")]
    post_match_boundaries = [b for b in boundaries if b.get("post_match")]
```

`split_video(video_path, active_boundaries, ...)` (1333-1340 の両分岐とも `boundaries` を `active_boundaries` に)。progress total (`len(boundaries)` at 1327) も `len(active_boundaries)` に。`_build_metadata_payload(..., boundaries=active_boundaries, post_match_boundaries=post_match_boundaries, output_files=output_files, ...)`。

- [ ] **Step 5: テスト pass**

Run: `pytest tests/test_split_matches.py -k "post_match or build_metadata or split" -v`
Expected: PASS。既存 split テストも green (post_match 空時は従来挙動 = active==boundaries)。

- [ ] **Step 6: 全体 green + commit**

Run: `pytest -q && ruff check . && pyright`
Expected: green。

```bash
git add allaganeye/commands/split_matches.py tests/test_split_matches.py
git commit -F - <<'EOF'
feat(split): #805 split flow が post_match boundary を MP4 除外し metadata 保持 (Refs #805)

_split_and_write_metadata が boundaries を active/post_match に分離、active のみ
split_video へ。_build_metadata_payload が post_match を output_file 無しの Match
として末尾 index に搬送。detector が未 flag のため実 detection では no-op (bit-exact)。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Task 3: detector が削除でなく flag を立てる (`_flag_post_match_trailing`)

**Files:**

- Modify: `allaganeye/video/detector.py` (`MatchBoundary` 25-31 / `_drop_post_match_trailing` 2394-2492 / 呼出 652-661)
- Test: `tests/test_detector.py` (`TestDropPostMatchTrailing` 2304-)

**重要**: この task で実 detection が post_match flag を立てる。Task 2 の split flow が flag を除外するので **MATCH MP4 出力は bit-exact** (post-match は旧=削除 / 新=flag 除外、どちらも MP4 化されない)。metadata は post_match segment が追加される (= 段階2 の意図した変化)。callback param はこの task では残す (warning は Task 4 で unwire、ここでは flag 化に集中)。

- [ ] **Step 1: 失敗するテスト (flag を立て segment を保持、削除しない)**

`tests/test_detector.py` `TestDropPostMatchTrailing` に追加:

```python
def test_post_match_flagged_not_dropped(self, monkeypatch):
    # 全 probe miss (False) -> post-match -> 旧: 削除 / 新: flag + 保持
    monkeypatch.setattr(
        "allaganeye.video.detector._has_scorebar_v2", lambda rgb: False
    )
    monkeypatch.setattr(
        "allaganeye.video.detector._probe_frame_rgb_hires",
        lambda path, t: object(),  # non-None なので probe は実行される
    )
    segments = [
        {"start": 0.0, "end": 600.0, "type": "unknown"},
        {"start": 600.0, "end": 900.0, "type": "unknown"},
    ]
    result = _flag_post_match_trailing(
        segments, Path("dummy.mp4"), 900.0, None, min_match_duration=300.0
    )
    assert len(result) == 2  # 削除されない
    assert result[-1].get("post_match") is True  # flag が立つ
    assert result[0].get("post_match") in (None, False)  # 先頭は無印
```

既存 `test_trailing_no_scorebar_dropped` 等「削除」前提テストは「flag + 保持」に書換 (len 不変 + `post_match=True` assert)。`_drop_post_match_trailing` の import 名も `_flag_post_match_trailing` に更新。

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_detector.py::TestDropPostMatchTrailing::test_post_match_flagged_not_dropped -v`
Expected: FAIL (`_flag_post_match_trailing` 未定義)。

- [ ] **Step 3: detector を flag 方式に変更**

1. `MatchBoundary` (25-31) に `post_match: NotRequired[bool]` を追加 (`from typing import NotRequired` が無ければ import)。
2. `_drop_post_match_trailing` を `_flag_post_match_trailing` に rename。末尾 (2477-2492) を変更:
   - stats の `post_match_trailing` カウンタ増分は維持 (2479-2481)。
   - `filter_unknown` の decrement (2482-2486) を **削除** (segment は matches に残るので unknown count から引かない)。
   - `trailing_drop_callback` の発火 (2490-2491) はこの task では**残す** (Task 4 で除去)。
   - `return segments[:-1]` を以下に置換:

   ```python
       segments[-1]["post_match"] = True
       return segments
   ```

3. docstring を flag 方式に更新 (「drop」→「flag (retain, default split 除外)」)。
4. 呼出 (652-653) の関数名を `_flag_post_match_trailing` に更新 (引数は現状維持、callback はまだ渡す)。

- [ ] **Step 4: テスト pass + TestDropPostMatchTrailing 全体**

Run: `pytest tests/test_detector.py::TestDropPostMatchTrailing -v`
Expected: 全 PASS (書換えた既存テスト含む)。probe-stride / lone-segment / vtuber gate / keep_trailing gate テストは flag 化に整合するよう assert を更新 (lone-segment は依然 flag されない、vtuber/keep_trailing は呼ばれない)。

- [ ] **Step 5: 全体 green + commit**

Run: `pytest -q && ruff check . && pyright`
Expected: green。

```bash
git add allaganeye/video/detector.py tests/test_detector.py
git commit -F - <<'EOF'
feat(detector): #805 post-match trailing を削除でなく flag 化 (Refs #805)

_drop_post_match_trailing -> _flag_post_match_trailing。全 probe miss 時に
segments[:-1] (不可逆削除) でなく segments[-1]["post_match"]=True で保持。
silent-loss クラスを構造的に消滅。MatchBoundary に post_match NotRequired。
Task 2 の split flow が flag を MP4 除外 = MATCH MP4 出力は bit-exact。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Task 4: warning unwire (W1) + cache version bump

**Files:**

- Modify: `allaganeye/detection/warnings.py` (`build_warnings` 60-85)
- Modify: `allaganeye/video/detector.py` (`detect_match_boundaries` の `trailing_drop_callback` param + 呼出 652-661)
- Modify: `allaganeye/commands/split_matches.py` (`_on_trailing_drop` collector / `build_warnings(trailing_drops=...)` 呼出 / `detect_kwargs` / `_CACHE_VERSION`)
- Test: `tests/test_warnings.py`, `tests/test_split_matches.py`, `tests/test_split_from_metadata.py`

**重要**: callback param をチェーン全体 (`_flag_post_match_trailing` → `detect_match_boundaries` → split_matches/detect.py) から一斉に除去する (mid-chain 除去は caller を壊すため 1 task で atomic)。detect.py 分は Task 5。

- [ ] **Step 1: テスト更新 (warning が emit されない)**

`tests/test_warnings.py`:

```python
def test_build_warnings_no_trailing_drops_param():
    # trailing_drops param 除去後は引数なしで空 list
    assert build_warnings() == []


def test_post_match_trailing_dropped_code_still_registered():
    # W1: emission は停止するが registry には deprecated 残置 (旧 metadata 読取互換)
    assert "post_match_trailing_dropped" in WARNING_CODES
```

`tests/test_split_matches.py` の `test_run_split_records_trailing_drop_warning` (4673) を **反転**: post-match を含む run で `warnings` が空 (emit されない) ことを assert (segment は post_match flag で matches に出る)。`test_run_split_no_trailing_drop_writes_empty_warnings` は維持。cache: `_CACHE_VERSION == 4` の pin test + 旧 v3 cache が miss する test を追加。

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_warnings.py::test_build_warnings_no_trailing_drops_param tests/test_split_matches.py::test_run_split_records_trailing_drop_warning -v`
Expected: FAIL (現状は trailing_drops param 有り + warning emit)。

- [ ] **Step 3: warning unwire 実装**

1. `warnings.py`: `build_warnings` の `trailing_drops` param を除去し空 list を返す scaffold に戻す (docstring も更新)。`WARNING_CODES["post_match_trailing_dropped"]` は残置し deprecated コメント追加。
2. `detector.py`: `_flag_post_match_trailing` から `trailing_drop_callback` param + 発火 (2490-2491) を除去。`detect_match_boundaries` signature から `trailing_drop_callback` param (405 付近) を除去、呼出 (652-661) からも除去。
3. `split_matches.py`: `_on_trailing_drop` collector + `trailing_drops` list (219-226) を除去、`detect_kwargs` の `trailing_drop_callback` (848-853) を除去、`build_warnings(trailing_drops=trailing_drops)` (317) を `build_warnings()` (= None default に戻し payload builder 側の `build_warnings()` に委譲、または warnings 引数自体を渡さない) に変更。
4. `_CACHE_VERSION` (~64) を `3` → `4` に bump。

- [ ] **Step 4: テスト pass**

Run: `pytest tests/test_warnings.py tests/test_split_matches.py tests/test_split_from_metadata.py -v`
Expected: PASS。`test_run_split_from_metadata_preserves_trailing_drop_warning` (旧 metadata の warning sanitize 互換) は維持 (registry 残置 + sanitize_warnings 不変)。

- [ ] **Step 5: 全体 green + commit**

Run: `pytest -q && ruff check . && pyright`

```bash
git add allaganeye/detection/warnings.py allaganeye/video/detector.py allaganeye/commands/split_matches.py tests/test_warnings.py tests/test_split_matches.py tests/test_split_from_metadata.py
git commit -F - <<'EOF'
feat(detect): #805 W1 warning emission 停止 + cache v4 (Refs #805)

post_match flag が代替するため post_match_trailing_dropped warning の emission を
停止 (trailing_drop_callback チェーンを除去)。code は registry に deprecated 残置
(旧 metadata 読取互換)。detection 出力 shape 変化のため _CACHE_VERSION 3->4。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Task 5: detect.py の warning unwire + post_match 搬送

**Files:**

- Modify: `allaganeye/commands/detect.py` (warning wiring 97-106 / 209-213 / 307-310 + payload builder)
- Test: `tests/test_detect.py`

**注**: detect.py は split しないので payload に output_file が無い変種。post_match flag は detect.py の matches にも出る (detect も `_flag_post_match_trailing` を経由)。実装者は detect.py の現行 payload builder を Read し、post_match flag を Match に搬送 (split_matches と同型) + warning unwire を行う。

- [ ] **Step 1: テスト更新**

`tests/test_detect.py`: `test_detect_records_trailing_drop_warning` (416) を反転 (warning emit されない + post_match flag が matches に出る)。`test_detect_no_trailing_drop_writes_empty_warnings` (453) 維持。

- [ ] **Step 2: 失敗確認**

Run: `pytest tests/test_detect.py -k trailing -v`
Expected: FAIL。

- [ ] **Step 3: 実装**

detect.py の `on_trailing_drop` / `trailing_drops` collector + `build_warnings(trailing_drops=...)` を除去 (split_matches と同型)。`_run_detection` への `trailing_drop_callback` 受渡を除去。detect の payload builder で post_match flag を Match に搬送 (detect は output_file 無しなので post_match match も同様に output_file 無し)。

- [ ] **Step 4: pass + 全体 green + commit**

Run: `pytest tests/test_detect.py -v && pytest -q && ruff check . && pyright`

```bash
git add allaganeye/commands/detect.py tests/test_detect.py
git commit -F - <<'EOF'
feat(detect): #805 detect コマンドの warning unwire + post_match 搬送 (Refs #805)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Task 6: GUI no-crash guard (post_match / output_file undefined)

**Files:**

- Modify: `gui/src/screens/CompleteScreen.tsx`, `gui/src/screens/PreviewScreen.tsx` (output_file 参照箇所)
- Test: `gui/src/screens/__tests__/*.test.tsx` (該当 screen test)

spec §5.2: Phase 1 では post_match match を含む metadata を render しても throw しない最小 guard。表示差分化は Phase 2。

- [ ] **Step 1: 失敗する vitest (post_match match を含む metadata で render が throw しない)**

該当 screen test に追加: post_match:true で output_file undefined の match を含む metadata fixture を load → render → `expect(() => render(...)).not.toThrow()`。preview 動画ロードが output_file undefined で graceful (skip / disabled) であることを assert。

- [ ] **Step 2: 失敗確認**

Run: `cd gui && npm test -- CompleteScreen` (該当 test)
Expected: FAIL (undefined output_file で throw or 不正動作)。

- [ ] **Step 3: guard 実装**

実装者は CompleteScreen/PreviewScreen で `match.output_file` 参照箇所を Read し、undefined を graceful 処理 (post_match match は preview/export 対象外として skip or placeholder)。最小変更、表示差分化はしない。

- [ ] **Step 4: pass + GUI 全体 green + commit**

Run: `cd gui && npm test && npm run typecheck && npm run lint && npm run build`
Expected: 全 green。

```bash
git add gui/src/screens/CompleteScreen.tsx gui/src/screens/PreviewScreen.tsx gui/src/screens/__tests__/
git commit -F - <<'EOF'
feat(gui): #805 post_match match の no-crash guard (Phase 1) (Refs #805)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Task 7: docs (metadata-spec.md)

**Files:**

- Modify: `docs/metadata-spec.md` (Match 表 / warnings 表 / 将来拡張)

- [ ] **Step 1: docs 更新**

spec §5.7 に従い: Match 表に `post_match` 行 (boolean NotRequired) + `output_file` を NotRequired に。warnings 表の `post_match_trailing_dropped` に「段階2 で emission 停止、post_match flag に置換、code は後方互換読取のため残置」。将来拡張に #373 互換注記。

- [ ] **Step 2: markdownlint + commit**

Run: `npx markdownlint-cli2@0.22.1 "docs/metadata-spec.md"`
Expected: 0 errors。

```bash
git add docs/metadata-spec.md
git commit -F - <<'EOF'
docs(metadata): #805 post_match flag + output_file NotRequired を spec 反映 (Refs #805)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## 実機検証 (Pre-flight、Iron Law 6、コード task ではない)

detector.py logic 変更のため **実機 bit-exact 検証を Idios に AskUserQuestion**:

- 5 OBS baseline (`E:/royalstraightflesh/videos`) で **MATCH MP4 出力が不変**であること (post_match は旧=削除/新=flag 除外で常に MP4 化されない)。
- metadata.json 差分は想定内: drop 非 trigger baseline は output-neutral (timestamp churn は grep 除外)、drop trigger baseline があれば post_match segment 追加 + warning 消滅。
- detached 実行可 (`Start-Process -WindowStyle Hidden`、`--no-cache` 必須、memory [[feedback_long_gpu_job_detached_execution]])。flag path を exercise する drop-trigger VOD があれば追加検証。

---

## Self-Review

**1. Spec coverage**: §5.1 schema=Task1 / §5.2 GUI zod+guard=Task1(zod)+Task6(guard) / §5.3 detector=Task3 / §5.4 split=Task2 / §5.5 cache=Task4 / §5.6 warnings=Task4+Task5 / §5.7 docs=Task7 / §6.1 unit tests=各 task / §6.2 bit-exact=実機検証節。全 §をカバー。

**2. Placeholder scan**: 各 task に具体コード/コマンド/file:line。detect.py (Task5) / GUI guard (Task6) は実装者が現行コードを Read して spec に従う refactor 指示 (vague placeholder ではなく precise location + 設計参照)。

**3. Type consistency**: `_flag_post_match_trailing` (Task3 で rename、Task4 で param 除去) / `post_match` flag / `post_match_boundaries` param / `_CACHE_VERSION=4` を全 task で一貫使用。green-preserving 順序 (schema→split no-op→detector flag→warning/cache→detect→GUI→docs) で各 task green + MATCH MP4 bit-exact 維持。
