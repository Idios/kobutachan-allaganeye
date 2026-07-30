# CLI 出力仕様 (Output Specification)

`allaganeye split` コマンドの CLI オプション組み合わせごとの**期待出力**を定義する。実装と docs の整合性を検証する基準として使用し、新規 CLI オプションを追加する PR は本マトリクスに行・列を追加することを必須とする (#405)。

関連: CLI 構文 (引数・オプション) は [`docs/cli-spec.md`](cli-spec.md) を参照。本ドキュメントは**出力側**の仕様に専念する。

## 適用範囲

- **対象コマンド**: `allaganeye split`
- **対象外コマンド**: `debug-brightness` (CSV 出力用途で `-v` / `-q` オプション自体を持たない。エラー表示のみ本仕様の 19b 準拠、ただし `-v` hint は表示しない #428)
- **対象外ストリーム**: stdout / stderr のメインストリーム。`logger.debug` 経由のログは本仕様に含まない (デフォルトで出力されず、開発者向け診断用)

## 排他オプション組み合わせ

同時指定すると **exit code 5** (ConfigValidationError) で終了する (#419):

| 排他ペア | 理由 |
| --- | --- |
| `-q` + `-v` | 「進捗出力抑制」と「詳細出力」は根本的に矛盾するため |
| `--gpu` + `--no-gpu` | GPU 強制と GPU 無効化は矛盾するため |

排他違反時は stderr に以下を出力し split 処理は開始しない:

```text
Error: --quiet and --verbose are mutually exclusive
```

## 直交フラグ (orthogonal flags)

以下のフラグは主軸 (`default` / `-v` / `-q` / `--dry-run`) と**直交**して重畳可能。マトリクスを簡潔に保つため各主軸列とは別軸として扱う:

| 直交フラグ | マトリクスへの影響 |
| --- | --- |
| `--gpu` / `--no-gpu` | 行 8 (Auto-selected GPU/CPU mode) のテキストが `Auto-selected ...` → `Forced GPU` / `Forced CPU` に変化。他行は影響なし。`--gpu` と `--no-gpu` は相互排他 (#419) |
| `--no-cache` | 行 7 (Cache hit params) と行 13 の `(cached)` サフィックスが常に非出力。他行は影響なし |
| `--no-audio` | 行 9 (検知パラメータ summary) の `audio=frozen` / `audio=off` トークンに反映。現状 AUDIO_FROZEN=True のため値に関わらず `frozen` 表示 (#384) |
| `--vtuber` | 行 9 の `vtuber=on` トークンに反映。`--vtuber` 採用 run の verbose 検知統計 (行 11) に `Timeline (vtuber)` / `V3:` 行が追加される (#895)。`--vtuber` が縮退 (V0 失敗等) した場合は timeline 統計行は出力されず通常 pass 1/2 統計に戻る。cache ヒット時 (行 7) は `vtuber_algo=N` トークンが `masked_fallback` 直後に挿入される (vtuber 影響 run のみ) |
| `-o`, `--sample-interval`, `--blackout-threshold`, etc. | 出力項目自体の有無には影響せず、値のみ変化 |

直交フラグ × 主軸組合せの全網羅 (例: `--gpu × 8 = 16 組合せ`) は **系統的検証チェックリスト (#409)** で補完する。

## マトリクス v2

凡例:

- **◯** = 出力する
- **×** = 出力しない
- **-** = 該当せず (split 処理に到達しないため)
- **❌** = exit 5 排他エラー (行そのものに到達しない)

| # | 出力項目 | 関連Issue | default | `-v` | `-q` | `--dry-run` | `-v --dry-run` | `-q --dry-run` | `-v -q` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 環境ヘッダ (allaganeye/ffmpeg/Python/OS) | - | × | ◯ | × | × | ◯ | × | ❌ |
| 2 | HW info (CPU/GPU/Memory/Disk) | [#377](https://github.com/Idios/kobutachan-allaganeye/issues/377) | × | ◯ | × | × | ◯ | × | ❌ |
| 3 | `Probing: <filename>` | - | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 4 | Metadata 詳細 (Duration / Resolution / FPS / Codec) | - | × | ◯ | × | × | ◯ | × | ❌ |
| 5 | `Auto-adjusted sample interval` | - | × | ◯ | × | × | ◯ | × | ❌ |
| 6 | Dry-run 通知 (`[dry-run] Detect only...` / `Dry run: skipping split`) | [#418](https://github.com/Idios/kobutachan-allaganeye/issues/418) | - | - | - | ◯ | ◯ | × | ❌ |
| 7 | Cache hit 検知パラメータ (`Cache hit: detection params from ...`) | [#380](https://github.com/Idios/kobutachan-allaganeye/issues/380) | × | ◯ (cache hit 時のみ) | × | × | ◯ | × | ❌ |
| 8 | Auto-selected / Forced GPU/CPU mode | - | × | ◯ | × | × | ◯ | × | ❌ |
| 9 | 検知パラメータ summary (`interval=..., threshold=..., workers=auto (N), audio=frozen, vtuber=off, masked=off`) | [#384](https://github.com/Idios/kobutachan-allaganeye/issues/384), [#389](https://github.com/Idios/kobutachan-allaganeye/issues/389) | × | ◯ | × | × | ◯ | × | ❌ |
| 10 | 進捗バー `Detecting` / `Refining` / `Scorebar` | [#368](https://github.com/Idios/kobutachan-allaganeye/issues/368), [#393](https://github.com/Idios/kobutachan-allaganeye/issues/393) | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 11 | 検知統計 (`Pass 1`, `Pass 2`, `Scorebar`, `Splitting` elapsed 含) | [#386](https://github.com/Idios/kobutachan-allaganeye/issues/386), [#387](https://github.com/Idios/kobutachan-allaganeye/issues/387) | × | ◯ | × | × | ◯ | × | ❌ |
| 12 | Filter drop 内訳 + unknown match 行 (`Filter: N candidates -> M matches` + `+ N unknown match (録画途中試合)`) | [#388](https://github.com/Idios/kobutachan-allaganeye/issues/388), [#433](https://github.com/Idios/kobutachan-allaganeye/issues/433) | × | ◯ | × | × | ◯ | × | ❌ |
| 13 | `Detected N match(es) ... (cached)` サフィックス含 | [#418](https://github.com/Idios/kobutachan-allaganeye/issues/418) (M) | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 14 | Match 一覧 (`[unknown]` / `[fl_match]` マーカー含) | [#382](https://github.com/Idios/kobutachan-allaganeye/issues/382) | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 15 | Gap 一覧 | - | × | ◯ | × | × | ◯ | × | ❌ |
| 16 | 進捗バー `Splitting` | - | ◯ | ◯ | × | - | - | - | ❌ |
| 17 | `Output: <dir>` / ファイル一覧 / `Metadata: <path>` | - | ◯ | ◯ | ◯ | - | - | - | ❌ |
| 18 | `Total: <duration>` | [#381](https://github.com/Idios/kobutachan-allaganeye/issues/381) | × | ◯ | × | × | ◯ | × | ❌ |
| 19a | エラー表示 (`-v`): `Error:` + `verbose_detail()` + full traceback | [#428](https://github.com/Idios/kobutachan-allaganeye/issues/428) | - | stderr | - | - | stderr | - | ❌ |
| 19b | エラー表示 (default): `Error:` + 1 行 hint | [#428](https://github.com/Idios/kobutachan-allaganeye/issues/428) | stderr | - | - | stderr | - | - | ❌ |
| 19c | エラー表示 (`-q`): `Error:` のみ | - | - | - | stderr | - | - | stderr | ❌ |

### マトリクスの読み方

- 行 6 (`Dry-run 通知`) で default / `-v` / `-q` 列が `-` なのは、これらの組合せでは `--dry-run` 自体が指定されていないため「通知する場面が存在しない」という意味
- 行 16-17 で `--dry-run` 系列が `-` なのは、dry-run は分割処理を skip するため split 出力・Splitting バーが発生しない
- 行 19 の `stderr` は「該当モードで該当フォーマットのエラーメッセージが stderr に出る」を意味し、エラーが発生した場合にのみ到達する条件行
- `-v -q` 列が全行 `❌` なのは、CLI 引数パース直後 (split 処理開始前) に ConfigValidationError で即 exit するため

## 強制 silent 契約 (`-q`)

`-q` モードでは `#418` 対応 (マトリクス行 3, 6, 7, 13 が全て `×`) により、以下のみが stdout に出力される:

```text
Output: <output_dir>
  <match_001.mp4>
  ...
Metadata: <metadata.json path>
```

エラーは stderr (19c 準拠)、その他 stdout メッセージは一切抑制される。

## エラー表示仕様 (19a / 19b / 19c / 19d)

詳細は [`docs/cli-spec.md` §「エラー表示 (#428 / #405 matrix v2)」](cli-spec.md) を参照。要約:

| モード | AllaganEyeError | 予期せぬ例外 |
| --- | --- | --- |
| `-v` (19a) | `Error: <msg>` + context 展開 + full traceback | full traceback (`__cause__` chain 含) |
| default (19b) | `Error: <msg>` + `(Run with -v / --verbose for full details)` | `Unexpected error: <exc>` + hint |
| `-q` (19c) | `Error: <msg>` のみ | `Unexpected error: <exc>` のみ |
| click-level option-parse error (19d) | `Error: No such option: <token>` + 改行 `Did you mean --<name>?` (stderr / `-v` / `-q` の影響なし、click level / 終了コード 2)。出力例の詳細は [`docs/cli-spec.md` §「click-level option-parse error」](cli-spec.md) を参照 | (該当なし — click level なので AllaganEyeError 系の例外経路を通らない) |

`debug-brightness` コマンドには `-v` / `-q` オプションが無いため、エラーは default 形式に準じるが、**存在しない `-v` オプションへ誘導しないよう hint を抑制**する (#428)。

## 関連 Issue 分類

### マージ済 (マトリクスと実装が一致)

- [#377](https://github.com/Idios/kobutachan-allaganeye/issues/377) (HW info)
- [#381](https://github.com/Idios/kobutachan-allaganeye/issues/381) (cached パスの Total 時間)
- [#382](https://github.com/Idios/kobutachan-allaganeye/issues/382) (Match type マーカー)
- [#383](https://github.com/Idios/kobutachan-allaganeye/issues/383) (ffmpeg version 冗長)
- [#384](https://github.com/Idios/kobutachan-allaganeye/issues/384) (audio=frozen)
- [#386](https://github.com/Idios/kobutachan-allaganeye/issues/386) (Scorebar elapsed)
- [#387](https://github.com/Idios/kobutachan-allaganeye/issues/387) (Splitting elapsed)
- [#388](https://github.com/Idios/kobutachan-allaganeye/issues/388) / [#433](https://github.com/Idios/kobutachan-allaganeye/issues/433) (Filter drop 内訳 + unknown match 行)
- [#389](https://github.com/Idios/kobutachan-allaganeye/issues/389) (workers=auto 解決値)
- [#368](https://github.com/Idios/kobutachan-allaganeye/issues/368) / [#393](https://github.com/Idios/kobutachan-allaganeye/issues/393) (3 フェーズ進捗バー)
- [#418](https://github.com/Idios/kobutachan-allaganeye/issues/418) (`-q` 厳密 silent: L/M/N 統合)
- [#419](https://github.com/Idios/kobutachan-allaganeye/issues/419) (`-q -v` / `--gpu --no-gpu` 排他)
- [#440](https://github.com/Idios/kobutachan-allaganeye/issues/440) / [#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) (click-level option-parse error hint, PR [#632](https://github.com/Idios/kobutachan-allaganeye/pull/632))

### Open (対応中・レビュー中)

- [#380](https://github.com/Idios/kobutachan-allaganeye/issues/380) (cache hit verbose params): PR [#416](https://github.com/Idios/kobutachan-allaganeye/pull/416)
- [#428](https://github.com/Idios/kobutachan-allaganeye/issues/428) (19a/19b エラー表示): PR [#429](https://github.com/Idios/kobutachan-allaganeye/pull/429)

## 保守ルール

### 新規 CLI オプション追加時

本マトリクスに以下を追加することを PR 必須チェック項目とする (`.github/pull_request_template.md` を参照):

1. 新規オプション単独列、または直交フラグ節への追記
2. 新規出力項目 (新規行) — 既存出力の拡張の場合は既存行に追記
3. 排他オプション関係がある場合は「排他オプション組み合わせ」節を更新

### マトリクスと実装の差分検出

- 実装変更 PR で出力書式を変える場合、本マトリクスの該当セルも同 PR で更新する
- 本マトリクスを基準に系統的検証チェックリスト (#409) を実施し、実機検証で差分を検出する
- 差分を発見した場合は `[bug]` issue として起票し `Refs #405` で本ドキュメントへ紐付ける

### 出力例の維持

本マトリクスは「出す / 出さない」を定義するのみで、具体的な出力例は以下の場所に分散する:

- verbose 全体像: [`docs/cli-spec.md` §「verbose (-v) 出力例」](cli-spec.md)
- verbose + cache hit: [`docs/cli-spec.md` §「verbose + キャッシュヒット時の出力」](cli-spec.md)
- verbose stats 内訳: [`docs/cli-spec.md` §「verbose stats の内訳行」](cli-spec.md)
- エラー表示: [`docs/cli-spec.md` §「エラー表示」](cli-spec.md)

出力例を変更する PR は本マトリクスのセルに変化が無くても、該当 docs 節の整合性を必ず目視確認する (再発防止: PR #343 系での「docs 出力例なし → 整合性検証が走らない」問題への対応)。

## export コマンド出力

関連: `export` コマンドの構文・オプション・wire protocol の詳細は [`docs/cli-spec.md` §「export コマンド」](cli-spec.md) を参照。

| モード | 生成ファイル | 備考 |
| --- | --- | --- |
| `export --codec copy` | `{idx:03}_{type}_{start}.mp4` (match ごと) | ストリームコピー MP4 (再エンコードなし)。`split` 出力と同じバイト内容を既存 `metadata.json` から生成 |
| `export --codec h264` | `{idx:03}_{type}_{start}.mp4` (match ごと) | 再エンコード MP4 (NVENC / QSV / AMF / libx264 fallback)。スロット数 = NVENC engine 数 (RTX 5090 → 3、RTX 4090 → 2 等)。iGPU / ソフトウェア encoder は 1 スロット |
| `export --json` | stdout: NDJSON ストリーム | 1 行 1 JSON イベント (progress / fallback / result / error / summary)。Tauri GUI subprocess が使用する wire protocol |
| `--include I,J,K` / `--exclude I,J,K` | metadata の `matches[].index` (**1 始まり**) と照合して match をフィルタ | `type_override="skip"` の match はこれらのフラグに関係なく常に除外。`post_match: true` の match も無条件除外 (`--include` 指定でも MP4 化されない、#805 Phase 1 契約) |

## minimap コマンド出力

関連: `minimap` コマンドの構文・オプション・exit code の詳細は [`docs/cli-spec.md` §「minimap コマンド」](cli-spec.md) を参照。

| モード | 生成ファイル | 備考 |
| --- | --- | --- |
| 提案モード (`--region` 未指定) | なし | stdout に `match N: --region X,Y,W,H (confidence C)` 形式で提案を表示する。エンコードなし・write-back なし。常に exit 4 |
| crop モード (`--region X,Y,W,H`) | `<out>/{idx:03}_{type}_{start}_minimap.mp4` (match ごと) | H.264 再エンコード MP4 (NVENC / QSV / AMF / libx264 fallback)。default 出力先は `<metadata dir>/minimap/` |
| crop モード (metadata write-back) | `metadata.json` 更新 | エンコード開始前に `minimap_regions` フィールドを atomic write-back する（エンコード失敗時も座標は保持される） |

### `--json` モード出力行 (crop モード)

`--json` フラグ指定時、stdout の各行は JSON オブジェクト 1 件（JSON Lines 形式）。GUI subprocess が parse する:

- `{"type":"result","match_index":N,"output_path":"...","duration_ms":N,"encoder_used":"h264_nvenc"|"libx264"|...}` — 1 match 成功
- `{"type":"error","match_index":N,"error_kind":"...","error_message":"...","error_hint":null|"..."}` — 1 match 失敗
- `{"type":"fallback","match_index":N,"fallback_from":"h264_nvenc","fallback_to":"libx264","message":"..."}` — GPU encoder 失敗 → libx264 fallback
- `{"type":"summary","success":N,"failure":N,"skipped":N,"cancelled":bool}` — 常に最終行

CAS 衝突 (`--expected-mtime` 不一致) は stdout への JSON 出力なしで **exit 6** のみ。GUI は exit 6 を受けて ConflictModal を表示する。

### `--json` モード出力行 (提案モード)

提案モードで `--json` を指定すると、stdout に match ごとに 1 行ずつ proposal を出力し常に exit 4 で終了する:

- `{"type":"proposal","match_index":N,"region":{"x":X,"y":Y,"w":W,"h":H}|null,"confidence":C,"scattered":bool}` — `region` は検出成功時は座標オブジェクト、失敗時は `null`。`confidence` は 0.0-1.0。`scattered` は検出結果が散らばり consensus が低いことを示す
