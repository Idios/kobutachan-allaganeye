---
name: enforce-acceptance-criteria
description: PR レビュー時に元 issue の受け入れ条件を逐条検証し、全項目が実証されていないと LGTM を出せないゲート。#367 対策。
user-invocable: true
argument-hint: <PR番号>
---

> Iron Law 1 (`.claude/hooks/session-start.sh`) の手順実装。詳細な背景・条文は hook を参照。

## 呼び出しタイミング

- `/review-pr` スキル冒頭から呼ばれる (§3 チェックリスト直前)
- 単独でも呼べる: `/enforce-acceptance-criteria <PR番号>`

## 手順 (Gate Function)

### Step 1: 受け入れ条件の逐条引用

```bash
# PR に紐づく元 issue 番号を特定
gh pr view $ARGUMENTS --json body | python -c "import json,sys,re;b=json.load(sys.stdin)['body'];[print(m) for m in re.findall(r'Refs? #(\d+)|Fixes? #(\d+)', b)]"

# 各 issue の本文から ## 受け入れ条件 セクションを抽出
gh issue view <ISSUE番号> --json body | python -c "import json,sys;b=json.load(sys.stdin)['body'];print(b.split('## 受け入れ条件')[1].split('##')[0] if '## 受け入れ条件' in b else 'NO ACCEPTANCE CRITERIA FOUND')"
```

受け入れ条件が存在しない issue の場合、**`/review-pr` をここで停止**し「元 issue に受け入れ条件が無いため機械的検証不可。手動検証要」とユーザーに報告する。

### Step 2: 対応する diff / test の逐条引用

受け入れ条件の各 `- [ ]` 項目に対して、以下を全て明示する:

| 条件 | 対応 diff | 対応 test | 実証方法 |
| --- | --- | --- | --- |
| (逐条コピー) | `<ファイル:行範囲>` | `<test_*.py::test_*>` | 実行ログ or スクリーンショット |

**条件 1 つでも「対応 diff/test が書けない」→ Iron Law 違反。LGTM 不可、修正依頼へ**。

### Step 3: Verification Checklist (全項目 ✓ で初めて LGTM)

以下**全て**チェックが付かなければ終了せず修正依頼:

- [ ] 受け入れ条件の全項目を逐条引用した
- [ ] 各条件に対応する diff の具体的なファイル:行範囲を特定した
- [ ] 各条件に対応するテストケース名を特定した
- [ ] テストが実際に通過していることを確認した (`gh pr checks` or 手動 pytest)
- [ ] baseline FAIL → FIX 検証テストがある場合、baseline FAIL の実証（修正前コミットの test 失敗ログ、または PR 本文での明記）が確認できた
- [ ] 参照ファイル追加を伴う条件がある場合、`gh pr diff --name-only` で追加ファイルの実体（拡張子・サイズ等）を確認した
- [ ] UI/出力変更の場合、実サンプル (CLI 出力・スクショ) が PR 本文に添付されているか確認した
- [ ] 複数 issue を束ねている PR の場合、全 issue の条件を逐条処理した
- [ ] 「Phase 2 は別途」等の先送りがある場合、子 issue 番号が PR 本文と親 issue 本文の両方に記載されているか確認した
- [ ] `Closes` / `Fixes` / `Resolves` キーワードが PR 本文に無い

### Step 4: 結果報告

**全項目 ✓**:

```bash
gh pr comment $ARGUMENTS --body "acceptance-criteria verified [<session-id>]
- (条件 1): (対応 diff / test 要約)
- (条件 2): ...
"
```

その後 `/review-pr` に戻り、残りのロジック/ドキュメントレビューへ進む。

**未達あり**:

```bash
gh pr comment $ARGUMENTS --body "修正依頼 (受け入れ条件未達) [<session-id>]
- 未達項目:
  - (条件 X): <理由: 対応 diff/test が無い / test 未 pass / 出力サンプル未添付 等>
- 対応方針: (具体的な修正指示)
"
```

`/review-pr` §「修正依頼コメント投稿」(レビュー専用セッション) または `docs/l2-workflow.md` §タスクフロー の「PR 作成と同一セッション」分岐に従い、修正 → 再 `/enforce-acceptance-criteria` ループ。

## Red Flags (以下の思考が浮かんだら STOP)

| 浮かんだ思考 | 現実 | 取るべき行動 |
| --- | --- | --- |
| 「大体満たしてる」 | 「大体」は NG。Iron Law は 100% | 未達項目を列挙して修正依頼 |
| 「機能は動いてるからテストは後で」 | baseline FAIL 検証なしは NG | テスト追加を要求 |
| 「UI 変更はスクショなしでも見れば分かる」 | レビュアは実行環境を持たない | 出力サンプル添付を要求 |
| 「複数 issue 束ねたけど条件は共通だろう」 | 各 issue の条件は別個に検証 | 全 issue 分を逐条処理 |
| 「Phase 2 は親 issue に書いてあるし大丈夫」 | 子 issue 番号が親に無いと追跡不能 | 子 issue 起票して親に link |

## 参考

- `docs/l2-workflow.md` §「レビュー受け入れ基準 (#367 対策)」
- `docs/issue-policy.md` §「Issue のライフサイクル管理」
- #367 — レビュープロセス改善の経緯
- #343 — 再発防止対象の事故事例
