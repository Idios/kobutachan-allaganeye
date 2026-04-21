<#
.SYNOPSIS
Build the allaganeye Portable ZIP for Windows.

.DESCRIPTION
Downloads Python 3.11 embeddable and FFmpeg LGPL essentials, installs
allaganeye and its runtime dependencies into the payload, adds a .bat
launcher, and compresses everything into dist/allaganeye-v<version>-windows.zip.

Downloaded artefacts (Python embed, get-pip.py, FFmpeg zip) are pinned by URL
and verified against hard-coded SHA256 digests. A mismatch aborts the build.

The script is idempotent: build/portable and dist are cleaned at the start.

.PARAMETER Version
Semantic version string (e.g. "0.2.0") used in the output ZIP filename.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Version
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BuildDir = Join-Path $RepoRoot 'build\portable'
$DistDir = Join-Path $RepoRoot 'dist'
$PayloadName = "allaganeye-v$Version"
$PayloadDir = Join-Path $BuildDir $PayloadName
$ZipPath = Join-Path $DistDir "$PayloadName-windows.zip"

$PythonVersion = '3.11.9'
$PythonEmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonEmbedSha256 = '009D6BF7E3B2DDCA3D784FA09F90FE54336D5B60F0E0F305C37F400BF83CFD3B'

$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
$GetPipSha256 = 'FEBA1C697DF45BE1B539B40D93C102C9EE9DDE1D966303323B830B06F3FBCA3C'

# FFmpeg version is pinned so the same allaganeye tag always ships the same FFmpeg.
# To update: bump $FFmpegVersion, replace $FFmpegSha256 with the new asset's hash.
$FFmpegVersion = '8.1'
$FFmpegUrl = "https://github.com/GyanD/codexffmpeg/releases/download/$FFmpegVersion/ffmpeg-$FFmpegVersion-essentials_build.zip"
$FFmpegSha256 = '8748283D821613D930B0E7BE685AAA9DF4CA6F0AD4D0C42FD02622B3623463C6'

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

# 4. FFmpeg LGPL essentials (version-pinned)
$FFmpegZip = Join-Path $BuildDir 'ffmpeg.zip'
Invoke-Download -Uri $FFmpegUrl -OutPath $FFmpegZip -ExpectedSha256 $FFmpegSha256
$FFmpegExtract = Join-Path $BuildDir 'ffmpeg-extracted'
Expand-Archive -Path $FFmpegZip -DestinationPath $FFmpegExtract -Force
$FFmpegBin = Get-ChildItem -Path $FFmpegExtract -Directory |
  Select-Object -First 1 |
  ForEach-Object { Join-Path $_.FullName 'bin' }
if (-not $FFmpegBin -or -not (Test-Path $FFmpegBin)) {
  throw "FFmpeg bin directory not found under $FFmpegExtract"
}
$FFmpegDest = Join-Path $PayloadDir 'ffmpeg'
New-Item -ItemType Directory -Force -Path $FFmpegDest | Out-Null
Copy-Item -Path (Join-Path $FFmpegBin 'ffmpeg.exe') -Destination $FFmpegDest
Copy-Item -Path (Join-Path $FFmpegBin 'ffprobe.exe') -Destination $FFmpegDest

# 5. Launcher
$Launcher = @'
@echo off
setlocal
set PAYLOAD=%~dp0
set ALLAGANEYE_FFMPEG=%PAYLOAD%ffmpeg\ffmpeg.exe
set PATH=%PAYLOAD%ffmpeg;%PATH%
"%PAYLOAD%python\python.exe" -m allaganeye %*
endlocal
'@
Set-Content -Path (Join-Path $PayloadDir 'allaganeye.bat') -Value $Launcher -Encoding ASCII

# 6. README
$Readme = @"
# allaganeye v$Version (Portable ZIP for Windows)

Python 3.11 and FFmpeg LGPL binaries are bundled alongside allaganeye.

## Usage

1. Extract this ZIP anywhere.
2. Open a Command Prompt in the extracted folder.
3. Run:

    allaganeye.bat split <path-to-video>

See https://github.com/Idios/kobutachan-allaganeye for full documentation.

## Licenses

- allaganeye: MIT (see the repository LICENSE file)
- Python: PSF License (python\LICENSE.txt)
- FFmpeg: LGPL (ffmpeg $FFmpegVersion essentials build from GyanD/codexffmpeg)
"@
Set-Content -Path (Join-Path $PayloadDir 'README.txt') -Value $Readme -Encoding UTF8

# 7. Compress
Compress-Archive -Path $PayloadDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Built $ZipPath"
