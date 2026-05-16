# Windows process tree orphan audit (#743)

L2a GUI (`gui/src-tauri/src/lib.rs`) は外部プロセスを 6 箇所で spawn する。本 audit はそれぞれの Windows process tree 振る舞いと孤児化リスクを整理し、#756 fix (Job Object 化) を `start_detect` のみに適用した理由を明示する。元 audit task は #743、修正実装は #756。

## §1 spawn site 一覧

| # | spawn site | spawn する process | 子孫プロセス | orphan risk | PROCESS_TRACKER 登録 | Job Object 適用 (#756) | 備考 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `probe_video_with` (`lib.rs:~638`) | ffprobe (単発) | なし | なし | no (`cmd.output()`、spawn+wait 一体) | no | 短命 metadata query。`output().await` ブロックで親と寿命同期 |
| 2 | `ensure_thumbnail_exists` (`lib.rs:~1236`) | ffmpeg (単発) | なし | なし | no (`cmd.output()`) | no | サムネ生成、数百 ms 以内 |
| 3 | `extract_brightness_window_impl` (`lib.rs:~1348`) | ffmpeg (単発) | なし | なし | no (`cmd.output()`) | no | preview brightness 抽出、~1s |
| 4 | `run_ffmpeg_export_attempt` (`lib.rs:~2019`) | ffmpeg (単発) | なし | あり (中断時) | yes | no | export 1 本ずつ、`TrackedChild::no_job(child)` |
| 5 | **`start_detect` (`lib.rs:~2651`)** | Python `allaganeye detect` | **ffmpeg N 個 (GPU detector で 16-32、`gpu_detector.py`)** | **あり (#756 root cause)** | yes | **yes** | 本 PR の対応対象。`TrackedChild { child, job: Some(_) }` |
| 6 | `open_folder_in_explorer` (`lib.rs:~1859`) | explorer.exe | (Windows shell process) | N/A (意図的 detach) | **no** | no | UI、本 app 終了後も残るべき |

## §2 #756 fix の挙動 (start_detect だけ Job 化)

### 2.1 なぜ start_detect だけか

`start_detect` は Python CLI (`allaganeye detect`) を spawn し、Python 側は GPU detection が有効な場合に内部で N 個 (16-32) の ffmpeg プロセスを並列 spawn する (`allaganeye/video/gpu_detector.py`)。Windows の `TerminateProcess` (= `tokio::process::Child::kill().await`) は **直接の子プロセスのみ kill** するため、Python だけが死んで ffmpeg 子孫は親なしの孤児として残留する (#756 root cause)。

他 5 spawn site は:

- **#1-#4 (ffmpeg / ffprobe 単発)**: 子孫を spawn しない。`Child::kill` で十分。
- **#6 (explorer.exe)**: 「UI が GUI 終了後も残る」のが意図 (Idios の方針: 「展開 = インストール、削除 = アンインストール」)。Job 化すると Job Close で explorer も道連れに kill されてしまうため絶対に対象外。

### 2.2 Job Object の効果

`gui/src-tauri/src/process_util/job_object.rs` に [`ProcessJob`](../gui/src-tauri/src/process_util/job_object.rs) を実装。動作は以下:

1. `CreateJobObjectW(None, None)` で名前なし Job を作成
2. `SetInformationJobObject` で `JOBOBJECT_EXTENDED_LIMIT_INFORMATION.BasicLimitInformation.LimitFlags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` を設定
3. `start_detect` の `cmd.spawn()` 直後に `AssignProcessToJobObject(job_handle, python_handle)` で Python CLI process を Job に追加
4. `TrackedChild { child, job: Some(_) }` に Job handle を保持
5. PROCESS_TRACKER 内で TrackedChild が生きている間 Job は維持される
6. `kill_tracked_processes` が PROCESS_TRACKER を drain すると `TrackedChild` が drop され、`ProcessJob` も drop される
7. `ProcessJob::drop` が `CloseHandle(job_handle)` を呼び、Windows kernel が `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` を発火して **assigned process と全 descendant を一括 kill**

Python が spawn する ffmpeg は親プロセス (Python) の Job membership を継承するため、Python が Job に入っていれば ffmpeg も自動的に Job に入る (Windows カーネルの仕様、`JOB_OBJECT_LIMIT_BREAKAWAY_OK` を明示的に設定しない限り)。

### 2.3 happy path (cancellation なし) での挙動

検知が正常完了するケースでは:

1. Python CLI が exit 0 で終わる → child の `wait().await` が `Ok(ExitStatus::success())` を返す
2. `untrack_child(id).await` が `TrackedChild` から `child` を抽出して返却、同時に **`TrackedChild` (= Job 保持側) は drop**
3. しかし Job 内のプロセス (Python) はすでに自然死しているため、Job の `KILL_ON_JOB_CLOSE` 発火は **no-op** (Job 内に kill 対象がいない)
4. `CloseHandle(job_handle)` は kernel handle を release するだけ

つまり Job Object 化による happy path への性能影響はゼロ。

## §3 親 app crash 時の挙動

`on_window_event(CloseRequested)` handler を通らずに親 Tauri app が異常終了するケース (panic / OS-side SIGKILL / electron-like crash):

- Windows kernel は process termination 時に **そのプロセスが保持していた全 handle を release** する
- `ProcessJob` の Job handle も release され、`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` が発火する
- 結果: Tauri app が crash しても Python CLI + ffmpeg descendants は kernel 側で確実に reap される

これは Job Object pattern が `taskkill /T /F /PID` 経由のソリューションより優れている主要因。`taskkill` は親 app が機能していないと呼ばれず、crash 時の cleanup を保証できない。

## §4 検証手順 (実機テスト)

以下は GUI build + 実機実行で確認すべき項目。CI は jsdom + cargo unit test なので React side wiring (`flow N` integration test) と Job API smoke test (`process_job_assign_real_child_drop_kills_it`) しか pin できない。

1. `cd gui && npm run tauri dev` で開発ビルドを起動
2. detecting 画面に到達 (動画 drop → [OK — 検知開始])
3. Task Manager (詳細タブ) を開き、`python.exe` + `ffmpeg.exe` プロセスが N 個立ち上がるのを確認
4. GUI のタイトルバー `×` を押下
5. ConfirmExitModal で [終了] を押下
6. Task Manager で:
   - `python.exe` (allaganeye CLI) が **0 個** であること
   - `ffmpeg.exe` (descendant) が **0 個** であること
   - explorer.exe が引き続き稼働していること (open_folder_in_explorer で起動した shell が残る)

### 4.1 障害シナリオ

以下も検証推奨:

- 検知中に Tauri app が panic (例: `dev_force_panic` Tauri command) → Task Manager で全プロセス消滅を確認
- 検知中に CPU/Memory が極端に逼迫 → Job handle drop が問題なく走るか

## §5 未対応 (deferred / out-of-scope)

| 項目 | 状態 | 理由 |
| --- | --- | --- |
| `run_ffmpeg_export_attempt` の Job 化 | 不要 | ffmpeg 1 本のみ、子孫なし。`Child::kill` で十分 |
| `taskkill /T /F /PID` fallback | 不要 | Job Object pattern が crash 時も含めてより確実 |
| `JOB_OBJECT_LIMIT_BREAKAWAY_OK` を必要とする legitimate child の救済 | 該当なし | 現状 Python も ffmpeg も BREAKAWAY を要求しない |
| Linux / macOS の同等対応 (`setpgid` + `kill -SIGTERM -<pgid>`) | 後回し | プロジェクト方針: 「対応プラットフォーム: Windows のみ」 |

将来的に新規 ffmpeg spawn site を追加する場合は、子孫を spawn するか? を必ず本 audit と同じ表形式で確認し、子孫を持つなら Job Object を適用する。

## §6 関連

- 実装: `gui/src-tauri/src/process_util/job_object.rs` + `gui/src-tauri/src/lib.rs` (`TrackedChild` / `track_child` / `start_detect`)
- 整合性 test: `gui/src-tauri/src/process_util/mod.rs` の `lib_rs_applies_apply_no_window_at_all_spawn_sites` と並ぶ「spawn site policy」回帰検査
- integration test: `gui/src/__tests__/flow.integration.test.tsx` の `flow N: detecting cancel triggers kill_tracked_processes (#756)`
- 元 issue: #743 (audit task)、#756 (orphan bug fix)
- 関連: #523 (CloseRequested → ConfirmExitModal 初期実装、direct child のみ kill)、#466 (export ffmpeg track_child)、memory `feedback_taskstop_child_process_leak.md`
