# L3 Phase 0: 検出 subsystem 現状 map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 検出 subsystem (detector.py / scorebar.py / capture_region.py / gpu_detector.py / presence.py) の現状を「git 考古学 + layer ごとの load-bearing / cruft / 有害 判定 + 相互作用 (特に `_drop_post_match_trailing` × `_has_scorebar_v2` × 新 membership の coupling) 」として 1 ドキュメントに集約し、Phase 1+ の再アーキ実装の前提を裏付ける。

**Architecture:** production コード変更ゼロ。新規ドキュメント `docs/detection-map.md` を作成し、既存 docs (`video-processing.md` / `scorebar-detection-design.md` / `system-architecture.md`) と**重複させず相互リンク**する。本 plan の成果物はドキュメント 1 枚 + spec への参照追記のみ。検証は「主張がコード/git の実体と一致するか」のセルフ突合で行う (動画実行不要)。

**Tech Stack:** Markdown (markdownlint CI 準拠) / git log・git blame (考古学) / Read・Grep (コード突合)。

---

## なぜ Phase 0 が独立成果物か

spec ([2026-05-31-l3-detection-rearchitecture-two-signal-design.md](../specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md)) §8 で Phase 0 を独立 phase に定めた。理由:

- Codex adversarial review (2026-05-30) が **`_drop_post_match_trailing` は v2 を直接プローブする hidden 第 2 分類器**であり、新 membership 信号と競合すると指摘 (spec §4 Codex #6 / R4)。この coupling を把握せずに Phase 1+ に入ると、prior pivot (presence 全置換) と同じ「未検証前提で実装 → 破綻」を繰り返す。
- 検出 subsystem は 7 年分 (#39〜#811、detector.py だけで 42 commit) の対症修正が層状に積もっており、どの層が **load-bearing (壊すと回帰)** / **cruft (惰性で残存)** / **有害 (能動的にバグの温床)** かが未整理。Phase 1 の「OBS 構造保持・分類器のみ差し替え」が安全かは、この棚卸し結果に依存する。
- 成果物がドキュメント 1 枚なので、production リスクゼロで単体完結する。

## 既存 docs との境界 (重複回避 — memory: PR #783 教訓)

新 doc を書く前に既存 doc を必ず確認すること。**以下は既存 doc が持つので新 doc では繰り返さずリンクする**:

| 既存 doc | 既にカバーしている内容 | 新 doc での扱い |
| --- | --- | --- |
| `docs/video-processing.md` | detect/probe/split の **現行アルゴリズム解説** + 設計経緯 (課題 1-7) | アルゴリズム詳細はリンク。新 doc は「layer 判定」を足す |
| `docs/scorebar-detection-design.md` | `_has_scorebar` v1 / v2 (#307,#522) の **採用根拠** | v2 内部はリンク。新 doc は「v2 が load-bearing か」の判定を足す |
| `docs/system-architecture.md` | コンポーネント構成・データフロー (CLI/GUI) | リンクのみ |

新 doc `docs/detection-map.md` の固有価値 = **(a) layer 別 keep/cruft/harmful 判定、(b) git 考古学による「なぜ追加されたか」、(c) 再アーキで触る層の coupling 図**。これらは既存 doc にない。

---

## File Structure

- **Create:** `docs/detection-map.md` — Phase 0 の成果物。検出 subsystem の現状 map。
- **Modify:** `docs/superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md` — §8 Phase 0 行に成果物 doc へのリンクを追記、§13 参照に追加。
- **Modify:** `docs/video-processing.md` — 既存 doc 側から新 map への相互リンクを 1 行追加 (双方向リンクで発見性確保)。

各タスクは独立した追記で、順に積み上げる。動画実行・production コード変更はない。

---

### Task 1: detection-map.md の骨格 + layer インベントリ

検出 subsystem の全 layer を列挙し、責務 + 主要シンボル + 既存 doc リンクの表を作る。判定列は後続 Task で埋める (この Task では「対象 layer の網羅」が完了基準)。

**Files:**

- Create: `docs/detection-map.md`
- Reference (読むだけ): `allaganeye/video/detector.py`, `allaganeye/video/scorebar.py`, `allaganeye/video/capture_region.py`, `allaganeye/video/gpu_detector.py`, `allaganeye/video/presence.py`

- [ ] **Step 1: 対象シンボルを Grep で網羅確認**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
grep -nE '^def |^class |^_[A-Z_0-9]+ =' allaganeye/video/detector.py allaganeye/video/scorebar.py allaganeye/video/capture_region.py
```

Expected: detector.py は `detect_match_boundaries` / `_scan_cpu` / `_group_blackout_regions` / `_expand_regions_with_transitions` / `_refine_blackout_regions` / `_has_scorebar_v2` / `_has_scorebar` / `filter`系 / `_filter_and_extract_segments` / `_drop_post_match_trailing` 等、scorebar.py は `classify_blackout` / `_is_static_from_frames` / `_merge_boundary_pairs` / `filter_blackouts_with_scorebar` / `_has_nearby_fanfare_hit`、capture_region.py は `localize_scorebar` / `detect_region_*` が出力される。この一覧が map の layer 母集合。

- [ ] **Step 2: detection-map.md の骨格を書く**

`docs/detection-map.md` を以下の内容で作成 (layer インベントリ表の判定列は `(Task 3 で判定)` プレースホルダではなく、空欄セル `—` を置き Task 3 で置換する。プレースホルダ文字列は残さない):

```markdown
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

(Task 2 で記入)

## 4. coupling 図: `_drop_post_match_trailing` × v2 × membership

(Task 4 で記入)

## 5. 再アーキ (spec) への含意

(Task 5 で記入)
```

- [ ] **Step 3: layer インベントリの網羅を Step 1 出力と突合**

Step 1 の Grep 出力に出た主要シンボルが Step 2 の表に漏れなく載っているか目視確認。漏れがあれば表に行を追加。`localize_present_at` 等 presence.py のシンボルは §2 表の脚注に「presence.py は Phase 1 spec の資産、§5 で扱う」と 1 行で言及。

- [ ] **Step 4: markdownlint**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: `Summary: 0 error(s)`。エラーが出たら `docs/markdownlint-guide.md` の fix recipe に従う (table の `|` 整形 / fenced code に language 指定 / 見出し前後の空行)。

- [ ] **Step 5: Commit**

```bash
git add docs/detection-map.md
git commit -m "docs(l3): 検出 subsystem map 骨格 + layer インベントリ (Phase 0 Task 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: git 考古学セクション (§3) を記入

各 layer が「どの課題に対する対症修正か」を git log / docstring から復元する。spec の主張 (積層した対症修正) を実証する。

**Files:**

- Modify: `docs/detection-map.md` (§3 を置換)
- Reference: git log, 各 module の docstring

- [ ] **Step 1: 各 layer 導入 commit の課題を抽出**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
git log --oneline -- allaganeye/video/detector.py | grep -iE '#71|#77|#107|#108|#109|#111|#201|#203|#288|#307|#522|#797|#806|#576|#575'
git log --oneline -- allaganeye/video/scorebar.py | head -15
```

Expected: 課題 1-7 (リスポーン暗転 #60 / パターンB境界欠落 #71 / パターンC #77 / キャラダウン #107 / 非FL #108-109 / 二重境界 / 静止画面誤分類 #201,#203) と scorebar v2 (#307,#522) / trailing drop (#797,#806) の commit が並ぶ。詳細経緯は `docs/video-processing.md` §設計経緯 (課題 1-7) に既出 → リンクする。

- [ ] **Step 2: §3 を時系列の「対症修正の地層」として記入**

`docs/detection-map.md` §3 のプレースホルダ行 `(Task 2 で記入)` を以下構造で置換 (各 entry は「契機の課題 → 追加された layer → それが生んだ新たな脆さ/制約」の 3 点。詳細解説は video-processing.md にリンクし重複させない):

```markdown
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
```

- [ ] **Step 3: markdownlint**

Run: `bash scripts/check-markdownlint.sh`
Expected: `Summary: 0 error(s)`

- [ ] **Step 4: Commit**

```bash
git add docs/detection-map.md
git commit -m "docs(l3): 検出 layer の git 考古学セクション (Phase 0 Task 2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: layer 判定列 (§2) を load-bearing/cruft/harmful で埋める

インベントリ表の判定列を、コード実体 + spec の決定を根拠に確定する。再アーキで「保持必須 / 整理候補 / 見直し対象」が一目で分かる状態にする。

**Files:**

- Modify: `docs/detection-map.md` (§2 表の判定列 `—` を置換)
- Reference: spec §3.5 (duration filter backstop の検証済み事実), §4 (Codex findings)

- [ ] **Step 1: 判定の根拠をコードで再確認**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
grep -n "min_match_duration" allaganeye/video/detector.py | head
grep -n "_has_scorebar_v2(" allaganeye/video/detector.py allaganeye/video/scorebar.py
```

Expected: `min_match_duration` は `detect_match_boundaries` 引数 (default 300) と `_filter_and_extract_segments` / `_drop_post_match_trailing` で使用。`_has_scorebar_v2` は scorebar.py の `_probe_scorebar_context` と detector.py の `_drop_post_match_trailing:1977` から呼ばれる (= v2 の 2 つの consumer)。

- [ ] **Step 2: §2 表の判定列を確定して置換**

各 `—` を以下の判定で置換 (根拠を §2 直後に脚注として 1 行ずつ付す):

- brightness Pass1/Pass2 (`_scan_cpu` / `_refine_blackout_regions` / `_group_blackout_regions`): **load-bearing** — spec §3.1① boundary 主軸、A.3 で OBS 秒未満精度を実証。
- `_expand_regions_with_transitions`: **load-bearing (但し VTuber で要調整)** — OBS では必須、VTuber crop で過剰 merge (spec P5 / re-plan #809 Wave F)。
- `_has_scorebar_v2`: **load-bearing (provisional)** — OBS の高特異度ガード (Codex #3)。spec Q3 で localize に置換予定だが parity 実証まで authoritative 温存。
- `_has_scorebar` (v1): **cruft** — opencv 不在時 fallback のみ。実運用 opencv 同梱で経路ほぼ死。
- `filter_blackouts_with_scorebar` / `classify_blackout`: **load-bearing (再編対象)** — 分類 orchestration。primitive を localize+motion に差し替え (spec §5)。
- `_is_static_from_frames`: **load-bearing (昇格対象・要検証)** — Q5 で分類補助に昇格予定だが Codex #1 で primary 化未検証 → **判定保留**寄り。
- `_merge_boundary_pairs`: **load-bearing** — 二重境界対策。流用。
- audio Fanfare promotion: **load-bearing (FP 余地あり)** — #288 救済。
- `_filter_and_extract_segments` (duration filter): **load-bearing (backstop)** — spec §3.5 でリザルト除去の真の backstop と実証。
- `_drop_post_match_trailing`: **harmful** — 不可逆削除 × 弱い否定信号 (#805) + v2 hidden coupling (Codex #6)。
- GPU Pass1: **load-bearing** — `--gpu` 経路。CPU と parity 必須 (Codex #8)。
- legacy fps filter path: **cruft (撤去予定)** — #576 で新 path 既定化、env var rollback のみ。v0.3.x で削除予定。
- `localize_scorebar`: **load-bearing (新基盤)** — 再アーキの分類器核 + VTuber anchor。
- `detect_region_*` (S1/S3): **判定保留 (脆い)** — re-plan R6。spec は scorebar 帯 anchor を主軸にし S3 を補助降格。

- [ ] **Step 3: markdownlint**

Run: `bash scripts/check-markdownlint.sh`
Expected: `Summary: 0 error(s)`

- [ ] **Step 4: Commit**

```bash
git add docs/detection-map.md
git commit -m "docs(l3): layer の load-bearing/cruft/harmful 判定 (Phase 0 Task 3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: coupling 図 (§4) — `_drop_post_match_trailing` × v2 × membership

Codex #6 が指摘した hidden coupling を、データフローと「再アーキで何が壊れるか」で図示する。これが Phase 0 の最重要成果。

**Files:**

- Modify: `docs/detection-map.md` (§4 を置換)
- Reference: `allaganeye/video/detector.py:1901-1993` (`_drop_post_match_trailing` 全体), spec §3.4 / R4

- [ ] **Step 1: trailing drop の v2 依存を行レベルで確認**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
sed -n '1973,1993p' allaganeye/video/detector.py
```

Expected: `_has_scorebar_v2(_probe_frame_rgb_hires(video_path, probe_at)) is not False` で「scorebar hit か probe 失敗なら keep / 全 probe が definite miss なら drop (`segments[:-1]`)」。= **v2 の False 判定が不可逆削除のトリガ**。

- [ ] **Step 2: §4 を coupling 図 + 競合シナリオで記入**

`(Task 4 で記入)` を以下で置換:

```markdown
## 4. coupling 図: `_drop_post_match_trailing` × v2 × membership

`_drop_post_match_trailing` (detector.py:1901) は segment 抽出の **後段**で、最終 segment が
post-match trailing (lobby/city) かを **v2 scorebar の不在を根拠に不可逆削除**する。

\```text
segments 抽出 (_filter_and_extract_segments)
        │
        ▼
最終 segment が type=unknown かつ end≈動画末尾 かつ len>=2 か?
        │ yes
        ▼
早期 candidate-match 窓を _TRAILING_PROBE_STRIDE で v2 プローブ
        │
        ├─ どれか True / None (probe 失敗) → keep (safe side)
        └─ 全て False (definite miss)      → segments[:-1]  ← 不可逆削除
\```

### 競合シナリオ (Codex #6 / spec R4)

| 変更 | trailing drop への影響 |
| --- | --- |
| v2 を localize に置換 (Q3) | trailing drop は v2 を直接呼ぶ (detector.py:1977)。置換すると **第 2 の分類器が暗黙に挙動変化**。localize はリザルト 91% present → trailing を「試合あり」と誤判定し drop し損ねる、逆に VTuber では本物 trailing を切る (R3) |
| membership 信号導入 (Q4) | membership は segment 抽出の前段。trailing drop は後段で独立に再判定するため、**2 つの membership 判断が二重化** |
| #805 非破壊化 | 不可逆削除 → フラグ方式にすると trailing drop の出力契約が変わる |

### 結論 (Phase 1+ への制約)

- spec §3.4 の通り、**Phase 1-3 は v2 を温存**し trailing drop を現状のまま据え置く。
- membership 統一と #805 非破壊化は **Phase 4 cutover 以降の別 phase**で、trailing drop を新 membership と同じ根拠に統一するか shadow 無効化してから扱う。
- Phase 2 で localize を shadow 並走させる際、**trailing drop は v2 (authoritative) のまま**にする (localize を trailing drop に配線しない)。
```

注: 上記の coupling 図は実ファイルでは三連バッククォートの fenced code (language `text`) として書く。

- [ ] **Step 3: markdownlint**

Run: `bash scripts/check-markdownlint.sh`
Expected: `Summary: 0 error(s)`。fenced code の language 指定 (MD040) と図中の `|` 漏れに注意。

- [ ] **Step 4: Commit**

```bash
git add docs/detection-map.md
git commit -m "docs(l3): trailing-drop × v2 × membership coupling 図 (Phase 0 Task 4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: §5 含意 + presence.py 資産整理 + 相互リンク + spec 追記

map の結論を spec の Phase 1+ 実装に接続し、presence.py 資産 (spec §10) の現状を記録し、既存 doc と双方向リンクする。

**Files:**

- Modify: `docs/detection-map.md` (§5 を置換)
- Modify: `docs/superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md` (§8 / §13)
- Modify: `docs/video-processing.md` (相互リンク 1 行)

- [ ] **Step 1: §5 含意を記入**

`(Task 5 で記入)` を以下で置換:

```markdown
## 5. 再アーキ (spec) への含意

### 5.1 Phase 1 で保持必須 (load-bearing)

- brightness Pass1/Pass2、duration filter (backstop)、`_merge_boundary_pairs` は OBS で bit-exact 維持。
- `_has_scorebar_v2` は authoritative 温存 (Q3 provisional)。

### 5.2 Phase 1 で触る (再編)

- `classify_blackout` の検出 primitive を localize+motion 化 (shadow 並走、§2 判定参照)。
- `_is_static_from_frames` を band-anchor 化 (絶対 ROI → localize bbox、spec §5)。OBS は絶対 ROI 縮退。

### 5.3 触ってはいけない (Phase 4 以降)

- `_drop_post_match_trailing` (harmful だが §4 の通り coupling 故に Phase 1-3 据え置き)。
- legacy fps filter path (cruft、別 issue で撤去)。

### 5.4 presence.py 資産 (spec §10)

- `compare_segments` / GT 突合ハーネス → 検証インフラとして存続。
- `localize_present_at` → Stage 2 分類で再利用。
- `scan_presence` / `segment_presence` / `detect_matches_by_presence` → VTuber + 診断専用に降格 (OBS production 経路では使わない)。
- branch `claude/l3-p2-region-detection` は Phase 1-2 実装で継続使用。
```

- [ ] **Step 2: spec §8 Phase 0 行と §13 参照に map へのリンク追記**

`docs/superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md` の §8 Phase 0 行末尾と §13 参照リストに `docs/detection-map.md` リンクを追加。

§8 の Phase 0 行 (`| **0** | 検出 subsystem の git 考古学...`) の「内容」セル末尾に追記:

```text
。成果物 = [docs/detection-map.md](../../detection-map.md)
```

§13 参照リストの現行コード行の直後に新規 bullet:

```markdown
- Phase 0 成果物: [docs/detection-map.md](../../detection-map.md) (layer 別 keep/cruft/harmful 判定 + git 考古学 + coupling 図)
```

- [ ] **Step 3: video-processing.md に相互リンク追加**

`docs/video-processing.md` の冒頭 `## 概要` セクション末尾に 1 行追加 (検出 layer の棚卸し map への導線):

```markdown
> 検出 subsystem の layer 別 load-bearing/cruft/harmful 判定・git 考古学・再アーキ coupling は [detection-map.md](detection-map.md) (L3 Phase 0) を参照。
```

- [ ] **Step 4: markdownlint + リンク到達性確認**

Run:

```bash
bash scripts/check-markdownlint.sh
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
test -f docs/detection-map.md && echo "map exists"
grep -c "detection-map" docs/video-processing.md docs/superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md
```

Expected: `Summary: 0 error(s)` / `map exists` / video-processing.md と spec の双方に detection-map 参照が 1 件以上。相対リンク `../../detection-map.md` が specs/ → docs/ に到達するか確認 (specs/ は docs/superpowers/specs/ なので `../../` で docs/ 直下)。

- [ ] **Step 5: Commit**

```bash
git add docs/detection-map.md docs/video-processing.md docs/superpowers/specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md
git commit -m "docs(l3): map 含意 + presence 資産整理 + 相互リンク (Phase 0 Task 5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 受け入れ条件 (Phase 0 完了基準)

- [ ] `docs/detection-map.md` が存在し、§1 凡例 / §2 layer インベントリ (判定列充填) / §3 git 考古学 / §4 coupling 図 / §5 含意 の 5 節を持つ。
- [ ] §2 の全 layer に load-bearing / cruft / harmful / 判定保留 のいずれかが付き、根拠脚注がある。
- [ ] §4 に `_drop_post_match_trailing` × v2 × membership の coupling 図 + 競合シナリオ表 + Phase 1+ 制約 (v2 温存) が記載される。
- [ ] 既存 doc (video-processing.md / scorebar-detection-design.md) と**重複せず相互リンク**している (memory: PR #783 教訓)。
- [ ] spec §8/§13 から map へのリンクがある (双方向)。
- [ ] markdownlint `Summary: 0 error(s)`。
- [ ] production コード (`allaganeye/**`) の変更が 0 (docs のみ)。

## 検証 (動画不要)

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
git diff --name-only develop-0.3.0...HEAD | grep -vE '^docs/' && echo "WARN: non-docs changed" || echo "OK: docs-only"
bash scripts/check-markdownlint.sh | tail -1
grep -c '^## ' docs/detection-map.md   # expect 5
```

Expected: `OK: docs-only` / `Summary: 0 error(s)` / `5`。

## このプランがやらないこと

- production コード変更 (Phase 1 以降)。
- 動画実機実行 / harness 実行 (Phase 2+)。
- issue 起票 (Iron Law 2、spec §11 の通り起票時に別途 AskUserQuestion)。
- v2 retire や trailing drop 改変 (map は「触らない」と結論づけるのが仕事)。
