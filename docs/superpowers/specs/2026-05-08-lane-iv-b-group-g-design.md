# L2 Lane IV-b: Group G (workflow / CI / docs) 設計

> **Status**: v0.2.0 リリースゲート Lane IV-b (wave 0、Group G) スコープ
> **Scope**: [#624](https://github.com/Idios/kobutachan-allaganeye/issues/624) + [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) + [#682](https://github.com/Idios/kobutachan-allaganeye/issues/682) 統合 (1 spec / 3 章 / 1 PR 統合)
> **session**: `friendly-fermi-b81bbe` (2026-05-08 brainstorming)
> **roadmap**: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md) §Group G

## §1 Overview

Lane IV-b (workflow / CI / docs 仕上げ) は v0.2.0 release gate (`docs/l2-e2e-checklist.md` PASS + `/release` skill 実行) の前段階で、開発フローの 3 つの摘出問題を解決する。3 件は file 共有なし (`.github/workflows/pr-checklist.yml` / `.github/ISSUE_TEMPLATE/bug_report.yml` / `.claude/skills/review-pr/SKILL.md`) で並行安全度高、目的は一貫 (release gate 仕上げ) のため **1 spec / 1 PR 統合** で実装する。

### 対象 issue 一覧

| issue | 状態 | 概要 | 本 spec での扱い |
| --- | --- | --- | --- |
| [#624](https://github.com/Idios/kobutachan-allaganeye/issues/624) | OPEN (P2 bug) | `pr-checklist.yml` が `## Test plan` の `- [ ]` を誤検出してマージブロック | §3 で workflow を section-aware 化 |
| [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) | OPEN (P2 task) | `bug_report.yml` 新設 (PR #497 で実装完了、L3 初期 UI 実測のみ deferred) | §4 で #669 (Group D) 連動先取りの field id 凍結 + placeholder/description 整備 |
| [#682](https://github.com/Idios/kobutachan-allaganeye/issues/682) | OPEN (P3 task) | `/review-pr` skill に「同種パターン全件 sweep」規約を追加 (PR #675 follow-up) | §5 で SKILL.md に sweep 節 + Red Flag 表更新 + 失敗事例追記 + empirical 2 Iter |

### Lane / wave 設計上の位置づけ

- **Lane IV-b** = wave 0 で並行可能な 4 lane の 1 つ (Lane I-A / IV-a / IV-b / IV-c)
- file 共有なし → Lane IV-a (配布) / IV-c (lint+CLI) / I-A (AppError migration) と並行可
- 後段 wave への依存なし → wave 1 以降の Lane I-B / II-a / II-b の merge 待ちなし
- ただし **#458 は Group D #669 (wave 1 ErrorModal bug_report 自動埋込) と連動**するため、本 spec で field id を凍結することで Group D 着手時の前提を確定させる

## §2 Goals

1. **#624**: CLAUDE.md / docs/l2-workflow.md PR template に従って書かれた PR が、Test plan / 引用 / 規約 section の `- [ ]` で誤検出されない。一方で `## 受け入れ条件` の未消化 `- [ ]` は引き続き fail する (Iron Law 1 自動執行を維持)
2. **#458**: ErrorModal (Group D #669) が GitHub URL parameter で自動埋込できる field id / placeholder を確定。bug_report.yml 自体は最小変更にとどめる
3. **#682**: `/review-pr` で root cause 識別時に「全件 grep 提示」が必須化され、PR #675 のような 3 round 分散の divergence を防ぐ。empirical-prompt-tuning で挙動を実証

## §3 #624 workflow section-aware 化

### §3.1 現状

[`.github/workflows/pr-checklist.yml`](../../../.github/workflows/pr-checklist.yml):

```yaml
name: PR Checklist Validation
on:
  pull_request:
    types: [opened, edited, synchronize]
jobs:
  validate-checklist:
    runs-on: ubuntu-latest
    steps:
      - name: Check PR checklist
        uses: actions/github-script@v7
        with:
          script: |
            const body = context.payload.pull_request.body || '';
            const unchecked = (body.match(/- \[ \]/g) || []).length;
            const checked = (body.match(/- \[x\]/gi) || []).length;
            if (checked === 0 && unchecked === 0) {
              console.log('No checklist found in PR body, skipping.');
              return;
            }
            if (unchecked > 0) {
              core.setFailed(`PR has ${unchecked} unchecked checklist item(s). Please complete all items before merging.`);
            } else {
              console.log(`All ${checked} checklist item(s) are checked.`);
            }
```

PR 本文全文を `/- \[ \]/g` で grep し件数だけで fail を判定。section 区別なし。

### §3.2 改修方針 (Q5 (A) 確定: `## 受け入れ条件` allowlist 厳密)

`## 受け入れ条件` (大文字小文字無視) または `## Acceptance criteria` (大文字小文字無視) の heading で始まる section 内の `- [ ]` のみカウント対象。それ以外の section (Test plan / Self-Test / 引用 / 説明等) の `- [ ]` は許容。

#### 採用 heading 形式

- `## 受け入れ条件` (日本語、メイン)
- `## Acceptance criteria` (英語、別名対応、`acceptance` `criteria` の大文字小文字混在は無視)
- `### 受け入れ条件` 等の `###`+ heading は **対象外** (section 単位の意味的に `##` heading が PR template の標準)
- `## 受け入れ条件 (追加)` 等の suffix 付き heading は **対象外** (heading 完全一致を優先、後方互換が必要になった時点で拡張)

`##` の後の heading 文字列を trim → 正規表現 `^(受け入れ条件|acceptance\s+criteria)\s*$` で完全一致 (大文字小文字無視) する。

### §3.3 実装構造

#### script を別 file に切り出し

`actions/github-script@v7` の inline script は単体テストできないため、**script を [`.github/scripts/check-pr-checklist.js`](../../../.github/scripts/check-pr-checklist.js) に切り出し**、yml 側で `script:` から `require()` で読み込む。Node.js unit test (vitest または node --test) で section parser の挙動を担保する。

##### `.github/scripts/check-pr-checklist.js` (擬似コード)

```javascript
// 受け入れ条件 section の `- [ ]` / `- [x]` をカウントする
function countAcceptanceCriteriaCheckboxes(body) {
  // `## ` heading で section 分割。最初の heading 前は捨てる
  const sections = body.split(/^##\s+/m).slice(1);
  // 受け入れ条件 / Acceptance criteria heading に該当する section のみ抽出
  const acceptanceText = sections
    .filter((s) => {
      const heading = (s.split(/\r?\n/)[0] || '').trim();
      return /^(受け入れ条件|acceptance\s+criteria)\s*$/i.test(heading);
    })
    .join('\n');
  const unchecked = (acceptanceText.match(/- \[ \]/g) || []).length;
  const checked = (acceptanceText.match(/- \[x\]/gi) || []).length;
  return { unchecked, checked, hasAnySection: acceptanceText.length > 0 };
}

module.exports = async ({ github, context, core }) => {
  const body = context.payload.pull_request.body || '';
  const { unchecked, checked, hasAnySection } = countAcceptanceCriteriaCheckboxes(body);
  if (!hasAnySection) {
    core.info('No `## 受け入れ条件` / `## Acceptance criteria` section found, skipping.');
    return;
  }
  if (unchecked > 0) {
    core.setFailed(
      `PR has ${unchecked} unchecked acceptance criteria item(s) in \`## 受け入れ条件\` section. Please complete all items before merging.`
    );
    return;
  }
  core.info(`All ${checked} acceptance criteria item(s) are checked.`);
};
```

##### `.github/workflows/pr-checklist.yml` (改修後)

```yaml
name: PR Checklist Validation
on:
  pull_request:
    types: [opened, edited, synchronize]
jobs:
  validate-checklist:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check PR checklist
        uses: actions/github-script@v7
        with:
          script: |
            const checker = require('./.github/scripts/check-pr-checklist.js');
            await checker({ github, context, core });
```

`actions/checkout@v4` の追加で repo の script file を読み込めるようになる (現状の inline script は checkout 不要だったが、外部 file 参照のため必要)。

### §3.4 chicken-and-egg 回避

本 PR 自体の本文を **旧 workflow** (全文 grep) で validate されることを前提に書く:

- `## 受け入れ条件` 内には `- [ ]` を含めない (3 issue 分の合算受け入れ条件を全件 `[x]` で記載)
- Test plan / その他 section も極力 `- [x]` で書く (全文 grep が実行されるので)
- merge 後は新 workflow が次回以降の PR から適用される

### §3.5 受け入れ条件 4 項目への対応

| # | 受け入れ条件 (issue #624) | 対応 |
| --- | --- | --- |
| 1 | `pr-checklist.yml` の script を改修し、CLAUDE.md template に従って PR を作成しても誤検出しないこと | §3.2-3.3 の script 切り出し + section allowlist で実現 |
| 2 | PR #621 / #622 相当の構造で validate-checklist が pass する | §6.1 の unit test で再現サンプルを 2 ケース固定 |
| 3 | `## 受け入れ条件` の未消化 `- [ ]` は引き続き fail を返すこと (#367 対策維持) | §6.1 の unit test で fail ケースを担保 |
| 4 | CLAUDE.md PR template / docs/l2-workflow.md PR template 例とテストの整合性が取れている | §3.6 で docs 整合確認 |

### §3.6 docs 整合確認 (本 spec 範囲)

- `CLAUDE.md` PR 作成ルール節 (現状は `docs/l2-workflow.md` リダイレクト) はそのまま (本 PR で変更しない)
- `docs/l2-workflow.md` の Self-Test Report 規約 (行 240-254) は section-aware と矛盾しないことを spec で確認:
  - 規約は「`## Test plan (本 PR 提出前にローカルで実行済)` セクションは `- [x]` で全件チェック済」
  - 新 workflow は `## 受け入れ条件` allowlist のため、Test plan は kein 影響を受けない (規約上 `[x]` 推奨は維持されるが、`[ ]` でも fail しなくなる)
  - 規約は **緩和方向** で整合 (現状規約が「`- [x]` で全件」だったのは旧 workflow の制約に追従していたため、新 workflow では section 別の柔軟性が許される。ただし規約自体は変更不要、`- [x]` で書く慣習は維持)

## §4 #458 bug_report.yml 仕上げ (#669 連動先取り)

### §4.1 現状

[`.github/ISSUE_TEMPLATE/bug_report.yml`](../../../.github/ISSUE_TEMPLATE/bug_report.yml) は PR #497 (2026-04-21 マージ済) で実装完了。受け入れ条件 6/7 項目完了、残り 1 項目 (L3 初期 UI 実測) は **本 spec 範囲外** (release gate 後に main 反映済み環境で別途実施)。

field id 一覧:

| field id | type | required | 自動埋込候補 (Group D #669) |
| --- | --- | --- | --- |
| `reproduction` | textarea | true | × (ユーザー記入のみ) |
| `expected` | textarea | true | × (ユーザー記入のみ) |
| `actual` | textarea | true | ✓ (エラーメッセージ + stack trace) |
| `environment` | textarea | false | ✓ (`allaganeye --version` + system_info) |
| `log_file_attachment` | textarea (render: text) | false | ✓ (logs/error-YYYYMMDD.log 末尾抜粋) |
| `consent` | checkboxes | true (× 2) | × (URL parameter で pre-check 不可、ユーザー操作必須) |

### §4.2 改修方針 (Q3 (a) 確定: #669 連動先取り)

**field id rename しない** (PR #497 の現行 id を凍結) を最重要原則とする。Group D #669 が実装する `https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml&actual=...&environment=...&log_file_attachment=...` URL の query parameter 名は本 spec で確定する。

#### 確定する field id (Group D 実装の前提)

| field id (URL parameter 名) | 自動埋込内容 | 備考 |
| --- | --- | --- |
| `actual` | エラーメッセージ + stack trace を URL encode | ErrorModal で表示中のエラー |
| `environment` | `allaganeye --version` 出力 + system_info (CPU/GPU/Memory/Disk) | metadata.json の `system_info` フィールドから取得 |
| `log_file_attachment` | `logs/error-YYYYMMDD.log` 末尾 (例: 50 行) を URL encode | ErrorModal の `[ログフォルダを開く]` ボタンで開けるファイルから取得 |

`reproduction` / `expected` / `consent` は URL parameter で埋め込まない (ユーザー記入)。

#### bug_report.yml 微修正範囲

placeholder / description / 上部 markdown 案内の文言を **ErrorModal 自動埋込前提** で点検し、最小修正:

1. **上部 markdown 案内に note 追加 (1 行)**: 「ErrorModal の `[GitHub Issue を作成]` ボタンを使うと一部項目が自動入力されます (公開後)」を追加。「公開後」 = main マージ + ErrorModal 機能 (#669) 実装後を指す
2. **`actual` の description 微修正**: 「エラーメッセージ全文やログがあれば貼り付けてください (ErrorModal から自動入力される場合あり)」と note を追加 (元文言: 「エラーメッセージ全文やログがあれば貼り付けてください」)
3. **`environment` の placeholder 維持**: `allaganeye --version` 出力例はそのまま (ErrorModal 自動埋込時も同形式で埋まる前提)
4. **`log_file_attachment` の description 微修正**: 「ErrorModal から自動入力される場合は末尾抜粋のみ。完全なログファイルが必要な場合は手動添付してください」を追加

合計 diff: 数行〜10 行未満の微修正。

### §4.3 受け入れ条件への対応

| # | 受け入れ条件 (issue #458) | 対応 |
| --- | --- | --- |
| 1 | `.github/ISSUE_TEMPLATE/bug_report.yml` が存在する | 既存 (PR #497) |
| 2 | New issue UI からテンプレ選択可能 | **deferred** (L3 初期で main 反映後に実測、本 PR scope 外) |
| 3 | 同意 checkbox 2 件 required | 既存 (PR #497) |
| 4 | docs/bug-report-guide.md へのリンク | 既存 (PR #497) |
| 5 | 既存テンプレートとの併存 | 既存 (PR #497) |

本 spec で **追加する受け入れ条件** (Group G #458 章として、§6.2 受け入れ条件統合に統合):

- field id (reproduction/expected/actual/environment/log_file_attachment/consent) を本 spec で凍結し、Group D #669 の URL parameter 名として確定したことを記述する
- placeholder / description / 上部 markdown 案内に ErrorModal 自動埋込 note を追加する

詳細な記述方式は [§6.2 受け入れ条件統合](#62-受け入れ条件統合) を参照。

## §5 #682 review-pr SKILL.md sweep 規約追加

### §5.1 現状

[`.claude/skills/review-pr/SKILL.md`](../../../.claude/skills/review-pr/SKILL.md) には「同種パターン全件 grep」規約なし。PR #675 で 3 round に分散の実害確定:

- Round 1 #5b: literal「関数本体先頭」訂正で 1 箇所のみ修正依頼 → 同 file 他 4 箇所見落とし
- Round 2 #8: 上記 4 箇所を explicit 列挙 → 別の 4 箇所見落とし
- Round 3 #9: さらに 4 箇所 → ようやく全件検出

3 round 要した PR 推進コスト × 3。Round 1 で `grep` 全件 sweep していれば 1 round で完了していた。

### §5.2 改修方針 (Q4 (a) 確定: issue 本文通り)

#### 5.2.1 SKILL.md に「同種パターン修正依頼の全件 sweep 規約」節を新規追加

新節 (例: `## 同種パターン sweep 規約`) を Step 5b (トリアージ) 周辺に挿入。内容:

- root cause (literal mismatch / 古い API / DCE 誇張表現 等) を識別したら、`grep -nE 'pattern1|pattern2|...'` で修正対象を**全件検出**してトリアージ表に掲載
- explicit な N 箇所だけを list して implementer に依頼するのは **Red Flag**
- トリアージ表 + implementer 修正依頼本文の両方に grep コマンドと hits を同梱

#### 5.2.2 Red Flag 表に追記

既存の Red Flag 表 (SKILL.md 内の「この思考が浮かんだら STOP」表) に 1 行追加:

| 浮かんだ思考 | 現実 |
| --- | --- |
| 「explicit N 箇所だけ列挙して全件 grep を要求しない」 | divergence 原因。1 round で完了せず Round 2/3 に分散する。root cause 識別時は `grep` 全件 sweep が必須 |

#### 5.2.3 トリアージ section の改定

issue #682 で言及される「Step 5b (トリアージ)」相当節を SKILL.md 内で特定し、以下を必須ステップとして追加:

- 同種パターン識別時は「全件 grep 提示」を必須化
- implementer への修正依頼本文に `grep -nE '...'` コマンドと hits を同梱

実装時に SKILL.md の最新の節名・番号を確認して本 spec の参照を更新する (現状 issue #682 起票時点では節名 = `Step 5b`)。

#### 5.2.4 「よくある失敗」表に PR #675 事例追記

SKILL.md の「よくある失敗」表 (または同等節) に PR #675 の経緯を追加:

> **PR #675 (StateSwitcher dev only) Round 1/3 divergence**: literal「関数本体先頭」訂正 + 旧 API `vi.stubEnv('DEV', '')` + DCE 誇張表現 の 3 種類の root cause が複数 file に散在していたが、各 Round で explicit N 箇所のみ列挙したため Round 1 → 2 → 3 と divergence 発生。Round 1 で `grep -nE '関数本体先頭|stubEnv.*DEV|DCE で完全削除'` 全件 sweep していれば 1 Round で完了していた。

### §5.3 empirical 検証 (memory `feedback_skill_revision_empirical.md` 準拠)

[`.claude/skills/review-pr/eval/`](../../../.claude/skills/review-pr/eval/) 配下に **(1) 前段階事例調査 → (2) モック設計 → (3) 要件チェックリスト → (4) subagent dispatch + 2 Iteration** の流れで empirical 検証する。memory `feedback_skill_revision_empirical.md` (2026-04-24 PR #511 で確立、Iteration 0/1 構造で「2 Iteration」を達成、新規 subagent 必須) を遵守する。

#### §5.3.1 前段階事例調査

PR #675 と類似 (Round 1 → 2 → 3 と divergence した) の実在 PR を **3 本ピックアップ**し、Explore agent 並列で指摘パターンを抽出してからモック設計に活かす。候補例 (実装時に `gh pr list --search 'review' --state all` 等で具体特定):

- **メイン事例**: PR #675 (StateSwitcher dev only Round 1/3 divergence、issue #682 起票元)
- **追加事例 2-3 本**: review-pr で Round 数が多めだった他 PR (`gh pr list --search "review-pr" --state all` から指摘 round 数を集計)

各事例で「root cause 種類」「散在 file 数」「Round 1 で見落とした explicit 箇所数」を抽出し、モック設計の参考にする。

#### §5.3.2 モック設計 (中央値 1 + edge 2)

memory 「中央値 1 + edge 2」原則に従い、3 シナリオを `eval/scenario_*.md` に書き出す:

| シナリオ id | 種類 | 内容 |
| --- | --- | --- |
| `scenario_e_sweep_central.md` | 中央値 | 単一 root cause が複数 file に散在 (例: literal mismatch が 4 file × 4-5 箇所、計 16-20 hits) |
| `scenario_e_sweep_edge_mixed.md` | edge 1 | 複数 root cause が混在 (literal mismatch + 旧 API 残存 + DCE 誇張表現 が 1 PR 内に並存、PR #675 を再現) |
| `scenario_e_sweep_edge_doc_only.md` | edge 2 | doc-only PR で sweep 規約が発動するケース (例: spec doc 内の literal が 5 箇所散在、コードは触らない) |

各シナリオの記述形式は既存の `eval/scenario_a_central.md` / `scenario_b_bundled.md` 等を踏襲する。

#### §5.3.3 要件チェックリスト (`eval/requirements.md` に追記)

memory 「`[critical]` タグ付きで事前固定」に従い、`eval/requirements.md` の既存要件群に sweep 関連要件を `[critical]` タグ付きで追加:

- `[critical]` root cause 識別時に subagent が `grep -nE '...'` 全件 sweep を提示するか
- `[critical]` explicit N 箇所のみ列挙する模範解答ではなく、grep hits を全件含めるか
- `[critical]` Red Flag 表の新項目を subagent が引用するか
- Round 1 で同種 hits を全件捕捉できているか (Round 2/3 への分散がないか) — non-critical (Round 数の自動測定は scenario 設計に依存)

#### §5.3.4 subagent dispatch + 2 Iteration

memory 「`general-purpose` + `model: sonnet` + 3 並列 + `run_in_background: true`」に従う:

- **dispatch 構成**: `subagent_type: general-purpose`, `model: sonnet`, `run_in_background: true`, 3 シナリオ並列
- **Iteration 0 (baseline)**: 改訂前 SKILL.md で 3 シナリオを 3 並列 dispatch → 各 scenario 結果を `eval/reports/iter_0_sweep_*.md` に保存。期待: Round 1 で全件 sweep されない (現状再現)
- **Iteration 1 (revaluation)**: 改訂版 SKILL.md で 3 シナリオを **新規 subagent** で 3 並列 dispatch → 各 scenario 結果を `eval/reports/iter_1_sweep_*.md` に保存。期待: Round 1 で全件 sweep される
  - **新規 subagent 必須**: memory 「Iteration 1 再評価では必ず新規 subagent (empirical Red Flag『同じ subagent を使い回そう』に該当するため同一 agent は不可)」に従う
- 比較サマリを `eval/reports/summary_sweep.md` に保存 (Iteration 0/1 で `[critical]` 要件の達成率の差分を表化)

#### §5.3.5 打ち切り基準

memory 「構造的欠陥 (新節欠落・判定基準不在レベル) が解消された時点で打ち切り可」に従う:

- Iteration 1 で `[critical]` 全要件が「○」になれば打ち切り
- Iteration 1 で `[critical]` 要件が「部分的」or「×」のまま残る場合: SKILL.md を更に改訂して **Iteration 2** を実施 (新規 subagent でさらに dispatch)
- 残る細部不明瞭点 (non-critical 要件) は **deferred issue** として追跡し、後続運用で育てる (本 PR には含めない)

#### §5.3.6 検証アーティファクト同梱

本 PR に以下を同梱:

```text
.claude/skills/review-pr/eval/
├── scenario_e_sweep_central.md       (新規)
├── scenario_e_sweep_edge_mixed.md    (新規)
├── scenario_e_sweep_edge_doc_only.md (新規)
├── requirements.md                    (既存に sweep 要件 [critical] x 3 + non-critical x 1 を追記)
└── reports/
    ├── iter_0_sweep_central_baseline.md
    ├── iter_0_sweep_edge_mixed_baseline.md
    ├── iter_0_sweep_edge_doc_only_baseline.md
    ├── iter_1_sweep_central_revaluation.md
    ├── iter_1_sweep_edge_mixed_revaluation.md
    ├── iter_1_sweep_edge_doc_only_revaluation.md
    └── summary_sweep.md
```

### §5.4 受け入れ条件 4 項目への対応

| # | 受け入れ条件 (issue #682) | 対応 |
| --- | --- | --- |
| 1 | SKILL.md に「同種パターン sweep 規約」節を追加 | §5.2.1 |
| 2 | Red Flag 表に「explicit N 箇所だけ列挙 → divergence」を追加 | §5.2.2 |
| 3 | 「よくある失敗」表に PR #675 Round 1, 3 経緯事例追記 | §5.2.4 |
| 4 | empirical-prompt-tuning で検証 (PR #675 同種シナリオ mock で 2 Iteration) | §5.3 |

## §6 PR 統合方針 + 受け入れ条件統合

### §6.1 PR スコープ宣言

PR スコープを **「Group G: workflow / CI / docs 仕上げ」** と明示し、3 issue を Refs:

```text
title: feat(workflow): Group G workflow / CI / docs 仕上げ (Refs #624 #458 #682)
body:
  ## スコープ
  Lane IV-b (Group G) として workflow / CI / docs 仕上げの 3 件を統合実装。
  3 件は file 衝突なし (`.github/workflows/pr-checklist.yml` /
  `.github/ISSUE_TEMPLATE/bug_report.yml` / `.claude/skills/review-pr/SKILL.md`)、
  目的は v0.2.0 release gate 仕上げで一貫。
  Refs #624, Refs #458, Refs #682
```

### §6.2 受け入れ条件統合

PR 本文 `## 受け入れ条件` に 3 issue 分を sub-section で分けて記述:

```markdown
## 受け入れ条件

### #624 (workflow section-aware 化)
- [x] pr-checklist.yml の script を改修し、CLAUDE.md template に従って PR を作成しても誤検出しないこと
- [x] PR #621 / #622 相当の構造で validate-checklist が pass する (unit test で再現)
- [x] `## 受け入れ条件` の未消化 `- [ ]` は引き続き fail を返すこと (#367 対策維持、unit test で確認)
- [x] CLAUDE.md PR template / docs/l2-workflow.md PR template 例とテストの整合性が取れている

### #458 (bug_report.yml field id 凍結 + #669 連動先取り)
- [x] field id (reproduction/expected/actual/environment/log_file_attachment/consent) を本 spec で凍結
- [x] placeholder / description / 上部 markdown 案内に ErrorModal 自動埋込 note を追加
- [x] field id を Group D #669 の URL parameter 名として確定したことを spec に記述
- (deferred) New issue UI からテンプレ選択可能 (L3 初期 UI 実測、release gate 後に別途実施、本 PR scope 外)

### #682 (review-pr sweep 規約追加)
- [x] SKILL.md に「同種パターン sweep 規約」節を追加
- [x] Red Flag 表に「explicit N 箇所だけ列挙 → divergence」を追加
- [x] 「よくある失敗」表に PR #675 Round 1/3 経緯事例追記
- [x] empirical-prompt-tuning で検証 (PR #675 同種シナリオ mock で 2 Iteration、eval/ 配下にアーティファクト同梱)
```

### §6.3 chicken-and-egg 回避

本 PR は **旧 workflow** (全文 grep) で validate される。本文に `- [ ]` を含めないために以下を守る:

- 受け入れ条件 sub-section は全件 `[x]` で記載
- deferred 項目は plain bullet (例: `- (deferred) ...`) で記述、`- [ ]` は使わない
- Test plan / 引用 / その他 section も `- [x]` または plain bullet `-` で書く

merge 後の next PR から新 workflow (section-aware) が適用される。

### §6.4 Iron Law 整合

| Iron Law | 本 PR での担保 |
| --- | --- |
| Law 1 (受け入れ条件全件チェック) | §6.2 の sub-section で 3 issue 分すべて引用、`/review-pr` で逐条検証 |
| Law 2 (bulk 操作 AskUserQuestion) | merge 後の `/close-issue` skill で 3 issue 順次 close (束ね PR ケース、各 issue 個別に Idios 確認) |
| Law 3 (1 PR = 1 scope) | スコープを「Group G workflow / CI / docs 仕上げ」と明示、3 issue を Refs。「複数 issue 統合」は記述上一貫した目的でくくれるため許容 (l2-workflow.md `(A) PR 内修正優先` 規約類比) |
| Law 4 (Closes 禁止) | PR 本文・commit msg に `Closes` / `Fixes` / `Resolves` 禁止、`Refs #624 #458 #682` のみ |
| Law 5 (曖昧点は AskUserQuestion) | brainstorming で Q1-Q6 の 6 質問を実施 (本 spec §1 session メタ参照) |
| Law 6 (PR 作成 Pre-flight) | `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認を PR 作成直前に実施 |

## §7 Test

### §7.1 #624 unit test

`.github/scripts/check-pr-checklist.test.js` (Node.js native test runner `node --test` または vitest) で section parser の挙動を担保:

| テストケース | 期待結果 |
| --- | --- |
| `## 受け入れ条件` 内 `- [ ]` 1 件、`## Test plan` 内 `- [ ]` 5 件 | unchecked = 1 (Test plan は無視)、fail |
| `## 受け入れ条件` 内 `- [x]` 全件、`## Test plan` 内 `- [ ]` 5 件 | unchecked = 0、pass |
| `## Acceptance criteria` (英語別名) 内 `- [ ]` 2 件 | unchecked = 2、fail |
| `## 受け入れ条件` section が存在しない、`## Test plan` 内 `- [x]` のみ | hasAnySection = false、skip |
| `## 受け入れ条件` 内 引用 `> - [ ]` (blockquote 内) | (blockquote 内も grep される、現状仕様と同等。spec 範囲では blockquote 除外しない) |
| PR #621 構造再現 (Test plan の `- [ ]` で fail していた構造) | pass |
| PR #622 構造再現 | pass |

CI で `node --test .github/scripts/check-pr-checklist.test.js` を実行する job を追加 (新規 workflow `.github/workflows/check-pr-checklist-test.yml` または既存 workflow に step 追加。本 spec では既存 workflow に新 step 追加で最小化)。

### §7.2 #458 yml syntax check

- `yamllint` または GitHub Issue Forms validator で `bug_report.yml` の syntax 通過を確認
- field id の凍結確認: 既存 PR #497 で確定した id (`reproduction` / `expected` / `actual` / `environment` / `log_file_attachment` / `consent`) が rename されていないことを spec doc で固定

### §7.3 #682 empirical 2 Iteration

[§5.3.6 検証アーティファクト同梱](#536-検証アーティファクト同梱) で確定したファイル群を `.claude/skills/review-pr/eval/reports/` に同梱する。打ち切り基準は [§5.3.5](#535-打ち切り基準) を参照。Iteration 1 で `[critical]` 要件未充足の場合は Iteration 2 を実施 (新規 subagent)。

### §7.4 markdownlint

本 spec doc (`docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md`) を含むすべての変更 .md ファイルが markdownlint pass:

```bash
bash scripts/check-markdownlint.sh
```

### §7.5 自動チェック (path 別)

本 PR の変更 path に `.github/` (workflow yaml + script JS) / `.github/ISSUE_TEMPLATE/` (yaml) / `.claude/skills/` (md) / `docs/superpowers/specs/` (md) のみが含まれる。Python / GUI コードには touch しないため:

- ✓ markdownlint (本 spec doc + SKILL.md + eval/ markdown)
- ✓ yamllint (workflow yaml + bug_report.yml)
- ✓ Node.js test (check-pr-checklist.test.js)
- × Python (`ruff` / `pyright` / `pytest`) — 変更対象外
- × GUI (`npm run lint` / `typecheck` / `test` / `build` / `cargo check`) — 変更対象外

実機検証 trigger (gpu_detector.py / audio/ / video/detector.py / gui/) には該当しないため、Self-Test Report の `### 実機検証 (machine-unverifiable)` 節は plain bullet で「該当なし (workflow / issue template / skill md のみの変更)」と記述する。

## §8 Rollout

### §8.1 実装順序

```text
1. 本 spec を docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md に commit
2. writing-plans skill 起動 → docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md 作成
3. 実装フェーズ:
   a. #682 SKILL.md 改訂 + empirical 2 Iteration (eval/ アーティファクト生成) — sweep 規約自体を先に整備し、自身の review にも適用できる状態にする
   b. #624 workflow 改修 (script 切り出し + unit test + yml 修正)
   c. #458 bug_report.yml 微修正 (placeholder / description / markdown 案内)
4. PR 作成 Pre-flight (Iron Law 6):
   - git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline
   - 取り込み未済 commit ある場合 → git merge origin/develop-0.2.0
   - gh pr list --search "Group G" --state all で並行 PR 重複確認
5. PR 作成 (Refs #624 #458 #682、§6.2 の受け入れ条件統合形式)
6. /review-pr で 3 issue 分の受け入れ条件逐条検証 + acceptance gate
7. CI 確認 (markdownlint / yamllint / node --test)
8. merge
9. /close-issue skill で 3 issue 順次 close (束ね PR ケース、各 issue 個別 Idios 確認):
   - #624: 全項目検証 → close
   - #682: 全項目検証 → close
   - #458: deferred 残作業 (L3 初期 UI 実測) を残して close するか, open 維持するか Idios 判断 (memory feedback も参照)
```

### §8.2 着手順序の根拠

**a. #682 を先に**: sweep 規約を先に SKILL.md に入れることで、本 PR 自身の `/review-pr` が新しい規約で動作する (#682 の規約は「同種パターン全件 sweep」であり、本 PR にも応用可能)。

**b. #624 を次に**: workflow script 切り出し + unit test 整備。新 workflow は merge 後の次回以降の PR から適用される。

**c. #458 を最後に**: 最小修正、他 2 件と独立。

## §9 トレードオフ整理

| 設計ポイント | 選択 | リスク | 緩和 |
| --- | --- | --- | --- |
| #458 を本 spec に含めるか | 含む (Q1 (B)) | bug_report.yml の変更が #669 (Group D) と重複するリスク | field id rename 禁止、最小変更にとどめる、note 追加と placeholder 微修正のみ |
| 1 PR 統合 | (Q6 (B)) | Iron Law 3 (1 PR = 1 issue) 違反警戒 | PR スコープを「Group G workflow / CI / docs 仕上げ」と明示、3 issue Refs、受け入れ条件 sub-section で分離記述 |
| section-aware ルール | allowlist 厳密 (Q5 (A)) | `## Receiving Criteria` 等の variant heading が無視される | spec で許容 heading を明示、必要時に拡張、`## 受け入れ条件` / `## Acceptance criteria` のみで現状の PR template と整合 |
| empirical 2 Iter | issue 本文通り (Q4 (a)) | mock シナリオ作成コスト | PR #675 を base にすれば既存事例の再現で済む |
| script 切り出し | yml inline → 別 .js file | 追加 file による yml の checkout 依存 | `actions/checkout@v4` を 1 step 追加で対応、unit test 可能化のメリットが上回る |

## §10 Memory feedback / 関連 doc

> Iron Law 整合は [§6.4](#64-iron-law-整合) を参照 (本節では重複させない)。

### Memory feedback 適用

- `feedback_gh_command_ja_heredoc.md`: `gh pr create --body-file -` で日本語本文を渡す
- `feedback_skill_revision_empirical.md`: §5.3 の empirical-prompt-tuning で 2 Iteration
- `feedback_taskstop_child_process_leak.md`: empirical 検証で subagent dispatch する場合、`run_in_background` 子プロセス残留に注意

### 関連 doc

- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger / `束ね PR` の close フロー
- [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md) — Group G の roadmap 位置づけ (wave 0 Lane IV-b)
- [`.claude/skills/review-pr/SKILL.md`](../../../.claude/skills/review-pr/SKILL.md) — §5 改修対象
- [`.claude/skills/review-pr/eval/`](../../../.claude/skills/review-pr/eval/) — §5.3 empirical 検証アーティファクト配置先
- [`.claude/hooks/session-start.sh`](../../../.claude/hooks/session-start.sh) — Iron Law の正
- [`.github/workflows/pr-checklist.yml`](../../../.github/workflows/pr-checklist.yml) — §3 改修対象
- [`.github/ISSUE_TEMPLATE/bug_report.yml`](../../../.github/ISSUE_TEMPLATE/bug_report.yml) — §4 改修対象
