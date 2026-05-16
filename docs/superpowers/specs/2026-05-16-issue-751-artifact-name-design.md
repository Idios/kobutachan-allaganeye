# Issue #751: CI artifact 名から `-portable` を削除 設計

> **Status**: design (brainstorming 確定、writing-plans 待ち)
> **作成**: 2026-05-16 / session `sharp-darwin-e7bf33`
> **対象 issue**: [#751](https://github.com/Idios/kobutachan-allaganeye/issues/751)
> **上位 plan**: なし (単独 task issue)

## 概要

CI artifact 名から `-portable` を削除する。Portable ZIP 哲学 (`CLAUDE.md §Portable ZIP 哲学`) 下で portable 版以外を開発する予定がないため、`-portable` 修飾は冗長。

- **旧**: `allaganeye-portable-windows-v${VERSION}`
- **新**: `allaganeye-windows-v${VERSION}`

release tag push で生成される配布 zip (`allaganeye-vX.Y.Z-windows.zip`) は既に `-portable` を含んでいないので変更不要。本変更は CI artifact (build-windows job の upload-artifact / release job の download-artifact) のみが対象。

## 背景

### 現状

[`.github/workflows/release.yml:263`](../../.github/workflows/release.yml) (build-windows job, upload-artifact) と [`:282`](../../.github/workflows/release.yml) (release job, download-artifact) が `allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}` という名前で artifact を扱っている。GitHub Actions UI からダウンロードした際は `allaganeye-portable-windows-v0.2.0.zip` というファイル名でユーザーに見える。

artifact 名に version を付与した経緯は [#616](https://github.com/Idios/kobutachan-allaganeye/issues/616) ([spec §1](2026-05-08-l2b-distribution-design.md)) で、`-portable-` prefix はその時点で既存挙動を踏襲したもの。

### Portable ZIP 哲学との整合

`CLAUDE.md §Portable ZIP 哲学`:

> ツール側はユーザー環境を変更しない。ファイル関連付け / レジストリ / PATH / 自動起動登録は提案禁止。展開 = インストール、削除 = アンインストール の Portable ZIP 哲学を維持する (2026-04-27 ユーザー方針確定)。

portable 以外の配布形態 (installer / msix / scoop manifest 等) は提供予定がないため、`-portable` で portable 版を区別する必要がない。

### Release target の確定

issue 本文の「対応方針」セクションは `v0.2.1 以降の minor release 直前` を初期想定していたが、本 session で Idios 確認 (2026-05-16) により **v0.2.0 release 前に対応** に変更:

- 影響範囲が `.github/workflows/release.yml` 2 行のみで極小
- v0.2.0 リリース時の Release ページ表示は `allaganeye-v0.2.0-windows.zip` (`-portable` 無し) で既に揃っているため、CI artifact 名も合わせる方が一貫性が取れる
- deferred ラベル付与 + v0.2.1 まで持ち越し と比較しても、PR 1 本の追加コストの方が project convention 上の混乱 (本文では deferred、ラベルでは scope 内、という乖離) が無くて望ましい

## 受け入れ条件 (元 issue 逐条)

元 [issue #751](https://github.com/Idios/kobutachan-allaganeye/issues/751) の「確認項目 / 作業項目」を逐条引用 (本 session で release target を v0.2.0 内に確定したことに伴い、4 項目目「test tag push 実行」を v0.2.0 release tag 時に統合)。

- [ ] `.github/workflows/release.yml:263` の `name:` を `allaganeye-windows-v${{ ... }}` 等 `-portable` 抜きに変更
- [ ] `.github/workflows/release.yml:282` の `name:` を上記と一致させる (build-windows と release job 間で参照名が一致する必要あり)
- [ ] `docs/superpowers/specs/`, `docs/superpowers/plans/` 配下で `allaganeye-portable-windows` を参照している現役 doc があれば更新 (過去 plan/spec は historical record として残置可)
- [ ] CI (PR の build-windows job) で release workflow の build 部分が成功することを確認
  - 元 issue の「test tag push」は v0.2.0 release tag 切り出し時に release job (`actions/download-artifact`) の resolve が成功することで合わせて検証する

## 設計

### yml 2 行修正

[`.github/workflows/release.yml:263`](../../.github/workflows/release.yml) (build-windows job):

```yaml
      - uses: actions/upload-artifact@v4
        with:
          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}  # 旧: allaganeye-portable-windows-v${{ ... }}
          path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
          if-no-files-found: error
```

[`.github/workflows/release.yml:282`](../../.github/workflows/release.yml) (release job):

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}  # 旧: allaganeye-portable-windows-v${{ ... }}
          path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
```

upload と download の name は **必ず一致** (`actions/upload-artifact` で publish された artifact を `actions/download-artifact` が同 name で resolve する仕様)。両方を同期して変更する。

### 変更しない (historical record 残置)

issue 本文「過去 plan/spec は historical record として残置可」方針に従い、以下は更新しない:

| ファイル | 該当箇所 | 理由 |
| --- | --- | --- |
| [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](2026-05-08-l2b-distribution-design.md) | §1 #616 line 44, 50, 56 | #616 完了時点の design 記述。「現状 ...」「PR Actions tab ... 形式」「`release.yml:212` を ... に変更」はいずれも当時の現状/受け入れ条件/設計を記録した historical record |
| [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md:77`](../plans/2026-05-07-l2-v020-roadmap.md) | 「CI artifact zip 名にバージョン番号付与 (`allaganeye-portable-windows-vX.Y.Z`)」 | roadmap における #616 表記。完了済み issue の説明。今後の roadmap update で必要なら #751 行を追加 |
| [`docs/superpowers/plans/2026-05-08-l2b-616-artifact-version.md`](../plans/2026-05-08-l2b-616-artifact-version.md) | 全体 | #616 の implementation plan 全体。当時の作業内容を記録した historical |
| [`docs/superpowers/plans/2026-05-08-l2b-617-bat-gui-launch.md:981`](../plans/2026-05-08-l2b-617-bat-gui-launch.md), [`:992`](../plans/2026-05-08-l2b-617-bat-gui-launch.md) | `gh run download ... --name "allaganeye-portable-windows-v..."` コマンド例 | #617 plan 内の検証コマンド例。当時の artifact 名で記録された historical |
| [`docs/superpowers/specs/2026-05-12-issue-729-integrity-manifest-bom-design.md:61`](2026-05-12-issue-729-integrity-manifest-bom-design.md) | `gh run download 25703326786 --name allaganeye-portable-windows-v0.2.0` | 特定 run id を含む historical record (#729 調査時の実行履歴) |

これらを更新しないことで:

- PR の diff が yml 2 行のみで集中し、レビューが容易
- 過去 spec/plan の `git log` 履歴と本文記述が乖離しない (historical record の性質)
- 将来「v0.2.0 リリース前は `-portable-` 付き artifact 名だった」という事実を spec 上で追跡可能

## 影響範囲

- [`.github/workflows/release.yml`](../../.github/workflows/release.yml) line 263 / 282 (2 箇所、各 1 行)

他のファイル更新なし (上記 historical record 残置方針)。

## 検証

### Machine-verified (Self-Test Report `[x]` bullet)

- `git diff .github/workflows/release.yml` で line 263 / 282 の name が `allaganeye-windows-v${{ ... }}` (`-portable-` 抜き) に変更されている
- `grep -nE "allaganeye-portable-windows" .github/workflows/release.yml` で 0 件
- PR の `build-windows` job が PASS (artifact upload で name 不正なら yml validate or upload-artifact action で fail)
- PR の他の jobs (CI workflow 等) に regression が無い

### Machine-unverifiable (Self-Test Report `-` bullet、Idios 目視)

- PR Actions tab → Release workflow run → ページ下部 Artifacts セクションで `allaganeye-windows-v0.2.0` (`-portable-` 抜き) が表示されている (`.zip` 拡張子は UI 上は省略表示される)
- v0.2.0 release tag 切り出し時、release job (`actions/download-artifact`) が新 name で artifact を resolve できることを確認 (PR 段階では release job が走らないため、tag push 時のリグレッションテスト扱い)

## Iron Law check

### Iron Law 1 (受け入れ条件)

PR review 時に `/review-pr` が `enforce-acceptance-criteria` skill を呼び、上記「受け入れ条件 (元 issue 逐条)」4 項目を逐条検証。

### Iron Law 3 (scope creep)

scope は yml 2 行のみ。doc は historical 残置で対象外。「ついでに他の workflow file を整理」「`-portable-` 文字列を全 doc から消す」等の拡大は禁止。

### Iron Law 4 (Closes 禁止)

PR 本文では `Refs #751` のみ。`Closes/Fixes/Resolves #751` は使わない。PR merge 後に受け入れ条件再検証 → `/close-issue` skill で手動 close。

### Iron Law 6 (Pre-flight)

PR 作成時に以下を順次実施:

- **Step 0** (hard-gate): `gh pr list --search "751" --state open` で並行 PR 重複確認 (<1s、build/verify の前)
- **Step 1**: `git fetch origin develop-0.2.0` で base 同期
- **Step 2**: `git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認
- **Step 3**: 取り込み未済 commit が `.github/workflows/release.yml` に touch しているか交差判定 (touch していれば merge / rebase 必須)
- **Step 4**: `gh pr list --search "751" --state all` で 並行 PR 重複再確認 (Step 0 から時間経過した場合の検出 window 補強)

### Iron Law 6 (path-based 自動チェック)

変更 path: `.github/workflows/release.yml` のみ。

| 観点 | 必要性 | 理由 |
| --- | --- | --- |
| `ruff check . / ruff format --check . / pyright / pytest` | 不要 | Python 変更なし |
| `npm run lint / typecheck / test / build / cargo check` (in `gui/`) | 不要 | GUI 変更なし |
| `markdownlint` (via `scripts/check-markdownlint.sh`) | 不要 (design doc commit 時のみ) | `.md` 変更は本 design doc 1 ファイルのみ。yml 変更とは独立 |
| yml syntax / actions validation | PR CI で自動検証 | `build-windows` job 実走で artifact upload まで確認 |

### Iron Law 6 (実機検証 trigger)

該当なし。変更 path は `.github/workflows/release.yml` のみで、ロジック変更 path (`gpu_detector.py` / `audio/*.py` / `video/detector.py` / `gui/src-tauri/**`) を含まない。GUI Tauri 起動 / GPU / audio / 長時間動画の実機検証は不要。

machine-unverifiable の `-` bullet (Idios 目視) は Self-Test Report に記載するが、`AskUserQuestion` での実機検証依頼は不要。

## リスク / トレードオフ

### 低リスク

- upload-artifact / download-artifact の name は CI 内部での artifact passing にのみ使われ、外部 API ではない (外部ユーザー向けの release zip 名は別 step `Create release archive` で生成される `allaganeye-vX.Y.Z-windows.zip` で、本変更の影響なし)
- name 不一致 (片方だけ更新するミス) は **v0.2.0 release tag push 時** に detect される (release job の `download-artifact` が `Artifact not found` で fail)。release job は `if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')` で **PR 上では実走しない** ため、PR 段階での自動検出は不可
  - 対策: PR 作成前に line 263 / 282 の name 文字列が完全一致しているか目視確認 + `grep -nE "allaganeye-portable-windows" .github/workflows/release.yml` で 0 件確認 (machine-verified の Self-Test Report に含める)

### 潜在的混乱

historical record 残置の方針により、過去 plan/spec を読んだユーザーが `allaganeye-portable-windows` という artifact 名で `gh run download` を試みて失敗する可能性がある。ただし:

- 過去 plan/spec は特定 PR (#616, #617, #729) の作業記録として参照されるもので、最新情報を引く文脈ではない
- 最新の artifact 名を知りたい場合は `release.yml` 現行版か、本 design doc を参照する想定
- 必要であれば後続で過去 plan/spec の冒頭に「artifact 名は v0.2.0 から `allaganeye-windows-v...` に変更 (`#751` 参照)」の注記を追加する別 issue を立てる (本 PR では対応しない)

## 開放問題 (writing-plans 持ち越し)

なし。本 design で受け入れ条件と設計が確定。

writing-plans フェーズでは以下を確定:

- PR title 文言の最終確定 (案: `chore(ci): #751 CI artifact 名から -portable を削除`)
- PR body の章構成と Self-Test Report 表記
- Iron Law 6 Pre-flight Step 0-4 の実行コマンドと出力ログ収集方法
- close-issue 時の issue 本文「対応方針」セクション更新文言
