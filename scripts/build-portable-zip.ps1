<#
.SYNOPSIS
Build the allaganeye Portable ZIP for Windows.

.DESCRIPTION
Downloads Python 3.11 embeddable and FFmpeg LGPLv3 static (BtbN), installs
allaganeye and its runtime dependencies into the payload, adds a .bat
launcher, and compresses everything into dist/allaganeye-v<version>-windows.zip.

Downloaded artefacts (Python embed, get-pip.py, FFmpeg zip) are pinned by URL
and verified against hard-coded SHA256 digests. A mismatch aborts the build.

The script is idempotent: build/portable and dist are cleaned at the start.

The script also exposes its main helpers as functions so Pester tests can load
them via dot-sourcing without triggering a real build:

    . ./scripts/build-portable-zip.ps1        # Version="" -> loads functions only

Pass -Version to actually run the build.

.PARAMETER Version
Semantic version string (e.g. "0.2.0") used in the output ZIP filename. When
omitted, the script loads its functions for dot-sourcing and returns without
building anything.
#>
[CmdletBinding()]
param(
  [string]$Version = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'

# Pinned versions - referenced from both the main build path and Pester tests.
$PythonVersion = '3.11.9'
$PythonEmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonEmbedSha256 = '009D6BF7E3B2DDCA3D784FA09F90FE54336D5B60F0E0F305C37F400BF83CFD3B'

$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
$GetPipSha256 = 'FEBA1C697DF45BE1B539B40D93C102C9EE9DDE1D966303323B830B06F3FBCA3C'

# FFmpeg is pinned to a specific BtbN autobuild so the same allaganeye tag ships
# the same binary and the LGPLv3 license applies uniformly across CI and Portable ZIP.
# To update: bump $FFmpegBuildTag / $FFmpegAsset / $FFmpegSha256 together.
# CI workflows (`.github/workflows/ci.yml`) must be updated with the matching
# linux64-lgpl asset at the same build tag; see docs/developer-setup.md § 9.
$FFmpegVersion = '8.1'
$FFmpegBuildTag = 'autobuild-2026-04-22-13-15'
$FFmpegAsset = 'ffmpeg-n8.1-10-g7f5c90f77e-win64-lgpl-8.1'
$FFmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFmpegBuildTag/$FFmpegAsset.zip"
$FFmpegSha256 = '230B29CD76AA194F76FB48BBF5D81CBAB8EFD7CD4FD1D7DE6500A040A8587A1C'

function Invoke-Download {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [Parameter(Mandatory = $true)][string]$OutPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256
  )
  Write-Host "Downloading $Uri"
  Invoke-WebRequest -Uri $Uri -OutFile $OutPath -UseBasicParsing
  $actual = (Get-FileHash -Algorithm SHA256 -Path $OutPath).Hash
  if ($actual -ne $ExpectedSha256.ToUpperInvariant()) {
    throw "SHA256 mismatch for ${Uri}: expected $ExpectedSha256, actual $actual"
  }
  Write-Host "  SHA256 verified: $actual"
}

function Assert-FFmpegLayout {
  <#
  Validate that an extracted BtbN FFmpeg archive has the expected layout
  (single top-level directory containing `bin/ffmpeg.exe` etc. and
  `LICENSE.txt`). Throws if the layout is wrong so the build fails loudly
  when BtbN changes their archive structure.
  Returns a PSCustomObject with Root / Bin / License paths.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$ExtractDir
  )
  $root = Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1
  if (-not $root) {
    throw "FFmpeg root directory not found under $ExtractDir"
  }
  $bin = Join-Path $root.FullName 'bin'
  $license = Join-Path $root.FullName 'LICENSE.txt'
  if (-not (Test-Path $bin)) {
    throw "FFmpeg bin directory not found: $bin"
  }
  if (-not (Test-Path $license)) {
    throw "FFmpeg LICENSE.txt not found: $license"
  }
  return [pscustomobject]@{
    Root    = $root.FullName
    Bin     = $bin
    License = $license
  }
}

