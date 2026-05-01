# Iteration 2 — 再評価レポート

**日時**: 2026-04-24
**対象 skill**: `.claude/skills/review-pr/SKILL.md` (改修後 = Iter 1 新出 5 件の細部判断基準を追記)
**subagent model**: sonnet
**dispatch 方式**: 新規 subagent 3 体を並列 `run_in_background: true` (empirical §「同じ subagent を使い回そう」Red Flag に従い Iter 0 / Iter 1 の agent は再利用せず)

---

## サマリ

| シナリオ | 判定 | tool_uses | duration_ms | Iter 1 新出検証 |
| --- | --- | --- | --- | --- |
| A (中央値) | 修正依頼 (ブロッカー 2 + 追加 4) | 3 | 49454 | 1/1 **解消** |
| B (束ね) | 修正依頼 (ブロッカー 3 + 追加 3) | 4 | 61948 | 3/3 **解消** |
| C (孤立) | 修正依頼 (ブロッカー 3 + 派生 1) | 4 | 44578 | 1/1 **解消** |

**結果**: Iter 1 新出 5 件すべて解消。全 subagent が追記箇所を明示的に参照して裁量補完なく判定。

---

## Scenario A (中央値) — Iter 2

- **agent_id**: `af373aca42dfda583`
- **検証対象**: `Closes` / `Fixes` / `Resolves` キーワード不在チェックを §B fallback 時にも明示スキップ可か

### 検証結果

- **skill 参照箇所**: §B「`/enforce-acceptance-criteria` 実行不可」の**項目 4**
- **判断**: **解消**
- **根拠**:
  - Iter 1 で曖昧だった「§B fallback 時にスキップ可か」が、§B 項目 4 で明示的に「必須チェックとして実施、省略しない」と記述された
  - enforce-ac が動く場合 (二重チェック → スキップ可) と fallback 時 (自動検証なし → 必須) の条件分岐が明確
  - モック PR #902 は `/enforce-acceptance-criteria` gate 未実行 (§B fallback 該当) → 項目 4 に従い `Closes` キーワード不在を手動確認する判断が一義的に導けた
  - PR 本文で `Refs #901` のみ確認 → PASS と判定可能
  - Iron Law 1 違反 (「自動検証がないから省略」) の合理化余地を skill 側で事前に塞いでいる

### 残存する裁量補完 (Scenario A 関連)

