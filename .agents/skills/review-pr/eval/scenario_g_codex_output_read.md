# シナリオ G: codex_output_read (#949→#1043 で `codex` CLI に統合)

`/review-pr` Step 5a の §「Codex 出力の読み取り」を対象とする EPT シナリオ。
第 1043 号 (`#1043`) で旧 companion script の job 追跡機構 (`status` / `result` / job id) を廃止し、
`codex` CLI 直呼び (`codex review --base <base> "<focus>"`、stdout 直読) に統合したため、
本シナリオはその新契約を検証する。iterate-review 側は
[`../../iterate-review/eval/scenario_g_codex_output_read.md`](../../iterate-review/eval/scenario_g_codex_output_read.md) を参照。

## G-1 (中央値): `codex review` が正常完了したあとの finding 取り込み

### 想定状況

PR `#<N>` は `allaganeye/video/detector.py` の core ロジック変更を含み、`/review-pr` Step 5a の
Codex review 起動条件の条件 3 (§「core 変更対象ファイル」の表に該当) を満たす。tier 1 = `codex` CLI 直接呼び出しで
`codex review --base develop-0.4.0 "<focus>"` を Bash 実行し、**exit code 0 で完了した**。
executor は Step 5b トリアージ表へ finding を統合する直前の地点にいる。

### 期待挙動

`codex review` の stdout をそのまま finding の入力にする。旧 `status` / `result` / job id 追跡機構は使わない。

### 要件チェックリスト

1. **[critical]** finding の取り込み元が `codex review` の stdout であることが deliverable から判る
2. **[critical]** `codex review` を実行する具体的な command が 1 本示され、そのまま実行できる形になっている (プレースホルダのみで終わっていない)
3. 旧 companion script の `status` / `result` / job id 追跡機構を**使っていない** (廃止済であることを認識している)
4. 実行する cwd の制約に言及している
5. Step 5b トリアージ表への統合 (出所の記載) に触れている

## G-2 (edge): `codex review` は exit 0 だが stdout が空 / parse 不能だった

### 想定状況

G-1 と同じ状況だが、`codex review --base develop-0.4.0 "<focus>"` が **exit code 0** で完了したものの
stdout が空 (または finding として parse できない) だった。stderr には error らしきものは出ていない。

### 期待挙動

exit 0 でも stdout が空 / parse 不能は「応答異常」として扱い、Codex の正常完了とはみなさない。
§Codex fallback の検出条件に従って扱う (fallback 待ち / 記録)。

### 要件チェックリスト

1. **[critical]** exit 0 を「正常完了」とみなして空の stdout を finding にする、という誤りをしていない
2. **[critical]** 「応答異常」として扱う (正常完了と区別している)
3. その後の扱い (§Codex fallback の検出条件 or 記録) に言及している
4. Step 6 レビュー報告の記録 1 行 (3 状態のどれか) で何と書くかが理由付きで示されている

## G-4 (hold-out): Pre-flight Step 5 の `codex review` を読み戻す

> **hold-out**。iteration 0-3 では使わず、収束判定時の overfitting check にのみ使う。
> `docs/l2-workflow.md` §「Codex 出力の読み取り」が skill 経由でなく**単独で**機能するかを見る。

### 想定状況

PR 作成直前の Iron Law 6 Pre-flight Step 5 で `codex review --base develop-0.4.0 "<focus>"` を
実行し exit 0 で完了した。executor は finding を triage して PR 本文へ反映する直前にいる。

### 要件チェックリスト

1. **[critical]** finding の取り込み元が `codex review` の stdout である
2. **[critical]** 実行する command が具体的で、そのまま実行できる形になっている
3. cwd の制約に言及している
