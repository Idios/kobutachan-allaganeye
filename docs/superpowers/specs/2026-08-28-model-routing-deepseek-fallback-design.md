# Claude 利用不可時の DeepSeek fallback ルーティング 設計

- **日付**: 2026-08-28
- **状態**: Design
- **対象**: allaganeye プロジェクトの開発ワークフロー設定（本ツールの実行時依存ではない。開発時のエージェント運用のみ）
- **前提**: [`2026-07-14-per-use-case-model-routing-design.md`](./2026-07-14-per-use-case-model-routing-design.md)（用途別モデルルーティング）の fallback 層。通常時は同 spec が正。

## 1. 背景・目的

Claude の usage limit 発動などで Claude Code 本体（主エージェント + サブエージェント）が使えない間、開発を止めずに DeepSeek で継続するための運用を定義する。既存の用途別モデルルーティング（難易度・性質によるルーティング）に「可用性」軸を追加するもので、両者は直交する。

## 2. 実現可能性と正直な制約

### 2.1 機構の確認

- **Codex は Claude と独立**した CLI（`codex`）であり、Claude の usage limit に影響されない。ただし **Codex 自身も usage limit になりうる**（2026-08-28 実測）。その場合、Claude 稼働時は既存 C6（superpowers subagent）が、Claude も不可時は DeepSeek V4 Pro が技術/adversarial レビューを直接代行する。
- **DeepSeek は Zed 上で主エージェントとして動く**。読み取り・検索・fetch・subagent 起動（`spawn_agent`）・terminal・ファイル編集が可能（Zed の権限次第）。

### 2.2 正直な制約（false-green の分かれ目）

1. **DeepSeek は Claude Code の subagent になれない**。`.claude/agents/*.md` の `model:` frontmatter が受け付けるのは Claude のエイリアス（`opus` / `sonnet` / `haiku` / `fable` / `inherit`）のみ。したがって fallback は「モデルを差し替える機械的変更」ではなく「**人間（Idios）が手動で切り替えるプロセス規約**」としてしか実現できない。hook による強制ルーティングは機構的に不可能。
2. **fallback 時の skill 実行は「手動追従」**。DeepSeek は Claude Code のスラッシュコマンド（`/review-pr` 等）を invoke できない。`.claude/skills/*/SKILL.md` を read して手順を手動で追従する。
3. **Codex を DeepSeek から呼べるかは terminal 権限に依存**する。Zed が DeepSeek に terminal 権限を付与していれば `codex` CLI を直接実行できる（Codex 本体は Claude 非依存）。付与していなければ既存 tier 3（Idios 手動 invoke）に落ちる。

## 3. 設計

### 3.1 fallback 対応表

| 用途（通常時） | fallback 先 | 実行手段 |
| --- | --- | --- |
| メイン（設計判断・複雑デバッグ・アーキ変更・新機能・統括） | DeepSeek V4 Pro | Zed 上で DeepSeek が主エージェント役 |
| Claude Opus（難易度の高い調査・コーディング・doc 作成。既定メイン） | DeepSeek V4 Pro | 同上（メインと同モデル。fallback では主エージェントが直接担当し、`Agent(model=opus)` 相当の別プロセス委譲はしない） |
| 全体レビュー・相談（Fable 最新） | Codex & DeepSeek V4 Pro の**並列独立クロスレビュー** | Codex + DeepSeek V4 Pro（俯瞰役代行）を独立に回し、主エージェントが突合 |
| 中難度定型（Sonnet 最新） | DeepSeek V4 Flash | Zed 上で DeepSeek V4 Flash が作業 |
| 低難度定型（Haiku 最新） | DeepSeek V4 Flash | 同上 |
| 技術レビュー・相談（Codex） | Codex（レビュアは不変） | fallback 時は companion script ではなく `codex` CLI 直呼び（CLI の version 整合が別途必要）。Codex も usage limit の場合は Claude Fable（Claude 稼働時）or DeepSeek V4 Pro（Claude も不可時） |

### 3.2 Fable fallback（並列独立 + 主エージェント突合）

