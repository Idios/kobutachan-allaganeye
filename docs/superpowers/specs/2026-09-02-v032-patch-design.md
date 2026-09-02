# v0.3.2 patch release 設計書 — v0.3.1 retrospective + deferred 50 件の吸収

- **status**: Track 0 (計画時点)
- **作成日**: 2026-09-02
- **最終更新**: 2026-09-02
- **対象リリース**: v0.3.2 (patch)
- **base ブランチ**: `develop-0.3.2`
- **Track 構造**: [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- **前例**: [2026-08-05-v031-patch-design.md](2026-08-05-v031-patch-design.md) (v0.3.1 Track 0)

## 1. スコープ (計画時点)

v0.3.2 のスコープは以下の 2 系統で確定する。

### 1.1 deferred (a) 吸収候補

v0.3.1 中に Idios が「v0.3.2 へ送る」と判断した 4 件。

| issue | 内容 |
| --- | --- |
| #975 | [bug] checker に残る近似の乖離 8 形 (fail-closed の射程外) |
| #997 | [task] areamap GT の pin 済み case に assert する test があることを強制していない |
| #998 | [task] 検証依存セット台帳と E: 原本の乖離 (手動分割 MP4 7 本が欠落) |
| #1008 | [task] screenshot-freshness: コメントのみの変更でも撮り直しを要求される粒度 + 撮り直し手順が ERR_MODULE_NOT_FOUND で動かない |

### 1.2 依存更新 (Dependabot)

v0.3.1 リリース後に Dependabot が発行した 10 件のうち、9 件を吸収、1 件を over-bump で close した。

**吸収 9 件** (base を `develop-0.3.2` へ retarget 済み):

| PR | 依存 | 種別 |
| --- | --- | --- |
| #1028 | `browserslist` 4.28.4 → 4.28.8 | セキュリティ修正 (high アラート #34 の解消) |
| #1025 | `react-dom` / `@types/react-dom` | 定期 (patch) |
| #1024 | `ruff` 0.16.1 → 0.16.5 | 定期 (patch) |
| #1023 | `@tauri-apps/plugin-dialog` 2.7.1 → 2.7.2 | 定期 (patch) |
| #1022 | `datamodel-code-generator` 0.72.1 → 0.76.0 | 定期 (minor) |
| #1021 | `numpy` 2.4.4 → 2.4.6 | 定期 (patch) |
| #1019 | `actions/upload-artifact` 4 → 7 | メジャー (CI 検証) |
| #1018 | `actions/setup-node` 4 → 7 | メジャー (CI 検証) |
| #1017 | `actions/github-script` 7 → 9 | メジャー (互換確認済み) |

**close 1 件**:

| PR | 依存 | 理由 |
| --- | --- | --- |
| #1020 | `fast-uri` 3.1.5 → 4.1.3 | over-bump。`ajv@8.18.0` の依存制約 `fast-uri: ^3.0.1` と衝突 (4.x は範囲外)。現行 3.1.5 は既に patch 済み |

## 2. §deferred 全件検証結果 (`/release` Step 0c)

2026-09-02 (計画時点) に `gh issue list --state open --label deferred` で取得した **50 件** の分類。

| 分類 | 件数 |
| --- | --- |
| (a) 次 release 吸収 | 4 |
| (b) deferred 継続 | 46 |
| (c) close | 0 |

### 2.1 (a) 次 release 吸収 (4 件)

| issue # | title | 判断理由 |
| --- | --- | --- |
| #975 | [bug] checker に残る近似の乖離 8 形 (fail-closed の射程外) | v0.3.1 中に Idios が v0.3.2 へ送ると判断 |
| #997 | [task] areamap GT の pin 済み case に assert する test があることを強制していない | 同上 |
| #998 | [task] 検証依存セット台帳と E: 原本の乖離 (手動分割 MP4 7 本が欠落) | 同上。v0.3.1 実機ゲートで skip 6 件の原因 |
| #1008 | [task] screenshot-freshness: コメントのみの変更でも撮り直しを要求される粒度 + 撮り直し手順が ERR_MODULE_NOT_FOUND で動かない | 同上。手順修正は配置の判断を伴う (issue コメントに実測あり) |

### 2.2 (b) deferred 継続 (46 件)

| issue # | title | 分類 |
| --- | --- | --- |
| #968 | [task] GUI が書き出し先の絶対パスを受け取っておらず、#930 のパス可視化が CLI 限定になっている | (b) deferred 継続 |
| #964 | [bug] GUI の name-pattern プレビューが sandbox 検証を持たず、exit 5 で拒否される名前をそれらしく表示する | (b) deferred 継続 |
| #957 | [task] typer 0.26+ (click vendoring) への移行判断と CLI 内部 API 依存の解消 | (b) deferred 継続 |
| #953 | [question] GUI minimap: 実行中の画面離脱で進捗表示を失う扱いの決着 | (b) deferred 継続 |
| #951 | [task] cv2 5.x 移行の判断と baseline 再取得 | (b) deferred 継続 |
| #937 | [bug] export/minimap 出力パスの同一性判定に残る 4 経路 (hardlink / 8.3 / macOS / 予約デバイス名) | (b) deferred 継続 |
| #933 | v0.3.0 doc 監査でスコープ外に置いた項目 (CI スキャナ / audit 閾値 / doc 陳腐化 9 件) | (b) deferred 継続 |
| #925 | [task] masked 録画の baseline 回帰ゲートを追加 (現状は不変性確認のみで正しさ未検証) | (b) deferred 継続 |
| #921 | [task] --vtuber: 試合間 gap 約 70 秒未満での結合を解消する | (b) deferred 継続 |
| #882 | [task] 検証データ保全の恒久策 (第 3 系統) 追加 | (b) deferred 継続 |
| #867 | [task] L3: #809 audit 追記 AC 残 2 点の移設 (cache 感度 + red tests) | (b) deferred 継続 |
| #866 | [task] L3: two-signal 再アーキ Phase 3-4 (VTuber 検証+cutover) 追跡 | (b) deferred 継続 |
| #861 | [task] L3: QSV/AMF decode hwaccel の扱い確定 (#762 後継) | (b) deferred 継続 |
| #809 | [task] L3: Pass 1 暗転検知の game 領域輝度適応 (VTuber 本番 wiring) | (b) deferred 継続 |
| #753 | [task] L3: VTuber + minimap キックオフ (parent issue) | (b) deferred 継続 |
| #742 | [refactor] 5 spawn site を tauri-plugin-shell::Command に移行 (#727 派生 (2), post-v0.2.0) | (b) deferred 継続 |
| #671 | [task] L2a: E2E test 自動化 feasibility 検討 (#484派生) | (b) deferred 継続 |
| #670 | [task] L3: GUI 動画 HTTP server 改善 (responsiveness) | (b) deferred 継続 |
| #518 | [question] note -> warnings: Warning[] 構造化 (将来検討) | (b) deferred 継続 |
| #480 | [task] L3: VTuber scorebar 局在化(P1) + ROI 適応分類(P4) (re-plan #753、旧: scorebar ROI 適応化) | (b) deferred 継続 |
| #479 | [task] ユーザー要望: Twitch アーカイブ URL からの試合分割取り込み | (b) deferred 継続 |
| #432 | [task] 他プロセス使用中による Permission denied 系問題の全体見直し | (b) deferred 継続 |
| #412 | [refactor] PR #323 refinement 残存長 segment の warning を機械的に追跡する | (b) deferred 継続 |
| #373 | [refactor] metadata.json に末尾打ち切り情報を残す | (b) deferred 継続 |
| #326 | [task] ハイブリッド skill 方式を idios-claudecode-tools テンプレートに反映 | (b) deferred 継続 |
| #152 | [risk] L4 (former L3): Tesseract 日本語言語パックの別途インストール要件 | (b) deferred 継続 |
| #151 | [risk] L4 (former L3): OBS 録画に音声トラックが存在しない場合の処理 | (b) deferred 継続 |
| #150 | [risk] L4 (former L3): openai-whisper の PyTorch 依存によるインストールサイズ肥大化 | (b) deferred 継続 |
| #140 | [risk] L4-L6 (former L3-L5): 全体処理時間の見積もりとユーザー体験 | (b) deferred 継続 |
| #139 | [question] L4-L6 (former L3-L5) の end-to-end パイプライン設計 | (b) deferred 継続 |
| #137 | [task] L6 (former L5): 投稿提案の出力設計 | (b) deferred 継続 |
| #136 | [task] L6 (former L5): サムネイル自動生成 | (b) deferred 継続 |
| #135 | [task] L6 (former L5): ハイライトクリップ自動切り出し | (b) deferred 継続 |
| #134 | [task] L5 (former L4) [LLM拡張]: API キー管理とセキュリティ | (b) deferred 継続 |
| #133 | [risk] L5 (former L4) [LLM拡張]: API コスト管理 — LLM 呼び出しの費用見積もり | (b) deferred 継続 |
| #132 | [task] L5 (former L4) [LLM拡張]: 投稿価値の評価基準定義 | (b) deferred 継続 |
| #131 | [task] L5 (former L4) [LLM拡張]: LLM プラグインアーキテクチャの設計 | (b) deferred 継続 |
| #130 | [task] L4 (former L3): 外部依存の追加と環境構築手順の整備 | (b) deferred 継続 |
| #129 | [risk] L4 (former L3): Whisper ローカル実行の処理時間・リソース消費 | (b) deferred 継続 |
| #128 | [risk] L4 (former L3): OCR 精度 — ゲーム独自フォントの認識リスク | (b) deferred 継続 |
| #127 | [task] L4 (former L3): イベントデータ出力フォーマットの設計 | (b) deferred 継続 |
| #126 | [task] L4 (former L3): Whisper による音声認識・SE 検出 | (b) deferred 継続 |
| #125 | [task] L4 (former L3): Tesseract OCR によるキルログ抽出 | (b) deferred 継続 |
| #63 | [task] L7 (former L6): プレイヤー名ぼかし機能の検討・実装 | (b) deferred 継続 |
| #32 | [task] Windows/Linux クロスプラットフォームテスト基盤の構築 | (b) deferred 継続 |
| #28 | [task] L7 (former L6): --precise フラグ（再エンコード分割モード）の追加 | (b) deferred 継続 |

## 3. 関連リンク

- [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- [`.claude/skills/release/SKILL.md`](../../../.claude/skills/release/SKILL.md) §Step 0c
- [2026-08-05-v031-patch-design.md](2026-08-05-v031-patch-design.md) — v0.3.1 Track 0 (前例)
