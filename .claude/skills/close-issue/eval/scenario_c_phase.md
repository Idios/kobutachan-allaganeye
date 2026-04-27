# シナリオ C: Phase 分割 (ケース C = N PR で 1 issue close)

参考事例: L2a GUI の段階開発 (#463 data 層 → #464 画面骨格 → #514 排他管理 など)、または bug fix の Phase 1/2 分割。本 issue は最終 PR マージ後に close 可能。

## 紐づく issue (#907 として仮定)

**タイトル**: `[task] L3 メタデータ化 Phase 1: キルログ OCR scaffolding`

**ラベル**: `[task]`, `l3-metadata`, `P2-medium`

**state**: `OPEN`

**closedByPullRequestsReferences**: `[{ "number": 917, "state": "MERGED" }, { "number": 918, "state": "MERGED" }]`

**timelineItems**: 一致 (#917 と #918 の 2 件)

**本文**:

```markdown
## 概要

L3 メタデータ化レイヤーの足場を組む。Phase 1 ではキルログ OCR の scaffolding (テンプレマッチ) のみ実装し、文字認識精度向上は L3 後続 issue で扱う。

## 背景

L3 のメタデータ化 (キルログ・音声・チャットのタイムスタンプ化) は既存試合分割 (L1) の上に構築する。Phase 1 では Tesseract 統合の足場・キルログ region 抽出・テンプレマッチによる kill icon 検出までをカバーする。

## 受け入れ条件

- [ ] `metadata/ocr.py` を新規追加し、キルログ region 抽出 + テンプレマッチで kill icon を検出する
- [ ] `metadata/refs/kill_icons/` に検出用テンプレ (3 jobs × 2 解像度 = 6 個) を同梱
- [ ] `metadata extract` サブコマンドを CLI に追加 (`allaganeye metadata extract <video> -o <out>`)
- [ ] 単体テスト: `tests/test_metadata_ocr.py` で region 抽出 + テンプレマッチを 4 ケース検証

## 関連 PR (Phase 分割)

- Phase 1: PR #917 (`metadata/ocr.py` + テンプレ同梱)
- Phase 1.5: PR #918 (CLI サブコマンド + テスト追加)

## 完了イメージ

`allaganeye metadata extract sample.mp4 -o killlog.json` で試合動画から kill 検出タイムスタンプ JSON が出力される。
```

---

## モック PR #917 (Phase 1)

**タイトル**: `feat(metadata): キルログ OCR scaffolding (Phase 1, Refs #907)`

**state**: `MERGED`

**mergedAt**: `2026-04-23T18:04:33Z`

**baseRefName**: `develop-0.2.0`

**headRefName**: `claude/907-phase1-ocr-scaffolding`

**closingIssuesReferences**: `[{ "number": 907 }]`

**本文**:

```markdown
## 概要

#907 Phase 1: `metadata/ocr.py` の足場 + テンプレマッチによる kill icon 検出。

- `metadata/ocr.py` を新規追加 (region 抽出 + テンプレマッチ)
- `metadata/refs/kill_icons/` に 6 テンプレ (DRG/MNK/SAM × 1080p/2160p) 同梱
- 単体テストはまだ追加していない (Phase 1.5 PR #918 で対応)

## 残タスク

- CLI サブコマンド + 単体テスト追加は #918 (Phase 1.5) で実装
```

### 主要 diff 要約 (+450 / -0)

```text
allaganeye/metadata/__init__.py            +5   -0
allaganeye/metadata/ocr.py                 +180 -0    # 新規: region + テンプレマッチ
allaganeye/metadata/refs/kill_icons/       +6 files (binary, ~120KB total)
CLAUDE.md                                  +18  -0    # §L3 メタデータ化 節新設
```

---

## モック PR #918 (Phase 1.5)

**タイトル**: `feat(cli): metadata extract サブコマンド + OCR 単体テスト (Phase 1.5, Refs #907)`

**state**: `MERGED`

**mergedAt**: `2026-04-26T09:15:42Z`

**baseRefName**: `develop-0.2.0`

**headRefName**: `claude/907-phase15-cli-and-tests`

**closingIssuesReferences**: `[{ "number": 907 }]`

**本文**:

```markdown
## 概要

#907 Phase 1.5: CLI サブコマンドと単体テスト追加。Phase 1 (#917) で実装した `metadata/ocr.py` を CLI から呼べるようにし、テストでカバレッジを担保する。

- `commands/metadata_extract.py` を新規追加
- `cli.py` に `metadata extract` サブコマンドを登録
- `tests/test_metadata_ocr.py` で region 抽出 + テンプレマッチを 4 ケース検証
- pytest 全 pass、ruff check 全 pass

## 動作確認

- 30s 試合動画で `allaganeye metadata extract` 実行 → kill log JSON 出力確認
```

### 主要 diff 要約 (+220 / -8)

```text
allaganeye/cli.py                         +35  -3    # metadata extract サブコマンド登録
allaganeye/commands/metadata_extract.py   +90  -0    # 新規
tests/test_metadata_ocr.py                +95  -5    # 4 ケース新規
```

---

## 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **PR 件数判定**: `closedByPullRequestsReferences` が 2 件 (#917, #918) → ケース C (Phase 分割) と機械判定すべき。1 PR (例えば #918 のみ) を見て close しようとする誤りをしないか試す
2. **受け入れ条件と PR の対応分離**: 受け入れ条件 4 項目のうち、項目 1-2 は #917、項目 3-4 は #918 で対応。subagent はマッピング表で「どの PR が満たすか」を明示する必要あり (本 skill SKILL.md Step 4 / ケース C 詳細運用に明記)
3. **全 PR マージ済み確認**: 両 PR とも `MERGED`。`gh pr view` を 2 件分実行して全件 MERGED であることを確認する必要あり (どちらか 1 件しか確認しない誤りをしないか)
4. **CLAUDE.md 更新箇所の検証**: 受け入れ条件には CLAUDE.md 更新は明記されていないが、PR #917 の diff に含まれる。subagent が「受け入れ条件外の変更」として正しく仕分け、close 判定に混入させないか試す
5. **「Phase 1 マージ済みだから close 可」誤判定**: PR #917 単独でも一見 issue の半分を満たすが、項目 3-4 (CLI サブコマンド + 単体テスト) は #918 で対応。subagent が #917 のみ確認して close しようとする誤りをしないか試す

## 検証環境情報

- CI: 両 PR とも green
- マージ: 両 PR `--squash` で `develop-0.2.0` に統合済
- `/review-pr` 段階で各 PR を独立にレビュー済 (前提)
