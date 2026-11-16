# L4: イベントデータ出力フォーマットの設計 (2026-11-16)

- **日付**: 2026-11-16
- **目的**: #127（L4 メタデータ化）のイベント出力フォーマット確定。`ko_indicator` /
  `assist_indicator` を主対象に、後続レイヤー（L6 価値評価 / L7 自動編集 / L5 OBS
  プラグイン）が同じ表現を消費できる形を決める
- **前提**: 信号モデルの設計は
  [`2026-09-10-l4l6-highlight-signal-model-design.md`](2026-09-10-l4l6-highlight-signal-model-design.md)
  §5 が正（**履歴として本文を書き換えない**）。本 note は §5.1 の語彙を実装可能な
  ワイヤ形式に落とし、**spec との差分を明記**する。KO / ASSIST の外観実測は
  [`2026-11-12-l4-ko-assist-indicator-appearance.md`](2026-11-12-l4-ko-assist-indicator-appearance.md)
  が正
- **実装**: #1106 作業項目 4（本 note に従って `allaganeye indicators` の出力と
  `metadata.json` の永続化を確定させる）

## 1. 決定事項

Idios 判断（2026-11-16、4 択すべて A）:

| # | 論点 | 決定 |
| --- | --- | --- |
| 1 | 出力先 | **`metadata.json` の root に `events[]` を持たせる**（`indicator_layout` と同じ write-back 経路）。`-o` は同形のエクスポートとして維持する |
| 2 | 語彙 | spec §5.1 に合わせて `signal_id` / `timestamp` / `score` / `evidence` を軸にし、`end` と `match_index` を足す（§3 で差分を明記）。`kind` / `start` は廃止 |
| 3 | 時刻基準 | **元録画の絶対秒**（float、0.01 秒丸め）。試合相対は consumer が導出する。**表示は `hh:mm:ss`** |
| 4 | 互換ルール | event item は **`additionalProperties: true`**（未知フィールド許容）。consumer は**未知 `signal_id` を既定で無視**する |
| - | `schema_version` | 追加は optional な root キーなので `"1"` のまま据え置く（bump すると既存 consumer に migration を強いるだけで、読み手が得る情報が増えない） |

### 決定 1 の根拠（GUI の書き戻し経路）

GUI の `[適用]`（`gui/src/state/metadataStore.ts::normalizeForPersistence`）は **root を
spread で保持**し、**match 配列だけを許可リストで組み直す**（`index` / `start_time` /
`end_time` / `*_display` / `duration` / `type` / `output_file` / `post_match`）。
つまり:

- **root に置いた `events[]` は GUI 経由の保存で保持される**
- **match 単位に置くと GUI 経由で落ちる**（新しい match フィールドを足すたびに
  allowlist と TS 型と Rust の検証を同時に直す必要がある）

読み込み側の zod は root / match とも `.passthrough()` なので、未知の root キーは
`load` で失われない。よって置き場所は root が正しい。

## 2. スキーマ

`schemas/metadata.schema.json` の `$defs.HighlightEvent`（root から
`events: HighlightEvent[]` として参照）。**SSoT は JSON Schema** で、Python の
`TypedDict`（`allaganeye/metadata_types.py`）と TypeScript の型
（`gui/src/types/metadata.generated.ts`）は codegen で生成する。

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `signal_id` | string (minLength 1) | ✓ | 信号識別子。現行値は `"ko_indicator"` / `"assist_indicator"`。**enum にしない**（信号追加のたびに schema を変えると、追加そのものが破壊的変更になる） |
| `timestamp` | number >= 0 | ✓ | 発生時刻。**元録画先頭からの絶対秒**（0.01 秒丸め） |
| `end` | number >= 0 | ✓ | 表示区間の終端（同じ基準の絶対秒）。L7 の切り出し幅と L6 のストリーク判定に使う |
| `score` | number [0,1] | ✓ | 検出の確信度（テンプレートマッチの区間内最大値） |
| `evidence` | object（自由） | ✓ | 検出根拠。現行の文書化キーは `samples`（連続ヒットした走査サンプル数。走査間隔 0.1 秒なら 15 が約 1.5 秒の表示に対応）。**追加キーは自由** |
| `match_index` | integer >= 1 または null | ✓ | 属する試合の `matches[].index`。どの試合区間にも入らない場合は `null`（イベント自体は捨てない） |

- `match_index` は `null` を取りうるので `"type": ["integer", "null"]`。**キー自体は常に出す**
  （省略すると consumer ごとに「無い」と「null」の 2 状態を扱う必要がある）
- `evidence` は必須だが中身は自由。必須にしたのは「根拠を持たないイベント」を producer 側で
  作らせないため（読み手は未知キーを無視できる）
- event item は `additionalProperties: true`、root は従来どおり `additionalProperties: false`
  （root は「知らない領域」を増やしたくない = 同居の判断を明示的に行う。event は
  信号追加のたびに増えるので開けておく）

### 例

```json
{
  "signal_id": "ko_indicator",
  "timestamp": 493.4,
  "end": 494.9,
  "score": 0.93,
  "evidence": { "samples": 15 },
  "match_index": 1
}
```

## 3. spec §5.1 との差分

