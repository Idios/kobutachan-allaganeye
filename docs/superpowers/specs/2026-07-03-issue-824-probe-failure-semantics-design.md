# #824 probe 失敗縮退 semantics 統一契約 設計 spec

> 状態: design (AskUserQuestion で Idios 確定 2026-07-03、adversarial review R1 反映済み)。実装は 2 信号 fusion 再アーキ ([`2026-05-31-l3-detection-rearchitecture-two-signal-design.md`](2026-05-31-l3-detection-rearchitecture-two-signal-design.md)) の Phase 2 (Stage 2 分類統合) と同一実装期に、実動画検証可能な環境で行う (本 spec 作成環境はノート PC のため OBS bit-exact gate / 実機検証を実行できない)。
> 関連: #824 (本 spec の元 issue) / #821 (masked-OBS parent) / #822 (localize 過分割) / #753 (L3 parent) / PR #823 R3-R5 (whack-a-mole 早期停止 → 本設計タスク切り出し) / #234 (probe pool 例外契約の過去事例) / #805 (「弱い信号での縮退/削除」の隣接クラス、非破壊化で解決済)

## 1. 背景と問題

L3 検出系 (presence / capture_region / scorebar localize / masked region) の probe 失敗 (decode 失敗 raw None / 例外 / consensus miss) の表現が site ごとに ad-hoc で、「bool false 化 / bool|None / 例外 / log」が混在している。PR #823 の /iterate-review で同一クラスの finding (probe 失敗が absent に silent に折り畳まれる) を R3 → R5 の 3 周で個別修正したが収束せず、根本要因は「明示 intent (--vtuber / --masked / harness) 下の弱い縮退が site ごとに ad-hoc な silent/loud 契約を持つ」ことにある。

