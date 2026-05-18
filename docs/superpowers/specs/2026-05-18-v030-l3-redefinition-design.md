# v0.3.0 / L3 redefinition design (Input Adaptation + Performance) (2026-05-18)

> **Status**: design (brainstorming 完了、writing-plans 入り口)
> **作成**: 2026-05-18 / session `elegant-euler-9d8bba`
> **目的**: v0.3.0 で取り組む L3 layer の意味を redefine し、関連 doc / issue を整理する方針を確定する設計。旧 L3 (メタデータ化: OCR / 音声認識) は L4 (former L3) として下流に 1 段スライド、新 L3 は「VTuber 配信動画対応 + ミニマップ切抜き + 性能改善」の 3 pillar 構成とする。

## 1. 背景

### 1.1 きっかけ

v0.2.0 / v0.2.1 release (2026-05-13/17) 完了に伴い develop-0.3.0 を cut 済み (commit `7e4f7a6`)。v0.3.0 のスコープ確定が必要なタイミングで、user (Idios) から L3 要件の見直し方針が提示された:

- **現 L3 要件**: メタデータ化 (OCR・音声認識)
- **新 L3 要件**: VTuber 録画対応 / ミニマップ切り抜きサポート / 性能改善

### 1.2 既存の伏線

- **#753** (P2-medium, deferred) が既に「L3 (new) キックオフ: VTuber 配信動画対応 + minimap 切抜き」として 2026-05 中に起票済み。旧 L3 を L4 に繰り下げる提案も本文に明記されている
- **#481** (gyawa VTuber requestor のミニマップ切抜き要望)、**#480** (配信者 scorebar ROI 適応化)、**#479** (Twitch URL 取り込み) が deferred で関連クラスタを形成
- 性能改善関連は **#761** (NVENC 並列 export)、**#762** (multi-vendor 並列 export)、**#765** (NVDEC saturation 計測記録)、**#752** (Portable ZIP file 数削減)、**#576** (detect fps filter 廃止検討)、**#670** (GUI 動画 HTTP server 改善) が deferred で揃っている
- 旧 L3 issue は **#125-#152** に 11 件 (OCR / Whisper / Tesseract / pipeline 設計)、すべて deferred

### 1.3 解決したい問題

1. **L3 の意味の二重化**: docs と #753 で「L3 = OCR/audio」と「L3 = VTuber/minimap」が並存しており、v0.3.0 着手前に正しい定義に統一する必要がある
2. **新 L3 への "性能改善" pillar 追加**: #753 には性能改善が含まれていないが、v0.3.0 の現実的価値 (テスト時間圧縮、export UX 改善) として user から追加要求あり
3. **下流 layer 番号の整合**: 旧 L3 を L4 にスライドさせると旧 L4/L5/L6 の番号も整合させる必要がある
4. **`deferred` 運用の明示化**: 現状 47 open issue すべてが deferred (= active scope 空)。v0.3.0 着手対象を明示的に拾い上げる運用ルールが未確定

## 2. 採用方針 (brainstorming で決定)

| 論点 | 選択肢 | 採用 | 根拠 |
|---|---|---|---|
| **Layer 構造** | (a) 下流 1 段スライド (b) 旧 L3 を L4 に吸収 (c) L3 swap のみ下流維持 | **(a) 下流 1 段スライド** | #753 提案踏襲。全 layer work を保全しつつ意味を明確化。doc 更新負荷はあるが one-time コスト |
| **性能改善 scope** | (i) export 並列 (ii) ZIP size (iii) detect 高速化 (iv) GUI responsiveness | **(i)(ii)(iii)(iv) 全採用** | user 指示 (4 領域すべてを v0.3.0 内で消化) |
| **Label 運用** | (a) 新規 layer label 追加 (b) 既存 label 温存 + title prefix | **(b) 既存 label 温存 + title prefix** | user 指示 (label が乱立しているので新規追加禁止)。`[type] L3:` 形式で識別 |
| **`deferred` 運用** | (a) deferred 外し = 任意の active (b) deferred 外し = v0.3.0 必須対応 | **(b) deferred 外し = v0.3.0 必須対応** | user 指示。v0.3.0 = 新 L3 という強い拘束で scope drift 防止 |
| **実装 phase 順序** | (a) Pillar 順 (1→2→3) (b) Pillar 3 → Pillar 1+2 | **(b) Pillar 3 → Pillar 1+2** | user 指示。Pillar 3 でテスト時間圧縮基盤を先に整備、その後の Phase 2 work を高速化 |
| **Release boundary** | (a) v0.3.0 = 全 Phase 完了 (b) v0.3.0 = Phase 1 のみ + v0.3.x で Phase 2 | **(a) 全 Phase 完了 (暫定)** | spec 段階では Phase 1 完了時点で再判断とし、boundary は未確定で保留 |
| **Spec 粒度** | (a) L3 定義 + scope spec (b) v0.3.0 release roadmap spec (c) Sequential mini-specs | **(a) L3 定義 + scope spec** | 各 pillar の technical detail は実装着手時の別 brainstorm で詰める。本 spec は L3 redefinition + 整理方針に focus |

