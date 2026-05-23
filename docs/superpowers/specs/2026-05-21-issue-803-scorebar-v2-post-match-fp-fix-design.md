# Design: scorebar V2 post-match FP fix (#803) + optional #797 bundle

| Field | Value |
| --- | --- |
| **Status** | #803 gate + #797 M7 drop は 5-baseline verified (2026-05-22、54 boundary 全 agreed / 0 finding)。#797 trailing-drop は Codex 再 review を受けて multi-probe guard に強化 (2026-05-23、§0.6「実装の変遷」)、5-baseline 実機 audit 再検証 pending |
| **Issues** | [#803](https://github.com/Idios/kobutachan-allaganeye/issues/803) (primary, P2 bug) + [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) (secondary, P2 refactor, conditional bundle) |
| **Parent spec** | [2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md](2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md) §9-§10 (V6.2 attempt → revert → #803 起票) |
| **Related root cause** | PR [#793](https://github.com/Idios/kobutachan-allaganeye/pull/793) post-merge verification で発覚した `_has_scorebar_v2` の post-match content (5700-6850s, obs-20260116) False positive (true M6 end 6540 を超えて FP 群発火) |
| **Adversarial review** | Iron Law 6 Pre-flight Step 5 で `/codex:adversarial-review` 実行予定 (PR 作成時) |
| **Scope** | v0.3.x (Pillar 3 detect / v0.3.0 baseline audit follow-up)。`#804` (validate-fps-retirement.py PTS fix) は別 session |

## §0. Phase 1 investigation results (2026-05-22 確定)

Phase 1 debug (`scripts/debug-scorebar-v2-fp.py`、obs-20260116、Idios RTX 5090 実機) で当初仮説 (§2.2 の padding / 色域 / 構造) を棄却し、root cause と Fix を確定した。本節が最新・確定で、§2.2 / §3.1 / §3.2 の当初記述は経緯として残す。

### §0.1 発見 1: 6540 の True は FP ではない (scorebar 残存)

実機 frame (PNG) + Primary path 数値で scorebar HUD の消失点を特定:

| t | Primary 本来座標 sat (left/center/right) | scorebar | 画面 |
| --- | --- | --- | --- |
| 6540 | 174.3 / 176.3 / 176.2 | **あり** | 試合終了「退出しますか」ダイアログ、scorebar HUD 残存 |
| 6541 | 0.0 / 0.0 / 16.2 | なし | Limsa ワープ暗転 |
| 6541-6543 | span=None | なし | ワープ / ローディング (彩度ゼロ) |
| 6544+ | Primary False | なし | Limsa 到着 |

→ **scorebar 消失点 = 6540-6541 間 (≈6540.5)**。ground truth M6 end 6540 と一致 (±1s)。6540 で V2 True は scorebar が実際にあるための正常検出。

### §0.2 発見 2: FP は Rescue path 単独犯 (6 件)

post-match の真の FP は **例外なく `Primary=False / Rescue=True`**。Primary path (絶対座標) は zero FP を維持:

| FP frame | Rescue span | width | 画面 (PNG) |
| --- | --- | --- | --- |
| 6544-6555 | 1407-1410..1919 | ~510 | Limsa、右端チャット欄を span 誤検出 |
| 6800 / 6850 | 8..1919 | 1912 | 派手な黄金内装 + ステンドグラス、全幅を誤検出 |
| 6895 | 8..544 | 537 | 同上、左端を誤検出 |

### §0.3 確定した root cause

`_find_scorebar_horizontal_range` (Rescue path の span 検出、detector.py:1073) が緩すぎる:

1. **width 上限が無い** — `_SCOREBAR_SCAN_MIN_WIDTH_PX=500` の下限のみ。画面全幅 1912px すら scorebar とみなす
2. **水平位置の検証が無い** — 画面右端 (1407..1919) / 左端 (8..544) を scorebar とみなす

in-match span は一貫して ~600..1320 / width ~715、4K Game DVR (#522) は ~613-620 / 中央寄り。FP span は位置・幅が大きく外れているのに accept されている。誤検出 span の相対 3 点に偶然 sat>70 & edge>40 が乗って AND が成立。

### §0.4 確定した Fix: Rescue span gating

`_find_scorebar_horizontal_range` が返す span に 2 つの gate を追加 (Primary path は無変更):

1. **width 上限** (新定数 `_SCOREBAR_SCAN_MAX_WIDTH_PX`、暫定 ~1100-1200px) — 1912px を reject、in-match ~715 / 4K ~615 を通す
2. **中央位置要求** — span が画面中央 x=960 を含む (`x_left <= 960 <= x_right`) ことを要求。1407..1919 / 8..544 を reject、600..1320 / 4K 中央寄りを通す

| span | width | 中央(960)含む | 判定 |
| --- | --- | --- | --- |
| 600..1320 (in-match) | ~720 | ✓ | 通す |
| ~613-620 (#522 4K) | ~615 | ✓ (中央寄り) | 通す |
| 1407..1919 (6544-6555) | ~510 | ✗ | reject (中央) |
| 8..1919 (6800/6850) | 1912 | ✓ | reject (width) |
| 8..544 (6895) | 537 | ✗ | reject (中央) |

具体閾値は Phase 2 で #522 baseline の実 span 値を確認して最終決定。

### §0.5 criteria 訂正 (#803 受け入れ条件)

issue #803 の「6540 で False を返す」は実機の scorebar 挙動と矛盾するため訂正する:

- 訂正前: 6540 で False
- 訂正後: **6540 で True (scorebar 残存) / 6541 で False (Limsa ワープ後、消失)**。真の試合終了境界 6540-6541 は ground truth と一致

この訂正は PR 本文の Iron Law 1 逐条検証と issue #803 コメントに Phase 1 実証データ付きで記録する (独断で issue 本文を書き換えない、Iron Law 5)。

### §0.6 #797 解決 (実装完了 2026-05-22)

実機検証で確定。当初想定した V6.2 (scorebar 二分探索) は**不要**だった:

1. **#803 Rescue gating** で M6 end が 7303→6542 (GT 6540 +2s) に正確化、M6 が unknown→fl_match に。
2. ただし gate 副作用で post-match (6542-7303) が unknown segment (M7 = match_007.mp4) として分離。これは detector "After last blackout" (line 1847) が試合終了後の trailing を出力する #797 の本体。
3. **対策 A (post-match trailing drop)**: 最後の有効 blackout が match_boundary なら trailing を post-match と判定し drop (`_filter_and_extract_segments` の "After last blackout")。obs-20260116 で M7 除去 → **6 match / 12 agreed / 0 finding** (GT 完全一致)。実装は plan Task 6。

他 4 baseline (118/119/127/209) は trailing < 300s で対策 A 影響なし、gate も in-match 通過で regression ゼロ。**5 baseline / 54 boundary 全 agreed**。V6.2 二分探索は M6 end が暗転境界として既に 6542 に確定したため要らなかった。

**実装の変遷 (#797 trailing-drop、Codex review chain)**: 上記 **対策 A** (最後の有効 blackout が `match_boundary` なら drop) は無方向な `match_boundary` 分類を key にしていたため、「lobby→試合開始→EOF まで試合」録画で真の試合 trailing を誤 drop しうる、と Codex adversarial-review (2026-05-22) が [high] 指摘。これを受けて専用 helper `_drop_post_match_trailing` が **trailing segment 自体の scorebar を probe** する方式 (C') に置換 (commit 64a72ba / d759fe9)。さらに再 review (2026-05-23) で「単一 midpoint probe は *mixed* trailing (真の試合 + より長い post-match tail。試合終了 blackout が `non_fl` 誤分類等で scorebar.py で drop された場合に発生) の試合部分まで誤 drop しうる」と [high] 指摘され、early (`_TRAILING_PROBE_START_OFFSET` で開幕 blackout を越えた点) / midpoint / late の **multi-probe guard** に強化。全 probe が definite miss (`False`) のときのみ drop し、1 つでも scorebar hit (`True`) / probe 失敗 (`None`) なら保持する (safe side)。obs-20260116 の M7 drop = 6 match / 0 finding と他 4 baseline の regression ゼロは、この multi-probe 版で実機 audit-compare 再検証する (§3.3 / §4.4、Iron Law 6)。

## §1. Goal & Non-goals

### §1.1 Primary goal (#803)

`allaganeye/video/detector.py::_has_scorebar_v2` (line 1190) を強化し、以下を達成する:

- **obs-20260116 で 6541 (Limsa ワープ後、scorebar 消失) を `False`** と返す (criteria 訂正、§0.5 参照。当初の「6540 で False」は scorebar 残存と矛盾)
- **obs-20260116 で 6450 / 6520 / 6540 (in-match + scorebar 残存) を `True`** と返す (既存挙動保持)
- 既存 validated 5 baseline (obs-20260116 / 20260118 / 20260119 / 20260127 / 20260209) で scorebar 分類 (12 match_boundary / 10 in_match / 2 non_fl) と post-PR #793 の 53 agreed boundary が完全保持される (regression なし)
- #522 (4K Game DVR Rescue path validation, 20260219) / #307 (V2 baseline validation, 156+ non-match frames zero FP) で regression なし

### §1.2 Secondary goal (#797) — 解決済 (§0.6 参照)

> **実装完了 (§0.6)**: V6.2 ではなく **対策 A (post-match trailing drop)** で #797 解決。obs-20260116 が 0 finding。以下は当初の V6.2 計画 (経緯として保持)。

Rescue gating (#803) の fix 完了後、V6.2 (scorebar HUD 二分探索、PR #793 reexamination spec §9 で revert された commit `f7f8879` の logic) を再実装する。

- **収束**: obs-20260116 で V6.2 が M6 end を `6540 ±5s` に収束させる → #803 + #797 を 1 PR で束ね close
- **非収束**: #797 を v0.3.x defer、#803 のみで PR を切る (`docs/v030-baseline-audit.md` に状況を記録)

判断は Phase 4 (§3.4) で実機検証結果から確定する。

### §1.3 Non-goals

- `#804` (`scripts/validate-fps-retirement.py` PTS extraction が常に 0.021 を返す bug) — 独立した P3-low utility bug、別 session で対応
- 他 baseline (obs-20260118 / 20260119 / 20260127 / 20260209) の boundary tuning — 既に 53 agreed のため tuning 不要
- scorebar V1 (`_has_scorebar`, line 1274) のリファクタ — V2 fallback として既存挙動保持
- `_find_scorebar_horizontal_range` 自体の再設計 — Rescue path の input として使うのみ
- audio Fanfare promote / WR scan の改修 — frozen-by-default の方針保持

## §2. 採用 approach: investigation-first minimal V2 strengthening

debug 結果ベースで minimal な条件追加を行う。投機的 (Approach B: padding-first) や全部入れ (Approach C: 3 条件 AND) は採用しない (over-fit / false negative risk が高い)。

### §2.1 V2 検出ロジックの現状 (root cause 分析の出発点)

`_has_scorebar_v2` は two-path OR semantics:

- **Primary path** (line 1248): `_EMBLEM_POSITIONS` 絶対座標で GC 紋章 3 点 AND 判定 (Maelstrom / Twin Adder / Immortal Flames の HSV saturation + Sobel edge density)
- **Rescue path** (line 1252): `_find_scorebar_horizontal_range` で動的 span を取得 → `_EMBLEM_RELATIVE_POSITIONS` 相対比で emblem 位置を算出 → 同じ 3 点 AND 判定 (#522 で追加、4K Game DVR の HUD scale 差異対応)

issue #803 実証データ (obs-20260116):

- 5700 / 6000 / 6400 / 6520 (in-match): True (期待 True、一致)
- **6540 (true M6 end / Fanfare moment): True (期待 False、FP)**
- 6555 - 6850 (post-match cutscene / GC scoreboard): True (期待 False、FP 群)
- 6890 / 6898 / 6900 / 6920-7290: False (一致)

FP 範囲 = 6540-6890 ≒ 350s。Primary / Rescue どちらの path が原因かは debug で確定する。

### §2.2 検出強化候補 (当初仮説 — Phase 1 で不採用、§0.4 参照)

> **確定 (§0.4)**: Phase 1 の結果、FP は Rescue path の span 検出由来と判明 (Primary は zero FP)。以下の当初候補 (padding / 色域 / 構造) はいずれも採用せず、**Rescue span gating** (`_find_scorebar_horizontal_range` に width 上限 + 中央位置要求) を採用する。本節は検討経緯として残す。

- **候補 1 (padding 検証)**: emblem 領域の上下 (e.g., `y-20:y-5`, `y+25:y+40`) の brightness 平均が閾値以下 (e.g., `< 60`) を要求。in-match scorebar は半透明黒背景の上に置かれる (post-match cutscene は明背景、city interior はステンドグラス背景で multi-color)
- **候補 2 (色域絞り込み)**: 3 GC の specific RGB range (Maelstrom red `(180-255, 30-80, 40-90)` / Twin Adder yellow `(220-255, 200-240, 60-110)` / Immortal Flames orange `(220-255, 100-160, 30-80)` 等、Phase 1 で確定) で template matching に絞り込み
- **候補 3 (構造検証)**: `_find_scorebar_horizontal_range` の span 内で中央寄りに score 数値 2 箇所の高 contrast vertical band を要求 (in-match のみ score 0-100 数値表示が 2 箇所中央寄りに存在)

3 候補全 AND は false negative risk が高いため避ける (over-fit による in-match 検出漏れ)。

## §3. Phase 構成

### §3.1 Phase 1: Investigation (frame-level FP localization) — 完了 (2026-05-22)

> **完了**: 実機 debug で root cause を確定 (§0)。FP は Rescue path 単独犯、scorebar 消失点は ground truth 6540 と一致。以下は実施手順の記録。

**目的**: FP 源を specific UI element (GC scoreboard / VICTORY banner / lobby UI / city interior 等) に紐付けて identify する。

**手順**:

1. throw-away script `scripts/debug-scorebar-v2-fp.py` を作成 (PR には含めない、Phase 5 / 5' 前に削除)
2. obs-20260116 から `_probe_frame_rgb_hires` で **15 timestamp** の 1920x1080 PNG を抽出して保存:
   - in-match baseline: 5450, 5700, 6000, 6400, 6450, 6520
   - true M6 end & FP 群: **6540** (Fanfare), 6555, 6600, 6700, 6800, 6850
   - transition / clean: 6890, 6895, 6898
3. 出力先: `output/v2-fp-investigation/<t>.png` (git ignore)
4. `_has_scorebar_v2` 内に temporary tracing を仕込み、Primary / Rescue どちらが True を返したかと、3 emblem 位置の HSV saturation / edge density 値を stderr に出力
5. **Execution**: Claude が script を書き、**Idios が RTX 5090 環境で実行**、output PNG + stderr trace log を Claude に共有 (Iron Law 6 実機検証必須)
6. Claude が PNG を Read tool で確認、Idios と一緒に FP 源 UI element を identify

**終了基準**:

- FP が Primary path / Rescue path のどちらで発火しているかが確定
- 6540-6850 範囲の FP frame 群に共通する UI 特徴 (e.g., 「emblem 位置に GC scoreboard の自分の GC 所属表示が偶然重なる」「post-match cutscene の colored banner が emblem 様」等) が特定
- Phase 2 候補のうち最も narrow に効く 1-2 つが選定可能

### §3.2 Phase 2: Rescue span gating (§0.4 で確定)

> **確定 (§0.4)**: 実装対象は `_find_scorebar_horizontal_range` (Rescue path の span 検出)。span に (1) width 上限 `_SCOREBAR_SCAN_MAX_WIDTH_PX` と (2) 中央位置要求 (`x_left <= 960 <= x_right`) の 2 gate を追加する。Primary path (`_emblem_and_check` / `_EMBLEM_POSITIONS`) は無変更 (zero FP 維持)。当初の §2.2 候補 (padding / 色域 / 構造) は不採用。

実装方針 (確定版):

- `_find_scorebar_horizontal_range` が longest span を返す直前 (detector.py:1136-1141 の width 下限チェック付近) に width 上限 + 中央位置 gate を追加し、外れたら `None` を返す
- 新定数 `_SCOREBAR_SCAN_MAX_WIDTH_PX` を `_SCOREBAR_SCAN_MIN_WIDTH_PX` の近くに追加。値は #522 baseline の実 span (4K Game DVR ~613-620) と in-match (~715) を通し 1912 を弾く範囲で確定 (暫定 ~1100-1200)
- 中央位置 gate (`x=960` を含む) は定数化せず 1920 幅前提の中央判定で実装 (probe は常に 1920x1080、`_SCOREBAR_V2_PROBE_WIDTH`)
- TDD: §4.1 unit test を先に書いて fail させてから実装

**Phase 2 → Phase 3 loop**:

- Phase 3 で regression が出たら gate 閾値 (width 上限値 / 中央位置条件) を緩和または再調整
- 緩和 / 調整の判断点が出たら都度 AskUserQuestion (Iron Law 5)

### §3.3 Phase 3: Regression check (mandatory gate)

**手順**:

1. unit test (`tests/test_scorebar_v2_fp.py`、§4.1) 全 pass
2. 既存 `tests/test_detector.py` / scorebar 関連 test (もしあれば) 全 pass
3. 5 baseline で `audit-prepare` + `audit-compare` 全件再実行 (`scripts/audit-prepare.py <label>` + `scripts/audit-compare.py <label>`)
   - obs-20260116 (M6 end は #797 verify で確認、他 11 boundary は agreed 維持)
   - obs-20260118 (12/12 agreed 維持)
   - obs-20260119 (18/18 agreed 維持)
   - obs-20260127 (6/6 agreed 維持)
   - obs-20260209 (6/6 agreed 維持)
4. **Execution**: Idios の RTX 5090 環境で実機実行 (audit 1 件あたり ~12 min wall)。Iron Law 6 trigger

**Pass 基準**:

- 既存 scorebar 分類 (12 match_boundary / 10 in_match / 2 non_fl) と post-PR #793 の 53 agreed boundary が完全保持
- 1 件でも regression (新 silent_miss / false_positive / boundary_shift) が出たら Phase 2 ↔ Phase 3 loop

### §3.4 Phase 4 (optional): #797 bundle — V6.2 reintroduce + verify

> **不採用 (§0.6)**: 実機検証の結果 V6.2 は不要だった。実装は **対策 A (post-match trailing drop)** = `_filter_and_extract_segments` の "After last blackout" を classification ベースで gate (plan Task 6)。以下は当初の V6.2 計画 (経緯として保持)。

Phase 3 全 pass 後にのみ実施。

**手順**:

1. V6.2 (scorebar HUD 二分探索) を再実装。reverted commit `f7f8879` の logic を current main branch (Phase 2 fix 後) に re-apply
   - 実装方針: cherry-pick + Phase 2 fix との conflict 解決 or 新規実装 — debug 結果と code diff の cleanness で判断
2. obs-20260116 で `_has_scorebar_v2` が True → False に切り替わる timestamp を `[match_start, video_end]` 区間で二分探索 (e.g., 1s 精度) し、M6 end として metadata.json に書き込み
3. `scripts/audit-compare.py obs-20260116` で M6 end が `6540 ±5s` に収束するか確認 (Idios の RTX 5090 で再実機検証)

**判断**:

- **収束** (`|baseline_M6_end - 6540| ≤ 5`): Phase 5 (束ね PR、§3.5)
- **非収束**: Phase 5' (#803 単独 PR、§3.6)。`docs/v030-baseline-audit.md` の #797 status を「V2 fix 後も V6.2 で 6540±5s に収束せず、別 root cause を v0.3.x で再調査」と更新

### §3.5 Phase 5 (束ね PR): #803 + #797 close

**前提**: Phase 4 で V6.2 が `6540 ±5s` に収束した場合

**PR 作成 (Iron Law 6 Pre-flight 必須)**:

- Step 0: `gh pr list --search "803" --state open` + `gh pr list --search "797" --state open` でハードゲート
- Step 1: `git fetch origin main`
- Step 2: `git log HEAD..origin/main` で取り込み未済 commit 確認
- Step 3: touched files 交差判定 (`allaganeye/video/detector.py` + 5 baseline JSON)
- Step 4: `gh pr list --search "803" --state all` + `gh pr list --search "797" --state all` で並行 PR 重複確認
- Step 5: `/codex:adversarial-review` で Iron Law 3 / encoding / GPU fallback / 同 issue 過去 PR root cause を疑う

**PR description**:

- title 例: `fix(detector): scorebar V2 post-match FP fix + HUD 二分探索 reintroduce (Refs #803 #797)`
- Iron Law 1: 両 issue の `## 受け入れ条件` 各項目を逐条引用し、対応する diff / test を逐条引用 (#367 対策)
- Iron Law 4: **Closes/Fixes/Resolves キーワード禁止**
- Self-Test Report: `[x]` machine-verified (ruff check / ruff format --check / pyright / pytest) vs plain `-` machine-unverifiable (5 baseline audit-compare / V6.2 obs-20260116 6540±5s 収束) を分離 (`docs/l2-workflow.md` §「Self-Test Report 規約」)
- session-id / EXECUTOR directive (`docs/l2-workflow.md` §「resume-plan handoff protocol」)

### §3.6 Phase 5' (#803 単独 PR): #797 defer

**前提**: Phase 4 で V6.2 が非収束、または Phase 4 を skip した場合

**PR description**:

- title 例: `fix(detector): scorebar V2 post-match FP fix (Refs #803)`
- 本文に「V6.2 reintroduce attempt は obs-20260116 M6 end を 6540±5s に収束させず、#797 は v0.3.x defer。`docs/v030-baseline-audit.md` 参照」と明記
- Iron Law 6 Pre-flight (Step 0-5) は同様に実施

### §3.7 Post-merge

- `/close-issue` skill で #803 (Phase 5 / 5' 両方) と #797 (Phase 5 のみ) を実測検証してから手動 close (Iron Law 4)
- #804 は別 session で対応 (本 spec の non-goal、§1.3)

## §4. Test strategy

### §4.1 Unit test (新規、TDD)

**File**: `tests/test_scorebar_v2_fp.py` (新規)

**Fixtures** (Rescue span gating を検証):

- (a) `synthetic_in_match_scorebar()`: 1920x1080 numpy array、span が中央 ~600..1320 (width ~720、x=960 を含む) になる横長彩度帯 + emblem 3 点 → V2 `True`
- (b) `synthetic_offcenter_span()`: span が画面右端 (~1410..1919) になる彩度帯 + その相対 3 点に sat/edge → Rescue 中央位置 gate で reject → V2 `False` (6544-6555 FP 相当)
- (c) `synthetic_overwide_span()`: span が画面ほぼ全幅 (~8..1919、width 1912) になる彩度帯 → Rescue width 上限 gate で reject → V2 `False` (6800/6850 FP 相当)
- (d) `synthetic_no_scorebar()`: 全 frame 均一輝度 (e.g., gray 128) → span None → V2 `False` (既存挙動)
- (e) Phase 1 で取得した real obs-20260116 frame の PNG fixture (`tests/fixtures/scorebar_v2/`) を 3 枚 (6520 in-match / 6540 scorebar 残存 / 6555 post-match FP)

**Test cases**:

- `test_v2_true_for_in_match_centered_span()` — fixture (a) で True
- `test_v2_false_for_offcenter_span()` — fixture (b) で False (中央位置 gate、#803)
- `test_v2_false_for_overwide_span()` — fixture (c) で False (width 上限 gate、#803)
- `test_v2_false_for_no_scorebar()` — fixture (d) で False (#307 regression)
- `test_find_scorebar_range_rejects_offcenter()` / `test_find_scorebar_range_rejects_overwide()` — `_find_scorebar_horizontal_range` 直接 unit test (gate 該当時 `None` を返す)
- `test_v2_real_obs_20260116_6555_false()` — fixture (e) で 6555 frame が False (#803、Rescue FP 解消)
- `test_v2_real_obs_20260116_6540_true()` — fixture (e) で 6540 frame が True (scorebar 残存、criteria §0.5)
- `test_v2_real_obs_20260116_6520_true()` — fixture (e) で 6520 in-match が True (既存挙動保持)

**TDD**: 各 test を先に書いて fail させ、Phase 2 fix で pass させる (`superpowers:test-driven-development` 全面採用、CLAUDE.md §Plugin との関係)。

### §4.2 Regression (既存 test suite)

- `pytest` (slow マーカー除外) で既存 test 全 pass
- `pytest -m slow` (動画ファイル必要) で scorebar 関連 slow test (もしあれば) 全 pass

### §4.3 Audit-compare regression (5 baseline)

- §3.3 で詳細記述。Iron Law 6 実機検証 trigger

### §4.4 実機検証依頼 (Idios dependency)

- Phase 1 frame extract + V2 trace (~10-30 min wall)
- Phase 3 5 baseline audit-compare (`--gpu --no-cache`、各 ~12 min wall、計 ~1h)
- Phase 4 V6.2 + audit-compare (obs-20260116 のみ、~15-30 min wall)
- AskUserQuestion で各 phase 完了時に next phase 依頼 (まとめて 1 回依頼するか phase 毎にするかは Idios 都合で決定、PR 作成時に確認)

## §5. Files touched (estimate)

| File | 操作 | 推定 lines |
| --- | --- | --- |
| `allaganeye/video/detector.py` | `_has_scorebar_v2` + `_emblem_and_check` + 関連定数の修正 | +30-80 |
| `tests/test_scorebar_v2_fp.py` | 新規 | +120-200 |
| `tests/fixtures/scorebar_v2/*.png` | 新規 (Phase 1 から抽出した実 frame 2-3 枚) | binary |
| `tests/baselines/v0.3.0/baselines/obs-20260116.json` | Phase 4 で V6.2 reintroduce する場合 regenerate | (regen) |
| `docs/v030-baseline-audit.md` | #797 status / Phase 5 or 5' 結果反映 | +10-30 |
| `CHANGELOG.md` | `[Unreleased]` Fixed (Iron Law 4 整合で Closes キーワード無し) | +2-5 |
| `scripts/debug-scorebar-v2-fp.py` | 一時 throw-away、commit しない | (throw-away) |

`scripts/debug-scorebar-v2-fp.py` は PR には含めない。Phase 1 終了後に削除。

## §6. Risks & Mitigation

| ID | Risk | Mitigation |
| --- | --- | --- |
| R1 | Phase 1 で FP source が UI element に紐付け identify できない | synthetic frame 解析 + `cv2.matchTemplate` 追加 tool。Idios の domain knowledge (FF14 UI 認識) で specific UI element を特定。最悪 V2 path 別 (Primary / Rescue) の numerical trace から条件追加位置を決定 |
| R2 | Phase 2 fix で in-match scorebar 検出漏れ (false negative) | Phase 3 が gate。1 件 regression で fix 緩和 or 別候補へ切替 (§3.2 → §3.3 loop)。緩和 / 切替の判断点が出たら都度 AskUserQuestion (Iron Law 5) |
| R3 | Phase 4 で V6.2 が `6540 ±5s` に収束しない | #797 を v0.3.x defer、Phase 5' で #803 単独 PR。`docs/v030-baseline-audit.md` の #797 status を update して再調査記録を残す |
| R4 | Codex adversarial-review で additional finding | `(A) PR 内修正優先` (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)。finding 内容次第で AskUserQuestion で (A)/(B)/(C) 振分 |
| R5 | encoding boundary (subprocess / IPC / OS API) で UTF-8 / cp932 / BOM 問題 | 本 PR は detector logic のみ touch で encoding boundary を超えないため低 risk。万一 Phase 1 script の stderr / PNG file name で問題が出たら CLAUDE.md §encoding boundary audit checklist (3 層) で fix |
| R6 | #797 verify を待つ間に他 branch / PR が `_has_scorebar_v2` を touch | Phase 5 PR 作成時に Iron Law 6 Pre-flight Step 0 / 4 (gh pr list --search) で重複検出。並行 PR があれば AskUserQuestion で順序判断 |

## §7. Open decision points (実装中に AskUserQuestion で都度確認)

- Phase 2 で width 上限 `_SCOREBAR_SCAN_MAX_WIDTH_PX` の最終値確定 (#522 baseline の 4K Game DVR 実 span ~615 を通し 1912 を弾く範囲)
- Phase 3 regression 発生時の gate 閾値緩和 or 再調整
- Phase 4 V6.2 収束 / 非収束時の Phase 5 vs 5' 分岐 (`6540 ±5s` 境界の judgment)
- Phase 5 で Codex adversarial-review finding が出た場合の (A)/(B)/(C) 振分
- 実機検証 cadence (Phase 毎依頼 vs まとめ依頼)

## §8. Iron Law 整合

| Iron Law | 本 spec での担保 |
| --- | --- |
| **1** (NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED) | Phase 5 / 5' PR description で #803 (+ #797) 受け入れ条件を逐条引用 + diff/test 引用 (`enforce-acceptance-criteria` skill) |
| **2** (NO BULK OPERATION WITHOUT AskUserQuestion CONFIRMATION) | bulk 操作 (3 件以上の baseline regen / 5 baseline 全件 audit) は本 spec 内で計画済 = 事前確認済。Phase 中に追加 bulk 操作が必要なら AskUserQuestion |
| **3** (NO SCOPE CREEP WITHOUT NEW ISSUE) | #804 は別 session、scope creep しない。Phase 1 debug 中に scope 外 (e.g., V1 reform / audio 再有効化) が必要になったら STOP + 新 issue 起票 (`scope-guard` skill) |
| **4** (NO Closes/Fixes/Resolves KEYWORDS) | Phase 5 / 5' PR 本文・commit メッセージで自動クローズキーワード禁止。merge 後に `/close-issue` skill で実測検証してから `gh issue close` |
| **5** (NO INDEPENDENT JUDGMENT ON AMBIGUOUS POINTS) | §7 Open decision points 全てに AskUserQuestion |
| **6** (NO PR CREATION WITHOUT VERIFIED CHECKS) | §3.5 Phase 5 で Pre-flight Step 0-5 + Codex adversarial-review。touched path が Python (`allaganeye/video/detector.py`) のため `ruff check . / ruff format --check . / pyright / pytest` を全 pass。GPU / 長時間動画 trigger に該当するため Idios に実機検証依頼 (§4.4) |

## §9. Process notes

- TDD: `superpowers:test-driven-development` HARD-GATE 全面採用 (CLAUDE.md §Plugin との関係)。Phase 2 実装は §4.1 unit test を先に書いて fail させた後に開始
- subagent + Codex 直列構成: Phase 4 (V6.2 reintroduce) は重要度高、`subagent-driven-development` + Codex `/codex:review` の 4 stage 直列を採用候補 (Codex 運用 §C5、`docs/l2-workflow.md` §「subagent + Codex 直列構成」)
- Brainstorming: 本 spec 自体が `superpowers:brainstorming` の output。次は `superpowers:writing-plans` で implementation plan に展開する
- resume-plan handoff: Phase 5 / 5' PR 提出時の resume task prompt に `EXECUTOR: self|dispatch (origin=..., generated=...)` ディレクティブを 1 行目に明記 (#722、`docs/l2-workflow.md` §「resume-plan handoff protocol」)
