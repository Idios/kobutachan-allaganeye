# GUI プロトタイプ スクリーンショット

本ディレクトリには GUI プロトタイプ 5 画面 (drop / detecting / complete / preview / export) のスクリーンショットを配置する (予定)。

## 状態

**空 (追加待ち)**

## 追加手順

handoff bundle の指示により、Claude はブラウザ描画・スクリーンショット取得を行わない。Idios が手動で以下のファイルを追加する:

1. [`../bundle/project/Allagan Eye GUI.html`](../bundle/project/Allagan%20Eye%20GUI.html) をブラウザで開く (Chrome 推奨、インターネット接続要: React/Babel CDN)
2. 5 つのアートボード (state: drop / detecting / complete / preview / export) を順にスクリーンショット
3. 以下のファイル名で保存:
   - `01-drop.png`
   - `02-detecting.png`
   - `03-complete.png`
   - `04-preview.png`
   - `05-export.png`

推奨解像度: 1200×780 (アートボード 1 つ分)。全体を 1 枚に収めるのであれば `00-canvas-overview.png` も可。

スクリーンショットは Claude Code の実装時に視覚参照として使われる (handoff 側 README 指示)。

## 注意事項

- **FF14 ゲーム画面のスクリーンショットは含めない** (Square Enix 権利物、GitHub 登録不可)
- **プロトタイプ UI のスクリーンショットのみ** が対象
