# 検出 subsystem 現状 map (Phase 0, re-plan #753)

> L3 検出再アーキ ([spec](superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md))
> の Phase 0 成果物。検出 subsystem の各 layer を **load-bearing / cruft / harmful** に
> 棚卸しし、git 考古学で「なぜ追加されたか」を記録し、再アーキで触る層の coupling を図示する。
> アルゴリズムの現行解説は [video-processing.md](video-processing.md) /
> [scorebar-detection-design.md](scorebar-detection-design.md) を参照 (本 doc は重複させない)。

## 1. 判定の凡例

- **load-bearing**: 撤去・改変すると baseline / 実機が回帰する。再アーキで保持必須。
- **cruft**: 惰性で残存。動作に寄与が薄く、再アーキで整理候補。
- **harmful**: 能動的にバグ/脆さの温床 (例: 弱い否定信号に依存した不可逆操作)。再アーキで設計見直し対象。
- **判定保留**: コード読解だけでは確証が持てず、harness 実測 (Phase 2+) で確定する。

## 2. layer インベントリ

> presence.py のシンボル (`localize_present_at` / `scan_presence` / `segment_presence` /
> `detect_matches_by_presence` / `refine_boundary`) は Phase 1 spec の資産で、§5 で扱う。

| layer (シンボル) | module | 責務 (1 行) | 導入 issue | 判定 |
| --- | --- | --- | --- | --- |
| `detect_match_boundaries` | detector.py | 検出 orchestration | #56 | load-bearing |
| `_scan_cpu` / Pass1 | detector.py | brightness 粗スキャン | #56/#68 | load-bearing |
| `_group_blackout_regions` | detector.py | 暗転フレーム→region | #57 | load-bearing |
| `_expand_regions_with_transitions` | detector.py | 遷移拡張 (閾値55) | #71 | load-bearing (要調整) |
| `_refine_blackout_regions` / Pass2 | detector.py | 0.25s 精密計測 | #77 | load-bearing |
| `_has_scorebar_v2` | detector.py | GC紋章3点AND (絶対座標) | #307/#522 | load-bearing (provisional) |
| `_has_scorebar` (v1) | detector.py | channel-std+edge fallback | #111 | cruft |
| `filter_blackouts_with_scorebar` | scorebar.py | 暗転分類 orchestration | #111 | load-bearing (再編対象) |
| `classify_blackout` | scorebar.py | match_boundary/in_match/non_fl | #111 | load-bearing (再編対象) |
| `_is_static_from_frames` (MAD) | scorebar.py | 静止画面 override | #201/#203 | 判定保留 (脆い) |
| `_merge_boundary_pairs` | scorebar.py | 境界ペアマージ | #111 | load-bearing |
| audio Fanfare promotion | scorebar.py | in_match→boundary 昇格 | #288 | load-bearing (FP余地) |
| `_filter_and_extract_segments` | detector.py | duration filter + segment 抽出 | #77/#388 | load-bearing (backstop) |
| `_flag_post_match_trailing` | detector.py | 試合後 trailing を post_match フラグ付与 (非破壊) | #797/#806/#805 | load-bearing (再編対象) |
| GPU Pass1 (`scan_gpu`) | gpu_detector.py | チャンク並列 GPU デコード | #37 | load-bearing |
| legacy fps filter path | detector.py | #576 で retire 済の旧 path | #575/#576 | cruft |
| `localize_scorebar` (P1) | capture_region.py | 位置独立 scorebar 局在化 | #811 | load-bearing (新基盤) |
| `detect_region_*` (S1/S3) | capture_region.py | VTuber 領域候補 (脆い) | #807 | 判定保留 (脆い) |

### 判定根拠 (脚注)

