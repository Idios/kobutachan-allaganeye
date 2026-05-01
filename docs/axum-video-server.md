# axum 局所 HTTP 動画サーバ仕様

> **Status**: v0.2.0 リリースゲート blocking spec
> **対象実装**: `gui/src-tauri/src/lib.rs:42-879` (VideoServer 系、[#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) / PR [#540](https://github.com/Idios/kobutachan-allaganeye/pull/540) で landed)
> **本 doc の用途**: 後続 PR ([#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) / [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) 等) のレビュー判断基準。preview 関連変更時は本 spec との適合確認を行う

## §1 Overview

### 目的

`allaganeye-gui.exe` (Tauri bundle) の preview 画面で、ローカルにある動画ファイルを HTML `<video>` 要素から frame seek 可能な形で再生するため、Rust 側に axum ベースの局所 HTTP video server を起動する。

`<video>` 要素は `file://` 直接参照では Tauri の WebView2 セキュリティポリシーと衝突するうえ、ブラウザ標準の HTTP Range request に依存した seekable streaming も成立しない。Rust 側で `127.0.0.1` にバインドした最小サーバを立て、unguessable な UUID token を URL に埋め込むことで、frontend からは通常の HTTP URL として扱いつつパス漏洩を回避する。

### Scope

- Range request 仕様 / token 機構 / path allowlist / bind / async lifecycle / 想定負荷見積 を確定する
- 後続 preview 関連 PR (例: thumbnail strip、preview 高速化、再エンコード preview) のレビュー時、本 spec との適合確認を行う
- 本 doc は **実装のリファレンス** であり、実装変更を強制するものではない (実装側を変更したら本 doc を同期する)

### 既存実装位置

| 要素 | line |
| --- | --- |
| `TokenMap` 型エイリアス (`Arc<Mutex<HashMap<Uuid, PathBuf>>>`) | `gui/src-tauri/src/lib.rs:35` |
| `VideoServer` struct (フィールド: `port: Option<u16>`, `tokens: TokenMap`) | `gui/src-tauri/src/lib.rs:42-45` |
| `VIDEO_SERVER` static (`OnceLock<Mutex<VideoServer>>`) + `video_server()` accessor | `gui/src-tauri/src/lib.rs:56-60` |
| `RegisteredVideo` struct (`url: String`, `token: String`、Serialize) | `gui/src-tauri/src/lib.rs:67-70` |
| `register_video` Tauri command | `gui/src-tauri/src/lib.rs:562-577` |
| `register_video_sync` testable helper (UUID 発行 + tokens insert の pure 関数) | `gui/src-tauri/src/lib.rs:805-809` |
| `ensure_server_started` (port 確保 + axum 背景 spawn、idempotent) | `gui/src-tauri/src/lib.rs:814-841` |
| `build_router` (axum `Router::new()` 構築) | `gui/src-tauri/src/lib.rs:846-850` |
| `serve_video` route handler (`tower_http::services::ServeFile` 経由) | `gui/src-tauri/src/lib.rs:852-879` |

### 関連

- 実装 PR: [#540](https://github.com/Idios/kobutachan-allaganeye/pull/540) (initial landed)
- 親 issue: [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) (preview 用 video server 設計)
- v0.2.0 ゲート issue: [#618](https://github.com/Idios/kobutachan-allaganeye/issues/618) (本 spec doc 整備)
- 後続 issue (preview 関連): [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) / [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645)
- Tauri command 全体一覧: [`docs/tauri-commands.md`](tauri-commands.md) (`register_video` は #12)
- GUI 全体構成: [`docs/system-architecture.md`](system-architecture.md)

## §2 Architecture

### コンポーネント構成

| コンポーネント | 役割 | スレッド・所有 |
| --- | --- | --- |
| `VideoServer` struct | port (`Option<u16>`) と `TokenMap` を保持する process-global state | `OnceLock<Mutex<VideoServer>>` (`tokio::sync::Mutex` で多 Tauri command 間 await 可能) |
| `VIDEO_SERVER` static | `OnceLock<Mutex<VideoServer>>` 一度だけ初期化される singleton | プロセス全体で 1 instance |
| `TokenMap` | `Arc<Mutex<HashMap<Uuid, PathBuf>>>` (`tokio::sync::Mutex`)。axum handler state と Tauri command の双方が共有 | `Arc::clone` で複製、内部 lock は短命 |
| `register_video` Tauri command | frontend からの登録要求を受け、`validate_video_path` → port 確保 → token 発行 → URL 返却 | Tauri runtime の async runtime |
| `register_video_sync` helper | `Uuid::new_v4()` 発行 + `tokens` insert のみを行う pure 関数。axum を起動せず単体テスト可能 | テスト時はメイン thread |
| `ensure_server_started` | port 未確保なら `127.0.0.1:0` で `TcpListener` を bind し `tokio::spawn` で axum を背景実行。確保済みならそのまま port を返す idempotent | 初回呼び出しで `tokio::spawn` 1 回、以降 no-op |
| `build_router` | `axum::Router::new().route("/video/{token}", get(serve_video)).with_state(tokens)` を組む | builder 関数 (副作用なし) |
| `serve_video` route handler | `Uuid::parse_str` で token を validate → tokens map から `PathBuf` を取得 → `tower_http::services::ServeFile::new(path)` で Range / Content-Type / If-Range を native handle | axum runtime のリクエスト毎 task |

### 起動シーケンス

初回 `register_video` 呼び出し時の制御フロー (2 回目以降は手順 2-a〜2-d を skip):

1. **入力 validation**: `register_video(path)` が `validate_video_path(&file_path)?` を呼び、canonical path 化 + 不正パス reject (`io.file_not_found` / `validation.not_a_file` / `io.permission_denied`) を行う。
2. **`ensure_server_started().await?` 呼び出し**: VIDEO_SERVER guard を取得し、`port` が `None` の場合のみ以下 a-d を実行 (確保済みなら同じ port を即返却して idempotent)。
   1. `tokio::net::TcpListener::bind("127.0.0.1:0").await` で OS に動的 port を割り当てさせる。失敗時は `subprocess.spawn_failed` `AppError` を返す。
   2. `listener.local_addr()?.port()` で確定 port を取得する。
   3. `guard.tokens.clone()` (`Arc::clone`) で TokenMap の参照を複製し、`build_router(tokens)` で axum `Router` を組む。
   4. `tokio::spawn(async move { axum::serve(listener, app).await })` で axum サーバを背景 task として起動 (Tauri main runtime と同じ tokio runtime を共有)。エラーは `eprintln!` でログのみ。
   5. `guard.port = Some(addr.port())` で port を VIDEO_SERVER state に永続化し、return する。
3. **token 発行 (lock guard 内)**: `register_video` 側で VIDEO_SERVER guard と `tokens.lock().await` の 2 段 lock を取得し、`register_video_sync(&canonical, &mut tokens)` で `Uuid::new_v4()` token を生成 + HashMap に `(token, canonical_path)` を insert する。
4. **URL 組立**: `RegisteredVideo { url: format!("http://127.0.0.1:{}/video/{}", port, token), token: token.to_string() }` を返却。frontend はこの `url` を `<video>` 要素の `src` に設定するだけで、HTTP Range seekable な再生が成立する。

サーバ shutdown は明示的には行わない: `tokio::spawn` した background task はプロセス終了時に WebView2 / Tauri runtime と同時に解放される。tokens map もプロセス内 in-memory のみで永続化されない (再起動でリセット)。

## §3 Token フォーマット + lifecycle

### Token 形式

- 型: `Uuid` (v4)
- 発行ルール: `register_video_sync` 呼び出しごとに `Uuid::new_v4()` で生成 (`gui/src-tauri/src/lib.rs:805-809`)
- 同一 path で複数回 `register_video` を呼んだ場合、毎回 distinct token が発行される。これは既存テスト `register_video_same_file_twice_yields_distinct_tokens` (`gui/src-tauri/src/lib.rs:3577-3590`) で保証される

### lifecycle

- 失効ルール: **GUI セッション中は保持、明示失効 API 無し** (現状実装)
- 不備として認識: `register_video_sync` で insert した token は明示的な remove 経路が無く、process 終了まで `VIDEO_SERVER` の `tokens: HashMap<Uuid, PathBuf>` (`gui/src-tauri/src/lib.rs:35` + `:44`) に残る。長時間実行時の memory 増加リスクあり (Task 8 で軽微 / 重大を判定)
- frontend → backend 受け渡し: `register_video` (`gui/src-tauri/src/lib.rs:573-576`) の戻り値 `RegisteredVideo` struct (`url: String`, `token: String`、`gui/src-tauri/src/lib.rs:67-70`) を frontend が受け、`<video src={url}>` に組み立てる (`url` は `format!("http://127.0.0.1:{}/video/{}", port, token)` で生成)

### tokens HashMap 構造

- `tokens: HashMap<Uuid, PathBuf>` で token → 解決 path をマップ
- 型エイリアス: `type TokenMap = Arc<Mutex<HashMap<Uuid, PathBuf>>>` (`gui/src-tauri/src/lib.rs:35`、`tokio::sync::Mutex`)
- lookup は `serve_video` route handler 内で実施 (`gui/src-tauri/src/lib.rs:852-879`)
- axum handler state と Tauri command の双方が `Arc::clone` で同じ map を共有

## §4 Range request 仕様

### 準拠

- RFC 7233 Range Requests に準拠
- 実装: axum 既定ではなく **`tower_http::services::ServeFile` に委譲** (`use tower_http::services::ServeFile;` `gui/src-tauri/src/lib.rs:22`)

### chunk size / partial content

- HTML5 `<video>` 要素の seek パターン: 任意 byte range を要求
- `ServeFile` が `Range` / `Content-Type` sniffing / `If-Range` を native ハンドル (`serve_video` 内コメント `// ServeFile handles Range, Content-Type sniffing, and If-Range. Forward the original request so the Range header survives.` `gui/src-tauri/src/lib.rs:869-870`)
- 実装は `let mut svc = ServeFile::new(p); match svc.try_call(request).await { Ok(resp) => resp.into_response(), Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "serve failed").into_response(), }` (`gui/src-tauri/src/lib.rs:871-875`) で original request をそのまま forward し、`Range` header を ServeFile に届ける
- chunk size の上限制限は無し (memory 圧迫リスクは preview 用途では実害ない領域)

### EOF 扱い / status code

- HTTP 206 (partial content) / 416 (Range Not Satisfiable) は `ServeFile` 内部で生成
- 範囲が file 終端を超える場合の応答 (HTTP 416 / file 末尾までの partial content) は `ServeFile` 既定挙動に従う
