# シナリオ B: edge - 束ね PR (複数 issue を 1 PR で閉じる、片方が部分未達)

参考事例: #449 (L2-0 ワークフロー刷新 + 旧ロール sweep) / #543 (GPU mode UX 三点修正)

## 紐づく issue (#910 / #911 として仮定)

### Issue #910

**タイトル**: `[task] GUI state store を Zustand から Jotai に移行 (評価検討)`

**ラベル**: `[task]`, `l2a-gui`, `P3-low`

**本文**:
```markdown
## 背景

現在 `gui/src/state/` は Zustand 採用 (#483 bootstrap 時選定)。
#464 以降の画面追加で selector 経由の re-render 問題が顕在化。
Jotai の atom 粒度で最適化できるか評価したい。

## 受け入れ条件

- [ ] `gui/src/state/appStateStore.ts` を Jotai atom ベースに書き換え
- [ ] `gui/src/state/metadataStore.ts` を Jotai atom ベースに書き換え
- [ ] vitest 既存テストが全 pass
- [ ] re-render profile を Playwright で比較し improvement を docs/design/README.md に追記
```

### Issue #911

**タイトル**: `[refactor] 旧 RestoreButton コンポーネントを削除し RestoreSection に統合`

**ラベル**: `[refactor]`, `l2a-gui`, `P3-low`

**本文**:
```markdown
## 背景

#516 で `RestoreButton` を追加したが、#520 で `RestoreSection` に吸収され、
`RestoreButton` は使われていない deadcode になっている。

## 受け入れ条件

- [ ] `gui/src/components/RestoreButton.tsx` を削除
- [ ] import 参照が残っていないか grep 検証
- [ ] vitest 既存テスト全 pass
```

---

## モック PR #912

**タイトル**: `refactor(gui): state store を Jotai に移行 + RestoreButton 削除 + docs 追記 (Refs #910 #911)`

**baseRefName**: `develop-0.2.0`

**labels**: `[task]`, `[refactor]`, `l2a-gui`

**本文**:
```markdown
## 概要

#910 と #911 をまとめて対応。関連するので 1 PR で処理。

- `gui/src/state/appStateStore.ts` を Jotai atom ベースに書き換え
- `gui/src/state/metadataStore.ts` を Jotai atom ベースに書き換え
- `gui/src/components/RestoreButton.tsx` を削除し、すべての import 参照を除去
- `gui/src/types/metadata.ts` の `MetadataEntry` 型を `MetadataRecord` にリネーム
  (命名一貫性改善)
- `docs/design/README.md` に Jotai 移行メモを追記

## 動作確認

- vitest: 全 pass
- Playwright re-render profile: 未実施 (次 PR で計測予定)
```

---

## 主要 diff 要約 (+420 / -530)

```
gui/src/state/appStateStore.ts      +105 -130   # Zustand → Jotai
gui/src/state/metadataStore.ts      +95  -140   # Zustand → Jotai
gui/src/components/RestoreButton.tsx  0  -85    # 削除
gui/src/components/RestoreSection.tsx +5  -3    # import 整理
gui/src/types/metadata.ts           +40  -35    # MetadataEntry → MetadataRecord リネーム
gui/src/state/metadataStore.test.ts +50  -30    # Jotai 対応
gui/src/screens/*.tsx               +20  -18    # MetadataRecord への追従 (5 ファイル)
docs/design/README.md               +15  -0     # Jotai 移行メモ
gui/package.json                    +2   -1     # jotai 追加、zustand 削除
gui/package-lock.json               +生成差分
```

### 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **束ね合理性の不足**: PR 本文は「関連するので 1 PR で処理」とだけ書かれ、束ねる合理性 (例: 型変更が両方に影響するので分離困難) が説明されていない。#910 と #911 は独立課題で、分けて処理可能
2. **#910 の受け入れ条件 部分未達**: 「re-render profile を Playwright で比較し improvement を docs/design/README.md に追記」が「次 PR で計測予定」として先送りされている。docs 追記も移行メモのみで profile 比較なし
3. **スコープ外変更**: `MetadataEntry` → `MetadataRecord` の型リネームが PR 本文では触れられているが、#910 #911 のどちらの受け入れ条件にも含まれていない (Iron Law 3 の典型的な「ついでに直した」パターン)
4. **テスト不足**: 型リネームに伴う screen 層 (5 ファイル) の変更に対して、screen 層の単体テストは追加されていない
5. **再 review ラウンド想定**: このモック は「Round 1 後に出された新指摘」の位置づけで、Round N 記法の必要性を subagent が認識するか確認する

## 検証環境情報

- CI: green (vitest / eslint / typecheck 全 pass、cargo check は該当なし)
- Playwright: 未設定 (GUI 側の再 render profile 用 tooling 未導入)
- `/enforce-acceptance-criteria` gate: 未実行
