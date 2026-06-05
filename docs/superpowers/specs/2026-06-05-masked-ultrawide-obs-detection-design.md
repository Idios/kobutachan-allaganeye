# masked + ultrawide OBS 検出対応 設計 (Sub-project A: 検出コア, 2026-06-05)

> L3「配信形式対応」の再定位。VTuber inset 検出 ([2026-05-31 spec](2026-05-31-l3-detection-rearchitecture-two-signal-design.md)) が
> 実機の不規則遷移で頭打ち・**保留** (#480) となった一方、**チャットを隠すマスク画像を全画面録画に重ねるユーザー**の動画は
> 実証の結果 **tractable** と判明した。本 spec はその masked + ultrawide OBS 録画の検出対応 (検出コア) を設計する。
>
> **Status**: brainstorming 完了 / user 承認待ち (spec review gate)
> **基づく**: 2026-06-05 実機検証 (本 § 5) + parked Phase 0/1/2 機構 (#480 branch `claude/l3-p2-region-detection`)
> **完了基準**: GUI 統合まで (user 確定)。本 spec = **Sub-project A (検出コア・CLI)**。**Sub-project B (GUI 領域調整 UI)** は A 完了後の別サイクル (本 spec 範囲外、別 spec)。

## 1. 背景: VTuber は defer、masked-OBS は直せる

L3 の `配信形式対応` には 2 つの非標準フォーマットが含まれる:

| | VTuber inset (defer 済 #480) | masked + ultrawide OBS (本 spec) |
| --- | --- | --- |
| 失敗の仕方 | under-detection (5/~11 試合) | **全滅** (0 blackout → 7h が 1 segment) |
| 根本原因 | 遷移が暗転でない**不規則な静止画面** | **明るいマスクが暗転中も点灯** → 全画面平均が閾値を割らない |
| game の写り方 | 小窓 inset (位置不定・脆い) | **全画面・scorebar も明瞭** |
| 直し方 | 別アプローチ要研究 (手詰まり) | **mask-free 領域の輝度を測る** (実証済) + ultrawide は localize 分類 (実証済) |

VTuber は「信号そのものが変則」で手詰まりだったが、masked-OBS は「信号はあるのに明るいマスクで平均が持ち上がっている」だけ。**game 領域 (mask 以外) を測れば本物の暗転が復活する**。

## 2. 確定方針 (brainstorming 2026-06-05, user 承認)

| # | 論点 | 決定 |
| --- | --- | --- |
| Q1 | 完了基準 | **GUI 統合まで** (v0.3.0)。A=検出コア / B=GUI に分解、A 先行 |
| Q2 | mask-free 測定領域の決定 | **自動検出 (static-overlay) + GUI 調整**。「暗転で暗くなる=game / 常時明るい=マスク」を動画から判定 |
| Q3 | masked mode の起動 | **自動 fallback** (標準 detect が blackout 0 → masked mode へ自動再検出)。標準 path 不変 = bit-exact 構造保証。`--masked` flag で override |
| Q4 | 分類器 | **localize present** (Phase 2 `_classify_blackout_localize`)。v2 は ultrawide 不可、localize は可 (§5 実証) |
| Q5 | 土台 | **parked Phase 0/1/2 の汎用機構を再利用** (region threading / `region_mean` / localize primitive / localize 分類器)。VTuber 固有 (band-anchor / `--vtuber` user flag) は再利用しない |

## 3. アーキテクチャ: 標準 path + masked fallback

```text
入力動画
  │
  ├─[標準 detect] 全画面 brightness Pass1 (現行不変)
  │      │
  │      ├─ blackout > 0 → 現行どおり (Pass2 → scorebar 分類 → segment) = bit-exact
  │      │
  │      └─ blackout == 0 (明確な失敗) ─┐
  │                                      ▼
  └─[masked fallback] (または --masked override)
         1. 自動領域検出 (static-overlay) → mask-free 測定矩形
         2. その矩形で Pass1/Pass2 再検出 (Phase 1 region 機構)
         3. localize present 分類 (Phase 2、ultrawide 対応)
         4. segment 抽出 (現行 duration filter 等)
```

**bit-exact の構造保証**: 標準 path (fallback 非 trigger) のコードは一切変えない。OBS 5 baseline は必ず blackout を拾う (full-frame で暗転が見える) ため fallback に入らず、現行と byte 一致。masked fallback path は「標準 path が 0 blackout を返した後」にのみ走る純粋な追加経路。VTuber で 2 度割った「standard path 内の always-on auto 推論」とは構造的に異なる (§10 R1)。

## 4. コンポーネント (Sub-project A)

### 4.1 自動領域検出 (static-overlay) — parked S3 の精緻化

- 疎サンプルした N フレーム (試合中＋暗転を含む) で per-pixel 判定: **最大輝度 > bright かつ 最小輝度 < dark = game** (暗転で暗くなる)。マスクは min が下がらない (常時明るい) ため除外。
- parked `capture_region.detect_region_blackout_overlap` (S3) が発想の土台。S3 は最大連結成分の **bbox** を返すが、内側/端マスクでは bbox がマスクを含みうる → **mask-free な測定矩形**を出す形に精緻化 (例: マスク bbox を求め、それを避ける最大 clean rectangle / または game bbox からマスク列を除外)。
- 出力 = 正規化 `CaptureRegion` (矩形)。既存 region 機構は矩形ベースのため矩形で受ける。GUI(B) がこの自動領域を表示し confirm/adjust。
- **bit-exact 不変**: 本検出は masked fallback path 内のみ。標準 path は呼ばない。

### 4.2 region-aware brightness (Phase 1 再利用)

- 4.1 の矩形を Pass1 (`_scan_cpu` / `scan_gpu`) / Pass2 (`_refine_blackout_regions`) に `region=` で渡す。`region_mean` がマスクを除外した game 矩形で平均輝度を測る。§5 で 74 blackout を実証。
- 完全に Phase 1 の実装済み機構 (region threading)。新規実装なし。

### 4.3 localize present 分類 (Phase 2 再利用)

- masked fallback の分類は `_classify_blackout_localize` (present 単独)。masked-OBS の遷移は**本物の暗転** (マスクで隠れていただけ) なので、in-match flank に scorebar present (localize=True) → 正しく match_boundary 分類。VTuber の under-detection (遷移が暗転でない) 問題は構造的に起きない。
- v2 (絶対 1920x1080 座標) は ultrawide 3440x1440 の歪みリサイズで FN (§5)。localize (位置独立) は detect 成功 (§5)。よって masked/ultrawide path は localize 必須。

### 4.4 起動 (fallback trigger)

- 標準 Pass1 完了後、blackout フレーム数 == 0 を検出したら masked fallback へ。明確な失敗信号 (実 FL 録画は必ず暗転を持つ)。
- `--masked` CLI flag で fallback を強制 (partial mask = full-frame で一部 blackout を拾うが under-detect するケース用の override)。GUI(B) の masked トグルも同経路。

## 5. 実証データ (2026-06-05, 実機)

サンプル: `E:\allaganeye-samples\20250527-29\` の 3 録画 (3440x1440 ultrawide, h264, 39-82GB, チャットを隠すキャラ立ち絵マスクを左下＋中右に静止合成)。

| 検証 | 方法 | 結果 |
| --- | --- | --- |
| 標準 path が壊れる | `detect` (--vtuber なし, OBS path) on 2026-05-29 (7h07m) | **0 blackout / 7h が 1 match** = 全滅 |
| 領域で暗転復活 | top 30% region で `scan_gpu` (first 2h) | **74 blackout** (full-frame は 0), region min 輝度 0.0 |
| ultrawide scorebar | gameplay 3 frame で v2 / localize | **v2=False / localize=True** (×3) |

→ masked-OBS は (a) region-aware 輝度で暗転復活 + (b) localize で ultrawide scorebar 分類、の両方が実機で成立。検証スクリプト: `_validate_masked.py` / `_validate_scorebar_uw.py` (branch、untracked)。

## 6. スコープ境界

**Sub-project A (本 spec) がやること**:

- masked fallback (trigger + 自動領域検出 + region brightness + localize 分類)。
- OBS 5 baseline bit-exact 維持。masked 3 サンプルの実用分割。
- `--masked` CLI flag (override)。

**やらないこと (範囲外 / 後 Phase)**:

- **Sub-project B (GUI 領域調整 UI)**: A 完了後の別 spec/plan/実装サイクル。A は GUI が消費する自動領域 (`CaptureRegion`) を出すところまで。
- **VTuber inset 検出**: defer 済 (#480、本 spec は復活させない)。`--vtuber` user-facing flag は under-detect するため hidden/experimental 化 (§9)。
- **partial mask の頑健化 / 一般のマスク配置・解像度への汎化**: 本 spec は実証済の masked+ultrawide ケースを実用化する最小。汎化は後続。
- **per-pixel mask 測定**: 本 spec は矩形 region (既存機構)。内側マスクで最大 clean rectangle が小さすぎる等の限界が出たら per-pixel 化を別途検討。

## 7. データ構造 / API

- **再利用 (parked Phase 0/1/2, branch)**: `region_mean` / region threading (`_scan_cpu`/`scan_gpu`/`_refine_blackout_regions` の `region=`) / `_probe_scorebar_context(with_localize=)` / `_localize_present_from_raw` / `_classify_blackout_localize` / `detect_region_blackout_overlap` (S3, 精緻化対象)。
- **新規 (Sub-project A)**: masked fallback orchestration (trigger 判定 → 自動領域 → region 再検出 → localize 分類)、static-overlay 領域検出の精緻化 (S3 → mask-free 矩形)、`--masked` flag。
- **出力**: 現行 `matches[]` / metadata.json schema 不変 (region フィールド永続化は B / 別途)。

## 8. 検証戦略

- **unit (動画不要)**: static-overlay 領域検出 (合成 frame: マスク=常時明るい / game=暗転で暗くなる → mask-free 矩形)。fallback trigger (0 blackout → masked mode 起動、>0 → 標準 path)。矩形 region brightness。localize 分類 (§4.3、Phase 2 既存 unit 流用)。
- **slow・実機 (Idios)**: 3 masked サンプルで実用分割 (試合数・境界の目視)。**OBS 5 baseline bit-exact** (fallback 非 trigger を構造確認)。CPU/GPU parity。
- **gate**: OBS bit-exact (baseline diff) + masked サンプル実用分割 (demonstrated-level)。

## 9. 土台・branch 戦略 (plan で確定)

parked Phase 0/1/2 (`claude/l3-p2-region-detection`、origin push 済、OBS bit-exact 実証済 §5) を土台に masked-OBS を構築する。landing 戦略は plan で確定する候補:

- (a) **parked branch を継続拡張** → Phase 0/1/2 + masked-OBS を「L3 配信形式対応」1 PR で land (`--vtuber` flag は hidden 化)。
- (b) Phase 0/1/2 (汎用機構, bit-exact, review 済) を先に develop-0.3.0 へ land → masked-OBS を別 PR で上に積む。
- いずれも `refactor-pattern.md` の Phase 分割閾値 (touched>30 / diff>1000) を確認。

`--vtuber` user-facing flag: under-detect するため masked land 時に **hidden / experimental 化** (内部 region 機構は残す)。

## 10. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | 自動領域検出が標準 OBS の bit-exact を壊す (VTuber で 2 度発生) | **masked fallback path 内に閉じ込め** (標準 path は呼ばない)。標準 path は構造的に不変。baseline は fallback 非 trigger を実機確認 |
| R2 | static-overlay 領域検出が内側/端マスクで不正確 (S3 bbox 限界) | mask-free 矩形化で精緻化。最大 clean rectangle が小さすぎる場合は GUI(B) で調整、または per-pixel 化 (後続) |
| R3 | fallback trigger (0 blackout) が partial mask を拾わない | `--masked` override + GUI トグル。partial mask 汎化は後続 |
| R4 | localize が masked/ultrawide で誤検出 (位置独立ゆえの noise) | Phase 2 の present majority + 実機 GT で確認。masked-OBS は遷移が本物の暗転なので VTuber より素直 |
| R5 | CPU/GPU/ultrawide リサイズ parity | 検証 matrix に CPU/GPU。region は正規化座標で解像度非依存 |

## 11. 参照

- VTuber spec (defer、土台機構の出所): [2026-05-31-l3-detection-rearchitecture-two-signal-design.md](2026-05-31-l3-detection-rearchitecture-two-signal-design.md)
- Phase 0 map: [docs/detection-map.md](../../detection-map.md)
- parked 実装: branch `claude/l3-p2-region-detection` (Phase 0/1/2, origin push 済)
- 実証スクリプト: `_validate_masked.py` / `_validate_scorebar_uw.py` (branch, untracked)
- 関連 issue: [#480](https://github.com/Idios/kobutachan-allaganeye/issues/480) (VTuber 検出, defer), [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) (minimap), [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753) (配信形式対応 parent) — masked-OBS の新規 issue 起票は Iron Law 2 で起票時 AskUserQuestion
