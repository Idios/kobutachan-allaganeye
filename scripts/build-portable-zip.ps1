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

$GetPipUrl = 'https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py'
# #681 -- Pin get-pip.py via the pypa/get-pip GitHub raw URL with a release
# tag (immutable per tag), not bootstrap.pypa.io/get-pip.py (unversioned;
# drifts whenever PyPA refreshes pip and breaks build-windows CI -- see
# #649 short-term fix and PR #675 Round 2 follow-up).
#
# To bump pip when a new release is required:
#   1. Pick a new tag from https://github.com/pypa/get-pip/tags (e.g. 26.1.2)
#   2. Update the URL above and the SHA below:
#        Invoke-WebRequest `
#          "https://raw.githubusercontent.com/pypa/get-pip/<tag>/public/get-pip.py" `
#          -OutFile get-pip.py
#        Get-FileHash get-pip.py -Algorithm SHA256
#   3. Verify the regression test still passes:
#        Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
$GetPipSha256 = '66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76'

# FFmpeg is pinned to a BtbN MONTHLY snapshot (the end-of-month daily that
# survives BtbN's ~14-day GC of regular dailies, kept for ~24 months). Daily
# autobuilds are GC'd after ~14 days, so daily pins go 404 in less than a
# month. Only autobuild-YYYY-MM-{28,29,30,31}-* tags survive long enough for
# the Portable ZIP build to remain reproducible. See #705.
# We use the LGPLv3 shared variant (wrapper exe + individual
# avcodec/avfilter/... DLLs) rather than the static build to keep Portable ZIP
# size down (~200 MB vs ~330 MB).
#
# To bump (typically once per year, well before the 24-month retention runs out):
#   1. Pick the latest monthly survivor from
#      https://github.com/BtbN/FFmpeg-Builds/releases (a tag matching
#      autobuild-YYYY-MM-{28,29,30,31}-*; daily tags are forbidden by the
#      `BtbN pinning policy (#705)` Pester regression test).
#   2. Fetch checksums.sha256 from that release and grep for the win64 +
#      linux64 lgpl-shared-8.1 assets to get both SHA256 values:
#        curl -sL "https://github.com/BtbN/FFmpeg-Builds/releases/download/<tag>/checksums.sha256" \
#          | grep -E 'win64-lgpl-shared-8\.1\.zip$|linux64-lgpl-shared-8\.1\.tar\.xz$'
#   3. Update the win64 SHA256 below and `$FFmpegBuildTag` / `$FFmpegAsset`,
#      and update the matching linux64 SHA256 + URL in
#      `.github/workflows/ci.yml` (3 steps: Cache, Download, Install) and the
#      win64 SHA256 in `.github/workflows/release.yml` (Cache step). All these
#      locations (4 SHA256 sites across 3 files + 1 URL in ci.yml Download)
#      must move together — drift is caught by the cache key mismatch. See
#      `docs/developer-setup.md` § 9 for the full checklist.
#   4. Verify regressions:
#        Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
#        pwsh -File scripts/build-portable-zip.ps1 -Version 0.2.0-test -SkipArchive
$FFmpegVersion = '8.1'
$FFmpegBuildTag = 'autobuild-2026-04-30-13-44'
$FFmpegAsset = 'ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1'
$FFmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFmpegBuildTag/$FFmpegAsset.zip"
$FFmpegSha256 = 'E27598E612078F25D3E9CF245CE5042990F2602146E5A6F8287B143B0DCE0E95'

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

function New-IntegrityManifest {
  <#
  .SYNOPSIS
  Generate integrity-manifest.json content by enumerating the payload directory (#668).

  .DESCRIPTION
  Walks ``$PayloadDir`` recursively, records each file's POSIX-style relative
  path and size with ``tolerance_bytes = 0`` (strict matching), and returns a
  JSON string. The following are excluded so the runtime check does not raise
  false positives:
  - ``integrity-manifest.json`` itself (chicken-and-egg).
  - ``*.pyc`` files. Python regenerates bytecode on first import, so the
    bytes in the downloaded ZIP differ from the build-time manifest entry.
    PR #702 実機検証 で発覚 (size_mismatch on
    ``python/Lib/site-packages/_distutils_hack/__pycache__/__init__.cpython-311.pyc``).
  - Any path containing a dotfile/dotdir segment (e.g. ``.agents/``,
    ``.lock``, ``.f2py_f2cmap``). ``actions/upload-artifact@v4`` has
    ``include-hidden-files: false`` by default, so these files are silently
    stripped from the ZIP that users actually receive.
    PR #702 実機検証 で発覚 (4 missing dotfile entries).

  Exposed as a function so Pester can verify the JSON shape and the
  exclusion rules without dot-sourcing the full build path.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$PayloadDir
  )

  $manifestName = 'integrity-manifest.json'
  $entries = @()
  $base = (Resolve-Path $PayloadDir).Path
  # PR #702 review #5: Sort by FullName for deterministic enumeration order.
  # Get-ChildItem の order は filesystem / locale 依存で local Windows と CI
  # runner で異なる可能性がある。manifest JSON の git diff noisy 化と build
  # 再現性低下を避けるため明示 sort する。
  Get-ChildItem -Path $PayloadDir -Recurse -File | Sort-Object FullName | ForEach-Object {
    if ($_.Name -eq $manifestName) { return }
    # PR #702 実機検証: skip Python bytecode (non-deterministic regen on import).
    if ($_.Extension -eq '.pyc') { return }
    $rel = $_.FullName.Substring($base.Length).TrimStart('\', '/')
    $relPosix = $rel -replace '\\', '/'
    # PR #702 実機検証: skip dotfile / dotdir paths (artifact upload strips
    # hidden files). Matches `.gitignore` at root or `.agents/...` deeper.
    if ($relPosix -match '(^|/)\.[^/]') { return }
    $entries += [pscustomobject]@{
      path = $relPosix
      size = $_.Length
      tolerance_bytes = 0
    }
  }

  $generatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  $manifest = [ordered]@{
    version = 1
    generated_at = $generatedAt
    files = @($entries)
  }
  return ($manifest | ConvertTo-Json -Depth 4)
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
# #729 Round 1: README.txt も BOM-less UTF-8 で書き出す (consistency with L587 manifest write).
# README.txt は機能的に BOM が問題になる parser を持たないが、Portable ZIP 内ファイルの
# encoding 一貫性のため [IO.File]::WriteAllText に揃える。詳細は L577-585 の comment 参照。
[System.IO.File]::WriteAllText(
    (Join-Path $PayloadDir 'README.txt'),
    $Readme,
    [System.Text.UTF8Encoding]::new($false)
)

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

# 8. Compress (skipped with -SkipArchive so CI can hand the payload folder
# directly to actions/upload-artifact; upload-artifact zips it once instead of
# producing a nested zip).
if ($SkipArchive) {
  Write-Host "Skipping archive creation (-SkipArchive). Payload at: $PayloadDir"
} else {
  Compress-Archive -Path $PayloadDir -DestinationPath $ZipPath -CompressionLevel Optimal
  Write-Host "Built $ZipPath"
}
