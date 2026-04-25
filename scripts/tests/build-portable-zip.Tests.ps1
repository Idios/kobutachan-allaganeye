<#
Pester v5 tests for scripts/build-portable-zip.ps1.

Run:
  Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1

CI: `.github/workflows/ci.yml` `installer-pester` job (windows runner).

Scope (#528 / #551 / #583):
  1. Invoke-Download verifies matching SHA256 / throws on mismatch.
  2. Assert-FFmpegLayout throws when the extracted archive has no `bin/`,
     returns Root/Bin/License paths when valid.
  3. Get-FFmpegSourceCommit extracts the upstream commit from valid BtbN
     asset names / throws on unexpected names.
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

Describe 'Get-FFmpegSourceCommit' {
  It 'extracts the upstream commit from a valid BtbN asset name' {
    $commit = Get-FFmpegSourceCommit -AssetName 'ffmpeg-n8.1-123-g7f5c90f77e-win64-lgpl-shared.zip'
    $commit | Should -Be '7f5c90f77e'
  }

  It 'throws when the asset name does not match the BtbN pattern' {
    { Get-FFmpegSourceCommit -AssetName 'unexpected-name.zip' } |
      Should -Throw -ExpectedMessage '*Cannot extract upstream source commit*'
  }
}

Describe 'Format-ReadmeContent' {
  It 'includes the LGPLv3 BtbN win64-lgpl-shared attribution and the source commit' {
    $readme = Format-ReadmeContent `
      -Version '0.2.0' `
      -FFmpegVersion '8.1' `
      -FFmpegBuildTag 'autobuild-2026-04-22-13-15' `
      -FFmpegSourceCommit '7f5c90f77e'

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
