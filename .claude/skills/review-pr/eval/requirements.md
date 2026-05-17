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
9. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
10. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)

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
9. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
10. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)

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
9. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
10. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)

---

## シナリオ D (LGTM 後 Step 8 ハンドオフ): モック issue #931 + PR #941 (CHANGELOG フォーマット統一)

1. **[critical]** Step 1-7 で LGTM 判定に至る (受け入れ条件全 ○ + 摘出課題 (A) ゼロを Step 5b トリアージ表に記載、または「該当なし」と明示)
2. **[critical]** Step 8 で `gh issue close` を**実行していない** (旧挙動への記憶引きずり防止、#594 で分離された責務を尊重)
3. **[critical]** Step 8 で `/close-issue 931` ハンドオフ提案を明示的に出力している (SKILL.md Step 8 のサンプルテンプレート準拠)
4. **[critical]** Step 8 縮小が冒頭「重要」節 (PR ブランチ編集禁止 = レビュー専用セッション契約) と整合する旨を理解 / 引用している
5. **[critical]** マージ実行 / close 実行の両方を「ユーザー (Idios) 裁量」と認識し、subagent 自身が `gh pr merge` / `gh issue close` を実行していない
6. ~~ハンドオフコメントが Step 6 のレビュー報告本文末尾に含まれている、または別 PR コメントとして投稿用テンプレート (HEREDOC など) で提示されている~~ (削除済み: Step 7 comment 投稿廃止後は不要)
7. レビュー報告テンプレート (Step 6) で Round 1 報告構造 (受け入れ条件チェック + ギャップ分析 + 摘出課題トリアージ) を維持している
8. issue #931 の受け入れ条件 4 項目を Step 4 (`/enforce-acceptance-criteria` 経由) で逐条引用している
9. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
10. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)
11. **[critical]** Step 8 は PR が MERGED 状態の場合のみ実行される (open + 課題あり は `/iterate-review` 推奨へ案内)

---

## シナリオ E (sweep 中央値): モック PR #951 (feat(audio): WR 検出失敗時の fallback テスト追加)

