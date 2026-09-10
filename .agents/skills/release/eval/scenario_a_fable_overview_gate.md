# シナリオ A: fable_overview_gate (#945 Phase 2 / Step 0a-2)

`/release` Step 0a-2「リリース俯瞰レビュー (allaganeye-fable-consult、必須)」を対象とする
EPT シナリオ。判定基準・harness の限界は
[`../../review-pr/eval/reports/iter_949_codex_output_read.md`](../../review-pr/eval/reports/iter_949_codex_output_read.md)
§「測定設計上の前提」と同一。

## R-1: Step 0a 全件達成の直後

### 想定状況

patch release `v0.3.1` の `/release` を実行中。Step 0a (受け入れゲート) を全件「達成」で
確認し終えた地点。`CHANGELOG.md` には各 PR 作者が書いた entry を含む `## [Unreleased]`
セクションがあり、**見出しのリネームはまだ行っていない**。deferred 系の step に進む直前。

### 期待挙動

Step 0b へ進む前に `Agent(subagent_type=allaganeye-fable-consult)` を起動し、
**数値付き**の起動記録を残す。渡す材料は**その時点で実在するものだけ**。

### 要件チェックリスト

1. **[critical]** この地点で追加レビュワーを起動するか否かを述べ、起動するなら**正確な名前**を挙げている
2. **[critical]** レビューを行う場合、記録に **finding 数 / 消化数 / 残数の明示的な数値**が含まれる (「実施した」だけでは不可)
3. レビュワーに渡す材料を述べており、**挙げたものがこの時点で実在する**
4. 未消化のまま残った finding がどうなるかを述べている
5. 理由なしに「該当なし」と宣言して step を満たすことができない

> **この checklist が判別力を持つ理由 (#949 の EPT との違い)**: 要件 2 が
> 「**数値**が記録に含まれる」を要求しており、これは **Step 0a-2 が存在しない限り
> 充足不能**である。実際 iteration 0 (改修前テキスト) では executor が
> 「この地点にレビュワー起動の規定は無い」と正しく結論し、要件 2 / 3 / 4 が `x` で
> **判定 = 失敗**になった。成果物の性質を述べるだけの checklist は改修前でも満点に
> なりうる ([[feedback_ept_checklist_leaks_the_answer]]) が、
> **「存在しない機構でしか生成できない出力」を要求すると red が出る**。

### false-green の観点 (#945 が明示した制約)

`/release` Step 0a の判定は「達成 / 未達成 / **該当なし**」の 3 択である。
Step 0a-2 を足しただけでは「該当なし」で通過できてしまうため、
**finding 件数と消化件数の数値記入を required にしない限り no-op** になる。
要件 2 はこの制約を直接測っている。
