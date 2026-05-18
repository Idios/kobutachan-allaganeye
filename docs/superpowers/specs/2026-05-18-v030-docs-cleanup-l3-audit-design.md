# v0.3.0 docs cleanup + 新 L3 整合性監査 + PR 課題サマリ規約 design (2026-05-18)

> **目的**: `v0.3.0` 開発期間中の doc 整理として、(i) 3 件の P3 deferred doc issue ([#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) / [#635](https://github.com/Idios/kobutachan-allaganeye/issues/635) / [#654](https://github.com/Idios/kobutachan-allaganeye/issues/654)) を消化、(ii) 新 L3 redefinition (PR [#776](https://github.com/Idios/kobutachan-allaganeye/pull/776)) 後の active docs 整合性を網羅監査、(iii) 不要となっている doc / source のクリーンアップ機会を発見・処理、(iv) PR template に「## 課題サマリ」セクションを新設し「期待値 vs 現状 vs 修正方針」が一目で読める PR 本文規約を確立する。

## 1. 背景

`develop-0.3.0` を 2026-05-16 に cut し ([#774](https://github.com/Idios/kobutachan-allaganeye/pull/774) v0.2.1 リリース後)、L3 redefinition を PR [#776](https://github.com/Idios/kobutachan-allaganeye/pull/776) (2026-05-18) で実施した。Wave A の 8 ファイル (`CLAUDE.md` / `docs/design-overview.md` / `docs/release-process.md` / `README.md` / `docs/cli-spec.md` / `docs/reference-videos.md` / `docs/issue-policy.md` / `docs/testing-guide.md`) は更新済み、Wave B (issue rename) も完了済み。

一方で以下が残っている:

- **P3 deferred doc** 3 件 (#634 / #635 / #654) — v0.2.0 / v0.2.1 期間に observation 起票したが対応が後送りになっている
- L3 redefinition 後の **active docs 全体整合性** の網羅検証は未実施 (Wave A は touch 対象 8 ファイルへの編集が主で、touch 対象外の active docs を網羅的に grep 検証していない)
- v0.2.0 / v0.2.1 で集中的に追加した docs や scripts に、リリース後にもはや不要となっている記述・ファイルが含まれている可能性
- **PR 本文の構造不明確** — `## 概要` (1-3 行 purpose) + `## 変更点` (主要変更箇条書き) では「期待値 vs 現状 vs 修正方針」のギャップが一目で読めず、レビュアー / 将来読者が PR の核心を素早く把握できない (user 観察、本セッション 2026-05-18 提示)

これらを 1 spec / 1 PR で消化する。

## 2. ゴール

1. 3 件 doc deferred issue の受入条件を逐条充足
2. 新 L3 / `L4 (former L3)` ナミング規約が active docs 全件で正しく適用されている (= ambiguous な `L3` 表記が新 L3 / 旧 L3 のどちらか文脈で曖昧でない)
3. CLAUDE.md / design-overview.md / release-process.md の layer table 3 つが行単位で一致
4. broken link / orphan doc / 自己申告 dead-flag コメント (`DEPRECATED` / `TODO: remove after vX` 等) が見つかれば triage して処理 (本 PR 内 / 別 issue / skip のいずれか)
5. PR template に「## 課題サマリ」新規セクション (3 サブ: `### 現状` / `### 期待値` / `### 修正方針`) を追加し、`docs/l2-workflow.md` §「PR 作成ルール」 にも convention を明文化。bug fix / regression PR で全サブ必須、feature / refactor PR は `N/A: <理由>` 許容。`pr-checklist.yml` workflow の section-aware regex を壊さないこと
6. PR タイトル `docs: v0.3.0 P3 deferred doc cleanup (#634 #635 #654) + L3 整合性監査 + 不要整理 + PR 課題サマリ規約` で `develop-0.3.0` にマージ

## 3. 重要な選択点と決定

| 選択点 | 候補 | 決定 | 根拠 |
| --- | --- | --- | --- |
| 全体構成 | (A) 統合 1 spec / (B) 段階分割 / (C) audit 先行 | **(A) 統合 1 spec** | brainstorm session 1 で user 確定 (推奨案)。docs only / scope 限定なので Iron Law 3 違反 risk 低 |
| 監査範囲 | (α) active docs 全部 / (β) plan touch 済 8 ファイル + 隣接 / (γ) CLAUDE.md + README.md のみ | **(α) active docs 全部** | brainstorm session 1 で user 確定 |
| PR 構成 | (1) 1 PR / (2) touched file 2 分割 / (3) issue 1 件 1 PR | **(1) 1 PR** | brainstorm session 1 で user 確定 (doc only / 互いに independent / scope 明確) |
| #635 対応 | (P) verify-only close / (Q) cross-link 追加 / (R) PR template explicit 化 | **(Q) cross-link** default、(R) は Phase 2 で AskUserQuestion 再判断 | session 2 で user が「対応して」と明示。Q が最小 / 最安全。R は CI ゲート影響なし確認が必要 |
| cleanup 観点 (source) | (i) shallow grep only / (ii) 深い dead-code detection | **(i) shallow grep only** | 本 PR scope を 1 PR に収めるため。深い検出は別 issue 化 |
| cleanup 観点 (doc) | (i) link audit のみ / (ii) link + orphan + stale 全て | **(ii) link + orphan + stale 全て** | session 2 で user が「不要となっているドキュメント」と広めに指示 |
| PR template 改善方向性 | (A) 「## 課題サマリ」新規セクション / (B) 「## 変更点」に before/after 必須化 / (C) 「## 概要」に 3 文必須ルール / (D) 別 spec | **(A) 「## 課題サマリ」新規セクション** | session 3 で user 確定。3 サブ (現状 / 期待値 / 修正方針) 必須、N/A 許容。最も強制力が強く読みやすい |
| PR 改善の issue tracking | (a) 新規 issue 起票 / (b) #635 scope 拡張 / (c) issue 起票せず spec 内のみ | **(c) issue 起票せず spec 内のみ** | session 3 で user 確定。小さめ convention 改善なので issue 不要との判断 |

## 4. Phase 構成

### Phase 0: 監査 (read-only)

| Phase | 目的 | 入力 | 出力 |
| --- | --- | --- | --- |
| **0A** | L3 整合性監査 | active docs 全件 | finding 一覧 (新 L3 / `L4 (former L3)` 表記の取り違え) |
| **0B-doc** | 不要 doc 監査 | active docs 全件 | broken link / orphan doc / stale info 一覧 |
| **0B-src** | 不要 source 監査 (shallow) | scripts/ + .github/scripts/ + allaganeye/ + gui/src/ | `DEPRECATED` / `TODO: remove after vX` 等の自己申告コメント検出のみ |

### Phase 1: triage

- 各 finding を以下のいずれかに振り分け (AskUserQuestion):
  - (a) 本 PR 内修正 (推奨、Iron Law 3 docs cleanup scope 内)
  - (b) 別 issue 起票 (本 PR より大きい / 別 scope)
  - (c) skip (false positive / 意図的残置)
- 0A の finding は smoke check で 0 件見込み (§6 末尾 "smoke check 暫定結果" 参照)
- 0B の finding 数次第で本 PR のサイズが変動 → diff 行数 100+ になりそうなら必ず triage で (b) に逃す

### Phase 2: 4 件 doc / template fix 実装

| Task | 由来 | 対象 | 変更内容 |
| --- | --- | --- | --- |
| **2.1** | #654 | `docs/output-spec.md:117` | Closed Issue 一覧の `#388` 行を `#388 / #433 (Filter drop 内訳 + unknown match 行)` に書き換え |
| **2.2** | #634 | `docs/cli-spec.md:376+` + `docs/output-spec.md` matrix v2 | click-level option-parse error (`Did you mean --version?`) のサブセクション追加。`allaganeye/cli.py:498-574` 実装と整合。matrix v2 にも click-level error 行 (19d 等) 追加 |
| **2.3** | #635 | `docs/l2-workflow.md` | §「PR 作成ルール」から §「Self-Test Report 規約」 (line 325-342) への cross-link 追加 (選択肢 Q)。`(R)` 採否は Phase 2 開始時に AskUserQuestion |
| **2.4** | session 3 観察 (issue 起票せず) | `.github/pull_request_template.md` + `docs/l2-workflow.md` | PR template に「## 課題サマリ」新規セクション追加 (`### 現状` / `### 期待値 (= 受け入れ条件 要約)` / `### 修正方針` の 3 サブ、N/A 許容)。位置: `## 概要` の直下、`## 変更点` の上。`docs/l2-workflow.md` §「PR 作成ルール」 に convention 明文化。`pr-checklist.yml` workflow の section-aware regex を壊さないこと (新セクションは regex 監視外なので影響なし) |

### Phase 3 (conditional): 監査 finding 実装

- Phase 1 で (a) 本 PR 内修正と triage された finding を実装

## 5. Files modified

### 確定

| Path | 由来 | 変更内容 |
| --- | --- | --- |
| `docs/output-spec.md` | #654 + #634 | `:117` Closed Issue 一覧 + matrix v2 click-level error 行 |
| `docs/cli-spec.md` | #634 | §「エラー表示」に click-level option-parse error サブセクション追加 |
| `docs/l2-workflow.md` | #635 + Phase 2.4 | §「PR 作成ルール」 → §「Self-Test Report 規約」 cross-link (#635 Q) + 「## 課題サマリ」 convention 明文化 |
| `.github/pull_request_template.md` | Phase 2.4 | 「## 課題サマリ」新規セクション (3 サブ: 現状 / 期待値 / 修正方針) を `## 概要` 直下に追加 |

### 暫定 (audit finding 次第)

| Path | 条件 |
| --- | --- |
| 他 active docs (期待値 0 件) | Phase 0A finding (a) triage で追加された場合 |
| broken link / orphan を持つ doc | Phase 0B-doc finding (a) triage で追加された場合 |
| `.github/pull_request_template.md` 追加 touch | #635 選択肢 R 採用時 (Phase 2.4 とは別箇所、Self-Test Report 節 comment 強化) |

### Files NOT modified (明示)

| Path | 理由 |
| --- | --- |
| `docs/superpowers/specs/*.md` / `docs/superpowers/plans/*.md` (既存 archive) | §4.1 文脈保存ルール (PR [#776](https://github.com/Idios/kobutachan-allaganeye/pull/776) spec で確定)。本 spec 本体は新規作成のため対象外 |
| `allaganeye/**/*.py` / `gui/src/**` / `gui/src-tauri/**` 本体 | 本 PR scope = docs only。`DEPRECATED` 等の grep 結果は triage で別 issue 化、コード本体の編集は本 PR では行わない |
| `commit messages` (過去分) | 不変 |

## 6. Phase 0 監査の具体手法

### Phase 0A (L3 整合性)

1. **Grep "L3"** in `CLAUDE.md` / `README.md` / `docs/*.md` (`docs/superpowers/` を除く) / `.github/**/*.{md,yml}` / `.claude/skills/**/*.md` / `.claude/hooks/**`
2. 各 hit を以下に分類:
   - **(i) 新 L3 として正しい**: `L3` 単独表記 → 文脈 (v0.3.0 / VTuber / minimap / perf) で新 L3 と確定できる
   - **(ii) `L4 (former L3)` ナミング適用済**: 旧 L3 (= 新 L4) を指す箇所が `L4 (former L3, …)` で書かれている
   - **(iii) ambiguous (要修正)**: `L3` 単独だが新旧どちらか不明 / `L3 初期` 等の時間表現で意図不明 / layer table 不一致
3. layer table の行単位照合:
   - `CLAUDE.md §段階的アーキテクチャ` のテーブル
   - `docs/design-overview.md §段階的アーキテクチャ` の ASCII art
   - `docs/release-process.md` の Layer-to-version 表 (`L1-L7` の行)
   - 3 つが同じ意味で同じ命名規約になっているか
4. `docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md` §9 Doc mapping table と現状を突合せ (Primary 3 件 / Secondary 5 件 / Other 1 件 / Files NOT touched 2 件 が plan 通りに反映済か)

**smoke check 暫定結果** (brainstorm session 1 で実施): 12 active docs 全件 OK、findings 0 件見込み。

### Phase 0B-doc (不要 doc 監査)

1. **Broken link audit**: `Grep "\[.*\]\(.*\)"` で markdown link を全抽出 → 各 link 先 (file path / section name) が実在するかを sample check
2. **Orphan doc check**: `docs/*.md` の各ファイルが少なくとも 1 箇所から参照されているか (`Grep <filename>` で参照箇所数 > 0)
3. **Stale info heuristic**:
   - `v0.1.x` / `v0.2.0` / `v0.2.1` 等の post-release version note で「リリース時に確定」が未確定のまま残っているもの
   - `TBD` / `TODO: remove after vX` / `(暫定)` / `(計画中)` で v0.3.0 開始時点で既に確定したもの

### Phase 0B-src (不要 source shallow check)

1. `Grep "DEPRECATED|TODO: remove after|XXX|FIXME: remove"` (case-sensitive) in:
   - `allaganeye/**/*.py`
   - `gui/src/**/*.{ts,tsx}`
   - `gui/src-tauri/src/**/*.rs`
   - `scripts/**/*.{sh,ps1,py}`
   - `.github/scripts/**`
2. 各 hit を Phase 1 triage に回す
3. **深い dead-code detection (e.g., `vulture` / `ts-prune` 実行) は本 PR scope 外**

## 7. Risks

| ID | Risk | 対策 |
| --- | --- | --- |
| R1 | Iron Law 3 scope creep — 0B findings が膨らみ「ついでに直す」化 | Phase 1 で必ず triage。diff 行数 100+ になりそうなら (b) 別 issue に逃す |
| R2 | #635 over-engineering — 既充足を冗長化 | 選択肢 Q default、R は AskUserQuestion で慎重判断 |
| R3 | PR #632 実装との drift — #634 doc 例が現実装と乖離 | `allaganeye/cli.py:498-574` を Phase 2.2 実装直前に Read で再確認 |
| R4 | markdownlint violation の二次発生 — 大量 doc 編集で local conv 違反 | 各 task 完了直後に `bash scripts/check-markdownlint.sh` 実行 (#660 規約) |
| R5 | layer table 不一致の見落とし | Phase 0A Step 3 を grep だけでなく行単位 diff で照合 |
| R6 | PR template 改修で `pr-checklist.yml` workflow 破壊 — section-aware regex (`.github/scripts/check-pr-checklist.js`) が見出し名を読んでいる | Phase 2.4 で `check-pr-checklist.js` を Read して regex 対象 heading 名 (e.g., `Self-Test Report`, `実機検証`, `関連ドキュメント / マトリクス更新`) を確認、これら既存 heading は触らない。「## 課題サマリ」は新規追加なので regex 対象外 |
| R7 | 課題サマリ convention の運用負荷 — 全 PR で 3 サブを書くのが重い | bug fix / regression PR は必須、feature / refactor PR は `N/A: <理由>` 許容で運用負荷を下げる。template comment で適用基準を誘導 |

## 8. Acceptance gates

### 各 issue 受入条件 (Iron Law 1)

- [ ] **#654**: `docs/output-spec.md:117` の `#388` 行が `#388 / #433 (Filter drop 内訳 + unknown match 行)` 形式
- [ ] **#654**: row 12 (`docs/output-spec.md:63`) と Closed Issue 一覧 (`:117`) の表現整合
- [ ] **#634**: `docs/cli-spec.md` のエラー表示章に click-level option-parse error の hint 出力例追加
- [ ] **#634**: `docs/output-spec.md` matrix v2 に click-level error 行追加
- [ ] **#634**: doc 修正が `allaganeye/cli.py:498-574` 実装と整合
- [ ] **#635**: `docs/l2-workflow.md` §「PR 作成ルール」 に checkbox convention の cross-link / 言及あり
- [ ] **#635**: `.github/pull_request_template.md` の convention 案内コメントは既存 (選択肢 R 採否で touch 判断)
- [ ] **Phase 2.4**: `.github/pull_request_template.md` に「## 課題サマリ」セクション追加 (3 サブ: `### 現状` / `### 期待値` / `### 修正方針`)
- [ ] **Phase 2.4**: `docs/l2-workflow.md` §「PR 作成ルール」 に「## 課題サマリ」 convention 明文化 (bug fix / regression は必須、feature / refactor は `N/A` 許容、判断基準明示)
- [ ] **Phase 2.4**: `pr-checklist.yml` workflow が CI で pass (新セクション追加で regression なし、PR 提出時に validate-checklist が落ちないこと)

### 監査結果 (Phase 0 output)

- [ ] Phase 0A findings table を PR 本文に記載 (期待 0 件、すべて (i)/(ii) 分類済)
- [ ] Phase 0B-doc findings table を PR 本文に記載 (見つかれば triage 結果も)
- [ ] Phase 0B-src findings table を PR 本文に記載 (見つかれば triage 結果も)
- [ ] layer table 3 ファイル一致確認結果を PR 本文に記載

### 自動チェック

- [ ] `bash scripts/check-markdownlint.sh` pass
- [ ] `Grep "Filter drop 内訳"` で `(Filter drop 内訳)` 単独 (#654 規約: `#388 / #433 (Filter drop 内訳 + unknown match 行)` の expanded 形式のみ残る) を確認
- [ ] `Grep "L3"` で ambiguous な単独 `L3` 表記が 0 件
- [ ] PR template の section heading 監視 (`.github/scripts/check-pr-checklist.js` regex) と新規「## 課題サマリ」が無関係であることを node 実行確認
- [ ] 本 PR 自体の本文が新 convention に従って「## 課題サマリ」 3 サブ書き込み済 (self-application: dogfooding)

### Self-Test Report (machine-verified)

- [ ] `bash scripts/check-markdownlint.sh` (docs 変更)
- [ ] `ruff check .` — N/A: Python 変更なし
- [ ] `ruff format --check .` — N/A: Python 変更なし
- [ ] `pyright` — N/A: Python 変更なし
- [ ] `pytest` — N/A: Python 変更なし
- [ ] GUI 系 — N/A: GUI 変更なし
- [ ] `cargo check` — N/A: Rust 変更なし

### 実機検証 (machine-unverifiable)

- 該当なし (docs only / docs/cli-spec.md / docs/output-spec.md / docs/l2-workflow.md のみ)

## 9. PR 構成

### Iron Law 6 Pre-flight (PR 作成直前)

- Step 0: `gh pr list --search "<元issue#>" --state open` × 3 (各 issue 別 PR 化されていないことを確認)
- Step 1: `git fetch origin develop-0.3.0`
- Step 2: `git log HEAD..origin/develop-0.3.0 --oneline` で取り込み未済 commit 確認
- Step 3: 取り込み未済 commit が touched files (docs/*.md) と path 交差なら取り込み
- Step 4: `gh pr list --search "<元issue#>" --state all` で並行 PR 再確認
- Step 5: `/codex:adversarial-review` (focus: Iron Law 3 docs cleanup scope creep / L3 整合性監査の網羅性 / #634 doc-impl drift / 0B findings の triage 妥当性)

### Codex adversarial-review focus

> Verify (i) Iron Law 3 — only docs cleanup / L3 audit / PR template 改修 changes, no incidental refactors leaked. (ii) Phase 0A audit comprehensive — `L3` mentions in CLAUDE.md / README.md / docs/*.md (excluding superpowers/) / .github/**/*.md|yml / .claude/skills/**/*.md / .claude/hooks/** all classified (i/ii/iii). (iii) #634 doc example matches current `allaganeye/cli.py:498-574` `_suggest_long_option_hint` / `main()` behavior. (iv) #635 cross-link points to live section. (v) 0B findings triage decisions are reasonable (本 PR / 別 issue / skip). (vi) Phase 2.4 PR template の新「## 課題サマリ」が `pr-checklist.yml` workflow (specifically `.github/scripts/check-pr-checklist.js` section regex) を破壊しないこと、新 heading 名が既存 regex pattern と衝突しないこと、validate-checklist CI が空サブで block しないこと。

### Closes 禁止 (Iron Law 4)

- PR 本文に `Closes #634` 等の自動クローズキーワード禁止
- マージ後 `/close-issue 634` / `/close-issue 635` / `/close-issue 654` を順次 (#635 は実際の修正内容を確定後 close)

### マージ後

- Phase 0 audit findings から派生した別 issue (Phase 1 で (b) triage されたもの) が複数あれば `/create-task` skill で順次起票
- `0B-src` の `DEPRECATED` / `FIXME` 系で深い分析が必要なものは「dead-code audit (v0.3.0 派生)」issue として起票

## 10. Out of scope

- 深い dead-code detection (`vulture` / `ts-prune` 等のツール実行) — 別 issue
- `allaganeye/**/*.py` / `gui/src/**/*` のコード refactor — 別 issue
- `docs/superpowers/specs/*.md` / `docs/superpowers/plans/*.md` archive の本文編集 — §4.1 文脈保存ルールで禁止
- v0.3.0 L3 work 本体 (VTuber / minimap / perf 3 pillar) — 別 spec で扱う
- 新規 doc 作成 (e.g., 新 user guide) — scope 外
- v0.2.0 / v0.2.1 リリース後の `CHANGELOG.md` cleanup — `/release` skill scope

## 11. 関連 issue / PR / spec

- [#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) — cli-spec.md / output-spec.md click-level option-parse error hint
- [#635](https://github.com/Idios/kobutachan-allaganeye/issues/635) — PR Test plan checkbox convention 明文化
- [#654](https://github.com/Idios/kobutachan-allaganeye/issues/654) — docs/output-spec.md:117 Closed Issue 一覧に #433 反映
- PR [#776](https://github.com/Idios/kobutachan-allaganeye/pull/776) — v0.3.0 L3 redefinition Wave A 8 ファイル更新 (本 spec の前提)
- `docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md` — L3 redefinition design (本 spec が監査する対象)
- `docs/l2-workflow.md` §「Self-Test Report 規約」 (line 325-342) — #635 で参照する既存規約
- `docs/refactor-pattern.md` — Phase 分割の判断基準 (本 PR が分割不要であることの裏付け)
- `.github/pull_request_template.md` — Phase 2.4 で「## 課題サマリ」 新規セクション追加対象
- `.github/scripts/check-pr-checklist.js` + `.github/workflows/pr-checklist.yml` — Phase 2.4 で section-aware regex を壊さないことを確認する対象