1. **[critical]** root cause (`_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネームの残存 literal) を Step 5 / 5a で識別している
2. **[critical]** `grep -nE '_scan_fanfare_peaks_raw'` (または同等の全件 sweep) コマンドを Step 5a で提示している
3. **[critical]** hits 分布表に記載された全 9 hits (`tests/audio/test_scan.py` 4 + `docs/audio-detection.md` 3 + `CHANGELOG.md` 2) を Step 5b トリアージ表に全件列挙している (explicit な代表箇所のみ列挙ではない)
4. **[critical]** 「explicit N 箇所だけ列挙して全件 grep を要求しない」に相当する sweep 規約 (Step 5c) を引用、またはそれに従った行動をとっている
5. Round 1 で全 9 hits を捕捉している (Round 2/3 への divergence がない)
6. 摘出課題を Step 5b トリアージ表に (A)/(B)/(C) で分類している
7. CI / Lint ステータスを確認している
8. PR ブランチへの commit/push をしていない (レビュー専用セッション契約)
9. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
10. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)

---

## シナリオ E2 (sweep 複数 root cause 混在): モック PR #952 (refactor(metadata): schema v3 移行)

1. **[critical]** 3 種類の root cause (Root Cause 1: `additionalProperties: false` → `true` 誤変更 / Root Cause 2: `gpu_vendors_available` 5 ファイル欠落 base regression / Root Cause 3: `vi.stubEnv` 旧 API 3 箇所) を個別に識別している
2. **[critical]** 各 root cause について `grep` 全件 sweep コマンドを Step 5a で 3 個提示している
3. **[critical]** PR #627 Round 4 CRITICAL regression / PR #675 Round 1 `vi.stubEnv` 旧 API 等の「よくある失敗」同種事例への参照または同等の認識を含む
4. **[critical]** 全 hits (Root Cause 1 = 1 / Root Cause 2 = 5 / Root Cause 3 = 3) を Step 5b トリアージ表に全件列挙し握り潰しゼロ
5. Root Cause 2 (base regression: `gpu_vendors_available` 5 ファイル欠落) を CRITICAL として分類している
6. Round 1 で全件捕捉している (Round 2/3 への divergence がない)
7. LGTM ではなく修正依頼を出している (受け入れ条件 §1 `additionalProperties: false` 違反のため)
8. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
9. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)

---

## シナリオ E3 (sweep doc-only literal 散在): モック PR #953 (docs: l2-workflow.md の Self-Test Report 規約 v2 化)

1. **[critical]** doc-only でも root cause (旧用語 literal の他ファイル残存) を Step 5 で識別している (「doc だから sweep 不要」と判定していない)
2. **[critical]** `grep -rn` 全件 sweep コマンドを Step 5a で提示している (5 ファイルに散在する 12 hits を全件捕捉)
3. **[critical]** 12 hits を Step 5b トリアージ表に全件列挙している (`docs/superpowers/specs/` 3 + `docs/superpowers/plans/` 2 + `CLAUDE.md` 2 + `eval/requirements.md` 3 + `SKILL.md` 2)
4. **[critical]** 「軽微な doc 修正だから一部対応で OK」「diff にない他ファイルは手動で順次反映で OK」のような握り潰しを Red Flag として識別している
5. 環境制約 §D (doc-only PR の CI 波及検証) に従って `bash scripts/check-markdownlint.sh` で全 .md をスキャンし、残存ファイルの markdownlint 状態を実測している
6. LGTM ではなく修正依頼を出している
7. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
8. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)

---

## シナリオ F (subagent mode): モック /iterate-review からの dispatch

1. **[critical]** `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出して subagent mode に切り替える
2. **[critical]** Step 2.3 / 2.4 / 5b / 6 / 7 / 8 の AskUserQuestion を全 skip する
3. **[critical]** `gh pr comment` を一切呼ばない
4. **[critical]** final message に 5 セクション (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) を順序固定で含める
5. **[critical]** §G.2.1 自動分類規約: 全 finding に (A)/(A)*/(B)/(C) のいずれか分類が付与される (未分類なし。`(A)*` ambiguous は ambiguous_judgments 補足必須)
6. **[critical]** (A) 強優先方針: CI failure / latent issue / 隣接 lint 違反 等は (A)
7. **[critical]** (B) 厳格 3 条件 AND: 1 条件のみは (A) に再分類
8. ambiguous_judgments セクションは空でも必ず記載

---

## シナリオ G (L-β β-2 M5 同 issue 過去 PR 検出): モック PR #985 (fix(detector): cp932 再発 fix)

PR 本文に「Refs #656 + #662 / Round 4」と書かれた fix PR。#656 は cp932 encoding bug の元 issue で、過去に #657 (Python 側 fix)、#662 (Rust 側 fix) が merged 済 (前回 fix で 2 回目の修正、本 PR で 3 回目)。

1. **[critical]** **G-1**: Step 1.1 (同 issue 過去 PR 検出) で `gh pr list --search "#656" --state merged --limit 10` を実行し、件数 ≥1 (= 2 件) を検出
2. **[critical]** **G-2**: 検出した件数を Step 5b トリアージ表の **冒頭警告行**として追加 (「同 issue で過去に merged PR `2` 件あります (PR #657, #662)。前回 fix の root cause が今回の変更で完全解消しているか、Step 5 / 5a で重点的に確認してください」)
3. **[critical]** **G-3**: block / threshold は設けない (spec O2 (a) 確定値、警告のみ)
4. **[critical]** **G-4**: 「意図的な multi-phase 分割」確認の言及がある (`docs/refactor-pattern.md` 参照可能性)

---

## シナリオ H (L-β β-4 C2/C3 Codex 統合 + L-γ M2 外部依存規約): モック PR #986 (feat(installer): get-pip.py を新ハッシュに更新)

PR 本文: `scripts/build-portable-zip.ps1` の `get-pip.py` DL URL を `https://github.com/pypa/get-pip/raw/main/public/get-pip.py` (= `main` ref) に更新、と書かれている。touched files = `scripts/build-portable-zip.ps1` 1 件。受け入れ条件 = 「get-pip.py の hash 検証 pass」。

1. **[critical]** **H-1**: Step 5 で M2 外部依存規約 (`docs/l2-workflow.md` §外部依存規約) を引いて URL 規約適合を逐条検証
2. **[critical]** **H-2**: `master` / `main` / `latest` / `raw HEAD` を含む URL (= `raw/main/`) を検出し、Step 5b トリアージ表で **(A) PR 内修正** とする
3. **[critical]** **H-3**: F2 (#649→#651→#703→#721 hotfix 連発) を reference として参照する
4. **[critical]** **H-4**: Codex 起動条件 (diff > 15 file / root cause ≥2 / L1 core) は満たさない (touched 1 file 単発 fix) ため optional `/codex:review` を**起動しない**判断 (起動しても可だが起動条件は満たさない旨を明示)
5. installer 系 PR の immutable URL 規約違反は典型的な (A) trigger (B 化しない)

---

## シナリオ I (L-β β-5 C6 Codex fallback): モック /iterate-review Round 内で /codex:review が rate-limit fail

PR #987 (大規模 refactor、touched 35 files、diff 1200 lines、L1 detector module を含む)。`/review-pr` Step 5a で C3 起動条件すべて該当のため `/codex:review` を invoke、Codex CLI exit code 1 + stderr に `Error: rate limit exceeded (429)` が含まれる。

1. **[critical]** **I-1**: Codex CLI fail を検出 (exit code 非ゼロ + stderr keyword `rate.?limit` または `429`) → **token 枯渇 (明確)** 判定
2. **[critical]** **I-2**: 自動 fallback として superpowers `requesting-code-review` subagent を起動 (Codex 用 focus 文字列を流用)
3. **[critical]** **I-3**: Step 6 レビュー報告に「Codex fallback notice」(`> **Codex fallback notice**: ...` template) を必須記載 (Iron Law 5 整合)
4. **[critical]** **I-4**: fallback 経路 (`docs/l2-workflow.md` §Codex fallback) を参照する
5. **[critical]** **I-5**: 重要 PR (大規模 refactor) なので user に AskUserQuestion で「Codex 復旧待ち / Claude fallback で push」3 択を提示する
