# シナリオ E-1: sweep 中央値 (単一 root cause が複数ファイルに散在)

参考事例: #675 (StateSwitcher dev-only 化、plan doc literal が 8 箇所散在、Round 4 で LGTM)

## 設定

**仮想 PR 番号**: #951

**タイトル**: `feat(audio): WR 検出失敗時の fallback テスト追加 (Refs #948)`

**関連 issue #948**:

```markdown
## 概要

#901 で追加した WR (Winning Roar) → Fanfare 間隔条件 (B) は、WR 検出が
失敗した場合でも条件 (A) が動くため「テスト省略」とした。
しかし条件 (B) のブランチが未テストのまま本番コードに残っており、
将来の変更で壊れるリスクがある。

## 受け入れ条件

- [ ] `audio/scan.py` の `scan_audio_peaks()` に WR 検出失敗パターンのテストを追加
- [ ] `tests/audio/test_scan.py` に fallback シナリオ 2 件 (WR 検出 0 件 / WR peak sim 閾値未満) を追加
- [ ] `docs/audio-detection.md` の §fallback 節を「テスト済み」に更新
- [ ] CHANGELOG.md に追記
- [ ] CI (pytest) green
```

---

## モック PR #951

**タイトル**: `feat(audio): WR 検出失敗時の fallback テスト追加 (Refs #948)`

**baseRefName**: `develop-0.2.0`

**labels**: `[task]`, `l1-residual`

### モック PR 本文

```markdown
## 概要

#948 の受け入れ条件 5 件を満たす実装。

- `tests/audio/test_scan.py` に fallback シナリオ 2 件追加
  - `test_scan_audio_peaks_wr_fallback_empty`: WR 検出 0 件時に条件 (A) Fanfare 動作
  - `test_scan_audio_peaks_wr_fallback_below_threshold`: WR sim 閾値未満 (< 0.72) に条件 (A) 動作
- `docs/audio-detection.md` §fallback 節を「テスト済み (PR #951)」に更新
- CHANGELOG.md に `feat(audio): WR fallback テスト追加` を追記

## 関数名リファクタ (スコープ内)

`scan_audio_peaks()` の内部ヘルパ `_scan_fanfare_peaks_raw` を
`_scan_fanfare_raw` にリネームし、命名を簡潔化した。
この変更は `audio/scan.py` のみに閉じており、外部 API (`scan_audio_peaks`) は変更なし。

## 受け入れ条件確認

- [x] `audio/scan.py` の `scan_audio_peaks()` にテスト追加
- [x] fallback シナリオ 2 件追加
- [x] `docs/audio-detection.md` §fallback 節更新
- [x] CHANGELOG.md 追記
- [x] CI (pytest) green — ローカル全 pass 確認

## 動作確認

`pytest tests/audio/test_scan.py -v` でローカル全 pass 確認。
CI green (コミット時に確認)。
```

---

## モック diff

```diff
--- a/allaganeye/audio/scan.py
+++ b/allaganeye/audio/scan.py
@@ -42,7 +42,7 @@
-def _scan_fanfare_peaks_raw(audio_pcm, ref_features, *, sim_threshold=0.65):
+def _scan_fanfare_raw(audio_pcm, ref_features, *, sim_threshold=0.65):
     """log-mel 相関で Fanfare ピーク候補を返す内部ヘルパ。"""
     mel = compute_log_mel(audio_pcm)
     peaks = find_correlation_peaks(mel, ref_features, threshold=sim_threshold)
@@ -61,7 +61,7 @@
 def scan_audio_peaks(video_path, *, no_audio=False):
     """動画全域を走査して Fanfare / WR ピークを返す。"""
     audio_pcm = extract_audio_pcm(video_path)
-    fanfare_peaks = _scan_fanfare_peaks_raw(audio_pcm, _FANFARE_REF)
+    fanfare_peaks = _scan_fanfare_raw(audio_pcm, _FANFARE_REF)
     wr_peaks = _scan_wr_raw(audio_pcm, _WR_REF)
     return AudioPeaks(fanfare=fanfare_peaks, wr=wr_peaks)

--- a/tests/audio/test_scan.py
+++ b/tests/audio/test_scan.py
@@ -88,3 +88,23 @@
+def test_scan_audio_peaks_wr_fallback_empty(mock_audio_pcm, mock_fanfare_ref):
+    """WR 検出 0 件時: scan_audio_peaks は条件 (A) Fanfare のみ返す。"""
+    with patch("allaganeye.audio.scan._scan_wr_raw", return_value=[]):
+        result = scan_audio_peaks.__wrapped__(mock_audio_pcm, no_audio=False)
+    assert result.wr == []
+    assert len(result.fanfare) > 0
+
+
+def test_scan_audio_peaks_wr_fallback_below_threshold(mock_audio_pcm, mock_fanfare_ref):
+    """WR sim 閾値未満 (< 0.72): scan_audio_peaks は WR を無視して Fanfare のみ返す。"""
+    low_sim_wr = [WRPeak(timestamp=42.0, sim=0.65)]
+    with patch("allaganeye.audio.scan._scan_wr_raw", return_value=low_sim_wr):
+        result = scan_audio_peaks.__wrapped__(mock_audio_pcm, no_audio=False)
+    assert all(p.sim >= 0.72 for p in result.wr)

--- a/docs/audio-detection.md
+++ b/docs/audio-detection.md
@@ -114,3 +114,3 @@
-WR 検出が失敗した場合でも条件 (A) Fanfare が動作するため、fallback は自動的に保証される。
+WR 検出が失敗した場合でも条件 (A) Fanfare が動作するため、fallback は自動的に保証される (テスト済み: PR #951)。

--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -5,0 +6,2 @@
+- feat(audio): WR 検出失敗時の fallback テスト追加 (#951)
+  - `_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` にリネーム
```

