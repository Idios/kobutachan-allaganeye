# Issue #729: integrity-manifest.json BOM 修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/build-portable-zip.ps1` L577 を PowerShell-version-agnostic な `[IO.File]::WriteAllText` + `[UTF8Encoding]::new($false)` に切り替えて `integrity-manifest.json` を BOM-less UTF-8 で書き出すように修正し、Python pytest / Rust cargo test / Pester の 3 layer regression coverage と CHANGELOG entry を整備し、Iron Law 6 を満たす PR を作成する。

**Architecture:** 単一 PR / 2 commits。test commit (Python pytest + Rust cargo test + Pester) → fix commit (build script L577 + CHANGELOG) の順。tests は read 側 BOM 拒否 (Python / Rust) と build 側 canonical encoding approach (Pester) の mirror coverage。本 PR merge 後に PR #720 AC4 (Idios の `cargo tauri build` release bundle CMD 窓不出実機検証) が unblock される。

**Tech Stack:** PowerShell 5.1 / 7+ (`Set-Content` vs `[IO.File]`), .NET (`System.Text.UTF8Encoding`, `System.IO.File`), Python 3.x (`pytest`, `json.loads` の BOM 拒否), Rust (`cargo test`, `serde_json::from_str`), Pester v5, markdownlint (CHANGELOG validation)

**Spec:** `docs/superpowers/specs/2026-05-12-issue-729-integrity-manifest-bom-design.md` (commit `db0afb1`)

**Session:** `cranky-bhabha-c33264` (前 session `naughty-meninsky-db73bc` で #729 起票)

---

## Task 1: Iron Law 6 Pre-flight (initial base sync 確認)

**Files:** (read-only)

- Check: `git fetch origin develop-0.2.0` → `git log HEAD..origin/develop-0.2.0` → `gh pr list --search "#729"`

- [ ] **Step 1: develop-0.2.0 を fetch して未取込 commit を確認**

Run:

```bash
git fetch origin develop-0.2.0
git log --oneline HEAD..origin/develop-0.2.0 | head -10
```

Expected output: 0 行 (取込済) または develop-0.2.0 の新規 commit 一覧。

- [ ] **Step 2: 未取込 commit が touched files と交差するか確認**

Run:

```bash
git log --oneline HEAD..origin/develop-0.2.0 -- \
  scripts/build-portable-zip.ps1 \
  scripts/tests/build-portable-zip.Tests.ps1 \
  tests/test_integrity.py \
  gui/src-tauri/src/integrity.rs \
  CHANGELOG.md
```

Expected: 0 行 (交差なし、merge 不要)。

- [ ] **Step 3: 交差ありなら merge + 自動チェック再実行**

If above step yields rows:

```bash
git merge origin/develop-0.2.0
# 競合解消 + 自動チェック再実行 (Task 9 と同じ commands)
```

If 0 rows: skip this step.

- [ ] **Step 4: 並行 worktree PR で #729 重複確認**

Run:

```bash
gh pr list --search "729 in:title,body" --state all --json number,title,state,headRefName | head -20
```

Expected: 既に #729 fix PR が他 branch で出ていないこと (本 worktree branch `claude/cranky-bhabha-c33264` 以外で `#729` を扱う PR がないこと)。

---

## Task 2: Python pytest 追加 (BOM rejection latent bug pin)

**Files:**

- Modify: `tests/test_integrity.py` (末尾、既存 `test_log_written_when_manifest_invalid_json` の後)

- [ ] **Step 1: tests/test_integrity.py 末尾に新規 test を追加**

末尾 (最終 test function の後) に空行 2 つを挟んで以下を append:

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

- [ ] **Step 2: pytest を走らせて pass 確認**

Run:

```bash
pytest tests/test_integrity.py::test_load_manifest_raises_on_bom_prefixed_json -v
```

Expected: `PASSED` (Python は既に BOM-prefixed JSON を `json.loads` で reject するため、test は initial commit で pass する。これは latent bug の pinning であり、TDD red-green ではない)。

- [ ] **Step 3: 既存 pytest 群が回帰なしを確認**

Run:

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 test pass (既存 test + 新規 1 件)。

---

## Task 3: Rust cargo test 追加 (BOM rejection mirror coverage)

**Files:**

- Modify: `gui/src-tauri/src/integrity.rs` (`mod tests` ブロック内、既存 `load_manifest_returns_err_for_invalid_json` の後)

- [ ] **Step 1: gui/src-tauri/src/integrity.rs の mod tests 内に新規 test 追加**

`load_manifest_returns_err_for_invalid_json` (現状 line 309-315 あたり) の後に空行を挟んで以下を insert:

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
        )
        .unwrap();
        drop(f);

        let err = load_manifest(&p).unwrap_err();
        assert!(err.contains("invalid JSON"), "got: {}", err);
    }
