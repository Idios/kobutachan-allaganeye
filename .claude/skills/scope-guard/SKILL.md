---
name: scope-guard
description: 実装中の「ついでに直した」スコープ逸脱を検知し、(a) 別 issue 起票 / (b) revert / (c) スコープ拡大 の 3 択をユーザー判断で強制する。Iron Law 3 の執行機構。
user-invocable: true
---

## Iron Law

**NO CHANGES OUTSIDE THE ISSUE SCOPE WITHOUT A NEW ISSUE.**

着手している issue の範囲外の変更を「ついでに」commit することは禁止。
気付いた問題があれば **作業を止めて** 新 issue を起票し、別 PR で対応する。

## 背景

複数スコープ (GUI / インストーラ / guard) が並行で動く L2 では、スコープ逸脱が
レビュアの負荷を増やし、ロールバック時の範囲特定を困難にする。
「軽微な改善」「ついでにリファクタ」で PR が肥大化する再発防止策。

## 呼び出しタイミング

- **実装中**: 着手 issue の範囲外変更を必要と判断した瞬間
- **PR 作成直前**: `git diff --stat` で変更範囲を確認する際に必ず実行
- **単独呼び出し**: `/scope-guard` で任意のタイミングでチェック

## 手順 (Gate Function)

### Step 1: 現在の issue スコープを特定

```bash
# 着手している issue の本文から スコープ記述を抽出
gh issue view <ISSUE番号> --json title,body | python -c "import json,sys;d=json.load(sys.stdin);print(d['title']);print(d['body'][:500])"

# issue の「## 確認項目 / 作業項目」or 「## 修正対象」セクションが範囲を示す
```

もし着手 issue が不明 (作業ブランチ名に番号が無い等) なら、ユーザーに確認:

```text
AskUserQuestion: 現在の作業ブランチはどの issue に対応しますか？
```

### Step 2: 変更範囲の確認

現行 develop ブランチを特定してから実行:

```bash
# 現行 develop ブランチを特定（origin の develop-* から最新版を選択）
DEVELOP_BRANCH=$(git branch -r | grep -E 'origin/develop-[0-9]+' | sed 's|.*origin/||' | sort -V | tail -1)
echo "base: $DEVELOP_BRANCH"  # 例: develop-0.2.0

# 変更範囲を確認
git diff --stat "$DEVELOP_BRANCH"...HEAD
git diff "$DEVELOP_BRANCH"...HEAD --name-only
```

ブランチ特定が不明瞭な場合は `AskUserQuestion` でユーザー確認。

変更ファイル一覧を issue スコープと照合:

| 変更ファイル | 目的 | issue スコープ内? | 判定 |
|---|---|---|---|
| (ファイル 1) | (目的) | ✓ | 続行可 |
| (ファイル 2) | (目的) | ✗ | Iron Law 違反、Step 3 へ |

### Step 3: 逸脱検知時の対応

**スコープ外変更が 1 件でもあれば、以下を実行**:

1. `AskUserQuestion` でユーザーに方針確認:
   - **(a) 別 issue として起票**: 変更を revert せず、同 commit 内で但し書き、新 issue を起票して親 issue にリンク
   - **(b) 今すぐ revert**: `git reset <sha> -- <逸脱ファイル>` で変更を退避し、別ブランチで後日対応
   - **(c) スコープ拡大を認める**: 元 issue の scope を編集し、変更を正当化 (ユーザー判断必須)

2. 上記いずれかを実行、**独断で (a)/(b)/(c) を選ばない**

**フロー**: (b) revert を選択した場合は本スキル終了（作業ブランチから逸脱変更が消えたため Step 4 不要）。(a)/(c) を選択した場合は Step 4 に進み PR 本文への記載事項を確認する。

### Step 4: PR 作成前の最終確認

PR 作成直前に以下を PR 本文に明記:

- 着手 issue 番号
- 変更ファイル一覧と各々の目的
- スコープ外変更がある場合、その理由と対応した子 issue 番号

## Red Flags (以下の思考が浮かんだら STOP)

| 浮かんだ思考 | 現実 | 取るべき行動 |
|---|---|---|
| 「ついでに直しておこう」 | Iron Law 違反 | 止まって新 issue 起票 |
| 「軽微な修正だから問題ない」 | 「軽微」の判断は reviewer の仕事、自己判断禁止 | ユーザー確認 |
| 「元 issue の範囲を少し広げれば済む」 | スコープ拡大は元 issue 更新が必要 | ユーザー確認して issue 本文更新 |
| 「分ける方が面倒」 | 束ねると #367 系の事故を招く | 別 PR に分ける |
| 「前から気になってたから直す」 | 気になってたなら issue に書くべき | 新 issue 起票 |

## 例外: 整合性維持のための同 PR 修正 (双方向)

以下のいずれの方向でも、「矛盾を発見した PR のスコープ内で同 PR 修正を許容する」。ただし PR 本文に「整合修正: X との整合」と明記する。

- **コード変更 PR で発見した、コードと矛盾するドキュメント**: 同 PR で修正可 (整合性維持のため)
- **doc 変更 PR で発見した、CI 設定 (`.github/workflows/`) / コード側参照との矛盾**: 同 PR で修正可 (doc パス・識別子変更の波及範囲が同 PR スコープに含まれるため)

**波及が大きい場合の目安** (`review-pr/SKILL.md` §Step 5b 典型ケース表と同じ定量基準):

- **(A) 同 PR 修正可の目安**: CI YAML 1-2 箇所の path 書換え / テスト追加 1-2 ファイル / doc 追従 1-2 箇所
- **(B) 別 issue 起票の目安**: 別レイヤー実装変更を伴う (検知パイプライン / GUI / CLI への連鎖修正) / 既存テスト再実行工数が長時間 (GPU / 音声統合で 30 分超) / 別担当領域
- 判断に迷う場合は `AskUserQuestion` でユーザー (Idios) 判断に回す

それ以外のドキュメント更新 (typo, 説明追加) は別 PR で。

## 参考

- `docs/l2-workflow.md` §「ルールと強制メカニズム」
- `docs/issue-policy.md` §「Issue のライフサイクル管理」
- #367 — 関連する受け入れ条件チェック (enforce-acceptance-criteria skill)
