# v0.3.2 patch release 設計書 — deferred 50 件の棚卸し + 依存更新の吸収

- **status**: Track 0 (計画時点)
- **作成日**: 2026-09-02
- **最終更新**: 2026-09-02
- **対象リリース**: v0.3.2 (patch)
- **base ブランチ**: `develop-0.3.2` (= `9191bed`、0.3.2 へ bump 済み)
- **Track 構造**: [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- **前例**: [2026-08-05-v031-patch-design.md](2026-08-05-v031-patch-design.md) (v0.3.1 Track 0)

## 1. 背景 (計画時点)

v0.3.1 は 2026-09-02 にリリース済み (tag v0.3.1)。本 spec は次サイクル v0.3.2 の
計画時点スコープ確定 (`/release` Step 0c) の記録である。

**v0.3.1 retrospective の機構化は本 spec の対象外。** 前例
[2026-08-05-v031-patch-design.md](2026-08-05-v031-patch-design.md) が既に retrospective の
機構化と deferred 吸収を担っており、v0.3.1 の機構化事象 (tag push 後の version-check 落ち →
skill §打ち直し で機構化済み / CHANGELOG 日付打ち直し / 実機ゲート skip 6 件 = #998 /
(a) 27 件中 3 件未消化 = #326 / #882 / #933) は同 spec に記録済み。本 spec は deferred の
棚卸し (50 件) と v0.3.1 後発の依存更新 (Dependabot) の吸収のみを扱う。

## 2. スコープ (計画時点)

### 2.1 deferred (a) 吸収候補 (4 件)

2026-09-02 の Step 0c で Idios が (a) 次 release 吸収を選択した 4 件。
50 件 ≥ 3 のため Iron Law 2 の事前確認を経て承認された (dispatch が (a) 候補 4 件を指定)。

| issue | 内容 | 判断理由 |
| --- | --- | --- |
| #975 | [bug] checker に残る近似の乖離 8 形 (fail-closed の射程外) | checker の fail-closed 射程外 8 形を潰す精度向上。issue 本文は P3-low「実害観測までは任意」だが、Idios が 08-31 コメントで v0.3.2 へ送ると判断 |
| #997 | [task] areamap GT の pin 済み case に assert する test が無い | 回帰防止のテスト強化 |
| #998 | [task] 検証依存セット台帳と E: 原本の乖離 (手動分割 MP4 7 本が欠落) | v0.3.1 実機ゲート skip 6 件の直接原因。Idios の物理作業 (E: から 7 本復元) が前提 |
| #1008 | [task] screenshot-freshness の粒度 + 撮り直し手順が ERR_MODULE_NOT_FOUND | GUI PR 毎の撮り直しコスト削減。手順修正は配置の判断を伴う (issue コメントに実測) |

### 2.2 依存更新 (Dependabot)

v0.3.1 リリース後に Dependabot が発行した 10 件のうち、7 件を吸収、3 件を close した。

**吸収 7 件** (base を `develop-0.3.2` へ retarget 済み):

| PR | 依存 | 種別 / 証拠 |
| --- | --- | --- |
| #1028 | `browserslist` 4.28.4 → 4.28.8 | セキュリティ修正 (open の high アラート #34 を解消) |
| #1024 | `ruff` 0.16.1 → 0.16.5 | 定期 (patch)。前例 R1 の「lint pin は単独先行」制約どおり単独 |
| #1023 | `@tauri-apps/plugin-dialog` 2.7.1 → 2.7.2 | 定期 (patch) |
| #1022 | `datamodel-code-generator` 0.72.1 → 0.76.0 | 定期 (minor)。codegen gate 緑 = 生成物差分なし |
| #1019 | `actions/upload-artifact` 4 → 7 | メジャー。download-artifact を同時に上げるか release job 実走確認が要る (§5) |
| #1018 | `actions/setup-node` 4 → 7 | メジャー (CI 検証) |
| #1017 | `actions/github-script` 7 → 9 | メジャー。互換確認済み (本 repo はローカル CJS を require、validate-checklist が緑) |

**close 3 件**:

| PR | 依存 | 理由 |
| --- | --- | --- |
| #1025 | `react-dom` / `@types/react-dom` | CI 赤。react-dom 19.2.8 の peer react ^19.2.8 に対し react が 19.2.5。react と同時に手で当てる形でないと merge 不可 |
| #1021 | `numpy` 2.4.4 → 2.4.6 | `constraints.txt:56` の bit-exact baseline provenance を動かす。baseline 再取得 (実機 detect、数時間規模) が必要。baseline 再取得は #951 (cv2 5.x) と同じ機会に計画 |
| #1020 | `fast-uri` 3.1.5 → 4.1.3 | over-bump。`ajv@8.18.0` の `fast-uri: ^3.0.1` と衝突 (4.x は範囲外)。現行 3.1.5 は patch 済み |

## 3. §deferred 全件検証結果 (`/release` Step 0c)

2026-09-02 (計画時点) に `gh issue list --state open --label deferred` で取得した 50 件の分類。
前例 §9.4.2 の 49 件との差分は +1 (#1008)。

| 分類 | 件数 |
| --- | --- |
| (a) 次 release 吸収 | 4 |
| (b) deferred 継続 | 46 |
| (c) close | 0 |

### 3.1 (a) 次 release 吸収 (4 件)

§2.1 を参照。

### 3.2 (b) deferred 継続 (46 件)

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #968 | [task] GUI が書き出し先の絶対パスを受け取っておらず、#930 のパス可視化が CLI 限定になっている | (b) deferred 継続 | L2a GUI、P3-low |
| #964 | [bug] GUI の name-pattern プレビューが sandbox 検証を持たず、exit 5 で拒否される名前をそれらしく表示する | (b) deferred 継続 | L2a GUI、P3-low |
| #957 | [task] typer 0.26+ (click vendoring) への移行判断と CLI 内部 API 依存の解消 | (b) deferred 継続 | 依存判断 |
| #953 | [question] GUI minimap: 実行中の画面離脱で進捗表示を失う扱いの決着 | (b) deferred 継続 | L2a GUI |
| #951 | [task] cv2 5.x 移行の判断と baseline 再取得 | (b) deferred 継続 | baseline 再取得と同機会に |
| #937 | [bug] export/minimap 出力パスの同一性判定に残る 4 経路 (hardlink / 8.3 / macOS / 予約デバイス名) | (b) deferred 継続 | 前提 #934 が CLOSED で充足済み、再評価待ち |
| #933 | v0.3.0 doc 監査でスコープ外に置いた項目 (CI スキャナ / audit 閾値 / doc 陳腐化 9 件) | (b) deferred 継続 | 前例 §9.4.1 から持ち越し。§B 3 項目 + §A 閾値判断が残 |
| #925 | [task] masked 録画の baseline 回帰ゲートを追加 (現状は不変性確認のみで正しさ未検証) | (b) deferred 継続 | L3 |
| #921 | [task] --vtuber: 試合間 gap 約 70 秒未満での結合を解消する | (b) deferred 継続 | L3 |
| #882 | [task] 検証データ保全の恒久策 (第 3 系統) 追加 | (b) deferred 継続 | 前例 §9.4.1 から持ち越し。Idios 環境側の作業 |
| #867 | [task] L3: #809 audit 追記 AC 残 2 点の移設 (cache 感度 + red tests) | (b) deferred 継続 | L3 |
| #866 | [task] L3: two-signal 再アーキ Phase 3-4 (VTuber 検証+cutover) 追跡 | (b) deferred 継続 | L3 |
| #861 | [task] L3: QSV/AMF decode hwaccel の扱い確定 (#762 後継) | (b) deferred 継続 | L3 |
| #809 | [task] L3: Pass 1 暗転検知の game 領域輝度適応 (VTuber 本番 wiring) | (b) deferred 継続 | L3 |
| #753 | [task] L3: VTuber + minimap キックオフ (parent issue) | (b) deferred 継続 | L3 parent |
| #742 | [refactor] 5 spawn site を tauri-plugin-shell::Command に移行 (#727 派生 (2), post-v0.2.0) | (b) deferred 継続 | refactor |
| #671 | [task] L2a: E2E test 自動化 feasibility 検討 (#484派生) | (b) deferred 継続 | L2a |
| #670 | [task] L3: GUI 動画 HTTP server 改善 (responsiveness) | (b) deferred 継続 | L3 |
| #518 | [question] note -> warnings: Warning[] 構造化 (将来検討) | (b) deferred 継続 | 将来検討 |
| #480 | [task] L3: VTuber scorebar 局在化(P1) + ROI 適応分類(P4) (re-plan #753、旧: scorebar ROI 適応化) | (b) deferred 継続 | L3 |
| #479 | [task] ユーザー要望: Twitch アーカイブ URL からの試合分割取り込み | (b) deferred 継続 | ユーザー要望 |
| #432 | [task] 他プロセス使用中による Permission denied 系問題の全体見直し | (b) deferred 継続 | — |
| #412 | [refactor] PR #323 refinement 残存長 segment の warning を機械的に追跡する | (b) deferred 継続 | refactor |
| #373 | [refactor] metadata.json に末尾打ち切り情報を残す | (b) deferred 継続 | #805 で前提変化、再評価待ち |
| #326 | [task] ハイブリッド skill 方式を idios-claudecode-tools テンプレートに反映 | (b) deferred 継続 | 前例 §9.4.1 から持ち越し。別 repo 転記 = Idios 手作業 |
| #152 | [risk] L4 (former L3): Tesseract 日本語言語パックの別途インストール要件 | (b) deferred 継続 | 将来レイヤー L4 |
| #151 | [risk] L4 (former L3): OBS 録画に音声トラックが存在しない場合の処理 | (b) deferred 継続 | 将来レイヤー L4 |
| #150 | [risk] L4 (former L3): openai-whisper の PyTorch 依存によるインストールサイズ肥大化 | (b) deferred 継続 | 将来レイヤー L4 |
| #140 | [risk] L4-L6 (former L3-L5): 全体処理時間の見積もりとユーザー体験 | (b) deferred 継続 | 将来レイヤー |
| #139 | [question] L4-L6 (former L3-L5) の end-to-end パイプライン設計 | (b) deferred 継続 | 将来レイヤー |
| #137 | [task] L6 (former L5): 投稿提案の出力設計 | (b) deferred 継続 | 将来レイヤー L6 |
| #136 | [task] L6 (former L5): サムネイル自動生成 | (b) deferred 継続 | 将来レイヤー L6 |
| #135 | [task] L6 (former L5): ハイライトクリップ自動切り出し | (b) deferred 継続 | 将来レイヤー L6 |
| #134 | [task] L5 (former L4) [LLM拡張]: API キー管理とセキュリティ | (b) deferred 継続 | 将来レイヤー L5 |
| #133 | [risk] L5 (former L4) [LLM拡張]: API コスト管理 — LLM 呼び出しの費用見積もり | (b) deferred 継続 | 将来レイヤー L5 |
| #132 | [task] L5 (former L4) [LLM拡張]: 投稿価値の評価基準定義 | (b) deferred 継続 | 将来レイヤー L5 |
| #131 | [task] L5 (former L4) [LLM拡張]: LLM プラグインアーキテクチャの設計 | (b) deferred 継続 | 将来レイヤー L5 |
| #130 | [task] L4 (former L3): 外部依存の追加と環境構築手順の整備 | (b) deferred 継続 | 将来レイヤー L4 |
| #129 | [risk] L4 (former L3): Whisper ローカル実行の処理時間・リソース消費 | (b) deferred 継続 | 将来レイヤー L4 |
| #128 | [risk] L4 (former L3): OCR 精度 — ゲーム独自フォントの認識リスク | (b) deferred 継続 | 将来レイヤー L4 |
| #127 | [task] L4 (former L3): イベントデータ出力フォーマットの設計 | (b) deferred 継続 | 将来レイヤー L4 |
| #126 | [task] L4 (former L3): Whisper による音声認識・SE 検出 | (b) deferred 継続 | 将来レイヤー L4 |
| #125 | [task] L4 (former L3): Tesseract OCR によるキルログ抽出 | (b) deferred 継続 | 将来レイヤー L4 |
| #63 | [task] L7 (former L6): プレイヤー名ぼかし機能の検討・実装 | (b) deferred 継続 | 将来レイヤー L7 |
| #32 | [task] Windows/Linux クロスプラットフォームテスト基盤の構築 | (b) deferred 継続 | — |
| #28 | [task] L7 (former L6): --precise フラグ（再エンコード分割モード）の追加 | (b) deferred 継続 | 将来レイヤー L7 |

### 3.3 Step 0c-2 (本文鮮度 + not_planned 残タスク)

- **not_planned 残タスク**: 区間 `v0.3.1..develop-0.3.2` は version bump 1 commit (`9191bed`) のため
  issue 参照マーカーなし → **検出 0 件**。走査拡張子は `*.py` / `*.md` / `*.rs` / `*.ts`、
  マーカー 3 形式 (`wired in #N` / `Refs #N` / `TODO(#N)`) のみ。
- **本文鮮度**: 前例 §9.4.4 の 4 件 (#964 / #518 / #933 / #326) は 08-31 時点のコメント提示のまま
  本文未更新 (updatedAt 08-31)。v0.3.2 でも再び鮮度切れとして検出。本文 edit は起票者 (Idios) 判断。

## 4. 受け入れ基準

- [ ] deferred (a) 4 件がすべて close される、または close できない理由が記録される
- [ ] 依存更新: open の high アラート #34 (browserslist) が #1028 で解消され、tag 時点で open の security alert が 0 件
- [ ] #1025 (react-dom) の決着: react + react-dom を同時に手で当てる、または据え置きの裁定
- [ ] #1021 (numpy) の決着: baseline 再取得を計画に載せる、または据え置きの裁定
- [ ] #998 復元後、実機ゲート skip 0 件
- [ ] `python scripts/check_version_consistency.py --tag v0.3.2` が exit 0
- [ ] #1019 (upload-artifact v7) と download-artifact v4 の組み合わせが release job で実走確認される (または download-artifact を同時に上げる)

## 5. Track 割り当て + 直列制約 + 裁定

| Track | 内容 | 状態 |
| --- | --- | --- |
| Track A | 依存更新 (Dependabot) | open-ended。マージで次の bump が発行される (open-pull-requests-limit 3 に張り付く)。締め切りは Track D 直前の Step 5 security 再チェック時点で open のものは次サイクル (security alert は例外) |
| Track B | deferred (a) 4 件 | #975 / #997 / #998 / #1008 |
| Track D | CHANGELOG 見出し確定 | version bump は `9191bed` で済み |

直列制約・裁定:

- #998 は Idios の物理作業 (E: から 7 本復元) が実機ゲートの前提
- #1008 は配置の判断 (issue コメントの 3 択) の裁定が要る
- #1024 (ruff) は前例 R1 の「lint pin は単独先行」制約どおり単独先行
- #1021 (numpy) は baseline 再取得 (R2 実機スロット) か据え置き
- #1019 (upload-artifact) は download-artifact 同時更新か release job 実走確認

## 6. 関連リンク

- [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- [`.claude/skills/release/SKILL.md`](../../../.claude/skills/release/SKILL.md) §Step 0c
- [2026-08-05-v031-patch-design.md](2026-08-05-v031-patch-design.md) — v0.3.1 Track 0 (前例)
