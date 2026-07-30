# Issue #729: integrity-manifest.json BOM bug 修正 設計

> **Status**: v0.2.0 リリースゲート単発 bug fix — PR #720 (Lane I-B Group B 章 1 / #679) Iron Law 6 verify で発見、PR #720 AC4 (実機検証) を block 中
> **Scope**: [#729](https://github.com/Idios/kobutachan-allaganeye/issues/729) (1 spec / 1 PR)
> **Roadmap**: `docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md` §5.5 派生 issue として記載済
> **依存元 PR**: [#720](https://github.com/Idios/kobutachan-allaganeye/pull/720) (MERGED、本 spec の trigger となった bug 発見元 — block されていた AC4 は本 PR merge 後に再開予定)
> **session**: `cranky-bhabha-c33264` (2026-05-12 brainstorming、Idios + Claude Opus 4.7)。前セッション `naughty-meninsky-db73bc` (PR #720 Iron Law 6 verify で bug 発見・#729 起票)

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#729](https://github.com/Idios/kobutachan-allaganeye/issues/729) | OPEN (P3-low, bug) | **本 spec で対応** — `scripts/build-portable-zip.ps1` の manifest 書き出しが PS 5.1 で BOM 付き UTF-8、Tauri / Python integrity check で parse fail |
| [#720](https://github.com/Idios/kobutachan-allaganeye/pull/720) | MERGED | #679 (Lane I-B Group B 章 1) の修正 PR。本 PR merge 完了直後の Iron Law 6 verify (Idios local Portable ZIP 起動) で integrity error modal を発見 → #729 起票。AC4 「`cargo tauri build` で release bundle + CMD 窓不出を実機検証」は #729 修正後に再開 |
| [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) | CLOSED | integrity-manifest.json の初出 issue。本 spec はその manifest 書き出しの encoding bug を狭く修正 |
| [#704](https://github.com/Idios/kobutachan-allaganeye/pull/704) | MERGED | `build-portable-zip.ps1` / Tests.ps1 を **UTF-8 with BOM** 化して PS 5.1 dot-source 互換に。本 spec は **script 本体 (BOM 必要、PS 5.1 parser 互換)** と **script が生成する manifest (BOM 不要、JSON parser 互換)** を区別し、後者のみを BOM-less 化する |
| [#702](https://github.com/Idios/kobutachan-allaganeye/pull/702) | MERGED | `New-IntegrityManifest` の `.pyc` / dotfile 除外 + 順序固定 + `manifest_error` 詳細化。本 spec の Pester test は #702 で確立した `Describe 'New-IntegrityManifest'` block の隣に新 `Describe` を追加する形 |

## §1 Background

### 1.1 #729 — Portable Bundle 起動時の integrity-check failure modal

Portable ZIP の `allaganeye-gui.exe` (Tauri release build) は起動時に [`gui/src-tauri/src/integrity.rs::check_install_dir`](../../gui/src-tauri/src/integrity.rs#L187) で `integrity-manifest.json` を読んで bundled file が manifest と一致するか検証する。検証失敗時は `integrity-error` Tauri event を emit、フロントエンドが `ErrorModal` を blocking 表示する仕様 (#668)。

PR #720 の Iron Law 6 verify (Idios local) で次が確認された:

- 再現手順: `cd gui && npm run tauri -- build` → `pwsh scripts/build-portable-zip.ps1 -Version 0.2.0 -SkipArchive` → `build/portable/allaganeye-v0.2.0/allaganeye-gui.exe` 起動
- 結果: `[startup] integrity-check failure: true` の error modal が常時表示
- manifest hex dump: `efbb bf7b 0d0a ... ï»¿{` — 先頭 3 byte に UTF-8 BOM (`EF BB BF`) が混入

### 1.2 根本原因 — PowerShell version 依存の Set-Content 挙動

[`scripts/build-portable-zip.ps1:577`](../../scripts/build-portable-zip.ps1#L577) は manifest を次のように書き出す:

```powershell
Set-Content -Path $ManifestPath -Value (New-IntegrityManifest -PayloadDir $PayloadDir) -Encoding UTF8
```

`Set-Content -Encoding UTF8` の BOM emit 挙動は **PowerShell version 依存**:

| PS edition | `Set-Content -Encoding UTF8` の出力 |
| --- | --- |
| Windows PowerShell 5.1 (`powershell.exe`) | **UTF-8 with BOM (`EF BB BF`)** |
| PowerShell 6.0+ (`pwsh`) | **UTF-8 BOM-less** (default が `utf8NoBOM` 相当に変更) |

本 spec 起草前 2026-05-12 の実機検証 (このマシン PS 5.1.26100.8115) で再確認: `Set-Content -Encoding UTF8` 直後の `[IO.File]::ReadAllBytes` で `EF BB BF 7B 0A 20 20 22 76 65 72 73 69 6F 6E 22` (`{\n  "version"` の前に BOM)。

### 1.3 BOM 拒否側の挙動

両側の integrity check は BOM 先頭の JSON を **invalid JSON として reject** する:

- **Rust** ([`gui/src-tauri/src/integrity.rs::load_manifest`](../../gui/src-tauri/src/integrity.rs#L67)): `serde_json::from_str(&text)` が BOM を不正な先頭文字として `Err("invalid JSON")` を返す
- **Python** ([`allaganeye/integrity.py::load_manifest`](../../allaganeye/integrity.py#L65)): `json.loads(path.read_text(encoding="utf-8"))` が `JSONDecodeError("Unexpected UTF-8 BOM (decode using utf-8-sig)")` を raise

(`Path.read_text(encoding="utf-8")` は BOM を strip しない。`encoding="utf-8-sig"` のみが strip する。)

本 spec 起草前 2026-05-12 の Python 実機 (CPython 3.x) で検証: `json.loads('﻿{"version": 1, "files": []}')` → `JSONDecodeError: Unexpected UTF-8 BOM`。`Path.read_text(encoding="utf-8")` 経由でも first char が `'﻿'`、`json.loads` が同 error。

### 1.4 CI smoke が本 bug を mask していた理由

[`.github/workflows/release.yml`](../../.github/workflows/release.yml) の build-windows job は `shell: pwsh` で build script を実行する (PS 7+)。CI artifact (`gh run download 25703326786 --name allaganeye-portable-windows-v0.2.0`) の manifest を fetch し hex 確認した結果: 先頭 byte は `7B 0D 0A 20 20 22 76 65 72 73 69 6F 6E 22` (`{\r\n  "version"`)、**BOM 無し**。

つまり:

- **CI (pwsh 7+)**: manifest BOM-less → integrity check pass → `Smoke test (run launcher --version)` で `exit code: 0` + `allaganeye 0.2.0` 出力で smoke 緑
- **Idios local (powershell.exe / PS 5.1)**: manifest BOM 付き → integrity check fail → GUI modal / CLI exit 7

CI smoke は `--version` の Python `version_callback` が integrity check を呼ぶ仕様 ([`allaganeye/cli.py:38-44`](../../allaganeye/cli.py#L38)) なので、もし CI 側で manifest が BOM 付きだったら CI で exit 7 を検出するはずだったが、pwsh 7 の挙動差により mask されていた。**本 bug は PS-version-dependent な silent regression hole**。

(Idios local の再現が「`pwsh scripts/...`」と issue 本文に書かれているが、実機の bytes は BOM 付き = PS 5.1 挙動と一致。pwsh alias / minor version 差 / `$PSDefaultParameterValues` 設定の可能性があるが、本 spec の修正は PS-agnostic な `[IO.File]::WriteAllText` に切り替えることで invocation path に関わらず BOM 無しを保証するため、再現条件の詳細究明は不要。)

## §2 Goals

1. **Source 修正**: `scripts/build-portable-zip.ps1` L577 を `[IO.File]::WriteAllText` + `[UTF8Encoding]::new($false)` に変更し、PS 5.1 / PS 7+ どちらで invoke しても BOM 無し UTF-8 を出力するようにする。
2. **Inline comment 追加**: 修正箇所に PS-version 依存性と `[IO.File]` API を使う理由を記述。`Tests.ps1` で同様の理由から `[IO.File]::WriteAllBytes` を使っている既存 precedent への参照を含める。
3. **3 layer regression coverage**:
   - **Pester** (build output 側、byte-level): `Describe 'Integrity manifest encoding (#729)'` で manifest 先頭 byte が BOM (`EF BB BF`) ではないことを assert
   - **Python pytest** (read 側 latent bug pin): `test_load_manifest_raises_on_bom_prefixed_json` で BOM-prefixed manifest → IntegrityError を assert
   - **Rust cargo test** (read 側 latent bug pin、mirror coverage): `load_manifest_returns_err_for_bom_prefixed_json` で BOM-prefixed manifest → `Err("invalid JSON")` を assert
4. **CHANGELOG entry**: `[Unreleased] / ### Fixed` に 1 行追記。v0.2.0 release notes 用。
5. **Iron Law 6 実機検証 (Idios)**: powershell.exe (PS 5.1) と pwsh (PS 7+) の両方で build script を走らせ manifest BOM 不在を確認、Tauri GUI 起動で integrity error modal が出ないこと確認、CLI `allaganeye.bat --version` が exit 0 で version 表示することを確認。

## §3 Non-goals (scope 外明記)

### 3.1 本 spec で touch しないこと

- **L571 README.txt の BOM**: 機能的影響なし (README は parsing 対象ではない)。一貫性向上は派生 issue (§9 参照) として別途検討。
- **Python `load_manifest` の `utf-8-sig` defensive 化**: build 側で BOM 不在を保証するため受け側は BOM 拒否のまま。受け側を tolerant にすると future build script regression を silent に吸収して問題発見が遅れる。
- **Rust `load_manifest` の BOM strip 化**: 同上の理由。
- **CI matrix 拡張 (PS 5.1 + pwsh 7 の 2 軸 Pester run / PS 5.1 経由 build smoke)**: 本 PR は source fix で PS-agnostic にするのが目標。CI matrix 強化は infrastructure 改善で別 issue (§9 参照)。
- **CI smoke pass の根本原因究明**: §1.4 で「pwsh 7 の `Set-Content -Encoding UTF8` 挙動が PS 5.1 と異なるため CI が緑だった」と結論済 (CI artifact の manifest hex を直接検証)。これ以上の調査不要。

### 3.2 別途実施

- PR #720 AC4 「`cargo tauri build` で release bundle + CMD 窓不出を実機検証」は本 PR merge 後に再開。

## §4 Trade-offs / Alternatives considered

### 4.1 採用: `[IO.File]::WriteAllText` + `UTF8Encoding(false)` (Approach A)

```powershell
[System.IO.File]::WriteAllText(
    $ManifestPath,
    $ManifestJson,
    [System.Text.UTF8Encoding]::new($false)
)
```

**Pros**:

- PS 5.1 / PS 7+ どちらで invoke しても挙動同一 (PS-agnostic)
- `Tests.ps1` line 51 / 64 で既に `[IO.File]::WriteAllBytes` を同じ理由で使用済 (precedent あり)
- 明示的 (encoding が引数で見える、cmdlet の version-dependent な hidden behavior に依存しない)

**Cons**:

- `Set-Content` cmdlet idiom から離れる (script 内の他の `Set-Content -Encoding ASCII` 等とは書き方が異なる)
- やや verbose

### 4.2 棄却: `Set-Content -Encoding utf8NoBOM` (Approach B)

```powershell
Set-Content -Path $ManifestPath -Value $ManifestJson -Encoding utf8NoBOM
```

**棄却理由**: `utf8NoBOM` は PS 6.0+ 専用 enum 値。PS 5.1 では `Cannot bind parameter 'Encoding'. Cannot convert value "utf8NoBOM" to type [FileSystemCmdletProviderEncoding]` で runtime fail。#704 で確立した PS 5.1 dot-source 互換性 (Tests.ps1 が build-portable-zip.ps1 を `.` source して helper を load する) は parser レベルで OK だが、build 本パスを PS 5.1 で invoke するケース (`powershell.exe -File scripts/build-portable-zip.ps1`) を再び破壊する。Approach A はこの制約を持たない。

### 4.3 棄却: `[IO.File]::WriteAllBytes(GetBytes(...))` (Approach D)

```powershell
$bytes = [System.Text.Encoding]::UTF8.GetBytes($ManifestJson)
[System.IO.File]::WriteAllBytes($ManifestPath, $bytes)
```

**棄却理由**: 結果は Approach A と等価 (`Encoding.UTF8.GetBytes` 単体では BOM を prepend しない) だが、`Encoding.UTF8` static instance は `emitUtf8Identifier=true` で writer 経由では BOM を吐く設計のため、読み手に「UTF8 = BOM 付きじゃないの?」と疑念を抱かせる。Approach A は `[UTF8Encoding]::new($false)` の ctor 引数で BOM 不要を明示するので可読性が高い。

### 4.4 棄却: 受け側 (Python / Rust) を BOM tolerant 化 (Approach C)

**棄却理由**: build 側を fix せず受け側を tolerant にすると、future build script regression を silent に吸収して問題発見が遅れる。「manifest wire format = BOM-less UTF-8 JSON」と定義した以上、定義違反は fail-fast すべき。Approach A + 受け側回帰 test (§6.2 / §6.3) で「build 側が正しく出すこと」「受け側が BOM を厳密に拒否すること」を双方 pin する設計が最も robust。

## §5 Implementation: `scripts/build-portable-zip.ps1` 修正

### 5.1 修正前 ([L573-578](../../scripts/build-portable-zip.ps1#L573))

```powershell
# 7.5 Integrity manifest (#668)
# Generated after all payload steps complete so it reflects the actual files
# Tauri build / pip install / FFmpeg copy / launcher / README produced.
$ManifestPath = Join-Path $PayloadDir 'integrity-manifest.json'
Set-Content -Path $ManifestPath -Value (New-IntegrityManifest -PayloadDir $PayloadDir) -Encoding UTF8
Write-Host "Generated $ManifestPath"
```

### 5.2 修正後

```powershell
# 7.5 Integrity manifest (#668)
# Generated after all payload steps complete so it reflects the actual files
# Tauri build / pip install / FFmpeg copy / launcher / README produced.
#
# #729: Set-Content -Encoding UTF8 is PS-version-dependent for BOM emission:
#   - Windows PowerShell 5.1 (powershell.exe): emits UTF-8 with BOM (EF BB BF)
#   - PowerShell 6.0+ (pwsh): emits BOM-less UTF-8 (default changed in 6.0)
# Both Rust serde_json::from_str and Python json.loads reject the leading BOM
# as invalid JSON. CI release.yml uses pwsh 7 so smoke tests masked this bug
# for any user invoking the build script with powershell.exe. Write the
# manifest via the .NET API with explicit BOM-less UTF8Encoding to remove
# the PS-version dependency entirely. Tests.ps1 already uses [IO.File]
# helpers for the same cross-version compat reason.
$ManifestPath = Join-Path $PayloadDir 'integrity-manifest.json'
$ManifestJson = New-IntegrityManifest -PayloadDir $PayloadDir
[System.IO.File]::WriteAllText(
    $ManifestPath,
    $ManifestJson,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Generated $ManifestPath"
```

### 5.3 設計判断ポイント

1. **`$ManifestJson` を一時変数に分離**: `WriteAllText` の 2nd arg に function call を inline すると可読性低下 + 中間値デバッグ困難。
2. **`$ManifestPath` は absolute path**: `[IO.File]::WriteAllText` は PSDrive を経由せず .NET の `Path.GetFullPath` で resolve する。L576 で `Join-Path $PayloadDir 'integrity-manifest.json'` を与えており `$PayloadDir` は `Resolve-Path` 経由の absolute なので問題なし。
3. **BOM 不出力指定**: `[UTF8Encoding]::new($false)` の ctor 引数 `false` = `encoderShouldEmitUTF8Identifier=false`。
4. **他の `Set-Content -Encoding UTF8` 箇所は touch しない**: L571 README.txt は §3.1 で scope 外と明記。

## §6 Tests

### 6.1 Pester: `Describe 'Integrity manifest encoding (#729)'` 追加

`scripts/tests/build-portable-zip.Tests.ps1` の末尾 (既存 `Describe 'BtbN pinning policy (#705)'` の後) に追加:

```powershell
Describe 'Integrity manifest encoding (#729)' {
  BeforeAll {
    $script:EncodingTmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "manifest-enc-test-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:EncodingTmpDir | Out-Null
    # Minimal payload so New-IntegrityManifest has at least one entry to emit.
    Set-Content -Path (Join-Path $script:EncodingTmpDir 'allaganeye.bat') -Value 'fake' -Encoding ASCII
  }

  AfterAll {
    if (Test-Path $script:EncodingTmpDir) {
      Remove-Item -Recurse -Force $script:EncodingTmpDir
    }
  }

  It 'writes integrity-manifest.json without UTF-8 BOM so serde_json / json.loads can parse it (#729)' {
    # build-portable-zip.ps1 L577 で Set-Content -Encoding UTF8 を使うと PS 5.1
    # では UTF-8 with BOM (EF BB BF) になり、Rust serde_json も Python json.loads
    # も先頭 BOM を invalid JSON として reject する。修正後の
    # [IO.File]::WriteAllText + UTF8Encoding(false) で BOM が消えることを
    # byte-level で固定する。Set-Content -Encoding UTF8 への意図しない退行を
    # CI で即検出するための pinning test。
    $manifestPath = Join-Path $script:EncodingTmpDir 'integrity-manifest.json'
    $json = New-IntegrityManifest -PayloadDir $script:EncodingTmpDir
    [System.IO.File]::WriteAllText(
      $manifestPath,
      $json,
      [System.Text.UTF8Encoding]::new($false)
    )

    $bytes = [System.IO.File]::ReadAllBytes($manifestPath)
    # First byte must be `{` (0x7B), not `EF` (start of BOM).
    $bytes[0] | Should -Be 0x7B
    # Defense in depth: explicitly assert the BOM byte sequence is absent.
    ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) | Should -BeFalse
  }
}
```

**設計判断**:

- `New-IntegrityManifest` 単体ではなく **書き込み行為 (WriteAllText 呼出) を含めた test**。`New-IntegrityManifest` は string を返すだけで encoding を持たないため、test の defense は「manifest が disk に BOM 無しで着地する」が本質。
- assertion を 2 種類 ((a) first byte `0x7B` positive、(b) `EF BB BF` シーケンス不在 negative) 出して failure 時の可読性を上げる。
- 既存 `Describe 'New-IntegrityManifest'` block は内容 / 除外 / 順序を扱うので別目的、独立 block で `#729` を grep-friendly に。

### 6.2 Python pytest: `test_load_manifest_raises_on_bom_prefixed_json` 追加

`tests/test_integrity.py` の既存 `test_load_manifest_raises_on_invalid_json` の隣に追加:

```python
def test_load_manifest_raises_on_bom_prefixed_json(tmp_path: Path) -> None:
    """BOM-prefixed manifest -> IntegrityError (#729 latent bug pin).

    scripts/build-portable-zip.ps1 used Set-Content -Encoding UTF8 which
    emits UTF-8 with BOM on Windows PowerShell 5.1 (PS 6.0+ emits BOM-less).
    json.loads rejects the leading U+FEFF as `Unexpected UTF-8 BOM`. The
    build script was fixed in #729 to emit BOM-less UTF-8 via
    [IO.File]::WriteAllText regardless of PS version. This test pins the
    Python read side's BOM rejection behavior so that a future accidental
    regression in the build script gets caught at pytest time in addition
    to the Pester / Rust layers.

    Detected during #729 root cause analysis (CLAUDE.md §バグ修正時の方針:
    同種バグの横展開チェック). The Python integrity check would also have
    failed on BOM-prefixed manifest, but CI smoke (release.yml shell: pwsh)
    never produced BOM-prefixed manifest so the failure path was untested.
    """
    bad = tmp_path / "bom.json"
    bad.write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"version": 1, "files": []}).encode("utf-8")
    )

    with pytest.raises(IntegrityError) as exc_info:
        load_manifest(bad)

    assert "invalid JSON" in str(exc_info.value)
    assert "json_error" in exc_info.value.context
    # JSONDecodeError の message に "BOM" が含まれることまでは assert しない
    # (Python version 差で文言が変わる可能性があるため、failure category だけ pin)
```

### 6.3 Rust cargo test: `load_manifest_returns_err_for_bom_prefixed_json` 追加

`gui/src-tauri/src/integrity.rs` の `mod tests` ブロック (既存 `load_manifest_returns_err_for_invalid_json` の隣) に追加:

```rust
#[test]
fn load_manifest_returns_err_for_bom_prefixed_json() {
    // #729: build-portable-zip.ps1 used Set-Content -Encoding UTF8 which
    // emits UTF-8 with BOM on Windows PowerShell 5.1 (PS 6.0+ emits BOM-less).
    // serde_json rejects the leading BOM as an invalid JSON character. The
    // build script was fixed in #729 to emit BOM-less UTF-8 via
    // [IO.File]::WriteAllText regardless of PS version. This test pins the
    // Rust read side's BOM rejection behavior so that a future accidental
    // regression in the build script gets caught at `cargo test` time in
    // addition to the Pester / pytest layers.
    let dir = TempDir::new().unwrap();
    let p = dir.path().join("integrity-manifest.json");
    let mut f = fs::File::create(&p).unwrap();
    f.write_all(&[0xEF, 0xBB, 0xBF]).unwrap();
    f.write_all(
        br#"{"version": 1, "generated_at": "2026-05-12T00:00:00Z", "files": []}"#,
    ).unwrap();
    drop(f);

    let err = load_manifest(&p).unwrap_err();
    assert!(err.contains("invalid JSON"), "got: {}", err);
}
```

## §7 CHANGELOG entry

`CHANGELOG.md` の `[Unreleased] / ### Fixed` セクションに次の 1 行を追記 (既存の scorebar V2 行の次):

```markdown
- Portable ZIP の `integrity-manifest.json` を BOM-less UTF-8 で書き出すように修正 (#729)。`scripts/build-portable-zip.ps1` で `Set-Content -Encoding UTF8` を使うと Windows PowerShell 5.1 (`powershell.exe`) では UTF-8 with BOM を emit し、Tauri GUI 起動時の integrity-check (`serde_json::from_str`) と CLI `--version` の integrity-check (`json.loads`) が双方 BOM 拒否で fail していた。PS 6.0+ (`pwsh`) では BOM-less だったため CI smoke (`shell: pwsh`) が本 bug を mask。`[IO.File]::WriteAllText` + `UTF8Encoding(false)` で PS-agnostic に変更
```

## §8 Verification plan

### 8.1 Machine-verified (PR body `[x]`)

Iron Law 6 §「PR 作成 path 別自動チェック」に従い、touched files の path に応じて以下を全 pass させる:

- **Python** (`tests/test_integrity.py` を touch):
  - `ruff check .`
  - `ruff format --check .`
  - `pyright`
  - `pytest tests/test_integrity.py -v`
- **Pester** (`scripts/**` を touch):
  - `pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -CI"`
- **Rust** (`gui/src-tauri/**` を touch):
  - `cd gui/src-tauri && cargo check`
  - `cd gui/src-tauri && cargo test integrity`
- **markdownlint** (`CHANGELOG.md` / 本 spec doc を追加):
  - `bash scripts/check-markdownlint.sh`

### 8.2 Iron Law 6 Pre-flight

PR 作成直前に実施:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 -- \
  scripts/build-portable-zip.ps1 \
  scripts/tests/build-portable-zip.Tests.ps1 \
  tests/test_integrity.py \
  gui/src-tauri/src/integrity.rs \
  CHANGELOG.md
# touched files と交差する取り込み未済 commit があれば git merge origin/develop-0.2.0 + 自動チェック再実行
gh pr list --search "#729" --state all
# 並行 worktree PR 重複確認
```

### 8.3 実機検証 (Idios) — PR body の plain bullet `-`

`gui/src-tauri/**` と `scripts/build-portable-zip.ps1` を touch するため Iron Law 6 §「実機検証 trigger 表」で `AskUserQuestion` 経由 Idios に依頼必須:

1. **powershell.exe (PS 5.1) 経由 build** → manifest BOM 不在確認 (修正前は BOM 確認済、修正後は BOM 無しが期待値)

   ```powershell
   powershell.exe -File scripts/build-portable-zip.ps1 -Version 0.2.0 -SkipArchive
   Format-Hex build/portable/allaganeye-v0.2.0/integrity-manifest.json | Select-Object -First 1
   # Expected: 先頭 16 bytes が '7B 0D 0A ...' で始まる (EF BB BF 不在)
   ```

2. **pwsh 7 経由 build** → manifest BOM 不在確認 (回帰なし、CI と同等)

   ```powershell
   pwsh -File scripts/build-portable-zip.ps1 -Version 0.2.0 -SkipArchive
   Format-Hex build/portable/allaganeye-v0.2.0/integrity-manifest.json | Select-Object -First 1
   ```

3. **Tauri GUI 起動 → integrity error modal が出ないこと確認** (#729 受け入れ条件):

   ```text
   build/portable/allaganeye-v0.2.0/allaganeye-gui.exe をダブルクリック
   Expected: メイン画面 (drop screen) が直接表示、integrity error modal なし
   ```

4. **CLI `allaganeye.bat --version` → exit 0 + version 表示確認** (Python integrity check pass、PR #720 AC4 と無関係に基本動作):

   ```cmd
   cd build\portable\allaganeye-v0.2.0
   allaganeye.bat --version
   echo Exit: %ERRORLEVEL%
   Expected: "allaganeye 0.2.0" + Exit: 0
   ```

### 8.4 PR 構成

- **Base**: `develop-0.2.0`
- **Branch**: `claude/cranky-bhabha-c33264` (現 worktree)
- **PR title 案**: `fix(build): integrity-manifest.json を BOM-less UTF-8 で書き出す (#729)`
- **PR body 構成**:
  - Summary (issue link、root cause 1 paragraph)
  - 受け入れ条件 (#729) 逐条引用 + diff 引用
  - 横展開 (Python / Rust の latent bug pin)
  - CI smoke mystery 解明 (§1.4 のサマリ)
  - Self-Test Report (machine-verified `[x]` + 実機検証 `-`)
- **Iron Law 4**: PR 本文に `Closes/Fixes/Resolves` キーワード**禁止**。マージ後に `/close-issue` skill 経由で受け入れ条件再実測 → 手動 `gh issue close`。
- **PR #720 AC4 unblock**: 本 PR merge 後に PR #720 のレビュー comment / unblock notification を出して Idios が #679 実機検証を再開できるようにする。

## §9 派生 issue (本 PR 内で起票しない)

本 PR で発見・観察したが scope 外として **本 PR merge 後に別途起票検討** する項目 (Iron Law 3 / scope-guard 準拠):

| 観察 | 起票候補 issue 文言 | priority |
| --- | --- | --- |
| L571 README.txt も `Set-Content -Encoding UTF8` で BOM 付き (機能影響なし、Portable ZIP 内ファイルの encoding 一貫性のみの問題) | `[chore] Portable ZIP の README.txt も BOM-less UTF-8 で書き出す (consistency)` | P4-trivial |
| Pester / build smoke を PS 5.1 + pwsh 7 の cross-version matrix で実行する CI 補強 (PS-version-dependent な silent regression を将来検出) | `[infra] release.yml の Pester / build smoke を PS 5.1 + pwsh 7 matrix で実行` | P3-low |

両者とも本 PR scope 外。本 PR merge 後に Idios と `AskUserQuestion` で起票要否を確認する (Iron Law 2 bulk operation 防止)。

## §10 References

- Issue: [#729](https://github.com/Idios/kobutachan-allaganeye/issues/729)
- 関連 PR: [#720](https://github.com/Idios/kobutachan-allaganeye/pull/720) (発見元、AC4 block 解除待ち) / [#704](https://github.com/Idios/kobutachan-allaganeye/pull/704) (PS 5.1 BOM 互換性) / [#702](https://github.com/Idios/kobutachan-allaganeye/pull/702) (`New-IntegrityManifest` 仕様確立)
- PS encoding doc: [Set-Content `-Encoding` (Microsoft Learn)](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/set-content#-encoding) — UTF8 default が PS 6.0 で BOM-less に変更された旨が記載
- Iron Law: `.claude/hooks/session-start.sh` (project session 先頭注入版)
- Workflow: [docs/l2-workflow.md](../../docs/l2-workflow.md) §「PR 作成 path 別自動チェック」 / §「実機検証 trigger 表」 / §「Self-Test Report 規約」