新 site 追加のたびに silent 縮退が混入しうる構造であり、warning による場当たり補強 (R3-R5) では再発を防げない。実際、R3-R5 後に追加された `_resolve_masked_region` (#821) は log すら持たない完全 silent 縮退を再導入している (§4 site 14)。

## 2. 期待される最終状態

probe 失敗の表現と縮退時の可視化が、L3 検出系の全 site で単一の契約に従う:

1. **probe 失敗は UNKNOWN として表現**し、absent (False) への暗黙変換を型レベルで禁止する
2. **UNKNOWN → ABSENT の変換は集約層のみが明示的に行い**、変換時の可視化 (warning 集計) を必須とする
3. **全滅 (全 probe UNKNOWN) は fail-loud** (VideoProcessingError)。適用 site は presence scan 集約層のみ (§5.2 の適用範囲明示を参照 — region 解決層は FULL_FRAME 縮退を維持する)
4. 新 site は tri-state 結果型を使う限り silent 縮退を書けない (契約が構造的に防ぐ)

## 3. スコープ (Idios 確定 2026-07-03)

| 論点 | 決定 | 理由 |
| --- | --- | --- |
| 統一表現 | **tri-state enum** (present / absent / unknown) | issue 本文の例示と同方向。失敗理由 payload が必要な site は限定的で、Result wrapper の型侵入度に見合わない |
| 適用範囲 | **L3 検出系のみ** (presence.py / capture_region.py / scorebar.py の localize 系 / detector.py の `--vtuber` gate 内 anchor 解決・masked fallback gate 内 region 解決。masked fallback の発動条件は `not vtuber and (masked or not blackout_times)` (detector.py:548) で、**`--masked` 指定なしでも標準 Pass 1 が blackout ゼロの run では自動発動する**)。production OBS path は**現状維持** | OBS baseline bit-exact リスクをゼロにする。OBS path の縮退 (255.0 = 非黒 bias 等) は「暗転誤検知防止」という別の設計意図を持ち、本契約の対象外 |
| 実装タイミング | **再アーキ spec Phase 2 (Stage 2 分類統合) と同一実装期** | issue 記載どおり変更回数最小。§7 参照 |

> **phase 呼称の正規化 (review R1 P2-1)**: issue #824 本文の「Phase 3 cutover (detection-map §5.4)」という呼称は supersede 済みの旧 presence spec 由来。現行の authoritative な phase 番号 (再アーキ spec §8: Phase 0-3 = 検証・非破壊 / Phase 4 = 切替) では **Phase 2 = Stage 2 分類の localize 統合 (shadow、v2 authoritative のまま) / Phase 4 = cutover (authoritative 切替)** であり、detection-map §5.4 の「`localize_present_at` → Stage 2 分類で再利用」は Phase 2 に当たる。本契約の実装は **Phase 2 と同一実装期**とし、Phase 4 cutover の gate (OBS parity 実証) とは独立。

### スコープ外 (明示)

- `detector.py` `_probe_single_frame` (detector.py:1226) の brightness 255.0 fallback (偽陰性防止 bias、意図された設計)
- `gpu_detector.py` chunk decode の silent None + debug log (Pass 1 probe pool、OBS production path)
- `_has_scorebar` (V1、detector.py:1774) / `_has_scorebar_v2` (detector.py:1690) の raw None → None 契約 — OBS production 分類の入口。V2 の「probe 失敗と opencv 未インストールが同じ None になる」区別不能は既知だが、変更は bit-exact リスクに見合わないため本契約では触らない
- `_flag_post_match_trailing` の probe None → keep (保守側) 挙動 — detection-map §4 に明記された設計済みの非破壊縮退 (#805)
- audio 系 (AUDIO_FROZEN #327 のため対象外)

## 4. 現状棚卸し (2026-07-03 実施、review R1 で実コード突合済み)

### 4.1 契約適用対象 (L3 検出系)

| # | site | 現行表現 | 縮退方針 | caller 選択 |
| --- | --- | --- | --- | --- |
| 1 | `localize_present_at` (presence.py:126) | raw None → 例外 or `present=False` (`raise_on_probe_failure` seam、keyword-only bool) | fail-loud (True 時) / silent absent (default) | **可** (bool seam のみ) |
| 2 | `scan_presence` (presence.py:164) | per-probe 例外を catch し `PresenceSample(present=False)` (内部呼出 presence.py:182 は `raise_on_probe_failure=True`) | silent absent + 部分故障集計 warning (R5) | 不可 |
| 3 | `detect_matches_by_presence` refine (presence.py:237-251) | refine 中の例外 catch → absent 続行 | silent absent + warning (R5) | 不可 |
| 4 | `_localize_present_from_raw` (scorebar.py:38) | **分離済み**: raw None (decode 失敗) → None / decode 成功 + localizer miss → False (docstring 明記) | §5.1 セマンティクスを既に持つ (表現形式が bool\|None なだけ) | 不可 |
| 5 | `_probe_scorebar_context` (scorebar.py:55) | probe 失敗 None は `_majority_scorebar` (scorebar.py:178) が**分母から除外**、全 None → None → classify 側で `"unknown"` (scorebar.py:396) | §5.2 に近い集約挙動を既に持つ。**OBS production 分類経路を含む** (`with_localize=False` が default CLI path) | 不可 |
| 6 | `localize_from_rgb_bytes` (capture_region.py:286) | raw None → None | silent None (decode 失敗と localize miss が呼び出し側で区別不能) | 不可 |
| 9 | `_resolve_detect_region` (detector.py:264) | anchor probe 例外 catch → FULL_FRAME。consensus miss warning もこの層 (detector.py:298-304) が発する | silent FULL_FRAME + warning (R4/R5) | 不可 |
| 10 | `detect_scorebar_band_region` consensus (capture_region.py:489) | `localize_fn` (`Callable[[float], ScorebarLocalization \| None]`、capture_region.py:494) の None → min_hits miss | silent FULL_FRAME (consensus miss-mode)。**この層自体は無音** — warning は caller (site 9) 帰属 | 不可 |
| 14 | `_resolve_masked_region` (detector.py:328-372、masked fallback gate 内 — `--masked` 指定時 or 標準 Pass 1 blackout ゼロ時に発動、detector.py:548) | per-frame decode None を **silent drop** (365-367) / `except Exception` → FULL_FRAME (371-372) | **完全 silent (log なし)**。R3-R5 後に追加され、本 spec が対象とするクラスをそのまま再導入した実例 | 不可 |

**「unknown を absent (または無音の縮退) に潰している」箇所** (契約導入で解消する対象): site 1 (default 時 raw None → present=False)、site 2 (例外 → PresenceSample(present=False)、warning はあるが sample 値としては absent と区別不能)、site 14 (decode None silent drop + 例外 silent FULL_FRAME)。site 4/5 は review R1 の突合で「既に §5 のセマンティクスに近い」ことが判明したため潰しリストから除外した (移行は表現形式の統一のみ、§5.4)。site 10 の consensus miss-mode (有効票不足 → FULL_FRAME) は現行挙動を維持する (§5.4 site 10)。

### 4.2 対象外 site (参考)

| # | site | 現行表現 | 対象外の理由 |
| --- | --- | --- | --- |
| 7 | `_has_scorebar_v2` (detector.py:1690) | raw None / cv2 欠如 → None → V1 fallback | OBS production 分類の入口 (§3 スコープ外) |
| 8 | `_has_scorebar` V1 (detector.py:1774) | raw None → None | 同上 |
| 11 | `_probe_single_frame` (detector.py:1226) | raw None → 255.0 (非黒 bias) | 偽陰性防止の意図された設計 |
| 12 | GPU chunk decode (gpu_detector.py) | subprocess fail / timeout → silent None + per-chunk debug log | OBS production Pass 1 |
| 13 | `_decode_gray_raw` (detector.py:1185) | timeout / returncode≠0 → None | probe 失敗の共通低層 (上位 site が解釈) |
| 15 | `_flag_post_match_trailing` の probe None → keep | 保守側縮退 (detection-map §4 明記) | #805 で設計済みの非破壊挙動 |

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
```

- **移行用 `.present` property は提供しない** (review R2 Codex HIGH)。「PRESENT のみ True」の bool property は UNKNOWN → False の silent 変換 escape hatch となり、§2 item 1 (暗黙変換の型レベル禁止) / item 4 (新 site は構造的に silent 縮退を書けない) と自己矛盾する。既存の `.present` 消費者は 2 箇所のみ (`segment_presence` presence.py:73 / refine presence.py:243-251) で、どちらも §5.4 で explicit な state 比較への移行を規定する。UNKNOWN → ABSENT 側への折り畳みは集約層が **明示的な state 比較で行い、grep 可能にする**。
- 「decode は成功したが localizer が miss」は**観測に基づく ABSENT** (真の不在判定) であり UNKNOWN ではない。site 4 は既にこの分離を実装しており (scorebar.py:38 docstring)、契約はこれを全 site の規範に昇格させるもの。
- 低層 localizer (site 6) の `ScorebarLocalization | None` は「decode 済み frame に対する局在化結果」としては None のままでよいが、**decode 失敗情報を境界の外に運ぶ経路**を §5.4 site 6/10 で規定する。
- **module 配置 (circular import 回避)**: `PresenceState` / `PresenceSample` / `ProbeFailurePolicy` は presence.py 所有にしない。presence.py は capture_region の `localize_from_rgb_bytes` を import しており (presence.py:22)、§5.4 site 6/10 で capture_region 側 (下位 module) が UNKNOWN を参照するため、presence 所有のままだと capture_region → presence の逆向き import で cycle になる (capture_region 内の detector import がすべて関数 local なのも、同じ cycle 制約の既存回避策)。実装 PR では両者から独立した中立 module (例: `allaganeye/video/probe_state.py`) に定義し、presence / capture_region / scorebar / detector がそこから import する。中立 module 案が実装時に過剰と判明した場合の代替 (sentinel object / `TYPE_CHECKING` + 文字列 annotation) の選択は実装 plan で確定する。

### 5.2 縮退方針の明示 API (seam の一般化)

`raise_on_probe_failure: bool` seam を廃し、集約層 (scan / refine / consensus) が受ける方針 enum に一般化する:

```python
class ProbeFailurePolicy(Enum):
    RAISE = "raise"            # UNKNOWN を即例外化
    ISOLATE = "isolate"        # per-probe 隔離: UNKNOWN のまま集約に流す (default)
```

- 単発 probe 関数 (site 1) は常に tri-state を返し、decode 例外を **caller に漏らさない** (UNKNOWN に写像し、写像した事実を debug log する)。
- 集約層 (site 2/3/10/14) が UNKNOWN の扱いを決める:
  - 集計から除外 (present 率・consensus 票の分母に入れない — site 5 の `_majority_scorebar` が既に持つ挙動の規範化)
  - UNKNOWN 数を集計し、部分故障 (UNKNOWN ≥ 1) で warning (§5.3 の log 階層と一致 — 現行 R5 実装 presence.py:201-210 の「failures ≥ 1 で warning」の規範化)、全滅 (100%) で `VideoProcessingError` (fail-loud)
  - **全滅 fail-loud の適用は site 2 (`scan_presence`) のみ** (現行の全滅 raise 挙動の規範化)。site 3 (refine) は §5.4 どおり現行挙動維持 (UNKNOWN を absent 側に倒す + warning)、region 解決層 (site 9/10/14) は全滅時も **FULL_FRAME 縮退 + §5.3 warning で続行し fail-loud を適用しない** (detect 出力不変 — §6 item 3(b) の bit-exact 論拠の前提)
  - warning message に UNKNOWN 数 / 総 probe 数を必須で含める (R5 の部分故障集計 warning を契約に昇格)
- **RAISE の現時点の消費者はゼロ** (現行 seam の呼び出し 2 箇所 = presence.py:182 / :239 はどちらも新設計で ISOLATE 化される)。将来の診断 harness / GT 突合用の speculative seam であり、実装時に消費者が現れなければ **ISOLATE のみで開始してよい** (enum は将来拡張として定義だけ残す)。

### 5.3 log 階層 (契約)

| 事象 | レベル | 必須内容 |
| --- | --- | --- |
| 全滅 (全 probe UNKNOWN) | exception (fail-loud) | probe 数、代表原因 |
| 部分故障 (UNKNOWN > 0) | warning (集約層で 1 回) | UNKNOWN 数 / 総数、time range |
| 単発 probe 失敗 | debug | timestamp、原因 (decode None / 例外種) |
| consensus miss (非例外、有効票不足) | warning (発火は region 解決層 = site 9/14) | 有効票数 / min_hits、FULL_FRAME 縮退の明示 |

### 5.4 site 別移行 map

| site | 移行内容 |
| --- | --- |
| 1 `localize_present_at` | 戻り値を tri-state 化 (raw None → UNKNOWN / localizer miss → ABSENT)。`raise_on_probe_failure` param 削除 (呼び出し 2 箇所は集約層方針 §5.2 に移行) |
| 2 `scan_presence` | per-probe try/except を「UNKNOWN 写像」に置換。全滅 fail-loud / 部分 warning は §5.2-5.3 の契約実装として維持 |
| 2b `segment_presence` (presence.py:73) | scan_presence 出力の直接消費者 (旧 `.present` 直読み — §5.1 の property 不提供に伴い explicit な state 比較へ移行)。**UNKNOWN sample は present run を構成しない (ABSENT と同様に run を切る側に倒す = 現行挙動の維持)**。この折り畳みは集約層の明示変換 (§5.2) として行い、UNKNOWN の可視化は scan_presence 側の部分故障 warning が担う (segment_presence 自体は純粋関数のため log を持たない) |
| 3 refine (`detect_matches_by_presence`) | refine では **UNKNOWN probe は False (absent) を返して bracket を更新する** (= 現行 R5 挙動の維持、presence.py:243-251。skip / refine abort はしない。境界誤差は最大 1 refine stride)。「有効票にしない」は §5.2 の UNKNOWN 集計 (分母除外) のみを指し、binary search の bracket 更新とは別軸。coarse 境界保持 (refine abort) への変更は行わない — §6 項 4 の「分類結果を変えない」前提を守る |
| 4 `_localize_present_from_raw` | **semantics 変更なし**。表現形式の置換のみ (bool\|None → PresenceState。None → UNKNOWN / False → ABSENT / True → PRESENT) |
| 5 `_probe_scorebar_context` | **with_localize (localize-present) 系のみ** tri-state 化。`scorebar_results` (bool\|None、OBS production 分類が消費) は**不変** — `_majority_scorebar` の None 分母除外 / classify の "unknown" 化 (scorebar.py:396) は既に契約相当の挙動であり触らない (review R1 P1-2 対応: OBS bit-exact 維持) |
| 6 `localize_from_rgb_bytes` + 10 `detect_scorebar_band_region` | `localize_fn` の signature を 3 値に拡張: `Callable[[float], ScorebarLocalization \| None \| Literal[PresenceState.UNKNOWN]]` 相当 (None = decode 成功 + miss / UNKNOWN = decode 失敗)。UNKNOWN の enum は §5.1 の中立 module に配置し、capture_region → presence の import を作らない (circular import 回避)。decode 失敗判定は binding closure (site 9 内の `_localize_at`、detector.py:276) が raw None を見て UNKNOWN を返す形で境界を越えさせる。consensus 集計 (site 10) は UNKNOWN を票の分母から除外し、UNKNOWN 数を §5.2 の部分故障 warning 集計に乗せる |
| 9 `_resolve_detect_region` | anchor 例外の catch → FULL_FRAME 縮退は維持 (`--vtuber` gate 内の設計済み縮退、detector.py:462)。warning 文言を §5.3 契約形式に揃える |
| 14 `_resolve_masked_region` | per-frame decode None → UNKNOWN 集計 (silent drop 廃止)、例外 catch → FULL_FRAME 縮退は維持しつつ **§5.3 の warning を必須化** (現状 log ゼロ)。site 9 と同型の契約に揃える |

## 6. テスト戦略

1. **既存 warning pin テスト 7 件の移行 map** (置換であり削除ではない。6 件は PR #823 R3-R5 由来、`test_borderline_pseudo_regions_capped_with_warning` は #842/#843 W4 由来の可能性あり — 実装時に git 履歴で帰属を確定):
   - `test_probe_scorebar_context_logs_probe_failure` (test_scorebar.py:1667) → site 5 の scorebar_results 側は不変のため**そのまま維持** (debug log 契約 §5.3 の pin)
   - `test_scan_presence_partial_failures_logged` (test_presence.py:290) / `test_refine_probe_failure_warns_and_treats_absent` (test_presence.py:305) → 「UNKNOWN 集計 warning + 分母除外」の契約テストに書換
   - `test_resolve_detect_region_swallows_exceptions_to_full_frame` (test_detector.py:2724) / `test_resolve_detect_region_warns_on_consensus_miss_full_frame` (test_detector.py:2743) → 文言契約 (§5.3 表) に揃えて維持
   - `test_localize_from_rgb_bytes_none_passthrough_and_decode` (test_presence.py:339) → None passthrough 維持 (§5.4 site 6: 関数自体の None 契約は不変)
   - `test_borderline_pseudo_regions_capped_with_warning` (test_detector.py:1645) → 対象外 (OBS path、無変更)
2. **新規契約テスト**: 「UNKNOWN が ABSENT に暗黙変換されない」型/分岐テスト (`.present` 相当の silent bool 化経路が存在しないことの pin を含む — §5.1)、全滅 fail-loud、部分故障 warning 集計 (UNKNOWN ≥ 1)、site 14 の decode 失敗可視化 (silent drop 廃止の pin)、refine 中の連続 UNKNOWN (§5.4 site 3: bracket が absent 側に単調更新され refine abort しないことの pin)
3. **OBS bit-exact gate**: (a) presence 系は OBS production 経路に非配線 (presence.py docstring + detection-map §5.4)、(b) anchor は `--vtuber` gate 内 (detector.py:462)、masked region は masked fallback gate (`not vtuber and (masked or not blackout_times)`、detector.py:548) が OBS baseline では非発動 (baseline は必ず ≥1 blackout → `not blackout_times` = False、detector.py:544-547 コメント)、かつ site 14 の変更は warning 可視化のみで detect 出力不変、(c) site 5 は with_localize 系のみ変更し **OBS が消費する scorebar_results (bool\|None) は不変** — の 3 点で OBS baseline 5 本の detect 出力は bit-exact のはず。実装 PR で必ず実測する (実動画環境)。**注意 (b) の適用範囲**: 「baseline は必ず ≥1 blackout」は baseline 5 本の dataset 性質であり、§3 の通り**非 baseline の OBS 録画でも標準 Pass 1 が blackout ゼロの run では masked fallback gate が自動発動し、site 14 (+ site 5 の with_localize 系) が production 到達しうる**。この case の安全性は bit-exact gate (適用範囲 = baseline 5 本のみ) ではなく、「site 14 = warning 可視化のみで detect 出力不変 / site 5 = scorebar_results 不変」という (b) 後段・(c) の code 論拠で担保する — 実装 PR は localize 系変更を「OBS production 非到達」と誤読しないこと
4. **実機検証**: masked/VTuber サンプル (`ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER`) での detect 回帰 + #822 の過分割サンプルでの挙動確認 (契約導入自体は分類結果を変えない想定の確認。§5.4 site 3 の「現行挙動維持」がその前提)

## 7. 実装タイミング (Idios 確定: Stage 2 統合と同一実装期)

- 再アーキ spec ([`2026-05-31`](2026-05-31-l3-detection-rearchitecture-two-signal-design.md) §8) の **Phase 2 (Stage 2 分類の localize 統合、shadow)** と同一実装期に行う。Phase 2 実装 plan (writing-plans) に本契約の §5.4 移行 map を task として編入する
- Phase 4 (cutover、authoritative 切替) の gate とは独立。本契約は Phase 2 時点の shadow 系 + gate 内経路に閉じ、v2 authoritative の挙動を変えない
- 実装環境要件: OBS baseline 5 本 + VTuber/masked サンプルへのアクセス (デスクトップ環境)。本 spec 作成環境 (ノート PC) では実装しない
- 実装 PR の Pre-flight は Iron Law 6 準拠 (detector.py 変更のため実機検証 AskUserQuestion 必須)

## 8. 却下した代替案

| 案 | 却下理由 |
| --- | --- |
| Result wrapper (`ProbeResult[T] = T \| ProbeFailure(reason)`) | 失敗理由 payload が必要な site が現状ない (log で足りる)。型の侵入度が大きく、Stage 2 統合と独立に全 signature を変えることになる |
| 例外ベース統一 (probe 失敗は常に raise) | bool 返却の既存 site 全てに try/except を強制し、per-probe 隔離 (site 2) が例外 flow 依存になる。#234 の教訓 (probe pool の例外は漏れやすい) に逆行 |
| 全 site 一括適用 (対象外 6 site 含む) | OBS production path (255.0 bias / GPU chunk / scorebar V1/V2 入口) の bit-exact リスクと実機検証コストが、得られる一貫性に見合わない。OBS path は別 issue で必要になってから |
