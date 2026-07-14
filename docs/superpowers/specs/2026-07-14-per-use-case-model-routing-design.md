# 用途別モデルルーティング 設計 (per-use-case model routing)

- **日付**: 2026-07-14
- **状態**: Design (承認済み方向性、spec レビュー段階)
- **対象**: allaganeye プロジェクトの開発ワークフロー設定（本ツールの実行時依存ではない。開発時のエージェント運用のみ）
- **関連 issue**: 未起票（実装計画 = writing-plans で起票方針を決める）

## 1. 背景・目的

allaganeye の開発では、タスクの難易度・性質に幅がある（設計判断・複雑デバッグ〜定型的な検索・フォーマット修正まで）。用途に応じてサブエージェント/レビューのモデルを使い分け、(a) 高難度は高性能モデル、(b) 定型は軽量モデルでトークン最適化、(c) レビュー・相談は観点別に適切なレビュアへ振り分ける運用を確立する。

### 要望（ユーザー）

| 用途 | 割り当て |
| --- | --- |
| メインエージェント | Opus 最新（ただしユーザーが都度選択。高難度と最初から分かるセッションは Fable） |
| 技術的なレビュー・相談 | Codex |
| 全体的なレビュー・相談 | Fable 最新 |
| 定型的な調査・作業 | Sonnet / Haiku 最新 |

## 2. 実現可能性（機構の確認）

Claude Code には用途別モデル切替の機構が揃っており、本要望は実現可能（claude-code-guide で公式仕様確認済み）。

1. **サブエージェント定義** `.claude/agents/*.md` の frontmatter `model:` に `opus` / `sonnet` / `haiku` / `fable` / `inherit` / フルモデル ID を指定可能。project-level (`.claude/agents/`) と user-level (`~/.claude/agents/`) の両方をサポート。
2. **エイリアス指定（`fable`/`opus`/`sonnet`/`haiku`）は各系統の「最新モデル」に自動追従**する。→「最新モデル」要件を満たすため、フル ID 固定はしない。
3. **Agent tool の `model` パラメータ**で呼び出しごとに上書き可能。**agent 定義の frontmatter より優先**する。→ ビルトイン（Explore 等）の上書きに使える。
4. **メインセッションのモデル**は settings.json `model` / `/model` / 環境変数で決まる。本設計では **固定しない**（ユーザーが都度選択）。
5. **Codex は「モデル」ではなくプラグインツール**。`model:` には指定できない。allaganeye では既に companion script + 3-tier invocation で技術/adversarial レビューに配線済み（CLAUDE.md §Codex 運用、Iron Law 6 Pre-flight Step 5）。

### 正直な制約

ルーティングは本質的に**アドバイザリ**である。Claude Code には「このタスク種別は必ずモデル X」を hook で強制する仕組みはない。担保できるのは 3 層のみ:

1. agent 定義の `model:` frontmatter
2. CLAUDE.md のガイダンス（主エージェントが従う）
3. 主エージェントの規律

hook による強制ルーティングは本設計のスコープ外（YAGNI）。

## 3. 前例（ユーザー既存資産）

- `idios-claudecode-tools/tools/model-router/` — `haiku-worker.md` / `sonnet-worker.md`（`model:` frontmatter 付き）+ 難易度→モデル対応表 + `setup.sh`（`~/.claude/agents/` へ配置）。本設計はこれを **Fable/Codex レイヤーまで拡張し、allaganeye プロジェクト内に閉じた形で再構成**する。
- `idios-claudecode-tools/templates/multi-agent/` — 役割ベース（director/engineer/lead/tester）worktree テンプレート。**今回は流用しない**（用途別モデルのみに絞る）。

## 4. 設計

### 4.1 ルーティング対応表

メインセッション（ユーザー選択、既定 Opus / 高難度は Fable）から**委譲**する先の使い分けを定義する。

| 用途 | モデル/ツール | 実現手段 | 呼び出し |
| --- | --- | --- | --- |
| メイン（設計判断・複雑デバッグ・アーキ変更・新機能・統括） | ユーザー選択（既定 Opus 最新 / 高難度 Fable 最新） | セッションモデル | 固定しない |
| 技術レビュー・相談（バグ/セキュリティ/GPU fallback/encoding/adversarial） | Codex | 既存 3-tier companion script | `codex-companion.mjs review\|adversarial-review`（**不変**） |
| 全体レビュー・相談（設計方針/UX/ドキュメント整合/受け入れ条件妥当性/俯瞰） | Fable 最新 (`fable`) | `.claude/agents/fable-consult.md` | `Agent(subagent_type=fable-consult)` |
| 中難度定型（原因既知バグ修正/テスト作成/スコープ明確 refactor/doc 更新） | Sonnet 最新 (`sonnet`) | `.claude/agents/sonnet-worker.md` | `Agent(subagent_type=sonnet-worker)` |
| 低難度定型（検索/リネーム/フォーマット/boilerplate/要約/情報収集） | Haiku 最新 (`haiku`) | `.claude/agents/haiku-worker.md`、ビルトイン Explore は `model:haiku` 上書き | `Agent(...)` |