全体レビュー（Fable 役）は fallback 時、**Codex（技術/adversarial）と DeepSeek V4 Pro（俯瞰）を別レイヤーで並列独立に実行**し、主エージェント（= DeepSeek V4 Pro）が両者の指摘を突合・トリアージする。既存の「Fable と Codex の棲み分け（併存レイヤー）」を踏襲し、Fable の席に DeepSeek が入る形。直列（片方の結果をもう片方が再レビュー）ではない。なお俯瞰役（DeepSeek V4 Pro）は主エージェントと同モデルのため、異モデル視点は Codex 側のみが提供する（既存 spec §8 の「メイン=Fable で異モデル視点喪失」と同型の制約）。

### 3.3 Claude Code 固有機構の置換表

| Claude Code 固有機構 | fallback（Zed + DeepSeek）での置換 |
| --- | --- |
| `Agent` tool（subagent dispatch） | Zed の `spawn_agent`（**model 指定不可** → 委譲先モデルは Idios が手動で選ぶ） |
| `AskUserQuestion` | 散文での確認依頼 |
| `superpowers:requesting-code-review` | DeepSeek 自身が code review を直接実施 |
| `/review-pr` 等のスラッシュコマンド | SKILL.md を read して手動追従 |
| `codex-companion.mjs` | `codex` CLI 直呼び（terminal 権限依存） |

### 3.4 fallback notice（記録義務、C6 同型）

Claude fallback で作成した成果物（PR 本文 / spec / doc / 実装）には、Codex fallback notice (C6) と同型の notice を必ず明示し、Claude/Opus/Fable レビュー済との誤認を防ぐ。検証可能性のため、どの DeepSeek モデルで作成したかをプレースホルダで残す:

```text
> **Claude fallback notice**: 本成果物は Claude usage limit のため
> DeepSeek <V4 Pro | V4 Flash> で作成しました。
> Claude 復旧後の再レビューを推奨します。
```

限界: 手動切替のため、notice を付け忘れると「Claude レビュー済」と誤認しうる。C6 と同様に記録義務で緩和するが、hook による機械強制はできない（§7 参照）。

## 4. 成果物

1. `docs/superpowers/specs/2026-08-28-model-routing-deepseek-fallback-design.md`（本 spec）
2. CLAUDE.md §モデルルーティング への fallback 小節（対応表 + 正直な制約 + notice）
3. `.claude/agents/*.md` 3 本への「ロール仕様はモデル非依存・fallback 時は DeepSeek が読む」注記
4. `docs/l2-workflow.md` への §Claude fallback（C6 の隣）

## 5. スコープ外（YAGNI / Iron Law 3）

- hook による強制ルーティングは作らない（機構的に不可能。アドバイザリ + 記録義務で運用）
- `.claude/skills/*/SKILL.md` 本体の改修はしない（fallback は SKILL.md の手動追従で成立するため）
- DeepSeek を Claude Code の subagent として登録する仕組みは作らない
- Zed への terminal 権限付与手順そのものの設計（Idios の環境設定に属する）

## 6. 受け入れ条件

- [ ] 本 spec が存在し、2026-07-14 routing spec との関係（fallback 層）が明記されている
- [ ] CLAUDE.md §モデルルーティング に fallback 対応表・正直な制約・fallback notice が追記されている
- [ ] `.claude/agents/allaganeye-fable-consult.md` / `-sonnet-worker.md` / `-haiku-worker.md` にモデル非依存のロール仕様である旨が記述されている
- [ ] `docs/l2-workflow.md` に §Claude fallback があり、Codex fallback (C6) と同型の notice テンプレート + 復旧後手順が書かれている
- [ ] `.claude/skills/*/SKILL.md` 本体に変更を加えていない
- [ ] fallback が「hook 強制ではなく手動切替 + 記録義務」であることが明記されている

## 7. リスク・留意点

- **アドバイザリの限界**: 手動切替のため、Idios が fallback notice を付け忘れると「Claude レビュー済」と誤認しうる。C6 と同じく記録義務で緩和するが、機械強制はできない。
- **モデル名の churn**: `DeepSeek V4 Pro` / `V4 Flash` は現行モデル名。モデル更新時は本 spec / CLAUDE.md / l2-workflow の 3 箇所を同期する。
- **Codex 呼び出しの環境依存**: terminal 権限の有無で「並列独立クロスレビュー」の実効性が変わる。権限が無い場合は Fable fallback の Codex 側が tier 3（Idios 手動）になる。
