# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-16

L2 (GUI + Portable 配布) リリース。Tauri ベースの GUI を新設し、Portable ZIP 配布で zero-environment setup を実現。GPU decode を Intel QSV / AMD d3d11va に拡張、CLI/GUI で metadata.json schema を統一、warnings 基盤を導入。L2 開発プロセスとして markdownlint 導入、Iron Law 6 (PR 作成前ゲート)、`/iterate-review` / `/close-issue` skill 等の workflow / docs / test infra を全般強化。

### Added

#### L2a: GUI (Tauri)

- Tauri プロジェクト bootstrap (#483, #499)
- Phase 1 data layer (detect/split + metadata contract + Zustand store) (#463, #504, #512)
- Phase 2 画面骨格 + [元に戻す] 機能 (#464, #516, #526)
- Phase 3 preview 本物化 + ffmpeg 中断フロー (#465, #523, #540)
- Phase 4 export 本物化 (ffmpeg 呼び出し + 進捗) + GPU encoder auto-select (#466, #545, #591, #596)
- DropScreen DnD + 直近録画リスト (recent.json + Tauri commands) + 詳細設定パネル (#568, #571, #613, #625, #655)
- detecting / complete 画面を本物化 (CLI 連携 + 輝度タイムライン) (#569, #623)
- preview FrameStrip brightness overlay (#645, #735)
- CompleteScreen 「所要」列追加 + threshold 連動 (#586, #588, #626)
- ExportScreen default outDir + ErrorModal tauri-command fallback (#680, #696, #741)
- 編集 draft 自動保存 (リロード耐性) + DraftRestoreModal (#517, #534, #697, #730)
- metadata.json 排他管理 (mtime 検知 + conflict modal) (#514, #532)
- ConflictModal で state.mtime_conflict AppError hint 表示 (#695, #725)
- sample mode 全画面 read-only 化 (#633, #719)
- GUI 5 画面横断 file path 表示統一 (#676, #747)
- GUI クラッシュ・エラー伝搬ハンドリング (#614, #661)
- AppError migration 完遂 (legacy fallback 撤去 + per-code default hint 全 80 site 適用) (#663, #689)
- InlineErrorHint component 新設 + 既存 5 site refactor (#693, #714)
- ErrorModal「Issue 本文をコピー」button 新設 (Plan B clipboard) (#669, #726)
- DropScreen で recentStore error notice 表示 (#698, #733)
- GUI 全画面 a11y polish (focus trap / Escape / DisabledTooltip / jest-axe) (#587, #631)

#### L2b: Portable ZIP installer

- リリース配布 workflow + Portable ZIP ビルドスクリプト (#461, #490)
- Python 3.11.9 + BtbN LGPLv3 FFmpeg 8.1 統一 (#508, #510, #531, #535)
- FFmpeg LGPLv3 LICENSE 同梱 + ソース入手経路を明記 (#509, #541)
- allaganeye-gui.exe を Portable ZIP に同梱 (#570, #615)
- allaganeye.bat ダブルクリックで GUI 起動 (#617, #701)
- Portable ZIP 同梱物の起動時健全性チェック (#668, #702)
- BtbN pin を monthly snapshot に切替 (~24ヶ月 retention) (#705, #721)
- Portable ZIP の SmartScreen 警告手順と署名方針記録 (#462, #495)
- Portable ZIP .bat/README.txt を docs と整合 (#503, #507)

#### GPU decode 拡張

- AV1/VP9 を GPU decode auto-select 対象に追加 (#414, #539)
- vendor probe + `--gpu-vendor` option 基盤 (NVIDIA 実装, AMD/Intel stub) (#546, #554)
- AMD GPU decode を d3d11va + hwdownload で実装 (#553, #578)
- Intel QSV decode 対応 (h264 / hevc / av1) (#550, #581)
- Intel QSV VP9 decode (#582, #585)
- GPU mode UX 三点修正 (#437, #438, #439, #543)

#### Metadata / Warnings 基盤

- metadata.json JSON Schema 化 + 型 codegen 導入 (#612, #627)
- metadata.json schema_version + migration 基盤 (#515, #533)
- warnings 基盤 (Warning type + 空 array) (#518, #544)

#### CLI / verbose

- HW info verbose を multi-CPU / multi-GPU 対応 (#435, #436, #650)
- 3 detect フェーズを最初から並べる多行 eager 表示 (#434, #642)
- single-dash long-option 入力時に `--<name>` ヒント表示 (#440, #632)
- verbose Filter 行に unknown match 件数の別行を追加 (#433, #638)
- 進捗バー ETA 表示の改善 (label / placeholder / visual baseline 維持) (#365, #687)

#### Docs / workflow

- UI interaction spec §1 共通原則 + §2.1-§2.5 各画面 UI 部品状態機械 + §3 拡充 (#590, #593, #598, #600, #603, #605, #608, #610)
- CLI+GUI 統合 system-architecture 新設 + ui-architecture GUI 限定明記 (#527, #542)
- 全 Tauri command の master 一覧 doc (#619, #665)
- v0.2.0 リリース受け入れゲートを定義 (#620, #621)
- L2 Tier 0 release gate (axum-video-server spec + l2-e2e-checklist) (#484, #618, #672)
- 外部ユーザー向けバグ報告ガイド + Issue Form (#458, #459, #497, #498)
- Iron Law 6 新設 (PR 作成前ゲート) (#636, #637)
- L2-0 ワークフロー刷新 + 旧ロール用語掃除 (#448, #449, #472, #473, #595, #597)
- L2 再定義 + L6/L7 削除 + L8→L6 リナンバー (#446, #447)
- markdownlint-cli2 導入 + 既存違反修正 (MD022/031/032/040, MD029/038/028, MD024 siblings_only) (#474, #494, #500, #501, #502)
- empirical-prompt-tuning で 5 スキル改善 (#475, #487, #511, #537)
- `/iterate-review` skill 新設 + `/review-pr` 機能整理 (review-fix ループ自動化) (#706)
- `/close-issue` skill (issue クローズ責務を分離) (#594, #602, #606, #607, #629)
- `claude/*` ブランチ自動削除機構 (#708, #732)
- CI: error.rs hint table drift check / gui-rust cargo test --lib / artifact zip versioning (#611, #616, #622, #686, #692, #715, #751, #754)
- リリース手動手順 (release-strategy.md → release-process.md にリネーム) (#461, #547)
- ESLint で window.confirm/alert/prompt を block (#643, #684)

### Changed

- subprocess 起動を tokio::process::Command に統一 (gui spawn 統一、Lane VII) (#727, #740)
- preuse-hook を exit 2 block → permissionDecision=ask へ (#559, #561)
- issue_close hook を bulk mode に緩和 (#485, #491)
- review-pr skill レビュー専用セッション前提に一本化 (#505, #506)
- review-pr: Iter 2 追記 + scope-guard 逆方向例外 + 摘出課題二択強制 + 環境制約節 + Round N (#562, #563, #564, #565, #567)
- review-pr: checkout 禁止を read 目的に緩和 (#673, #674)
- guard をプログラム結合から運用連携に転換 (#454, #496)
- SideRail 全体削除 (#677, #739)
- `*Error` / `*ErrorHint` 並列構造を unified `*ErrorState` に集約 (#694, #745)
- 残 4 site の `String(e)` を `appErrorMessage(e)` に置き換え (Lane II-b) (#678, #718)
- metadataStore `*ErrorHint` lifecycle pinning (#691, #716)

### Fixed

- scorebar V2 (`_has_scorebar_v2`) を two-path OR semantics に変更 (Primary=absolute `_EMBLEM_POSITIONS` + Rescue=dynamic span + `_EMBLEM_RELATIVE_POSITIONS`)。1080p OBS validated set (20260116/118/119/219) は Primary で完全無回帰、4K Game DVR の HUD scale 差異は Rescue path で救済 (#522)
- Portable ZIP の `integrity-manifest.json` を BOM-less UTF-8 で書き出すように修正 (#729)。`scripts/build-portable-zip.ps1` で `Set-Content -Encoding UTF8` を使うと Windows PowerShell 5.1 (`powershell.exe`) では UTF-8 with BOM を emit し、Tauri GUI 起動時の integrity-check (`serde_json::from_str`) と CLI `--version` の integrity-check (`json.loads`) が双方 BOM 拒否で fail していた。PS 6.0+ (`pwsh`) では BOM-less だったため CI smoke (`shell: pwsh`) が本 bug を mask。`[IO.File]::WriteAllText` + `UTF8Encoding($false)` で PS-agnostic に変更
- 日本語 path で subprocess cp932 失敗 (#656, #657)
- detect 子プロセスの UTF-8 stdout 強制 + lossy decode (#656, #662)
- start_detect 失敗を可視化 + python -m フォールバック (#646, #647)
- detecting ログを overflow: auto + auto-scroll 化 (#639, #641)
- parse_detect_progress_line silent skip を warn 出力に (#648, #731)
- run_split / --from-metadata で brightness_samples を書く (#644, #734)
- scorebar 分類進捗を Refining bar に統合 (#664, #666)
- scorebar classify_blackout に対称 re-probe fallback (#524, #552)
- scorebar V2 で emblem 位置を動的検出し 4K Game DVR 対応 (#522, #525)
- NVENC/AMF 起動失敗 stderr を ffmpeg 8.1 BtbN LGPL に対応 (#604, #609)
- VP9 を NVDEC cuvid から外し soft decode 経路に (#538, #549)
- production build CMD 窓を抑止 (#679, #720)
- StateSwitcher を dev only に絞り topBar との z-index 重複を解消 (#653, #675)
- PreviewScreen state mutation flow + dirty consume confirm (#589, #628)
- get-pip.py SHA pin を pypa/get-pip versioned tag URL に切替 (#681, #703)
- get-pip.py SHA256 pin を PyPA 最新版に更新 (#649, #651)
- Tests.ps1 に UTF-8 BOM 付与 (PS5.1 parse fix) (#704, #713)
- pyproject packages.find 明示 + license SPDX 新形式 (#469, #489)
- markdownlint nested gui/node_modules / build/** を ignore に追加 (#700, #717, #723, #724)
- BtbN LGPL 方針を code/test/docs サイドに浸透 (#508, #535)

### Internal

- L2 開発ロードマップ更新 (8 → 11 → 13 group / 6 → 8 lane wave) (#683, #709, #738)
- Phase 0 計測結果反映 + feasibility.md Electron-vs-Tauri (#450, #467, #468, #470, #471)
- GUI handoff bundle 取込み (#105, #453)
- Lane V Phase 1 (Group I) post-#663 hint UI cleanup spec + 実装計画 (#691, #693, #695, #697, #698, #712)
- L2 Lane I-B Group B spec + plan (#644, #648, #679, #711)
- L2 Lane IV-c Group H spec + plan + plan-fix (#365, #643, #690)
- Lane VI / Group L — hook test infra + resume-plan handoff 規約 (#710, #722, #744)
- workflow / CI / docs 仕上げ (Group G) (#458, #624, #682, #688)
- L2 (v0.2.0) 残作業 roadmap (8 brainstorming groups) (#683)
- developer-setup: venv Permission denied トラブルシュート追記 (#431, #566)
- detection_params 型違反 + Rust load_metadata エラーパステスト追加 (#520, #521, #530)
- baseline を scorebar-on semantics に移行、20260118 の 4 件非FL を除外 (#529, #536)
- legacy 20260118 Match 8 end を 6184.0 → 6465.25 に更新 (#560, #575)
- build-portable-zip.ps1 に Pester v5 テスト追加 (#528, #548)
- launcher template の exit code 伝搬 idiom に Pester regression 追加 (#583, #584)
- release.yml smoke-test Level B 追加 (#572, #579)
- ci(release): build-windows に Portable ZIP smoke-test ステップ追加 (#557, #558)
- CI/Release 軽量化: 二重 zip + shared FFmpeg + cache (#551, #555)
- CI artifact zip 名にバージョン番号を含める (#616, #686)
- CI artifact 名から `-portable` を削除 (#751, #754)
- Stop hook 診断ログ追加 (worktree dir cleanup 切り分け) (#477, #707)
- worktree 残骸 sweep スクリプト (#477, #493)
- CLAUDE.md / project skill / hook の plugin・system プロンプト重複整理 (#667)
- PR 作成・レビュー時の base 同期 + 並行 PR + 摘出処置運用化 (#659, #660)
- archive: l1-detection-redesign.md (#476, #492)
- develop-0.2.0 init (version bump + tools relocation) (#443)
- L1 リリース完了反映 + ロードマップ目標日更新 (#444, #445)
- ffmpeg fps filter の version 依存制約を docs に明記 (#577, #592)
- stderr_tail 末尾長を定数化 (#413, #630)
- AppError stale docstring 更新 (#699, #746)
- ui-architecture §4.9 catch 漏れ AppError fallback 追加 (#696)
- `/close-issue` skill: Refs #N fallback + Iter 2 検証 + reports 整理 (#606, #607, #629)

## [0.1.1] - 2026-04-20

L1 (試合分割) の正式リリース版。2026-04-17 に `v0.1.0-preview` として公開後、品質向上を経て `v0.1.1` として正式リリース。verbose 出力の網羅的改善、GPU/CPU 検知精度の一致、進捗バー UX 修正、メタデータ拡充、運用ルール強化。

### Added

- verbose ヘッダに HW 情報 (CPU/GPU/Memory/Disk) を表示 (#377)
- verbose 出力に Pass 1/Pass 2/Scorebar/Splitting の elapsed time を表示 (#386, #387)
- verbose 出力に Filter drop 内訳を表示 (#388)
- verbose 出力に検知候補 metadata、resolved workers 数を表示 (#389)
- キャッシュヒット時にも verbose で検知パラメータを表示 (#380)
- Match 一覧に `[unknown]` マーカーを表示 (#382)
- metadata.json に `detection_params` / `detected_at` を記録 (#370)
- metadata.json の `gaps` 配列に raw 秒フィールドを追加 (#369)
- metadata.json の `output_file` パスを POSIX 区切りに正規化 (#371)
- コーデックに基づく GPU/CPU モード自動選択 (#334)
- 分割前にディスク空き容量をチェック (#338)
- `-V` / `--version` ショートフラグと verbose パイプライン統計 (#336, #337)
- verbose エラー詳細 (traceback + ffmpeg stderr) を出力 (#351)
- CLI 出力仕様マトリクス docs (`docs/output-spec.md`) を新設 (#405)
- 過去 PR audit レポート (`docs/audits/2026-04-19-pr-audit.md`) を追加 (#410)
- ロール定義にユーザー確認ルール / Memory 活用ガイダンスを追加 (#400)
- Director / Lead Engineer 行動規範 A/B/C を docs に明文化 (#399)
- PreToolUse hook で確認ゲートを実装 (#401)
- Quick Start に venv セットアップ手順を追記 (#364)
- 出力ファイル一覧に `.detection_cache.json` を追記 (#360)
- `--gpu` がデフォルト off の理由を README / CLI ヘルプに補足 (#332)

### Changed

- verbose 出力の `audio=on/off` を実態に合わせ `audio=frozen` に修正 (#384)
- verbose 出力の ffmpeg version 文字列を簡潔化 (`8.1` 等) (#383)
- verbose 出力の Total time 表示を全パス (cache hit + split 含む) に統一 (#381)
- `-q` モードで dry-run 通知の出力を抑制 (#418)
- CLI で `-q` / `-v` / `--gpu` / `--no-gpu` 同時指定を排他エラー化 (#419)

### Fixed

- 進捗バー (Detecting/Refining/Scorebar) の上書き表示問題 (#368, #393)
- Pass 2 中の進捗無音問題 (#366)
- 進捗バー ETA ラベル明確化、split 出力表示改善 (#328, #329, #331)
- GPU mode で CPU と Match 境界が一致しない問題 (#392, sample grid 整列)
- Pass 1 統計の verbose 表示漏れ (#386)
- Pass 1 borderline frame 対策 (A3/A4 hysteresis) (#361)
- GPU chunk progress をリアルタイムで進捗バーに反映 (#333)
- 凍結中の音声スキャンをデフォルトで無効化 (#327)
- `scan_fanfare_hits` の FileNotFoundError を `VideoProcessingError` でラップ (#350)
- CLI エラー表示を output matrix v2 (19a/19b/19c) に整合 (#428)

### Internal

- テスト網羅性向上 (オプション組合せ網羅、GPU chunk_timestamps parametric、system_info Linux/Darwin パーサ実解析、metadata gaps shape、Pass 2 進捗、B グループカバレッジ等)
- `setup-session` の開発ブランチ参照とパスを動的化
