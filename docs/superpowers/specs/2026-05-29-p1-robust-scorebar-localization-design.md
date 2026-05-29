# P1: robust scorebar 局在化 (anchor) 設計 (2026-05-29)

> **Status**: brainstorming 完了 / writing-plans へ
> **Parent (re-plan)**: [2026-05-28-vtuber-region-boundary-replan-design.md](2026-05-28-vtuber-region-boundary-replan-design.md) §3 P1 / §6 P1 スケッチ
> **上位 issue**: [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)
> **基づく**: Phase 2a ([2026-05-26-vtuber-capture-region-detection-design.md](2026-05-26-vtuber-capture-region-detection-design.md)) の S2 / `_has_scorebar_v2`、#809 Wave F 実機検証
> **issue 対応**: 起票方針は Iron Law 2 で user 承認後に確定 (§11)。案: #480 を localization(P1)+classification(P4) に再定義し P1 を内包

## 1. 目的

任意の単フレームから FL scorebar を **位置独立** (game inset の x/y 位置・HUD スケールに非依存) に局在化し、span・位置・confidence を返す純粋関数 `localize_scorebar` を提供する。これは再アーキテクチャ (replan) の **上流 anchor** であり、P2 (領域検出) と P4 (#480 境界分類) の共有基盤になる。

replan の核心: **FL scorebar の HUD 幾何はコンテンツ固定**で encoder/overlay/inset 位置に依存しない。よって「黒画面の深さ」(脆い・1-source 過学習) ではなく scorebar 幾何を anchor にすることで原理的に頑健化する。

## 2. スコープと成果物

### 2.1 P1 の成果物

- `ScorebarLocalization` dataclass (§4)
- `localize_scorebar(frame: np.ndarray) -> ScorebarLocalization | None` (`allaganeye/video/capture_region.py`)
- 補助 helper (saturated-run 列挙 / emblem margin、§5)
- 上記のユニット/合成/実フレーム テスト (§8)

### 2.2 P1 がやらないこと (境界)

| 項目 | 担当 |
| --- | --- |
| game 矩形の逆算 (span → game rect) | **P2** (現 S2 の `gw/gh` 逆算ロジックは P2 へ移設) |
| 複数フレーム consensus / median | **P2** |
| 暗転分類 (`match_boundary`/`in_match`/`non_fl`) | **P4 (#480)** |
| coarse region の metadata 永続化 | **P6 (#810)** |
| detect pipeline への wiring | **P2 / P3 / P4** |

P1 は **単フレーム localization のみ**。robustness (外れ値除去) は P2 の多フレーム consensus が担う。

### 2.3 不変条件 (判定挙動を変えないもの)

`_has_scorebar_v2` / `_probe_scorebar_context` / `_drop_post_match_trailing` / `_find_scorebar_horizontal_range` の **判定挙動 (bool/span の結果) は不変**。P1 は Additive (新規関数) で追加し、OBS 分類 path には P1 を一切結線しない (§7)。

注: §5.2/§5.3 で共有 helper を extract する選択肢を採る場合も、それは **挙動完全保存 (behavior-preserving) な内部抽出**に限り、上記関数の判定結果は 1 bit も変えない (§8.4 F4 parity test で担保)。「touch しない」の核心は OBS 判定の不変であり、内部構造の保存的抽出は許容範囲。D1 (Additive) の趣旨を最優先して zero-touch を選ぶこともできる (§5.2)。

## 3. 決定事項 (brainstorming 2026-05-29)

| # | 論点 | 決定 | 理由 |
| --- | --- | --- | --- |
| D1 | 実装構成 | **Additive (新規 `localize_scorebar`)**。`_has_scorebar_v2` は不変 | wired・OBS bit-exact 検証済 primitive を touch せず、OBS 回帰を構造的に防止。replan の「新ロジックを gate 内に封じる」哲学に合致 |
| D2 | 局在化アルゴリズム | **方式1: all-runs × all-y band scan + emblem-AND gate** | 検証済み emblem-AND (zero-FP) を最終 discriminator にする素直な一般化。x/y 位置独立。#803 center-straddling 前提を構造的に解消 |
| D3 | S2 (`detect_region_scorebar_band`) | **P1 で退役** (`localize_scorebar` に一般化、テストは localize 系へ移行) | unwired・superseded。dead/重複コードを残さず clean。overview の「S2 を一般化」に沿う |
| D4 | multi-source 検証 | **P1 のマージ gate (受け入れ条件)**。実装+gyawa+合成は今進め、追加 source 入手・guard verify・検証完了まで **P1 マージは保留** | 追加 VTuber source 入手見込みあり。gyawa 1-source 過学習リスク (R2) を実データで潰してから land する |

> **D4 の replan との差分**: replan §5/§8 は multi-source を「data-gated *follow-up*」としていたが、本 P1 では user 判断により **マージ gate** に強化する。これは P1 (および依存する P2→P4→P5 chain) の land を multi-source データ入手まで保留することを意味する (§8.4 / §10 で chain 影響を明記)。
>
> **D2 の plan 時改訂**: 方式1 の y 走査 hit 選択を当初の first-hit short-circuit から **best-hit (emblem margin 最大の候補を選択)** に変更した (plan 作成時に first-hit の confidence/y 精度問題が判明、2026-05-29 user 承認済)。詳細・理由は §5.4。

## 4. API / データ構造

```python
@dataclass(frozen=True)
class ScorebarLocalization:
    x_left: int        # 1920x1080 probe 上の px、inclusive
    x_right: int       # px、inclusive
    y_top: int         # scorebar 帯の上端 px (P2 はこれを game 上端 anchor に使う)
    y_bottom: int      # y_top + band_h
    confidence: float  # [0,1]、emblem margin 由来 (§6)
```

- **入力**: `np.ndarray (1080, 1920, 3) uint8` (RGB)。caller は `_probe_frame_rgb_hires` で取得。
- **座標系**: probe px (emblem 機構と同一基準で精度確保)。正規化 ([0,1]) は consumer (P2) が `/1920, /1080` で実施。
- **戻り値**: 局在化成功で `ScorebarLocalization`、非試合/検出不能/cv2 不在/形状不一致で `None` (§7)。

## 5. アルゴリズム (方式1)

### 5.1 擬似コード

```text
localize_scorebar(frame):                       # frame: (1080,1920,3) uint8
    if cv2 unavailable: return None
    if frame.shape != (1080,1920,3): return None
    band_h = _SCOREBAR_SCAN_Y_END - _SCOREBAR_SCAN_Y_START   # = 45
    y_max  = int(1080 * _BAND_Y_MAX_FRAC)                     # ≈ 594
    best = None                                  # (margin, x_left, x_right, y)
    for y in range(0, y_max, stride):            # stride 既定 = _BAND_SCAN_STRIDE (6) → ~99 steps (全走査)
        band = frame[y : y + band_h]             # (45,1920,3)
        for (x_left, x_right) in saturated_runs(band):   # width-gated 全 run、center 前提なし
            positions = emblem_positions(x_left, x_right, y)   # _EMBLEM_RELATIVE_POSITIONS
            margin = emblem_and_margin(frame, positions)       # 3点 AND 通過なら最弱 margin、不通過 None
            if margin is not None and (best is None or margin > best.margin):
                best = (margin, x_left, x_right, y)            # best-hit: 最大 margin を保持
    if best is None: return None
    return ScorebarLocalization(best.x_left, best.x_right, best.y, best.y + band_h, conf(best.margin))
```

### 5.2 saturated_runs (#803 center-straddling の撤廃)

既存 `_find_scorebar_horizontal_range` は (a) sat/val 閾値で per-pixel mask → (b) col-ratio で saturated column 判定 → (c) gap-merge で run 構築 → (d) **screen center を straddle する run のみ採用** → (e) width gate、という流れ。

P1 の `saturated_runs(band)` は **(a)〜(c) を共有**し、(d) を撤廃して **width-gated 全 run のリスト**を返す:

- 撤廃理由: VTuber inset は frame 中心に無いため center-straddling 前提が破綻する。
- #803 (post-match 広帯の誤検出) の代替防御: 全 run に emblem-AND をかける。post-match の彩度帯は emblem-AND (zero-FP 検証済) で落ちるので、center 前提なしでも誤検出しない。
- width gate (`_SCOREBAR_SCAN_MIN_WIDTH_PX`=500 .. `_SCOREBAR_SCAN_MAX_WIDTH_PX`=1440) は既定維持。

**実装手段** (plan/TDD で確定、いずれも OBS 判定不変):

- **案 A (zero-touch、D1 趣旨最優先)**: P1 側で run 構築 (a)〜(c) を ~15 行持つ。`_find_scorebar_horizontal_range` を一切編集しない。
- **案 B (共有 extract)**: (a)〜(c) を behavior-preserving な pure helper `_scorebar_saturated_runs(band)` に抽出し、`_find_scorebar_horizontal_range` (center+width filter を後段適用) と P1 (width filter のみ + 全 run) が共用。重複ゼロだが wired 関数の内部を保存的に書き換える。§8.4 F4 parity test で挙動保存を担保。

D1 (Additive) を OBS 安全のため選んだ経緯から既定は案 A 寄り。重複を嫌う場合に案 B を選択 (parity test で安全)。どちらでも **OBS 判定は 1 bit も変わらない**。

### 5.3 emblem_positions / emblem_and_margin

- `emblem_positions(x_left, x_right, y)`: `_EMBLEM_RELATIVE_POSITIONS` の `(name, cx_rel, hw_rel, ey1, ey2)` から、span 幅 `bar_w = x_right - x_left` を基準に各 emblem の絶対矩形を算出 (現 S2 / `_has_scorebar_v2` Path2 と同一式)。y オフセットを加算して band 内座標を frame 座標へ戻す。
- `emblem_and_margin(frame, positions)`: 各 emblem で `mean_sat` (bright pixel) と `edge_density` (Sobel) を計算し、`_EMBLEM_SAT_THRESHOLD`(70) / `_EMBLEM_EDGE_THRESHOLD`(40) と比較。3点すべて両閾値超なら最弱 margin を返し、1点でも不通過なら `None`。bool だけ返す既存 `_emblem_and_check` の margin 版。
  - **実装手段** (plan/TDD で確定、§5.2 と同じ案 A/案 B の trade-off): 案 A = P1 側に margin 計算を持つ (`_emblem_and_check` 不変)。案 B = `_emblem_and_margin` を新設し `_emblem_and_check` をその bool ラッパに保存的 refactor (OBS parity で担保)。いずれも `_has_scorebar_v2` の判定不変。

### 5.4 探索順序とコスト (best-hit、plan 作成時の改訂)

- **best-hit**: y を全走査し、emblem-AND 通過候補のうち **margin 最大の (run, y)** を返す。当初案の first-hit short-circuit は、scan band が scorebar 帯に**部分的に重なった時点** (true y_top 手前) で AND が通り、(a) y_top が ±stride 超ずれ、(b) 部分重なりで sat が薄まり confidence が clean in-match でも低く出る、という問題があったため改訂 (plan 作成時に判明、user 承認済)。best-hit は最大整合の y を選ぶため y_top 精度 ±stride/2、confidence は最良整合 margin になる。
- コスト: short-circuit を持たず常に ~99 y-step 全走査 (band の HSV 変換 + run 構築)。emblem-AND は width-gated run (非試合では 0〜1 本) のみに走るため、支配コストは per-y の HSV 変換 (cheap numpy)。spec §5.1/§9 R3 が「最悪は全走査」を既に織り込み済み。
- `stride` は引数で可変 (既定 6)。P2 多フレーム利用時に実測コストが問題化したら upper-frame 一括 HSV + sliding window へ最適化 (YAGNI、後付け)。

## 6. confidence

emblem-AND の **最弱リンク margin** から連続値を算出する:

```text
ratio_sat_i  = mean_sat_i  / _EMBLEM_SAT_THRESHOLD     # i ∈ {left, center, right}
ratio_edge_i = edge_i      / _EMBLEM_EDGE_THRESHOLD
m            = min over i of min(ratio_sat_i, ratio_edge_i)   # AND 通過時 m > 1.0
confidence   = clamp((m - 1.0) / (TARGET_RATIO - 1.0), 0.0, 1.0)
```

- AND 通過 = 全 ratio > 1.0。margin が大きいほど 1.0 に近づく。`m` は best-hit (§5.4) で選ばれた **最大 margin 候補**のものなので、confidence は「最良整合 frame 位置での余裕」を表す。
- `TARGET_RATIO` (満点に達する margin 倍率) は gyawa/OBS の clear な in-match frame で confidence が 1.0 近傍に出るよう calibrate (既定候補は実装時に決定)。
- 用途: P2 が「inset を信頼して採用するか FULL_FRAME に縮退するか」の gate に使う。P4 は localization の **有無** (None か否か) を主に使う。

## 7. OBS bit-exact / None 契約 / 小 inset 制約

### 7.1 OBS bit-exact (全 P hard gate の P1 分担)

- P1 は OBS 分類 path (`_probe_scorebar_context` → `_has_scorebar_v2`) と `_drop_post_match_trailing` から **consume されない** (P2 以降が non-full-frame & high-confidence gate 内でのみ P1 を呼ぶ)。
- よって P1 PR 時点で OBS の detect/split 出力は v0.3.0 baseline と **bit-exact** (構造的に自明)。§8.4 F4 の parity/baseline test で担保。

### 7.2 None 契約

`None` を返す条件 (S2 契約を継承):

- cv2 (opencv) 未インストール
- frame 形状が 1920x1080 でない
- 全 y・全 run で emblem-AND が不通過 (lobby / loading / transition / post-match interior / 純黒画面)

### 7.3 小 inset 制約 (既知・data-gated)

`_SCOREBAR_SCAN_MIN_WIDTH_PX`(500) は frame 相対の絶対 px。inset が小さく scorebar 幅 < 500px だと run が width gate で落ち `None` → P2 は **FULL_FRAME に safe 縮退** (誤検出ではなく検出機会の損失)。min-width の相対化 (inset 推定幅基準) は multi-source データ入手後の調整候補。gyawa は大 inset で本制約に非該当。

## 8. テスト戦略 / 受け入れ条件

### 8.1 合成 位置・スケール復元 (主たる robustness 検証、データ非依存)

既知の scorebar swatch (3 emblem 風の high-sat/high-edge パッチを `_EMBLEM_RELATIVE_POSITIONS` 比で配置) を、合成 1920x1080 frame の **様々な (x_offset, y_offset, scale)** に貼り付け、`localize_scorebar` が `(x_left, x_right, y_top)` を許容誤差内で復元し confidence が高いことを assert。**P1 の存在意義 = 位置独立性を直接検証**する。

### 8.2 Negative

- 無地 / 低彩度 frame → `None`
- 端寄り edge-only 帯 (#803 の右チャット panel / 左 widget 相当) → `None`
- post-match 風の広彩度帯 (emblem なし) → `None`

### 8.3 gyawa 実フレーム (slow, sample-gated, 1-source)

- in-match frame → 妥当な span/y で局在化
- lobby / transition frame → `None`

### 8.4 OBS parity (bit-exact hard gate)

- **F4-a**: 5 OBS baseline の detect 出力が不変 (nothing wired のため自明に pass する回帰 guard)
- **F4-b**: OBS in-match frame で `localize_scorebar` ≠ None かつ `_has_scorebar_v2` = True と整合 / OBS non-match frame で両者整合し `None`
- helper extract (§5.2/§5.3) を採る場合、この parity test が「extract が OBS 判定を変えていない」ことの担保になる

### 8.5 異常系

- cv2 不在 → `None`
- 形状不一致 → `None`

### 8.6 受け入れ条件 (issue 化時の `## 受け入れ条件` 原型)

1. `localize_scorebar` / `ScorebarLocalization` が §4 の API で実装され、§8.1 合成 position/scale test が pass する (位置独立性)
2. §8.2 negative・§8.5 異常系・§8.3 gyawa 実フレームが pass する
3. §8.4 OBS parity / baseline bit-exact が pass する (OBS hard gate)
4. S2 (`detect_region_scorebar_band`) が退役し、テストが localize 系へ移行している (D3)
5. `ruff check . && ruff format --check . && pyright && pytest` が全 pass (Iron Law 6)
6. **(マージ gate, D4)** 追加 VTuber source を 1 つ以上入手・`allaganeye-guard verify` 通過後、その実フレームで §8.3 相当の localization が pass する。**本項目が満たされるまで P1 はマージしない** → **✅ 2026-05-29 検証済 (§8.7、guard は FP override 経由)。**

> 1〜5 は実装完了で達成。6 は §8.7 の multi-source 実機検証で達成 (guard verify は FP のため owner override、§8.7 参照)。

### 8.7 multi-source 実機検証結果 (2026-05-29、D4 達成)

`E:\allaganeye-samples` の **5 本の実 VTuber FF14 FL VOD** (Twitch DL、8〜22GB) で `localize_scorebar` を時刻 grid (120s..3h/5min) probe 検証。

**guard verify**: 5 本すべて `allaganeye-guard verify` (v0.4.0) **FAIL**。原因はいずれも false positive と実証:

- `exploit_framework_marker` (2本): 6byte 署名 `FC E8 82 00 00 00` が moov sample-table / H.264 データ中に 1 回偶発衝突 (shellcode ではない)。rule (`ffmpeg_cve.yar`) は短い context-free 署名で大容量データに FP しやすい。
- `Non-media data exceeds scan buffer limit (10MB)` (5本): moov atom が 28〜64MB (>guard の 10MB scan buffer)。長尺 VOD は必ず該当。
- → owner (Idios) が FP と判断し override で processing 認可。**guard FP + cp932 CLI crash (絵文字ファイル名) は guard repo の別 issue で追跡**。

**localize 結果** (confidence >=0.5 の高信頼 hit クラスタ、probe px):

| source | x_left | x_right | y_top | span | conf med | n |
| --- | --- | --- | --- | --- | --- | --- |
| シルロリ | 633 (sd4.5) | 1287 (sd2.2) | 24 (sd3.1) | 654 | 1.00 | 18 |
| メテオ | 646 (sd8) | 1273 (sd7) | 42 (sd5) | 627 | 0.92 | 14 |
| Shinryu | 554 (sd10) | 1131 (sd44) | 63 (sd20) | 577 | 0.95 | 16 |
| 湿気 | 446 | 1477 | 90 (sd14) | 1033 | 1.00 | 21 |
| きゅま | 532 | 1149 | 3 | 617 (sd34) | 0.57 | 10 |

**結論**:

1. **位置独立を実データで実証** (R2 解消): 5 source が異なる y_top (3〜90) / span (577〜1033) / x-center を持ち、localize が各々の scorebar を捕捉。gyawa 単一過学習ではない。
2. **confidence が discriminator として機能**: 高信頼 hit はタイトにクラスタ (シルロリ sd≈3px)、低信頼は散乱。spec §6 の confidence-gate (P2 用) 設計を実証。
3. **きゅま は P2 課題**: span 一貫 (617±34) だが高信頼でも位置分散大 (conf 0.57)。VOD 内で FL inset 位置が変動 (scene 切替) しており localize は追従できている。**VOD 内レイアウト変動は P2 の per-segment region (`RegionTimeline.segments`) で扱う**。P1 の欠陥ではない。

## 9. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | all-runs 化で #803 級 FP 再発 | emblem-AND (zero-FP 検証済) を最終 gate に維持。#803 相当を §8.2 negative test 化 |
| R2 | gyawa 1-source 過学習 | 幾何ベース anchor + §8.1 合成 position/scale で位置独立を検証。multi-source を D4 でマージ gate に格上げし実データで確証 |
| R3 | y-scan コスト (P2 多フレーム時) | stride / short-circuit。必要時のみ upper-frame 一括 HSV + sliding window (YAGNI) |
| R4 | helper extract が OBS 判定を変える | extract は behavior-preserving、§8.4 F4 で担保。回避時は複製 (zero-touch) |
| R5 | 小 inset で scorebar < min-width → 未検出 | FULL_FRAME safe 縮退 (誤検出ではない)。min-width 相対化は data-gated follow-up (§7.3) |

## 10. P2 以降への引き継ぎと chain 影響

- **P2** は sample した複数 in-match frame に `localize_scorebar` を適用し、`x_left/x_right/y_top` の median/consensus → game 上端・幅を逆算 (現 S2 の `gw=bar_w/W`, `gh=(bar_w/_GAME_ASPECT)/H` 式)。S3 extent で下端・左右補完。幾何サニティ + confidence gate。OBS は FULL_FRAME。
- **P4 (#480)** は `localize_scorebar` の inset 内 span/位置で scorebar を読み、暗転を分類。
- **chain 影響 (D4 由来)**: P1 → P2 → {P3, P4} → P5 の依存上、P1 のマージを multi-source データまで保留すると後続も保留になる。回避したい場合の選択肢 (user review で確認):
  - (i) P1 を branch 上で実装・レビュー完了させ、**マージのみ**データ待ち保留 (P2 は P1 branch 上で先行着手可)
  - (ii) chain 全体をデータ入手まで保留
  - 既定の解釈は (i) (実装は進め land を保留)

## 11. 未確定 (Iron Law 2 で user 承認後に確定)

- **issue 起票**: P1 を #480 に内包 (案: #480 を localization+classification に再定義) するか新規起票するか。#809 の close 方針 (park した branch の扱い)。これらは issue 編集/起票を伴うため §3 D1-D4 確定後、起票時に AskUserQuestion で確認。
- **追加 source の具体 (D4)**: 入手時期・source 種別が判明したら §8.3/§8.6-6 を更新。

## 12. 参照

- replan overview: [2026-05-28-vtuber-region-boundary-replan-design.md](2026-05-28-vtuber-region-boundary-replan-design.md)
- Phase 2a: [2026-05-26-vtuber-capture-region-detection-design.md](2026-05-26-vtuber-capture-region-detection-design.md) (§6.3.1 S2 上端 15.7px / S3 IoU)
- #809 wiring (park): [2026-05-27-vtuber-pass1-region-wiring-design.md](2026-05-27-vtuber-pass1-region-wiring-design.md)
- 現行コード: `allaganeye/video/capture_region.py` (`detect_region_scorebar_band`=S2 → 退役対象), `allaganeye/video/detector.py` (`_has_scorebar_v2` / `_find_scorebar_horizontal_range` / `_emblem_and_check` / `_EMBLEM_RELATIVE_POSITIONS` / `_SCOREBAR_SCAN_*`), `allaganeye/video/scorebar.py` (`_probe_scorebar_context`)
- 既存 issue: #480 (scorebar ROI 適応、P1+P4 再定義案), #810 (metadata 領域), #753 (上位)
