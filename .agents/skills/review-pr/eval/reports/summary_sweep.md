# sweep 規約検証 — Iteration 0/1 比較サマリ

## [critical] 達成率

| シナリオ | Iteration 0 (baseline) | Iteration 1 (revaluation) | 改善 |
| --- | --- | --- | --- |
| E (中央値, PR #951) | 1 / 4 | 4 / 4 | +3 |
| E2 (混在, PR #952) | 0 / 4 | 4 / 4 | +4 |
| E3 (doc-only, PR #953) | 1 / 4 | 4 / 4 | +3 |

合計: Iteration 0 = 2 / 12, Iteration 1 = 12 / 12, 改善 = +10

---

## 構造的欠陥の解消

### シナリオ E (中央値: 単一 root cause の複数ファイル散在)

**Iteration 0 で識別された欠陥**:

- Step 5a に grep 全件 sweep の強制規約がなく「残存の可能性がある」という観点表明にとどまった
- explicit 列挙型の指摘で止まり、diff 外ファイルへの mandate がなかった
- 9 hits が Round 2/3 に分散するリスクが残った

**Iteration 1 での解消**:

- Step 5c 適用を Step 5.1 で明示宣言し、`grep -nE '_scan_fanfare_peaks_raw'` コマンドを Step 5a で提示
- Step 5b トリアージ表に全 9 hits を個別列挙 (tests 4 + docs 3 + CHANGELOG 2)
- 修正依頼コメントに grep コマンドと hits 数を同梱し、Round 1 で全件捕捉を達成
- divergence リスクを排除

### シナリオ E2 (複数 root cause 混在: schema 誤変更 + base regression + 旧 API)

**Iteration 0 で識別された欠陥**:

- Root Cause 2 の波及確認が `metadata_writer.py` 1 ファイルにとどまり、schema + gui 4 ファイルへの grep sweep が実施されなかった
- Root Cause 3 は diff 未掲載のため「可能性がある」の一般警告にとどまった
- 過去事例 (PR #627 Round 4 / PR #675 Round 1) との接続がなく、同種パターン再発の認識機構が働かなかった

**Iteration 1 での解消**:

- RC1 / RC2 / RC3 の 3 コマンドを Step 5a で提示 (`additionalProperties` / `gpu_vendors_available` 5 ファイル / `vi.stubEnv` 旧 API)
- Step 5b に全 9 hits を個別列挙 (RC1 = 1 / RC2 = 5 / RC3 = 3)
- RC2 で「PR #627 Round 4 CRITICAL と同構造」、RC3 で「PR #675 Round 1 と同種」を明示
- RC2 の 5 hits を全件 CRITICAL 分類し、Round 1 で全件捕捉

### シナリオ E3 (doc-only: 旧用語 literal が 5 ファイルに散在)

**Iteration 0 で識別された欠陥**:

- §D 適用の認識はあったが grep コマンドを具体的に提示せず、「grep してください」という PR コメント指示にとどまった
- doc-only PR への sweep mandate が明文化されておらず、12 hits の特定が PR 作成者に委ねられた
- requirements.md / SKILL.md の旧用語残存が見落とされやすい構造だった

**Iteration 1 での解消**:

- Step 5.1 で「doc-only 修正だから sweep 不要 = Red Flag」を明示
- Step 5a で 2 種の grep コマンドを提示
- Step 5b に全 12 hits を個別列挙 (specs/ 3 + plans/ 2 + CLAUDE.md 2 + requirements.md 3 + SKILL.md 2)
- §D CI 波及検証として `bash scripts/check-markdownlint.sh` 実行を (A) PR コメントに含めた
- Round divergence パターン (#661 Round 3 同構造) を Round 1 で阻止

---

## 打ち切り判定

- [critical] 全要件 Iteration 1 で **○ (12 / 12)** → **打ち切り** (Task 7 で確認)

[判定結果: **打ち切り** — Iteration 2 は不要。Task 7 で改訂 SKILL.md の最終確認と PR マージ判断へ]

---

## 補足: sweep 規約の有効性確認

Step 5c の追加 (commit `fc37237`) により以下が実証された:

1. **単一 root cause シナリオ (E)**: explicit 列挙型から全件 sweep 型へ。9 hits を Round 1 で全件捕捉
2. **複数 root cause シナリオ (E2)**: 3 root cause × 3 grep コマンド体系が機能。9 hits + CRITICAL 分類 + 過去事例参照を Round 1 で達成
3. **doc-only シナリオ (E3)**: Red Flag 識別 + §D CI 波及検証との連携が機能。12 hits を Round 1 で全件捕捉

Iteration 0 の 2/12 → Iteration 1 の 12/12 は、SKILL.md Step 5c の明示的な規約化によって達成されたものであり、改訂の有効性を実証する。
