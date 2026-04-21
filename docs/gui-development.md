# GUI 開発ガイド (L2a)

Allagan Eye の L2a GUI は [Tauri 2](https://v2.tauri.app/) + [React 19](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/) で構築する。CLI (`allaganeye`) の薄いラッパとして動作し、Windows 専用 (L2 全体の決定 #451 に従う)。

本ドキュメントは **GUI 開発者 / コントリビュータ向け**。エンドユーザー向けのクイックスタートは [`quickstart.md`](quickstart.md) を参照 (GUI のエンドユーザー案内は #464 Phase 2 以降に追記予定)。

## 前提条件

| ツール | 最小バージョン | インストール方法 (Windows) |
|---|---|---|
| Node.js | 22 LTS | [nodejs.org](https://nodejs.org/) / `winget install OpenJS.NodeJS.LTS` |
| Rust | 1.80+ | [rustup.rs](https://rustup.rs/) (`rustup-init.exe`) |
| Microsoft C++ Build Tools | Visual Studio 2022 相当 | `rustup` 初回実行時に案内あり / [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |
| WebView2 Runtime | 同梱 (Windows 11) | Windows 10 の場合は [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/) から入手 |

## セットアップ

```bash
cd gui
npm install
```

初回のみ。以降は `package-lock.json` に基づいて `npm ci` でも可。

## 開発起動

```bash
cd gui
npm run tauri dev
```

Tauri CLI が以下を並列起動する:

1. Vite dev server (`http://127.0.0.1:1420`)
2. `cargo run` で Rust バックエンドをビルド・実行
3. WebView2 ウィンドウが Vite dev server をロード

ファイル編集で HMR (hot module replacement) が発動する。Rust 側の変更は再ビルドが必要。

## ビルド確認 (smoke test)

```bash
cd gui
npm run lint         # ESLint (flat config)
npm run typecheck    # tsc --noEmit
npm test             # vitest (jsdom + @testing-library/react)
npm run build        # vite build → gui/dist/
cd src-tauri
cargo check          # Rust 側の型/依存チェック
```

`cargo check` は `tauri.conf.json` の `frontendDist: "../dist"` を要求するため、**必ず `npm run build` を先に実行する必要がある**。

## テスト

- **フレームワーク**: [vitest](https://vitest.dev/) + [@testing-library/react](https://testing-library.com/docs/react-testing-library/intro/) + [jsdom](https://github.com/jsdom/jsdom)
- **配置規約**: ソースと同一ディレクトリに `*.test.ts` / `*.test.tsx` として配置 (`src/lib/foo.ts` → `src/lib/foo.test.ts`)
- **セットアップ**: `src/test-setup.ts` で `@testing-library/jest-dom` matcher と `afterEach(cleanup)` を注入 (`vite.config.ts` の `test.setupFiles` で参照)
- **watch モード**: `npm run test:watch`

現時点で追加済みのテスト:

- `src/lib/preventBrowserShortcuts.test.ts`: WebView のブラウザショートカット抑止ロジックの単体テスト (F5/Ctrl+R/F12/Ctrl+U/Ctrl+P 等の分類 + installer の preventDefault 呼び出し確認)
- `src/App.test.tsx`: placeholder の smoke render テスト

## CI 構成

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) に 3 ジョブが定義されている:

| ジョブ | OS | 役割 |
|---|---|---|
| `python` | ubuntu-latest | 既存: ruff / pyright / pytest |
| `gui-frontend` | ubuntu-latest | npm ci → lint → typecheck → build → `gui/dist/` をアーティファクト保存 |
| `gui-rust` | windows-latest | `gui-frontend` のアーティファクトを取得して `cargo check` |

`gui-rust` が Windows runner なのは **L2 の Windows 専用ターゲット (#451) に合わせるため**。`gui-frontend` を ubuntu 分離しているのはコスト最適化 (Windows runner は低速)。

## アーキテクチャ概要

全体像・シーケンス図は `plans/` の bootstrap 計画 (`twinkling-sauteeing-sunset.md` 相当、PR #483 のアーカイブ) を参照。要点:

- **UI 層**: React 19 + TypeScript が `gui/src/` 配下。state 管理は [Zustand](https://github.com/pmndrs/zustand) (#482 で決定)。
- **IPC**: `@tauri-apps/api` の `invoke('command', args)` / `listen('event', cb)` で Rust 側と通信。
- **Rust 層**: `gui/src-tauri/` が Cargo crate。plugin として `dialog` / `fs` / `shell` を有効化。axum HTTP サーバ (動画配信用) は #465 Phase 3 で実装。
- **外部バイナリ**: `allaganeye` CLI・`ffmpeg` は `tauri-plugin-shell` + `tokio::process::Command` で子プロセス起動。stdout/stderr の両方を行単位で event emit し、exit code もフロントに返す。
- **設計源流**: [`docs/design/phase0-tauri-reference.md`](design/phase0-tauri-reference.md) に Phase 0 で検証済みの全実装断片がある。

## トラブルシュート

### `cargo check` が `frontendDist "../dist" doesn't exist` で失敗

→ 先に `npm run build` を実行する。`tauri-build` (build.rs) が `gui/dist/` の存在を要求するため。

### `npm run tauri dev` 起動後、Tauri ウィンドウが空白

→ Vite dev server (`http://127.0.0.1:1420`) が他プロセスに専有されている可能性。`npm run dev` 単体で起動確認し、ポート競合を解決する。

### production build で F5 を押しても反応しない

→ 仕様。`gui/src/main.tsx` で `import.meta.env.PROD` 時に F5 / Ctrl+R / Ctrl+Shift+R / F12 / Ctrl+U / Ctrl+P / 右クリックを `preventDefault` している。詳細は `gui/src/main.tsx` の keydown ハンドラを参照。

### DevTools (F12) が開かない

→ 仕様。production ビルドでは Tauri が DevTools を無効化する。debug ビルド (`npm run tauri dev`) では開く。

### Windows で `error: linker 'link.exe' not found`

→ MSVC Build Tools が未インストール。Visual Studio Build Tools 2022 の「C++ build tools」ワークロードをインストールして PATH を通す。

## バージョンポリシー

- **strict pin**: `package.json` および `Cargo.toml` の全依存を `=x.y.z` で厳格ピン。Phase 0 (#468) で検証した挙動を再現可能にするため
- **アップデート**: パッチ/マイナー更新は手動で行い、動作確認の上コミット
- **Cargo.lock / package-lock.json**: application なので commit する

## 実装進捗

L2a の画面は 4 Phase に分かれている ([docs/design/README.md](design/README.md) 参照):

- **#483 bootstrap**: 本 scaffold (プレースホルダ画面のみ)
- **#463 Phase 1**: CLI 分離 + TS 型 + Zustand store
- **#464 Phase 2**: 5 画面骨格 (drop/detecting/complete/preview/export) + aetherTheme CSS
- **#465 Phase 3**: preview 画面の axum HTTP 動画配信、CLI stdout/stderr streaming
- **#466 Phase 4**: export 画面の ffmpeg 実行制御