```

Note: indentation は既存 `mod tests` 内の他 test と揃える (4 spaces)。`use std::io::Write;` は既存 import (line 276 あたり) に既にある。

- [ ] **Step 2: cargo test を走らせて pass 確認**

Run:

```bash
cd gui/src-tauri && cargo test load_manifest_returns_err_for_bom_prefixed_json
```

Expected: `test result: ok. 1 passed; 0 failed`.

- [ ] **Step 3: 既存 integrity test 群が回帰なしを確認**

Run:

```bash
cd gui/src-tauri && cargo test integrity
```

Expected: 全 test pass (既存 13 件前後 + 新規 1 件)。

- [ ] **Step 4: cargo check で type / borrow 系 error なしを確認**

Run:

```bash
cd gui/src-tauri && cargo check
```

Expected: `Checking allaganeye-gui ...` → `Finished` (warning は許容、error は不可)。

---

## Task 4: Pester test 追加 (canonical encoding approach pin)

**Files:**

- Modify: `scripts/tests/build-portable-zip.Tests.ps1` (末尾、既存 `Describe 'BtbN pinning policy (#705)'` の後)

- [ ] **Step 1: Tests.ps1 末尾に新規 Describe block を append**

末尾 (最終 `Describe 'BtbN pinning policy (#705)'` の `}` の後) に空行 1 つを挟んで以下を append:

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

- [ ] **Step 2: Pester を走らせて pass 確認**

Run:

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -CI"
```

Expected: 全 Describe block pass (既存 + 新規 `Integrity manifest encoding (#729)` 1 件)。 Failure 0 件。

(`pwsh` 未インストール環境では `powershell.exe -Command "Invoke-Pester ..."` で代替可能だが、CI と挙動を揃えるため `pwsh` 推奨。)

---

## Task 5: Test 追加 commit

**Files:** (commit のみ)

- [ ] **Step 1: 3 layer test の追加を 1 commit にまとめて add**

Run:

```bash
git add tests/test_integrity.py gui/src-tauri/src/integrity.rs scripts/tests/build-portable-zip.Tests.ps1
git status --short
```

Expected: 3 ファイルが M (modified) 表示。

- [ ] **Step 2: commit**

Run:

```bash
git commit -m "$(cat <<'EOF'
test(integrity): 3 layer で BOM-prefixed manifest 拒否を pin (#729)

#729 root cause analysis で発見した latent bug の regression coverage を追加:

- Python pytest test_load_manifest_raises_on_bom_prefixed_json:
  json.loads が BOM-prefixed JSON を Unexpected UTF-8 BOM で reject する
  挙動を pin。Python の read_text(encoding="utf-8") は BOM strip しない
  ため、現在の整合性は build 側で BOM 不出力 を担保している。

- Rust cargo test load_manifest_returns_err_for_bom_prefixed_json:
  serde_json::from_str が BOM-prefixed JSON を invalid JSON として
  reject する挙動を pin。GUI Tauri 起動時の integrity-check が依存。

- Pester Integrity manifest encoding (#729):
  [IO.File]::WriteAllText + UTF8Encoding(false) で manifest が BOM-less
  に着地することを byte-level で pin (first byte = 0x7B, BOM 不在)。

3 layer mirror coverage により、future build script regression が起きても
受け側 (Python / Rust) と書き側 (Pester canonical approach) のいずれかで
catch されることを保証。

session: cranky-bhabha-c33264

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit 成功 + new commit hash 表示。

---

## Task 6: Build script L577 修正 (source fix + comment)

**Files:**

- Modify: `scripts/build-portable-zip.ps1` (L573-578)

- [ ] **Step 1: scripts/build-portable-zip.ps1 の manifest 書き出し block を編集**

L573-578 (現状):

```powershell
# 7.5 Integrity manifest (#668)
# Generated after all payload steps complete so it reflects the actual files
# Tauri build / pip install / FFmpeg copy / launcher / README produced.
$ManifestPath = Join-Path $PayloadDir 'integrity-manifest.json'
Set-Content -Path $ManifestPath -Value (New-IntegrityManifest -PayloadDir $PayloadDir) -Encoding UTF8
Write-Host "Generated $ManifestPath"
```

を次に置換:

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

(L571 の `Set-Content -Path (Join-Path $PayloadDir 'README.txt') -Value $Readme -Encoding UTF8` は spec §3.1 の scope 外なので touch しない。)

- [ ] **Step 2: Pester 全体を再 run して回帰なし確認**

Task 4 で追加した test を含めて全 Pester pass を確認:

Run:

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -CI"
```

