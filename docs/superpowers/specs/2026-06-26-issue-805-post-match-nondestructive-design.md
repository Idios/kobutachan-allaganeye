# #805 段階2: post-match trailing 非破壊化 設計 spec

> 状態: design (brainstorming 承認済み、Idios 2026-06-26)。実装は writing-plans → Subagent-Driven。
> 関連: #797 (段階0 = trailing drop 導入) / #805 段階1 (G4 = warnings + `--keep-trailing` escape hatch、v0.3.0 出荷済) / #373 (末尾打ち切り情報 metadata 記録、本 spec の schema と互換設計) / [`2026-05-21-issue-803-scorebar-v2-post-match-fp-fix-design.md`](2026-05-21-issue-803-scorebar-v2-post-match-fp-fix-design.md) §0.6 (round-1〜6 の変遷)

## 1. 背景と問題

`_drop_post_match_trailing` (`allaganeye/video/detector.py`、#797) は最終 segment が post-match trailing (lobby/city) と判定したとき `return segments[:-1]` で **不可逆削除**する。削除判定は「early-window scorebar probe が全 miss (`_has_scorebar_v2` が全 `False`)」という**否定信号のみ**に依存している。

scorebar detector が FN する環境 (未対応 HUD layout / 4K Game DVR 等) では、**実試合の trailing が全 probe miss → 実試合を silent に削除**しうる (試合 1 本喪失、エラーなし = L1 の目的に対する最悪の失敗)。round-1〜6 の Codex adversarial-review で probe 位置・数・gate を 6 回チューニングしたが毎回新たな silent-loss エッジが露出した (もぐら叩き)。根本は **「不可逆削除 × 弱い否定信号 (scorebar 不在)」** という構造であり、heuristic のチューニングでは消えない (memory: [[feedback_adversarial_review_whackamole]])。

段階1 (G4) は削除そのものは維持したまま、削除した span を `warnings[]` (`post_match_trailing_dropped`) に記録 + `--keep-trailing` escape hatch を追加した (緩和策)。本 spec の段階2 は**削除を構造的に廃止**し silent-loss クラスを設計から消滅させる。

## 2. 期待される最終状態 (段階2)

post-match と判定した trailing segment を**削除せず、非破壊フラグ `post_match: true` を立てて metadata に保持**する。default の split 出力 (MP4) からは除外するが、segment は metadata.json に残り復元可能。これにより scorebar の FN/FP がどう転んでも「実試合の不可逆削除」は構造的に起こらなくなる (削除という操作自体が存在しなくなる)。

## 3. スコープ (Idios 2026-06-26 確定)

- **本 spec = 段階2 のみ** (`post_match` flag on Match)。#373 (`dropped:{leading,trailing}` で < `min_match_duration` の余りを記録) は別 P3 issue のまま。本 spec の schema は #373 の `dropped` section を将来追加できる形 (`additionalProperties:false` を壊さない余地) に設計するが #373 は実装しない。
- **Phase 分割** (`docs/refactor-pattern.md` 準拠):
  - **Phase 1 = Python/CLI core** (本 spec の主対象)。schema + codegen + 最小 GUI zod field (CI integrity green 維持) + detector flag + split 除外 + metadata 搬送 + cache version bump + docs + Python tests。**silent-loss クラスを Phase 1 で構造的に消滅**させる。
  - **Phase 2 = GUI** (別 PR)。CompleteScreen/PreviewScreen での `post_match` 表示差分化 + export 除外 + `normalizeForPersistence` passthrough + GUI tests。
  - 両 Phase とも #805 配下 (#805 は close 禁止のまま継続 = risk tracking issue)。

## 4. 設計判断 (brainstorming で Idios 確定)

| 論点 | 決定 | 理由 |
| --- | --- | --- |
| flag 表現 | `post_match: bool` NotRequired on `Match` | issue 指定「NotRequired フラグ方式」。segment は >= `min_match_duration` で Match 構造を持てる |
| `--keep-trailing` 意味 | **B: 現状維持** (probe を skip、segment は無印通常 match として split) | 最小 blast radius。default path のみ削除→flag 化。split filter は `post_match:true` 除外で一貫。detection cache key (keep_trailing) 不変 |
| 段階1 warning | **W1: emission 停止** | flag が first-class 代替。message の「dropped」前提が段階2 で偽になる。warning code は registry に deprecated 残置 (旧 metadata 読取維持) |
| #373 統合 | 段階2 のみ・schema は互換設計 | Iron Law 3 scope 遵守。#373 は別 cycle |
| Phase | Python/CLI core (P1) → GUI (P2) | schema 変更は GUI zod integrity test と結合するため P1 は最小 zod field を含む |

## 5. Phase 1 詳細設計

### 5.1 schema (`schemas/metadata.schema.json` `$defs/Match`)

- `post_match` を `properties` に追加 (型 `boolean`、`required` には**入れない** = NotRequired)。description: 「true のとき post-match trailing segment (#805 段階2)。非破壊フラグ、default split 出力から除外。absent/false = 通常 match」。
- `output_file` を `required` から**外す** (NotRequired 化)。default 除外の post_match segment は MP4 を生成しないため `output_file` を持たない。通常 match は従来どおり `output_file` を持つ (絶対欠落させない = 5.4 の payload builder が保証)。
- `additionalProperties: false` は維持。#373 の `dropped` section は `Metadata` top-level (`$defs/Match` ではなく root) に将来追加する想定なので本変更と独立 (互換)。
- 再生成: `python scripts/codegen/generate.py` → `allaganeye/metadata_types.py` (`Match` TypedDict に `post_match: NotRequired[bool]` / `output_file: NotRequired[str]`) + `gui/src/types/metadata.generated.ts`。

### 5.2 GUI zod 最小更新 (`gui/src/types/metadata.schema.ts`、Phase 1 で CI green 維持に必須)

- `MatchSchema` に `post_match: z.boolean().optional()` を追加。
- `output_file` を `.optional()` に変更 (schema と整合)。
- `gui/src/types/__tests__/zod-schema-integrity.test.ts` が field 一致を gate するため Phase 1 で同時更新必須 (これを怠ると gui-frontend CI red)。
- **Phase 1 の GUI no-crash guard (最小)**: Phase 1 CLI が書いた metadata.json (post_match match = `output_file` undefined) を Phase 1 GUI が読んだとき **crash しない**ことを保証する。CompleteScreen/PreviewScreen が `match.output_file` を参照する箇所 (preview 動画ロード等) で undefined を graceful に扱う最小 guard を入れる (post_match match は preview/export 対象外として skip / placeholder)。vitest で「post_match match を含む metadata を load → render が throw しない」を 1 test 追加。**表示の差分化 (badge / dimmed) と export 除外 UX は Phase 2**。Phase 1 では post_match match は通常 match に近い見え方でよい (crash しなければ可)。

### 5.3 detector.py

- `MatchBoundary` TypedDict (`detector.py:25-31`、hand-written) に `post_match: NotRequired[bool]` を追加。
- `_drop_post_match_trailing` (`detector.py:2394-2492`):
  - 末尾の `return segments[:-1]` (削除) を廃止。post-match 確定時 (全 probe miss) は **最終 segment に `post_match=True` を立てて `return segments`** (segment を保持)。
  - stats の `filter_drops["post_match_trailing"]` カウンタは**維持** (検出した post_match 数の観測値として有用、verbose 表示に使う)。`filter_unknown` の整合調整 (現 2482-2486) は、segment が matches に残るので**不要化**する (decrement しない) — segment は依然 unknown type だが matches に残るため `filter_unknown` から引く必要がない。この挙動差は verbose 統計のみに影響 (出力 MP4 / matches[] の本体には無関係)。
  - `trailing_drop_callback` パラメータを**除去** (W1: warning を emit しないため callback の消費先が無くなる)。
  - 関数名は `_drop_post_match_trailing` のまま維持してよい (削除はしないが「post-match を default 出力から落とす」意味は保たれる) か、`_flag_post_match_trailing` に rename するか — **rename を採用** (挙動を正確に表す。callers は 1 箇所 = `detector.py:652`)。docstring も flag 方式に全面更新。
- 呼出し側 (`detector.py:652-661`): `keep_trailing` gate は**現状維持** (`if src_resolution is not None and not vtuber and not keep_trailing:`)。`trailing_drop_callback` 引数の受渡しを除去。`--keep-trailing` 時は本関数を呼ばない = probe せず flag も立たない = segment は無印通常 match (現状と bit-exact)。

### 5.4 split 除外 + metadata 搬送 (`allaganeye/commands/split_matches.py` + `allaganeye/video/splitter.py`)

- `_split_and_write_metadata` (`split_matches.py:1287`) で `split_video` 呼出前に boundaries を **active (post_match でない) と post_match に分離**:
  - `active_boundaries = [b for b in boundaries if not b.get("post_match")]`
  - `post_match_boundaries = [b for b in boundaries if b.get("post_match")]`
- `split_video(video_path, active_boundaries, ...)` に **active のみ**渡す → MP4 は active 分だけ生成 (default 出力 = 現状と同一 = bit-exact)。
- `_build_metadata_payload` (`split_matches.py:1375-1494`):
  - active boundaries (N) を `output_files` (N) と zip → index 1..N、`output_file` 有り。
  - post_match boundaries を index N+1.. として append、`post_match: true`、`output_file` は**付けない** (NotRequired)。
  - `matches[]` は active + post_match を index 連番で並べる (active 先頭、post_match 末尾)。
- `--keep-trailing` 時: detection が post_match flag を立てないため `post_match_boundaries` は空 → 全 boundaries が active → 現状どおり全 split。bit-exact。

### 5.5 cache version bump (`split_matches.py`)

- `_CACHE_VERSION` を **3 → 4** に bump。理由: detection 出力 (cached segments) の shape が変わる (旧 = post_match segment が削除済み / 新 = post_match flag 付きで残る)。version bump で旧 cache (削除済み shape) の silent 再利用を防ぐ ([[feedback_detection_flag_cache_key]]: detection 出力を変える変更は cache version を bump)。
- cache key params (keep_trailing 含む) 自体は**不変** (keep_trailing semantics は B で現状維持)。verbose の cache hit 表示も keep_trailing 行は不変。

### 5.6 warnings unwiring (W1、`warnings.py` + `split_matches.py` + `detect.py`)

- `post_match_trailing_dropped` の **emission を停止**:
  - `split_matches.py` の `_on_trailing_drop` collector + `trailing_drops` 蓄積 + `build_warnings(trailing_drops=...)` 呼出を除去 (`build_warnings()` を空引数に戻す)。
  - `detect.py` の同型配線 (`on_trailing_drop` / `trailing_drops`) も除去。
  - `_run_detection` の `detect_kwargs` から `trailing_drop_callback` を除去。
- `warnings.py`:
  - `build_warnings` の `trailing_drops` パラメータを除去 (空 list を返す #518 scaffold に戻る) **か**、param は残し未使用にする — **除去を採用** (dead param を残さない、callers は内部のみ)。
  - `WARNING_CODES["post_match_trailing_dropped"]` は **registry に残置** (deprecated コメント付き)。`sanitize_warnings` は旧 metadata.json の当 code を引き続き読める (後方互換)。
- docstring / コメントの「#805 段階1」言及を段階2 の事実に更新。

### 5.7 docs (`docs/metadata-spec.md`)

- `Match` オブジェクト表に `post_match` 行 (boolean, NotRequired, 「post-match trailing 非破壊フラグ、段階2」) + `output_file` を NotRequired に更新。
- warnings の `post_match_trailing_dropped` 行に「段階2 で emission 停止、`post_match` flag に置換 (code は後方互換読取のため registry 残置)」と注記。
- 将来拡張表に #373 との互換 (`dropped` section は将来 top-level 追加可) を注記。

## 6. Phase 1 検証

### 6.1 unit tests (Python、本 Phase で完結)

- detector: `_flag_post_match_trailing` (旧名 `_drop_post_match_trailing`) が削除でなく flag を立てることを assert。post-match 確定 → 最終 segment `post_match=True` で len 不変。probe-stride / lone-segment / vtuber gate / keep_trailing gate の既存テストは「削除」前提を「flag」前提に書換 (`tests/test_detector.py` `TestDropPostMatchTrailing`)。
- split: post_match segment が MP4 化されず metadata に残る (`tests/test_split_matches.py`)。active/post_match の index 連番。`--keep-trailing` で全 split (post_match 空)。
- payload: `_build_metadata_payload` が post_match Match を `output_file` 無しで出力。
- cache: `_CACHE_VERSION=4`、旧 version cache (3) が miss する pin test。
- warnings: `post_match_trailing_dropped` を **emit しない**ことを assert (旧 `test_run_split_records_trailing_drop_warning` 等は「emit されない」に反転、または削除して flag 検証に置換)。registry には code が残る pin test。`sanitize_warnings` が旧 code を読める後方互換 test。
- schema: `post_match` / NotRequired `output_file` が schema-valid (`tests/test_metadata_schema.py`)。

### 6.2 bit-exact gate (実機、Iron Law 6)

- **5 OBS baseline で MATCH MP4 出力が不変**であること (post_match は元々 MP4 化されない — 旧=削除 / 新=flag 除外 — ので MP4 boundaries は bit-exact)。
- metadata.json の差分は **想定内**:
  - drop を trigger しない baseline (1080p OBS で silent-loss 非顕在、memory) → output-neutral (post_match segment 無し、warning も元々空) = 完全一致想定。
  - drop を trigger する baseline があれば → metadata に post_match segment 追加 + warning 消滅 (これは期待される段階2 の変化)。
- timestamp churn (detected_at 等) は非意味的 → grep 除外で output-neutral 判定 ([[feedback_worktree_bash_cwd_drift]] の baseline regen 教訓)。
- flag path 自体 (post-match を flag して残す) を実機で exercise するには drop を trigger する入力が要る。5 OBS baseline が trigger しない場合は unit test が primary、bit-exact は回帰なし確認。drop を trigger する VOD (masked / 4K samples 等) があれば追加 exercise。**実機検証要否・範囲は Pre-flight で Idios に AskUserQuestion** (Iron Law 6: detector.py logic 変更)。

## 7. 後方互換

- 旧 metadata.json (post_match field 無し / warning 有り) は読取互換: `Match` の `post_match` は NotRequired なので absent でも valid。`post_match_trailing_dropped` warning は registry 残置で `sanitize_warnings` が読める。
- 旧 cache (v3) は version bump で miss → 再 detect (silent 再利用なし)。
- GUI: Phase 1 で zod が `post_match` optional / `output_file` optional を受け、§5.2 の no-crash guard で post_match match (`output_file` undefined) を含む metadata を render しても throw しないことを保証する。UI 差分化 (badge / dimmed) と export 除外 UX は Phase 2。

## 8. Phase 2 preview (別 PR、本 spec の対象外詳細)

- CompleteScreen/PreviewScreen で `post_match:true` match を視覚的に区別 (dimmed / badge)。
- export flow で post_match を default 除外 (opt-in で含める)。
- `normalizeForPersistence` が `post_match` を strip せず passthrough (CLI 由来の provenance flag)。
- GUI tests (vitest)。

## 9. #373 互換性 (実装しないが設計で担保)

- 段階2 の `post_match` flag は **>= `min_match_duration` の post-match segment** (Match になりうる) 用。
- #373 の `dropped:{leading,trailing}` は **< `min_match_duration` の余り** (Match にならない span) 用。
- 両者は別機構だが、本 spec の schema 変更 (`$defs/Match` への field 追加) は root への `dropped` section 追加と独立 (互換)。#373 を将来やるとき本 spec の変更を壊さない。
