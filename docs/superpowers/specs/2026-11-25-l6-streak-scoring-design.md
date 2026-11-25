# L6: rule-based ストリークスコアリングの設計 (2026-11-25)

- **日付**: 2026-11-25
- **目的**: #1049（L6 価値評価）のスコア関数と、その GT 検証方法を確定する
- **前提**: 信号モデルは
  [`2026-09-10-l4l6-highlight-signal-model-design.md`](2026-09-10-l4l6-highlight-signal-model-design.md)
  §5.3 が正（**履歴として本文を書き換えない**）。イベントのワイヤ形式は
  [`2026-11-16-l4-event-output-format-design.md`](2026-11-16-l4-event-output-format-design.md)
  の `events[]` が正
- **実装**: `allaganeye/highlights/scoring.py`（純関数のみ。I/O は持たない）

## 1. 決定事項

Idios 判断（2026-11-25）:

| # | 論点 | 決定 |
| --- | --- | --- |
| Q1(B) | スコアの構成要素 | **重み付き長さ（KO > ASSIST）+ 密度**。試合文脈（スコア差・残り時間）は 0.4.0 では使わない |
| Q2(C) | ストリークの窓 | **パラメータ化**し、既定は spec §5.3 の **±5 秒**。GT で 5 / 10 / 15 秒を比較してから既定値を確定する |
| Q3(B) | 検証方法 | **全ストリークを 3 段階（強 / 中 / 弱）で人手採点**し、モデルスコアとの **Spearman 相関**で評価する（採点は Idios の作業） |
| Q4(B) | 出力 | `metadata.highlights[]`（root、`{index, match_index, start, end, score, event_positions, signal_ids}`）。**write-back は L7 (#135) で行う**。本 phase は型と計算まで |

### Q1 で試合文脈を落とした理由

スコア差・残り時間といった試合文脈は `metadata.json` に系列として存在しない
（`matches[]` にあるのは境界時刻だけ）。文脈を入れるには試合中のスコアバーを
0.1 秒刻みで読む新しい信号抽出が必要で、±数点の精度向上に対して検出系の
追加コストが見合わない。**0.4.0 はイベント列だけで完結させる**。将来
`signal_id` を増やせば同じ `ScoringEvent` 正規化で吸収できる（§2）。

## 2. 信号 → ストリークへの正規化

metadata の `events[]` はレイヤー間の契約なので、スコア関数は生の dict を読まない。
`ScoringEvent.from_signal()` が `signal_id` を内部の `kind` に写す:

| `signal_id` | `kind` | provenance（スコアに影響しない） |
| --- | --- | --- |
| `ko_indicator` | `ko` | `position`（metadata 内の 1 始まり索引） |
| `assist_indicator` | `assist` | `signal_id` / `match_index` |
| 未知の値 | （捨てる） | — |

- **未知 `signal_id` は None を返して無視する**。イベント形式 spec §1 の
  「consumer は未知 `signal_id` を既定で無視する」をそのまま実装したもので、
  信号を足しても既存の読み手が壊れない。
- 非有限の `timestamp` / `end` は捨てる（`NaN` を 1 件混ぜるとソートが壊れ、
  以降のストリークが全滅するため、入口で落とす）。
- `end < start` は `end = start` に**丸める**（捨てない）。`end` はスコアに
  寄与せず（§4）、`Highlight.end` の表示にだけ効くため、欠測より丸めが安全。

## 3. 束ね方（ストリークの定義）

```text
sort events by (start, end, kind)
for each event: if event.start - last_event.start <= window: append to current group
                else: start a new group
```

**判定に使うのは直前イベントの「発生時刻」で、表示終了時刻ではない。** spec §5.3 は
「あるイベントの前後 5 秒以内に別の KO / ASSIST があれば同一ストリーク」と書いており、
表示長（`.evidence.samples` 由来の `end`）に依存させると同じ試合でも HUD や
走査 fps で境界が動いてしまう。発生時刻の差だけで閉じれば、`end` の推定精度から独立する。

この規則は**連鎖**する（推移的閉包）:

| 発生時刻 | 結果 |
| --- | --- |
| 3 / 6 / 9 秒（3 秒刻み） | 1 本（3 件）。合計 span は 6 秒だが隣接差がすべて 5 秒以内 |
| 3 / 9 秒（6 秒差） | 2 本（各 1 件） |

「ストリーク全体の幅が窓以内」ではなく連鎖を採るのは、`KO → 4 秒後 ASSIST →
8 秒後 KO` のような**実際の連続した活躍**を 1 本にまとめるため。幅で切ると
この例が 2 本に割れる。

`window_seconds` は有限かつ非負を要求する（`0` は「同時刻のみ束ねる」、
負値と非有限は `ValueError`）。非有限 `start` のイベントは束ねの前に落とす。

## 4. スコア式

```text
weighted     = ko_weight * ko_count + assist_weight * assist_count
length_term  = weighted / (weighted + saturation)          # 0..1 へ単調飽和
span         = 最後の event.start - 最初の event.start
density      = size / max(span + window, 1e-6)
density_term = min(1, density / full_density)
score        = length_share * length_term + (1 - length_share) * density_term
             = round(clamp(score, 0, 1), 3)
```

| 定数 | 値 | 意味 |
| --- | --- | --- |
| `ko_weight` | 1.0 | 基準。KO は 1 試合あたり GT 実測 4-11 回 |
| `assist_weight` | 0.35 | ASSIST は KO の 3-4 倍出るため同数なら KO を高く評価する。**GT 後に調整する前提の初期値** |
| `saturation` | 1.5 | 重み付き件数が増えても 1.0 に張り付かないための飽和点 |
| `full_density` | 0.25 | 「1 秒あたり 0.25 件」で密度項が満点 |
| `length_share` | 0.7 | 長さ項 7 : 密度項 3 |

### 計算例（既定 ±5 秒）

| ストリーク | length_term | density_term | score |
| --- | --- | --- | --- |
| 単独 KO | 1/2.5 = 0.400 | 1/5/0.25 = 0.800 | **0.520** |
| 単独 ASSIST | 0.35/1.85 = 0.189 | 0.800 | **0.372** |
| KO + ASSIST（2 秒差） | 1.35/2.85 = 0.474 | 2/7/0.25 = 1.143 → 1.0 | **0.632** |
| KO ×2（1 秒差） | 2/3.5 = 0.571 | 2/6/0.25 = 1.333 → 1.0 | **0.698** |

**単独イベントの密度項は `1 / window` に反比例する**（`span = 0` のため）。
つまり `window` はスコアの絶対水準を動かす。窓を変えた比較では順位相関（§5）だけを
見るのはこのため。

## 5. GT 検証方法（Q3-B）

### 5.1 GT の作り方

1. 参照窓（±5 秒）で束ねた**全ストリークが `tests/fixtures/highlights_gt/scoring_gt.json` に
   draft（`tier: null`）として入っている**。束ね結果は機械生成なので、手で書き写さない
2. Idios が各 group の `tier` を **3 = 強 / 2 = 中 / 1 = 弱** で埋める
3. `chosen_window_seconds` を `5 / 10 / 15` のいずれかに記入する（§5.2 の実測から選ぶ）

**採点はスコアを見ずに行う**（アンカリング回避）。draft にスコア列は無く、
一覧が要るときは `pytest -s tests/test_highlight_scoring_gt.py` の出力（スコアなし）を
使う。スコア付きの一覧は `_worksheet(with_score=True)` でしか出ない。

GT は**参照窓のグループ（イベント列そのもの）を保持**し、時刻だけに依存させない:

```json
{
  "reference_window_seconds": 5.0,
  "chosen_window_seconds": null,
  "provenance": "...",
  "cases": [
    {
      "label": "ref1",
      "source": "tests/fixtures/indicators_gt/20260116_1.json",
      "groups": [
        { "tier": 3, "events": [{ "kind": "ko", "start": 123.4 }, { "kind": "assist", "start": 127.0 }] },
        { "tier": null, "events": [{ "kind": "assist", "start": 200.5 }] }
      ]
    }
  ]
}
```

イベント列を持たせるのは、**窓を変えたときの対応付けを決定的にする**ため。
時刻（丸め値）で突き合わせると、イベント列や束ね規則を変えたときに静かに
別グループと一致しうる。

draft のままでも**構造の検査（§5.3 の 1 番目）は有効**になる。`tier` を全部埋めて
`chosen_window_seconds` を記入した時点で Spearman ゲートが有効化される。

### 5.2 窓の比較

参照窓は**下限**として扱う（±5 秒で束ねたグループは、より広い窓では必ず
1 本に収まる）。窓 `W >= reference` について:

1. 各 case のイベントを `W` で束ねる
2. 参照グループを、その全イベントを含む `W` のストリークへ写す
3. `W` のストリークの参照段階 = 写ってきた参照段階の **max**（「その範囲で
   一番良い瞬間」がハイライトの強さだとみなす）
4. 全 case の (モデルスコア, 参照段階) で Spearman 相関 `rho` を取る

`max` を採るのは、ハイライトの体感が「区間の平均」より「最良の瞬間」に
引きずられるため。**ただし広い窓では段階が上方へ寄るバイアスがある**ので、
レポートには `mean` 版の `rho` も併記する（ゲートは `max` 版）。

### 5.3 合否

1. 参照グループが `group_streaks(events, reference_window)` の結果と**一致**すること
   （GT と実装のドリフト検出。draft でも実行する）
2. GT のイベント集合が indicators の GT と**完全一致**すること（グループの取りこぼし検出）
3. `chosen_window_seconds` が `{5, 10, 15}` のいずれかで、`rho` が**最大**の窓と一致すること
4. その窓の `rho >= 0.60`（**暫定値**。裁定データを見て確定する。§7）

`chosen_window_seconds` を GT 側に持たせるのは、「どの窓が最良か」という
**判断をデータと同じ場所に固定**するため。実装側だけで argmax を取ると、
スコア式の変更が選定の根拠を黙って書き換えてしまう。

### 5.4 GT が未裁定のときの扱い

| 状態 | 挙動 |
| --- | --- |
| `scoring_gt.json` が無い | GT テストは**理由付きで skip**（`#992` の areamap GT と同じ扱い） |
| draft（`tier: null` が残る） | **構造と束ねの整合（§5.3 の 1–2 番目）は実行**し、Spearman だけ skip |
| 裁定済 + `chosen_window_seconds` 記入 | 全項目を実行（毎 PR の回帰ゲート） |

Spearman の経路（ロード → 窓写像 → 相関）は、裁定を待たずに**合成 GT** で
検証してある（`test_synthetic_gt_runs_the_full_gate_path`）。合成 GT はスコアから
機械的に tier を作るので精度の根拠にはならないが、写像の取り違えを検出できる。
逆順の合成 GT で `rho < 0` になること（ゲートが実際に落ちること）も pin している。

**このテストは `slow` マーカーを付けない。** 入力は既存の GT JSON
（`tests/fixtures/indicators_gt/*.json`）だけで動画を開かないため、CI の
既定実行に含められる。

## 6. 実測（2026-11-25、GT イベント 87 件 / 3 case）

`tests/fixtures/indicators_gt/*.json` の GT イベント（`20260116_1` 31 件 /
`20260116_5` 51 件 / `other_hud` 5 件）を入力にした束ね結果:

| 窓 | ストリーク数 | 複数イベント | 最大サイズ | サイズ分布 |
| --- | --- | --- | --- | --- |
| ±5 秒 | 63 | 18（29%） | 3 | 1:45 / 2:12 / 3:6 |
| ±10 秒 | 51 | 24（47%） | 5 | 1:27 / 2:15 / 3:7 / 4:1 / 5:1 |
| ±15 秒 | 40 | 19（48%） | 7 | 1:21 / 2:7 / 3:5 / 4:2 / 5:2 / 6:2 / 7:1 |
| ±20 秒 | 33 | 19（58%） | 9 | 1:14 / 2:6 / 3:5 / 4:2 / 5:2 / 6:2 / 7:1 / 9:1 |

**±5 秒では 71% が単独イベントである。** これは spec §5.3 の既定を否定する材料では
ない（単独 KO にも価値はある）が、GT 比較の設計に効く:

スコアの分布は ±5 秒で **12 種類しかなく、うち 27 件が 0.372（単独 ASSIST）に集中**する:

| 窓 | スコアの異なり数 | 最大の同点塊 |
| --- | --- | --- |
| ±5 秒 | 12 | 27 件（0.372 = 単独 ASSIST） |
| ±10 秒 | 23 | 6 件 |
| ±15 秒 | 19 | 5 件 |

> **帰結**: ±5 秒の Spearman は 27 件の同点塊に支配され、**識別力がほぼ無い**。
> GT 裁定は参照窓（±5 秒）の全 63 件に付けるが、**窓の選定は ±10 / ±15 の
> `rho` で行う**のが妥当、というのが実測からの示唆。最終判断は Idios（§7）。

## 7. 未決事項

1. **既定窓**: 5 / 10 / 15 秒のうち `rho` 最大のもの。GT 裁定後に `chosen_window_seconds`
   を埋めて確定する。§6 の同点塊を踏まえると ±10 秒が有力
2. **`assist_weight` / `saturation` / `full_density` / `length_share`**: 現値は
   「単独 KO > 単独 ASSIST かつ KO+ASSIST が単独 KO より上」という順序制約だけを
   満たす初期値。裁定データで順序が崩れたら調整する
3. **`rho` の合格しきい値**: 暫定 0.60。段階が 3 値なので上限は 1.0 だが、
   同点塊があれば 0.8 超は現実的でない
4. **ML 導入判断**（issue 作業項目 4）: rule-based の `rho` を見てから。
   本 phase では判断しない

## 8. 実装メモ

- 公開 API: `group_streaks` / `score_streak` / `score_events` / `rank_streaks` /
  `to_highlights` / `scoring_events_from_metadata`
- `score_events` は**発生時刻昇順**を返す（`rank_streaks` は別関数）。並びを
  暗黙に変えると `event_positions` の対応が読み手から追えなくなるため分けた
- `to_highlights` の `index` は**スコア順の 1 始まり**。`event_positions` は
  metadata `events[]` の 1 始まり索引で、L7 が前後秒数拡張に使う
- `Highlight.start` / `end` は**イベントの活動区間**（最初の発生〜最後の終了）。
  `--pre` / `--post` の拡張は L7 の責務
- `metadata.highlights[]` の write-back・schema 追加は #135（L7）。本 phase は
  `to_payload()` の形までを固定する
