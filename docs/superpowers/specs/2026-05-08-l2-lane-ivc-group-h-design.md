# L2 Lane IV-c: Group H lint / CLI 系 polish 設計

> **Status**: v0.2.0 wave 0 (Lane IV-c) — `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` Group H に対応
> **Scope**: [#643](https://github.com/Idios/kobutachan-allaganeye/issues/643) ESLint Tauri 2 silent loss 予防 + [#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) CLI progress bar ETA ラベル (1 spec / 2 章 / 2 PR)
> **session**: `musing-davinci-38136f` (2026-05-08 brainstorming)

## 関連 issue 整理 (本 spec 着手時の wave 0 確定)

| issue | priority | 状態 | 処置 |
| --- | --- | --- | --- |
| [#643](https://github.com/Idios/kobutachan-allaganeye/issues/643) | P3 (task) | OPEN | **本 spec §4 (章 1) で対応** |
| [#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) | bug (P3 相当、v0.2.0 取り込み disposition、2026-05-07) | OPEN | **本 spec §5 (章 2) で対応**。L1 CLI 由来 bug だが Idios 判断で v0.2.0 内に取り込み |

両 issue は file 衝突なし (lint config = `gui/`、progress bar = `allaganeye/`)、依存なし。Lane IV-c の wave 0 並行 polish として 1 spec / 2 章 / 2 PR 構成で扱う (roadmap.md L98 / L168-169)。

## §1 Background

### 1.1 #643 — Tauri 2 silent loss 再発防止 (lint level)

PR [#628](https://github.com/Idios/kobutachan-allaganeye/pull/628) の実機 UAT で発見:

- `PreviewScreen` の `[◀ 一覧へ]` / `[書き出し →]` 経路で `window.confirm()` を使っていたが、Tauri 2 WebView2 の security 制約で dialog は no-op となり、`window.confirm()` が常に `false` を返す silent loss が発生
- 同 PR の commit `cc94f1f` で `gui/src/screens/PreviewScreen.tsx` (handleBack/Export) と `gui/src/components/RestoreButton.tsx` の `window.confirm` を `@tauri-apps/plugin-dialog` の `ask` に一括 migrate して解消
- 同時に `docs/ui-interaction-spec.md` §1.3 を「Tauri 2 plugin-dialog ask 必須、全画面で統一」に書き換え

**現状の問題**: lint レベルで強制していないため、将来の新規 GUI 画面・新規 component で `window.confirm()` / `window.alert()` / `window.prompt()` を素朴に書き直すと再発する。実装者が docs を読まないと気付けない。

### 1.2 #365 — 進捗バーの ETA ラベル不足 (PR #343 不完全修正)

issue [#329](https://github.com/Idios/kobutachan-allaganeye/issues/329) で「時間表示に ETA ラベルを付ける」要件が起票され、PR [#343](https://github.com/Idios/kobutachan-allaganeye/pull/343) で対応されたが現実装は要件未達。

ユーザーには `93%  00:00:22` のようにラベルなしの数値が表示され、その時間が経過時間か残り時間か判断できない (issue body の再現 console 出力):

```text
(.venv) E:\tmp\allaganeye-usertest\kobutachan-allaganeye>allaganeye split "..\2026-04-08 21-14-05.mkv" --dry-run
Probing: 2026-04-08 21-14-05.mkv
[dry-run] Detect only. Video will not be split.
Detecting  #################################---  93%  00:00:22
```

**根本原因**: `allaganeye/commands/split_matches.py:1083-1089` の `_eta_progressbar`:

```python
return click.progressbar(
    length=length,
    label=label.ljust(_PROGRESS_LABEL_WIDTH),
    bar_template="%(label)s%(bar)s %(info)s",
    show_eta=True,
    show_percent=True,
)
```

click 8.x の `%(info)s` は `<percent>  <eta>` をラベルなしで展開するだけ。`ETA:` を含む format には `%(eta)s` placeholder の独自展開、または `format_progress_line` の override が必要。

**影響範囲**: `_eta_progressbar` を使う全 progress bar = `Detecting` / `Refining` / `Scorebar` / `Splitting` の 4 bar 全て (caller は `split_matches.py:810 / 898 / 922 / 1130`)。

**根本原因 (二次)**: PR #343 のテストで実出力にラベル文字列 `'ETA: '` が含まれることを検証していなかった (進捗バー出力の snapshot / 部分文字列テスト不在) ため、実装が要件を満たしていないことに merge まで気付けなかった。

## §2 Goals

### 2.1 #643 (章 1)

- `gui/src/` 配下に `confirm()` / `alert()` / `prompt()` (bare global) を書くと ESLint がエラー
- `window.confirm()` / `window.alert()` / `window.prompt()` (member access) を書くと ESLint がエラー
- エラーメッセージで `@tauri-apps/plugin-dialog` の代替 API + `docs/ui-interaction-spec.md` §1.3 リンクを案内
- 既存 `gui/src/` は新 rule 全 PASS (現状実呼び出し残存なし)
- 違反コードに対して CI lint job が exit 1 で fail することを **CI run URL の machine-verified evidence** で実証

### 2.2 #365 (章 2)

- Detecting / Refining / Scorebar / Splitting の 4 bar 全てで `93% ETA: 00:00:22` 形式に統一
- GPU mode (`suppress_click_eta=True` → `show_eta=False`、PR [#438](https://github.com/Idios/kobutachan-allaganeye/pull/438) 経路) でも ETA 二重表示が起きないこと
- 進捗バー出力に対する `format_progress_line()` ダイレクト assertion を unit test に追加し、PR #343 で起きた「テスト無しで不完全 merge」の再発を防ぐ

## §3 Architecture & Scope

### 3.1 Lane IV-c 全体構造

```text
Group H: lint / CLI 系 polish (1 spec / 2 章 / 2 PR)
├── 章 1: #643 ESLint Tauri 2 silent loss 予防 (gui/)
│   PR #1: gui/eslint.config.js + docs/ui-interaction-spec.md
└── 章 2: #365 CLI progress bar ETA ラベル (allaganeye/)
    PR #2: allaganeye/commands/split_matches.py + tests/test_split_matches.py
```

### 3.2 file 衝突境界 (roadmap.md §3-bis matrix を継承)

| 章 | 触る file | 触らない file (file matrix で他 lane と共有しない確認) |
| --- | --- | --- |
| 章 1 (#643) | `gui/eslint.config.js`、`docs/ui-interaction-spec.md` | `gui/src/**` (本 PR で実装変更なし、既存コードは新 rule 全 PASS)、`gui/src-tauri/**`、`allaganeye/**` |
| 章 2 (#365) | `allaganeye/commands/split_matches.py`、`tests/test_split_matches.py` | `gui/**`、`allaganeye/video/**`、`allaganeye/audio/**`、`allaganeye/cli.py` |

→ **章 1 と章 2 は完全独立**。同 worktree (Lane IV-c) で 2 branch 切替方式で開発し、2 PR を同時並行で出す:

- 章 1 branch: `claude/musing-davinci-38136f-eslint`
- 章 2 branch: `claude/musing-davinci-38136f-progress-bar`

### 3.3 Iron Law 整合

| Iron Law | 担保方法 |
| --- | --- |
| 1: 受け入れ条件逐条 | §4 / §5 の「受け入れ条件マッピング」表で各 PR review 時に逐条 evidence |
| 3: scope creep 禁止 | 1 PR = 1 issue を厳守。ESLint config と progress bar を 1 PR にまとめない |
| 4: Closes/Fixes/Resolves 禁止 | PR 本文・commit に `Refs #643` / `Refs #365` のみ。close は別途 `/close-issue` skill |
| 6: PR Pre-flight | 各 PR で `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + `gh pr list --search "<元 issue#> in:title,body" --state all` (例: `gh pr list --search "643 in:title,body" --state all`) で並行 worktree PR 重複確認 |
| 6: 自動チェック (path 別) | 章 1 = `npm run lint` / `typecheck` / `test` / `build` + `cargo check`、章 2 = `pytest` / `ruff check` / `ruff format --check` / `pyright` |
| 6: 実機検証 trigger | 章 1 = config-only で実機不要 (検証 PR で CI evidence)、章 2 = 短い動画 1 回 + GPU mode 1 回の表示確認を AskUserQuestion で依頼 |

## §4 章 1: #643 ESLint Tauri 2 silent loss 予防

### 4.1 `gui/eslint.config.js` patch

既存 `src/**/*.{ts,tsx}` block の `rules` 内に `no-restricted-globals` + `no-restricted-properties` を追加:

```js
{
  files: ['src/**/*.{ts,tsx}'],
  languageOptions: {
    globals: {
      ...globals.browser,
    },
  },
  plugins: { 'react-hooks': reactHooks },
  rules: {
    ...reactHooks.configs.recommended.rules,

    // #643: Tauri 2 WebView2 disables window.confirm/alert/prompt as no-op.
    // Catch both bare global calls and `window.X` member access.
    // See docs/ui-interaction-spec.md §1.3.
    'no-restricted-globals': [
      'error',
      {
        name: 'confirm',
        message:
          'Tauri 2 WebView2 disables window.confirm. Use `import { ask } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
      },
      {
        name: 'alert',
        message:
          'Tauri 2 WebView2 disables window.alert. Use `import { message } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
      },
      {
        name: 'prompt',
        message:
          'Tauri 2 WebView2 disables window.prompt. Use plugin-dialog equivalents instead. See docs/ui-interaction-spec.md §1.3.',
      },
    ],
    'no-restricted-properties': [
      'error',
      {
        object: 'window',
        property: 'confirm',
        message:
          'Tauri 2 WebView2 disables window.confirm. Use `import { ask } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
      },
      {
        object: 'window',
        property: 'alert',
        message:
          'Tauri 2 WebView2 disables window.alert. Use `import { message } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
      },
      {
        object: 'window',
        property: 'prompt',
        message:
          'Tauri 2 WebView2 disables window.prompt. Use plugin-dialog equivalents instead. See docs/ui-interaction-spec.md §1.3.',
      },
    ],
  },
},
```

採用理由:

- **bare global 経路** (`confirm()`) と **member access 経路** (`window.confirm()`) は ESLint で別 rule の管轄になる (`no-restricted-globals` は前者、`no-restricted-properties` は後者)。Tauri 2 silent loss は両経路で発生するため両方を block する必要あり
- `no-restricted-properties` の object: `window` 指定で false positive を回避 (`document.confirm` 等は対象外、Tauri 2 の制約は `window.confirm` のみ)
- error message に「代替 API import 文」+「docs link」の両方を含めるのは issue 受け入れ条件 2/5 への直接対応

### 4.2 `docs/ui-interaction-spec.md` §1.3 末尾追加段落

§1.3 のアンチパターン段落 (現行 line 64) の直後に新規パラグラフを追加:

```markdown
**lint 強制 ([#643](https://github.com/Idios/kobutachan-allaganeye/issues/643))**: 上記 canonical 違反 (`window.confirm` / `window.alert` / `window.prompt` の bare 呼び出しおよび `window.X` 経由 member access) は `gui/eslint.config.js` の `no-restricted-globals` + `no-restricted-properties` で **error として block** する。`npm run lint` / CI gui-frontend job が fail し、IDE 上でも即時警告される。エラーメッセージに plugin-dialog 代替 API へのリンクを含める。
```

### 4.3 受け入れ条件マッピング (Iron Law 1 担保)

| issue 受け入れ条件 | この設計で対応する箇所 |
| --- | --- |
| `gui/eslint.config.js` (or 等価) に `no-restricted-globals` 相当の rule 追加 | §4.1 patch の `no-restricted-globals` block |
| エラーメッセージに plugin-dialog 代替 API + `docs/ui-interaction-spec.md` §1.3 リンクを含める | §4.1 各 rule の `message` field に「Use `import { ... } from "@tauri-apps/plugin-dialog"`」+ 「See docs/ui-interaction-spec.md §1.3」を含む |
| 故意に `window.confirm` を含むコードを書いた branch で CI lint が fail することを確認 | §6.2 の「ESLint 違反検証 PR」フロー (検証 PR の CI run URL を本流 PR の Self-Test Report に machine-verified として記録) |
| CI grep check を併設するか判断 (ESLint で十分なら不要) | **判断: 不要**。理由: ESLint rule は IDE 警告 + CI fail の双方を兼ね、`grep` は コメント / docstring 内の言及まで誤検出する (現状 `gui/src/screens/PreviewScreen.tsx:445` と `gui/src/components/RestoreButton.tsx:9` の説明コメント内 `window.confirm` がそれにあたる) |
| `docs/ui-interaction-spec.md` §1.3 末尾に「lint で強制」記述を追加 | §4.2 の追加段落 |

## §5 章 2: #365 CLI progress bar ETA ラベル

### 5.1 `_ETAProgressBar` subclass 実装

`allaganeye/commands/split_matches.py` の `_eta_progressbar` を click.ProgressBar subclass + override 方式に refactor:

実装は `from click._termui_impl import ProgressBar as _ClickProgressBar` 経由で `_ClickProgressBar` alias として import (`click.ProgressBar` は click 8.x の public API として export されていないため)。

```python
class _ETAProgressBar(_ClickProgressBar):
    """Progress bar with explicit 'ETA: H:MM:SS' label (#365).

    click のデフォルト ``%(info)s`` placeholder は ``<percent>  <eta>``
    をラベルなしで展開するだけのため、ユーザーには時刻文字列だけが見え、
    経過時間/残り時間/動画内位置のどれか判別できない (#329 元 issue,
    PR #343 不完全修正、#365 で再対応)。

    本 subclass は ``format_progress_line`` を override し以下に統一:

        Detecting  ###################---  93% ETA: 00:00:22

    ``show_eta=False`` (GPU mode #438 の ``suppress_click_eta=True``
    経路) では ETA セクションを出さず percent のみ表示。caller 側が
    self-computed ETA を label に組み込む既存挙動と互換。

    依存する `click._termui_impl` module の `ProgressBar` class が提供するメソッド (click 8.x の internal だが API surface は安定):
      - ``format_bar()``    -- bar 文字列
      - ``format_pct()``    -- "  N%" or "NN%" (左 padding あり)
      - ``format_eta()``    -- "H:MM:SS" or "" (eta_known=False / show_eta=False のとき空)
      - ``self.label``      -- ljust 済みラベル
      - ``self.show_eta``   -- ETA 表示フラグ
      - ``self.eta_known``  -- ETA 計算可能フラグ (1 update 後に True)
    """

    def format_progress_line(self) -> str:
        bar = self.format_bar()
        pct = self.format_pct()
        if self.show_eta and self.eta_known:
            eta = self.format_eta()
            return f"{self.label}{bar} {pct} ETA: {eta}"
        return f"{self.label}{bar} {pct}"


def _eta_progressbar(
    length: int, label: str, *, suppress_click_eta: bool = False
) -> _ETAProgressBar:
    """Create a progress bar with explicit ETA label (#329 / #365).

    Labels are left-justified to ``_PROGRESS_LABEL_WIDTH`` so that
    Detecting / Refining / Scorebar / Splitting bars align vertically.

    When ``suppress_click_eta`` is True (GPU mode, #438), click's own
    ETA is hidden (``show_eta=False``); caller supplies a self-computed
    ETA in the label instead. ``_ETAProgressBar.format_progress_line``
    consumes ``show_eta`` to skip the 'ETA: ' tail in that path.
    """
    return _ETAProgressBar(
        iterable=None,
        length=length,
        label=label.ljust(_PROGRESS_LABEL_WIDTH),
        bar_template="",  # 未使用 (format_progress_line を override したため)
        show_eta=not suppress_click_eta,
        show_percent=True,
    )
```

### 5.2 click 8.x の public API 依存リスク

- `format_progress_line` / `format_bar` / `format_pct` / `format_eta` は click 8.0 〜 8.2 で signature 変更なし
- `self.eta_known` / `self.show_eta` 属性も同期間で stable
- `pyproject.toml` に明示的な click pin は無く、typer (本 project の dependency) 経由依存。typer 0.9+ は click 8.x を要求するため major upgrade は typer 側 release で同期される
- → **本 PR では click 上限 pin を追加しない**。代わりに §6.1 の unit test (4 parametrize) が click upgrade 時の API 互換性 regression を即座に検出する

### 5.3 4 bar の format 統一確認

| caller | 該当行 | bar instance | label | 期待 line (format 統一の確認、ETA 値は例) |
| --- | --- | --- | --- | --- |
| `_run_detection_with_refine_bar` | `split_matches.py:810` | `_eta_progressbar(total, "Detecting")` | `"Detecting "` | `Detecting  #####---  50% ETA: 00:00:10` |
| `_run_refine_progress` | `split_matches.py:898` | `_eta_progressbar(total, "Refining")` | `"Refining  "` | `Refining   #####---  50% ETA: 00:00:10` |
| `_run_scorebar_filter` | `split_matches.py:922` | `_eta_progressbar(total, "Scorebar")` | `"Scorebar  "` | `Scorebar   #####---  50% ETA: 00:00:10` |
| `_split_and_write_metadata` | `split_matches.py:1130` | `_eta_progressbar(total, "Splitting")` | `"Splitting "` | `Splitting  #####---  50% ETA: 00:00:10` |

`_PROGRESS_LABEL_WIDTH` の ljust によって 4 bar 共通幅で揃う。実際の ETA 値は各 phase の処理量・経過時間によって異なるが、`<label><bar> NN% ETA: H:MM:SS` という format は 4 bar 共通。

### 5.4 GPU mode (`suppress_click_eta=True`) 互換性

- GPU 経路 (`gpu_detector.py` 連動) は `_eta_progressbar(total, label, suppress_click_eta=True)` を呼ぶ (PR [#438](https://github.com/Idios/kobutachan-allaganeye/pull/438))
- caller 側で chunk 完了率から ETA を手計算し、`progress.label = f"... ETA: {fmt}"` のように label に組み込む既存実装
- 新 `_ETAProgressBar` は `show_eta=False` 時に ETA tail を出さないため、caller が label に push 済みの ETA と二重表示にならない
- 実装時に `gpu_detector.py` 連動箇所と既存 GPU mode の出力 format を読み合わせ、回帰しないことを §6.1 の test `test_eta_progressbar_suppresses_eta_in_gpu_mode` で実証

### 5.5 受け入れ条件マッピング (Iron Law 1 担保)

issue [#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) には明示的な `## 受け入れ条件` セクションが無く、「期待動作」と「根本原因分析」セクションが実質的な受け入れ基準。逐条マッピング:

| issue 期待動作 / 根本原因対応 | この設計で対応する箇所 |
| --- | --- |
| 期待動作: `Detecting ####---  93% ETA: 00:00:22` 形式 | §5.1 `_ETAProgressBar.format_progress_line` で `f"{self.label}{bar} {pct} ETA: {eta}"` |
| 影響範囲全 4 bar (`Detecting`, `Refining`, `Scorebar`, `Splitting`) | §5.3 表で `_eta_progressbar` の戻り型を `_ETAProgressBar` に変えるだけで全 caller が新 format を享受 |
| 直接原因 (`%(info)s` でラベルなし展開) の解消 | §5.1 で `bar_template=""` + `format_progress_line` override により click の組み込み templating を bypass |
| 検出漏れ (PR #343 のテスト不足) の再発防止 | §6.1 で `format_progress_line()` の出力に対する parametrize test (4 bar) + regex 一致 + GPU mode 経路 test を追加 |

## §6 Testing / Verification

### 6.1 #365 unit test (`tests/test_split_matches.py` に追加)

```python
import re
import time
import pytest

from allaganeye.commands.split_matches import (
    _ETAProgressBar,
    _eta_progressbar,
    _PROGRESS_LABEL_WIDTH,
)

_ETA_LINE_PATTERN = re.compile(r"\b\d{1,3}%\s+ETA:\s+(?:\d+d\s+)?\d+:\d{2}:\d{2}\b")


def _drive_to_known_eta(bar: _ETAProgressBar, completed: int) -> None:
    """Force eta_known by simulating elapsed time + progress.

    click ProgressBar は ``start`` / ``last_eta`` が None / update 未実行の間
    ``eta_known=False`` のまま 'ETA: --' 相当を出す。テストでは過去
    timestamp + update() で eta_known=True を満たす。
    """
    past = time.time() - 10.0
    bar.start = past
    bar.last_eta = past
    bar.update(completed)


@pytest.mark.parametrize(
    "label", ["Detecting", "Refining", "Scorebar", "Splitting"]
)
def test_eta_progressbar_label_present_for_all_bars(label):
    """4 bar 全てで 'ETA: H:MM:SS' label を出すこと (#365)."""
    bar = _eta_progressbar(100, label)
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    assert line.startswith(label.ljust(_PROGRESS_LABEL_WIDTH))
    assert "ETA: " in line, f"missing 'ETA: ' label in: {line!r}"
    assert _ETA_LINE_PATTERN.search(line), f"format mismatch: {line!r}"


def test_eta_progressbar_suppresses_eta_in_gpu_mode():
    """suppress_click_eta=True (GPU mode #438) では ETA tail を出さず percent のみ."""
    bar = _eta_progressbar(100, "Detecting", suppress_click_eta=True)
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    assert "ETA: " not in line
    assert re.search(r"\b\d{1,3}%\s*$", line.rstrip()), line


def test_eta_progressbar_no_eta_before_first_update():
    """update 前 (eta_known=False) は ETA tail を出さず percent のみ."""
    bar = _eta_progressbar(100, "Detecting")

    line = bar.format_progress_line()

    assert "ETA: " not in line
    assert "0%" in line
```

**狙い**:

- 4 bar parametrize で「全 caller で format 統一」を 1 test で担保
- regex `\b\d{1,3}%\s+ETA:\s+(?:\d+d\s+)?\d+:\d{2}:\d{2}\b` で **`93% ETA: 00:00:22` 完全形を検証** (`Nd HH:MM:SS` 形式 / 日付なし `HH:MM:SS` 形式 どちらにも対応、PR #343 の test 不足の根本原因対策)
- GPU mode 経路 (suppress_click_eta=True) を独立 test で担保 → #438 既存挙動の互換性
- update 前 (eta_known=False) を test して click upgrade での挙動変化を早期検知

### 6.2 #643 ESLint 違反検証 PR (CI fail evidence)

ESLint config の自動 test 化はせず、**違反コードを含む検証 PR を 1 度立てて CI が fail することを CI run URL の machine-verified evidence として記録** する。Idios 実機 `npm run lint` 手動確認は不要。

**フロー**:

1. メイン PR #1 (`Refs #643`) を立てて CI 全 PASS を確認 (= 既存 src/ は新 rule で fail しない)
2. 別 branch `claude/musing-davinci-38136f-eslint-verify` を切り、メイン PR #1 のコミット + 違反コード追加 commit を載せる:

   ```tsx
   // gui/src/__verify_eslint_643__.tsx
   export function _verify() {
     confirm("bare global");
     window.confirm("member access");
     alert("bare alert");
     window.alert("member alert");
     prompt("bare prompt");
     window.prompt("member prompt");
   }
   ```

3. 検証 PR を立てる: タイトル `test: verify ESLint blocks Tauri 2 silent loss patterns (Refs #643, expected to fail CI)`、本文に「**この PR は CI fail evidence のための検証専用、merge せず close する**」を明記
4. CI gui-frontend lint job が exit 1 + 6 違反 (3 globals + 3 properties) を報告することを確認
5. 検証 PR を **close without merge** (実装は本流 PR #1 で merge)
6. メイン PR #1 の Self-Test Report に「Verification PR #XXX (closed without merge): CI run YYY confirms 6 violations blocked」を **machine-verified** として記録

### 6.3 既存テスト回帰確認

- `tests/test_split_matches.py` の既存 43 test は context manager protocol (`with bar as progress: progress.update(1)`) のみ依存。`_eta_progressbar` の戻り型を `_ETAProgressBar` (click.ProgressBar subclass) に変えても context manager protocol (`with bar as progress: progress.update(1)`) は維持される。ただし `click.progressbar` factory を直接 monkeypatch している既存 test (test_split_matches.py 内 6 件) は `_ETAProgressBar` への patch 対象変更が必要 (PR #687 で `patch("click.progressbar")` → `patch(f"{MODULE}._ETAProgressBar")` に更新)。
- 実装時に `grep -n 'click.progressbar' tests/` を走らせ、`click.progressbar` を直接 monkeypatch する箇所が無いか確認
- `tests/test_regression_330.py` (進捗バー regression test) と `tests/test_progress_emitter.py` も影響範囲として実装時に走査

### 6.4 CI 統合

| job | 既存で走るか | 本 PR の追加 |
| --- | --- | --- |
| `pytest` (`.github/workflows/python.yml`) | ✓ | §6.1 の新 4 test を自動 pickup |
| `npm run lint` (gui-frontend job) | ✓ | §4.1 の新 rule を自動適用 (既存 src/ は全 PASS 想定、§6.2 検証 PR で違反コード時の fail evidence 取得) |
| `ruff check` / `ruff format --check` / `pyright` | ✓ | 影響なし |

→ **CI yaml の変更は不要**。

### 6.5 Self-Test Report (両 PR 本文用テンプレ)

**PR #1 (Refs #643)**:

```markdown
## Self-Test Report

### machine-verified
- [x] cd gui && npm run lint (新 rule で gui/src/ 全 PASS)
- [x] cd gui && npm run typecheck
- [x] cd gui && npm test
- [x] cd gui && npm run build
- [x] cd gui/src-tauri && cargo check
- [x] 違反コード検証 PR #XXX (closed without merge): CI run URL で
      no-restricted-globals 3 件 + no-restricted-properties 3 件
      = 計 6 violation を block することを確認

### machine-unverifiable
(なし)
```

**PR #2 (Refs #365)**:

```markdown
## Self-Test Report

### machine-verified
- [x] pytest tests/test_split_matches.py (§6.1 新 4 test 含む全 PASS)
- [x] pytest -m "not slow and not baseline_regen" (regression 確認)
- [x] ruff check . / ruff format --check .
- [x] pyright

### machine-unverifiable (Idios 実機)
- 短い sample 動画で `allaganeye split <v> --dry-run` 実行 → 4 bar 全てに 'ETA: H:MM:SS' 表示
- `--gpu` で ETA 二重表示なし (GPU mode #438 互換確認)
- 既存 metadata.json と diff なし
```

### 6.6 実機検証依頼 (Iron Law 6 AskUserQuestion)

PR #1 (#643): **依頼不要** (§6.2 の検証 PR フローで machine-verified evidence 取得)。

PR #2 (#365) 作成時に AskUserQuestion で実機表示確認を依頼:

```text
PR #2 (#365 ETA label) は CLI 進捗表示の format 変更です。検知ロジック
不変ですが、4 bar の表示確認は機械化できないため Idios 実機を依頼します。

実機検証項目:
(a) 短い sample 動画で `allaganeye split <video> --dry-run` 実行
    → Detecting / Refining / Scorebar / Splitting 4 bar 全てに
      'ETA: H:MM:SS' が表示されること
(b) GPU mode (--gpu) で同 sample 動画 → ETA 二重表示が起きないこと
(c) 既存 metadata.json と diff なし (検知ロジック regression なし)
```

## §7 着手順序 / 実装 lane

### 7.1 推奨着手順

```text
T+0: 章 1 branch (claude/musing-davinci-38136f-eslint) を切る
     - gui/eslint.config.js patch + docs/ui-interaction-spec.md §1.3 追記
     - ローカル npm run lint / typecheck / test / build / cargo check 全 PASS 確認
     - PR #1 (Refs #643) を develop-0.2.0 base で立てる

T+1: 章 1 検証 branch (claude/musing-davinci-38136f-eslint-verify) を切る
     - gui/src/__verify_eslint_643__.tsx を追加
     - 検証 PR を立てて CI fail (6 violations) を確認 → close without merge
     - 検証 PR の CI run URL を PR #1 Self-Test Report に追記

T+2: 章 2 branch (claude/musing-davinci-38136f-progress-bar) を切る
     - allaganeye/commands/split_matches.py に _ETAProgressBar 追加
     - tests/test_split_matches.py に §6.1 新 4 test 追加
     - ローカル pytest / ruff / pyright 全 PASS 確認
     - PR #2 (Refs #365) を develop-0.2.0 base で立てる
     - AskUserQuestion で Idios 実機表示確認を依頼

T+3: PR #1 / PR #2 を /review-pr → 受け入れ条件 + 摘出課題確認 → merge
     → /close-issue で #643 / #365 を base ブランチでの実測再検証後 close
```

### 7.2 並行運用注意点 (`docs/l2-workflow.md` §PR 作成 Pre-flight 適用)

各 PR 作成前:

- `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit を確認
- 当 PR の touched files (章 1 = `gui/eslint.config.js` / `docs/ui-interaction-spec.md`、章 2 = `allaganeye/commands/split_matches.py` / `tests/test_split_matches.py`) と未済 commit の touched files が交差するなら `git merge origin/develop-0.2.0` で取り込み + 自動チェック再実行
- `gh pr list --search "643 in:title,body" --state all` / `gh pr list --search "365 in:title,body" --state all` で並行 worktree PR 重複確認

### 7.3 関連 doc

- `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` — Group H 全体位置付け / wave 0 lane 配置
- `docs/l2-workflow.md` — PR Pre-flight / Self-Test Report / 実機検証 trigger
- `docs/ui-interaction-spec.md` §1.3 — Tauri 2 silent loss canonical 規定 (本 spec で「lint 強制」段落を追加)
- `allaganeye/commands/split_matches.py:1070-1089` — 既存 `_eta_progressbar` (本 spec で `_ETAProgressBar` subclass に refactor)
- `gui/eslint.config.js` — 既存 flat config (本 spec で `no-restricted-globals` + `no-restricted-properties` rule を追加)

### 7.4 close-issue ハンドオフ

PR #1 / PR #2 merge 後、`/close-issue` skill で以下を実測再検証してから close:

- #643: develop-0.2.0 base でメイン PR #1 commit を取り込んだ状態で `npm run lint` PASS、検証 PR の CI fail evidence URL を close コメントに転記
- #365: develop-0.2.0 base で `pytest tests/test_split_matches.py` の §6.1 新 test PASS + 短い動画で実機 4 bar 表示確認を Idios に最終確認