Iter 1 並記の 2 件 (`cli.py` の (A)/(B) 二重構造表現のズレ、`/test-pr` 依頼の (A) vs 検証推奨の境界) は本 issue (#563) スコープ外のため未対応。Step 5b 典型ケース表 / Step 6 検証推奨セクションで実運用上の判断材料は提供されている。

---

## Scenario B (束ね) — Iter 2

- **agent_id**: `a2de8795bb6b65aa4`
- **検証対象**: (1) grep 検証の判定水準 / (2) scope-guard 投げ先 / (3) diff 外 doc 確認

### 検証結果

#### 1. grep 検証の判定水準

- **skill 参照箇所**: §D 項目 4 サブ項目 (i)-(iv)。特に「(ii) grep 結果なし + CI typecheck green (pyright / tsc) → 実質的に未使用と判定可、追加対応不要」
- **判断**: **解消**
- **根拠**: RestoreButton.tsx 削除 (#911 条件 2) について、grep で参照なし + CI typecheck green (tsc) を (ii) に該当すると判定し、追加対応不要として 911-2 を ○ 認定できた。Iter 1 では「CI typecheck green を代替証拠として良いか曖昧」だった点が §D 項目 4 の明示条件分岐で解消。動的 import なし (React 静的 import) のため (iv) 該当せず、裁量補完なし。

#### 2. scope-guard 発動時の AskUserQuestion 投げ先

- **skill 参照箇所**: §修正依頼コメント投稿 末尾「補足: scope-guard 発動時の AskUserQuestion 投げ先」節
- **判断**: **解消**
- **根拠**: `MetadataEntry` → `MetadataRecord` リネームは #910/#911 の受け入れ条件外で scope-guard 典型ケース該当。Iter 1 では「PR 作成者 or Idios」不明瞭だったが、補足節で「ユーザー (Idios)」と明示されたため投げ先が確定。scope-guard skill §Step 3 (人間メンテナ判断 a/b/c ゲート) と一貫性あり、裁量補完なし。

#### 3. diff 外 doc 確認の処置分類

- **skill 参照箇所**: Step 5「コード / テスト変更 PR の場合」末尾の「diff 外 doc の確認ができない場合の処置」節
- **判断**: **解消**
- **根拠**: docs/design/README.md の Jotai 移行メモが profile 比較を含まない件について、レビューセッション単独では判断困難だが「確認できない場合は独断 skip せず (A) で依頼」方針が確定。Iron Law 3/5 参照も明記され、「保守的判断」で独断 skip する誘惑が封じられた。裁量補完なし。

### 残存する裁量補完 (Scenario B 関連)

- §D 項目 4 (ii) の CI typecheck green 依拠は CSS Module / 動的 class 参照 (文字列連結) 時に検出漏れの可能性 — 本モックでは該当せず影響軽微。次 Iter で「静的文字列参照のみ対象」補足の検討余地あり
- AskUserQuestion 投げ先補足は §修正依頼コメント投稿末尾にあるが、Step 5b 典型ケース表 (軽微スコープ外行) からの参照リンクがあると迷子になりにくい

---

## Scenario C (孤立) — Iter 2

- **agent_id**: `adcddc0da8f956d4b`
- **検証対象**: CI 波及の (A) vs (B) 判定における「波及が大きい」の定量基準

### 検証結果

- **skill 参照箇所**: Step 5b 典型ケース表「doc 変更 PR で発見した CI 設定との矛盾」行の (A) 目安 / (B) 目安
- **判断**: **解消**
- **根拠**:
  - CI YAML の `gui/dist` 参照数 = 1 ファイル
  - 追従修正箇所数 = CI YAML 1 箇所 + CLAUDE.md 1 箇所 = 合計 2 箇所
  - GUI / CLI / 検知パイプラインへの連鎖修正 = なし (path 文字列置換のみ)
  - GPU / 音声統合テストの再実行工数 = 不要 (doc-only PR)
  - → **(A) 目安「CI YAML 1-2 箇所の path 書換え / doc 追従 1-2 箇所」に完全合致**
  - → 迷いなく (A) PR コメントに定量判定できた (Iter 1 では裁量判断が残っていた部分が解消)

### 残存する裁量補完 (Scenario C 関連)

- AskUserQuestion の escalation 閾値 (例: 「CI YAML が 3 ファイル以上 かつ 連鎖なし」のような中間ケース) は依然として裁量が残る可能性があるが、本シナリオでは発生せず

---

## 総合判定

- **Iter 2 改修の効果**: Iter 1 新出 5 件の細部判断基準が全件解消。3 subagent が skill 記述を明示的に参照して裁量補完なく判定
- **empirical 収束**: 本 Iter で新たな構造的欠陥 / 細部不明瞭点の追加発生なし。skill 改修サイクルは本 Iter で完了可能
- **次 Iter (将来) の検討事項**:
  1. `/test-pr` 依頼の処置分類 (A) vs 検証推奨セクションの関係明文化 (Scenario A 派生)
  2. §D 項目 4 (ii) の「静的文字列参照のみ対象」補足追加 (Scenario B 派生、CSS Module / 動的 class 対応)
  3. Step 5b 典型ケース表 (軽微スコープ外行) からの §修正依頼コメント投稿 補足節への参照リンク (Scenario B 派生)
  4. Round N 収束判定 (Step 7a) の実機発散時運用検証 (Scenario B 派生、将来の Iter 3 モック想定)

いずれも本 issue (#563) スコープ外、別途 skill 改善 issue で追跡可 (P3-low)。

---

## 参考

- [iter_0_baseline.md](iter_0_baseline.md) — Iter 0 詳細
- [iter_1_revaluation.md](iter_1_revaluation.md) — Iter 1 詳細
- [summary.md](summary.md) — 全 Iter 横断サマリ
- raw subagent 結果は session transcript 保持 (#565 方針 (c) 現状維持決定)
