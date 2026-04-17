セッション用 worktree のセットアップまたは再利用を行います。

引数: `<role> <number>`（例: `engineer 2`, `lead 3`, `tester 2`）

以下の手順を実行してください:

> **注意**: 本コマンドはメインリポジトリのルートから実行すること。worktree 内から実行された場合は、まずメインリポジトリのルートに移動する:
> ```bash
> MAIN_REPO=$(git rev-parse --path-format=absolute --git-common-dir | sed 's|/\.git$||')
> cd "$MAIN_REPO"
> ```

## ステップ 0: 開発ブランチの特定

現在の開発ブランチを特定する:

```bash
git fetch origin
DEV_BRANCH=$(git branch -r --list 'origin/develop-*' --sort=-creatordate | head -1 | sed 's|origin/||;s/^[[:space:]]*//')
```

`DEV_BRANCH` が空の場合はエラーとして中断する:

```bash
if [ -z "$DEV_BRANCH" ]; then echo "ERROR: origin/develop-* branch not found"; exit 1; fi
```

結果を `<develop-branch>` として以降のステップで使用する。

## ステップ 1: 引数の解析

引数から以下を決定する:

| 引数 | worktree サフィックス | ROLE ファイル | セッション ID | ブランチ名 |
|---|---|---|---|---|
| `engineer <N>` | `eng<N>` | `engineer` | `engineer-<N>` | `engineer-<N>/work` |
| `lead <N>` | `lead<N>` (`lead 1` のみ `lead`) | `lead-engineer` | `lead-<N>` | `lead-<N>/work` |
| `tester <N>` | `tester<N>` (`tester 1` のみ `tester`) | `tester` | `tester-<N>` | `tester-<N>/work` |
| `director <N>` | `director<N>` (`director 1` のみ `director`) | `director` | `director-<N>` | `director-<N>/work` |

worktree ディレクトリ: `.claude/worktrees/<サフィックス>/`

## ステップ 2: worktree の存在確認

```bash
ls -d .claude/worktrees/<サフィックス> 2>/dev/null
```

### 2a: 既存 worktree がある場合（再利用）

1. work ブランチに切り替えてから開発ブランチの最新を取り込む:
   ```bash
   cd .claude/worktrees/<サフィックス>
   git checkout <セッション ID>/work
   git fetch origin <develop-branch>
   git merge origin/<develop-branch>
   ```

2. `settings.local.json` を同ロールの既存セッションからコピーする:
   - 同ロールの worktree（番号1）から `.claude/settings.local.json` をコピー
   - コピー元が存在しない場合はスキップ

### 2b: worktree が存在しない場合（新規作成）

1. メインリポジトリから worktree を作成する:
   ```bash
   git worktree add .claude/worktrees/<サフィックス> -b <セッション ID>/work origin/<develop-branch>
   ```

2. ROLE ファイルを作成する:
   ```bash
   echo "<ROLE ファイル値>" > .claude/worktrees/<サフィックス>/ROLE
   ```
   ※ 末尾に改行を含めること

3. `settings.local.json` を同ロールの既存セッションからコピーする:
   - 同ロールの worktree（番号1）の `.claude/settings.local.json` をコピー
   - コピー元が存在しない場合はスキップ
   ```bash
   mkdir -p .claude/worktrees/<サフィックス>/.claude
   cp .claude/worktrees/<コピー元サフィックス>/.claude/settings.local.json \
      .claude/worktrees/<サフィックス>/.claude/settings.local.json
   ```

## ステップ 3: 完了報告

以下を報告する:
- worktree パス
- ブランチ名
- セッション ID
- 開発ブランチ（`<develop-branch>`）
- 新規作成 or 再利用
- settings.local.json のコピー元（コピーした場合）