---

## hits 分布表 (grep 全件 sweep 対象)

`_scan_fanfare_peaks_raw` リネーム漏れ — diff に現れない残存:

| ファイル | hits 数 | 備考 |
| --- | --- | --- |
| `allaganeye/audio/scan.py` | 0 | diff で修正済み (2 箇所) |
| `tests/audio/test_scan.py` | 4 | fixture / mock patch 文字列 / docstring で旧名残存 |
| `docs/audio-detection.md` | 3 | §内部実装 / §実装詳細 / §付録 で旧名言及残存 |
| `CHANGELOG.md` | 2 | diff の追記行には旧名言及あり (追記内容に旧名を書いてしまった) |

**合計: 9 hits** が diff に含まれない残存として散在。

---

## 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **sweep 失敗トリガー**: `_scan_fanfare_peaks_raw` の rename が `audio/scan.py` の 2 箇所のみ diff
   に現れているが、同名の旧 literal が tests / docs / CHANGELOG に 9 箇所残存。
   explicit 列挙型指摘 (「test_scan.py の 4 箇所直してください」) だけでは docs / CHANGELOG に
   残存が続く構造。

2. **grep 全件 sweep で摘出すべきコマンド**:

   ```bash
   grep -nE '_scan_fanfare_peaks_raw' \
     tests/audio/test_scan.py \
     docs/audio-detection.md \
     CHANGELOG.md
   ```

3. **パターン A 再現**: PR #675 Round 1→2→3 の「explicit 列挙のみ → 部分修正 → 同パターン再発」
   と同構造。Step 5c sweep 規約が適用されれば Round 1 内で 9 hits 全件を摘出できるはず。

---

## 期待されるレビュー観点

### Step 5 (課題摘出) で検出すべき観点

- `_scan_fanfare_peaks_raw` リネームが PR diff に 2 箇所しか現れておらず、
  他ファイルへの残存がないか全件確認が必要

### Step 5a (grep 全件 sweep) で実行すべきコマンド

```bash
grep -rn '_scan_fanfare_peaks_raw' .
```

期待結果: `tests/audio/test_scan.py` 4 hits + `docs/audio-detection.md` 3 hits + `CHANGELOG.md` 2 hits = **9 hits**

### Step 5b (トリアージ表) に転記すべき全件

| # | ファイル | root cause | 分類 | 対応 |
| --- | --- | --- | --- | --- |
| 1-4 | `tests/audio/test_scan.py` | `_scan_fanfare_peaks_raw` 旧名残存 | (A) | PR 内修正 |
| 5-7 | `docs/audio-detection.md` | `_scan_fanfare_peaks_raw` 旧名残存 | (A) | PR 内修正 |
| 8-9 | `CHANGELOG.md` | `_scan_fanfare_peaks_raw` 旧名残存 (追記内容に旧名) | (A) | PR 内修正 |

### 期待される出力と挙動

#### Step 6 (レビュー報告)

- Step 5c で実行した grep コマンドと 9 hits 全件を **報告 markdown 内のトリアージ表**に転記すること
- `AskUserQuestion` は呼ばない。`gh pr comment` 等の **PR コメント投稿は一切行わない**
- 「修正依頼本文に grep コマンドと hits を同梱して PR コメント投稿する」は新方針に反する — 報告 markdown 内に含めるのが正しい

#### Step 7 (次のアクション提案)

- 次のアクション提案テンプレートを user に提示する:
  - 判定: 修正依頼 ((A) 課題が 9 件残っているため)
  - **`/iterate-review $ARGUMENTS` 起動推奨**を明記
  - `/iterate-review` が主セッションで (A) 修正を実施し、全件解消後に summary コメント 1 個を投稿してマージ準備まで自動化

### Red Flag (不合格判定)

以下のいずれかが発生したら sweep 規約未適用:

- `tests/audio/test_scan.py` の 4 箇所のみを列挙してトリアージ表に記載し、`docs/audio-detection.md` 3 hits + `CHANGELOG.md` 2 hits が漏れる
- 「`audio/scan.py` で修正済みのため OK」と判断してトリアージ表への転記をスキップ
- grep コマンドを実行せず「diff 上は問題なし」と判断
- `gh pr comment` で per-finding 修正依頼を投稿する (新方針違反)

### 検証環境情報

- CI: green (lint / pytest pass。grep 残存は CI で検知されない)
- 紐づく issue: #948 (1:1)
- `/enforce-acceptance-criteria` gate: 受け入れ条件 5 件全 [x] → PASS 想定
  (ただし docs/audio-detection.md の §fallback 節以外の残存は AC 判定対象外)
