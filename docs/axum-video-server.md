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
| `TokenMap` 型エイリアス | `Arc<Mutex<HashMap<Uuid, PathBuf>>>` (`tokio::sync::Mutex`)。axum handler state と Tauri command の双方が共有 | `Arc::clone` で複製、内部 lock は短命 |
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
- 同一 path で複数回 `register_video` を呼んだ場合、毎回 distinct token が発行される。これは既存テスト `register_video_same_file_twice_yields_distinct_tokens` (`gui/src-tauri/src/lib.rs:3577-3590`) で保証される (Uuid v4 衝突確率は 122-bit entropy で実用上ゼロ)

### lifecycle

- 失効ルール: **GUI セッション中は保持、明示失効 API 無し** (現状実装)
- 不備として認識: `register_video_sync` で insert した token は明示的な remove 経路が無く、process 終了まで `VIDEO_SERVER` の `tokens: HashMap<Uuid, PathBuf>` (`gui/src-tauri/src/lib.rs:35` + `:44`) に残る。triage 課題 (failure to invalidate API; long-running session で memory growth、別 issue で改善検討)
- frontend → backend 受け渡し: `register_video` (`gui/src-tauri/src/lib.rs:573-576`) の戻り値 `RegisteredVideo` struct (`url: String`, `token: String`、`gui/src-tauri/src/lib.rs:67-70`) を frontend が受け、`<video src={url}>` に組み立てる (`url` は `format!("http://127.0.0.1:{}/video/{}", port, token)` で生成)

### tokens HashMap 構造

- `tokens: HashMap<Uuid, PathBuf>` で token → 解決 path をマップ
- `TokenMap` 型エイリアス: `Arc<Mutex<HashMap<Uuid, PathBuf>>>` (`gui/src-tauri/src/lib.rs:35`、`tokio::sync::Mutex`)
- lookup は `serve_video` route handler 内で実施 (`gui/src-tauri/src/lib.rs:852-879`)
- axum handler state と Tauri command の双方が `Arc::clone` で同じ map を共有

## §4 Range request 仕様

### 準拠

- RFC 7233 Range Requests に準拠
- 実装: axum 既定ではなく **`tower_http::services::ServeFile` に委譲** (`use tower_http::services::ServeFile;` `gui/src-tauri/src/lib.rs:22`)

### chunk size / partial content

- HTML5 `<video>` 要素の seek パターン: 任意 byte range を要求
- `ServeFile` が `Range` / `Content-Type` sniffing / `If-Range` を native ハンドル (`serve_video` 内コメント `// ServeFile handles Range, Content-Type sniffing, and If-Range. Forward the original request so the Range header survives.` `gui/src-tauri/src/lib.rs:869-870`)
- 実装 (`gui/src-tauri/src/lib.rs:871-875`) で original request をそのまま forward し、`Range` header を ServeFile に届ける:

  ```rust
  let mut svc = ServeFile::new(p);
  match svc.try_call(request).await {
      Ok(resp) => resp.into_response(),
      Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "serve failed").into_response(),
  }
  ```

- chunk size の上限制限は無し (preview 用途 — single 試合 preview ≤ ~30 min、~4K まで — では memory 圧迫リスクは実害ない領域)

### EOF 扱い / status code

- HTTP 206 (partial content) / 416 (Range Not Satisfiable) は `ServeFile` 内部で生成
- 範囲が file 終端を超える場合の応答 (HTTP 416 / file 末尾までの partial content) は `ServeFile` 既定挙動に従う

## §5 Path allowlist 機構

### allowlist 構造

- `register_video` Tauri command (`gui/src-tauri/src/lib.rs:562-577`) で登録された path のみが serve 対象となる
- 内部構造: `tokens: HashMap<Uuid, PathBuf>` (`gui/src-tauri/src/lib.rs:35` + `:44`、`TokenMap = Arc<Mutex<HashMap<Uuid, PathBuf>>>`)。token (Uuid v4) → canonical な `PathBuf` の lookup table
- 未登録 path への直接アクセス経路は無い: `serve_video` route handler (`gui/src-tauri/src/lib.rs:852-879`) は受け取った URL path の `{token}` を `Uuid::parse_str` で validate し、`tokens` map から `PathBuf` を取得する。token が map に存在しなければ 404 を返し、URL path 自体は file system path として解決されない

### canonical path 検証

