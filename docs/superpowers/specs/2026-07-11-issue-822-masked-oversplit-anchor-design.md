# #822 masked 過分割解消: anchor presence + segment 検証 設計 spec

> 状態: design (AskUserQuestion で Idios 確定 2026-07-11: 案 1 / 非試合 segment 削除 + fail-safe / masked の in_match keep 規則撤廃)。
> 実装は #824 契約 ([2026-07-03 spec](2026-07-03-issue-824-probe-failure-semantics-design.md)) と同一実装期 (spec §7)。
> 関連: #822 (本 spec の元 issue) / #824 (probe 失敗 semantics、同一実装期) / #821 (masked-OBS parent) / #753 (L3 parent) / 再アーキ spec ([2026-05-31](2026-05-31-l3-detection-rearchitecture-two-signal-design.md) §8 Phase 2) / masked spec ([2026-06-05](2026-06-05-masked-ultrawide-obs-detection-design.md) §6 で「精緻化は後続」とされた当のタスク)

## 1. 実データ分析: issue 仮説の訂正 (2026-07-11 実施)

issue #822 の仮説「試合終盤の定型暗転を boundary と誤判定」を実フレーム検証した結果、故障モードは別物と確定した。

**~5.5min の短 clip (29 M19/M21、27 M7、28b M2/M8) の中身は全フレーム Wolves' Den Pier (試合間 lobby)** である (M19 +330s にはデイリーチャレンジのレディチェックが写る)。29 M24 (23.2min) も全域 lobby (長時間の休憩滞在)。root cause の 1 行化:

> **実境界 blackout に挟まれた非試合 (lobby) 区間が `min_match_duration` (300s) 以上のとき segment として生き残る。** ~5.5min の一貫性は当該プレイヤーの再キュー待ち時間であり、300s 未満の通常 lobby は duration filter が黙って除去していたため露見しなかった。

メカニズム (production probe の再現で実証):

1. **merge gate の構造的破綻**: `_merge_boundary_pairs` の gap 9 probe は `any_scorebar=True` で merge を拒否するが、位置独立 localizer (`localize_scorebar`、best-hit 方式) が lobby フレームで 20-45%/frame の率で FP (conf ≤0.32、位置ランダム) を出す → ほぼ全 lobby で merge 失敗。短 lobby control (29 M1→M2、250s) でも 4/9 FP を実測 — **破綻は表面化した 5.5min ペアに限らず系統的**
2. **best-hit 方式の flank 誤判定 (両方向)**:
   - FP 方向: M18/19 境界の post-flank で Wolves' Den の HUD を 3 probe 連続・同一 bbox (y=[504,555]) で FP → majority では防御不能 → in_match 誤分類 (現行は「in_match ≥3.5s keep」規則で偶然 boundary 化)
   - FN 方向: staging (バーは可視だがスコア 0/700 で低彩度) と試合中の一部フレームで、真のバーが「FULL PARTY」バナー等の強い band 応答にスコア負けし best-hit を奪われ absent 化。**entry 境界の keep は現状 lobby FP の偶然に依存している**

### 1.1 anchor 方式のプロトタイプ実証

真のスコアバーは per-video で位置が極めて安定: 29 の 17 試合 midpoint probe で 15 hit が x=[614,1305]、y_top=12±6、conf 1.00 (FP 1 件は conf 0.17 で位置乖離)。「y 走査を anchor 帯 ±60px に制限 + saturated run の x-IoU ≥ 0.5 gate」に制約した emblem 3 点 AND (= v2 と同じ特異度エンジンを学習位置で回す **per-video v2**) をプロトタイプ実装して計測:

| テストセット | 結果 |
| --- | --- |
| lobby 18 probe (M19 gap 9 + M1M2 control 4 + M24 deep 5) | **18/18 absent** (FP ゼロ) |
| 試合中 best-hit FN ケース (t=19000) | PRESENT に回復 (margin 1.36) |
| 勝利ウィンドウ/リザルト pre-flank ×3 | PRESENT (margin 1.28-1.36) — v2 残像問題は at-anchor では発生しない |
| staging 頭 (zone-in 直後 ~60s、スコア 0/700) | 4/5 absent — **唯一の残弱点** (§3.2 の non_fl keep 規則で吸収) |