| spec §5.1 | 本 note | 理由 |
| --- | --- | --- |
| `signal_id` | `signal_id`（同じ） | 種別（KO / ASSIST）と検出器の出所を 1 項目に集約できる。`kind` との二重表現は持たない |
| `timestamp` | `timestamp`（同じ、絶対秒） | 試合相対は `timestamp - matches[i].start_time` で一意に導出できる（重複保存しない） |
| `score` | `score`（同じ、0..1） | 変更なし |
| `evidence` | `evidence`（同じ、自由 object） | 変更なし。現行実装は `samples` を入れる |
| （なし） | **`end` を追加** | spec は点イベントだが、実装は「表示区間」（KO は約 1.5 秒、連続更新は 0.15-0.35 秒間隔）を返す。L7 の切り出しに終端が要る |
| （なし） | **`match_index` を追加** | spec の `timestamp` だけでは「どの試合か」を consumer が毎回区間探索する必要がある。producer は既に区間を持っている |

**点イベントとして使いたい consumer** は `timestamp` だけ読めばよい（`end` は無視可能）。

## 4. 互換ルール

1. **producer はフィールドを追加してよい。** event item は `additionalProperties: true` なので
   schema 違反にならない。既存フィールドの意味・型・単位は破壊的に変えない
2. **consumer は未知フィールドを無視する。** JSON の読み取りはキー指定で行い、全キーの
   網羅一致を要求しない
3. **未知 `signal_id` は既定で無視する。** 新しい信号（`kill_feed` / `lb_reset` 等）が
   増えても、既存 consumer は「知らない信号」として素通りさせる。判定は**許可リスト方式**
   （既知だけを扱い、未知は落とさず読み飛ばす）にする
4. **`signal_id` は enum にしない**（schema も string + minLength）。enum にすると
   信号追加 = schema の破壊的変更になる
5. 削除・改名は破壊的変更として扱う（旧キーを 1 リリース残すか、`signal_id` 側で
   バージョンを切る）。**現時点で削除予定のフィールドは無い**

pin の方法:

- schema 側: `tests/test_indicators_events.py` が **`additionalProperties: true` と
  `signal_id` が enum でないこと**を schema から直接読み、互換ルール 1/3/4 を固定する
- consumer 側: `gui/src/screens/IndicatorsScreen.test.tsx` が**未知 `signal_id` を
  描画しない**ことを固定する
- 生成物: codegen の drift は CI（`python` / `gui-frontend` job の
  `git diff --exit-code`）が固定する（declaration-catalog `metadata-schema`）

## 5. 出力経路

| 経路 | 何が出るか |
| --- | --- |
| `allaganeye indicators <metadata>`（既定） | stdout に人間向け summary。**表示は `hh:mm:ss`** |
| 同 `-o PATH` | `{"metadata", "layout", "recalibrated", "events"}` の JSON ドキュメント。`events[]` は §2 の形 |
| 同 `--json` | stdout に JSON Lines。最終 `complete` 行が `-o` と同じ本体を持つ |
| 同 `--write`（既定） | `metadata.json` に `indicator_layout` と **`events`（全件で置換）** を同じ atomic write で書く |
| 同 `--no-write` | `metadata.json` を変更しない（`events` も書かない） |
| `allaganeye detect` / `split` / `export` / `minimap` | `events` を書かない・読まない（L4 は検知パイプラインの外） |

- **`--write` が `events` も書く理由**: 検出は録画 15 分あたり数分かかる。結果を
  metadata に残さないと、GUI を閉じた時点で失われ、L6 / L7 は毎回再走査になる
- **置換セマンティクス**: `events` は毎回**全件置換**する（差分マージはしない）。
  検出条件（`--interval` / `--region` / しきい値）が変われば結果集合そのものが変わるため、
  古いイベントを残すと「どの条件の結果か」が曖昧になる
- `indicator_layout` と `events` は**同じ write** に入れる（片方だけ更新された中間状態を
  作らない）。CAS guard（`--expected-mtime`、exit 6）は両方に効く
- `-o` は staging → `os.replace` のまま（既存挙動）。metadata write-back の後に公開する
  順序も既存どおり

## 6. consumer 側の参照方法

- **GUI**: `start_indicators` の `complete` payload（`events[]`）をそのまま表示する。
  `metadata.events` は zod（`HighlightEventSchema`、event は passthrough）で読み、
  `[適用]` でも root のまま保持する。未知 `signal_id` は描画しない
- **L6 価値評価（#1049）**: `events[]` の `timestamp` / `end` / `signal_id` を使う。
  ストリークは spec §5.3 の ±5 秒窓（設定可能）。`score` は重み付けの入力
- **L7 自動編集**: `timestamp - pre` 〜 `end + post` で切り出す（`match_index` から
  `matches[i]` の出力ファイル / 区間を引く）
- **L5 OBS プラグイン（#1107）**: 参照方法の決定は #1107 に委譲する。本 note は
  「同じ `events[]` を読めばよい」ところまでを固定する

## 7. 未決 / 将来

- 走査間隔を変えると `evidence.samples` の意味が変わる（0.1 秒で 15 = 約 1.5 秒）。
  秒に正規化した `duration_s` を足すかは、L6 で `samples` を実際に使うときに判断する
- 信号が増えて `events[]` が大きくなった場合の分割（artifact 化）は、実測サイズが
  問題になってから判断する（現行は 15 分あたり数十件 = 数 KB 程度）
- `score` の校正（検出器ごとに意味が違う）は #1046 / #1049 の範囲
