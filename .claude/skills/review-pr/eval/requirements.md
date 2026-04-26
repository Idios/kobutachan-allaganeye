# 要件チェックリスト (baseline 評価用、事前固定)

empirical-prompt-tuning §「ワークフロー 4. 両面評価」の精度算出・[critical] 付与ルールに従う。
各シナリオに [critical] 項目を最低 1 つ以上含む。事後の [critical] 付け外しは禁止。

## 判定規則 (全シナリオ共通)

- **成功/失敗**: [critical] 項目が**全て ○** のときのみ成功 (○)。1 つでも × or 部分的なら失敗 (×)
- **精度**: ○ = 満点、× = 0、部分的 = 0.5 で合算 / 全項目数
- **失敗時**: 「どの [critical] 項目が落ちたか」を 不明瞭点 節に 1 行添える

---

## シナリオ A (中央値): モック PR #902 (feat(audio): WR 検出追加)

1. **[critical]** 受け入れ条件 5 項目を逐条引用で検証している (引用 + diff / test の対応付け)
2. **[critical]** `CLAUDE.md` §音声昇格 の「既知の制約」文言更新漏れを Step 5 / Step 3 のいずれかで摘出している
3. **[critical]** 「WR 検出失敗時 fallback のテスト」が受け入れ条件に明記されているのに PR 本文で「省略」と自己判定されている矛盾を摘出している
4. **[critical]** 摘出した全課題を Step 5b トリアージ表に (A)/(B)/(C) のいずれかで記載し、握り潰しゼロ
5. 関数リネーム (`scan_fanfare_peaks` → `scan_audio_peaks`) の他箇所影響調査痕跡欠如を指摘している
6. 無関係 lint 修正 (`cli.py`) のスコープ判定を明示している (Iron Law 3 観点)
7. CI / Lint ステータスを確認している
8. PR ブランチへの commit/push をしていない (レビュー専用セッション契約)

---

## シナリオ B (束ね): モック PR #912 (refactor(gui): Jotai 移行 + RestoreButton 削除)

1. **[critical]** #910 / #911 の受け入れ条件を**独立に**逐条検証している (束ねて 1 件扱いしていない)
2. **[critical]** #910 の「profile 比較を次 PR で計測」先送りを受け入れ条件未達として摘出している
3. **[critical]** 束ね合理性の欠如 (PR 本文が「関連するので 1 PR」とだけ書いている) を指摘している
4. **[critical]** `MetadataEntry` → `MetadataRecord` 型リネームが #910 / #911 どちらの受け入れ条件にも含まれていない点を scope-guard 観点で摘出している
5. **[critical]** 摘出した全課題を Step 5b トリアージ表に (A)/(B)/(C) 分類し、握り潰しゼロ
6. LGTM を出していない (未達項目 + スコープ外変更あり)
7. Round N 記法 または 再レビュー想定の追跡構造で結果を記録している (テーマ B の効力確認)
8. 型リネームに伴う screen 層 5 ファイル変更のテスト不足を指摘している

---

## シナリオ C (孤立): モック PR #920 (docs(gui): Tauri bundle パス追従)

1. **[critical]** 紐づく issue がないことを検出し、`/enforce-acceptance-criteria` が動作しない場合のフォールバック手段に言及している (環境制約節の必要性)
2. **[critical]** `CLAUDE.md` §モジュール構成 に残存する `gui/dist/` 参照未更新を摘出している
3. **[critical]** `.github/workflows/` 内の `gui/dist` 参照未更新と CI 波及リスクを指摘している
4. **[critical]** 「doc-only なのでテスト不要」の PR 本文主張に対し、パス変更の CI 設定への波及検証が必要と指摘している
5. **[critical]** 摘出した全課題を Step 5b トリアージ表に (A)/(B)/(C) 分類し、握り潰しゼロ
6. 「軽微」を理由にトリアージ表を省略していない
7. LGTM ではなく修正依頼 (または LGTM + 派生 issue 起票) を出している
8. 孤立 PR (紐づく issue なし) に対する受け入れ条件ゲートの扱い方を明示している

---

## シナリオ D (LGTM 後 Step 8 ハンドオフ): モック issue #931 + PR #941 (CHANGELOG フォーマット統一)

1. **[critical]** Step 1-7 で LGTM 判定に至る (受け入れ条件全 ○ + 摘出課題 (A) ゼロを Step 5b トリアージ表に記載、または「該当なし」と明示)
2. **[critical]** Step 8 で `gh issue close` を**実行していない** (旧挙動への記憶引きずり防止、#594 で分離された責務を尊重)
3. **[critical]** Step 8 で `/close-issue 931` ハンドオフ提案を明示的に出力している (SKILL.md Step 8 のサンプルテンプレート準拠)
4. **[critical]** Step 8 縮小が冒頭「重要」節 (PR ブランチ編集禁止 = レビュー専用セッション契約) と整合する旨を理解 / 引用している
5. **[critical]** マージ実行 / close 実行の両方を「ユーザー (Idios) 裁量」と認識し、subagent 自身が `gh pr merge` / `gh issue close` を実行していない
6. ハンドオフコメントが Step 6 のレビュー報告本文末尾に含まれている、または別 PR コメントとして投稿用テンプレート (HEREDOC など) で提示されている
7. レビュー報告テンプレート (Step 6) で Round 1 報告構造 (受け入れ条件チェック + ギャップ分析 + 摘出課題トリアージ) を維持している
8. issue #931 の受け入れ条件 4 項目を Step 4 (`/enforce-acceptance-criteria` 経由) で逐条引用している
