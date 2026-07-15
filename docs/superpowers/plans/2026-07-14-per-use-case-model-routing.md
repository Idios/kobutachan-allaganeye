# 用途別モデルルーティング Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** allaganeye 開発時のサブエージェント/レビューを用途別モデル（メイン=Opus/Fable、技術レビュー=Codex、全体レビュー=Fable、定型=Sonnet/Haiku）へ振り分ける仕組みを project-local に導入する。

**Architecture:** `.claude/agents/*.md` の frontmatter `model:` エイリアスでサブエージェントのモデルを固定し、CLAUDE.md にルーティング方針を明文化する。強制はせずアドバイザリ運用（3 層: agent 定義 / CLAUDE.md / 主エージェント規律）。既存 Codex 配線は不変。

**Tech Stack:** Claude Code subagent 定義（Markdown + YAML frontmatter）、CLAUDE.md、markdownlint。

## Global Constraints

- **エイリアスで最新追従**: `model:` はフル ID でなくエイリアス（`fable` / `sonnet` / `haiku`）で書く。各系統の最新に自動追従させる（「最新モデル」要件）。
- **メインモデルは固定しない**: settings.json への `model` 追記は禁止（ユーザーが都度選択）。
- **Codex 配線不変**: `## Codex 運用` 節・Iron Law 6 Pre-flight Step 5・3-tier invocation には一切変更を加えない。
- **配置は project-local のみ**: `.claude/agents/`（repo 内）に置く。user-level `~/.claude/agents/` や `idios-claudecode-tools/tools/model-router` は変更しない。
- **アドバイザリ**: hook による強制ルーティングは作らない。
- **本ツールの実行時依存に非該当**: 開発運用設定のみ。CLI/GUI の挙動・出力は変わらない。
- **markdownlint**: 追加・変更する全 `.md`（agent 定義 3 ファイル + CLAUDE.md）は `bash scripts/check-markdownlint.sh` を pass させる。
- **commit の Co-Authored-By**: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## 前提（実装前・PR 前の運用メモ、TDD タスク外）

- **issue 起票**: PR 前に issue-policy に従い `task:` prefix の GitHub issue を起票する（Iron Law 6 は issue 参照を要求）。起票は `/create-task` skill で対話的に行い、本 spec/plan を紐づける。
- **PR / merge は Idios 専任**: PR 作成は Iron Law 6 Pre-flight を通過後、merge は Idios が手動。agent は merge しない。
- **実機検証は不要判定**: Python/GUI ロジック（`gpu_detector.py` / `audio/*` / `detector.py` / `gui/src-tauri/**` 等）を touch しない docs/config 変更のため、Iron Law 6 の GPU/audio/長時間/Tauri 実機検証 trigger には該当しない。該当チェックは markdownlint のみ。

---

## File Structure

