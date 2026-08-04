# metadata.json `capture_regions` フィールド確定 (#810) design

- 日付: 2026-07-07
- 対象 issue: [#810](https://github.com/Idios/kobutachan-allaganeye/issues/810) (parent: #753)
- 前提 spec: [2026-05-26-vtuber-capture-region-detection-design.md](2026-05-26-vtuber-capture-region-detection-design.md) §4 (出力 contract)
- 決定方式: brainstorming (AskUserQuestion 4 点 + design 承認、2026-07-07)

## 1. 背景と目的

parent #753 の Phase 2a (#807) で `CaptureRegion` / `RegionTimeline` の in-memory contract は確定済みだが、
detector が解決した領域は検出後に破棄され metadata.json に残らない。`RegionTimeline.to_dict` は
実装済みだが未配線 (dead code)。また `masked_fallback_used` には明示 provenance があるのに、
band anchor の FULL_FRAME 縮退は logger.warning のみで metadata に痕跡が残らない非対称がある。

本 design は metadata.json に領域フィールド `capture_regions` を確定し、consumer
(Pass 1 wiring #809 / scorebar ROI #480 / minimap #481 / GUI) が一貫参照できる共有スキーマを与える。

## 2. アプローチ比較

| 案 | 内容 | 判定 |
| --- | --- | --- |
| **A (採用)** | top-level optional `capture_regions` (`RegionTimeline.to_dict` 形式 + `fallback_reason`)。detector は callback seam、cache に保存+引継 | issue 本文 + AskUserQuestion 4 回答と整合 |
| B | `detection_params` 内に埋め込み | region は「出力」であり param でない。cache key 汚染リスク。不採用 |
| C | サイドカー JSON 継続 | issue が metadata.json 本体への確定を要求。不採用 |

## 3. Schema 形状 (schemas/metadata.schema.json = SSoT)

```jsonc
// top-level、optional (pre-#810 ファイルは欠落 = 後方互換)
"capture_regions": {
  "coarse": { "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0,
              "confidence": 1.0, "source": "fallback" },
  "segments": [],          // 要素: { "time_range": [t0, t1], "region": CaptureRegion }
  "fallback_reason": null  // string | null
}
```

- `$defs` に `CaptureRegion` (x/y/w/h: number 0–1、confidence: number 0–1、source: string
  minLength 1、全 required) / `RegionSegment` (`time_range`: 2 要素 number 配列 + `region`、
  全 required) / `CaptureRegions` (coarse + segments + fallback_reason、全 required) を追加。
  いずれも `additionalProperties: false` (既存 defs と同規約)
- `source` は **enum にしない** (free string + 文書化)。warning code と同じ forward-compat 哲学。
  現行値: `"fallback"` (FULL_FRAME) / `"band"` (scorebar 帯 ROI) / `"tierA"` (game 矩形) /
  `"tierB"` (将来 precise)。現行 `CaptureRegion` docstring の source コメントに `"band"` が
  漏れているため修正する
- `fallback_reason` は **required nullable** (writer は常に明示 emit)。値: `"anchor_error"`
  (Stage 0 例外縮退) / `"consensus_miss"` (consensus 不成立縮退) / `null` (縮退なし)。
  free string (将来の縮退種別に開放)
- `schema_version` は `"1"` のまま (additive optional field、#569 / #591 前例)
- codegen 再実行 → `allaganeye/metadata_types.py` + `gui/src/types/metadata.generated.ts` 更新

## 4. Semantics (consumer 向け契約)

- `coarse` = **その run の Pass 1 輝度計測に実際に使われた領域** (前提 spec §4「Tier A
  (Pass 1 用)」と一致)。種別は `source` が示す:
  - 標準 OBS → FULL_FRAME (`source="fallback"`) — issue 受け入れ条件 2 を充足
  - `--vtuber` → scorebar 帯 ROI (`source="band"`)。**game 全矩形ではない**点を
    metadata-spec に明記する (#481 が誤読しないため)
  - masked fallback 採用 run → mask-free game 矩形 (`source="tierA"`)
- `segments` = Tier B per-segment 精密領域。**本 issue では常に `[]`** (#480 P4 が埋める。
  schema だけ先に確定するのが本 issue の趣旨)
- `fallback_reason` は band anchor 縮退の provenance (`masked_fallback_used` との非対称解消)。
  masked の縮退 (mask 不発見) は既存の `masked` / `masked_fallback_used` フラグ対で
  導出可能なため対象外 (文書化のみ)
- 読み手規約: field 欠落 = pre-#810 出力 (領域不明)。unknown な source / fallback_reason
  値は受容する (forward compat)

## 5. 配線 (detector → metadata)

- `RegionTimeline` に `fallback_reason: str | None = None` を追加し `to_dict()` に含める。
  **`from_dict()` classmethod を新設** (round-trip 対称性。dead code だった `to_dict` が
  ここで本配線される)
- `_resolve_detect_region()` の返り値を `tuple[CaptureRegion, str | None]`
  (region, fallback_reason) に変更。既存の logger.warning は維持
- `detect_match_boundaries()` に `region_callback: Callable[[RegionTimeline], None] | None = None`
  を追加 (`brightness_callback` / `masked_fallback_callback` と同型 seam)。
  **最終的に有効だった領域で 1 回だけ**発火する:
  - masked fallback 採用時 → mask-free rect (`_detect_masked_fallback` の返り値を
    `tuple[list[MatchBoundary], CaptureRegion] | None` に拡張)
  - それ以外 → Stage 0 の解決結果 (band or FULL_FRAME + reason)
- `run_detect` / `run_split` が callback で捕捉し
  `_build_metadata_payload(..., capture_regions=...)` へ渡す (optional 引数、None なら省略)

## 6. Cache / round-trip

- `_save_cache`: `capture_regions` (dict 形式) を **top-level** に保存
  (`masked_fallback_used` 同型、cache key 非対象)
- cache-hit: `_read_cached_capture_regions()` で読み出す。**legacy cache** (field なし) は
  cache 記録の `params.vtuber == False` かつ `masked_fallback_used == False` なら標準 path
  確定なので FULL_FRAME timeline を合成し、それ以外 (vtuber / masked) は field 省略
  (領域不明を偽装しない)
- `split --from-metadata`: 既存 preserve パターン (brightness_samples 同型) で元 metadata の
  `capture_regions` を引き継ぐ
- verbose: cache-miss の detection stats と `_display_cache_hit_params` に region 1 行を追加
  (縮退を silent にしない PR #823 R4/R5 方針の延長、表示のみ)

## 7. GUI / Rust

- zod (`gui/src/types/metadata.schema.ts`): `CaptureRegionsSchema` を明示追加し
  `capture_regions: ....optional()`。top-level `.passthrough()` により未更新でも round-trip は
  壊れないが、型付き明示が #612 規約
- GUI 機能追加なし (表示等はスコープ外)。round-trip 保全テストのみ追加
- **Rust `validate_metadata_for_write` は変更なし** (optional field 非検証は
  brightness_samples / system_info の前例に合わせる)。「present だが malformed な optional
  field は zod reload を壊しうる」既存クラスの隙間は capture_regions にも同様に存在する →
  **別 issue に切り出す** (Idios 決定 2026-07-07。起票文面は PR 後に提示)

## 8. Docs 更新

- `docs/metadata-spec.md`: スキーマ定義に field 追加 + 新 §`capture_regions`
  (semantics / source 値 / fallback_reason / cache・round-trip 挙動)
- `docs/output-spec.md`: metadata.json の field 列挙は持たない構造と確認済み。マトリクス /
  保守ルールに触れる箇所が無いか実装時に再確認し、変更不要なら PR 本文で逐条根拠を明記
- `docs/detection-map.md`: capture region の「検出後破棄」記述があれば永続化に更新
- CLAUDE.md: `capture_region.py` 行の責務説明を 1 行更新 (metadata 永続化に言及)

## 9. テスト計画 (TDD)

1. `RegionTimeline` to_dict / from_dict round-trip (fallback_reason 含む) — red first
2. JSON Schema 適合: `test_metadata_schema.py` / `test_metadata_types.py` の既存ハーネスに
   capture_regions ケース追加 (valid / 境界外 x / source 空文字 reject 等)
3. `_build_metadata_payload` が field を emit / None で省略
4. detector `region_callback`: vtuber band 解決 / anchor 例外→`anchor_error` /
   consensus-miss→`consensus_miss` / masked rect / 標準 FULL_FRAME の 5 経路 (mock)
5. cache: save→hit 引継 / legacy 標準→FULL_FRAME 合成 / legacy vtuber→省略
6. `--from-metadata` preserve
7. GUI: zod parse + metadataStore round-trip (vitest) + `npm run typecheck`
   (vitest は型検査しない教訓)
8. codegen drift: `python scripts/codegen/generate.py` 後に diff ゼロ確認
9. **OBS baseline**: 検出 logic の分岐は不変 (観測のみ) だが detector.py を touch するため、
   実動画 baseline 突合で boundaries 不変 + metadata diff が capture_regions のみであることを
   確認する (slow、実機)

## 10. スコープ境界 (やらない)

Pass 1 領域輝度適応 (#809) / scorebar ROI 適応 (#480) / minimap 切抜き (#481) / GUI 表示
(region overlay 等) / warnings 機構での縮退可視化 (#824 隣接) / Rust optional-field 検証拡張
(既存クラス、別 issue 候補)。

## 11. 決定ログ

| 論点 | 決定 (Idios、2026-07-07) |
| --- | --- |
| 縮退 provenance の記録方式 | **reason フィールド** (`capture_regions.fallback_reason`)。warnings 機構は使わない (#824 と非干渉) |
| masked mask-free rect の記録 | **記録する** (coarse = rect、source="tierA") |
| field 名 | **`capture_regions`** (モジュール名 capture_region.py / issue タイトルと一致) |
| cache-hit の扱い | **cache に保存 + 引継** (masked_fallback_used 同型)。legacy cache は標準 path 確定時のみ FULL_FRAME 合成 |
| Rust write 検証の隙間 | **別 issue 起票** (optional field 全体の write-side 検証硬化。起票文面は PR 後に提示) |
| design 全体 | **承認** (2026-07-07 AskUserQuestion) |
| preserve 値の検証 | **in-PR sanitize 硬化** (codex adversarial-review F1、2026-07-07 AskUserQuestion で spec の defer 判断を更新)。cache 二重 read (F2) は別 issue |

## 12. 参照

- issue: [#810](https://github.com/Idios/kobutachan-allaganeye/issues/810) / parent
  [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)
- consumer: #809 (Pass 1 wiring) / #480 (scorebar ROI) / #481 (minimap) / GUI
- contract: `allaganeye/video/capture_region.py` (`CaptureRegion` / `RegionTimeline`)
- 隣接: #824 (probe 失敗縮退の semantics 統一契約) — 縮退の**内部表現・可視化**は #824、
  本 issue は**解決結果の永続化**のみ
- SSoT: `schemas/metadata.schema.json` → codegen (#612) / `docs/metadata-spec.md`
