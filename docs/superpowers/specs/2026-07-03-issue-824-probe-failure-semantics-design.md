# #824 probe 失敗縮退 semantics 統一契約 設計 spec

> 状態: design (AskUserQuestion で Idios 確定 2026-07-03)。実装は Phase 3 cutover (detection-map §5.4) と同時期に実動画検証可能な環境で行う (本 spec 作成環境はノート PC のため OBS bit-exact gate / 実機検証を実行できない)。
> 関連: #824 (本 spec の元 issue) / #821 (masked-OBS parent) / #822 (localize 過分割) / #753 (L3 parent) / PR #823 R3-R5 (whack-a-mole 早期停止 → 本設計タスク切り出し) / #234 (probe pool 例外契約の過去事例) / #805 (「弱い信号での縮退/削除」の隣接クラス、非破壊化で解決済)

## 1. 背景と問題

L3 検出系 (presence / capture_region / scorebar localize) の probe 失敗 (decode 失敗 raw None / 例外 / consensus miss) の表現が site ごとに ad-hoc で、「bool false 化 / bool|None / 例外 / log」が混在している。PR #823 の /iterate-review で同一クラスの finding (probe 失敗が absent に silent に折り畳まれる) を R3 → R5 の 3 周で個別修正したが収束せず、根本要因は「明示 intent (--vtuber / harness) 下の弱い縮退が site ごとに ad-hoc な silent/loud 契約を持つ」ことにある。

新 site 追加のたびに silent 縮退が混入しうる構造であり、warning による場当たり補強 (R3-R5) では再発を防げない。

## 2. 期待される最終状態

probe 失敗の表現と縮退時の可視化が、L3 検出系の全 site で単一の契約に従う:

1. **probe 失敗は UNKNOWN として表現**し、absent (False) への暗黙変換を型レベルで禁止する
2. **UNKNOWN → ABSENT の変換は集約層のみが明示的に行い**、変換時の可視化 (warning 集計) を必須とする
3. **全滅 (全 probe UNKNOWN) は fail-loud** (VideoProcessingError)
4. 新 site は tri-state 結果型を使う限り silent 縮退を書けない (契約が構造的に防ぐ)

## 3. スコープ (Idios 確定 2026-07-03)

| 論点 | 決定 | 理由 |
| --- | --- | --- |
| 統一表現 | **tri-state enum** (present / absent / unknown) | issue 本文の例示と同方向。失敗理由 payload が必要な site は限定的で、Result wrapper の型侵入度に見合わない |
| 適用範囲 | **L3 検出系のみ** (presence.py / capture_region.py / scorebar.py の localize 系)。production OBS path (detector.py `_probe_single_frame` の 255.0 bias / gpu_detector.py chunk decode / `_has_scorebar` V1) は**現状維持** | OBS baseline bit-exact リスクをゼロにする。OBS path の縮退 (255.0 = 非黒 bias) は「暗転誤検知防止」という別の設計意図を持ち、本契約の対象外 |
| Phase 3 cutover との関係 | **統合前提で spec 化** (localize_present_at の Stage 2 統合と同時に実装) | issue 記載どおり変更回数最小。cutover 自体が presence API を production に近づけるため、契約導入はその前提整備として同時に行うのが自然 |

### スコープ外 (明示)