**Fable と Codex の棲み分け（レイヤー併存）**:

- **Codex**: コード技術詳細（バグ、セキュリティ、GPU fallback 文字列マッチ、encoding boundary、adversarial pass）。
- **Fable**: 非コード寄り・俯瞰（設計方針の妥当性、UX、ドキュメント整合、受け入れ条件の網羅性/曖昧性、スコープ判断の相談）。
- 両者は**別レイヤーで併存**。既存 Codex 配線（Iron Law 6 Pre-flight Step 5、3-tier）は不変。Fable は Codex を置換しない追加レイヤー。

**灰色ゾーンの判定基準**（実運用で「どっち？」を避けるため明文化）:

- **指摘の修正先が「コード/テスト diff」になるもの → Codex**、**「文書・方針・プロセス」になるもの → Fable**。
- **invariant / 不可逆操作に関わる spec は両方**にかける（併存レイヤーなので重複コストは許容）。実績上 Codex は spec 段階の invariant 設計（#805/#848 の Phase 分割境界）や受け入れ条件の実質性（#844 false-green gate）で成果を挙げてきた。
- **「Fable にレビューさせた ≠ Codex レビュー不要」を明記する**。Fable 一次通過を Codex 省略の口実にしない。

### 4.2 成果物

1. `.claude/agents/fable-consult.md`（`model: fable`）
2. `.claude/agents/sonnet-worker.md`（`model: sonnet`）
3. `.claude/agents/haiku-worker.md`（`model: haiku`）
4. CLAUDE.md 新節「## モデルルーティング（用途別モデル使い分け）」

settings.json でのメインモデル固定は**行わない**。

### 4.3 agent 定義（内容案）

> **注記**: 本節は設計時の内容案。**実装後の最終版は `.claude/agents/*.md` が SSoT**。spec 側から再コピーして退行させないこと（Fable 最終レビュー Minor 反映）。

#### `.claude/agents/fable-consult.md`

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
- spec/design doc 執筆完了後・ユーザーレビュー前（＝ brainstorming のドッグフーディングを恒常化）
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

#### `.claude/agents/sonnet-worker.md`

```markdown
---
name: sonnet-worker
description: 中難度の定型タスク（原因既知バグ修正/テスト作成/スコープ明確 refactor/doc 更新/依存更新）を実行するワーカー。
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

#### `.claude/agents/haiku-worker.md`

```markdown
---
name: haiku-worker
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

### 4.4 CLAUDE.md 新節（骨子）

新節「## モデルルーティング（用途別モデル使い分け）」を、既存「## Codex 運用」の近傍に追加する。内容:

- 4.1 のルーティング対応表
- 呼び出し規約:
  - 全体レビュー・相談 → `Agent(subagent_type=fable-consult)`。**推奨トリガー地点**（spec 執筆後のユーザーレビュー前 / 選択肢が割れたとき / 受け入れ条件新規策定 issue の起票前）も明記
  - 中難度定型 → `Agent(subagent_type=sonnet-worker)`
  - 低難度定型 → `Agent(subagent_type=haiku-worker)`、ビルトイン Explore 起動時は `model: "haiku"` を渡す
  - 技術レビュー・相談 → 既存 Codex（§Codex 運用へ参照）
- 設計原則: エイリアスで最新追従 / アドバイザリ（3 層）/ Codex 不変・Fable は別レイヤー / メインモデルは固定せずユーザー選択
- Codex との棲み分け（Fable=非コード俯瞰 / Codex=コード技術、判定は「修正先が diff か文書か」、Fable 済み≠Codex 不要）を明記
- 本プロジェクトは project-local の agent 定義を使う（user-level `~/.claude/agents/` の同名定義より優先）旨を明記

### 4.5 ビルトインエージェントの扱い

ビルトインは agent 定義で上書きせず、**Agent tool の `model` パラメータ**で都度指定する（param が定義より優先されるため確実）。既定則:

- **Explore は `model: haiku`**（fan-out 検索は低難度）。
- **Plan・general-purpose 等その他ビルトインは model 未指定（メインを inherit）を既定**とし、明らかに定型な場合のみ `sonnet` を明示する。Plan（設計立案 = 高難度）を惰性で haiku に落とさない。
- **fork はモデル上書き不可で常に親（メイン）を継承**する点に注意。

