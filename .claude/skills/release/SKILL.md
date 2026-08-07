---
name: release
description: deferred issue レビュー → バージョンバンプ → リリース PR 作成 → タグ打ち直前の CHANGELOG 見出し日付確定 を自動化する
---

# リリーススキル

バージョンバンプとリリース PR を作成します。

## 引数

`$ARGUMENTS` にバージョン種別を指定（省略時は自動判定）:

- `patch`: バグ修正のみ
- `minor`: 新機能追加
- `major`: 破壊的変更

自動判定ルール（引数省略時）: 前回タグ以降のコミット prefix から判定。`feat:` / `feat(...)` があれば minor、`!` または `BREAKING CHANGE` があれば major、それ以外（`fix` / `docs` / `refactor` / `chore` / `test` のみ）は patch。判断が曖昧な場合はユーザーに確認する。

## 手順

### Step 0a: リリース受け入れゲートの確認（必須）

リリース PR を作成する前に、[`docs/release-process.md` §レイヤーリリース受け入れゲート](../../../docs/release-process.md) のチェックリストを全件達成しているか確認する。本ステップはスキップできない。

1. 対象バージョン (例 `v0.2.0`) を特定し、§共通項目 + §`v0.x.0` (L?) 固有項目 の 2 ブロックをユーザーに提示
   - **patch release には対応するレイヤー固有ブロックが存在しない**（固有項目は minor の `v0.x.0` 単位でしか定義されない）。その場合は §共通項目 のみを提示し、「レイヤー固有項目は該当なし（patch release のため）」と**明示**する。黙って 1 ブロックだけ出して済ませない
   - §共通項目 は minor / patch の**両方**に適用される（裁定 D5）。patch だからと本ゲートごと省略しない
2. 各項目について「達成 / 未達成 / 該当なし」を 1 件ずつ確認 (3 件以上の bulk 確認になる場合はサンプル提示 + 全件 OK / 個別調整 / 中止 の 3 択)
3. 1 件でも未達成があれば本スキルは中断し、ユーザーに残タスクの優先処理を依頼
4. 全件達成を確認してから Step 0b へ進む

注意: 本ゲートは Iron Law 1 (受け入れ条件全充足) のリリースレベル展開。`deferred` review (Step 0b / 0c) はゲート §共通項目内の 1 行に対応するため、Step 0b / 0c はゲート確認の延長として扱う。

### Step 0b: deferred 全件取得 (M9、F8 教訓)

リリース前に `deferred` ラベル付き issue を全件取得する。**release-blocker label は新設しない** (M8 撤回、2026-05-17 確定) — 取得対象は `deferred` 単独で十分。

```bash
gh issue list --repo Idios/kobutachan-allaganeye --state open --label "deferred" --limit 200 \
  --json number,title,labels,createdAt,updatedAt
```

- 件数 0 → deferred 分類 (Step 0c) は skip。ただし **Step 0c-2 の not_planned 残タスク確認** (リリース区間ベース、deferred 件数と独立) は必ず実施してから Step 2 へ進む (本文鮮度は対象 deferred が無いため skip 可)
- 件数 ≥1 → **Step 0c-2 (本文鮮度 + not_planned) を実施後**、Step 0c で全件分類

### Step 0c: deferred 1 件ずつ 3 択分類 (M9 再設計版)

Step 0b で取得した各 deferred issue について、AskUserQuestion で以下 3 択を user に提示:

