セッション用 worktree のセットアップまたは再利用を行います。

引数: `<role> <number>`（例: `engineer 2`, `lead 3`, `tester 2`）

以下の手順を実行してください:

## ステップ 1: 引数の解析

引数から以下を決定する:

| 引数 | worktree サフィックス | ROLE ファイル | セッション ID | ブランチ名 |
|---|---|---|---|---|
| `engineer <N>` | `eng<N>` | `engineer` | `engineer-<N>` | `engineer-<N>/work` |
| `lead <N>` | `lead<N>` (`lead 1` のみ `lead`) | `lead-engineer` | `lead-<N>` | `lead-<N>/work` |
| `tester <N>` | `tester<N>` (`tester 1` のみ `tester`) | `tester` | `tester-<N>` | `tester-<N>/work` |
| `director <N>` | `director<N>` (`director 1` のみ `director`) | `director` | `director-<N>` | `director-<N>/work` |

worktree ディレクトリ: `E:\projects\kobutachan-tools\kobutachan-allaganeye-<サフィックス>\`

## ステップ 2: worktree の存在確認

```bash
ls -d E:/projects/kobutachan-tools/kobutachan-allaganeye-<サフィックス> 2>/dev/null
```

### 2a: 既存 worktree がある場合（再利用）

1. そのディレクトリへ移動
2. `git status` で状態確認
3. ROLE ファイルが存在することを確認
4. `/assume-role <role>` を実行

### 2b: 既存 worktree がない場合（新規作成）

1. main ブランチの最新を取得:
   ```bash
   git -C E:/projects/kobutachan-tools/kobutachan-allaganeye fetch origin
   ```
2. worktree を作成:
   ```bash
   git -C E:/projects/kobutachan-tools/kobutachan-allaganeye worktree add -b <ブランチ名> E:/projects/kobutachan-tools/kobutachan-allaganeye-<サフィックス> origin/main
   ```
3. worktree に移動
4. ROLE ファイルを作成:
   ```bash
   echo "<role>" > ROLE
   ```
5. `.claude/settings.local.json` を作成（同一ロールの worktree 間で共有するため、本体リポジトリからコピー）
6. `/assume-role <role>` を実行

## ステップ 3: 作業開始

ユーザーに以下を報告:
- worktree パス
- ブランチ名
- セッション ID
- ロールの概要