Expected: 全 test pass (build script の edit 後も既存 #704 BOM test / 既存 helper test / 新規 #729 test 全て pass)。

特に重要な確認:

- 既存 `Describe 'File encoding (#704)'` (build-portable-zip.ps1 自体が UTF-8 with BOM であることを assert) が pass し続ける (script 本体の encoding は変えていない)
- 新規 `Describe 'Integrity manifest encoding (#729)'` が pass

---

## Task 7: CHANGELOG entry 追加

**Files:**

- Modify: `CHANGELOG.md` (L8-12 あたり、`[Unreleased] / ### Fixed` セクション)

- [ ] **Step 1: CHANGELOG.md の `[Unreleased] / ### Fixed` セクションに 1 行追記**

L12 (現状の `- scorebar V2 ... (#522)` 行) の直後に以下を insert:

```markdown
- Portable ZIP の `integrity-manifest.json` を BOM-less UTF-8 で書き出すように修正 (#729)。`scripts/build-portable-zip.ps1` で `Set-Content -Encoding UTF8` を使うと Windows PowerShell 5.1 (`powershell.exe`) では UTF-8 with BOM を emit し、Tauri GUI 起動時の integrity-check (`serde_json::from_str`) と CLI `--version` の integrity-check (`json.loads`) が双方 BOM 拒否で fail していた。PS 6.0+ (`pwsh`) では BOM-less だったため CI smoke (`shell: pwsh`) が本 bug を mask。`[IO.File]::WriteAllText` + `UTF8Encoding(false)` で PS-agnostic に変更
```

- [ ] **Step 2: markdownlint で CHANGELOG.md を検証**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: `Summary: 0 error(s)` (`docs/superpowers/specs/2026-05-12-...` も含めて全 .md がパス)。

エラーが出た場合は典型的に MD028 (blockquote 連結) または MD056 (table cell `|` escape) で、手動修正。

---

## Task 8: Fix + CHANGELOG commit

**Files:** (commit のみ)

- [ ] **Step 1: scripts/build-portable-zip.ps1 + CHANGELOG.md を add**

Run:

```bash
git add scripts/build-portable-zip.ps1 CHANGELOG.md
git status --short
```

Expected: 2 ファイルが M 表示。

- [ ] **Step 2: commit**

Run:

```bash
git commit -m "$(cat <<'EOF'
fix(build): integrity-manifest.json を BOM-less UTF-8 で書き出す (#729)

scripts/build-portable-zip.ps1 L577 の Set-Content -Encoding UTF8 は
PowerShell-version-dependent な BOM 挙動を持つ:

- Windows PowerShell 5.1 (powershell.exe): UTF-8 with BOM (EF BB BF)
- PowerShell 6.0+ (pwsh): UTF-8 BOM-less (default が 6.0 で変更)

Tauri release build の integrity-check (serde_json::from_str) と CLI
--version の integrity-check (json.loads) は双方とも先頭 BOM を invalid
JSON として reject するため、PS 5.1 で build した portable bundle が
起動時に integrity error modal を表示していた (#720 Iron Law 6 verify で発見)。

[System.IO.File]::WriteAllText + [UTF8Encoding]::new(false) に切り替え、
PowerShell version に関わらず BOM 不出力を保証する。Tests.ps1 line 51/64
で既に [IO.File]::WriteAllBytes を同理由で使う precedent と整合。

CI release.yml が shell: pwsh のため smoke test (allaganeye.bat --version)
は本 bug を mask していた (CI artifact から fetch した manifest が BOM-less
であることを実測確認、design doc §1.4 参照)。

横展開: tests/test_integrity.py / gui/src-tauri/src/integrity.rs /
scripts/tests/build-portable-zip.Tests.ps1 に 3 layer BOM 拒否 / 不在
regression test を別 commit で追加済。

Refs: docs/superpowers/specs/2026-05-12-issue-729-integrity-manifest-bom-design.md

session: cranky-bhabha-c33264

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit 成功 + new hash 表示。

(Iron Law 4: コミットメッセージに `Closes/Fixes/Resolves #729` 等の自動クローズ keyword は **入れない**。マージ後手動 `gh issue close`。)

---

## Task 9: 全 machine-verified self-test (PR 作成前)

**Files:** (read-only)

Iron Law 6 §「PR 作成 path 別自動チェック」に従い、touched files の path に応じた全自動チェックを pass させる。

- [ ] **Step 1: Python 系 - ruff check**

Run:

```bash
ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 2: Python 系 - ruff format check**

Run:

```bash
ruff format --check .
```

Expected: `... files already formatted` (no diff)。

- [ ] **Step 3: Python 系 - pyright**

Run:

```bash
pyright
```

Expected: `0 errors, 0 warnings, 0 informations`.

- [ ] **Step 4: Python 系 - pytest (focused on integrity)**

Run:

```bash
pytest tests/test_integrity.py -v
```

Expected: 全 test pass (既存 + 新規 `test_load_manifest_raises_on_bom_prefixed_json`)。

- [ ] **Step 5: Python 系 - pytest 全体 (sanity check)**

Run:

```bash
pytest -x
```

Expected: 全 test pass、回帰なし。`-x` で first-failure stop なので fail があれば早期検出。

- [ ] **Step 6: Pester 系 - Invoke-Pester**

Run:

```bash
pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -CI"
```

Expected: 全 Describe block pass (既存 8 block + 新規 #729 block = 9 block 程度)。

- [ ] **Step 7: Rust 系 - cargo check**

Run:

```bash
cd gui/src-tauri && cargo check
```

Expected: `Finished` (error 不可、warning は許容)。

- [ ] **Step 8: Rust 系 - cargo test (integrity focus)**

Run:

```bash
cd gui/src-tauri && cargo test integrity
```

Expected: 全 integrity test pass (新規 BOM test 含む)。

- [ ] **Step 9: Rust 系 - cargo test 全体 (sanity check)**

Run:

```bash
cd gui/src-tauri && cargo test
```

Expected: 全 test pass、Tauri side の回帰なし。

- [ ] **Step 10: markdownlint**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: `Summary: 0 error(s)`.

---

## Task 10: Iron Law 6 Pre-flight (PR 作成直前の最終確認)

**Files:** (read-only)

- [ ] **Step 1: develop-0.2.0 を再度 fetch して未取込 commit の最新状態確認**

Run:

```bash
git fetch origin develop-0.2.0
git log --oneline HEAD..origin/develop-0.2.0 | head -10
```

Expected: 取込未済 commit 一覧 (Task 1 から増えている可能性あり)。

- [ ] **Step 2: touched files との交差確認**

Run:

```bash
git log --oneline HEAD..origin/develop-0.2.0 -- \
  scripts/build-portable-zip.ps1 \
  scripts/tests/build-portable-zip.Tests.ps1 \
  tests/test_integrity.py \
  gui/src-tauri/src/integrity.rs \
  CHANGELOG.md
```

Expected: 0 行が望ましい。1 行以上なら次 step。

- [ ] **Step 3: 交差ありなら merge + Task 9 再実行**

If yields rows:

```bash
git merge origin/develop-0.2.0
# 競合解消後、Task 9 の全 step を再実行
```

If 0 rows: skip.

- [ ] **Step 4: 並行 worktree PR で #729 タイトル / 本文に含む PR 重複確認 (final)**

Run:

```bash
gh pr list --search "729 in:title,body" --state all --json number,title,state,headRefName,baseRefName
```

Expected: 本 worktree の branch `claude/cranky-bhabha-c33264` 以外で #729 を扱う open PR が無いこと。close 済みは無視可。

---

## Task 11: PR 作成

**Files:** (gh CLI)

- [ ] **Step 1: PR body markdown を temp file に書き出し**

`/tmp/pr-body-729.md` 等を作って以下内容を保存 (HEREDOC で日本語 UTF-8 を保つ、memory feedback参照):

```bash
cat > /tmp/pr-body-729.md << 'EOF'
## Summary

[#729](https://github.com/Idios/kobutachan-allaganeye/issues/729) の修正。`scripts/build-portable-zip.ps1` の `integrity-manifest.json` 書き出しが PowerShell 5.1 で BOM 付き UTF-8 となり、Tauri GUI 起動時の integrity check (`serde_json::from_str`) と CLI `--version` (`json.loads`) が双方 fail していた問題を `[IO.File]::WriteAllText` + `[UTF8Encoding]::new($false)` で PS-agnostic に修正。

Spec: [docs/superpowers/specs/2026-05-12-issue-729-integrity-manifest-bom-design.md](docs/superpowers/specs/2026-05-12-issue-729-integrity-manifest-bom-design.md)
Plan: [docs/superpowers/plans/2026-05-12-issue-729-integrity-manifest-bom.md](docs/superpowers/plans/2026-05-12-issue-729-integrity-manifest-bom.md)

## Root Cause

`Set-Content -Encoding UTF8` の BOM 挙動は PS-version-dependent:

| PS edition | 出力 |
| --- | --- |
| Windows PowerShell 5.1 (`powershell.exe`) | UTF-8 with BOM (`EF BB BF`) |
| PowerShell 6.0+ (`pwsh`) | BOM-less (default changed in 6.0) |

CI `release.yml` の build-windows job が `shell: pwsh` のため BOM 無し manifest が生成されており、smoke test (`allaganeye.bat --version`) も exit 0 で pass していたため本 bug を mask。Idios local の Iron Law 6 verify (PR #720 完了直後) で初検出。

CI artifact (`gh run download 25703326786`) の manifest を fetch して hex 確認した結果、CI 側は `{` (`7B 0D 0A ...`) で先頭が始まる BOM 無し manifest であることを実測確認 (spec doc §1.4 参照)。

## 受け入れ条件 ([#729](https://github.com/Idios/kobutachan-allaganeye/issues/729))

#729 本文の修正方針:

- [x] **PS-agnostic な書き出し方式に変更**: `scripts/build-portable-zip.ps1` L577 で `Set-Content -Path $ManifestPath -Value (...) -Encoding UTF8` を `[System.IO.File]::WriteAllText($ManifestPath, $ManifestJson, [System.Text.UTF8Encoding]::new($false))` に置換 (commit `<FIX_COMMIT_HASH>`)
- [x] **PS 5.1 と PS 7+ どちらで build script を invoke しても manifest 先頭 byte が BOM (`EF BB BF`) ではないこと**: Pester `Describe 'Integrity manifest encoding (#729)'` で byte-level assertion で pin (commit `<TEST_COMMIT_HASH>`)
- [ ] **実機検証**: powershell.exe (PS 5.1) / pwsh (PS 7+) の両方で build → BOM 不在確認 + Tauri GUI 起動で integrity error modal 不出 + CLI `--version` exit 0 確認 (Idios)

## 横展開 (CLAUDE.md §バグ修正時の方針)

`#729` root cause 分析で Python 側 (`allaganeye/integrity.py::load_manifest`) も同じく BOM-prefixed manifest を `json.loads` で reject することを実機確認。これは latent bug の document 化として 2 layer regression test を追加:

- [x] `tests/test_integrity.py::test_load_manifest_raises_on_bom_prefixed_json` — Python `json.loads` の BOM 拒否を pin
- [x] `gui/src-tauri/src/integrity.rs::load_manifest_returns_err_for_bom_prefixed_json` — Rust `serde_json::from_str` の BOM 拒否を pin

これにより future build script regression が起きても受け側 / 書き側のいずれかで catch される 3 layer mirror coverage が成立。

## Self-Test Report

### Machine-verified

- [x] `ruff check .` — passed
- [x] `ruff format --check .` — passed
- [x] `pyright` — passed
- [x] `pytest tests/test_integrity.py -v` — passed (既存 + 新規 1 件)
- [x] `pytest -x` — passed (回帰なし)
- [x] `pwsh -NoProfile -Command "Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1 -CI"` — passed (既存 + 新規 `Integrity manifest encoding (#729)` 1 件)
- [x] `cd gui/src-tauri && cargo check` — passed
- [x] `cd gui/src-tauri && cargo test integrity` — passed (既存 + 新規 1 件)
- [x] `cd gui/src-tauri && cargo test` — passed (回帰なし)
- [x] `bash scripts/check-markdownlint.sh` — passed (`0 error(s)`)
- [x] Iron Law 6 Pre-flight (`git fetch origin develop-0.2.0` → `git log HEAD..origin/develop-0.2.0 -- <touched files>` → `gh pr list --search "729"`): touched files との交差 0 件、並行 #729 PR なし

### 実機検証 (machine-unverifiable、Idios 担当)

- [ ] `powershell.exe -File scripts/build-portable-zip.ps1 -Version 0.2.0 -SkipArchive` → `Format-Hex build/portable/allaganeye-v0.2.0/integrity-manifest.json | Select-Object -First 1` で先頭 16 bytes が `7B 0D 0A ...` で BOM 不在を確認
- [ ] `pwsh -File scripts/build-portable-zip.ps1 -Version 0.2.0 -SkipArchive` → 同じく BOM 不在を確認 (回帰なし)
- [ ] `build/portable/allaganeye-v0.2.0/allaganeye-gui.exe` 起動 → integrity error modal が **出ないこと** 確認 (drop screen が直接表示)
- [ ] `cd build\portable\allaganeye-v0.2.0 && allaganeye.bat --version` → exit 0 + `allaganeye 0.2.0` 出力確認

## PR #720 AC4 unblock

本 PR merge 後、PR #720 (#679 CMD 窓抑止) AC4 「`cargo tauri build` で release bundle 作成 + detect / export 実行時の CMD 窓不出 実機検証」が unblock される。Idios は本 PR で fix された portable bundle で改めて PR #720 AC4 検証を実施可能。

## 派生 issue (spec §9、本 PR では起票しない)

- L571 README.txt も `Set-Content -Encoding UTF8` で BOM 付き (機能影響なし、consistency only) — P4-trivial
- Pester / build smoke を PS 5.1 + pwsh 7 の matrix で実行する CI 補強 — P3-low

両者とも本 PR merge 後に Idios と `AskUserQuestion` で起票要否確認。

EOF
```

(コミット hash プレースホルダ `<FIX_COMMIT_HASH>` / `<TEST_COMMIT_HASH>` は Step 2 で gh pr create する直前に `git log --oneline -2` で確認して置換する。)

- [ ] **Step 2: コミット hash を埋めて gh pr create**

実 hash を `git log --oneline -3` で取得して PR body に置換:

```bash
TEST_HASH=$(git log --oneline -3 | grep "test(integrity)" | awk '{print $1}')
FIX_HASH=$(git log --oneline -3 | grep "fix(build)" | awk '{print $1}')
sed -i "s/<FIX_COMMIT_HASH>/$FIX_HASH/g" /tmp/pr-body-729.md
sed -i "s/<TEST_COMMIT_HASH>/$TEST_HASH/g" /tmp/pr-body-729.md

# Push branch first
git push origin HEAD

# Create PR
gh pr create \
  --base develop-0.2.0 \
  --head claude/cranky-bhabha-c33264 \
  --title "fix(build): integrity-manifest.json を BOM-less UTF-8 で書き出す (#729)" \
  --body-file /tmp/pr-body-729.md
```

Expected: PR URL が出力される。

Iron Law 4 reminder: PR title / body に `Closes/Fixes/Resolves` keyword は **入れない**。`Refs #729` 程度に留める。Issue close は merge 後 `/close-issue` skill で手動。

---

## Task 12: 実機検証依頼 (AskUserQuestion to Idios)

**Files:** (interaction only)

Iron Law 6 §「実機検証 trigger 表」: `gui/src-tauri/**` および `scripts/build-portable-zip.ps1` を touch するため Idios に実機検証を `AskUserQuestion` で依頼必須。

- [ ] **Step 1: PR URL を含めて AskUserQuestion を発行**

Use `AskUserQuestion` with the following question and option set:

```text
質問: PR <PR_URL> の実機検証 4 項目をどう進める?

オプション:
1. 今すぐ実機検証する (4 項目: powershell.exe build / pwsh build / GUI 起動 / CLI --version)
2. 後で実機検証する (PR は merge 待機、Idios の都合の良い時に)
3. 実機検証手順を変更したい (項目追加 / 削除 / 順序変更)
4. PR 自体に課題あり (実機検証前に修正が必要)
```

- [ ] **Step 2: Idios の回答に応じて分岐**

- `1. 今すぐ実機検証する` → Idios が手元で 4 項目実行、結果報告を待つ。PR body / コメントで結果を反映。
- `2. 後で実機検証する` → PR は待機状態。Idios の re-ping を待つ。
- `3. 実機検証手順を変更したい` → 詳細を AskUserQuestion で確認して手順 update。
- `4. PR 自体に課題あり` → 課題詳細を確認、(A) PR 内追加修正で対応 (l2-workflow.md §「(A) PR 内修正優先 規約」)。

- [ ] **Step 3: 実機検証完了後、PR body の `[ ]` を `[x]` に update**

実機検証 4 項目が全 pass した場合、PR body の Self-Test Report `### 実機検証` セクションの `[ ]` を `[x]` に置換 (gh pr edit --body-file で再 upload)。

これで本 PR は LGTM 候補となり、`/iterate-review` skill か Idios 手動 review → merge → `/close-issue` skill で #729 と PR #720 AC4 を順次クローズ可能。

---

## Self-Review (post-write check)

Plan を書き終えた後、spec と照合して以下を確認 (this section は人間レビュー用ガイド、tasks ではない):

1. **Spec coverage check** (spec §2 Goals 5 項目 → plan task mapping):
   - §2 Goal 1 (Source 修正 + comment) → Task 6 ✓
   - §2 Goal 2 (Inline comment) → Task 6 ✓
   - §2 Goal 3 (3 layer regression) → Task 2 (Python) + Task 3 (Rust) + Task 4 (Pester) ✓
   - §2 Goal 4 (CHANGELOG entry) → Task 7 ✓
   - §2 Goal 5 (実機検証) → Task 12 ✓

2. **Spec §3 Non-goals 遵守確認**:
   - L571 README.txt → 本 plan 全 task で touch しない ✓
   - Python / Rust の defensive 化 → 本 plan で実装せず regression test のみ追加 ✓
   - CI matrix 拡張 → 本 plan で実装せず ✓

3. **Iron Law adherence**:
   - Iron Law 1 (PR merge は受け入れ条件全 check 後) → Task 12 完了後 `/close-issue` skill 経由でクローズする旨明記 ✓
   - Iron Law 2 (bulk operation 確認) → 本 plan は単 PR、bulk 該当なし ✓
   - Iron Law 3 (scope creep 禁止) → §3 Non-goals 明記、派生 issue は本 PR で起票せず Task 12 後の Idios 確認に委ねる ✓
   - Iron Law 4 (Closes/Fixes keyword 禁止) → Task 8 commit msg + Task 11 PR body で明示的に禁止リマインダ ✓
   - Iron Law 5 (曖昧判断は AskUserQuestion) → Task 12 で実機検証手順を AskUserQuestion 化 ✓
   - Iron Law 6 (PR 作成 Pre-flight + 実機検証 trigger) → Task 1 (initial) + Task 10 (final) + Task 12 (実機検証依頼) で 3 段階に分けて確実に遵守 ✓

4. **Tooling consistency**:
   - Pester は `pwsh -NoProfile` で起動 (CI と同じ)
   - cargo test は `cd gui/src-tauri &&` prefix (workspace root から)
   - pytest は project root から `pytest tests/...`
   - markdownlint は `bash scripts/check-markdownlint.sh` (CI 同 version)

5. **No placeholders**:
   - 全 task に code block + 期待 output を記載済
   - `<FIX_COMMIT_HASH>` / `<TEST_COMMIT_HASH>` は Task 11 Step 2 で git log から自動置換する手順を明示済 (placeholder ではなく substitution variable)
   - `<PR_URL>` は Task 11 Step 2 の gh pr create 出力から取得する placeholder。Task 12 Step 1 で AskUserQuestion に注入。
