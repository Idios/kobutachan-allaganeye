# シナリオ A: 中央値 (機能追加 PR、スコープ外改善候補が潜む)

参考事例: #525 (scorebar V2 + 4K DVR 対応) / #416 (verbose キャッシュ表示)

## 紐づく issue (#901 として仮定)

**タイトル**: `[task] 音声昇格条件に WR (Winning Roar) 検出を追加 (L3 準備)`

**ラベル**: `[task]`, `l1-residual`, `P2-medium`

**本文**:

```markdown
## 背景

現在の音声昇格 (`allaganeye/audio/scan.py`) は Fanfare ピーク検出のみ。
Fanfare は試合中にも弱いピーク (sim 0.65-0.75) を出すため、本条件のみでは偽陽性が混入しうる。
CLAUDE.md §検知アルゴリズム §音声昇格 の「既知の制約」で、WR (Winning Roar) 参照を同梱して
WR→Fanfare 間隔による (B) 条件を追加する旨を予告している。

## 受け入れ条件

- [ ] `audio/refs/wr.npz` を同梱し、`audio/matcher.py` で WR 参照ピークを検出できる
- [ ] `audio/scan.py` が Fanfare ピークと WR ピークの両方を返す
- [ ] `video/scorebar.py` の音声昇格条件を「Fanfare ピーク (A)」OR「WR→Fanfare 間隔 30-120s (B)」に拡張
- [ ] 新条件 (B) の単体テストを追加 (happy path + WR 検出失敗時 fallback)
- [ ] CLAUDE.md §音声昇格 の「既知の制約」文言を実装済み記述に更新

## 完了イメージ

`--audio` モード (デフォルト) で 2026-04-08 57:53 ケースの救済が維持されつつ、
試合中の Fanfare 弱ピーク由来の偽陽性が減ること。
```

---

## モック PR #902

**タイトル**: `feat(audio): WR 検出を音声昇格 (B) 条件として追加 (Refs #901)`

**baseRefName**: `develop-0.2.0`

**labels**: `[task]`, `l1-residual`

**本文**:

```markdown
## 概要

#901 の受け入れ条件を満たす実装。

- `audio/refs/wr.npz` を同梱 (validated set から生成)
- `audio/matcher.py` に `detect_wr_peaks()` を追加
- `audio/scan.py` の `scan_fanfare_peaks()` を `scan_audio_peaks()` にリネームし、
  Fanfare + WR の両方を返す
- `video/scorebar.py` の音声昇格ロジックを拡張:
  - 条件 (A): 既存の Fanfare ピーク (暗転後 0-60s)
  - 条件 (B): 新規。WR ピーク検出後 30-120s 以内に Fanfare ピーク
- 単体テスト 3 件追加

## 既知の限界

軽微な lint warning 修正も含む (別ファイル)。
テストは happy path のみ。WR 検出失敗時の fallback ケースは実装上 (A) 条件が動くので
テスト省略。

## 動作確認

2026-04-08 57:53 ケース: 救済継続確認
2026-04-14 録画: 試合中 Fanfare 弱ピーク 3 箇所が偽陽性から外れた
```

---

## 主要 diff 要約 (+380 / -72)

```text
allaganeye/audio/refs/wr.npz        (new file, binary)
allaganeye/audio/matcher.py         +45  -5    # detect_wr_peaks 追加
allaganeye/audio/scan.py            +38  -18   # scan_audio_peaks へリネーム、戻り値拡張
allaganeye/video/scorebar.py        +62  -15   # 条件 (B) 追加
allaganeye/commands/split_matches.py +8  -8    # scan_fanfare_peaks → scan_audio_peaks 追従
tests/test_audio_wr.py              +110 -0    # 新規: detect_wr_peaks happy path + scan_audio_peaks
tests/test_scorebar_promotion.py    +85  -6    # 条件 (B) happy path のみ追加
allaganeye/cli.py                   +3  -2     # 無関係な lint warning 修正 (unused import 削除)
CHANGELOG.md                        +5  -0
```

### 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **docs 更新漏れ**: `CLAUDE.md` §音声昇格 の「既知の制約」文言が未更新 (受け入れ条件の最終項目が未達)
2. **テストの未カバー分岐**: PR 本文で「fallback ケースは (A) 条件が動くのでテスト省略」と自己判定しているが、受け入れ条件に「WR 検出失敗時 fallback のテスト」が明記されている → 受け入れ条件未達
3. **スコープ外変更**: `allaganeye/cli.py` の lint warning 修正が PR 本文に記載あるが、PR スコープは音声昇格拡張。scope-guard 観点で分離すべき候補 (軽微だが別 issue 化で追跡すべきか)
4. **関数リネーム影響範囲**: `scan_fanfare_peaks` → `scan_audio_peaks` を `split_matches.py` で追従しているが、他の import 箇所 (テスト / 外部ドキュメント参照) の調査痕跡が PR 本文にない

## 検証環境情報

- CI: green (lint / pytest 全 pass)
- `/enforce-acceptance-criteria` gate: 未実行