staging 弱点により「flank 分類の anchor 化だけ」では entry 境界が non_fl → 削除 → lobby が次試合に融合し現状より悪化する。これが 2 層構成 (§2) を要する理由。

## 2. 確定方針 (AskUserQuestion、Idios 2026-07-11)

| # | 論点 | 決定 | 理由 |
| --- | --- | --- | --- |
| Q1 | アプローチ | **案 1: anchor presence + segment 検証の 2 層構成** (案 2 merge quorum 最小修正 / 案 3 anchor のみ は却下) | 全 7 過分割ケースを構造的に解消。案 2 は entry 境界の FP 依存構造を温存 (whack-a-mole 継続)、案 3 は staging 弱点の救済に時間定数ハックが必要で脆い |
| Q2 | 非試合 segment の処置 | **削除** (stats/log に削除数を記録)。fail-safe: 全 segment が非試合判定になる場合は全件 keep + warning | OBS path の non_fl 除去と同じ意味論。lobby footage に保持価値なし |
| Q3 | masked path の「in_match ≥3.5s は boundary として keep」規則 (v2 残像 FN 救済用) | **masked では撤廃** (in_match は duration 問わず非境界として除去)。OBS path の同規則は不変 | at-anchor はリザルト画面でも正検出する (margin 1.3 実測) ため残像問題が発生しない。規則温存は試合中 3.5-6s 暗転による zero-gap 分割リスクを残す |

## 3. アーキテクチャ: masked fallback 内の 2 層構成

`_detect_masked_fallback` (detector.py) の改訂データフロー:

```text
1. _resolve_masked_region                    (既存。#824 site 14 = warning 契約化のみ)
2. NEW: anchor 解決                           sparse ~24 frame localize → conf フィルタ →
   (_resolve_scorebar_anchor)                 y-cluster dominant → median ScorebarLocalization。
                                              失敗時 anchor=None → 現行動作縮退 + warning (§5)
3. Pass 1/2 region-aware                     (不変)
4. filter_blackouts_with_scorebar(localize=True, anchor=…)
   - classify: at-anchor tri-state presence (§3.1)
   - masked 分類規則 (§3.2): in_match → 全除去 / non_fl → boundary 候補として keep
   - merge gap probe も at-anchor 化
5. _filter_and_extract_segments              (不変)
6. NEW: segment 検証 (Layer 2、§3.3)          scan_presence (sample_fn=at-anchor) 9 点 probe、
                                              valid probe の present majority 未満 → 削除
```

OBS production path (`classify_blackout(localize=False)`、`_merge_boundary_pairs` の非 localize branch、`_flag_post_match_trailing`) と `--vtuber` path は**一切変更しない**。変更は masked gate + presence.py (OBS 非配線) + capture_region の additive 変更に閉じる (bit-exact 構造保証、detection-map §5 制約遵守)。

### 3.1 Layer 1: anchor 解決 + at-anchor presence primitive

**anchor 解決**: `detect_scorebar_band_region` (capture_region.py:510) の consensus core (sparse sample → localize → y_top クラスタ tol 60px → dominant cluster → median) を `consensus_scorebar_localization(...) -> ScorebarLocalization | None` として抽出し共有する。既存 caller (`--vtuber` Stage 0) は抽出後も挙動不変 (`detect_scorebar_band_region` が core を呼ぶ形、既存 unit の argv/出力 pin で担保)。masked 用パラメータ: サンプル数を増やす (24 目安)、低 conf hit の事前フィルタ (閾値は実装時に 3 サンプルで calibrate、実測では真 hit conf ~1.00 / FP ≤0.67)、min_hits を引き上げ。dominant cluster 不成立 → None。

**at-anchor presence primitive**: `localize_scorebar` の走査を anchor 近傍に制約する評価関数 (additive param または新関数。default = 従来全走査で既存 caller bit-same):

