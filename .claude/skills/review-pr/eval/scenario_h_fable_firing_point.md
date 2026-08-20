# シナリオ H: fable_firing_point (#945 allaganeye-fable-consult の発火点)

`/review-pr` Step 5a に新設した §「optional 俯瞰レビュー (allaganeye-fable-consult)」を対象とする
EPT シナリオ。**発火する側 (F-1) と発火しない側 (F-2) の対**で構成する
(片側だけだと「常に起動する」実装でも通ってしまう)。

## F-1 (発火する側): doc-only + spec doc 新規追加

### 想定状況

PR は `docs/` 配下 5 file の変更に加え、`docs/superpowers/specs/` へ新規 spec doc を 1 件追加する。
code file の変更はゼロ。diff 320 行、single root cause。
executor は Step 5a を進めて Step 6 レビュー報告を組み立てる直前にいる。

### 期待挙動

`allaganeye-fable-consult` を起動し、finding を Step 5b へ **skill が定義した出所ラベル**で統合する。
起動記録は数値付きで書く。

### 要件チェックリスト

1. **[critical]** 起動する専門レビュアーを**正確な名前で**挙げている
2. **[critical]** 起動有無を問わず、レビュアーごとに Step 6 へ 1 行記録がある (非起動時は理由付き)
3. doc / spec 品質を見るレビュアーを起動した場合、finding が出所ラベル付きで Step 5b へ流れる
4. 「意図的に skip」と「忘れた」が事後に区別できる
5. 起動したレビュアーに何を見せたかを述べている

## F-2 (発火しない側): 通常の code PR

### 想定状況

`allaganeye/export/pool.py` / `tests/test_pool.py` / `docs/cli-spec.md` の 3 file、diff 90 行、
single root cause。doc-only でなく、spec / plan の新規追加もなく、15 file / 500 行 を大きく下回り、
L1 core (CLI / detector / GPU) の変更でもない。

### 期待挙動

Fable も Codex も**起動せず**、どちらについても理由付きの 1 行記録を残す。
**skill が定義していない記録書式を発明しない。**

### 要件チェックリスト

1. **[critical]** 起動する / しないレビュアーを正確な名前で挙げている
2. **[critical]** skill が定義する全レビュアーについて、起動有無の 1 行記録がある (非起動時は理由付き)
3. 理由が本 PR の実際の性質 (file 数 / 行数 / 変更種別) に基づいており、汎用文言でない
4. 「意図的に skip」と「忘れた」が事後に区別できる
5. **skill が定義していない記録書式を発明していない**

> **F-2 の 要件 5 が対になっている理由**: F-1 だけだと「起動して何か書けば通る」ため、
> 書式を実行者が発明しても検出できない。改修前テキストでは実際に executor が
> 出所ラベルと記録行の**両方を発明した** (iteration 0 の red baseline)。
