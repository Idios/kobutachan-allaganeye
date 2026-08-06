<#
Pester v5 tests for scripts/build-portable-zip.ps1.

Run:
  Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1

CI: `.github/workflows/ci.yml` `installer-pester` job (windows runner).

Scope (#528 / #551 / #583):
  1. Invoke-Download verifies matching SHA256 / throws on mismatch.
  2. Assert-FFmpegLayout throws when the extracted archive has no `bin/`,
     returns Root/Bin/License paths when valid.
  3. Get-FFmpegSourceRef extracts the upstream commit (old BtbN naming) or
     release tag (new BtbN naming) from valid BtbN asset names / throws on
     unexpected names.
  4. Format-ReadmeContent includes the LGPLv3 attribution + BtbN /
     win64-lgpl-shared pointers required by Portable ZIP license compliance.
  5. Get-LauncherTemplate preserves the python exit code propagation idiom
     (#580: `set EXIT_CODE=%ERRORLEVEL%` + `endlocal & exit /b %EXIT_CODE%`).
  6. Script parameters: -SkipArchive switch / -Version optional for dot-source.

We dot-source build-portable-zip.ps1 without -Version so it loads the helper
functions and returns before running the real build.
#>

BeforeAll {
  $script:BuildScript = Join-Path (Join-Path $PSScriptRoot '..') 'build-portable-zip.ps1'
  . $script:BuildScript
}

Describe 'Invoke-Download' {
  BeforeAll {
    $script:TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "build-portable-zip-tests-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:TmpDir | Out-Null
  }

  AfterAll {
    if (Test-Path $script:TmpDir) {
      Remove-Item -Recurse -Force $script:TmpDir
    }
  }

  It 'emits a verified message when the downloaded file matches the expected SHA256' {
    $outPath = Join-Path $script:TmpDir 'match.bin'
    # Raw ASCII bytes for 'pester-match' (12 bytes, no BOM/newline).
    # Verified via `printf 'pester-match' | sha256sum`.
    $expected = '1FCD54F3ACE7BB354D466C56742E4DCE7879EB2D8E6AF99308A8967DBE6A9DE6'

    Mock Invoke-WebRequest {
      $bytes = [System.Text.Encoding]::ASCII.GetBytes('pester-match')
      [System.IO.File]::WriteAllBytes($OutFile, $bytes)
    }

    $output = Invoke-Download -Uri 'https://example.invalid/match' -OutPath $outPath -ExpectedSha256 $expected 6>&1
    ($output -join "`n") | Should -Match 'SHA256 verified:'
    Should -Invoke Invoke-WebRequest -Times 1 -Exactly
  }

  It 'throws when the downloaded SHA256 does not match' {
    $outPath = Join-Path $script:TmpDir 'mismatch.bin'

    Mock Invoke-WebRequest {
      $bytes = [System.Text.Encoding]::ASCII.GetBytes('pester-mismatch')
      [System.IO.File]::WriteAllBytes($OutFile, $bytes)
    }

    { Invoke-Download -Uri 'https://example.invalid/mismatch' -OutPath $outPath `
        -ExpectedSha256 '0000000000000000000000000000000000000000000000000000000000000000' } |
      Should -Throw -ExpectedMessage '*SHA256 mismatch*'
  }
}

Describe 'Assert-FFmpegLayout' {
  BeforeAll {
    $script:ExtractRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ffmpeg-layout-tests-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:ExtractRoot | Out-Null
  }

  AfterAll {
    if (Test-Path $script:ExtractRoot) {
      Remove-Item -Recurse -Force $script:ExtractRoot
    }
  }

  It 'throws when the single top-level directory has no bin/ subdirectory' {
    $noBin = Join-Path $script:ExtractRoot 'no-bin'
    New-Item -ItemType Directory -Force -Path $noBin | Out-Null
    # Simulate a BtbN-style top-level directory but without the expected bin/.
    New-Item -ItemType Directory -Force -Path (Join-Path $noBin 'ffmpeg-fake-top') | Out-Null

    { Assert-FFmpegLayout -ExtractDir $noBin } |
      Should -Throw -ExpectedMessage '*bin directory not found*'
  }

  It 'returns Root/Bin/License when the layout is valid' {
    $ok = Join-Path $script:ExtractRoot 'ok'
    New-Item -ItemType Directory -Force -Path $ok | Out-Null
    $top = Join-Path $ok 'ffmpeg-fake-top'
    New-Item -ItemType Directory -Force -Path (Join-Path $top 'bin') | Out-Null
    Set-Content -Path (Join-Path $top 'LICENSE.txt') -Value 'fake license'

    $layout = Assert-FFmpegLayout -ExtractDir $ok
    $layout.Root | Should -Be $top
    $layout.Bin | Should -Be (Join-Path $top 'bin')
    $layout.License | Should -Be (Join-Path $top 'LICENSE.txt')
  }
}

Describe 'Get-FFmpegSourceRef' {
  It 'extracts the upstream commit from a valid BtbN asset name (old format: count + commit hash)' {
    # Old BtbN naming: ffmpeg-n<version>-<count>-g<commit>-<target>-<variant>.
    # Function returns the commit hash so README.txt can point users at the
    # exact source under LGPLv3 obligations.
    $ref = Get-FFmpegSourceRef -AssetName 'ffmpeg-n8.1-123-g7f5c90f77e-win64-lgpl-shared.zip'
    $ref | Should -Be '7f5c90f77e'
  }

  It 'extracts the release tag from a valid BtbN asset name (new format: bare patch release)' {
    # New BtbN naming (since ca. 2026-05-06): ffmpeg-n<version>-<target>-<variant>.
    # Function returns the release tag (n<version>) since the commit hash is
    # no longer embedded in the asset name. Both refs let users fetch the
    # exact source under LGPLv3 obligations.
    $ref = Get-FFmpegSourceRef -AssetName 'ffmpeg-n8.1.1-win64-lgpl-shared-8.1.zip'
    $ref | Should -Be 'n8.1.1'
  }

  It 'throws when the asset name does not match the BtbN pattern' {
    { Get-FFmpegSourceRef -AssetName 'unexpected-name.zip' } |
      Should -Throw -ExpectedMessage '*Cannot extract upstream source ref*'
  }
}

Describe 'Format-ReadmeContent' {
  It 'includes the LGPLv3 BtbN win64-lgpl-shared attribution and the source commit' {
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-22-13-15' `
      -FFmpegSourceRef '7f5c90f77e'

    $readme | Should -Match 'LGPLv3'
    $readme | Should -Match 'BtbN/FFmpeg-Builds'
    # The Portable ZIP ships the shared variant (#551), so README must point
    # to the matching BtbN asset name to satisfy LGPLv3 source-availability.
    $readme | Should -Match 'win64-lgpl-shared'
    $readme | Should -Match '7f5c90f77e'
    $readme | Should -Match 'autobuild-2026-04-22-13-15'
    # Shared-build wording supersedes the old "Static linking restrictions"
    # paragraph; assert the new dynamic-linking explanation is present.
    $readme | Should -Match 'shared-build DLLs'
  }

  It '-IncludeGui:$true emits the GUI launch section and WebView2 runtime notice (#570)' {
    # When the Tauri-built allaganeye-gui.exe is bundled (Portable ZIP includes
    # both CLI .bat and GUI .exe), README.txt must instruct users to
    # double-click and warn about WebView2 Runtime dependency on older Windows.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-22-13-15' `
      -FFmpegSourceRef '7f5c90f77e' `
      -IncludeGui:$true
    $readme | Should -Match 'ダブルクリック'
    $readme | Should -Match 'WebView2 Runtime'
    $readme | Should -Match 'developer\.microsoft\.com'
  }

  It '-IncludeGui:$true emits the Tauri 2 / React 19 license entry (#570)' {
    # GUI license entry is required for the MIT + WebView2 + Tauri attribution
    # so that the dual-license structure (CLI MIT / FFmpeg LGPLv3 / GUI MIT) is
    # explicit in the user-facing README.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-22-13-15' `
      -FFmpegSourceRef '7f5c90f77e' `
      -IncludeGui:$true
    $readme | Should -Match 'Allagan Eye GUI'
    $readme | Should -Match 'Tauri 2'
  }

  It '-IncludeGui:$false (default) omits the GUI section for CLI-only ZIPs (#570)' {
    # Local dry-run / partial builds may produce CLI-only Portable ZIPs (no
    # Tauri exe). README.txt must not advertise the GUI in that case to avoid
    # user confusion. Default value of -IncludeGui is $false.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-22-13-15' `
      -FFmpegSourceRef '7f5c90f77e'
    $readme | Should -Not -Match 'WebView2 Runtime'
    $readme | Should -Not -Match 'Allagan Eye GUI'
    $readme | Should -Not -Match 'allaganeye-gui\.exe'
  }

  It 'embeds release tag as source ref for new BtbN naming format (#683)' {
    # fixture (`autobuild-2026-05-06-13-32` + `n8.1.1`) は NEW format parse
    # coverage 用で、実 `$FFmpegBuildTag` とは独立 (現 pin と drift していても OK)。
    # 新 BtbN naming (n8.1.1) では Get-FFmpegSourceRef が release tag を返し、
    # README には (ref n8.1.1) で記述される。`(commit ...)` の旧文言が残らない
    # ことも併せて verify (PR #683 review #10)。
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1'
    $readme | Should -Match '\(ref n8\.1\.1\)'
    $readme | Should -Not -Match '\(commit n8\.1\.1\)'
  }

  It '-IncludeGui:$true README documents .bat double-click as the primary GUI entry (#617)' {
    # README must explain that `.bat` double-click launches the GUI when
    # GUI exe is bundled. The phrase "ダブルクリック" + "allaganeye.bat" must
    # appear together so the new UX (issue #617) is documented for users
    # who read README.txt before running anything. README は #749 で日本語化済み。
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1' `
      -IncludeGui:$true
    $readme | Should -Match '`allaganeye\.bat`.*ダブルクリック'
  }

  It '-IncludeGui:$true README orders GUI section before drag-drop and Command Prompt sections (#617)' {
    # Per spec §3 + issue #617 doc requirement: ".bat double-click → GUI"
    # comes first, drag-drop and Command Prompt are 2-3.
    # We assert relative ordering by comparing IndexOf positions.
    # README は #749 で日本語化済みのため IndexOf 検索キーも日本語化。
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1' `
      -IncludeGui:$true
    $idxBatDoubleClick = $readme.IndexOf('最も簡単')
    $idxDragDrop = $readme.IndexOf('ドラッグ＆ドロップ')
    $idxCommandPrompt = $readme.IndexOf('コマンドプロンプトから実行')

    $idxBatDoubleClick | Should -BeGreaterThan -1
    $idxDragDrop | Should -BeGreaterThan -1
    $idxCommandPrompt | Should -BeGreaterThan -1
    $idxBatDoubleClick | Should -BeLessThan $idxDragDrop
    $idxDragDrop | Should -BeLessThan $idxCommandPrompt
  }

  It 'README documents PyInstaller frozen distribution (#752, regression guard)' {
    # #752 で Python embed が PyInstaller --onedir に置き換わったため、README から
    # "Python 3.11 と FFmpeg LGPL バイナリが同梱" / "python\LICENSE.txt" の旧 wording が
    # 消えていることを assert する。frozen bundle path (`allaganeye\_internal\`) と
    # canonical PSF license URL が新 wording で参照されていることも併せて確認。
    $readme = Format-ReadmeContent `
      -Version '0.3.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-30-13-44' `
      -FFmpegSourceRef 'n8.1.1'
    # 旧 wording は完全に消えている
    $readme | Should -Not -Match 'Python 3\.11 と FFmpeg'
    $readme | Should -Not -Match 'python\\LICENSE\.txt'
    # 新 wording が含まれる
    $readme | Should -Match 'PyInstaller frozen application'
    $readme | Should -Match 'allaganeye\\_internal\\'
    $readme | Should -Match 'docs\.python\.org/3/license\.html'
  }
}

Describe 'Get-LauncherTemplate' {
  It 'preserves python exit code via EXIT_CODE save and endlocal & exit /b idiom (#580)' {
    # Launcher must propagate python exit code so callers can chain
    # `allaganeye.bat detect file.mp4 && next-step` and CI smoke (Level B in
    # release.yml) can observe non-zero exit codes. CI smoke is the de-facto
    # regression test; this unit test is the unit-level safety net (#583).
    $template = Get-LauncherTemplate
    $template | Should -Match 'set EXIT_CODE=%ERRORLEVEL%'
    $template | Should -Match 'endlocal & exit /b %EXIT_CODE%'
  }

  It 'no-args branch launches GUI via start when allaganeye-gui.exe exists (#617)' {
    # When user double-clicks .bat without args and the GUI exe is present at
    # runtime, the dispatcher must launch the GUI asynchronously (start "") so
    # the cmd window does not linger, then exit with code 0. The if-exist +
    # start block is generated in BOTH -IncludeGui:$true (GUI bundled) and
    # -IncludeGui:$false (CLI-only) templates as a defensive runtime check;
    # -IncludeGui only controls the help text content. Default call here
    # exercises the structural element common to both variants.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if exist "%PAYLOAD%allaganeye-gui\.exe"'
    $template | Should -Match 'start "" "%PAYLOAD%allaganeye-gui\.exe"'
  }

  It 'no-args + GUI absent falls back to :show_help label (#617)' {
    # CLI-only ZIP fallback: if allaganeye-gui.exe is not bundled,
    # double-click should still display the help text + pause (preserves
    # the pre-#617 UX for that case).
    $template = Get-LauncherTemplate
    $template | Should -Match 'goto :show_help'
    $template | Should -Match '(?m)^:show_help\s*$'
  }

  It 'recognizes --help, -h, and /? as explicit help flags (#617)' {
    # Explicit help flags must reach :show_help even when GUI exe is bundled,
    # otherwise `allaganeye.bat --help` would silently launch the GUI.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if /i "%~1"=="--help"'
    $template | Should -Match 'if /i "%~1"=="-h"'
    $template | Should -Match 'if "%~1"=="/\?"'
  }

  It 'dispatches video drag-drop to PyInstaller frozen allaganeye.exe split (#752)' {
    # The video drag-drop branch must invoke the PyInstaller-frozen entry
    # point `allaganeye\allaganeye.exe split %*` so all args are forwarded.
    # Pre-#752 used `python\python.exe -m allaganeye split %*`; that path
    # is removed because the embed Python interpreter is no longer shipped.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if /i "%EXT%"==".mp4"'
    $template | Should -Match 'if /i "%EXT%"==".mkv"'
    $template | Should -Match 'if /i "%EXT%"==".avi"'
    $template | Should -Match 'if /i "%EXT%"==".mov"'
    $template | Should -Match '"%PAYLOAD%allaganeye\\allaganeye\.exe" split %\*'
    # Pre-#752 path must not linger in the template.
    $template | Should -Not -Match 'python\\python\.exe'
  }

  It 'dispatches non-video args to PyInstaller frozen allaganeye.exe (#752)' {
    # Non-video args (e.g. allaganeye.bat detect <file>, --version) must
    # also be dispatched to `allaganeye\allaganeye.exe %*` (PyInstaller frozen).
    $template = Get-LauncherTemplate
    $template | Should -Match '"%PAYLOAD%allaganeye\\allaganeye\.exe" %\*'
    $template | Should -Not -Match 'python\\python\.exe'
  }

  It '-IncludeGui:$true emits help text mentioning .bat double-click as the first option (#617)' {
    # When GUI exe is bundled, help text must mention .bat double-click as
    # the easiest entry. The literal "Double-click" + "allaganeye.bat" is
    # the canonical phrase users will read in `allaganeye.bat --help`.
    $template = Get-LauncherTemplate -IncludeGui:$true
    $template | Should -Match 'Double-click allaganeye\.bat'
  }

  It '-IncludeGui:$false (default) omits Double-click GUI mention from help text (#617)' {
    # CLI-only ZIP: help text MUST NOT advertise GUI double-click since the
    # GUI exe is not bundled. The runtime `if exist` check still appears in
    # the template as a defensive fallback, but the help text must be free
    # of the user-facing "Double-click" advertisement.
    $template = Get-LauncherTemplate
    $template | Should -Not -Match 'Double-click allaganeye\.bat'
  }
}

Describe 'Script parameters' {
  It 'exposes -SkipArchive as a switch parameter' {
    # CI sets -SkipArchive so actions/upload-artifact can zip the payload
    # folder once (#551). Regression-test: keep the switch on the param block.
    $cmd = Get-Command $script:BuildScript
    $cmd.Parameters.ContainsKey('SkipArchive') | Should -BeTrue
    $cmd.Parameters['SkipArchive'].SwitchParameter | Should -BeTrue
  }

  It 'keeps -Version optional so dot-sourcing loads functions without building' {
    # The Pester suite dot-sources the script with no arguments to load helper
    # functions; making -Version mandatory again would break this contract.
    $cmd = Get-Command $script:BuildScript
    $cmd.Parameters['Version'].Attributes |
      Where-Object { $_ -is [System.Management.Automation.ParameterAttribute] } |
      ForEach-Object { $_.Mandatory | Should -BeFalse }
  }
}

Describe 'New-IntegrityManifest' {
  BeforeAll {
    $script:ManifestTmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "manifest-test-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:ManifestTmpDir | Out-Null
  }

  AfterAll {
    if (Test-Path $script:ManifestTmpDir) {
      Remove-Item -Recurse -Force $script:ManifestTmpDir
    }
  }

  It 'enumerates files and produces valid JSON with required fields' {
    # Arrange: create a payload with files at different depths
    $f1 = Join-Path $script:ManifestTmpDir 'allaganeye.bat'
    Set-Content -Path $f1 -Value 'fake' -Encoding ASCII

    $ffDir = Join-Path $script:ManifestTmpDir 'ffmpeg'
    New-Item -ItemType Directory -Force -Path $ffDir | Out-Null
    $f2 = Join-Path $ffDir 'ffmpeg.exe'
    Set-Content -Path $f2 -Value 'fake binary' -Encoding ASCII

    $libDir = Join-Path $script:ManifestTmpDir 'lib\allaganeye\audio\refs'
    New-Item -ItemType Directory -Force -Path $libDir | Out-Null
    $f3 = Join-Path $libDir 'fanfare.npz'
    Set-Content -Path $f3 -Value 'fake npz' -Encoding ASCII

    # Act
    $json = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $manifest = $json | ConvertFrom-Json

    # Assert: schema
    $manifest.version | Should -Be 1
    # New-IntegrityManifest emits "yyyy-MM-ddTHH:mm:ssZ" verbatim into the
    # JSON string. We assert against the raw $json text rather than
    # $manifest.generated_at because PS 7 ConvertFrom-Json auto-parses ISO
    # strings into [DateTime], and `Should -Match` then coerces via culture-
    # specific ToString (e.g. "5/9/2026 2:38:26 AM" on en-US runners) which
    # the regex would reject — even though Pester's error formatter then
    # displays the value via the "o" round-trip format, masking the cause
    # (PR #702 CI repro).
    $json | Should -Match '"generated_at":\s*"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"'
    $manifest.files | Should -Not -BeNullOrEmpty

    # POSIX-style separators in path field
    $paths = @($manifest.files | ForEach-Object { $_.path })
    $paths | Should -Contain 'allaganeye.bat'
    $paths | Should -Contain 'ffmpeg/ffmpeg.exe'
    $paths | Should -Contain 'lib/allaganeye/audio/refs/fanfare.npz'

    # Each entry has size > 0 and tolerance_bytes = 0
    foreach ($entry in $manifest.files) {
      $entry.size | Should -BeGreaterThan 0
      $entry.tolerance_bytes | Should -Be 0
    }
  }

  It 'excludes integrity-manifest.json itself from the enumeration' {
    # #729 Round 1: align fake-manifest fixture encoding with sibling fixtures
    # (L360/L365/L370 all use ASCII). The exclusion test enumerates by name,
    # so the fake manifest's content / encoding is irrelevant to the assertion;
    # ASCII is the simplest consistent choice for '{}'.
    $extra = Join-Path $script:ManifestTmpDir 'integrity-manifest.json'
    Set-Content -Path $extra -Value '{}' -Encoding ASCII

    $json = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $manifest = $json | ConvertFrom-Json
    $paths = @($manifest.files | ForEach-Object { $_.path })
    $paths | Should -Not -Contain 'integrity-manifest.json'
  }

  It 'excludes *.pyc files (PR #702 実機検証 で発覚: Python が import 時に再生成 → size_mismatch)' {
    # Simulate setuptools' compiled bytecode that triggered the regression.
    $pycDir = Join-Path $script:ManifestTmpDir 'python\Lib\site-packages\_distutils_hack\__pycache__'
    New-Item -ItemType Directory -Force -Path $pycDir | Out-Null
    Set-Content -Path (Join-Path $pycDir '__init__.cpython-311.pyc') -Value 'fake bytecode' -Encoding ASCII

    # Also drop a non-pyc sibling under the same dir to confirm we only filter .pyc, not the dir.
    Set-Content -Path (Join-Path $pycDir 'sibling.txt') -Value 'kept' -Encoding ASCII

    $json = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $manifest = $json | ConvertFrom-Json
    $paths = @($manifest.files | ForEach-Object { $_.path })
    @($paths | Where-Object { $_ -like '*.pyc' }) | Should -BeNullOrEmpty
    $paths | Should -Contain 'python/Lib/site-packages/_distutils_hack/__pycache__/sibling.txt'
  }

  It 'excludes dotfile and dotdir-segment paths (PR #702 実機検証 で発覚: actions/upload-artifact strip hidden default)' {
    # Root-level dotfile.
    Set-Content -Path (Join-Path $script:ManifestTmpDir '.gitignore') -Value 'fake' -Encoding ASCII
    # Dotfile deep in a tree (mimics setuptools/_vendor/.lock).
    $vendorDir = Join-Path $script:ManifestTmpDir 'python\Lib\site-packages\setuptools\_vendor'
    New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
    Set-Content -Path (Join-Path $vendorDir '.lock') -Value 'fake' -Encoding ASCII
    # File under a dotdir segment (mimics typer/.agents/skills/typer/SKILL.md).
    $dotDir = Join-Path $script:ManifestTmpDir 'lib\typer\.agents\skills\typer'
    New-Item -ItemType Directory -Force -Path $dotDir | Out-Null
    Set-Content -Path (Join-Path $dotDir 'SKILL.md') -Value 'fake' -Encoding ASCII
    # Sibling normal file at the same depth as the dotdir (must be kept).
    $normalDir = Join-Path $script:ManifestTmpDir 'lib\typer\notdot'
    New-Item -ItemType Directory -Force -Path $normalDir | Out-Null
    Set-Content -Path (Join-Path $normalDir 'kept.md') -Value 'fake' -Encoding ASCII
    # Filename containing dots (extension) at non-leading position must be kept.
    Set-Content -Path (Join-Path $script:ManifestTmpDir 'normal.txt') -Value 'fake' -Encoding ASCII

    $json = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $manifest = $json | ConvertFrom-Json
    $paths = @($manifest.files | ForEach-Object { $_.path })

    # Excluded
    $paths | Should -Not -Contain '.gitignore'
    $paths | Should -Not -Contain 'python/Lib/site-packages/setuptools/_vendor/.lock'
    $paths | Should -Not -Contain 'lib/typer/.agents/skills/typer/SKILL.md'
    @($paths | Where-Object { $_ -match '(^|/)\.' }) | Should -BeNullOrEmpty

    # Kept
    $paths | Should -Contain 'lib/typer/notdot/kept.md'
    $paths | Should -Contain 'normal.txt'
  }

  It 'enumerates files in deterministic order (PR #702 review #5: Sort-Object FullName)' {
    # Two manifest generations on the same payload must produce byte-identical
    # JSON so build artifacts are reproducible and git diffs stay quiet.
    $json1 = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    $json2 = New-IntegrityManifest -PayloadDir $script:ManifestTmpDir
    # generated_at timestamps differ between calls; strip them before compare.
    $stripGen = { param($s) ($s -replace '"generated_at"\s*:\s*"[^"]*"', '"generated_at":"_"') }
    (& $stripGen $json1) | Should -Be (& $stripGen $json2)
  }
}

# Describe 'GetPip pinning (#681)' block was removed by #752: get-pip.py is no
# longer downloaded as PyInstaller --onedir bundles its own pip-managed venv.
# The version pin moved to scripts/installer/requirements-pyinstaller.txt and
# is covered by the `PyInstaller artifacts (#752)` block above.

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

  It 'build-portable-zip.ps1 is also saved as UTF-8 with BOM so PowerShell 5.1 can dot-source it (Round 2 extension #704)' {
    # build-portable-zip.ps1 contains 8 lines of non-ASCII Japanese comments
    # (around L93 §, L391-419 monthly snapshot bump comments). PS5.1 dot-source
    # via this Tests.ps1's BeforeAll would parse-fail without BOM, exactly the
    # same way Tests.ps1 itself failed before its BOM was added. Empirical scope
    # extension found during /iterate-review Round 2.
    $bytes = [System.IO.File]::ReadAllBytes($script:BuildScript)
    $bytes[0] | Should -Be 0xEF
    $bytes[1] | Should -Be 0xBB
    $bytes[2] | Should -Be 0xBF
  }
}


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


Describe 'Measure-PortableZipBaseline (#752)' {
  # Lazy-loaded: only test the script when it exists. Acts as TDD anchor for
  # Task 2 (script creation) without breaking the existing Pester suite that
  # is dot-sourced at BeforeAll without the new script.
  BeforeAll {
    $script:MeasureScript = Join-Path (Join-Path $PSScriptRoot '..') 'measure-portable-zip-baseline.ps1'
    $script:MeasureTmp = Join-Path ([System.IO.Path]::GetTempPath()) "measure-baseline-tests-$(New-Guid)"
    New-Item -ItemType Directory -Force -Path $script:MeasureTmp | Out-Null
    # Fake payload: 3 files across 2 top-level dirs.
    $payload = Join-Path $script:MeasureTmp 'fake-payload'
    New-Item -ItemType Directory -Force -Path $payload | Out-Null
    Set-Content -Path (Join-Path $payload 'allaganeye.bat') -Value 'bat content' -Encoding ASCII
    $libDir = Join-Path $payload 'lib\foo'
    New-Item -ItemType Directory -Force -Path $libDir | Out-Null
    Set-Content -Path (Join-Path $libDir 'foo.py') -Value '# py' -Encoding ASCII
    $ffDir = Join-Path $payload 'ffmpeg'
    New-Item -ItemType Directory -Force -Path $ffDir | Out-Null
    Set-Content -Path (Join-Path $ffDir 'fake.dll') -Value 'binary' -Encoding ASCII
    $script:FakePayload = $payload
  }
  AfterAll {
    if (Test-Path $script:MeasureTmp) {
      Remove-Item -Recurse -Force $script:MeasureTmp
    }
  }

  It 'produces JSON with required top-level schema fields' {
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    $obj = $jsonText | ConvertFrom-Json
    $obj.schema_version | Should -Be 1
    # PR #785 CI fix: PS 7+ ConvertFrom-Json auto-parses ISO 8601 strings to [DateTime],
    # whose .ToString() (implicit on Should -Match) emits culture-specific format
    # with subseconds (e.g. "2026-05-18T13:55:04.0000000Z"). Assert against raw
    # JSON text instead — same pattern as N-IntegrityManifest test at line 387.
    $jsonText | Should -Match '"measured_at":\s*"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"'
    $obj.payload_dir | Should -Be $script:FakePayload
    $obj.total_file_count | Should -Be 3
    $obj.total_size_bytes | Should -BeGreaterThan 0
  }

  It 'aggregates files by top-level directory' {
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    $obj = $jsonText | ConvertFrom-Json
    $obj.by_top_dir.lib.file_count | Should -Be 1
    $obj.by_top_dir.ffmpeg.file_count | Should -Be 1
    $obj.by_top_dir._root.file_count | Should -Be 1
  }

  It 'aggregates files by extension' {
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    $obj = $jsonText | ConvertFrom-Json
    $obj.by_extension.'.py'.count | Should -Be 1
    $obj.by_extension.'.dll'.count | Should -Be 1
    # `.bat` のような low-frequency extension は _other に分類されない (拡張子そのまま) のが望ましいが、
    # 実装簡略化のため代表的な extension (.py / .pyd / .dll / .pyi / .so) 以外は _other 集約。
    # 1 件しか fake payload に含まれていないため、`-Be 1` で double-count 等の regression を厳密検出。
    $obj.by_extension._other.count | Should -Be 1
  }

  It '-Format Human writes human-readable table to stdout' {
    $output = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Human
    ($output -join "`n") | Should -Match 'total_file_count'
    ($output -join "`n") | Should -Match '3'
  }

  It 'throws when -PayloadDir does not exist' {
    { & $script:MeasureScript -PayloadDir (Join-Path $script:MeasureTmp 'missing') -Format Json } |
      Should -Throw -ExpectedMessage '*not found*'
  }

  It 'JSON output starts with `{` (not UTF-8 BOM) so downstream parsers stay strict-compatible' {
    # Regression guard mirroring `Describe 'Integrity manifest encoding (#729)'`:
    # the measurement script itself emits text via stdout, but the CI step
    # writes the captured text to build/portable/baseline.json. The canonical
    # write pattern (`[IO.File]::WriteAllText` + UTF8Encoding($false)) is in
    # release.yml. Here we assert the script's stdout text has no BOM at
    # offset 0, so any future consumer doing `[byte[]]` inspection sees
    # `{` (0x7B) first. Defends against future refactors that pipe through
    # PS-version-dependent encoders.
    $jsonText = & $script:MeasureScript -PayloadDir $script:FakePayload -Format Json
    # & script returns string array; join to single string for byte inspection.
    $firstChar = ($jsonText -join "`n").Substring(0, 1)
    $firstChar | Should -Be '{'
  }

  # NOTE: 本 assertion は #752 PR で post-build measurement の値を hardcode する。
  # 値は CI build-windows job の baseline.json artifact から取得。
  # 旧 (develop-0.3.0 main) baseline と新 (PyInstaller --onedir) after を
  # 並べて削減率を assert することで、将来の不用意な再回帰を防ぐ。
  # Bump 時 (PyInstaller version 更新等) は本 const を再測定して上書きする。
  Context 'File count reduction floor (#752 post-merge regression guard)' {
    BeforeAll {
      # $script:RepoRoot は outer Describe 'Measure-PortableZipBaseline (#752)' の
      # BeforeAll で定義されていないため、本 Context の BeforeAll で local に定義。
      # (次の Describe 'PyInstaller artifacts (#752)' BeforeAll と同等の式)
      $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
      # 旧 (PyInstaller 移行前) baseline は conservative estimate。develop-0.3.0 main
      # の Portable ZIP は Python 3.11 embed + numpy/scipy/cv2/typer 等の pip install
      # が展開された状態で 2500+ file 程度が想定値。本 const は 2000 に conservative
      # に下げており、実値が 2500+ で reduction ratio がより大きくなれば assertion は
      # 通る (test がより緩い方向に振れるだけ)。PR push 後の CI artifact から develop
      # 比較値を取得して上書き可能。
      # Option B (estimated) を使用。理由: Python 3.11 が local 環境に未インストール
      # で local PyInstaller build を走らせられなかったため (Python 3.12 のみ available)。
      # CI build-windows job の baseline.json artifact が真値の根拠となる。
      $script:OLD_BASELINE_FILE_COUNT = 2000
      # PyInstaller --onedir output の上限。conservative estimate (実測 + buffer)。
      # PyInstaller 6.x + numpy/scipy/cv2 の onedir output は 300-400 file 規模が想定
      # (binary + Python stdlib + 3rd party shared libs のみ、site-packages の純 Python
      # source ファイル群は frozen された)。conservative に 400 を ceiling とする。
      # 実測値が 300 程度に収束した場合は本 const を 350 程度に絞ることで regression
      # を sharp に検出できるが、bump 時 false positive を避けるため余裕を持たせる。
      $script:NEW_AFTER_FILE_COUNT_CEILING = 400
      $script:RecentBaseline = Join-Path $script:RepoRoot 'build\portable\baseline.json'
    }

    It 'frozen output file count is at most NEW_AFTER_FILE_COUNT_CEILING' {
      if (-not (Test-Path $script:RecentBaseline)) {
        # ローカル build せずに Pester を回す場合 (CI lint job 等) は assertion を skip
        Set-ItResult -Skipped -Because 'build/portable/baseline.json not present (no local build); CI smoke covers this in release.yml'
        return
      }
      $obj = Get-Content $script:RecentBaseline -Raw | ConvertFrom-Json
      $obj.total_file_count | Should -BeLessOrEqual $script:NEW_AFTER_FILE_COUNT_CEILING
    }

    It 'reduction from OLD_BASELINE_FILE_COUNT is at least 80%' {
      if (-not (Test-Path $script:RecentBaseline)) {
        Set-ItResult -Skipped -Because 'build/portable/baseline.json not present (no local build); CI smoke covers this in release.yml'
        return
      }
      $obj = Get-Content $script:RecentBaseline -Raw | ConvertFrom-Json
      $reductionRatio = 1.0 - ($obj.total_file_count / $script:OLD_BASELINE_FILE_COUNT)
      $reductionRatio | Should -BeGreaterThan 0.8
    }
  }
}


Describe 'PyInstaller artifacts (#752)' {
  BeforeAll {
    $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $script:SpecFile = Join-Path $script:RepoRoot 'scripts\installer\allaganeye.spec'
    $script:ReqFile = Join-Path $script:RepoRoot 'scripts\installer\requirements-pyinstaller.txt'
  }

  It 'allaganeye.spec exists at scripts/installer/' {
    Test-Path $script:SpecFile | Should -BeTrue
  }

  It 'requirements-pyinstaller.txt exists and pins pyinstaller + hooks-contrib at exact versions' {
    Test-Path $script:ReqFile | Should -BeTrue
    $content = Get-Content $script:ReqFile -Raw
    $content | Should -Match 'pyinstaller==6\.20\.0'
    $content | Should -Match 'pyinstaller-hooks-contrib==2026\.5'
  }

  It 'allaganeye.spec references allaganeye/__main__.py as entry script (relative to spec)' {
    $spec = Get-Content $script:SpecFile -Raw
    # Relative path from scripts/installer/ to allaganeye/__main__.py is ../../allaganeye/__main__.py
    $spec | Should -Match "Analysis\(\s*\[\s*'\.\./\.\./allaganeye/__main__\.py'\s*\]"
  }

  It 'allaganeye.spec collect_data_files allaganeye.audio.refs (fanfare.npz)' {
    $spec = Get-Content $script:SpecFile -Raw
    $spec | Should -Match "collect_data_files\(\s*'allaganeye\.audio\.refs'\s*\)"
  }

  It 'allaganeye.spec disables UPX compression (Idios 2026-05-18 決定)' {
    $spec = Get-Content $script:SpecFile -Raw
    $spec | Should -Match 'upx\s*=\s*False'
    $spec | Should -Not -Match 'upx\s*=\s*True'
  }

  It 'allaganeye.spec excludes obvious unused stdlib (#752)' {
    # Size reduction: tkinter / PIL / matplotlib / pytest / sphinx は allaganeye
    # 本体および依存からは import されない。明示 exclude で frozen bundle size を
    # 削減する。bump 時に excludes リストの妥当性を再評価する trigger として
    # 本 test を用意。
    $spec = Get-Content $script:SpecFile -Raw
    $spec | Should -Match "'tkinter'"
    $spec | Should -Match "'PIL'"
    $spec | Should -Match "'matplotlib'"
    $spec | Should -Match "'pytest'"
    $spec | Should -Match "'sphinx'"
  }
}

Describe 'Dependency constraints wiring (#916)' {
  # 出荷物の依存版を CI と揃えるための配線を pin する。効かせないと build した日の
  # PyPI 最新 4.x が ZIP に入り、CI が検証した版と別物になる (#916 と同型の穴が
  # 配布側に残る)。
  #
  # bare-name の全文 scan は production comment や無関係な statement を拾って
  # false-green になるため、**statement 単位に scope してから call-form まで**
  # assert する (memory: source-scan guard は statement に scope + call-form assert)。
  BeforeAll {
    $script:ConstraintsRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $script:ConstraintsBuildScript = Join-Path $script:ConstraintsRepoRoot 'scripts\build-portable-zip.ps1'
    $script:ConstraintsFile = Join-Path $script:ConstraintsRepoRoot 'constraints.txt'

    # 行頭コメントを除去してからバッククォート継続を畳み、論理 statement にする。
    $lines = Get-Content $script:ConstraintsBuildScript
    $stripped = $lines | Where-Object { $_.Trim() -notmatch '^#' }
    $joined = ($stripped -join "`n") -replace '`\s*\n\s*', ' '
    $script:PipInstallStatements = @(
      $joined -split "`n" | Where-Object { $_ -match '-m\s+pip\s+install\b' }
    )
    # pip 自身の self-upgrade は constraints の対象外 (pip の版は固定していない。
    # 既知の残余として docs/l2-workflow.md §外部依存規約 に記載)。
    $script:PackageInstallStatements = @(
      $script:PipInstallStatements | Where-Object { $_ -notmatch 'install\s+--upgrade\s+pip\b' }
    )
  }

  It 'constraints.txt exists at repo root' {
    Test-Path $script:ConstraintsFile | Should -BeTrue
  }

  It 'finds exactly 2 package-installing pip statements (new unguarded install fails here)' {
    # 本数を pin することで、`-c` を付け忘れた 3 本目が静かに増えるのを防ぐ。
    # 増減させた場合は下の call-form assert も併せて見直すこと。
    $script:PackageInstallStatements.Count | Should -Be 2
  }

  It 'every package-installing pip statement passes -c with an absolute constraints path' {
    # 相対パス不可: build venv の cwd が repo root とは限らないため、
    # `Join-Path $RepoRoot` で絶対パス化されていることまで assert する。
    foreach ($stmt in $script:PackageInstallStatements) {
      $stmt | Should -Match '-c\s+\(Join-Path\s+\$RepoRoot\s+''constraints\.txt''\)'
    }
  }
}