- **(a) 次 release で吸収**: 本 release / 次 patch の **Track B 吸収候補** とする。spec PR (Track 0) の table に記録
- **(b) deferred 継続**: ラベル変更なし。本 release では取り込まない (次 cycle に再評価)
- **(c) close**: `gh issue close <番号> --comment "<理由>"` でクローズ (won't fix / 再現不能 / 仕様変更等)

#### bulk 件数の運用 (Iron Law 2 整合)

- 件数 ≤2: 1 件ずつ AskUserQuestion で個別確認
- 件数 ≥3: **先に Iron Law 2 bulk pre-check** (サンプル 1 件提示 + 「全件 OK (= 全件 (b) deferred 継続) / 個別調整 / やめる」3 択)
- 「全件 OK」選択時の挙動 (B-2/B-3 fix): **全件を (b) deferred 継続として処置**し、Step 0c table の分類列を全件 `(b) deferred 継続` で埋める。「全件 (a) 次 release 吸収」と読み違えやすいため pre-check の選択肢 description で「(b) 継続」を明示する規約とする。「全件 (a) 次 release 吸収」を意図する場合は user が `Other` で明示する
- 「個別調整」選択時のみ 1 件ずつの確認に進む

#### Step 0c 結果の spec PR table 化 (Track 0)

(a) / (b) / (c) 各分類結果を spec PR (Track 0、`docs/superpowers/specs/<date>-v0.M.N+1-patch-design.md`) の §deferred 全件検証結果 table に保存:

```markdown
### §deferred 全件検証結果 (`/release` Step 0c)

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #374 | ... | (a) 次 patch 吸収 | UX critical |
| #432 | ... | (b) deferred 継続 | L3 scope |
| #555 | ... | (c) close | 再現不能 |
```

(a) と分類された issue 群が [`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造) の **Track B 吸収候補** となる。Track B PR は本 spec PR の table をリンクで引く。

#### Step 0c で block する条件 (release PR 作成前 gate)

- deferred 件数 > 0 かつ Step 0c の確認が完了していない → release PR 作成を block (本 skill が abort)
- (a) 分類 issue 群が次 release scope に取り込まれる commit / PR plan を持たない → block (`/iterate-review` / `/create-task` で Track B PR の plan を先に作る)

F8 (deferred 持ち越し: #374 / #458 / #743 / #749 / #756 が v0.2.1 まで漏れた事例) の根本対策。

#### Step 0c-2: deferred 本文鮮度 + not_planned 残タスク確認 (#817 / audit P2-39)

**実行順序**: 本確認は Step 0c の分類 (bulk pre-check 含む) の**前に**実施する。bulk pre-check で「全件 OK (= 全件 (b) 継続)」を選ぶ場合も省略しない (古い本文・orphan 残タスクのまま継続するのを防ぐのが目的のため)。なお **本文鮮度** は各 deferred issue 単位のため deferred 0 件時はスキップ可だが、**not_planned 残タスク** はリリース区間ベース (deferred 件数と独立) のため deferred 0 件でも必ず実施する。

以下 2 点を確認する (closed 側から open 側への参照切れの構造的検出):

- **本文鮮度**: 各 deferred issue の本文と直近コメントを、関連 spec / design doc と突合する。本文が現状の実装・方針と矛盾 (鮮度切れ) している場合は、分類前に `gh issue edit <番号>` での本文更新を提案する (古い前提のまま (b) 継続すると次 cycle も腐り続けるため、#753「親 issue 本文が腐る」と同型の予防)
- **not_planned 残タスク**: リリース区間 (前タグ〜HEAD) の commit / doc が参照する issue 番号のうち、コード/doc 内マーカー (`wired in #N` / `Refs #N` / `TODO(#N)` 等) が指す `#N` が **not_planned で close** されている場合、その残タスクの行き先 (再起票要否) を確認する (#762 が not_planned close されて残タスクが orphan 化した事例)。行き先が無ければ `/create-task` 起票を提案。マーカー探索の具体例:

  ```bash
  # リリース区間の diff から issue 参照マーカーを抽出
  git log <前タグ>..HEAD -p -- '*.py' '*.md' '*.rs' '*.ts' | grep -oE '(wired in|Refs|TODO\() ?#[0-9]+'
  # 抽出した各 #N の close 理由を確認 (not_planned を検出)
  gh issue view <N> --json state,stateReason --jq '"\(.state) \(.stateReason)"'
  ```

### Step 2: リリース準備

1. 現在のバージョンを `pyproject.toml` から取得
2. 前回リリースタグ以降のコミットを分析:

   ```bash
   git log $(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~50")..HEAD --oneline
   ```

3. バージョン種別を決定（引数指定 or 上記「自動判定ルール」）
4. **分岐元ブランチ**と**リリース PR の宛先 (`--base`)** を分けて特定する。**この 2 つは同じとは限らない**:

   | 種別 | 分岐元 (`release/v<新バージョン>` をここから切る) | リリース PR の `--base` |
   | --- | --- | --- |
   | minor / major | `develop-<新バージョン>`（既存 develop ブランチ） | **`main`** |
   | patch | `develop-<新バージョン>` があればそこ、無ければ `main` | 分岐元と同じ |

   - 実例 (minor): v0.3.0 = PR [#924](https://github.com/Idios/kobutachan-allaganeye/pull/924) は head=`release/v0.3.0` / **base=`main`**、分岐元は `develop-0.3.0`。**`--base` に分岐元をそのまま渡すと、リリース PR が `main` ではなく develop を向く**
   - 実例 (patch): v0.2.1 はバンプを `develop-0.2.1` に載せ、その後 `develop-0.2.1 → main` のリリース PR ([#774](https://github.com/Idios/kobutachan-allaganeye/pull/774)) を別途出している
   - 判断が曖昧な場合は `git branch -r | grep -E 'origin/develop-|origin/main'` の結果を提示してユーザー確認

   > **`develop-<次バージョン>` を切るタイミング** (#918 item1): ここで指す `develop-<新バージョン>` は**今リリースするバージョンの開発統合先**であり、**既に存在している**ブランチである。本スキルが新規作成することはない。
   >
   > *次*のバージョン用の `develop-<次バージョン>` は、**タグ打ちと GitHub Release 作成が完了した後**に `main` から切る（[`docs/release-process.md`](../../../docs/release-process.md) §レイヤー間の移行手順 の 5、§ルール の 4）。リリース PR を `main` へマージする前でも、タグを打つ前でもない。切った直後に[バージョン保持箇所](../../../docs/versioning.md)を全箇所まとめて次バージョンへ更新する。

### Step 3: バージョンバンプと PR 作成

1. **事前品質チェック** ([`docs/l2-workflow.md`](../../../docs/l2-workflow.md) §「PR 作成 path 別自動チェック」):

   ```bash
   ruff check .
   ruff format --check .
   pytest
   pyright
   ```

   いずれか失敗したら修正してから以下に進む
2. [`docs/versioning.md`](../../../docs/versioning.md) §バージョン管理場所 に挙がっている**全フィールド**の version を新バージョンへ更新する（フィールド一覧の機械可読な正は [`scripts/check_version_consistency.py`](../../../scripts/check_version_consistency.py) の `VERSION_LOCATIONS`、#911）。1 ファイルが複数フィールドを持つことがある（ファイル数 < フィールド数）ので、ファイル単位で数えて満足しないこと。lockfile (`gui/package-lock.json` / `gui/src-tauri/Cargo.lock`) は **該当フィールドの直接編集を既定**とする（バンプでは version 以外を動かさないため。依存そのものを更新したい場合はパッケージマネージャを使い、バンプとは別コミットに分ける）。このとき**旧バージョン文字列の一括置換はしない** — lockfile には依存由来の部分一致（`0.3.0` に対する `30.3.0` 等）が多数あり誤爆する。該当フィールドの行だけをピンポイントで直す。更新できたら必ず検証する:

   ```bash
   python scripts/check_version_consistency.py --tag v<新バージョン>
   ```

   exit 0 でなければ先に進まない（exit 1 = フィールド間 or tag との不一致 / exit 2 = 検査自体の構造エラー）。`release.yml` の `version-check` job が tag push 時に同じスクリプトで同じ判定を行うため、ここを飛ばすとリリース当日に fail する。`--tag` は**期待値の文字列**を渡すだけで、git tag が既に存在する必要はない（タグ打ちは本スキル範囲外の後工程）

   > 更新対象を `grep -r '<旧バージョン>' --include='*.py' --include='*.toml' --include='*.json'` で拾う旧手順は使わない。`Cargo.lock` のように上記 glob のどれにも載らない保持ファイルがあり、取りこぼす（#817 / audit P2-33 の手順を #911 で置換）

3. リリースブランチを作成（Step 2-4 の表の**分岐元**から分岐。PR の `--base` とは別物なので取り違えない）:

   ```bash
   git checkout <分岐元ブランチ>
   git pull
   git checkout -b release/v<新バージョン>
   ```

4. 変更をコミット（session-id を含める、[`docs/l2-workflow.md`](../../../docs/l2-workflow.md) §「PR 規約」 §「コミットメッセージ session-id」）:

   ```bash
   # バージョンを保持する「全ファイル」を stage する。path は手で列挙せず
   # --list-paths から得る (VERSION_LOCATIONS が正なので、保持先が増えても
   # 取りこぼさない)。--list-paths は path を重複なしで返すので、出力行数は
   # フィールド数ではなくファイル数になる (1 ファイル 2 フィールドの箇所がある)。
   # pyproject.toml だけを stage して他を置き去りにすると
   # release.yml の version-check job が fail する (#911)。
   # git add は cwd 側の repo に効くので、Step 3-2 でバンプしたのと同じツリーを
   # cwd にすること (worktree 作業中なら worktree root)。--list-paths の出力自体は
   # repo root 相対の固定文字列で cwd には依存しない
   git add -- $(python scripts/check_version_consistency.py --list-paths)
   git commit -m "chore: bump version to <新バージョン> [<session-id>]"

   # commit 後に stage 漏れを検出する。合格条件 = 出力に「バージョン保持ファイルが
   # 1 つも現れない」こと。出力が空である必要はない (他ファイルの残留は可)
   git status --short
   ```

   バージョン保持ファイル以外の差分（Step 3-1 で直した lint 等）が残っている場合は、
   バンプと混ぜず別コミットに分ける（このコミットは version bump 単独に保つ）

5. リリースブランチを push:

   ```bash
   git push -u origin release/v<新バージョン>
   ```

6. リリース PR を作成（`--base` は Step 2-4 の表の**リリース PR の宛先**。minor / major では **`main`** であって分岐元の develop ではない。Windows + Git Bash での日本語本文破損回避のため `printf | --body-file -` 方式）:

    ```bash
    printf '%s\n' "## Release v<新バージョン>

    ### 変更内容
    <コミット分析結果のサマリー>

    ### deferred issue レビュー結果
    <Step 0c の 3 択分類結果を記載>

    ### チェックリスト
    - [ ] バージョン保持フィールドが全て一致 (\`python scripts/check_version_consistency.py --tag v<新バージョン>\` が exit 0)
    - [ ] 全テスト通過 (\`pytest\`, \`ruff check .\`, \`ruff format --check .\`, \`pyright\`)
    - [ ] deferred issue を全件レビュー済み
    - [ ] CLAUDE.md の更新が必要な変更はない

    作成: <session-id>" | gh pr create \
      --title "Release v<新バージョン>" \
      --body-file - \
      --base <リリース PR の宛先> \
      --label "release" \
      --assignee Idios
    ```

7. ユーザーに PR URL とバージョン変更内容を報告

### Step 4: CHANGELOG 見出し日付をタグ打ち日に合わせる（タグ打ちの直前、必須）

`CHANGELOG.md` の対象バージョン見出しは `## [<新バージョン>] - YYYY-MM-DD` の形をとり、**日付 = そのタグを打つ日 (JST)** とする（[`docs/release-process.md`](../../../docs/release-process.md) §タグ運用、裁定 D6 / #948）。リリース PR の作成からタグ打ちまでは日を跨ぐことがある（v0.3.0 では見出し日付が 2 回書き換わった）ため、**タグを打つ当日に**見出し日付を確認・更新して commit する。

1. `CHANGELOG.md` の `## [<新バージョン>] - ...` の日付を**当日の JST 日付**へ直す。**既にリリース済みのバージョン節は触らない**（裁定 D7）
2. 検査してから commit する:

   ```bash
   # 基準日はローカル時刻を offset 付き ISO8601 で渡す（スクリプトが Asia/Tokyo へ変換する）。
   python scripts/check_version_consistency.py --tag v<新バージョン> \
     --changelog-date-from "$(python -c 'import datetime; print(datetime.datetime.now().astimezone().isoformat())')"

   git add -- CHANGELOG.md
   git commit -m "docs: set CHANGELOG date for v<新バージョン> [<session-id>]"
   ```

   exit 0 でなければタグを打たない（exit 1 = 見出し日付 / バンプ方向の不一致、exit 2 = 検査自体の構造エラー）。**同じ検査を `release.yml` の `version-check` job がタグ push 時に実行する**ため、ここを飛ばすと*タグを打った後に*赤くなり、タグの打ち直しが必要になる

**この commit をどこへ載せるか**: **リリース PR の head ブランチ（`release/v<新バージョン>`）へ直接 commit / push する。日付のためだけの新しい PR は作らない。** リリース PR はまだマージ前なので、この commit は同じ PR に乗って Step 2-4 で決めた**宛先**へ渡る（minor / major なら `main`。patch で `develop-<新バージョン>` を経由する場合はまずそこへ渡り、後続の `develop-<新バージョン> → main` PR で `main` に載る）。**宛先の名前は Step 2-4 の表が正**で、ここの記述で上書きしない。

> **実行順序の制約**: Step 4 は**リリース PR をマージする前**に実行する。`main` は保護ブランチ（`release/vX.Y.Z → main` のマージのみ受け付ける、[`docs/release-process.md`](../../../docs/release-process.md) §ルール 1）なので、マージ後に日付だけ直そうとしても直接 commit できない。**Step 4 → リリース PR マージ → タグ打ちを同じ JST 日のうちに終える**のが正しい順序で、v0.3.0 もこの順で確定させている。
>
> なお基準日を省いた `python scripts/check_version_consistency.py --tag v<新バージョン>` は、日付欄の**存在**しか見ない（値は比較しない）。Step 3 のバンプ時点ではタグを打つ日が未確定なので、そちらでは省略形で構わない。

### タグ打ち・GitHub Release 作成

リリース PR マージ後の手順（本スキル範囲外、`docs/release-process.md` §タグ運用 を参照）:

- patch リリース: マージされたブランチで `git tag -a v<新バージョン> -m "Release v<新バージョン>: <概要>"` → `git push origin v<新バージョン>`
- minor/major リリース: `develop-<新バージョン>` を `main` にマージしてから `main` でタグ打ち
- **annotated tag（`-a`）で打つ**。`version-check` job は CHANGELOG 見出し日付の基準日として annotated tag の `taggerdate` を第一候補に読む
- **GitHub Release は `git push origin v<新バージョン>` で [`release.yml`](../../../.github/workflows/release.yml) が自動作成する**。本文は [`scripts/extract_release_notes.py`](../../../scripts/extract_release_notes.py) が CHANGELOG.md の該当セクションから抽出し、Portable ZIP も自動添付される
  - 手動で `gh release create ... --notes-from-tag` を叩かない（#918 item4）。Release が二重作成されるうえ、`--notes-from-tag` はタグメッセージを本文にするため CHANGELOG の内容が反映されない
  - CI 障害等で手動作成が必要な場合のみ、[`docs/release-process.md`](../../../docs/release-process.md) §手動リリース手順 (CI 迂回) に従う（Actions の一時無効化を含む手順一式がある）