- y 走査域: `anchor.y_top ± 60px` (クラスタ tol と同値)
- saturated run の x-IoU gate: run と anchor x-range の IoU ≥ 0.5
- 判定エンジン: 既存 `_scorebar_saturated_runs` + `_emblem_and_margin` (emblem 3 点 AND) をそのまま使用
- 戻り値は tri-state native (#824 §5.1): decode 失敗 (raw None) = UNKNOWN / 制約下で emblem AND 不成立 = ABSENT / 成立 = PRESENT + confidence

### 3.2 masked 分類規則の変更 (`_classify_blackout_localize` / keep 判定)

presence primitive を at-anchor に置換した上で、keep 判定を masked path (localize=True) についてのみ次のとおり変更する:

| 分類 | OBS path (不変) | masked path 現行 | masked path 新 |
| --- | --- | --- | --- |
| in_match short (<3.5s) | remove | remove | remove |
| in_match long (≥3.5s) | **keep (boundary)** | keep (boundary) | **remove** (Q3。at-anchor に残像 FN が無いため規則の存在理由が消滅) |
| match_boundary | keep | keep | keep |
| non_fl | remove | remove | **keep (boundary 候補)** (staging 弱点で entry 境界が non_fl 化するため。乱立する非試合 segment は Layer 2 が除去) |
| unknown | keep (safe) | keep (safe) | keep (safe) |

> **erratum (2026-07-14, PR-B final review + codex 収束摘出)**: 本表の「masked path 新」規則は **anchor 解決成功時のみ** 適用する
> (`anchored = localize AND anchor != None` gate)。anchor 未解決の縮退 run と `--vtuber` path は
> pre-#822 規則のまま (§5 の「現状より悪化しない」floor と §8 の #480 defer を機構的に保証)。
> 実装は `scorebar.py` の `anchored` gate を正とする。

`#524` re-probe fallback (両側 not True 時の region_width+1/2/3s 再 probe) は at-anchor 化した presence で同構造のまま維持する。

### 3.3 Layer 2: segment 検証

`_filter_and_extract_segments` の出力 (masked path のみ) に対し:

1. 各 segment 内の 9 点均等 timestamp (merge gap probe と同じ配分式) を `scan_presence` (presence.py、`sample_fn` = at-anchor presence を bind) で probe する。現行 `scan_presence` は全動画 grid 前提 (`duration` + `stride`) のため、**時間範囲 (または明示 timestamp 列) を受ける additive 拡張**を行う (既存呼び出しは default で挙動不変)
2. UNKNOWN は分母から除外 (#824 §5.2)。valid probe の PRESENT 数が majority (過半) 未満 → 非試合 segment として削除。削除数・削除区間を stats + log (info) に記録
3. fail-safe:
   - 削除の結果 segment がゼロになる場合 → 全件 keep + warning (anchor 誤りの疑い。silent 全滅を防ぐ)
   - segment 内全 probe UNKNOWN → keep (保守側) + warning (§5.3 の部分故障 warning と同型)
4. 判別余地は実測で大きい: 試合 segment の present 率 ~85-100% (staging 頭を含んでも 9 点中高々 2 点) vs lobby 0/18

Layer 2 は `scan_presence` (#824 site 2) の最初の production 消費者 (masked gate 内) となる。presence.py の OBS 配線は行わない。

## 4. #824 契約の編入 (同一実装期)

[#824 spec §5.4](2026-07-03-issue-824-probe-failure-semantics-design.md) の移行 map 全 site (1 / 2 / 2b / 3 / 4 / 5 / 6+10 / 9 / 14) を本実装期で実装する。要点:

- 中立 module `allaganeye/video/probe_state.py` に `PresenceState` / `PresenceSample` / `ProbeFailurePolicy` を配置 (#824 §5.1 の circular import 回避案)
- at-anchor primitive は最初から tri-state を返す (bool 経由の暗黙変換経路を作らない)
- Layer 2 の集約規則 (UNKNOWN 分母除外 / 部分故障 warning / scan 全滅 fail-loud) = #824 §5.2-5.3 契約の実装
- 既存 warning pin テスト 7 件は #824 spec §6 の移行 map どおり書換/維持
- site 5 の `scorebar_results` (OBS 消費) は不変 — bit-exact 論拠 (#824 spec §6 item 3) を実装 PR に転記し「localize 系変更 = OBS 非到達」と誤読しないこと (masked fallback は `--masked` 無指定でも標準 Pass 1 blackout ゼロ時に自動発動する)

## 5. エラー処理・縮退

| 事象 | 挙動 |
| --- | --- |
| anchor 解決失敗 (dominant cluster 不成立) | anchor=None → Layer 1/2 とも現行 position-independent 動作に縮退 + warning (#824 §5.3 形式)。検出が現状より悪化しない下限を保証 |
| Layer 2 で全 segment 非試合判定 | 全件 keep + warning (Q2 fail-safe) |
| segment 内全 probe UNKNOWN | keep (保守側) + warning |
| probe 部分故障 | UNKNOWN 集計 warning (#824 §5.2、分母除外) |

## 6. cache key (memory: detection-flag-cache-key)

masked path の検出出力が変わるため、旧 cache の silent 再利用は released regression class。`_save_cache` / `_load_cache` / verbose 表示の 3 箇所に masked アルゴリズム版数 (または anchor 関連 param) を追加する。legacy cache は `.get(..., default)` で不一致 → miss になる形。

## 7. テスト戦略

1. **TDD unit (動画不要、合成 frame)**: consensus core 抽出の挙動 pin (既存 caller bit-same) / anchor 解決 (cluster vs scattered FP、min_hits 縮退) / at-anchor primitive tri-state (PRESENT / ABSENT / UNKNOWN、y 制約・x-IoU gate) / masked 分類規則 (§3.2 表の 5 行、OBS 側不変 pin) / merge at-anchor / Layer 2 (majority、削除、fail-safe 2 種、UNKNOWN 分母) / #824 pin 7 件移行
2. **OBS bit-exact gate**: baseline 5 本の detect 出力 byte 一致を実測 (構造保証の主張だけで済ませない)
3. **実機 (3 masked サンプル)**: 27 / 28 / 29 を再 detect (`--no-cache`、7h 級 GPU detect は detached Start-Process — memory: long-gpu-job-detached-execution)。期待: 過分割 zero-gap ペア解消 + 既存正検出の非退行。期待 match 数の目安: 29: 25→22 / 28b: 8→6 / 27: 13→12。**28b M5/M6 ペアの真相 (実試合の中割りか lobby 融合か) と、28 (非 b) run が 1 match unknown になった原因の確認を GT 確定タスクとして編入**
4. **CPU/GPU parity**: masked path は分類/検証が CPU probe のため Pass 1 の GPU/CPU で出力不変のはず — 最低 1 サンプルで確認

## 8. スコープ境界 (やらない)

- OBS production path / `--vtuber` path の anchor 化 (#480 defer、v0.4.0 期)
- anchor の metadata 永続化 (schema 変更) — v1 は log のみ。#810 `capture_regions` への追加は後続判断
- presence.py の OBS 配線 / `_flag_post_match_trailing` の変更 (detection-map §5 制約)
- `min_match_duration` の変更・lobby 判定の時間ヒューリスティック追加 (presence 信号で解くのが本筋)

## 9. PR 分割 (見立て、plan で確定)

**PR-A (#824 契約 = 挙動不変 refactor + pin テスト) → PR-B (#822 anchor + Layer 2 = 挙動変更 + 実機 gate)** の直列 2 PR。#824 spec §7 の「同一実装期」要求は満たす。PR-A 完了時点で OBS bit-exact gate を一度回し、挙動不変を先に固定してから PR-B の挙動変更を載せる (regression の切り分け性)。

## 10. 参照

- 分析 artifacts: `.tmp-822-analysis/` (untracked scratch。実装 PR で `.gitignore` + pyright exclude 追加は #828 前例に従う)
- プロトタイプ実測値: 本 spec §1.1 の表 (セッション 2026-07-11、worktree heuristic-leavitt-8211de)
- issue #822 本文の確認項目 1 (M19/M21/M24 の特徴分析) は本 spec §1 で消化。項目 2 (精緻化方針) は §2-§3。項目 3 (3 サンプル実機再検証) は §7 item 3
