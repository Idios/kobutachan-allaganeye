# Phase 0 Tauri 実装リファレンス

[#468](https://github.com/Idios/kobutachan-allaganeye/issues/468) で構築・検証した Tauri プロトタイプから、**L2a Phase 3 (preview 画面, [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465)) / Phase 4 (export, [#466](https://github.com/Idios/kobutachan-allaganeye/issues/466))** で再利用可能なコード片と設定を抜粋した技術リファレンス。

プロトタイプ本体 (`.claude/prototypes/tauri-phase0/`) は worktree 内 gitignore のため、worktree 削除で消滅する。本ドキュメントが唯一の保存先。

## 背景

Phase 0 で実測した Tauri 2.10.3 の挙動:

- **axum + tower-http の `ServeFile` 経由の video 配信** で 36 GB ファイルのランダム seek が p95 294 ms / 100/100 成功 (Electron の 352 ms を上回る)
- **`tokio::process::Command` + `app.emit()`** で allaganeye CLI stdout を行単位で realtime streaming (706s の長時間 detect で first-line 1.3-1.7s)
- `asset://` (convertFileSrc) 経由も動くが遅い (p95 991 ms)。本実装では axum 経路を優先

## ハマり箇所 (先に読んでおくと数時間節約)

| 症状 | 原因 | 修正 |
| --- | --- | --- |
| `tauri` dependency features mismatch, `protocol-asset` feature を要求 | tauri.conf.json で `assetProtocol.enable: true` だが Cargo.toml で features 未指定 | `tauri = { version = "2", features = ["protocol-asset"] }` |
| `Permission fs:allow-read-meta not found` | 存在しないパーミッション名 | `fs:allow-stat` を使う |
| `icons/icon.ico not found` | bundle inactive でも Windows resource 生成で必須 | ダミー ICO を PowerShell で生成し `tauri.conf.json > bundle > icon: ["icons/icon.ico"]` に登録 |
| `frontendDist "../dist" doesn't exist` | `cargo check` は `beforeBuildCommand` を実行しない | 事前に `npm run build` で `dist/` を作る、または cargo check 前に vite build 実行 |
| `vite.config.ts` async/process TS error | Vite 6 の UserConfigExport 型が async 関数を受け付けない、Node types 未導入 | `defineConfig({...})` を同期にし `declare const process: any` で逃げる |
| `CLI live log` が全行 2 倍表示 | React StrictMode で Tauri の async `listen()` が 2 回登録される | main.tsx から `<React.StrictMode>` を外す (本物実装では async-safe な useEffect パターンを使う) |
| Electron `child_process.spawn(..., { shell: true })` でスペース入りパス分断 | shell=true で cmd.exe が空白を引数区切りと解釈 | `shell: false` (既定) にして Node の `CreateProcess` に任せる |

## 必要な dependencies

### `src-tauri/Cargo.toml`

```toml
[package]
name = "<your-crate>"
version = "0.0.0"
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = ["protocol-asset"] }
tauri-plugin-dialog = "2"
tauri-plugin-fs = "2"
tauri-plugin-shell = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
tokio-util = { version = "0.7", features = ["io"] }
axum = { version = "0.7", features = ["macros"] }
tower-http = { version = "0.5", features = ["fs"] }
hyper = "1"
futures = "0.3"
urlencoding = "2"
percent-encoding = "2"

[features]
default = ["custom-protocol"]
custom-protocol = ["tauri/custom-protocol"]

[lib]
name = "<your_crate>_lib"
crate-type = ["staticlib", "cdylib", "rlib"]
```

### `src-tauri/tauri.conf.json` (抜粋)

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "identifier": "dev.allaganeye.gui",
  "build": {
    "beforeDevCommand": "npm run dev",
    "devUrl": "http://127.0.0.1:1420",
    "beforeBuildCommand": "npm run build",
    "frontendDist": "../dist"
  },
  "app": {
    "security": {
      "csp": "default-src 'self' ipc: http://ipc.localhost http://127.0.0.1:* ; style-src 'self' 'unsafe-inline'; media-src 'self' asset: http://asset.localhost blob: http://127.0.0.1:* ; connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:*",
      "assetProtocol": { "enable": true, "scope": ["**"] }
    }
  },
  "bundle": {
    "active": false,
    "targets": "all",
    "icon": ["icons/icon.ico"]
  }
}
```

`media-src` に `http://127.0.0.1:*` を含めるのが重要 (axum サーバへの `<video>` 接続を許可)。

