# CLI 出力仕様 (Output Specification)

`allaganeye split` / `allaganeye detect` コマンドの CLI オプション組み合わせごとの**期待出力**を定義する。実装と docs の整合性を検証する基準として使用し、新規 CLI オプションを追加する PR は本マトリクスに行・列を追加することを必須とする (#405)。

関連: CLI 構文 (引数・オプション) は [`docs/cli-spec.md`](cli-spec.md) を参照。本ドキュメントは**出力側**の仕様に専念する。

## 適用範囲

- **対象コマンド**: `allaganeye split` (検知+分割 / `--from-metadata` 分割のみ の 2 経路) / `allaganeye detect` (#463 で分離。detect は split の検知フェーズと同じ進捗・verbose 出力契約に従う)
- **対象外コマンド**: `debug-brightness` (CSV 出力用途で `-v` / `-q` オプション自体を持たない。エラー表示のみ本仕様の 19b 準拠、ただし `-v` hint は表示しない #428)
- **対象外ストリーム**: stdout / stderr のメインストリーム。`logger.debug` 経由のログは本仕様に含まない (デフォルトで出力されず、開発者向け診断用)

### detect コマンドの適用境界

マトリクスは元々 `split` を対象に作成されたため、`detect` を対象に加えるにあたり **全 19 行を `allaganeye/commands/detect.py` の実行経路に対して突合した** (#862)。以下の 5 点を除き、残る行は split と同一のヘルパ (`_print_environment_header` / `_display_cache_hit_params` / `_resolve_gpu_mode_with_probe` / `_run_detection` / `_print_detection_stats` / `_display_results` / `_display_gaps` / `_emit_total_time`) を detect も呼ぶため、**表の値がそのまま detect にも適用される**。

detect に該当しない行 (この 4 点で網羅):

- **行 6 (`Dry-run 通知`)**: `detect` に `--dry-run` オプションは存在しない (`allaganeye/cli.py` 参照)。`--dry-run` 系列の列 (3 列) は detect では意味を持たない
- **行 11 のうち `Splitting` elapsed**: `Splitting: N matches, Xs` (2 space indent 付き) は `_emit_splitting_elapsed` (`allaganeye/commands/split_matches.py` で定義) が出力し、その呼び出し元は `run_split` (cache hit / cache miss の 2 経路) と `run_split_from_metadata` (`split --from-metadata`) の計 3 箇所、すなわち**分割フェーズを実行する split 側の経路のみ**。detect (`allaganeye/commands/detect.py` の `run_detect`) は `_print_detection_stats` のみを呼び `_emit_splitting_elapsed` を一切呼ばないため、`Pass 1` / `Pass 2` / `Scorebar` / Filter drop 内訳は出力されるが `Splitting` elapsed は出力されない
- **行 16 (`Splitting` 進捗バー)**: 分割フェーズが存在しないため detect では常に非出力
- **行 17 のうち `Output: <dir>` + ファイル一覧**: 分割フェーズが存在しないため detect では出力されない。`Metadata: <path>` のみ detect も出力するが、`show` が真のとき (= `-q` でも `--progress-format json` でもないとき) に限る (`run_detect` 末尾の `if show:` ガード)
- **行 15a (ディスク空き容量 warning)**: 出力ファイルを書かないため detect では容量検査そのものを行わない。`_check_disk_space` の呼び出しは `allaganeye/commands/split_matches.py` の 3 箇所 (`run_split` の cache hit / cache miss と `run_split_from_metadata`) だけで、`allaganeye/commands/detect.py` には**関数の参照が 1 つも無い** (#933)

行 12a (`Region:`) は #908 で後から追加した行のため上記 #862 突合には含まれないが、split (`run_split`) / detect (`run_detect`) が同一のガード条件 (`if captured_region is not None:`) で出力するため、**表の値がそのまま detect にも適用される**。この行だけは `_print_detection_stats` の内側ではなく呼び出し元に置かれており (行 11 / 行 12 は同ヘルパ内)、それが #862 PR-A の突合をすり抜けた原因。

行 12b-12e (masked / vtuber の検知統計) も #862 突合の後に追加された行だが、`_print_detection_stats` の**内側**にあり、split (`run_split`) / detect (`run_detect`) が同一のガード条件 (`if verbose and show and detect_stats is not None:`) で同ヘルパを呼ぶため、**表の値がそのまま detect にも適用される** (#920)。

**`-q` の挙動は split と異なる**: detect の `-q` は `show = not quiet and not json_mode` の評価により、`Metadata: <path>` 行も含め stdout を全抑制する。下記「強制 silent 契約 (`-q`)」節は **split 専用**の契約であり、detect の `-q` 挙動には適用されない。

**`--progress-format json` は本マトリクスの対象外**: detect 固有のオプション (#569) で、JSON モード時は構造化 JSON Lines を stdout に出力し他のすべての stdout 出力を抑制する。`--progress-format json` 時の挙動詳細は [`docs/cli-spec.md`](cli-spec.md) §「detect コマンド」を参照。

### `split --from-metadata` の適用境界

`split --from-metadata <metadata.json>` (#463) は検知フェーズを skip する第 3 の実行経路 (`allaganeye/commands/split_matches.py` の `run_split_from_metadata`) で、`run_split` とは別の出力プロファイルを持つ。

- **非出力**: 行 1-10 (環境ヘッダ / HW info / `Probing:` / Metadata 詳細 / `Auto-adjusted` / Dry-run 通知 / Cache hit params / GPU mode / 検知パラメータ summary / 検知進捗バー)、行 11 のうち検知統計部分 (`Pass 1` / `Pass 2` / `Scorebar`)、行 12 (Filter drop 内訳) / 行 12a (`Region:`) / **行 12b-12e (masked / vtuber の検知統計)** / 行 13 (`Detected N match(es)`) / 行 14 (Match 一覧) / 行 15 (Gap 一覧)。いずれも検知を行わないため (`run_split_from_metadata` は `_print_detection_stats` を呼ばない)
- **出力**: 行 16 (`Splitting` 進捗バー) / 行 17 (`Output:` + ファイル一覧 + `Metadata:`) / 行 11 のうち `Splitting` elapsed (`_emit_splitting_elapsed`) / **行 15a (ディスク空き容量 warning)** / 行 18 (`Total:`) / 行 19 系エラー表示
- **本経路固有の行**: 下表 3b / 3c

| # | 出力項目 | 関連Issue | default | `-v` | `-q` | `--dry-run` | `-v --dry-run` | `-q --dry-run` | `-v -q` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3b | `Splitting N match(es) from <metadata.json 名>` (`--from-metadata` 経路のみ) | [#463](https://github.com/Idios/kobutachan-allaganeye/issues/463) | ◯ | ◯ | × | ❌ | ❌ | ❌ | ❌ |
| 3c | `Source: <解決済み source path>` (2 space indent 付き、`--from-metadata` 経路のみ) | [#463](https://github.com/Idios/kobutachan-allaganeye/issues/463) | × | ◯ | × | ❌ | ❌ | ❌ | ❌ |

3b は `if show:` (= `not quiet`)、3c は `if verbose and show:` のガード下 (`run_split_from_metadata`)。`--dry-run` 系列が `❌` なのは `--from-metadata` と `--dry-run` が排他 (exit 5) で行に到達しないため。`-q` 時は 3b / 3c とも抑制され、下記「強制 silent 契約 (`-q`)」節の出力集合 (`Output:` / ファイル一覧 / `Metadata:`) に一致する。

## 排他オプション組み合わせ

同時指定すると **exit code 5** (ConfigValidationError) で終了する (#419):

| 排他ペア | 理由 |
| --- | --- |
| `-q` + `-v` | 「進捗出力抑制」と「詳細出力」は根本的に矛盾するため |
| `--gpu` + `--no-gpu` | GPU 強制と GPU 無効化は矛盾するため |
| `VIDEO_PATH` + `--from-metadata` | 検知実行と検知スキップは同時に成立しないため (#463) |
| `--from-metadata` + `--dry-run` | 分割のみ経路に「分割を skip する」指定は無意味なため。metadata 再生成は `allaganeye detect` を使う |

排他違反時は stderr に以下を出力し split 処理は開始しない:

```text
Error: --quiet and --verbose are mutually exclusive
```

## 直交フラグ (orthogonal flags)

以下のフラグは主軸 (`default` / `-v` / `-q` / `--dry-run`) と**直交**して重畳可能。マトリクスを簡潔に保つため各主軸列とは別軸として扱う:

| 直交フラグ | マトリクスへの影響 |
| --- | --- |
| `--gpu` / `--no-gpu` | **明示指定時は行 8 (`Auto-selected ... mode`) が非出力**になる (`allaganeye/commands/split_matches.py` の `_resolve_gpu_mode_with_probe` が auto 判定に入る前に early return するため)。`--gpu` かつ vendor 解決時は行 8a (`GPU vendor: <vendor>`) のみ出力、`--no-gpu` では行 8 / 8a とも非出力。他行は影響なし。`--gpu` と `--no-gpu` は相互排他 (#419) |
| `--gpu-vendor` | 行 8a の `<vendor>` 値のみ変化。未実装 / probe 未検出の vendor 指定は exit 5 (#546 / #553 / #550 / #582) |
| `--no-cache` | 行 7 (Cache hit params) と行 13 の `(cached)` サフィックスが常に非出力。他行は影響なし |
| `--no-audio` | 行 9 (検知パラメータ summary) の `audio=frozen` / `audio=off` トークンに反映。現状 AUDIO_FROZEN=True のため値に関わらず `frozen` 表示 (#384) |
| `--vtuber` | 行 9 の `vtuber=on` トークンに反映。`--vtuber` 採用 run の verbose 検知統計に **行 12d / 12e** が追加される (#895)。`--vtuber` が縮退 (V0 失敗等) した場合は timeline 統計行は出力されず通常 pass 1/2 統計に戻る。cache ヒット時 (行 7) は `vtuber_algo=N` トークンが `masked_fallback` 直後に挿入される (vtuber 影響 run のみ) |
| `--masked` | 行 9 の `masked=on` トークンに反映。masked fallback 採用 run では verbose 検知統計に **行 12b / 12c** が追加される (#822)。暗転が 1 件も検出できなかった録画では `--masked` 未指定でも fallback が自動発動するため、**行 9 が `masked=off` のままでもこれらの統計行が出力されうる** (#821)。cache ヒット時 (行 7) は `masked=` に加え resolved の `masked_fallback=` が出力され、masked 影響 run のみ `masked_algo=N` トークンが `masked_fallback` の直後に挿入される。`--vtuber` との同時指定は exit 5 |
| `--keep-trailing` | 出力項目自体の有無には影響しない。cache ヒット時 (行 7) の `keep_trailing=on` トークン値に反映され、post-match trailing を通常 match として MP4 化するため行 17 のファイル一覧と行 11 の `Splitting: N matches` の件数が変化しうる (#805)。行 13 の `Detected N match(es)` と行 14 の Match 一覧は default でも post_match segment を数えるため、本フラグでは変化しない |
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
| 8 | `Auto-selected GPU/CPU mode` (auto 判定時のみ。`--gpu` / `--no-gpu` 明示時は非出力) | - | × | ◯ | × | × | ◯ | × | ❌ |
| 8a | `GPU vendor: <vendor>` (2 space indent 付き、GPU 経路採用 + vendor 解決時のみ) | [#546](https://github.com/Idios/kobutachan-allaganeye/issues/546), [#553](https://github.com/Idios/kobutachan-allaganeye/issues/553), [#550](https://github.com/Idios/kobutachan-allaganeye/issues/550) | × | ◯ (GPU 採用 + vendor 解決時のみ) | × | × | ◯ (同左) | × | ❌ |
| 9 | 検知パラメータ summary (`interval=..., threshold=..., workers=auto (N), audio=frozen, vtuber=off, masked=off`) | [#384](https://github.com/Idios/kobutachan-allaganeye/issues/384), [#389](https://github.com/Idios/kobutachan-allaganeye/issues/389) | × | ◯ | × | × | ◯ | × | ❌ |
| 10 | 進捗バー `Detecting` / `Refining` / `Scorebar` | [#368](https://github.com/Idios/kobutachan-allaganeye/issues/368), [#393](https://github.com/Idios/kobutachan-allaganeye/issues/393) | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 11 | 検知統計 (`Pass 1`, `Pass 2`, `Scorebar`, `Splitting` elapsed (split のみ) 含) | [#386](https://github.com/Idios/kobutachan-allaganeye/issues/386), [#387](https://github.com/Idios/kobutachan-allaganeye/issues/387) | × | ◯ | × | × | ◯ | × | ❌ |
| 12 | Filter drop 内訳 + unknown match 行 (`Filter: N candidates -> M matches` + `+ N unknown match (録画途中試合)`) | [#388](https://github.com/Idios/kobutachan-allaganeye/issues/388), [#433](https://github.com/Idios/kobutachan-allaganeye/issues/433) | × | ◯ | × | × | ◯ | × | ❌ |
| 12a | `Region: <capture region token>` (`captured_region` 解決時のみ) | [#810](https://github.com/Idios/kobutachan-allaganeye/issues/810), [#908](https://github.com/Idios/kobutachan-allaganeye/issues/908) | × | ◯ (cache miss 時のみ) | × | × | ◯ (cache miss 時のみ) | × | ❌ |
| 12b | `masked L2 validation: N segment(s) dropped (below quorum)` (2 space indent 付き) | [#822](https://github.com/Idios/kobutachan-allaganeye/issues/822) | × | ◯ (cache miss + masked fallback 採用 + 当該カウンタ > 0 時のみ) | × | × | ◯ (同左) | × | ❌ |
| 12c | `masked L2 zero-gap merge: N pair(s) merged (flank flicker split)` (2 space indent 付き) | [#822](https://github.com/Idios/kobutachan-allaganeye/issues/822) | × | ◯ (cache miss + masked fallback 採用 + 当該カウンタ > 0 時のみ) | × | × | ◯ (同左) | × | ❌ |
| 12d | `Timeline (vtuber): N probes, anchor conf X.XX` (2 space indent 付き) | [#895](https://github.com/Idios/kobutachan-allaganeye/issues/895) | × | ◯ (cache miss + vtuber timeline 採用時のみ) | × | × | ◯ (同左) | × | ❌ |
| 12e | `V3: N gaps tested, N merged, N peek-overridden; V4: N dropped, N low-confidence` (2 space indent 付き) | [#895](https://github.com/Idios/kobutachan-allaganeye/issues/895) | × | ◯ (cache miss + vtuber timeline 採用時のみ) | × | × | ◯ (同左) | × | ❌ |
| 13 | `Detected N match(es) ... (cached)` サフィックス含 | [#418](https://github.com/Idios/kobutachan-allaganeye/issues/418) (M) | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 14 | Match 一覧 (`[unknown]` / `[fl_match]` マーカー含) | [#382](https://github.com/Idios/kobutachan-allaganeye/issues/382) | ◯ | ◯ | × | ◯ | ◯ | × | ❌ |
| 15 | Gap 一覧 | - | × | ◯ | × | × | ◯ | × | ❌ |
| 15a | ディスク空き容量 warning (`Warning: free space is tight (estimated: ..., free: ...)`、**stderr**) | [#338](https://github.com/Idios/kobutachan-allaganeye/issues/338), [#933](https://github.com/Idios/kobutachan-allaganeye/issues/933) | stderr (推定サイズが空きの 80% 超のときのみ) | stderr (同左) | × | - | - | - | ❌ |
| 16 | 進捗バー `Splitting` | - | ◯ | ◯ | × | - | - | - | ❌ |
| 17 | `Output: <dir>` / ファイル一覧 / `Metadata: <path>` | - | ◯ | ◯ | ◯ | - | - | - | ❌ |
| 18 | `Total: <duration>` | [#381](https://github.com/Idios/kobutachan-allaganeye/issues/381) | × | ◯ | × | × | ◯ | × | ❌ |
| 19a | エラー表示 (`-v`): `Error:` + `verbose_detail()` + full traceback | [#428](https://github.com/Idios/kobutachan-allaganeye/issues/428) | - | stderr | - | - | stderr | - | ❌ |
| 19b | エラー表示 (default): `Error:` + 1 行 hint | [#428](https://github.com/Idios/kobutachan-allaganeye/issues/428) | stderr | - | - | stderr | - | - | ❌ |
| 19c | エラー表示 (`-q`): `Error:` のみ | - | - | - | stderr | - | - | stderr | ❌ |

### マトリクスの読み方

- 行 12a (`Region:`) が条件付きなのは、`captured_region` が解決済み (非 `None`) のときだけ出力するため (`run_split` / `run_detect` の `if captured_region is not None:` ガード)。実運用上これは **cache miss (実際に検知を走らせた) と同義**である:
  - **cache miss 時**: `detect_match_boundaries` は標準 / vtuber / masked のどの経路を通っても `region_callback` を必ず呼ぶ。`region_callback(...)` の呼び出しは同関数内の 3 箇所 (vtuber timeline 採用時 / masked fallback 採用時 / 標準 path 確定時) で、早期 return 2 箇所 (`return timeline_boundaries` / `return masked_segments`) はいずれも**直前に**呼び出しを済ませている。したがって `captured_region` は常に埋まり、`-v` なら必ず出力される
  - **cache hit 時**: `captured_region` は cache 記録値から復元される (split は `_split_and_write_metadata` へ `capture_regions=hit.capture_regions` を渡し、detect は `captured_region = hit.capture_regions` を代入する) が、cache-hit 分岐は `Region:` 行に到達する前に return / スキップするため **表示されない**。split は cache-hit 分岐 (`run_split` の `if hit is not None:`) がブロック末尾の `return` で抜けるため `Region:` のガードに到達しない。detect は `Region:` 出力ガードが cache-miss ブロック (`run_detect` の `if boundaries is None:`) の**内側**にあるため、cache hit ではブロックごとスキップされる。`--no-cache` を付ければ cache miss 扱いになり出力される
- **行 12b-12e が「cache miss 時のみ」なのは行 12a と同じ理由**による。4 行はいずれも `_print_detection_stats` が出力し、その呼び出しガードは `if verbose and show and detect_stats is not None:` で、`detect_stats` は `verbose` のときだけ dict になる (`detect_stats = {} if verbose else None`)。cache hit 分岐はこのガードに到達する前に return / スキップするため表示されない
- **行 12b-12e が「採用時のみ」なのは、統計 key が経路ごとに書き分けられているため**。表の凡例より強い条件が付くので個別に記す:
  - **行 12b / 12c (masked)**: `masked_segments_dropped` / `masked_l2_zero_gap_merges` を書くのは masked fallback の経路 (`allaganeye/video/detector.py`) だけで、かつ**カウンタが 0 なら行を出さない** (健全な run で 0 行のノイズを出さないため)。**vtuber 経路では出力されない** — `allaganeye/video/vtuber_timeline.py` の V4 検証は専用の local stats を使って呼ばれ、main stats への key 混入と verbose 二重表示を避けている。V4 の drop 数は行 12e の `V4: N dropped` 側へ translate される
  - **行 12d / 12e (vtuber)**: `if "vtuber_timeline_probes" in stats:` の**単一ガード配下**にあるので 2 行は常に同時に出る。key を書くのは V2 が非空を保証した後で、**縮退時 (V4 が全 segment を drop) は書いた key を pop する**ため、band-crop path へ fall back した run の verbose に放棄した統計は残らない
- **行 15a が stderr かつ `-v` 非依存なのは**、`_check_disk_space` の warning ガードが `if estimated > free * _DISK_SPACE_WARNING_RATIO and show:` (`show` = `not quiet`) であり verbose を見ないため。`--dry-run` 系列が `-` なのは、cache hit / cache miss どちらの経路でも **dry-run の early return が `_check_disk_space` の呼び出しより前**にあり、容量検査そのものに到達しないため (行 16-17 と同じ理由)。推定サイズが空き容量を**超える**場合は warning ではなく exit 1 のエラーになるので、本行は「超えないが 80% を超えた」場合だけの行である
- 行 8 / 行 8a は `allaganeye/commands/split_matches.py` の `_resolve_gpu_mode_with_probe` が出力する。行 8 は **`--gpu` / `--no-gpu` いずれも未指定 (auto 判定) のときだけ**出力される。行 8a は「GPU 経路が採用され (auto 判定で GPU 選択、または `--gpu` 明示)」かつ「vendor が解決できた (`_select_gpu_vendor` が非 `None`)」の AND 条件でのみ出力される。vendor 未解決時は `-hwaccel auto` に縮退し行 8a は出ない
- 行 6 (`Dry-run 通知`) で default / `-v` / `-q` 列が `-` なのは、これらの組合せでは `--dry-run` 自体が指定されていないため「通知する場面が存在しない」という意味
- 行 16-17 で `--dry-run` 系列が `-` なのは、dry-run は分割処理を skip するため split 出力・Splitting バーが発生しない
- 行 19 の `stderr` は「該当モードで該当フォーマットのエラーメッセージが stderr に出る」を意味し、エラーが発生した場合にのみ到達する条件行
- `-v -q` 列が全行 `❌` なのは、CLI 引数パース直後 (split 処理開始前) に ConfigValidationError で即 exit するため

## 強制 silent 契約 (`-q`) — split 専用

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

## ユーザーに提示するパスの契約 (Refs #935 P2-4)

**CLI がユーザーに提示するパス (完了行 / `--json`) は絶対パスで出す。** `-o` に渡された相対パス・ドライブ相対パスをそのまま提示してはならない。

**GUI は本契約の適用範囲外である** (現状パスを受け取っていないため。下表と #968 を参照)。**「提示するパスは絶対」を GUI にも適用済みと読まないこと。**

| 提示先 | 形式 | 実装 |
| --- | --- | --- |
| `--json` の `output_path` | **絶対パス + POSIX 区切り** (`/`) | `Path(os.path.abspath(output_path)).as_posix()` (`allaganeye/export/schema.py` の `ProgressEvent.result`) |
| 完了行 `[OK] match NNN -> <path>` | **絶対パス + プラットフォーム固有の区切り** (Windows は `\`) | 上記 payload を `Path(str(...))` で再構成 (`allaganeye/commands/export.py` / `allaganeye/commands/minimap.py`) |
| GUI | **パスを受け取らない (本契約の適用外)** | Rust 側は wire event の `output_path` を deserialize するが、フロントへ転送する `ExportProgress` (`gui/src-tauri/src/lib.rs`) に**パス field が無い**ため破棄される。GUI が画面に出す出力先はユーザーが指定した値そのもので、本契約の絶対化は**効いていない** (追跡: #968) |

**規約の要点**:

- **絶対化には `os.path.abspath` を使い、`Path.resolve()` は使わない。** `abspath` は正規化のみを行い **symlink を解決しない**ため、報告されるパスが「ffmpeg が実際に書いた場所」と一致する。`resolve()` は symlink 先を返すので、ユーザーが指定した場所と表示が食い違う
- `--json` が POSIX 区切りなのは GUI (wire protocol) 互換のため。人間向けの完了行は**シェル / エクスプローラへそのまま貼れる形**にするため OS ネイティブ区切りにする。**この 2 つが異なるのは意図的**である
- ドライブ相対パス (`E:out` のような Windows 固有形。シェルの quote 落ちで発生する) は、絶対化によって実際の解決先が可視化される。**これが本規約の主目的**である

> **根拠 (#930)**: `-o` に渡された相対パスをそのまま表示していたため、shell の quote 落ちで `E:\royalstraightflesh\videos\20260127` が `E:royalstraightfleshvideos20260127` (ドライブ相対) に化けた際、**実際の書き出し先が読み取れなかった**。quote 落ち自体はユーザーの入力ミスだが、表示がそれを可視化できていなかったことが欠陥である。

**GUI プレビューとの対応 (#964 で mirror 実装済み)**: GUI の name-pattern プレビューは `gui/src/utils/namePatternSandbox.ts` (`computeNamePatternIssues`) が **層 1 と同一の検証を mirror** し、プレビュー時点で警告表示する (`NamePatternWarnings`、ExportScreen / MinimapScreen の命名規則入力下)。警告は「書き出し時に CLI が exit 5 で拒否される」ことを先回りして知らせるもので、**書き出し自体はブロックしない** (字句解決のため symlink 等の実 FS 状態は再現できず、最終 gate は CLI 側の exit 5 のまま)。層 2 / 層 3 は実ファイルの identity (`st_dev`/`st_ino`) を扱うため GUI プレビューへ移植できない。

**name-pattern sandbox 検証の層構造 (#930 + #937)**: CLI の出力パス検証は preflight の文字列・解決パス検査だけでは塞げない経路 (hardlink / 8.3 短縮名 / 予約デバイス名) があるため、**判定の置き場所**を 3 層に分けている。

1. **preflight (書き込み前・文字列/解決パス)**: `resolve_output_paths` が ①出力ディレクトリ外への脱出 ②source video への上書き ③同一ファイルへの衝突 (大文字小文字・`..`・末尾 dot/space は `_identity_key` で fold) ④Windows 不正名 (`:` = NTFS ADS、`#930`) ⑤予約デバイス名 (`NUL`/`CON`/`PRN`/`AUX`/`COM1-9`/`LPT1-9`、`#937` (a)) を exit 5 で拒否。`allaganeye/export/pool.py` の `_render_and_sandbox` / `resolve_output_paths`
2. **worker 再検証 + source hardlink ガード (書き込み直前)**: `export_matches` が per-match で層 1 を再検証 (preflight を通らない caller = GUI / in-process の最終防壁) し、さらに書き込み対象が **source video の hardlink alias** (`st_dev`/`st_ino` 一致) なら書き込み前に拒否 (#937 (b))。path 比較では見えない「出力名 = source の別名」による入力 truncate を防ぐ
3. **post-write identity 検証 (書き込み後)**: `_verify_written_identity` が成功出力の実ファイルを (st_dev, st_ino) で突合し、**hardlink pair / NTFS 8.3 短縮名 alias** を exit 5 で報告 (#937 (b))。preflight は出力ファイルが未作成のため原理的に見えない経路の事後検出 (事前拒否ではなく「成功と誤報告しない」)

**macOS (APFS/HFS+ の case-insensitive volume) は対応 platform 外** (Windows のみ動作確認) のため対象外 (#937 (c))。塞ぐには Darwin での volume case-sensitivity probe が必要で、macOS を対応 platform に含める判断とセットで扱う。層 2 / 層 3 への到達には**作為的な `metadata.json` (予約デバイス名 / 脱出) か、あらかじめ仕込まれた出力ディレクトリ (hardlink) か、対応外 platform** が要り、release blocker ではない。

**本契約の 3 点セット** ([`docs/l2-workflow.md` §規約・ガード導入の 3 点セット](l2-workflow.md) 準拠):

| | 実体 |
| --- | --- |
| ①発火点 | [`/review-pr`](../.agents/skills/review-pr/SKILL.md) Step 5「パス生成点・表示点を触る PR の場合」 |
| ②非実施記録 | 同 step。非該当なら `パス契約: 非該当 (理由: パスの生成点・表示点に変更なし)` を Step 6 に 1 行 |
| ③red 実証 | `tests/test_export_schema.py::test_progress_event_result_reports_absolute_path` (相対 `-o` を渡して絶対パスが返ることを assert。`os.path.abspath` を外すと red になることを PR #930 が実測済み) |

`--json` の絶対化のみ ③ が存在する。**完了行のネイティブ区切りと GUI 側には pin test が無い**ため、この 2 つは現状 ③ 未達である (#934 で機械検査化する範囲に含める)。

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
| `--include I,J,K` / `--exclude I,J,K` | metadata の `matches[].index` (**1 始まり**) と照合して match をフィルタ | **提案モード・crop モードの双方に適用**される (フィルタはモード分岐より前に評価される)。除外された match は crop モードで MP4 が生成されず、提案モードの提案対象・`--json` の出力対象からも外れる。`type_override="skip"` の match はこれらのフラグに関係なく常に除外。`post_match: true` の match も無条件除外 (`--include` 指定でも MP4 化されない、#805 Phase 1 契約) |

### `--json` モード出力行 (crop モード)

`--json` フラグ指定時、stdout の各行は JSON オブジェクト 1 件（JSON Lines 形式）。GUI subprocess が parse する。crop モードの wire protocol は `export` コマンドと同一実装 (`allaganeye/export/pool.py` / `allaganeye/export/schema.py`) を共有するため、イベント種別を増減する変更は本節と [`docs/cli-spec.md` §「Wire protocol (`--json` モード)」](cli-spec.md) の両方を同 PR で更新する:

- `{"type":"progress","match_index":N,"percent":P,"stage":"encoding"|"done"}` — encode 進捗。1 match につき複数行 emit される (`stage` は encode 中が `"encoding"`、完了時に `percent=100.0` で `"done"`)
- `{"type":"result","match_index":N,"output_path":"...","duration_ms":N,"encoder_used":"h264_nvenc"|"libx264"|...}` — 1 match 成功
- `{"type":"error","match_index":N,"error_kind":"...","error_message":"...","error_hint":null|"..."}` — 1 match 失敗
- `{"type":"fallback","match_index":N,"fallback_from":"h264_nvenc","fallback_to":"libx264","message":"..."}` — GPU encoder 失敗 → libx264 fallback
- `{"type":"summary","success":N,"failure":N,"skipped":N,"cancelled":bool}` — 常に最終行

CAS 衝突 (`--expected-mtime` 不一致) は stdout への JSON 出力なしで **exit 6** のみ。GUI は exit 6 を受けて ConflictModal を表示する。

### `--json` モード出力行 (提案モード)

提案モードで `--json` を指定すると、stdout に match ごとに 1 行ずつ proposal を出力し常に exit 4 で終了する:

- `{"type":"proposal","match_index":N,"region":{"x":X,"y":Y,"w":W,"h":H}|null,"confidence":C,"scattered":bool}` — `region` は検出成功時は座標オブジェクト、失敗時は `null`。`confidence` は 0.0-1.0。`scattered` は検出結果が散らばり consensus が低いことを示す