- `detector.py` `_probe_single_frame` の brightness 255.0 fallback (偽陰性防止 bias、意図された設計)
- `gpu_detector.py` chunk decode の silent None (Pass 1 probe pool、OBS production path)
- `_has_scorebar` (V1) / `_has_scorebar_v2` の None 契約変更 — ただし §6.4 の「cv2 未インストールと probe 失敗の区別」は cutover 時に tri-state 化の恩恵を受ける候補として記録
- audio 系 (AUDIO_FROZEN #327 のため対象外)

## 4. 現状棚卸し (2026-07-03 実施)

probe 失敗を扱う site は 13。うち本契約の対象 (L3 検出系) は site 1-6, 9, 10。

| # | site | 現行表現 | 縮退方針 | caller 選択 |
| --- | --- | --- | --- | --- |
| 1 | `localize_present_at` (presence.py:124) | raw None → 例外 or absent (`raise_on_probe_failure` seam) | fail-loud (全滅) / silent (部分) | **可** (bool seam) |
| 2 | `scan_presence` (presence.py:162) | per-probe 例外隔離 | silent absent + warning (R5) | 不可 |
| 3 | `detect_matches_by_presence` refine (presence.py:235) | 例外 catch | silent absent + warning (R5) | 不可 |
| 4 | `_localize_present_from_raw` (scorebar.py:38) | raw None → None | silent None | 不可 |
| 5 | `_probe_scorebar_context` (scorebar.py:55) | 部分失敗 debug log | silent None/False 化 (R4) | 不可 |
| 6 | `localize_from_rgb_bytes` (capture_region.py:286) | raw None → None | silent None | 不可 |
| 9 | `_resolve_detect_region` (detector.py:264) | anchor 例外 catch | silent FULL_FRAME + warning (R4/R5) | 不可 |
| 10 | `detect_scorebar_band_region` consensus (capture_region.py:489) | localize None → min_hits miss | silent FULL_FRAME (consensus miss) + warning | 不可 |

(対象外: 7/8 `_has_scorebar_v2`/`_has_scorebar` raw None→None V1 fallback、11 `_probe_single_frame` 255.0 bias、12 GPU chunk silent None、13 `_decode_gray_raw` silent None)

**「unknown を absent に潰している」箇所** (契約導入で解消する対象): site 1 (default 時 loc None → present=False)、site 2 (例外 → PresenceSample(present=False))、site 4 (loc None → False)、site 5 (None → False 化)。site 10 の consensus miss-mode は「有効票不足 → FULL_FRAME」で、票数集計に unknown を含めない現行挙動を維持する (§6.3)。

## 5. 統一契約の設計

### 5.1 結果型

```python
class PresenceState(Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"   # probe 失敗 (decode None / 例外)。absent と区別する

@dataclass(frozen=True)
class PresenceSample:
    time: float
    state: PresenceState          # 旧: present: bool
    confidence: float             # UNKNOWN のとき 0.0

    @property
    def present(self) -> bool:    # 移行用 (PRESENT のみ True)。cutover 完了後に deprecate
        return self.state is PresenceState.PRESENT
```

- `ScorebarLocalization | None` を返す低層 localizer (site 4/6) は None のままでよい (None = 「この 1 frame では局在化できず」)。**None を bool False に変換する箇所を `PresenceState.UNKNOWN` / `ABSENT` の明示分岐に置換**する: decode 失敗 (raw None) → UNKNOWN、decode 成功 + localizer miss → ABSENT。
- 「decode は成功したが localizer が miss」は**観測に基づく ABSENT** (真の不在判定) であり UNKNOWN ではない。R3-R5 の混乱の一因はこの 2 つの同一視。

### 5.2 縮退方針の明示 API (seam の一般化)

`raise_on_probe_failure: bool` seam を廃し、集約層 (scan / refine / consensus) が受ける方針 enum に一般化する:

```python
class ProbeFailurePolicy(Enum):
    RAISE = "raise"            # UNKNOWN を即例外化 (診断 harness 用)
    ISOLATE = "isolate"        # per-probe 隔離: UNKNOWN のまま集約に流す (default)
```

- 単発 probe 関数 (site 1) は常に tri-state を返す (例外を握らない。decode 例外は UNKNOWN に写像し、写像した事実を debug log)。
- 集約層 (site 2/3/10) が UNKNOWN の扱いを決める:
  - 集計から除外 (present 率計算の分母に入れない)
  - UNKNOWN 率を集計し、しきい値超過 (>50%) で warning、全滅 (100%) で `VideoProcessingError` (fail-loud)
  - warning message に UNKNOWN 数 / 総 probe 数を必須で含める (R5 の部分故障集計 warning を契約に昇格)

### 5.3 log 階層 (契約)

| 事象 | レベル | 必須内容 |
| --- | --- | --- |
| 全滅 (全 probe UNKNOWN) | exception (fail-loud) | probe 数、代表原因 |
| 部分故障 (UNKNOWN > 0) | warning (集約層で 1 回) | UNKNOWN 数 / 総数、time range |
| 単発 probe 失敗 | debug | timestamp、原因 (decode None / 例外種) |
| consensus miss (非例外、有効票不足) | warning | 有効票数 / min_hits、FULL_FRAME 縮退の明示 |

### 5.4 site 別移行 map

| site | 移行内容 |
| --- | --- |
| 1 `localize_present_at` | 戻り値を tri-state 化。`raise_on_probe_failure` param 削除 (呼び出し 2 箇所は §5.2 の集約層方針に移行) |
| 2 `scan_presence` | per-probe try/except を「UNKNOWN 写像」に置換。全滅 fail-loud / 部分 warning は §5.2-5.3 の契約実装として維持 |
| 3 refine (`detect_matches_by_presence`) | 同上。UNKNOWN は「境界を動かさない」(absent 扱いで refine を進めない) |
| 4 `_localize_present_from_raw` | raw None (UNKNOWN 相当) と localizer miss (ABSENT) の戻り値を分離 (bool → PresenceState) |
| 5 `_probe_scorebar_context` | 内部の None/False 化を tri-state 化。V1/V2 fallback 判定 (対象外 site 7/8) との境界は現状維持 |
| 6 `localize_from_rgb_bytes` | 呼び出し側 (site 10) が decode 失敗と localize miss を区別できるよう、raw None 時は呼び出し前に UNKNOWN 判定 (関数自体は None 返却のまま) |
| 9 `_resolve_detect_region` | anchor 例外の catch → FULL_FRAME 縮退は維持 (--vtuber gate 内の設計済み縮退)。warning 文言を §5.3 契約形式に揃える |
| 10 `detect_scorebar_band_region` | consensus 集計を「有効票 (PRESENT/ABSENT) のみ」で行い、UNKNOWN 率を §5.2 のしきい値監視に乗せる |

## 6. テスト戦略

1. **R3-R5 warning pin テスト 7 件の移行 map** (置換であり削除ではない):
   - `test_probe_scorebar_context_logs_probe_failure` → tri-state 化後も debug log 契約 (§5.3) を pin
   - `test_scan_presence_partial_failures_logged` / `test_refine_probe_failure_warns_and_treats_absent` → 「UNKNOWN 集計 warning + 分母除外」の契約テストに書換
   - `test_resolve_detect_region_swallows_exceptions_to_full_frame` / `test_resolve_detect_region_warns_on_consensus_miss_full_frame` → 文言契約 (§5.3 表) に揃えて維持
   - `test_localize_from_rgb_bytes_none_passthrough_and_decode` → None passthrough 維持 (§5.4 site 6)
   - `test_borderline_pseudo_regions_capped_with_warning` → 対象外 (OBS path、無変更)
2. **新規契約テスト**: 「UNKNOWN が ABSENT に暗黙変換されない」型/分岐テスト、全滅 fail-loud、部分故障 warning 集計、UNKNOWN 率しきい値
3. **OBS bit-exact gate**: presence 系は OBS production 経路に非配線 (detection-map §5.4)、anchor は `--vtuber` gate 内のため、OBS baseline 5 本の detect 出力は bit-exact のはず。実装 PR で必ず実測する (実動画環境)
4. **実機検証**: masked/VTuber サンプル (`ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER`) での detect 回帰 + #822 の過分割サンプルでの挙動確認 (契約導入自体は分類結果を変えない想定の確認)

## 7. 実装タイミング (Idios 確定: cutover 統合前提)

- detection-map §5.4 Phase 3 cutover (`localize_present_at` の Stage 2 統合) と**同一実装期**に行う。cutover 実装 plan (writing-plans) に本契約の §5.4 移行 map を task として編入する
- 実装環境要件: OBS baseline 5 本 + VTuber/masked サンプルへのアクセス (デスクトップ環境)。本 spec 作成環境 (ノート PC) では実装しない
- 実装 PR の Pre-flight は Iron Law 6 準拠 (detector.py 隣接変更のため実機検証 AskUserQuestion 必須)

## 8. 却下した代替案

| 案 | 却下理由 |
| --- | --- |
| Result wrapper (`ProbeResult[T] = T \| ProbeFailure(reason)`) | 失敗理由 payload が必要な site が現状ない (log で足りる)。型の侵入度が大きく、cutover と独立に全 signature を変えることになる |
| 例外ベース統一 (probe 失敗は常に raise) | bool 返却の既存 site 全てに try/except を強制し、per-probe 隔離 (site 2) が例外 flow 依存になる。#234 の教訓 (probe pool の例外は漏れやすい) に逆行 |
| 全 13 site 一括適用 | OBS production path (255.0 bias / GPU chunk) の bit-exact リスクと実機検証コストが、得られる一貫性に見合わない。OBS path は別 issue で必要になってから |