- **`detect_match_boundaries`**: 検出パイプライン全体の orchestration entry point。撤去不可。
- **`_scan_cpu` / `_group_blackout_regions` / `_refine_blackout_regions`**: spec §3.1① brightness が境界検出の主軸。spec A.3 で OBS 秒未満精度を実証。load-bearing。
- **`_expand_regions_with_transitions`**: OBS 録画では境界拾い漏れ防止に必須。ただし VTuber crop では lobby 輝度と重なり過剰 merge が発生する (spec P5 / re-plan #809 Wave F)。load-bearing だが VTuber 対応で閾値調整が必要。
- **`_has_scorebar_v2`**: OBS で高特異度を実現する GC 紋章 3 点 AND ガード (Codex #3)。`_flag_post_match_trailing` と `_probe_scorebar_context` (scorebar.py) の 2 箇所から呼ばれる hidden coupling がある (Codex #6)。spec Q3 で `localize_scorebar` に置換予定だが parity 実証まで authoritative として温存 (provisional)。
- **`_has_scorebar` (v1)**: opencv 未インストール時の fallback のみ。実運用では opencv を同梱するため経路はほぼ死んでいる。cruft。
- **`filter_blackouts_with_scorebar` / `classify_blackout`**: 暗転分類の orchestration と個別判定。spec §5 で primitive を `localize_scorebar` + motion に差し替える再編対象だが現在は load-bearing。
- **`_is_static_from_frames` (MAD)**: short blackout 限定の局所 override として #201/#203 で追加。spec Q5 で分類補助に昇格予定だが Codex #1 で primary 化が未検証のため判定保留。
- **`_merge_boundary_pairs`**: 二重境界を 1 ペアにまとめる対症修正。現行パイプラインで必要。流用予定。
- **audio Fanfare promotion**: scorebar 残像で `in_match` に誤分類された境界を音声で救済 (#288)。Fanfare は試合中にも弱いピークを出すため FP 余地が残る。
- **`_filter_and_extract_segments`**: `min_match_duration` (default 300 s) でリザルト画面を backstop 除去する。spec §3.5 でこの duration filter が真の backstop と実証されている。
- **`_flag_post_match_trailing`**: 試合後 trailing を scorebar 不在 (弱い否定信号) を根拠に判定するが、#805 段階2 で**削除を廃止し `post_match: true` フラグ方式に置換**した (旧 `_drop_post_match_trailing` の `segments[:-1]` 不可逆削除を撤去)。flag された segment は metadata に保持され default split (MP4) からのみ除外されるため、`_has_scorebar_v2` FN 環境でも実試合を silent に削除する事故 (試合 1 本喪失) は構造的に起こらない (削除という操作自体が存在しない)。`_has_scorebar_v2` を直接呼ぶ coupling は維持 (§4)。load-bearing (再編対象)。
- **GPU Pass1 (`scan_gpu`)**: `--gpu` 経路の主実装。CPU Pass1 と結果 parity が必要 (Codex #8)。load-bearing。
- **legacy fps filter path**: #576 で新 path を default 化、env var `ALLAGANEYE_DETECT_FPS_FILTER=1` の rollback 専用。v0.3.x で削除予定。cruft。
- **`localize_scorebar` (P1)**: 再アーキの分類器核。VTuber 配信の任意 inset 位置に対応する anchor として設計。load-bearing (新基盤)。
- **`detect_region_*` (S1/S3)**: re-plan R6 で scorebar 帯 anchor を主軸とし S3 を補助に降格。ハーネス実測前は確証が持てないため判定保留。

## 3. git 考古学 (なぜ追加されたか)

> 詳細経緯は [video-processing.md §設計経緯](video-processing.md#設計経緯) に既出。
> 本節は「対症修正が積層した順序」と「各層が生んだ新たな制約」に絞る。

| 時期 | 契機 (課題) | 追加 layer | 生んだ制約/脆さ |
| --- | --- | --- | --- |
| #60 | リスポーン暗転の誤検知 | min_blackout_duration filter | 短い真境界も落ちうる |
| #71 | 試合境界の未検出 (パターンB) | `_expand_regions_with_transitions` (閾値55) | lobby 輝度依存。VTuber crop で過剰 merge (#809 Wave F) |
| #77 | 境界未検出 (パターンC) | Pass2 refine + duration filter | — |
| #107 | キャラダウン暗転 | `in_match` duration guard | — |
| #108/#109 | 非 FL コンテンツ | `non_fl` 分類 | — |
| #111 | scorebar 分類統合 | `filter_blackouts_with_scorebar` 一式 | 絶対座標前提 (VTuber inset で破綻 = #480) |
| #201/#203 | 静止ローディング誤分類 | `_is_static_from_frames` (MAD override) | short blackout 限定の局所 override |
| #288 | scorebar 残像で境界誤分類 | audio Fanfare promotion | Fanfare 試合中弱ピークで FP 余地 |
| #307/#522 | scorebar FP | `_has_scorebar_v2` (GC紋章3点AND) | 絶対/相対 two-path。位置特異 = VTuber 不可 |
| #797/#806 | 試合後 trailing 残存 | `_flag_post_match_trailing` (#797 当初は不可逆削除→#805 でフラグ化) | v2 直接プローブの coupling (Codex #6)。当初の不可逆削除リスクは #805 段階2 で撤去済 |

## 4. coupling 図: `_flag_post_match_trailing` × v2 × membership

`_flag_post_match_trailing` (detector.py) は segment 抽出の **後段**で、最終 segment が
post-match trailing (lobby/city) かを **v2 scorebar の不在を根拠に判定**し、該当時は
`post_match: true` フラグを付与する (#805 段階2 で不可逆削除を撤去、非破壊)。

```text
segments 抽出 (_filter_and_extract_segments)
        │
        ▼
最終 segment が type=unknown かつ end≈動画末尾 かつ len>=2 か?
        │ yes
        ▼
早期 candidate-match 窓を _TRAILING_PROBE_STRIDE で v2 プローブ
        │
        ├─ どれか True / None (probe 失敗) → そのまま keep (通常 match 扱い)
        └─ 全て False (definite miss)      → segments[-1]["post_match"]=True  ← フラグ付与 (非破壊、削除なし)
```

> #805 段階2 で旧 `segments[:-1]` 不可逆削除を撤去。flag された segment は metadata に
> 保持され default split (MP4) からのみ除外されるため、scorebar FN による silent-loss
> (試合 1 本喪失) は構造的に起こらない (削除という操作が存在しない)。

### 競合シナリオ (Codex #6 / spec R4)

| 変更 | trailing 判定への影響 |
| --- | --- |
| v2 を localize に置換 (Q3) | trailing 判定は v2 を直接呼ぶ (`_flag_post_match_trailing` 内の `_has_scorebar_v2` 直接呼び出し)。置換すると **第 2 の分類器が暗黙に挙動変化**。localize はリザルト 91% present → trailing を「試合あり」と誤判定し flag し損ねる、逆に VTuber では本物 trailing を post_match 扱い (R3) |
| membership 信号導入 (Q4) | membership は segment 抽出の前段。trailing 判定は後段で独立に再判定するため、**2 つの membership 判断が二重化** |
| #805 非破壊化 (段階2 Phase 1 完了) | 不可逆削除 → `post_match` フラグ方式に置換済。出力契約は「最終 segment を消す」から「flag して MP4 から除外・metadata 保持」に変わった (silent-loss クラス消滅) |

### 結論 (Phase 1+ への制約)

- spec §3.4 の通り、**Phase 1-3 は v2 を温存**し trailing 判定 (`_flag_post_match_trailing`) を現状のまま据え置く。
- #805 非破壊化 (削除 → `post_match` フラグ) は段階2 Phase 1 で完了済。membership 統一は **Phase 4 cutover 以降の別 phase**で、trailing 判定を新 membership と同じ根拠に統一するか shadow 無効化してから扱う。
- Phase 2 で localize を shadow 並走させる際、**trailing 判定は v2 (authoritative) のまま**にする (localize を trailing 判定に配線しない)。

## 5. 再アーキ (spec) への含意

### 5.1 Phase 1 で保持必須 (load-bearing)

- brightness Pass1/Pass2、duration filter (backstop)、`_merge_boundary_pairs` は OBS で bit-exact 維持。
- `_has_scorebar_v2` は authoritative 温存 (Q3 provisional)。

### 5.2 Phase 1 で触る (再編)

- `classify_blackout` の検出 primitive を localize+motion 化 (shadow 並走、§2 判定参照)。
- `_is_static_from_frames` を band-anchor 化 (絶対 ROI → localize bbox、spec §5)。OBS は絶対 ROI 縮退。

### 5.3 触ってはいけない (Phase 4 以降)

- `_flag_post_match_trailing` (#805 で非破壊化済。§4 の通り v2 coupling 故に L3 再アーキ Phase 1-3 は据え置き)。
- legacy fps filter path (cruft、別 issue で撤去)。

### 5.4 presence.py 資産 (spec §10)

- `compare_segments` (`tests/presence_harness.py`) / GT 突合ハーネス → 検証インフラとして存続。
- `localize_present_at` → Stage 2 分類で再利用。
- `scan_presence` / `segment_presence` / `detect_matches_by_presence` → VTuber + 診断専用に降格 (OBS production 経路では使わない)。
- branch `claude/l3-p2-region-detection` は Phase 1-2 実装で継続使用。
