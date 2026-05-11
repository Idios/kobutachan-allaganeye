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
    $readme | Should -Match 'double-click'
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
    # GUI exe is bundled. The phrase "Double-click" + "allaganeye.bat" must
    # appear together so the new UX (issue #617) is documented for users
    # who read README.txt before running anything.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1' `
      -IncludeGui:$true
    $readme | Should -Match 'Double-click `?allaganeye\.bat`?'
  }

  It '-IncludeGui:$true README orders GUI section before drag-drop and Command Prompt sections (#617)' {
    # Per spec §3 + issue #617 doc requirement: ".bat double-click → GUI"
    # comes first, drag-drop and Command Prompt are 2-3.
    # We assert relative ordering by comparing IndexOf positions.
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-05-06-13-32' `
      -FFmpegSourceRef 'n8.1.1' `
      -IncludeGui:$true
    $idxBatDoubleClick = $readme.IndexOf('Double-click')
    $idxDragDrop = $readme.IndexOf('Drop a video file')
    $idxCommandPrompt = $readme.IndexOf('Command Prompt')

    $idxBatDoubleClick | Should -BeGreaterThan -1
    $idxDragDrop | Should -BeGreaterThan -1
    $idxCommandPrompt | Should -BeGreaterThan -1
    $idxBatDoubleClick | Should -BeLessThan $idxDragDrop
    $idxDragDrop | Should -BeLessThan $idxCommandPrompt
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

  It 'preserves case-insensitive video drag-drop dispatch (regression)' {
    # The video drag-drop branch (existing pre-#617 behavior) must remain.
    # All four video extensions are case-insensitive (if /i) and the script
    # invokes `python -m allaganeye split %*` to preserve full arg pass-through.
    $template = Get-LauncherTemplate
    $template | Should -Match 'if /i "%EXT%"==".mp4"'
    $template | Should -Match 'if /i "%EXT%"==".mkv"'
    $template | Should -Match 'if /i "%EXT%"==".avi"'
    $template | Should -Match 'if /i "%EXT%"==".mov"'
    $template | Should -Match '"%PAYLOAD%python\\python\.exe" -m allaganeye split %\*'
  }

  It 'preserves CLI passthrough for non-video args (regression)' {
    # Non-video args (e.g. allaganeye.bat detect <file>, --version) must
    # still be dispatched to `python -m allaganeye %*`.
    $template = Get-LauncherTemplate
    $template | Should -Match '"%PAYLOAD%python\\python\.exe" -m allaganeye %\*'
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
    $extra = Join-Path $script:ManifestTmpDir 'integrity-manifest.json'
    Set-Content -Path $extra -Value '{}' -Encoding UTF8

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

Describe 'GetPip pinning (#681)' {
  It 'pins $GetPipUrl to a versioned pypa/get-pip GitHub raw URL' {
    # bootstrap.pypa.io/get-pip.py is unversioned and PyPA refreshes it without
    # notice, drifting our hardcoded SHA pin and breaking build-windows CI
    # (#649, PR #675 Round 2). #681 pins the URL to a versioned pypa/get-pip
    # GitHub raw URL whose content is immutable per release tag.
    # This regression test guards against accidental rollback to the
    # unversioned bootstrap.pypa.io URL.
    $GetPipUrl | Should -Match '^https://raw\.githubusercontent\.com/pypa/get-pip/[\w.\-]+/public/get-pip\.py$'
  }

  It 'pins $GetPipSha256 to the literal value matching the pypa/get-pip 26.1.1 tag' {
    # SHA256 verify (Invoke-Download) stays as defense-in-depth even with the
    # immutable URL: catches the (very unlikely) force-push scenario on the
    # upstream pypa/get-pip release tag.
    # value-equality lock so any accidental SHA edit without a corresponding
    # URL tag bump is caught at test time, not at CI build-windows time.
    $GetPipSha256 | Should -Be '66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76'
  }
}

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
