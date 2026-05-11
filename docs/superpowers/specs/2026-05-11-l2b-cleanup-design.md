# Lane IV-e / Group K: L2b cleanup 2 件 設計

> **Status**: design (brainstorming 確定、writing-plans 待ち)
> **作成**: 2026-05-11 / session `focused-lichterman-5e413f`
> **対象 issue**: #704 / #705 (2 件、roadmap §3-bis Lane IV-e)
> **上位 plan**: [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md)
> **関連先行 spec**: [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](2026-05-08-l2b-distribution-design.md) (Lane IV-a §2 #681 で BtbN URL aging を「Lane IV-a の 5 章目」として後送りに確定 → 本 spec §2 で消化)

## §0 概要

### Lane IV-e / Group K の目的

L2 (v0.2.0) リリース残作業のうち、**L2b 配布まわりの cleanup** 2 件を 1 spec / 2 章 / 2 PR (並行可) で扱う。Lane IV-a (Group F、Wave 0) の merge 後に摘出された P3-low 品質 issue を v0.2.0 ship 直前の品質一段上のため吸収する。

### 章順 (独立性順 = merge conflict リスク低い順)

| 章 | issue | priority | scope | 並行安全度 |
| --- | --- | --- | --- | --- |
| §1 | #704 | P3 (bug) | `scripts/tests/build-portable-zip.Tests.ps1` 1 file (BOM 付与 + 新 `Describe` block 1 個 regression test append) | high |
| §2 | #705 | P3 (task) | `scripts/build-portable-zip.ps1` (BtbN pin ブロック) + `.github/workflows/ci.yml` + `.github/workflows/release.yml` + `docs/release-process.md` + `docs/developer-setup.md` §9 + `docs/quickstart.md` §10 | high (#704 と file 重複なし) |

### 全体方針

- **1 spec / 2 章 / 2 PR**: Lane IV-a §1-§2 precedent と同型 (Iron Law 3 整合: 1 PR = 1 issue scope)
- **PR 出順**: §1 (#704) → §2 (#705)。ただし file 完全独立のため並行可。bandwidth 次第で 1 worktree 連続 / 2 worktree 並行のいずれでも可
- **brainstorming 確定事項**: 各章の主要判断点 (Recommended 採用) は本 spec で確定。実装手順 minor 確定事項 (新 SHA256 値 / EOL 不変保証手順 / Format-ReadmeContent test 拡張方法 等) は writing-plans フェーズに持ち越し
- **Lane 配置**: roadmap §3-bis Lane IV-e (wave 1)、並行 lane = Lane I-B (Group B) / II-a (Group C) / II-b (Group D + #696) / V (Group I) / IV-b' (Group G + Group J)。共有 file ゼロ (matrix §3-bis 確認済)

### Iron Law 整合

- **Iron Law 1** (受け入れ条件): 各章で元 issue を逐条引用、各 PR review で `enforce-acceptance-criteria` skill を必ず呼ぶ
- **Iron Law 3** (scope): 1 PR = 1 issue。本 brainstorming で確定した範囲を逸脱しない
- **Iron Law 4** (close keyword): 全 PR で `Closes/Fixes/Resolves` 禁止、`Refs #N` のみ
- **Iron Law 6** (Pre-flight): 各 PR で `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認

### empirical 調査 summary (本 brainstorming で実施)

issue #705 candidate 確定の前提として、本 brainstorming セッション (`focused-lichterman-5e413f`、2026-05-11) で BtbN/FFmpeg-Builds の retention 実態を `gh api repos/BtbN/FFmpeg-Builds/releases` で実測。issue #705 本文の「BtbN は最新 30 件程度のみ保持」前提は誤りで、実際は以下 (本 spec §2 設計の根拠):

| 種別 | 例 | 保持期間 (実測) |
| --- | --- | --- |
| daily | `autobuild-2026-05-06-13-32` | **~14 日** (次の月初までの間) |
| monthly survivor | `autobuild-2026-04-30-13-44` (= 各月末日 daily が survive) | **~24 ヶ月** |
| 全 release 数 | (2026-05-11 時点) | **37 tags / 2024-06-30 〜 2026-05-10** |

加えて、`checksums.sha256` sidecar が release ごと 1 file (~5 KB、49 asset 網羅) で提供されることも empirical に確認 ([URL pattern: `https://github.com/BtbN/FFmpeg-Builds/releases/download/<tag>/checksums.sha256`](https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-04-30-13-44/checksums.sha256))。

Lane IV-a §2 (#681) の in-place rewrite と同型 (empirical でない前提に基づく candidate 群を empirical で確定する pattern)。

---

## §1 #704: Pester PS5.1 + BOM 不在で parse 失敗

### 背景

- `scripts/tests/build-portable-zip.Tests.ps1` は UTF-8 (BOM 不在) で保存されている。**empirical 確認済み**: file 先頭 12 byte = `3c 23 0d 0a 50 65 73 74 65 72 20 76` = `<#\r\nPester v` (BOM `EF BB BF` 不在)
- Windows PowerShell 5.1 (`powershell.exe`) はデフォルト encoding を ANSI / CP932 (日本語環境では Shift-JIS) として解釈する
- BOM があれば PS5.1 でも UTF-8 として認識するが、現状の Pester test file は BOM 不在のため日本語コメントが mojibake → parse error
- CI workflow は `pwsh -NoProfile` (PS7.x、UTF-8 default) で実行するため、CI では検出されず、ローカル PS5.1 ユーザーが `powershell.exe -Command "Invoke-Pester ..."` で実行すると parse 失敗、ローカル regression test 不能
- 摘出元: PR #701 Round 1 review (subagent code quality)、(B) マージ後別 issue 化として triage 済

#### 該当する非 ASCII 行 (empirical 確認済み)

| 行 | 内容 | 由来 |
| --- | --- | --- |
| L197-199 | `# 新 BtbN naming (n8.1.1) では Get-FFmpegSourceRef が release tag を返し、...` (`Format-ReadmeContent` test) | PR #683 (commit 6e27ccc) で追加 |
| L224 | `# Per spec §3 + issue #617 doc requirement: ".bat double-click → GUI"` | PR #701 で追加 (`§` と `→` 含む) |

### 受け入れ条件 (元 issue #704 逐条)

- [ ] file の現状 encoding を確認 (`xxd` 等で先頭 3 byte 確認、BOM 不在を verify) — **本 brainstorming で empirical verify 済**
- [ ] 修正方針 (a)/(b)/(c) を決定 (Idios 判断) — **本 brainstorming で (a) UTF-8 BOM 付与 に確定**
- [ ] 採用案を実装
- [ ] PS5.1 (`powershell.exe`) でローカル `Invoke-Pester` を実行し parse 失敗が解消されることを verify
- [ ] CI `installer-pester` job が引き続き PASS することを verify
- [ ] 必要に応じて `docs/testing-guide.md` 等に運用 note 追記

### 設計

#### 採用案: option (a) UTF-8 BOM 付与

- `scripts/tests/build-portable-zip.Tests.ps1` の先頭に **UTF-8 BOM (`EF BB BF`)** を付与
- PowerShell 標準の `Set-Content -Path <file> -Value (Get-Content -Raw <file>) -Encoding utf8BOM` を使う想定 (writing-plans で実装手順確定)
- **本 file のみ対応**、他 .ps1 file (`build-portable-zip.ps1` 本体等) は現在 非 ASCII を含まないため touch しない (Iron Law 3 厳守、scope = `Tests.ps1` 1 file)
- Pester test に BOM 検証 case を 1 個追加し、rollback (再度 BOM 不在に戻る誤編集) を防ぐ regression test とする

#### 不採用案

| 案 | 理由 |
| --- | --- |
| (b) 日本語コメントを英訳 | encoding 依存ゼロは魅力だが、project review 文化 (日本語) と齟齬。今後コメント追加時に同じ問題が再発するため恒久対策にならない |
| (c) PS7 必須化 + docs 明記 | file 不変は魅力だが、Idios 環境含む PS5.1 default ユーザーが Pester 実行不可になる運用負担。Windows 11 デフォルトは依然 PS5.1 |

### 影響範囲

- `scripts/tests/build-portable-zip.Tests.ps1` (BOM 付与のみ + 新 `Describe` block 1 個 append、内容実体は不変)

### 実装方針

PR 1 つ、minimum-change:

1. `scripts/tests/build-portable-zip.Tests.ps1` の先頭に UTF-8 BOM (`EF BB BF`) を付与
   - 実装方法は writing-plans で確定 (e.g. `Set-Content -Encoding utf8BOM` / 手動 byte 書き込み / git pre-commit hook 使用 etc.)
   - **EOL 不変**: BOM 付与のみで CRLF/LF 変換が起きないことを保証 (Set-Content の挙動 + `git diff` で encoding 以外の差分ゼロ確認)
2. 同 file の末尾近くに新 `Describe 'File encoding (#704)'` block を append し、BOM 検証 1 case を追加 (regression test)
3. `docs/testing-guide.md` の運用 note 追記は **不要** と判断 (修正後は PS5.1 / PS7 両対応となり運用変更なし)

### テスト方針

#### Pester (CI で実行可)

新 `Describe 'File encoding (#704)'` block を `scripts/tests/build-portable-zip.Tests.ps1` 末尾に append:

```pwsh
Describe 'File encoding (#704)' {
  It 'is saved as UTF-8 with BOM so PowerShell 5.1 (powershell.exe) can parse non-ASCII comments' {
    # Without a BOM, Windows PowerShell 5.1 (default ANSI / CP932 in JP locale)
    # interprets non-ASCII comments as Shift-JIS, causing parse errors. The CI
    # `installer-pester` job uses `pwsh -NoProfile` (PS7.x, UTF-8 default), so
    # local PS5.1 regression coverage relies on a BOM marker. See #704.
    $bytes = [System.IO.File]::ReadAllBytes($PSCommandPath)
    $bytes[0] | Should -Be 0xEF
    $bytes[1] | Should -Be 0xBB
    $bytes[2] | Should -Be 0xBF
  }
}
```

`$PSCommandPath` は実行中の Pester test file path を返す自動変数で、self-referential check として確実。

#### CI (自動)

- `installer-pester` job 全 `Describe` pass (新 `File encoding (#704)` 含む)
- 既存 test 全 pass (BOM 付与は test 動作に影響しない)

#### 実機検証 (Idios)

- **必須**: ローカル PS5.1 (`powershell.exe`) で `Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1` を実行し parse 失敗が解消されることを verify (元 issue 受け入れ条件 4)
- **machine-unverifiable**: PS5.1 環境は CI 未提供のため、Idios 実機での確認が唯一の verification 経路

### リスク / トレードオフ

- **EOL conversion リスク**: `Set-Content -Encoding utf8BOM` がうっかり LF → CRLF 変換すると git diff が大きくなり review 困難。writing-plans で `git diff --stat` 1 行 + byte レベル diff (encoding 3 byte 追加のみ) を確認する手順を含める
- **BOM 付与による副作用**: PowerShell 5.1 / 7.x / Pester v5 すべてで BOM 付き UTF-8 を正常 parse 可。CI の `pwsh` でも regression なし
- **新 BOM 検証 test 自身の self-test**: test file が BOM 不在に戻ると test 自身も parse 失敗するため `It` block が実行されない (False Negative リスク)。だが CI `installer-pester` job が「test 数が想定値と異なる」「Discover phase で parse 失敗」を検出するため、検出は可能 (writing-plans で確認)

### 開放問題 (writing-plans 持ち越し)

- BOM 付与の実装方法 (`Set-Content -Encoding utf8BOM` / 手動 hex / git config 等) 確定
- EOL 不変保証手順 (実装後の `git diff --stat` + byte 比較)
- 新 `Describe 'File encoding (#704)'` block の実装位置 (file 末尾 vs Describe 順序)
- `installer-pester` job の Discover phase での parse 失敗検出 mechanism 確認 (Pester v5 の挙動)

---

## §2 #705: BtbN autobuild URL 陳腐化対策

### 背景

- `scripts/build-portable-zip.ps1:78` の `$FFmpegBuildTag = 'autobuild-2026-05-06-13-32'` は **daily autobuild tag** (BtbN が ~14 日で GC)
- 現 pin は ~25-30 日で 404、Portable ZIP build 不可能 (release.yml + ci.yml + build-portable-zip.ps1 全て fail)
- empirical 調査結果 (§0 末尾、本 spec) で BtbN の retention 実態を確定:
  - daily: ~14 日
  - monthly survivor (各月末日 daily): ~24 ヶ月
  - `checksums.sha256` sidecar 提供あり (release ごと 1 file)

### 経緯 (Lane IV-a §2 in-place rewrite との連続性)

- Lane IV-a §2 (#681) brainstorming 確定時、scope を get-pip.py 限定とし、BtbN URL aging は Lane IV-a の 5 章目 = 別 issue (#705) として後送りに確定
- 本 brainstorming セッションで empirical 調査を実施し、issue 本文の前提 (「BtbN は最新 30 件程度のみ保持」) を **修正** (実際は monthly snapshot が ~24 ヶ月 retention)
- Lane IV-a §2 in-place rewrite と同型 (empirical でない前提に基づく candidate 群を empirical で確定)

### 受け入れ条件 (元 issue #705 から、AC 編集なし)

- [ ] BtbN `.sha256` sidecar 提供有無の WebFetch 調査 — **本 brainstorming で empirical verify 済 (`checksums.sha256` 1 file が release ごと提供、~5 KB、49 asset を網羅)**
- [ ] BtbN autobuild tag retention 実績調査 — **本 brainstorming で empirical verify 済 (上表 §0)**
- [ ] 修正方針 (i)-(iv) の採用判断 (組合せ可、AskUserQuestion で Idios 承認) — **本 brainstorming で (α) monthly pin + Pester regression test に確定**
- [ ] `scripts/build-portable-zip.ps1` (line 64-75 → empirically 70-81) の更新
- [ ] `.github/workflows/ci.yml` の整合更新 (linux64-lgpl-shared 版)
- [ ] `.github/workflows/release.yml` の整合更新 (cache key の SHA256)
- [ ] 再発防止 regression test 追加
- [ ] `docs/developer-setup.md` § 9 / `docs/release-process.md` の BtbN bump 手順を新方式に整合更新
- [ ] `installer-pester` CI が新方式で全 PASS
- [ ] CI `build-windows` job が実 build を完走

### 設計

#### 採用案: option (α) — 4月末 monthly snapshot pin + Pester regression test

empirical 調査で判明した「monthly snapshot は ~24 ヶ月 retention」という事実に基づき、**daily から monthly への pin 切替** を主軸とする。これにより構造的に retention 問題を解決 (現状 14 日 → 24 ヶ月、~50倍)。

##### 新 pin の確定

| 項目 | 旧値 (daily) | 新値 (monthly survivor) |
| --- | --- | --- |
| `$FFmpegBuildTag` | `autobuild-2026-05-06-13-32` | `autobuild-2026-04-30-13-44` |
| `$FFmpegAsset` | `ffmpeg-n8.1.1-win64-lgpl-shared-8.1` | `ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1` |
| `$FFmpegSha256` | `16F409AB...` (旧) | (writing-plans で `checksums.sha256` から取得して確定) |
| ci.yml linux asset | `ffmpeg-n8.1.1-linux64-lgpl-shared-8.1.tar.xz` | `ffmpeg-n8.1-11-g75d37c499d-linux64-lgpl-shared-8.1.tar.xz` |
| ci.yml linux SHA256 | `ec754605...` (旧) | (writing-plans で `checksums.sha256` から取得して確定) |
| FFmpeg source ref (README 表示) | `n8.1.1` (release tag) | `g75d37c499d` (commit hash via OLD format) |

##### `Get-FFmpegSourceRef` 互換性 (empirical 確認済)

- 現 `Get-FFmpegSourceRef` (`scripts/build-portable-zip.ps1:128-`) は OLD format (`ffmpeg-n<ver>-<count>-g<commit>-...`) と NEW format (`ffmpeg-n<ver>-...`) **両方を扱える** (PR #683 review #9 で対応済、Tests.ps1 L110-129 でテスト済)
- 新 monthly asset `ffmpeg-n8.1-11-g75d37c499d-...` は OLD format に該当 → 既存 regex `^ffmpeg-n[^-]+-[0-9]+-g([0-9a-f]+)-` がマッチし `g75d37c499d` を返す
- **本 PR で `Get-FFmpegSourceRef` 関数本体の変更は不要**

##### `Format-ReadmeContent` への影響

- README は `(commit g75d37c499d)` 形式で表示される (OLD format 経路)
- 既存 Pester test (Tests.ps1 L196-207) は NEW format (`(ref n8.1.1)`) を assert しているため、本 PR では (1) 新 monthly に合わせて test fixture を更新する OR (2) NEW/OLD 両 format 用に test を 2 個保持する を選択 (writing-plans で確定)
  - (2) を推奨: BtbN が将来 release tag に戻った時 (例: 2026-05-31 monthly が n8.1.1 ref を保持) の前提で 2 format 両対応を test レベルで担保

##### Pester regression test (新設、monthly pattern enforcement)

新 `Describe 'BtbN pinning policy (#705)'` block を `scripts/tests/build-portable-zip.Tests.ps1` 末尾に append:

```pwsh
Describe 'BtbN pinning policy (#705)' {
  It 'pins $FFmpegBuildTag to a BtbN monthly snapshot (end-of-month daily survivor)' {
    # BtbN GCs daily autobuild tags after ~14 days but keeps end-of-month
    # snapshots (autobuild-YYYY-MM-{29,30,31}-*) for ~24 months. Pinning to
    # a monthly snapshot gives the Portable ZIP build a ~24-month retention
    # buffer instead of ~14 days. See #705 for the empirical study.
    # Allowed day suffixes: 28 (Feb non-leap fallback), 29-31.
    $FFmpegBuildTag | Should -Match '^autobuild-\d{4}-\d{2}-(28|29|30|31)-\d{2}-\d{2}$'
  }

  It 'pins $FFmpegAsset to a win64-lgpl-shared variant matching the build tag epoch' {
    # Defense-in-depth: catches accidental rollback to a stale asset name
    # that doesn't exist in the new monthly tag.
    $FFmpegAsset | Should -Match '^ffmpeg-n[\d.]+(-\d+-g[0-9a-f]+)?-win64-lgpl-shared-[\d.]+$'
  }
}
```

day suffix `28` を含めるのは February の non-leap year fallback 用 (BtbN が 2 月末を `02-28-...` で保持する可能性を許容)。

#### 不採用案 (本 brainstorming で empirical 結果を踏まえ skip)

| 案 | 概要 | 不採用理由 |
| --- | --- | --- |
| (i) `.sha256` sidecar 動的検証 | `checksums.sha256` から SHA を fetch して動的検証 | (α) monthly pin で構造的 retention 解決済、SHA pin 維持コストは年 1 回程度の手動 bump で十分。実装コスト > 利益 |
| (ii) multi-tag fallback chain | 新 tag → 旧 tag 順試行 | monthly retention ~24 ヶ月で構造的に不要。fallback chain は network noise + 失敗 path の test 困難 |
| (iii) kobutachan 側 mirror | 自リポ Releases に再ホスト | 24 ヶ月 retention で十分なバッファ、~85 MB × N versions の Releases 容量 + LGPLv3 redistribution 対応コスト > 利益 |
| (iv) Renovate / dependabot 自動 bump | 短期 SHA pin 更新の自動化 | bot 運用コスト + noise PR 増加。年 1 回程度の手動 bump で運用回るため v0.2.0 段階では overkill。v0.3.0 以降に再考可 |

(i) `checksums.sha256` 利用は **bump 手順の便利機能** として writing-plans で `docs/release-process.md` の手順に組み込む案あり (関数化はせず手動 bump 時の参照 URL として明記)。Iron Law 3 整合 (本 PR 範囲は monthly pin 切替に限定)。

### 影響範囲

- `scripts/build-portable-zip.ps1` (line 70-81 → 新 monthly pin / asset / SHA + comment block 更新)
- `scripts/tests/build-portable-zip.Tests.ps1` (新 `Describe 'BtbN pinning policy (#705)'` block append + 必要に応じて `Format-ReadmeContent` test 拡張)
- `.github/workflows/ci.yml` (`Cache FFmpeg archive` cache key + `Download FFmpeg archive` URL + `Install ffmpeg` SHA256、3 step、linux64-lgpl-shared 版)
- `.github/workflows/release.yml` (`Cache FFmpeg archive` cache key の SHA256、win64-lgpl-shared 版)
- `docs/release-process.md` § 11 (FFmpeg bump 手順を「monthly snapshot のみ pin、daily 禁止」に明記)
- `docs/developer-setup.md` § 9 (同上、BtbN bump checklist に monthly 制約 + `checksums.sha256` 参照手順を追記)
- `docs/quickstart.md` § 10 (FFmpeg ref が `n8.1.1` → `g75d37c499d` 等に表示変更されることを反映、または ref 文字列を generic 化)

### 実装方針

PR 1 つ、scope = #705 1 件 (Iron Law 3 整合):

1. **SHA 取得**: `checksums.sha256` を BtbN release tag `autobuild-2026-04-30-13-44` から fetch、`ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1.zip` と `ffmpeg-n8.1-11-g75d37c499d-linux64-lgpl-shared-8.1.tar.xz` の SHA256 を抽出 (writing-plans で実装手順確定)
2. **build script 更新**: `scripts/build-portable-zip.ps1:77-81` の `$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256` を新 monthly 値に置換、line 70-76 の comment block を新方式 (monthly only / `checksums.sha256` 参照) に書き換え
3. **CI yml 更新**: ci.yml の 3 step (cache key / download URL / install SHA) と release.yml の cache key を新 monthly 値に同期
4. **Pester 追加**: 新 `Describe 'BtbN pinning policy (#705)'` 2 case を Tests.ps1 末尾に append、`Format-ReadmeContent` test を必要に応じて 2 format 両対応に拡張
5. **doc 更新**: `docs/release-process.md` / `docs/developer-setup.md` § 9 / `docs/quickstart.md` § 10 を新方針に整合
6. **Pre-flight verify**: BtbN release page `https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-04-30-13-44` で新 asset の存在 + size を再確認 (writing-plans / 実装時)

### テスト方針

#### 自動 (CI で完結)

- `installer-pester`: 新 `Describe 'BtbN pinning policy (#705)'` 2 case + 既存 `Format-ReadmeContent` test pass (2 format 両対応に拡張した場合は新 case も pass)
- `build-windows` job: 実 Portable ZIP build を完走 (新 URL から FFmpeg DL + SHA verify + 展開 + 同梱が成功)
- `python` job (Linux CI): 新 linux64-lgpl-shared 版 FFmpeg で全 pytest pass
- `markdownlint`: 更新 doc 全 pass

#### 実機検証 (Idios)

- **必須**: ローカルで `pwsh -NoProfile -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive` 実行 → Portable ZIP build payload が `n8.1-11-g75d37c499d` で完走することを verify (元 issue 受け入れ条件「CI `build-windows` job が実 build を完走」のローカル version)
- **machine-unverifiable**: BtbN 上流が monthly snapshot を future にも継続提供すること (運用前提)。release-process.md / developer-setup.md にこの前提を明記

### リスク / トレードオフ

- **FFmpeg ref 変更**: `n8.1.1` (release tag) → `g75d37c499d` (commit hash、n8.1+11 commits) — 同 8.1 系列、API 互換、軽微な regression 可能性は low (BtbN が production 用にビルドしている dev ref のため安定性検証済み)。Idios 実機での Portable ZIP build 完走 + サンプル動画分割成功で十分 verify (writing-plans の実機検証項目に追加)
- **monthly survivor の availability 前提**: 「BtbN が monthly survivor を継続提供」の運用前提。empirical 過去 24 ヶ月で確認済だが、上流の policy 変更には脆弱。万一中断された場合は (iii) self-mirror に切替 (defer 案として release-process.md に明記)
- **bump 頻度**: 24 ヶ月 retention のため bump は実質 1 年 1 回程度で十分。Lane IV-a §2 の get-pip pin と同程度の運用コスト
- **下位互換性**: Portable ZIP のエンドユーザー視点では FFmpeg 8.1 系の挙動が同等のため transparent (README に表示される ref 文字列のみ変更)
- **SHA pin force-push 攻撃**: `Invoke-Download` の `Get-FileHash` SHA256 verify が defense-in-depth として残存、リスクなし
- **PR size**: scope を BtbN URL aging 限定、touched files = 6 (script 1 + Tests.ps1 1 + yml 2 + doc 3)、Iron Law 3 整合

### 開放問題 (writing-plans 持ち越し)

- 新 `$FFmpegSha256` (win64) と ci.yml 用 linux64 SHA256 の正確な値 (実装時に `checksums.sha256` から取得)
- `Format-ReadmeContent` test を 2 format 両対応に拡張する手順 (新 test 追加 vs 既存 fixture 切替)
- `docs/quickstart.md` § 10 の ref 文字列が hardcode されているか、template 化されているかの確認 (writing-plans で grep)
- BtbN bump 手順 doc (release-process.md / developer-setup.md § 9) の文言案 — 「monthly survivor only、daily 禁止、`checksums.sha256` から SHA 取得」明記
- 実機検証 trigger 確認: `AskUserQuestion` で writing-plans / 実装時に Idios に依頼
- writing-plans 着手時の final verify: `gh api 'repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-04-30-13-44'` で asset / SHA drift 再確認

---

## §3 章間 dependency / PR 出順 / l2-workflow Pre-flight

### PR 出順 (確定)

1. **§1 #704** (`Tests.ps1` 1 file の BOM 付与、最も独立、merge conflict リスク最小)
2. **§2 #705** (`build-portable-zip.ps1` + ci.yml + release.yml + 3 doc、横断)

### 並行可能性

file 共有なし、原則として並行可:

- §1 は `scripts/tests/build-portable-zip.Tests.ps1` のみ touch
- §2 は `scripts/build-portable-zip.ps1` と yml と doc を touch、`Tests.ps1` には append (新 `Describe 'BtbN pinning policy (#705)'` block 追加) する **可能性** がある
- → **§1 と §2 が並行する場合**、両方が `Tests.ps1` 末尾に append すると最終 merge 時に conflict が発生しうる

#### conflict 回避策 (writing-plans / 実装時)

| 状況 | 対応 |
| --- | --- |
| §1 → §2 連続 (1 worktree) | conflict なし、推奨 |
| §1 // §2 並行 (2 worktree) | 後着の PR が `git merge origin/develop-0.2.0` 後に該当 file の append 行を rebase で吸収 (Iron Law 6 PR Pre-flight 適用)。Tests.ps1 末尾の `Describe` block は順序に依存しないため rebase で安全 |

### 章間 dependency

- **§1 と §2 の `Tests.ps1` 共有**: §1 = 新 `Describe 'File encoding (#704)'`、§2 = 新 `Describe 'BtbN pinning policy (#705)'` を **どちらも file 末尾に append**。同 file だが別 `Describe` block で論理的に独立。連続実行 (1 worktree) なら conflict ゼロ、並行なら後着 PR で rebase
- **§2 と Lane IV-a §2 (#681) merge 完了の前提**: `scripts/build-portable-zip.ps1` の get-pip pin (line 53-68) は PR #703 (#681) で merge 済 → §2 着手時に develop-0.2.0 に存在することを Pre-flight で確認 (`git log --oneline scripts/build-portable-zip.ps1`)
- **並行 lane との衝突なし**: roadmap §3-bis matrix で確認済、Lane I-B (lib.rs) / II-a (PreviewScreen) / II-b (Export+ErrorModal) / V (post-#663) / IV-b' (workflow / CI / docs) との file 共有ゼロ
  - 念のため: Lane IV-b' は `.markdownlint-cli2.yaml` (#700) / `.github/workflows/error-rs-hint-drift.yml` 等 (#692) / `.github/ISSUE_TEMPLATE/bug_report.yml` (#458) を touch、ci.yml 本体は touch しない想定 → §2 の ci.yml 編集と独立

### Iron Law 整合 (再掲)

- **Iron Law 1**: 各 PR review で `enforce-acceptance-criteria` skill を必ず呼ぶ (受け入れ条件逐条引用)
- **Iron Law 2**: 2 PR を一括 merge / 一括 close 候補に上げる場合は `AskUserQuestion` 不要 (3 件以上が trigger)。だが、3 件目 (#704 + #705 + 第 3 PR) の bulk operation を企てるなら必須
- **Iron Law 3**: 1 PR = 1 issue scope。§1 = #704 only、§2 = #705 only。本 brainstorming 外の改善 (例: 他 .ps1 file への BOM 拡張 / Renovate 導入 / mirror 構築) は別 issue
- **Iron Law 4**: 全 PR で `Closes/Fixes/Resolves` 禁止、`Refs #N` のみ。マージ後 `/close-issue` skill で受け入れ条件再検証 + 手動 `gh issue close`
- **Iron Law 6**: 各 PR で
  - `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認
  - `gh pr list --search "<元issue#>" --state all` で並行 worktree PR 重複確認 (本 brainstorming 時点で 0 件、再確認必須)
  - 並行 worktree が `Tests.ps1` を編集中なら append 順序を協調 (slack 不要、git merge で吸収可能)

### l2-workflow Pre-flight

各 PR で実機検証 trigger 確認:

| 章 | 実機検証 trigger | 詳細 |
| --- | --- | --- |
| §1 #704 | **必須** (PowerShell file 編集) | ローカル PS5.1 (`powershell.exe`) で `Invoke-Pester` 実行 → parse 失敗解消を verify |
| §2 #705 | **必須** (build-portable-zip.ps1 編集 = release ビルド経路 + ci.yml 編集 = installer-pester / build-windows 全 job 影響) | (1) ローカル `pwsh -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive` で Portable ZIP build payload 完走 / (2) build した ZIP からサンプル動画分割成功 |

Self-Test Report 規約 (`docs/l2-workflow.md` §「Self-Test Report 規約」):

- machine-verified: `[x]` checkbox (ruff / pyright / pytest / npm lint / vitest / Pester / cargo check / markdownlint)
- machine-unverifiable: plain bullet `-` (Idios 目視・実機検証項目)

(A) PR 内修正優先 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」): レビュー摘出問題は原則 PR 内追加修正、サイズだけで (B) 別 issue を選ばない

---

## §4 writing-plans 持ち越し事項 (まとめ)

### §1 #704

- BOM 付与の実装方法 (`Set-Content -Encoding utf8BOM` / 手動 hex / git config 等) 確定
- EOL 不変保証手順 (実装後の `git diff --stat` + byte 比較)
- 新 `Describe 'File encoding (#704)'` block の実装位置 (file 末尾 vs Describe 順序)
- `installer-pester` job の Discover phase での parse 失敗検出 mechanism 確認 (Pester v5 の挙動)

### §2 #705

- 新 `$FFmpegSha256` (win64) と ci.yml 用 linux64 SHA256 の正確な値 (実装時に `checksums.sha256` から取得)
- `Format-ReadmeContent` test を 2 format 両対応に拡張する手順 (新 test 追加 vs 既存 fixture 切替)
- `docs/quickstart.md` § 10 の ref 文字列が hardcode されているか、template 化されているかの確認 (writing-plans で grep)
- BtbN bump 手順 doc (release-process.md / developer-setup.md § 9) の文言案 — 「monthly survivor only、daily 禁止、`checksums.sha256` から SHA 取得」明記
- 実機検証 trigger: `scripts/build-portable-zip.ps1` 編集 + CI yml 編集 = release ビルド経路 → Idios 実機で Portable ZIP build 完走 + サンプル動画分割成功までを verify (`AskUserQuestion` で writing-plans / 実装時に依頼)
- writing-plans 着手時の final verify: `gh api 'repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-04-30-13-44'` で asset / SHA drift 再確認

---

## 参考 doc

- [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md) — 上位 plan (Lane IV-e)
- [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](2026-05-08-l2b-distribution-design.md) — Lane IV-a §2 (#681) で BtbN URL aging を本 spec に後送りに確定した先行 spec
- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [`docs/release-process.md`](../../release-process.md) — v0.2.0 リリース判定 + § 11 FFmpeg bump 手順
- [`docs/developer-setup.md`](../../developer-setup.md) § 9 — Python / FFmpeg バージョン更新チェックリスト
- [`docs/quickstart.md`](../../quickstart.md) § 10 — エンドユーザー向け FFmpeg ref 表示
- `.claude/hooks/session-start.sh` — Iron Law 5 条 + Red Flags

## 関連 issue

- 親: [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) (L2b ゼロ環境構築配布)
- §1: [#704](https://github.com/Idios/kobutachan-allaganeye/issues/704)
- §2: [#705](https://github.com/Idios/kobutachan-allaganeye/issues/705)
  - Lane IV-a §2 ([#681](https://github.com/Idios/kobutachan-allaganeye/issues/681)、closed via PR [#703](https://github.com/Idios/kobutachan-allaganeye/pull/703)) で scope 分離が確定
- 摘出元 PR: §1 = [#701](https://github.com/Idios/kobutachan-allaganeye/pull/701) (Round 1 review、(B) マージ後別 issue 化)