### `src-tauri/capabilities/default.json`

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "dialog:default",
    "fs:default",
    "fs:allow-read-file",
    "fs:allow-stat",
    "shell:default",
    "shell:allow-execute",
    "shell:allow-spawn"
  ]
}
```

## コア: 大容量動画を `<video>` に配信する axum HTTP サーバ

### Rust 側 (`src-tauri/src/lib.rs` 抜粋)

```rust
use std::path::PathBuf;
use std::sync::Arc;

use axum::Router;
use tauri::Manager;
use tokio::sync::Mutex;
use tower_http::services::ServeFile;

#[derive(Default)]
pub struct AppState {
    current_port: Mutex<Option<u16>>,
}

#[tauri::command]
pub async fn start_http_server(
    state: tauri::State<'_, Arc<AppState>>,
    path: String,
) -> Result<String, String> {
    let pb = PathBuf::from(&path);
    if !pb.exists() {
        return Err(format!("file not found: {}", path));
    }

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();

    // ServeFile が Range ヘッダを解釈して 206 Partial Content を返す。
    // これが tauri#6375 の asset:// 経路より速い seek の鍵。
    let app = Router::new().fallback_service(ServeFile::new(pb));

    tokio::spawn(async move {
        if let Err(e) = axum::serve(listener, app).await {
            eprintln!("[axum] server error: {}", e);
        }
    });

    *state.current_port.lock().await = Some(port);
    Ok(format!("http://127.0.0.1:{}/", port))
}
```

`tauri::Builder::default().manage(Arc::new(AppState::default()))` で State を登録し、`invoke_handler(tauri::generate_handler![start_http_server])` で公開。

### フロント側 (React 19 + `@tauri-apps/api` 2.x)

```tsx
import { invoke } from '@tauri-apps/api/core';

