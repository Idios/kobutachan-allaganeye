<#
.SYNOPSIS
Build the allaganeye Portable ZIP for Windows.

.DESCRIPTION
Downloads Python 3.11 embeddable and FFmpeg LGPLv3 shared (BtbN), installs
allaganeye and its runtime dependencies into the payload, adds a .bat
launcher, and compresses everything into dist/allaganeye-v<version>-windows.zip.

Downloaded artefacts (Python embed, get-pip.py, FFmpeg zip) are pinned by URL
and verified against hard-coded SHA256 digests. A mismatch aborts the build.

The FFmpeg zip is cached in $env:ALLAGANEYE_BUILD_CACHE_DIR when that variable
is set. CI populates that directory with actions/cache so the ~85MB BtbN zip
is downloaded only on cache miss.

The script is idempotent: build/portable and dist are cleaned at the start.

The script also exposes its main helpers as functions so Pester tests can load
them via dot-sourcing without triggering a real build:

    . ./scripts/build-portable-zip.ps1        # Version="" -> loads functions only

Pass -Version to actually run the build.

.PARAMETER Version
Semantic version string (e.g. "0.2.0") used in the output ZIP filename. When
omitted, the script loads its functions for dot-sourcing and returns without
building anything.

.PARAMETER SkipArchive
If specified, leave the expanded payload under build/portable/allaganeye-v<version>/
and do not create the final zip. CI passes this so actions/upload-artifact can
zip the payload folder once, avoiding a "zip inside a zip" artifact. Local
dry-run invocations omit this switch and still get dist/allaganeye-v*-windows.zip.
Ignored when -Version is omitted (dot-sourcing path).
#>
[CmdletBinding()]
param(
  [string]$Version = '',
  [switch]$SkipArchive
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'

# Pinned versions - referenced from both the main build path and Pester tests.
$PythonVersion = '3.11.9'
$PythonEmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonEmbedSha256 = '009D6BF7E3B2DDCA3D784FA09F90FE54336D5B60F0E0F305C37F400BF83CFD3B'

$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
# #649 -- PyPA refreshes get-pip.py without versioning the URL, so the
# pinned hash drifts whenever pip releases. When build-windows fails with
# "SHA256 mismatch for https://bootstrap.pypa.io/get-pip.py", refresh the
# pin via:
#   Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py
#   Get-FileHash get-pip.py -Algorithm SHA256
# Long-term we should switch to a versioned URL (e.g. .../pip/24.0/get-pip.py)
# or the bootstrap-served `.sha256` sidecar -- tracked in #649.
$GetPipSha256 = '66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76'

# FFmpeg is pinned to a specific BtbN autobuild so the same allaganeye tag ships
# the same binary and the LGPLv3 license applies uniformly across CI and Portable ZIP.
# We use the shared variant (wrapper exe + individual avcodec/avfilter/... DLLs)
# rather than the static build to keep Portable ZIP size down (~200 MB vs ~330 MB).
# To update: bump $FFmpegBuildTag / $FFmpegAsset / $FFmpegSha256 together.
# CI workflows (`.github/workflows/ci.yml`) must be updated with the matching
# linux64-lgpl-shared asset at the same build tag; see docs/developer-setup.md § 9.
$FFmpegVersion = '8.1'
$FFmpegBuildTag = 'autobuild-2026-05-06-13-32'
$FFmpegAsset = 'ffmpeg-n8.1.1-win64-lgpl-shared-8.1'
$FFmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFmpegBuildTag/$FFmpegAsset.zip"
$FFmpegSha256 = '16F409AB737538778F9CD4BFC69953E2E1DC2558F6DC5CA17CC72083D60DC735'

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

function Get-FFmpegSourceRef {
  <#
  Extract the upstream FFmpeg source ref (commit hash or release tag) from a
  BtbN asset name. Both refs let users fetch the exact source under LGPLv3
  obligations (commit hash via `git checkout <hash>`, release tag via
  `git checkout n8.1.1` from the FFmpeg upstream repo).

  BtbN embeds it as one of two formats:
    - Old (autobuild-YYYY-MM-DD prior to BtbN's patch-release naming switch
      ca. 2026-05-06): ffmpeg-n<version>-<count>-g<commit>-<target>-<variant>
      (e.g. ffmpeg-n8.1-10-g7f5c90f77e-win64-lgpl-shared-8.1)
      -> returns commit hash "7f5c90f77e"
    - New (BtbN switched to bare patch-release tags, no count + commit hash
      in the name): ffmpeg-n<version>-<target>-<variant>
      (e.g. ffmpeg-n8.1.1-win64-lgpl-shared-8.1)
      -> returns release tag "n8.1.1"

  Renamed from `Get-FFmpegSourceCommit` (PR #683 review #9) so the function
  name reflects the post-rename semantics ("source ref" covers both commit
  hash and release tag, consistent with BtbN's two naming formats).
  #>
  param(
    [Parameter(Mandatory = $true)][string]$AssetName
  )
  # Old format first: extract commit hash from the trailing -g<hex>- segment.
  if ($AssetName -match '^ffmpeg-n[^-]+-[0-9]+-g([0-9a-f]+)-') {
    return $matches[1]
  }
  # New format: bare release tag (n<version>) immediately followed by the
  # target/variant segment (alphabetic prefix like "win64", "linux64").
  if ($AssetName -match '^ffmpeg-(n\d+(?:\.\d+)+)-[A-Za-z]') {
    return $matches[1]
  }
  throw "Cannot extract upstream source ref (commit hash or release tag) from asset name: $AssetName"
}

function Format-ReadmeContent {
  <#
  Produce the README.txt shipped inside the Portable ZIP. Exposing this as a
  function lets Pester assert the LGPLv3 attribution + source pointers are
  present without running a full build.

  -IncludeGui:$true (when the Tauri-built `allaganeye-gui.exe` is bundled, #570)
  emits a "Easiest: double-click `allaganeye.bat`" section as the FIRST usage
  entry, followed by drag-drop and Command Prompt sections (#617). The WebView2
  Runtime dependency note moves into this section. -IncludeGui:$false (default,
  CLI-only ZIP) keeps drag-drop as the first usage entry without any GUI
  references.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$FFmpegVersion,
    [Parameter(Mandatory = $true)][string]$FFmpegBuildTag,
    [Parameter(Mandatory = $true)][string]$FFmpegSourceRef,
    [switch]$IncludeGui
  )
  $guiSection = if ($IncludeGui) {
@'

### Easiest: double-click `allaganeye.bat`

Double-click `allaganeye.bat` in this folder to launch the GUI
(`allaganeye-gui.exe`). The GUI lets you drop a video file, review detected
matches, fine-tune match boundaries, and export each match as MP4.

NOTE: The GUI requires Microsoft Edge WebView2 Runtime, which is preinstalled
on Windows 11 and recent Windows 10 builds. If the GUI fails to start with a
missing-runtime dialog, install it from:

    https://developer.microsoft.com/en-us/microsoft-edge/webview2/

(`Evergreen Standalone Installer` is sufficient and does not require admin
rights for per-user install.)

'@
  }
  else { '' }

  $guiLicenseLine = if ($IncludeGui) {
@"
- Allagan Eye GUI (``allaganeye-gui.exe``): MIT (built with Tauri 2.x + React 19)
    WebView2 Runtime is loaded from the user's system at runtime, not redistributed.

"@
  }
  else { '' }

  return @"
# allaganeye v$Version (Portable ZIP for Windows)

Python 3.11 and FFmpeg LGPL binaries are bundled alongside allaganeye.

## Usage
$guiSection
### Drag-and-drop a video file

Drop a video file (.mkv / .mp4 / .avi / .mov) onto ``allaganeye.bat`` and it
will split the video automatically. The command window stays open at the end so
you can read the result -- press any key to close it.

Output MP4 files and metadata.json land under ``output\`` inside this folder.

### From a Command Prompt

If you want to pass options such as --dry-run or -o, open a Command Prompt in
this folder and run:

    allaganeye.bat split "C:\path\to\video.mkv"
    allaganeye.bat split "C:\path\to\video.mkv" --dry-run
    allaganeye.bat --version

See https://github.com/Idios/kobutachan-allaganeye for full documentation.

## Licenses

- allaganeye: MIT (see the repository LICENSE file)
$guiLicenseLine- Python: PSF License (python\LICENSE.txt)
- FFmpeg: LGPLv3 (full text in ffmpeg\LICENSE.txt)
    Build:         ffmpeg n$FFmpegVersion win64-lgpl-shared build (BtbN/FFmpeg-Builds)
    Build tag:     $FFmpegBuildTag
    Source:        https://git.ffmpeg.org/ffmpeg.git (ref $FFmpegSourceRef)
    Build scripts: https://github.com/BtbN/FFmpeg-Builds

allaganeye (MIT) invokes the FFmpeg binary as a separate subprocess only.
The shared-build DLLs are loaded dynamically by the FFmpeg executables and are
redistributed under LGPLv3 alongside the license text; LGPLv3 therefore does
not apply to allaganeye itself.
"@
}

function Get-LauncherTemplate {
  <#
  .SYNOPSIS
  Returns the .bat launcher template embedded in the Portable ZIP.

  Exposed as a function so Pester (#583) can verify the exit code propagation
  idiom (#580: `set EXIT_CODE=%ERRORLEVEL%` + `endlocal & exit /b %EXIT_CODE%`)
  without dot-sourcing the full build path.

  -IncludeGui:$true (when allaganeye-gui.exe is bundled in the ZIP) emits help
  text that mentions ".bat double-click -> GUI" as the primary entry. -IncludeGui:$false
  (default, CLI-only ZIP) omits the GUI mention so users are not directed to a
  non-existent exe. Symmetric with Format-ReadmeContent -IncludeGui (#570).

  Branch order in the template (top-down, first match wins, #617):
    1. --help / -h / /?               -> :show_help (explicit help flags always reach help)
    2. no args + GUI exe exists       -> start "" "%PAYLOAD%allaganeye-gui.exe" + exit /b 0
    3. no args + GUI exe absent       -> :show_help (CLI-only ZIP fallback)
    4. video file extension           -> python -m allaganeye split %*  (existing pre-#617 behavior)
    5. other args                     -> python -m allaganeye %*        (existing pre-#617 behavior)

  The runtime `if exist "%PAYLOAD%allaganeye-gui.exe"` check is a defensive
  fallback that handles the (rare) case where a user manually deletes the GUI
  exe from a -IncludeGui:$true ZIP. -IncludeGui only controls the help text.
  #>
  param(
    [switch]$IncludeGui
  )

  $helpUsageLines = if ($IncludeGui) {
@'
echo   1. Double-click allaganeye.bat to launch the GUI (allaganeye-gui.exe).
echo   2. Drag a video file (.mkv / .mp4 / .avi / .mov) onto allaganeye.bat
echo      to split it automatically.
echo   3. From a Command Prompt:
echo      allaganeye.bat split "C:\path\to\video.mkv"
'@
  }
  else {
@'
echo   1. Drag a video file (.mkv / .mp4 / .avi / .mov) onto allaganeye.bat
echo      to split it automatically.
echo   2. From a Command Prompt:
echo      allaganeye.bat split "C:\path\to\video.mkv"
'@
  }

  return @"
@echo off
setlocal
set PAYLOAD=%~dp0
set ALLAGANEYE_FFMPEG=%PAYLOAD%ffmpeg\ffmpeg.exe
set PATH=%PAYLOAD%ffmpeg;%PATH%

if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
if "%~1"=="/?" goto :show_help

if "%~1"=="" (
  if exist "%PAYLOAD%allaganeye-gui.exe" (
    start "" "%PAYLOAD%allaganeye-gui.exe"
    endlocal
    exit /b 0
  )
  goto :show_help
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
set EXIT_CODE=%ERRORLEVEL%

echo.
pause
endlocal & exit /b %EXIT_CODE%

:show_help
echo.
echo allaganeye - FF14 Frontline video splitter
echo.
echo How to use:
$helpUsageLines
echo.
echo Docs: https://github.com/Idios/kobutachan-allaganeye
echo.
pause
endlocal
exit /b 0
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

# 4. FFmpeg LGPLv3 shared, BtbN/FFmpeg-Builds (version-pinned)
# LGPLv3 redistribution requires shipping the license text alongside the binary
# and making the corresponding source available. We copy LICENSE.txt into the
# payload and point README at the upstream source repo.
$FFmpegZip = Join-Path $BuildDir 'ffmpeg.zip'
# Optional download cache: CI sets $env:ALLAGANEYE_BUILD_CACHE_DIR and uses
# actions/cache to persist the BtbN zip across runs. Local builds leave the
# variable unset and always download. Cache is keyed by asset name so a pinned
# bump invalidates automatically; the SHA256 is re-verified on every reuse.
$FFmpegCacheDir = $env:ALLAGANEYE_BUILD_CACHE_DIR
if ($FFmpegCacheDir) {
  $FFmpegCached = Join-Path $FFmpegCacheDir "$FFmpegAsset.zip"
  if (Test-Path $FFmpegCached) {
    $cachedHash = (Get-FileHash -Algorithm SHA256 -Path $FFmpegCached).Hash
    if ($cachedHash -eq $FFmpegSha256.ToUpperInvariant()) {
      Copy-Item -Path $FFmpegCached -Destination $FFmpegZip
      Write-Host "Using cached FFmpeg zip: $FFmpegCached"
    } else {
      Write-Host "  Cached FFmpeg zip SHA256 mismatch, re-downloading"
    }
  }
}
if (-not (Test-Path $FFmpegZip)) {
  Invoke-Download -Uri $FFmpegUrl -OutPath $FFmpegZip -ExpectedSha256 $FFmpegSha256
  if ($FFmpegCacheDir) {
    New-Item -ItemType Directory -Force -Path $FFmpegCacheDir | Out-Null
    Copy-Item -Path $FFmpegZip -Destination (Join-Path $FFmpegCacheDir "$FFmpegAsset.zip") -Force
    Write-Host "Saved FFmpeg zip to cache: $FFmpegCacheDir"
  }
}
$FFmpegExtract = Join-Path $BuildDir 'ffmpeg-extracted'
Expand-Archive -Path $FFmpegZip -DestinationPath $FFmpegExtract -Force
$FFmpegLayout = Assert-FFmpegLayout -ExtractDir $FFmpegExtract
$FFmpegSourceRef = Get-FFmpegSourceRef -AssetName $FFmpegAsset
$FFmpegDest = Join-Path $PayloadDir 'ffmpeg'
New-Item -ItemType Directory -Force -Path $FFmpegDest | Out-Null
# Shared build: copy ffmpeg.exe, ffprobe.exe, and all DLLs. ffplay.exe is excluded
# because allaganeye never invokes it and keeping it would cost ~17 MB.
Copy-Item -Path (Join-Path $FFmpegLayout.Bin 'ffmpeg.exe') -Destination $FFmpegDest
Copy-Item -Path (Join-Path $FFmpegLayout.Bin 'ffprobe.exe') -Destination $FFmpegDest
Get-ChildItem -Path $FFmpegLayout.Bin -Filter '*.dll' | Copy-Item -Destination $FFmpegDest
Copy-Item -Path $FFmpegLayout.License -Destination (Join-Path $FFmpegDest 'LICENSE.txt')

# 5. Tauri GUI bundle (optional, auto-detect)
# This block runs BEFORE the launcher (step 6, #617) so $TauriIncluded is
# available to Get-LauncherTemplate -IncludeGui and Format-ReadmeContent -IncludeGui.
#
# Copy the Tauri-built GUI binary (allaganeye-gui.exe) into the payload root
# as-is. The cargo binary name has no whitespace so users / scripts can
# reference it without quoting headaches; tauri.conf.json `productName`
# ("Allagan Eye") is still used by Tauri for the window title at runtime,
# but the executable filename stays in cargo/snake/dash form for portability.
#
# Build is the caller's responsibility: CI runs `npm install && npm run tauri build`
# in a preceding workflow step, and the resulting exe lands at
# gui/src-tauri/target/release/allaganeye-gui.exe. tauri.conf.json keeps
# `bundle.active = false` because the Portable ZIP is the distribution form
# and Tauri's NSIS/MSI bundles are not used. Local dry-run may skip the
# Tauri build; if the exe is absent we log a warning and continue (CLI-only ZIP).
$TauriExe = Join-Path $RepoRoot 'gui\src-tauri\target\release\allaganeye-gui.exe'
$TauriIncluded = $false
if (Test-Path $TauriExe) {
  Copy-Item -Path $TauriExe -Destination (Join-Path $PayloadDir 'allaganeye-gui.exe')
  Write-Host "Bundled GUI: $TauriExe -> $PayloadDir\allaganeye-gui.exe"
  $TauriIncluded = $true
} else {
  Write-Warning "Tauri GUI build not found at $TauriExe - Portable ZIP will be built without the GUI binary. Run 'cd gui && npm install && npm run tauri build' first to include the GUI."
}

# 6. Launcher (after Tauri detection so the .bat help text and runtime branch
# can reflect whether allaganeye-gui.exe is bundled, #617).
# Template is defined as Get-LauncherTemplate (#583) so Pester can verify the
# exit code propagation idiom (#580) without dot-sourcing the full build path.
$Launcher = Get-LauncherTemplate -IncludeGui:$TauriIncluded
Set-Content -Path (Join-Path $PayloadDir 'allaganeye.bat') -Value $Launcher -Encoding ASCII

# 7. README (after Tauri detection so the GUI section is conditional)
$Readme = Format-ReadmeContent `
  -Version $Version `
  -FFmpegVersion $FFmpegVersion `
  -FFmpegBuildTag $FFmpegBuildTag `
  -FFmpegSourceRef $FFmpegSourceRef `
  -IncludeGui:$TauriIncluded
Set-Content -Path (Join-Path $PayloadDir 'README.txt') -Value $Readme -Encoding UTF8

# 8. Compress (skipped with -SkipArchive so CI can hand the payload folder
# directly to actions/upload-artifact; upload-artifact zips it once instead of
# producing a nested zip).
if ($SkipArchive) {
  Write-Host "Skipping archive creation (-SkipArchive). Payload at: $PayloadDir"
} else {
  Compress-Archive -Path $PayloadDir -DestinationPath $ZipPath -CompressionLevel Optimal
  Write-Host "Built $ZipPath"
}