- `register_video` 内で `validate_video_path(&file_path)?` (`gui/src-tauri/src/lib.rs:564`) を呼び出す。`validate_video_path` ヘルパ (`gui/src-tauri/src/lib.rs:775-800`) は次の 3 段検証を実施する:
  1. `path.exists()` で存在確認 (`io.file_not_found` AppError で reject)
  2. `fs::metadata(path)?.is_file()` で regular file 判定 (`validation.not_a_file` AppError で reject)
  3. `fs::canonicalize(path)?` で canonical 化 (失敗時は `io.read_failed` AppError で reject)
- canonical 化された絶対 path のみが `tokens` map に insert される (`register_video_sync`、`gui/src-tauri/src/lib.rs:805-809`)
- 既存 Rust テスト:
  - `register_video_rejects_missing_file` (`gui/src-tauri/src/lib.rs:3517-3526`): 存在しない path を reject
  - `register_video_rejects_directory` (`gui/src-tauri/src/lib.rs:3532-3540`): directory を reject
  - `validate_video_path_accepts_regular_file` (`gui/src-tauri/src/lib.rs:3545-3552`): regular file を canonical 化された絶対 path に変換

### 脅威モデル — Path traversal

- 攻撃シナリオ: 外部 origin (もしくは loopback 経由でアクセスできる別プロセス) が `/video/{token}/../../etc/passwd` のような traversal を試行する
- 防御: `serve_video` は URL path から token のみを抽出し、`tokens` map から取得する `PathBuf` を `ServeFile::new(p)` に渡す。token から得られる `PathBuf` は登録時に `validate_video_path` で canonical 化された絶対 path で固定されるため、URL path に traversal 文字が含まれても `tokens` lookup の結果は影響を受けない
- 補強: axum の route definition は `/video/{token}` 単一 segment にのみマッチする (`build_router`、`gui/src-tauri/src/lib.rs:846-850`)。複数 segment や `..` を含む URL は route match 自体に失敗して 404 になる

### 脅威モデル — Token leak

- GUI セッション内保持 + 外部送信経路無しが前提
- Uuid v4 の予測困難性: 122-bit entropy により総当たり推測は実用上不可能 (1 秒間に 10^9 推測でも全空間走破に 10^20 年規模)
- frontend が `<video src={url}>` で組み立てた URL は WebView2 内でのみ参照され、外部送信経路は無い (Tauri WebView2 sandbox 内部での `file://` 代替経路)

## §6 Bind + port

### Bind address

- **`127.0.0.1` 必須** — 外部 NIC への bind は禁止
- 実装: `tokio::net::TcpListener::bind("127.0.0.1:0").await` (`gui/src-tauri/src/lib.rs:820`) で IPv4 loopback のみ
- IPv6 loopback `::1` の扱い: 現状実装は IPv4 loopback only (`127.0.0.1` literal で bind しているため `::1` には listen していない)。dual stack 非対応

### Port 動的割当

- フィールド: `VideoServer` struct の `port: Option<u16>` (`gui/src-tauri/src/lib.rs:42-45`、初期値 `None`)
- 起動時に OS から空き port を取得: `TcpListener::bind("127.0.0.1:0")` の `0` 指定で OS に動的割当を委譲し、`listener.local_addr()?.port()` で確定 port を読み取る (`gui/src-tauri/src/lib.rs:820-828`)
- 単一インスタンス起動順序: `VIDEO_SERVER` static (`OnceLock<Mutex<VideoServer>>`、`gui/src-tauri/src/lib.rs:56-60`) を経由し、初回 `ensure_server_started().await` 呼び出し時に lazy init される (`guard.port` が `None` の場合のみ bind + spawn を実行、確保済みなら同じ port を即返却して idempotent)
- port 割当後は `guard.port = Some(addr.port())` で永続化され、プロセス内では同一 port が再利用される (`gui/src-tauri/src/lib.rs:839`)

### 脅威モデル — 外部 IF 経由攻撃

- `127.0.0.1` bind により外部 NIC からは到達不能 (LAN 上の他端末や WAN からのアクセス経路無し)
- 同一マシン内の他 user / 他プロセスからは loopback 経由でアクセス可能だが、token を知らなければ実害なし: Uuid v4 の 122-bit entropy + GUI セッション内保持 + 外部送信経路無しにより、別プロセスが有効な token を入手する経路は存在しない
- 補足: Windows 上では loopback 通信に対する firewall 制約が緩いが、token 不知では `serve_video` が 404 を返すのみで file system 走査経路は無い (前述の §5 path allowlist 機構による)