> **改名注記 (#889 Codex adversarial-review 反映)**: worker は当初 `sonnet-worker` / `haiku-worker` として実装したが、user-level model-router との同名衝突（precedence 依存の silent 誤ルーティング）を Codex が No-ship としたため、**`allaganeye-sonnet-worker` / `allaganeye-haiku-worker` へ改名**して確定。**Task 2 本文・検証も新名へ更新済み**。旧名は本注記と Task 4 の user-level 衝突例にのみ残す（実行時に旧名を使わないこと）。正は `.claude/agents/allaganeye-*.md` + CLAUDE.md 対応表。

- Create: `.claude/agents/fable-consult.md` — 全体レビュー・相談ワーカー（`model: fable`、read-only）
- Create: `.claude/agents/allaganeye-sonnet-worker.md` — 中難度定型ワーカー（`model: sonnet`）
- Create: `.claude/agents/allaganeye-haiku-worker.md` — 低難度定型ワーカー（`model: haiku`）
- Modify: `CLAUDE.md` — `## モデルルーティング（用途別モデル使い分け）` 節を `## Codex 運用`（L299-331）の直後・`## CLAUDE.md 継続改善`（L332）の直前に挿入

---

## Task 1: fable-consult 定義（全体レビュー・相談レイヤー）

**Files:**

- Create: `.claude/agents/fable-consult.md`

**Interfaces:**

- Produces: `subagent_type=fable-consult` で起動可能な read-only レビュア。`model: fable`。tools = `Read, Grep, Glob, WebSearch, WebFetch`（Edit/Write/Bash/Agent なし）。

- [ ] **Step 1: ファイル作成**

`.claude/agents/fable-consult.md` を以下の内容で作成する（**この内容そのまま**）:

```markdown
---
name: fable-consult
description: 全体的なレビュー・相談用（設計方針/UX/ドキュメント整合/受け入れ条件の網羅性・妥当性/俯瞰的セカンドオピニオン）。コード技術詳細の adversarial レビューは Codex を使うこと。
model: fable
tools: Read, Grep, Glob, WebSearch, WebFetch
---

# Fable Consult（全体レビュー・相談）

設計・方針・ドキュメント・全体整合について俯瞰的なセカンドオピニオンを返すレビュア/相談役。

## 対象

- 設計判断・spec のレビュー（見落とし/矛盾/曖昧さ/スコープ過大）
- 受け入れ条件の網羅性・妥当性の点検
- UX・ドキュメント整合・命名・全体像の相談
- 複数選択肢のトレードオフ整理

## 推奨起動トリガー（原則。hook 強制はしない）

- spec/design doc 執筆完了後・ユーザーレビュー前
- brainstorming で選択肢が割れて決めきれないとき
- 受け入れ条件を新規策定した issue の起票前

## 非対象（Codex へ）

- コードのバグ/セキュリティ/GPU fallback 文字列/encoding boundary/adversarial pass
  → これらは Codex（`codex-companion.mjs`）を使う
- 「Fable にレビューさせた」ことを Codex レビュー省略の口実にしない

## 制約

- 実装・ファイル編集は行わない（read-only。tools からも Edit/Write/Bash を除外）
- サブエージェントの起動（Agent tool）は行わない
- 指摘は主エージェントに構造化して返し、独断で修正・commit しない
- 不明点は臆測せず「確認すべき点」として返す
```

- [ ] **Step 2: frontmatter 検証**

Run: `sed -n '1,6p' .claude/agents/fable-consult.md`
Expected: `model: fable` と `tools: Read, Grep, Glob, WebSearch, WebFetch` が存在し、`Bash` / `Edit` / `Write` を含まない。

- [ ] **Step 3: commit**

```bash
git add .claude/agents/fable-consult.md
git commit -m "feat: fable-consult 全体レビュー・相談サブエージェント定義 (model: fable, read-only)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: allaganeye-sonnet-worker / allaganeye-haiku-worker 定義（定型作業レイヤー）

**Files:**

- Create: `.claude/agents/allaganeye-sonnet-worker.md`
- Create: `.claude/agents/allaganeye-haiku-worker.md`

**Interfaces:**

- Produces: `subagent_type=allaganeye-sonnet-worker`（`model: sonnet`）/ `subagent_type=allaganeye-haiku-worker`（`model: haiku`）。両者とも本文に「Iron Law」を含む（project-local 判別マーカー。user-level model-router 版には無い）。

- [ ] **Step 1: allaganeye-sonnet-worker.md 作成**

`.claude/agents/allaganeye-sonnet-worker.md` を以下の内容で作成する:

```markdown
---
name: allaganeye-sonnet-worker
description: 中難度の定型タスク（原因既知バグ修正/テスト作成/スコープ明確 refactor/doc 更新/機械的依存更新）を実行するワーカー。
model: sonnet
---

# Sonnet Worker（中難度定型）

## 対象

- バグ修正（原因が特定済みのもの）
- ユニット/統合テスト作成
- スコープが明確な refactor
- ドキュメント更新
- 依存更新（機械的で major/minor bump を伴わないもののみ。security bump は罠が多い実績があるため主エージェント主導）

## 制約（allaganeye Iron Law 整合）

- アーキテクチャレベルの変更は主エージェントへ委譲
- スコープ外の変更（「ついでに直す」）は禁止（Iron Law 3）。逸脱を検知したら止めて報告
- 曖昧な判断は独断で prescribe しない（Iron Law 5）。主エージェントへ報告して終了
- 複数ファイルに跨る大規模変更は事前に主エージェントと方針合わせ
- サブエージェントの起動（Agent tool）は行わない。分解が必要なら主エージェントへ返す
```

- [ ] **Step 2: allaganeye-haiku-worker.md 作成**

`.claude/agents/allaganeye-haiku-worker.md` を以下の内容で作成する:

```markdown
---
name: allaganeye-haiku-worker
description: 低難度の定型タスク（ファイル検索/リネーム/フォーマット修正/boilerplate 生成/要約/情報収集）を高速・低コストで処理するワーカー。
model: haiku
---

# Haiku Worker（低難度定型）

## 対象

- ファイル検索・パターンマッチ・情報収集・要約
- 単純なリネーム・置換・フォーマット修正
- 定型コード生成（boilerplate）・ログ/コメント追加

## 制約（allaganeye Iron Law 整合）

- 設計判断・アーキテクチャ変更は行わない
- スコープ外の変更は禁止（Iron Law 3）
- サブエージェントの起動（Agent tool）は行わない
- 不明点があれば主エージェントに報告して終了する
```

- [ ] **Step 3: frontmatter 検証**

Run: `head -5 .claude/agents/allaganeye-sonnet-worker.md; echo '---'; head -5 .claude/agents/allaganeye-haiku-worker.md`
Expected: それぞれ `model: sonnet` / `model: haiku` を含む。

- [ ] **Step 4: commit**

```bash
git add .claude/agents/allaganeye-sonnet-worker.md .claude/agents/allaganeye-haiku-worker.md
git commit -m "feat: allaganeye-sonnet-worker/allaganeye-haiku-worker 定型作業サブエージェント定義 (Iron Law 整合制約付き)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: CLAUDE.md モデルルーティング節

**Files:**

- Modify: `CLAUDE.md`（`## Codex 運用` 節の直後、`## CLAUDE.md 継続改善` の直前に挿入）

**Interfaces:**

- Consumes: Task 1/2 の agent 名（`fable-consult` / `allaganeye-sonnet-worker` / `allaganeye-haiku-worker`）。
- Produces: ルーティング規約の SSoT 節。

- [ ] **Step 1: 挿入位置の確認**

Run: `grep -n '^## CLAUDE.md 継続改善' CLAUDE.md`
Expected: 1 行ヒット（この行の直前に新節を挿入する）。

- [ ] **Step 2: 新節を挿入**

`## CLAUDE.md 継続改善` の行の直前に、以下のブロックを挿入する（**この内容そのまま**、末尾に空行を 1 つ入れて既存節と分離）:

```markdown
## モデルルーティング（用途別モデル使い分け）

開発時のサブエージェント/レビューを用途別のモデルへ振り分ける。**本ツールの実行時依存ではなく開発運用のみ**（CLI/GUI の挙動・出力は変わらない）。設計 spec は [`docs/superpowers/specs/2026-07-14-per-use-case-model-routing-design.md`](docs/superpowers/specs/2026-07-14-per-use-case-model-routing-design.md) を参照。

ルーティングは**アドバイザリ**（hook 強制はしない）。担保は 3 層: agent 定義 `model:` / 本節のガイダンス / 主エージェントの規律。

### 対応表

| 用途 | モデル/ツール | 呼び出し |
| --- | --- | --- |
| メイン（設計判断・複雑デバッグ・アーキ変更・新機能・統括） | ユーザー選択（既定 Opus 最新 / 高難度は最初から Fable 最新）。**固定しない** | セッションモデル |
| 技術レビュー・相談（バグ/セキュリティ/GPU fallback/encoding/adversarial） | Codex | 既存 3-tier（§Codex 運用）。**不変** |
| 全体レビュー・相談（設計方針/UX/ドキュメント整合/受け入れ条件妥当性/俯瞰） | Fable 最新 | `Agent(subagent_type=fable-consult)` |
| 中難度定型（原因既知バグ修正/テスト作成/スコープ明確 refactor/doc 更新） | Sonnet 最新 | `Agent(subagent_type=allaganeye-sonnet-worker)` |
| 低難度定型（検索/リネーム/フォーマット/boilerplate/要約/情報収集） | Haiku 最新 | `Agent(subagent_type=allaganeye-haiku-worker)`。ビルトイン Explore は `model:"haiku"` を渡す |

- **エイリアス指定**（`fable` / `opus` / `sonnet` / `haiku`）で各系統の最新に自動追従（フル ID 固定はしない）。
- agent 定義は **project-local**（`.claude/agents/`）を使う。user-level `~/.claude/agents/` の同名定義より優先。

### fable-consult の推奨トリガー地点（原則。強制ではない）

- spec/design doc 執筆完了後・ユーザーレビュー前
- brainstorming で選択肢が割れて決めきれないとき
- 受け入れ条件を新規策定した issue の起票前

### Fable と Codex の棲み分け

- **修正先が「コード/テスト diff」→ Codex**、**「文書・方針・プロセス」→ Fable**。
- invariant / 不可逆操作に関わる spec は**両方**にかける（併存レイヤー、重複コスト許容）。
- **「Fable にレビューさせた」≠ Codex レビュー不要**。Fable 一次通過を Codex 省略の口実にしない。

### ビルトインエージェント

- Explore は `model:"haiku"`（fan-out 検索は低難度）。
- Plan・general-purpose 等その他は model 未指定（メイン inherit）を既定とし、明らかに定型のみ `sonnet` 明示。Plan（高難度）を惰性で haiku に落とさない。
- fork はモデル上書き不可で常に親（メイン）を継承する。
```

- [ ] **Step 3: 挿入結果の検証**

Run: `grep -n '^## モデルルーティング' CLAUDE.md && grep -c 'subagent_type=fable-consult' CLAUDE.md`
Expected: `## モデルルーティング` 節が 1 つ存在し、`subagent_type=fable-consult` を 1 回以上含む。既存 `## Codex 運用` 節が無傷であること（`git diff CLAUDE.md` で Codex 節に変更が無いことを確認）。

- [ ] **Step 4: commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md にモデルルーティング節を追加 (用途別モデル使い分け規約)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: 検証（markdownlint + 実サブエージェント起動 + 同名衝突判別）

**Files:**（新規変更なし。検証のみ）

- [ ] **Step 1: markdownlint**

Run: `bash scripts/check-markdownlint.sh`
Expected: exit 0（agent 定義 3 ファイル + CLAUDE.md が全て pass）。違反が出たら `docs/markdownlint-guide.md` の recipe に従い修正して再実行。修正が発生したら該当ファイルを `git add` + amend or 追加 commit。

- [ ] **Step 2: fable-consult 起動検証（frontmatter 経由）**

`Agent(subagent_type="fable-consult", model 未指定)` で軽量タスク（例: 「あなたの役割と使用モデルを 1 行で述べよ」）を起動する。
Expected: エラーなく応答が返る（frontmatter `model: fable` 経由での起動が成立）。§7 AC「実装後 subagent_type=fable-consult で起動し fable で応答」を満たす。

- [ ] **Step 3: worker 起動検証（一意名で user-level 衝突なし）**

`allaganeye-` prefix により user-level model-router (`~/.claude/agents/` の旧名 worker、Iron Law 記述なし) とは一意名で衝突しない（precedence 非依存。#889 Codex No-ship 対応で改名済み）。
`Agent(subagent_type="allaganeye-haiku-worker")` で「あなたの制約を列挙せよ」を起動する。
Expected: 応答に **「Iron Law」** が含まれる（project-local 定義が起動している確証）。同様に `allaganeye-sonnet-worker` でも「Iron Law」を確認する。

- [ ] **Step 4: Codex 配線不変の確認**

Run: `git diff main -- CLAUDE.md | grep -A2 -B2 'Codex' | head -40`
Expected: `## Codex 運用` 節・Iron Law 6 Pre-flight Step 5 の記述に diff が無い（新節追加のみで既存 Codex 記述は無変更）。

- [ ] **Step 5: 受け入れ条件の逐条セルフ照合**

spec §7 の各 checkbox を diff/ファイルと逐条突合し、全項目を満たすことを確認する（Iron Law 1 の予行）。未達があれば該当 Task に戻る。

---

## Self-Review（この plan を書いた後の照合）

- **spec coverage**: §4.2 成果物 4 点 → Task 1（fable-consult）/ Task 2（2 worker）/ Task 3（CLAUDE.md 節）で網羅。§4.5 ビルトイン規約 → Task 3 Step 2 の「ビルトインエージェント」小節。§5 機構検証 → Task 4 Step 2。§7 AC 8 項 → Task 4 Step 2/3/4/5 で検証。§8 同名衝突 → Task 4 Step 3 + 改名 fallback。
- **placeholder scan**: 各ファイル内容は全文記載。TBD/TODO なし。
- **type consistency**: agent 名は全 Task で `fable-consult` / `allaganeye-sonnet-worker` / `allaganeye-haiku-worker` に統一。CLAUDE.md 節の呼び出し例も同名。
- **gap**: settings.json 変更なし（Global Constraints で明示的に禁止）。実機検証 trigger 非該当を前提メモで明示。