async function playFile(absPath: string, videoEl: HTMLVideoElement) {
  const url = await invoke<string>('start_http_server', { path: absPath });
  videoEl.src = url;  // e.g. "http://127.0.0.1:64305/"
}
```

同一セッション中に別の動画に切り替える場合、現行実装ではサーバが leak する (`current_port` を上書き)。本実装では前のリスナを `shutdown_signal` で停止する設計を検討。

### L2a Phase 3 での拡張ポイント

- **サムネイルキャッシュ配信**: `~/.allaganeye/cache/<hash>/thumbs/*.webp` を同じ axum サーバでサブルート (`/thumbs/*`) にマウント
- **メタデータ JSON**: `metadata.json` を `/meta` で配信 (同一 origin なので CSP fetch OK)
- **並列サーバ**: IN 側プレイヤーと OUT 側プレイヤーで別ポートにしてバッファ競合を避けるか、単一サーバで運用するか要判断

## コア: CLI の stdout を行単位ストリーミング

### Rust 側

```rust
use std::process::Stdio;
use std::time::Instant;

use serde::Serialize;
use tauri::Emitter;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command as TokioCommand;

#[derive(Serialize, Clone)]
pub struct CliLine {
    pub stream: String,
    pub line: String,
    pub at: u64,
}

#[derive(Serialize)]
pub struct CliResult {
    pub code: Option<i32>,
    #[serde(rename = "durationMs")]
    pub duration_ms: u64,
}

#[tauri::command]
pub async fn run_cli(
    app: tauri::AppHandle,
    args: Vec<String>,
) -> Result<CliResult, String> {
    let start = Instant::now();
    let mut cmd = TokioCommand::new("allaganeye");
    cmd.args(&args);
    cmd.env("PYTHONUNBUFFERED", "1");  // 保険。現行 Tauri では無くても動作するが害はない
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    let stdout = child.stdout.take().ok_or("no stdout")?;
    let stderr = child.stderr.take().ok_or("no stderr")?;

    for (stream_name, pipe) in [("stdout", stdout), ("stderr", stderr)] {
        let app_ = app.clone();
        let start_ = start;
        let name_ = stream_name.to_string();
        tokio::spawn(async move {
            let mut reader = BufReader::new(pipe).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                let _ = app_.emit(
                    "cli:line",
                    CliLine {
                        stream: name_.clone(),
                        line,
                        at: start_.elapsed().as_millis() as u64,
                    },
                );
            }
        });
    }

    let status = child.wait().await.map_err(|e| e.to_string())?;
    Ok(CliResult {
        code: status.code(),
        duration_ms: start.elapsed().as_millis() as u64,
    })
}
```

注: 上記の `for` ループは型が異なる 2 つのパイプを渡すため、そのままは compile しない。元コード ([commit 履歴](https://github.com/Idios/kobutachan-allaganeye/pull/470)) では 2 回 `tokio::spawn` を書き下している形式が実働コード。本リファレンスの `for` 形式は可読性のため省略表現。

### フロント側

```tsx
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

type CliLine = { stream: string; line: string; at: number };

useEffect(() => {
  let unlisten: UnlistenFn | null = null;
  let cancelled = false;
  listen<CliLine>('cli:line', (ev) => {
    // ev.payload.line を UI に追記
  }).then((u) => {
    if (cancelled) u();   // mount/unmount race 対策
    else unlisten = u;
  });
  return () => {
    cancelled = true;
    if (unlisten) unlisten();
  };
}, []);

async function runDetect(videoPath: string) {
  const r = await invoke<{ code: number | null; durationMs: number }>('run_cli', {
    args: ['detect', videoPath],  // Phase 1 で split から detect へ分離済想定
  });
  return r;
}
```

**StrictMode を有効化する場合**、上記 `cancelled` フラグ付きのパターンが必須。外して良いなら main.tsx から `<React.StrictMode>` を外す方が簡単。

### L2a Phase 4 (export) での拡張ポイント

- ffmpeg は `run_cli` の代わりに直接 `TokioCommand::new("ffmpeg")` で起動
- stderr の `frame=N fps=M ...` パースで進捗抽出 → `app.emit("export:progress", ...)`
- キャンセル対応: `child.kill().await` を別コマンドとして公開
- 複数ファイルの並行起動は Tokio tasks で管理 (同時実行数は CPU コア数の 50% 目安)

## vite.config.ts (最小動作版)

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite 6 の UserConfigExport 型は async を受け付けないため、env 参照はインラインで。
declare const process: any;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: '127.0.0.1',
  },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    target: 'chrome120',
    minify: typeof process !== 'undefined' && process.env?.TAURI_ENV_DEBUG ? false : 'esbuild',
    sourcemap: typeof process !== 'undefined' && !!process.env?.TAURI_ENV_DEBUG,
  },
});
```

## ICO 生成 (PowerShell)

```powershell
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap 32, 32
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(200, 163, 92))  # aetherTheme gold
$g.Dispose()
$icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
$fs = [System.IO.File]::Create('src-tauri/icons/icon.ico')
$icon.Save($fs)
$fs.Close()
$icon.Dispose(); $bmp.Dispose()
```

本実装では handoff の公式ロゴ SVG / PNG を `@tauri-apps/cli`'s `tauri icon` コマンドで全解像度 ICO/ICNS/PNG 生成する。

## 関連

- 設計仕様: [`README.md`](README.md)
- 計測結果: [`feasibility.md`](feasibility.md)
- 元プロトタイプ: `.claude/worktrees/relaxed-mestorf-9807da/.claude/prototypes/tauri-phase0/` (worktree 削除で消滅予定)
- 採用確定コメント: [#450#issuecomment-4282416551](https://github.com/Idios/kobutachan-allaganeye/issues/450#issuecomment-4282416551)

作成: relaxed-mestorf-9807da (2026-04-21)
