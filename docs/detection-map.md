# 検出 subsystem 現状 map (Phase 0, re-plan #753)

> L3 検出再アーキ ([spec](superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md))
> の Phase 0 成果物。検出 subsystem の各 layer を **load-bearing / cruft / harmful** に
> 棚卸しし、git 考古学で「なぜ追加されたか」を記録し、再アーキで触る層の coupling を図示する。
> アルゴリズムの現行解説は [video-processing.md](video-processing.md) /
> [scorebar-detection-design.md](scorebar-detection-design.md) を参照 (本 doc は重複させない)。

## 1. 判定の凡例

- **load-bearing**: 撤去・改変すると baseline / 実機が回帰する。再アーキで保持必須。
- **cruft**: 惰性で残存。動作に寄与が薄く、再アーキで整理候補。
- **harmful**: 能動的にバグ/脆さの温床 (例: 不可逆削除 × 弱い否定信号)。再アーキで設計見直し対象。
- **判定保留**: コード読解だけでは確証が持てず、harness 実測 (Phase 2+) で確定する。

## 2. layer インベントリ

> presence.py のシンボル (`localize_present_at` / `scan_presence` / `segment_presence` /
> `detect_matches_by_presence` / `refine_boundary`) は Phase 1 spec の資産で、§5 で扱う。

| layer (シンボル) | module | 責務 (1 行) | 導入 issue | 判定 |
| --- | --- | --- | --- | --- |
| `detect_match_boundaries` | detector.py | 検出 orchestration | #56 | — |
| `_scan_cpu` / Pass1 | detector.py | brightness 粗スキャン | #56/#68 | — |
| `_group_blackout_regions` | detector.py | 暗転フレーム→region | #57 | — |
| `_expand_regions_with_transitions` | detector.py | 遷移拡張 (閾値55) | #71 | — |
| `_refine_blackout_regions` / Pass2 | detector.py | 0.25s 精密計測 | #77 | — |
| `_has_scorebar_v2` | detector.py | GC紋章3点AND (絶対座標) | #307/#522 | — |
| `_has_scorebar` (v1) | detector.py | channel-std+edge fallback | #111 | — |
| `filter_blackouts_with_scorebar` | scorebar.py | 暗転分類 orchestration | #111 | — |
| `classify_blackout` | scorebar.py | match_boundary/in_match/non_fl | #111 | — |
| `_is_static_from_frames` (MAD) | scorebar.py | 静止画面 override | #201/#203 | — |
| `_merge_boundary_pairs` | scorebar.py | 境界ペアマージ | #111 | — |
| audio Fanfare promotion | scorebar.py | in_match→boundary 昇格 | #288 | — |
| `_filter_and_extract_segments` | detector.py | duration filter + segment 抽出 | #77/#388 | — |
| `_drop_post_match_trailing` | detector.py | 試合後 trailing 不可逆削除 | #797/#806 | — |
| GPU Pass1 (`scan_gpu`) | gpu_detector.py | チャンク並列 GPU デコード | #37 | — |
| legacy fps filter path | detector.py | #576 で retire 済の旧 path | #575/#576 | — |
| `localize_scorebar` (P1) | capture_region.py | 位置独立 scorebar 局在化 | #811 | — |
| `detect_region_*` (S1/S3) | capture_region.py | VTuber 領域候補 (脆い) | #807 | — |

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
| #797/#806 | 試合後 trailing 残存 | `_drop_post_match_trailing` | **不可逆削除 × v2 直接プローブ** (#805/Codex #6) |

## 4. coupling 図: `_drop_post_match_trailing` × v2 × membership

(Task 4 で記入)

## 5. 再アーキ (spec) への含意

(Task 5 で記入)