function Get-FFmpegSourceCommit {
  <#
  Extract the upstream FFmpeg git commit hash from a BtbN asset name.
  BtbN assets embed it as: ffmpeg-n<version>-<count>-g<commit>-<target>-<variant>
  So users can fetch the exact source under LGPLv3 obligations.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$AssetName
  )
  if ($AssetName -match '^ffmpeg-n[^-]+-[^-]+-g([0-9a-f]+)-') {
    return $matches[1]
  }
  throw "Cannot extract upstream source commit from asset name: $AssetName"
}

function Format-ReadmeContent {
  <#
  Produce the README.txt shipped inside the Portable ZIP. Exposing this as a
  function lets Pester assert the LGPLv3 attribution + source pointers are
  present without running a full build.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$FFmpegVersion,
    [Parameter(Mandatory = $true)][string]$FFmpegBuildTag,
    [Parameter(Mandatory = $true)][string]$FFmpegSourceCommit
  )
  return @"
# allaganeye v$Version (Portable ZIP for Windows)

Python 3.11 and FFmpeg LGPL binaries are bundled alongside allaganeye.

## Usage

### Basic: drag-and-drop

Drop a video file (.mkv / .mp4 / .avi / .mov) onto ``allaganeye.bat`` and it
will split the video automatically. The command window stays open at the end so
you can read the result -- press any key to close it.

Output MP4 files and metadata.json land under ``output\`` inside this folder.

### Advanced: from a Command Prompt

If you want to pass options such as --dry-run or -o, open a Command Prompt in
this folder and run:

    allaganeye.bat split "C:\path\to\video.mkv"
    allaganeye.bat split "C:\path\to\video.mkv" --dry-run
    allaganeye.bat --version

See https://github.com/Idios/kobutachan-allaganeye for full documentation.

## Licenses

- allaganeye: MIT (see the repository LICENSE file)
- Python: PSF License (python\LICENSE.txt)
- FFmpeg: LGPLv3 (full text in ffmpeg\LICENSE.txt)
    Build:         ffmpeg n$FFmpegVersion win64-lgpl static build (BtbN/FFmpeg-Builds)
    Build tag:     $FFmpegBuildTag
    Source:        https://git.ffmpeg.org/ffmpeg.git (commit $FFmpegSourceCommit)
    Build scripts: https://github.com/BtbN/FFmpeg-Builds

allaganeye (MIT) invokes the FFmpeg binary as a separate subprocess only.
Static linking restrictions of LGPLv3 therefore do not apply to allaganeye itself.
"@
}

# Dot-sourced (no -Version): stop here so callers only get the function
# definitions. Pester tests rely on this behaviour.
if ([string]::IsNullOrEmpty($Version)) { return }

# --- Main build path below ---

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BuildDir = Join-Path $RepoRoot 'build\portable'
$DistDir = Join-Path $RepoRoot 'dist'
$PayloadName = "allaganeye-v$Version"
$PayloadDir = Join-Path $BuildDir $PayloadName
$ZipPath = Join-Path $DistDir "$PayloadName-windows.zip"

