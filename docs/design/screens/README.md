# GUI プロトタイプ スクリーンショット

GUI プロトタイプ 5 画面 (drop / detecting / complete / preview / export) のスクリーンショット。

> **実装は 6 画面**である (`minimap` が [#893](https://github.com/Idios/kobutachan-allaganeye/issues/893) で追加)。本ディレクトリは **handoff bundle 由来のプロトタイプ**を保持する場所で、`minimap` はプロトタイプが存在しない (bundle より後に設計された) ため 5 枚のままである。**実装された 6 画面のスクリーンショットは `image/` 配下** (`01-drop.png` 〜 `06-minimap.png`) を参照。

## ファイル一覧

| ファイル | 画面 | 状態 |
| --- | --- | --- |
| [`01-drop.png`](01-drop.png) | ① インポート (Drop / Import) | state: drop |
| [`02-detecting.png`](02-detecting.png) | ② 検知中 (Detecting) | state: detecting |
| [`03-complete.png`](03-complete.png) | ③ 一覧 (Matches) | state: complete |
| [`04-preview.png`](04-preview.png) | ④ 境界調整 (Preview) | state: preview |
| [`05-export.png`](05-export.png) | ⑤ 書き出し (Export) | state: export |

解像度: 約 1836 × 1323 (アートボード 1200 × 780 ＋ キャプション)。

## 用途

- 実装時の視覚参照 (handoff 側 README の指示: `bundle/project/variants/aether.jsx` のコンポーネント形状と合わせて参照する)
- レビュー時の比較基準 (実装結果とスクショを対比して差分確認)
- ユーザーガイド・ドキュメントでの利用 (将来)

## 注意事項

- **FF14 ゲーム画面のスクリーンショットは含めない** (Square Enix 権利物、GitHub 登録不可)
- 本ディレクトリ内は**プロトタイプ UI のスクリーンショットのみ**
- プロトタイプに変更があった場合は、Idios が手動で再取得して差し替える (handoff bundle README の指示により Claude はブラウザ描画・スクショ取得を行わない)