## 3. 新 L3 定義 (3 pillars)

**L3: 配信形式対応 + 性能改善 (Input Adaptation + Performance)**

- **入力**: L1/L2 で扱う OBS 録画動画 (現状想定) + 拡張形態 (VTuber 配信動画等)
- **処理**:
  - **Pillar 1: VTuber 配信動画対応** — 録画 frame の overlay/webcam/枠装飾を考慮した game capture 領域の検出、scorebar V2 検出の capture 領域適応
  - **Pillar 2: ミニマップ切抜き** — game capture 内のミニマップ ROI 検出 + 切抜き出力 (別 MP4 / frame 連番 / 座標 timeline + 切抜きパラメータのいずれか、実装時 brainstorm で確定)
  - **Pillar 3: 性能改善** — export 並列化 (#761 / #762) + Portable ZIP size 削減 (#752) + detect 高速化 (#576 / #765) + GUI responsiveness (#670)
- **出力**: 既存 metadata.json 構造の拡張 (capture 領域・minimap ROI など、実装時 brainstorm で詳細確定) + 新規 minimap 切抜き artifact

Pillar 1 と Pillar 2 は **game capture 領域検出** が共通基盤となるため、issue 運用上は `l3-input-adapt` 相当のクラスタとして扱う (label は新設しない、title prefix で識別)。

## 4. Layer shift map

```text
Before (current)                          After (new)
─────────────────────────────────────     ─────────────────────────────────────
L1: 試合分割                Released      L1: 試合分割                Released
L2: 配布・統合              In dev        L2: 配布・統合              In dev
L3: メタデータ化 (OCR/audio)              L3 (new): 配信形式対応+性能改善 ← v0.3.0
L4: 価値評価 (ML)                         L4 (former L3): メタデータ化 (OCR/audio)
L5: 自動編集                              L5 (former L4): 価値評価 (ML)
L6: プライバシー (暫定)                   L6 (former L5): 自動編集
                                          L7 (former L6): プライバシー (暫定)
```

### 4.1 文脈保存ルール

- 既存 spec / plan / commit log が "L3" と書いている箇所は **本文不変**。読み手は「文書作成時点での L3」と読む
- 公式 layer table を持つ doc (CLAUDE.md / docs/design-overview.md / docs/cli-spec.md / docs/release-process.md / README.md) のみ新番号で書き直し
- title rename 時は `[type] L4 (former L3): …` 形式で **1 回だけ** rename。以後の rename 連鎖は禁止 (混乱回避)

## 5. Label / Title convention (no new labels)

### 5.1 Title convention

```text
[type] [layer]: 簡潔な要約

例:
[task] L3: VTuber 動画の game capture 領域検出 algorithm 実装
[task] L4 (former L3): Tesseract OCR によるキルログ抽出     ← #125 等
[task] L5 (former L4): LLM プラグインアーキテクチャ設計      ← #131
[risk] L4 (former L3): Whisper PyTorch 依存サイズ            ← #150 等
```

### 5.2 既存 label の使い分け (変更なし、新規追加禁止)

| Label | 意味 | v0.3.0 での運用 |
|---|---|---|
| `deferred` | 現バージョンスコープ外 | **`deferred` 外し = v0.3.0 (新 L3) 必須対応**。v0.3.0 着手 issue は `deferred` を外す。それ以外 (旧 L3 / L4-L7) は `deferred` 継続 |
| `l1-residual` | L1 残課題 | 既存付与を温存、新規付与しない |
| `l2a-gui` / `l2b-installer` / `l2-decision` / `l2-workflow` | L2 サブスコープ | 既存通り |
| `P0`〜`P3` | 優先度 | layer 移動による自動変更なし。v0.3.0 着手対象は個別判断で priority 見直し |
| `task` / `bug` / `enhancement` / `doc` / `question` / `risk` / `refactor` | 種別 | 既存通り |

### 5.3 検索手順

- v0.3.0 着手対象 (新 L3): GitHub issue 検索 `is:open -label:deferred`
- 旧 L3 work (= 新 L4): `is:open in:title "L4 (former L3)"`
- 全 L4 (新規 + former): `is:open in:title L4`

## 6. Issue inclusion mapping

### 6.1 Pillar 1+2 (VTuber + minimap, v0.3.0 必須対応)

| # | 現 title | 操作 |
|---|---|---|
| #753 | [task] L3 (new) キックオフ: VTuber 配信動画対応 + minimap 切抜き | `deferred` 外す。本 issue を v0.3.0 の親 issue にする。child issue は実装着手時に派生 |
| #481 | フロントラインゲーム中のミニマップ映像の切抜き機能サポート | `deferred` 外す。title rename: `[enhancement] L3: minimap 切抜き機能`。priority P3 → P2 |
| #480 | [task] 配信者動画対応: スコアバー ROI の適応化 | `deferred` 外す。title rename: `[task] L3: VTuber 配信動画対応 (scorebar ROI 適応化)`。P3 → P2 |

### 6.2 Pillar 3 (perf, v0.3.0 必須対応)

| # | 現 title | 操作 |
|---|---|---|
| #761 | [task] NVENC 複数 engine の並列 export 基盤化 | `deferred` 外す。title rename: `[task] L3: NVENC 並列 export 基盤化`。P2 維持 |
| #762 | [task] dGPU + iGPU encoder の multi-vendor 並列 export | `deferred` 外す。title rename: `[task] L3: multi-vendor 並列 export (dGPU+iGPU)`。P2 維持 |
| #752 | [task] L2b: Portable ZIP の python/lib ファイル数削減方式の検討 | `deferred` 外す。title rename: `[task] L3: Portable ZIP file 数削減`。P3 → P2 |
| #576 | [refactor] _scan_cpu の fps filter 廃止検討 | `deferred` 外す。title rename: `[refactor] L3: detect fps filter 廃止 (CPU 律速改善)`。P3 → P2 |
| #670 | [task] L2a: 動画 HTTP server 改善 | `deferred` 外す。title rename: `[task] L3: GUI 動画 HTTP server 改善 (responsiveness)`。P3 → P2 |

### 6.3 判断保留 (`deferred` 維持、L3 外)

| # | 理由 |
|---|---|
| #765 | NVDEC saturation 計測 **記録** issue。action なし、参照用 |
| #479 | Twitch URL 取り込みは法的論点 + Web 依存で `CLAUDE.md §設計原則` 再検討要。L3 では扱わず |

### 6.4 下流 layer rename (`deferred` 維持)

| 旧 layer → 新 layer | 対象 issue | 件数 |
|---|---|---|
| L3 → L4 (former L3) | #125, #126, #127, #128, #129, #130, #139, #140, #150, #151, #152 | 11 |
| L4 → L5 (former L4) | #131, #132, #133, #134 (LLM 拡張) | 4 |
| L5 → L6 (former L5) | #135, #136, #137 (highlight / thumbnail / post output) | 3 |
| L6 → L7 (former L6) | #63, #28 (player blur / --precise) | 2 |

合計 20 件 rename。

### 6.5 Iron Law 2 対応 (bulk operation)

上記 rename + `deferred` 外しの操作合計は **20 件超の bulk operation**。実装段階 (writing-plans 後) で `AskUserQuestion` で「サンプル 1 件提示 + 全件 OK / 個別調整 / やめる」3 択を取る。本 spec ではあくまで方針定義に留める。

## 7. Implementation phase 順序

**v0.3.0 = 新 L3 全 pillar 完了 (暫定 assumption — Phase 1 完了時点で再判断)**

ユーザー指示「テスト時間削減のため Pillar 3 優先」を踏まえ、実装 phase 順序:

### 7.1 Phase 1: Pillar 3 (perf) — テスト時間圧縮基盤

| Wave | Issue | 効果 | 並列性 |
|---|---|---|---|
| 1a | #576 `detect fps filter 廃止` | **全 issue のテスト時間に効く基盤改善** (最優先) | 独立 worktree 可 |
| 1b | #761 `NVENC 並列 export` | export 系 regression test 圧縮 | 1a と並列可 |
| 1c | #670 `GUI 動画 HTTP server 改善` | GUI test responsiveness 改善 | 1a と並列可 |
| 1d | #752 `Portable ZIP file 数削減` | distribution test 圧縮、初回 DL UX | 1a と並列可 |
| 1e | #762 `multi-vendor 並列 export` | #761 上に積む、dGPU+iGPU 拡張 | 1b 完了後 |

### 7.2 Phase 2: Pillar 1+2 (input adapt) — Phase 1 完了後

| Wave | Issue | 備考 | 並列性 |
|---|---|---|---|
| 2a | #753 child issue 起票 (game capture 領域検出 algo / scorebar V2 適応 / minimap ROI 検出 等) | #753 を parent として child を派生。各 child は別 brainstorm で詳細設計 | Phase 2 の基盤、先行必須 |
| 2b | #480 `scorebar ROI 適応化` | 2a の game capture 領域検出基盤の上に実装 | 2c と並列可 (game capture 基盤を共有するが output path 異独立) |
| 2c | #481 `minimap 切抜き機能` | 2a の game capture 領域検出を再利用 | 2b と並列可 |

### 7.3 Release boundary (未確定 / 保留)

- 暫定: v0.3.0 = Phase 1 + Phase 2 すべて完了
- 代替案: v0.3.0 = Phase 1 完了で release / v0.3.x or v0.4.0 = Phase 2
- **Phase 1 完了時点で改めて判断** (spec review or 別 brainstorm)

## 8. Regression prevention baseline (Pillar 3 / 2b 用)

### 8.1 Baseline 動画セット (2 系統)

| 系統 | 動画 | 役割 |
|---|---|---|
| **OBS baseline** | ALLAGANEYE_SAMPLE_VIDEO_DIR 配下の代表 OBS 録画 (Phase 1 child issue で N 本選定) | Pillar 3 (perf) の bit-exact 一致検証。「正常検知可能な録画で改修後 regression なし」を保証 |
| **VTuber primary benchmark** | `E:\videos\gyawa_vatos\2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4` (7,554,775,607 bytes, gyawa 提供 2026-05-18) | Phase 2 (input adapt) の primary test target + Pillar 3 robustness 検証 |

### 8.2 Baseline 定義 (項目別)

| 項目 | 内容 | 比較方法 |
|---|---|---|
| **検知結果 baseline** | `metadata.json` の `matches` (`index` / `start_time` / `end_time` / `duration` / `type` / `output_file`) + `gaps` | bit-exact (JSON canonical 比較)。`detected_at` は除外 |
| **書出し結果 baseline (split)** | 試合 MP4 のファイルサイズ + SHA-256 hash | byte-exact (`-c copy` 無劣化分割のため決定論的) |
| **書出し結果 baseline (export GUI)** | encoder/version 依存で byte-exact 不可 | ffprobe メタデータ一致 (長さ・解像度・fps・codec) + 任意 1 フレーム抽出 spot check |

### 8.3 VTuber benchmark の前提条件 (CLAUDE.md §セキュリティ検査 整合)

- 外部 (gyawa, X `@gyawaff14`, #481 で提供約束あり) からの動画
- **Phase 1 着手 (= 検知 baseline 生成) 前に `allaganeye-guard verify` を通す** (PASS exit 0 / 1)
- verify 未完までは agent (Claude) は動画中身を再生・分析しない
- 動画本体は repo に commit しない。**metadata snapshot のみ commit** (`tests/baselines/v0.3.0/`)

### 8.4 VTuber primary benchmark の Ground Truth (user 手動検証済み)

`2772549129-151803977-…-4726a8a519a8.mp4` の試合 5 件 (大体の暗転時刻、user 目視):

| index | start (HH:MM:SS) | end (HH:MM:SS) | start_sec | end_sec | duration |
|---|---|---|---|---|---|
| 1 | 00:23:53 | 00:39:21 | 1433 | 2361 | 15m28s |
| 2 | 00:43:44 | 01:00:35 | 2624 | 3635 | 16m51s |
| 3 | 01:10:53 | 01:27:22 | 4253 | 5242 | 16m29s |
| 4 | 01:34:44 | 01:46:19 | 5684 | 6379 | 11m35s |
| 5 | 01:50:09 | 02:05:37 | 6609 | 7537 | 15m28s |

### 8.5 Phase 別の VTuber benchmark 使い方

| Phase | 比較対象 | 内容 |
|---|---|---|
| Phase 1 (Pillar 3) 着手前 | — | allaganeye-guard verify → 現状 (改修前) で `allaganeye detect` 実行 → 検知結果 snapshot を baseline として commit (現状の不完全検知も含めてそのまま固定) |
| Phase 1 各 Wave 完了時 | **改修前 snapshot baseline** | bit-exact 一致 (perf 改善で検知結果が変わらないこと) |
| Phase 2b 完了時 | **Ground Truth** | 5 試合検出 + `start_time` / `end_time` が ground truth と **±10s 以内** (fps filter offset #575 max ~1.1s + 暗転 grouping 許容) + 検出順序 index 1-5 一致 |
| Phase 2c 完了時 | — | minimap 切抜き artifact が生成されることを確認 (新規 output, baseline 不要) |

### 8.6 Ground Truth metadata snapshot (commit 対象)

`tests/baselines/v0.3.0/vtuber-primary-ground-truth.json`:

```jsonc
{
  "source_file": "2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4",
  "source_size_bytes": 7554775607,
  "source_dir_label": "gyawa_vatos",
  "ground_truth_provider": "user (manual)",
  "ground_truth_provided_at": "2026-05-18",
  "tolerance_sec": 10,
  "matches": [
    {"index": 1, "start_time": 1433, "end_time": 2361, "duration": 928,  "type": "fl_match"},
    {"index": 2, "start_time": 2624, "end_time": 3635, "duration": 1011, "type": "fl_match"},
    {"index": 3, "start_time": 4253, "end_time": 5242, "duration": 989,  "type": "fl_match"},
    {"index": 4, "start_time": 5684, "end_time": 6379, "duration": 695,  "type": "fl_match"},
    {"index": 5, "start_time": 6609, "end_time": 7537, "duration": 928,  "type": "fl_match"}
  ]
}
```

### 8.7 Phase 1 着手前の準備 (新規 child issue, prioritized order)

| Order | Item | Owner | 備考 |
|---|---|---|---|
| (i) | `allaganeye-guard verify` 実行 + PASS 記録 (gyawa 提供 7.5 GB MP4) | human (Idios) | guard tool を別 repo で実行 |
| (ii) | OBS baseline 動画セット選定 (ALLAGANEYE_SAMPLE_VIDEO_DIR から N 本、N は child issue で確定) | agent + human | サイズ・代表性・再現性で選定 |
| (iii) | 全 baseline 動画で改修前検知結果 + split 書出し結果を生成・commit | agent | `tests/baselines/v0.3.0/` 配下 |
| (iv) | baseline 比較スクリプト (`scripts/compare-baseline.py`) を実装 | agent | 各 Wave PR の Self-Test Report で使用 |

(i)-(iv) は Phase 1 Wave 1a (#576 detect 改修) より前に必須。

### 8.8 baseline drift 判定との関係

既存 [`docs/testing-guide.md` §「baseline drift の判定」](../../testing-guide.md) は ffmpeg version 依存 (#575) の context で運用されている。本 spec の baseline は **同一 ffmpeg version での実装変更 regression** を見るため、別軸で運用。docs/testing-guide.md に「v0.3.0 L3 work 用 regression baseline」節を追加 (§9.3 参照)。

## 9. Documents 更新リスト

### 9.1 Primary (layer table を直接書き換え)

| Doc | 更新内容 |
|---|---|
| `CLAUDE.md` | §段階的アーキテクチャ table を新 layer table に書き換え。L3 (new) の 3 pillar を簡潔に記述 |
| `docs/design-overview.md` | §概要・段階的アーキテクチャの ASCII 図を新 layer table に書き換え。L3 (new) の input adapt + perf を新節で詳述、旧 L3 (= 新 L4) は L4 節に移動 |
| `docs/release-process.md` | L3/L4/L5/L6 の roadmap 言及を新番号に置換。v0.3.0 = 新 L3 release boundary 方針 (§7.3 未確定分) は別途決定したら反映 |
| `README.md` | **§ロードマップ section (L43-L53) を削除**。layer 詳細は CLAUDE.md / docs/design-overview.md に委譲済み (§ドキュメント で design-overview.md link 案内済み) |

### 9.2 Secondary (incidental な L3 言及、文脈で書き換え)

| Doc | 更新内容 |
|---|---|
| `docs/cli-spec.md` | L3 関連の言及があれば「旧 L3 → L4 (former L3)」の文脈注釈または番号置換 |
| `docs/l2-workflow.md` | L3 言及があれば同様に置換 |
| `docs/issue-policy.md` | §2 スコープラベル表に「**新 L3 work は新規 label 追加せず、title prefix `[type] L3:` で識別**」「**`deferred` 外し = v0.3.0 着手対象**」の運用ルールを明記 |
| `docs/reference-videos.md` | L3 言及があれば文脈置換 |
| `docs/ui-interaction-spec.md` | L3 言及があれば文脈置換 (incidental の可能性高い) |

### 9.3 Testing 関連 (§8 baseline 規定の反映)

| Doc | 更新内容 |
|---|---|
| `docs/testing-guide.md` | 新節「v0.3.0 L3 work 用 regression baseline」を追加。OBS baseline + VTuber primary benchmark + ground truth 規定 + `tests/baselines/v0.3.0/` 配置規約 |

### 9.4 Specs / Plans (時系列文脈保存、原則不変)

| 場所 | 方針 |
|---|---|
| `docs/superpowers/specs/*.md` (既存 28 本) | **本文不変**。読み手は文書作成時点での L3 = 旧 L3 = 新 L4 と読む |
| `docs/superpowers/plans/*.md` (既存) | 同上、本文不変 |

### 9.5 新規作成ファイル

| ファイル | 内容 | 担当 |
|---|---|---|
| `docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md` (本 file) | brainstorming 結果の design | 本セッション |
| `docs/superpowers/plans/2026-05-18-v030-l3-redefinition-plan.md` | 本 spec を実行するための implementation plan | writing-plans skill |
| `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` | Phase 1 child issue (iii) で生成 |
| `tests/baselines/v0.3.0/<OBS-baseline-N>.json` | 同上 |
| `scripts/compare-baseline.py` | Phase 1 child issue (iv) で実装 |

## 10. Out of scope (本 spec が扱わないもの)

- **各 pillar の technical detail**: VTuber 動画 game capture 領域検出 algorithm / minimap ROI 検出 algorithm / NVENC 並列 export 実装方式 / Portable ZIP file 削減方式 etc. — 各 child issue 着手時に別 brainstorm で詳細設計
- **VTuber 動画の中身分析**: allaganeye-guard verify 通過前は動画 frame の解析 / 視覚的 inspection は行わない
- **旧 L3 work (OCR/Whisper) の再評価**: L4 (former L3) として deferred 継続。v0.3.0 で扱わない
- **Twitch URL 取り込み (#479)**: 法的論点 + Web 依存で `CLAUDE.md §設計原則` 要再検討。v0.3.0 では扱わない

## 11. Open questions (spec review / 後続 brainstorm で解決)

1. **Release boundary**: v0.3.0 = 全 Phase 完了 vs Phase 1 完了 (§7.3)。Phase 1 完了時点で再判断
2. **OBS baseline 動画セットの N 本**: Phase 1 着手時の child issue (§8.7 (ii)) で確定
3. **minimap 切抜き出力形式**: 別 MP4 / frame 連番 / 座標 timeline + 切抜きパラメータのいずれか。Phase 2c 着手時の child issue で確定
4. **game capture 領域検出 algorithm**: 黒帯検出 / 暗転 frame 重なり / template matching のいずれか or 複合。Phase 2a child issue で実験ベース確定

## 12. 参照

- 現状 layer 定義: [CLAUDE.md §段階的アーキテクチャ](../../../CLAUDE.md) / [docs/design-overview.md](../../design-overview.md)
- 関連 issue:
  - [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753) (L3 new kickoff)
  - [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) (minimap)
  - [#480](https://github.com/Idios/kobutachan-allaganeye/issues/480) (scorebar ROI)
  - [#761](https://github.com/Idios/kobutachan-allaganeye/issues/761) (NVENC parallel)
  - [#762](https://github.com/Idios/kobutachan-allaganeye/issues/762) (multi-vendor parallel)
  - [#752](https://github.com/Idios/kobutachan-allaganeye/issues/752) (ZIP size)
  - [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576) (fps filter)
  - [#670](https://github.com/Idios/kobutachan-allaganeye/issues/670) (HTTP server)
  - [#765](https://github.com/Idios/kobutachan-allaganeye/issues/765) (NVDEC saturation)
- セキュリティ規約: [CLAUDE.md §セキュリティ検査](../../../CLAUDE.md) / [docs/guard-integration.md](../../guard-integration.md)
- baseline drift: [docs/testing-guide.md §baseline drift の判定](../../testing-guide.md)