foreach ($dir in @($BuildDir, $DistDir)) {
  if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null

# 1. Python embeddable
$PythonZip = Join-Path $BuildDir 'python-embed.zip'
Invoke-Download -Uri $PythonEmbedUrl -OutPath $PythonZip -ExpectedSha256 $PythonEmbedSha256
$PythonDir = Join-Path $PayloadDir 'python'
Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force

$PthFile = Join-Path $PythonDir 'python311._pth'
Set-Content -Path $PthFile -Encoding ASCII -Value @(
  'python311.zip',
  '.',
  '..\lib',
  'import site'
)

# 2. Install pip into the embedded interpreter
$GetPipPath = Join-Path $BuildDir 'get-pip.py'
Invoke-Download -Uri $GetPipUrl -OutPath $GetPipPath -ExpectedSha256 $GetPipSha256
$PythonExe = Join-Path $PythonDir 'python.exe'
& $PythonExe $GetPipPath --no-warn-script-location --no-cache-dir

# 3. Install allaganeye + deps into payload\lib
$LibDir = Join-Path $PayloadDir 'lib'
New-Item -ItemType Directory -Force -Path $LibDir | Out-Null
& $PythonExe -m pip install `
    --target $LibDir `
    --no-compile `
    --no-warn-script-location `
    --no-cache-dir `
    $RepoRoot

# 4. FFmpeg LGPLv3 static, BtbN/FFmpeg-Builds (version-pinned)
# LGPLv3 redistribution requires shipping the license text alongside the binary
# and making the corresponding source available. We copy LICENSE.txt into the
# payload and point README at the upstream source repo.
$FFmpegZip = Join-Path $BuildDir 'ffmpeg.zip'
Invoke-Download -Uri $FFmpegUrl -OutPath $FFmpegZip -ExpectedSha256 $FFmpegSha256
$FFmpegExtract = Join-Path $BuildDir 'ffmpeg-extracted'
Expand-Archive -Path $FFmpegZip -DestinationPath $FFmpegExtract -Force
$FFmpegLayout = Assert-FFmpegLayout -ExtractDir $FFmpegExtract
$FFmpegSourceCommit = Get-FFmpegSourceCommit -AssetName $FFmpegAsset
$FFmpegDest = Join-Path $PayloadDir 'ffmpeg'
New-Item -ItemType Directory -Force -Path $FFmpegDest | Out-Null
Copy-Item -Path (Join-Path $FFmpegLayout.Bin 'ffmpeg.exe') -Destination $FFmpegDest
Copy-Item -Path (Join-Path $FFmpegLayout.Bin 'ffprobe.exe') -Destination $FFmpegDest
Copy-Item -Path $FFmpegLayout.License -Destination (Join-Path $FFmpegDest 'LICENSE.txt')

# 5. Launcher
# The launcher is ASCII-only so that it runs on any Windows code page without
# chcp munging. Keep help text in English for the same reason.
# Behaviour:
#   - double-click (no args)       -> print help + pause
#   - drag & drop of a video file  -> treat as `allaganeye split <file>` + pause
#   - explicit args via cmd        -> pass through to allaganeye + pause
$Launcher = @'
@echo off
setlocal
set PAYLOAD=%~dp0
set ALLAGANEYE_FFMPEG=%PAYLOAD%ffmpeg\ffmpeg.exe
set PATH=%PAYLOAD%ffmpeg;%PATH%

if "%~1"=="" (
  echo.
  echo allaganeye - FF14 Frontline video splitter
  echo.
  echo How to use:
  echo   1. Drag a video file ^(.mkv / .mp4 / .avi / .mov^) onto allaganeye.bat
  echo      to split it automatically.
  echo   2. From a Command Prompt:
  echo      allaganeye.bat split "C:\path\to\video.mkv"
  echo.
  echo Docs: https://github.com/Idios/kobutachan-allaganeye
  echo.
  pause
  endlocal
  exit /b 0
)

set EXT=%~x1
set IS_VIDEO=
if /i "%EXT%"==".mp4" set IS_VIDEO=1
if /i "%EXT%"==".mkv" set IS_VIDEO=1
if /i "%EXT%"==".avi" set IS_VIDEO=1
if /i "%EXT%"==".mov" set IS_VIDEO=1

if defined IS_VIDEO (
  "%PAYLOAD%python\python.exe" -m allaganeye split %*
) else (
  "%PAYLOAD%python\python.exe" -m allaganeye %*
)

echo.
pause
endlocal
'@
Set-Content -Path (Join-Path $PayloadDir 'allaganeye.bat') -Value $Launcher -Encoding ASCII

# 6. README
$Readme = Format-ReadmeContent `
  -Version $Version `
  -FFmpegVersion $FFmpegVersion `
  -FFmpegBuildTag $FFmpegBuildTag `
  -FFmpegSourceCommit $FFmpegSourceCommit
Set-Content -Path (Join-Path $PayloadDir 'README.txt') -Value $Readme -Encoding UTF8

# 7. Compress
Compress-Archive -Path $PayloadDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Built $ZipPath"