## §7 Async lifecycle

### 背景 task の起動

- `axum::serve(listener, app)` は `tokio::spawn` で背景 task として実行される (`gui/src-tauri/src/lib.rs:833-837`):

  ```rust
  tokio::spawn(async move {
      if let Err(e) = axum::serve(listener, app).await {
          eprintln!("video server error: {}", e);
      }
  });
  ```

- 起動失敗時は `eprintln!` で stderr に記録のみ (Tauri 側 ErrorModal には伝搬しない、現状実装の制約)
- Tauri main runtime と同じ tokio runtime を共有するため、別 runtime の bootstrap は不要

### GUI 終了時の graceful shutdown

- 現状実装: tauri ウィンドウ close → process 終了 → spawn された tokio task は OS による強制終了
- 明示的な shutdown signal 経路 (`tauri::Manager` の `RunEvent::Exit` 等) は **無し** (現状実装の制約。`gui/src-tauri/src/` 配下に `RunEvent::Exit` 使用箇所なし)
- HTTP `<video>` stream 中の TCP connection は process 終了で OS が回収する。token map (in-memory `HashMap<Uuid, PathBuf>`) も同時に解放される
- 改善余地: `RunEvent::Exit` で server に shutdown signal を送る経路の整備 (別 issue で改善検討)

### 単一インスタンス前提

- `VIDEO_SERVER: OnceLock<Mutex<VideoServer>>` (`gui/src-tauri/src/lib.rs:56`) により process 内で 1 つだけ
- `video_server() -> &'static Mutex<VideoServer>` accessor (`gui/src-tauri/src/lib.rs:58-60`) が `OnceLock::get_or_init(|| Mutex::new(VideoServer::new()))` で初期化を冪等化
- 複数 `register_video` 呼び出しは同一 server に token を追加するのみで、新たな bind / spawn は発生しない (`ensure_server_started` の idempotent 性、§2 起動シーケンス手順 2 参照)

## §8 想定負荷見積

### 想定 scenario

- preview 画面で 2:50:28 録画 (h264 1080p / ~30 Mbps) を loopback 経由で seek + frame 送信
- 同時 2 stream の seek を想定 (preview 微細タイムライン [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) で導入予定)

### 見積もり値

| 項目 | 想定値 | 計測有無 |
| --- | --- | --- |
| 1 stream bandwidth (peak) | ~30 Mbps | 推測値 (h264 1080p 60fps の典型 bitrate) |
| 同時 2 stream bandwidth | ~60 Mbps | 推測値 |
| loopback 帯域 | ~10 Gbps (Windows 標準) | OS 仕様 |
| 余裕度 | 約 170 倍 | 実用上 bottleneck にならない |

### 注記

- 上記は **推測値** (実機計測未実施)。`v0.3.0` で再計測予定
- 計測手段: Windows リソースモニタ + `<video>` element の `currentTime` 移動回数 / 秒
- 「TBD」「後日計測」だけの placeholder は禁止 (本 spec の方針)

## §9 References

### Cross-references

- [`docs/system-architecture.md` §2.4 GUI 内の video 配信](./system-architecture.md#24-gui-内の-video-配信-subprocess-ではない) — 配布物視点での位置付け
- [`docs/ui-architecture.md` §5 preview](./ui-architecture.md#5-各画面の-phase-state) — preview 画面 UI 状態機械

### 関連 PR

- [#540](https://github.com/Idios/kobutachan-allaganeye/pull/540) — 実装本体 (landed)
- [#623](https://github.com/Idios/kobutachan-allaganeye/pull/623) — Phase 2.5 detecting/complete 本物化 (preview screen 到達経路の前段)

### 関連 issue

- [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) — Phase 3 preview 本物化 (親 issue)
- [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) — PreviewScreen state mutation flow (closed)
- [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) — preview 微細タイムライン (open / 本 spec の Phase 3 拡張余地)

### 既存テスト (回帰検出)

- `gui/src-tauri/src/lib.rs:3517` — `register_video_rejects_missing_file`
- `gui/src-tauri/src/lib.rs:3532` — `register_video_rejects_directory`
- `gui/src-tauri/src/lib.rs:3545` — `validate_video_path_accepts_regular_file`
- `gui/src-tauri/src/lib.rs:3557` — `register_video_returns_distinct_tokens_for_two_registrations`
- `gui/src-tauri/src/lib.rs:3577` — `register_video_same_file_twice_yields_distinct_tokens`