CLAUDE.md にこの規約を書く。

## 5. Fable ドッグフーディング（要望対応）

本 spec を執筆後、**実際に `fable-consult`（`model: fable`）サブエージェントを起動して本設計をレビュー**させる。目的は 2 つ:

1. 設計の俯瞰レビュー（見落とし/矛盾/スコープ）
2. **機構が実際に動くことの検証**（fable エイリアスで subagent が起動できること）

指摘を反映してからユーザーレビューへ回す。

**検証状況（2026-07-14 時点）**: 本 spec レビューは `Agent(model=fable)` param 経由で実行済み → **`fable` エイリアスで subagent が起動・応答できることは実証済み**（High/Med 指摘を取得し反映）。ただし frontmatter `model: fable`（`subagent_type=fable-consult` 経由）での起動は実装後に別途検証する（§7 AC 参照）。

## 6. スコープ外（YAGNI / Iron Law 3）

- hook による強制ルーティングは作らない（アドバイザリで運用）
- `/review-pr`・`/iterate-review` skill 本体の改修はしない（Fable の pipeline 組込みは別途検討）
- `templates/multi-agent` の役割ベース worktree 構成は流用しない
- settings.json でのメインセッションモデル固定はしない
- user-level `~/.claude/agents/` への配置・model-router との統合はしない（本件は allaganeye プロジェクト内に閉じる）

## 7. 受け入れ条件

- [ ] `.claude/agents/fable-consult.md` が存在し `model: fable`、read-only tools（Edit/Write/Bash を含まない）、推奨起動トリガー、Codex との棲み分けが記述されている
- [ ] `.claude/agents/sonnet-worker.md` が存在し `model: sonnet`、Iron Law 整合の制約（スコープ外禁止/曖昧点は独断禁止/subagent 起動禁止）が記述されている
- [ ] `.claude/agents/haiku-worker.md` が存在し `model: haiku`、Iron Law 整合の制約が記述されている
- [ ] CLAUDE.md に「モデルルーティング」節があり、対応表・呼び出し規約（fable トリガー地点含む）・Codex 棲み分け（判定基準 + Fable 済み≠Codex 不要）・アドバイザリ明記・メインモデル非固定・project-local 優先を含む
- [ ] エイリアス指定（フル ID 固定なし）で最新追従することが明記されている
- [ ] 実装後、`subagent_type=fable-consult`（frontmatter 定義経由）で起動し fable で応答することを確認（param 経由の検証とは別物）
- [ ] `sonnet-worker` / `haiku-worker` が **project-local 定義で**起動することを実測確認（user-level `~/.claude/agents/` に同名定義が存在する状態で、定義固有マーカー等で判別。project > user 優先を前提化しない）
- [ ] 既存 Codex 配線（Iron Law 6 Pre-flight Step 5、3-tier）に変更を加えていない

## 8. リスク・留意点

- **アドバイザリの限界**: 主エージェントが規律を破ればルーティングは効かない。CLAUDE.md 明記と agent 定義で担保するが、hook 強制はしない（意図的）。特に fable-consult は Codex のような必須フック地点がないため形骸化しやすい → §4.3 の推奨トリガー地点を CLAUDE.md にも明記して発火動機を与える。
- **model-router との重複（silent 誤作動リスク）**: user-level に既存 `haiku-worker` / `sonnet-worker` がある。project-local を優先させる想定だが、precedence を前提化せず §7 AC で実測検証する（このプロジェクトが繰り返し学んだ「弱い前提の silent 誤作動」クラス）。検証で project-local が勝たない場合は **agent 名を変えて衝突自体を消す**（例: `worker-sonnet` / `worker-haiku`）ことを fallback とする。
- **命名の将来 churn**: `sonnet-worker` / `haiku-worker` はモデル名を焼き込んでいるため、将来ルーティングを変えると名前ごと churn する弱点がある。可視性の実利を優先して現案維持だが、認識しておく。
- **メインが Fable のセッション**: 高難度セッションでメイン = Fable の場合、`fable-consult` はメインと同モデルになる。**コンテキスト独立の価値は残るが、異モデル視点という価値は失われる**。重要案件では Codex 側レビューで補完する。
- **retrospective 条項**: v0.3.0 リリース後（または導入から数週間後）に fable-consult / worker の実呼び出し実績を振り返り、形骸化していれば hook 強制化 or 廃止を再検討する。アドバイザリ運用（hook 見送り）の再評価点をここに固定する。
