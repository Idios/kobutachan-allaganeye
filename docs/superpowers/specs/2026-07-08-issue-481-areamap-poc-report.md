# エリアマップ window 検出 PoC 結果レポート (#481)

- 日付: 2026-07-08
- 対象 issue: [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) (parent: #753)
- 前提 design: [2026-07-08 minimap 切抜き design](2026-07-08-issue-481-minimap-crop-design.md)
  §6 (PoC / plan Phase 0)
- PoC script: `scripts/areamap_poc.py` / GT: `tests/baselines/v0.3.0/areamap-gt.json`
- 判定基準 (design §6.2): GT IoU ≥ 0.9 の検出成功率が高い案を勝者。両案とも実用水準に
  届かない場合は STOP し `--region` 手動 primary へ scope 縮小

> **本レポートの立場**: 本 PoC は「候補 A / B のどちらを製品実装するか」の判断材料である。
> 数字を良く見せる誘因は無い。以下は実測値と限界をそのまま記す。

## 1. dataset 構成

GT manifest = 7 case / 4 動画。IoU 判定は正規化 xywh、成功閾値 `IOU_SUCCESS = 0.9` (design §6.2)。

| case | 動画種別 | t (s) | GT bbox (norm xywh) | map | visible | 役割 |
| --- | --- | --- | --- | --- | --- | --- |
| obs-20260116-1@t300 | OBS full-frame | 300 | `0, 0, 0.284, 0.403` | onsal_hakair | true | 正例 |
| obs-20260116-1@t700 | OBS full-frame | 700 | `0, 0, 0.284, 0.403` | onsal_hakair | true | 正例 |
| obs-20260118-2@t600 | OBS full-frame | 600 | `0, 0, 0.191, 0.352` | seal_rock | true | 正例 |
| masked-a29-m001@t200 | masked (VTuber) | 200 | `0, 0.171, 0.151, 0.429` | (不明) | true | 正例 |
| masked-a29-m001@t400 | masked (VTuber) | 400 | `0, 0.171, 0.151, 0.429` | (不明) | true | 正例 |
| obs-20260209-mkv@t1106 | OBS (lobby/city) | 1106 | (なし) | — | false | 負例 |
| obs-20260209-mkv@t2354 | OBS (lobby/city) | 2354 | (なし) | — | false | 負例 |

- 正例 5 (OBS 3 + masked 2) / 負例 2 (lobby、window 閉/非 FL)
- masked 正例の GT は「右端 ±15px 不確実」(terrain/window 境界が soft) と manifest に明記
- GT は「エリアマップ window 全体 (装飾ヘッダー + 枠込み)」で定義。検出側を GT に合わせる方針
  (GT を検出に合わせて緩めることは禁止 — GT 不変)
- ref 照合は **leave-one-video-out (LOVO)**: 各 case の検出時、その case の動画由来の GT crop を
  ref から除外して build (`build_refs(exclude_video_id=...)`)。GT leakage を防ぐ

## 2. 候補案 (design §6.1)

- **A: 時間安定性 + map 照合** — 試合内 5 フレーム (t±8/±4/0、4s 間隔) の temporal median/std で
  「背景は動くが window は静的」な static component を抽出 → 既知マップの低解像度 ref と multi-scale
  `TM_CCOEFF_NORMED` 照合で bbox 確定 + map 種別判定。ref 中心が static component 内なら component
  bbox を採用、不成立時は最大 edge density の static component に fallback
- **B: window 枠 edge 検出** — temporal median 上で Canny + `HoughLinesP` → 水平/垂直線から矩形候補を
  組み、周縁 edge support で filter

## 3. 調整履歴と数値推移

各ラウンド = 仮説 → 変更 → full compare (`python scripts/areamap_poc.py compare`、全 7 case)。
positive は IoU ≥ 0.9 の数、negative reject は None (未検出) を返せた数。

| round | 変更概要 | A (pos / neg-rej) | B (pos / neg-rej) |
| --- | --- | --- | --- |
| 0 (baseline) | P1-P4 実装のまま | 1/5 / 0/2 | 0/5 / 2/2 |
| 1 | A: whole-frame blob guard 追加 | 1/5 / 1/2 | (変更なし) 0/5 / 2/2 |
| 2 | A: static mask 拡大 (std/morph/dilate 掃引) / B: 枠 support 緩和 掃引 | 全 variant 悪化 → 棄却 | 全 variant 悪化 → 棄却 |
| 3 | A: 外枠 edge-snap / `require_ref` gate 検証 | net-negative → 不採用 | (対象外) |
| **最終** | Round 1 の whole-frame guard のみ採用 | **1/5 / 1/2** | **0/5 / 2/2** |

### Round 1 — whole-frame blob guard (採用)

- **仮説**: calm scene (試合が一瞬静止) では frame 全体が static となり mask が frame サイズの単一
  blob に collapse する。この blob が返ると full-frame の false box になる (obs-20260116-1@t700 /
  obs-20260209-mkv@t2354 で実発生)
- **変更**: `_static_components` に「w ≥ 0.95×W かつ h ≥ 0.95×H の component は drop」ガードを追加
  (`A_MAX_DIM_FRAC = 0.95`)。window は決して frame サイズにならないため
- **結果**: A の negative reject が 0/2 → **1/2** に改善 (t2354 が FP → reject)。t700 は
  full-frame false box → 正直な MISS に変化 (幾何は改善するが正例なので pos 数は不変)。positive は不変
- 本ガードは A の唯一の net-positive な構造変更。lint/pyright clean で採用

### Round 2 — static mask 拡大 / B support 緩和 (棄却)

- **仮説 (A)**: static core が GT より過小 (下記 §5) なので mask を広げれば GT に届く
- **A 掃引**: `std ∈ {16, 20}` (baseline 12) / morph close/open kernel / dilate ∈ {7, 9} を組合せ
- **結果 (A)**: **全て baseline より悪化**。std を上げると window の static mask が隣接する静的
  UI/地形と merge し bbox が GT を超えて over-cover する。obs-20260116-1@t300 の IoU は
  0.657 (baseline) → 0.103 (std16) / 0.255 (std20) に低下。「mask を広げる」方向は誤り
- **仮説 (B)**: 垂直 support 要求が厳しく正例を落としているので緩めれば recall が上がる
- **B 掃引**: `min_vsup ∈ {0, 1}` (両側 → 片側/不要) / `support ∈ {0.25, 0.30}`
- **結果 (B)**: 緩和すると「検出」は増えるが IoU=0.000 の誤矩形が大量発生し、negative reject が
  2/2 → **0/2** に崩壊。B の厳しい support 要求こそが perfect negative reject の源泉であり、
  緩めると precision が全崩壊する。緩和は棄却、strict のまま維持

### Round 3 — edge-snap / require_ref gate (不採用)

- **edge-snap (A)**: static core bbox の外側を raw frame の Canny edge で探索し外枠へ snap。
  obs-20260116-1@t300 は 0.657 → 0.838 に改善するが、唯一 OK だった obs-20260118-2@t600 が
  0.909 → 0.511 に破壊される (戦場の強 edge が誤 snap target になる)。IoU 強度 floor を入れても
  t600 は 0.836 に劣化し、net で成功数は増えない。**net-negative のため不採用**
- **`require_ref` gate (A)**: 「ref 照合成立を採用の必須条件にすれば lobby を弾ける」を検証。
  だが ref score は **正例と負例を分離しない** (§4 参照): lobby 負例の ref score
  (t1106=0.76 / t2354=0.81) が複数の正例 (obs-20260116-1=0.66-0.68 / obs-20260118-2=0.72) より
  **高い**。`ref_min` をどこに引いても lobby は通り正例が先に死ぬ。gate として機能しない → 不採用

## 4. 最終成績

`python scripts/areamap_poc.py compare` の実動画出力 (最終チューニング版、Round 1 適用)。

### per-case

| case | visible | A | B |
| --- | --- | --- | --- |
| obs-20260116-1@t300 | true | LOW (IoU=0.657, map=seal_rock, s=0.68) | LOW (IoU=0.553, s=0.72) |
| obs-20260116-1@t700 | true | MISS | MISS |
| obs-20260118-2@t600 | true | **OK (IoU=0.909, map=onsal_hakair, s=0.72)** | MISS |
| masked-a29-m001@t200 | true | LOW (IoU=0.480, map=onsal_hakair, s=0.79) | MISS |
| masked-a29-m001@t400 | true | LOW (IoU=0.479, map=onsal_hakair, s=0.85) | LOW (IoU=0.447, s=0.51) |
| obs-20260209-mkv@t1106 | false | FP (s=0.76) | OK (reject) |
| obs-20260209-mkv@t2354 | false | OK (reject) | OK (reject) |

### summary

| 案 | positive (IoU≥0.9) | negative reject | 定量所見 |
| --- | --- | --- | --- |
| **A** | **1/5 (20%)** | **1/2** | 唯一の OK は t600 のみ。他正例は IoU 0.48-0.66 帯で under-cover。lobby 1 件を FP |
| **B** | **0/5 (0%)** | **2/2** | 正例で内枠に lock (IoU≤0.55) or MISS。negative は完璧だが positive がゼロ |

> map 種別ラベル (`map=seal_rock` 等) は誤りを含む (obs-20260116-1 は実際 onsal_hakair だが
> seal_rock と照合)。§4 の通り ref 照合は識別器として機能していないため、bbox 出力は主に
> temporal-stability 部分が担い、map ラベルは信頼できない。

## 5. 両候補の定性所見 (強み・弱み・限界)

### 候補 A (時間安定性 + map 照合)

- **強み**: 半透過・リサイズに一定頑健。static component が window を「大まかに」捉える
  (5/5 正例で window 付近に box を出す)。masked (VTuber) 動画でも局在はする
- **弱み 1 — bbox 過小 (構造的)**: GT の右 1/4・下 1/8 は map interior (移動する自軍/敵 blip) で
  temporal std が閾値を超え「静的」判定されない。obs-20260116-1@t300 で GT box 内の static 率は
  std<12 で 56.8% しかなく (std<50 でようやく 91.7%)、static core は GT の約 0.66 IoU が上限。
  これが LOW 多発の主因
- **弱み 2 — calm scene で degenerate**: 試合が一瞬静止すると mask が frame 全体に collapse
  (t700 / t2354)。Round 1 guard で false box は防げるが、その case では window を検出できない
  (MISS)
- **弱み 3 — map 照合が識別器にならない**: 256px 幅の grayscale ref を `TM_CCOEFF_NORMED` で
  multi-scale 照合しても、汎用的な地形テクスチャに対し spurious な 0.7-0.8 peak が frame 内の
  どこにでも立つ。正例より lobby 負例の score が高くなり、閾値による gate も map 種別判定も
  信頼できない。実質「temporal-stability だけで動いており map 照合は寄与していない」
- **弱み 4 — lobby 非識別**: lobby/city の minimap は試合中エリアマップと同一 UI 部品で、外観
  (parchment 背景・矩形枠・地形・blip) がほぼ区別不能。appearance だけでは lobby を弾けない
  (t1106 FP)。ただし製品では試合中フレームのみ sample するため実害は限定的 (§6 参照)

### 候補 B (window 枠 edge 検出)

- **強み**: asset 不要。厳格な周縁 support 要求により **negative reject が完璧 (2/2)**。誤検出は
  出さない
- **弱み 1 — 内枠 lock で under-cover**: HoughLinesP が拾う最強 edge は外枠 (装飾ヘッダー込み) では
  なく内側の map/parchment 境界。obs-20260116-1@t300 で B の box は (8,5,353,372) と GT
  (0,0,545,435) の内側に収まり IoU 0.553 で頭打ち
- **弱み 2 — 垂直 edge が弱く MISS 多発**: エリアマップ枠は低コントラストで縦線が 4-10 本しか
  出ず、両側縦線 support が成立せず 5 正例中 3 が MISS
- **弱み 3 — precision/recall の壁**: support を緩めると recall は上がるが IoU=0.000 の誤矩形と
  lobby FP が噴出し negative reject が崩壊 (§Round 2)。strict/loose のどちらでも IoU≥0.9 に届く
  正例はゼロ

### 共通の限界

- GT が「window 全体 (非静的な map interior + 低コントラスト外枠を含む)」であるため、
  temporal-std (A) も強 edge (B) も GT 境界を安定に復元できない。IoU=0.9 という厳しい bar に対し、
  A は core が過小、B は内枠 lock で、**両案とも構造的に届かない**

## 6. 勝者判定素案と根拠

**素案: 両案不合格 → `--region` 手動 primary への scope 縮小 (design §6.2 STOP 条件に該当)。**

- design §6.2 の勝者条件は「GT IoU ≥ 0.9 の検出成功率が高い案」。A=1/5 (20%)・B=0/5 (0%) で、
  A が名目上上回るが 20% は自動 crop の実用水準に達しない (5 試合に 4 試合が bbox 過小 or 誤検出)
- §6.2 の STOP 条件「両案とも成功率が実用水準に届かない場合は `--region` 手動 primary へ scope
  縮小し AskUserQuestion で再判断」に該当する
- したがって v0.3.0 は **`--region` 手動指定を primary path** とし、自動検出は付随的位置づけに
  縮小するのが妥当。design §7 の「全試合で検出失敗 → exit 4 + `--region` 案内」フローと整合する
- **A を「best-effort な自動 seed」として残す選択肢** (任意): A は 5/5 正例で window 近傍に局在し、
  whole-frame guard 後は lobby も 1/2 は reject する。IoU≥0.9 は満たせないが、`--region` の初期値
  proposal (ユーザーが微調整する出発点) としてなら価値がありうる。ただし map ラベルは出さず、
  「概略領域の提案」に用途を限定する前提。採否は Idios の checkpoint 判断に委ねる
- **B の実装は非推奨**: positive 0/5 で自動検出の価値が無く、negative の強さは `--region` primary
  では活きない

> 最終判断 (A を seed に残すか / 完全に手動のみか) は task brief の Step 3 checkpoint
> (AskUserQuestion、Idios) に委ねる。本レポートは素案と根拠の提示に留める。

## 7. 残リスク

- **サンプル数が小さい** (正例 5 / 負例 2)。特に masked は 1 動画 2 case のみで、masked での傾向は
  暫定。判断を覆すには more sample が要るが、傾向 (bbox 過小・内枠 lock) は OBS/masked で共通
- **map ref asset の有効性が未確立**: LOVO で ref を build しても照合が識別器にならなかった。
  design §6.1 の「派生特徴量 (npz) 同梱」方針は、照合手法を根本的に変えない限り再考が必要
- **`--region` primary の UX 未検証**: 手動 primary に倒す場合、ユーザーが source 解像度 pixel を
  screenshot で測る運用 (design §7) の実用性は別途要確認
- **IoU=0.9 の妥当性**: crop 用途では IoU 0.9 は厳しい。もし「多少の余白込み crop で可」なら閾値
  緩和で A が実用化しうる余地はあるが、これは GT/閾値変更を伴うため本 PoC の scope 外
  (IOU_SUCCESS は不変で回した)。閾値再設計は checkpoint での論点候補

## 付録: overlay 目視検証

最終版で 5 正例の overlay PNG (GT=緑 / 検出=赤) を出力し目視した (数字と絵の整合確認)。

- **obs-20260118-2@t600 (A, IoU=0.909)**: 赤と緑がほぼ一致。static core が偶然 GT に密着した唯一の
  OK。画と数字が整合
- **obs-20260116-1@t300 (A, IoU=0.657)**: 赤の右辺・下辺が緑の内側に収まり明確に under-cover。
  絵が 0.657 と整合
- **obs-20260116-1@t700 (A, MISS)**: 緑のみ描画 (赤なし) = whole-frame guard 発火で None 返却。
  MISS ラベルと整合
- **masked-a29-m001@t200/t400 (A, IoU≈0.48)**: 赤が緑より上・右に offset し地形へ overshoot。
  0.48 と整合
- **obs-20260116-1@t300 (B, IoU=0.553)**: 赤が内側 map 境界に lock し外枠を取りこぼす。B の「内枠
  lock」特性と整合

(overlay PNG は `.tmp-areamap-poc/final/` に生成。非 commit。)
