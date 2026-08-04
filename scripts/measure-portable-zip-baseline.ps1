<#
.SYNOPSIS
Measure Portable ZIP payload file count and size for #752 baseline / regression tracking.

.DESCRIPTION
Recursively walks the expanded Portable ZIP payload directory and aggregates
file counts + sizes by:
  - top-level directory
  - file extension (.py / .pyd / .dll / .pyi / .so / _other)

Output is machine-parseable JSON (default) or a human-readable table.

The output is used by:
  - Pester regression test (`scripts/tests/build-portable-zip.Tests.ps1`)
    to assert the post-PyInstaller file count reduction.
  - CI release.yml `build-windows` job artifact upload (`baseline.json`).
  - PR body before/after comparison (#752 acceptance criterion).

.PARAMETER PayloadDir
Path to the expanded payload root (e.g. `build/portable/allaganeye-v0.3.0/`).

.PARAMETER Format
'Json' (default) emits machine-parseable JSON. 'Human' emits a readable table.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$PayloadDir,
  [ValidateSet('Json', 'Human')][string]$Format = 'Json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path $PayloadDir)) {
  throw "Payload directory not found: $PayloadDir"
}

$resolved = (Resolve-Path $PayloadDir).Path

# Aggregation buckets.
$tracked_extensions = @('.py', '.pyd', '.dll', '.pyi', '.so')
$by_top_dir = @{}
$by_extension = @{}
foreach ($ext in $tracked_extensions) {
  $by_extension[$ext] = @{ count = 0; size_bytes = 0L }
}
$by_extension['_other'] = @{ count = 0; size_bytes = 0L }

$totalCount = 0
$totalSize = 0L

Get-ChildItem -Path $resolved -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
  $totalCount++
  $totalSize += $_.Length

  $rel = $_.FullName.Substring($resolved.Length).TrimStart('\', '/')
  # top-level dir (or _root if file sits at payload root).
  $segments = $rel -split '[\\/]', 2
  $topDir = if ($segments.Count -eq 1) { '_root' } else { $segments[0] }
  if (-not $by_top_dir.ContainsKey($topDir)) {
    $by_top_dir[$topDir] = @{ file_count = 0; size_bytes = 0L }
  }
  $by_top_dir[$topDir].file_count++
  $by_top_dir[$topDir].size_bytes += $_.Length

  $ext = $_.Extension.ToLower()
  if ($tracked_extensions -contains $ext) {
    $by_extension[$ext].count++
    $by_extension[$ext].size_bytes += $_.Length
  } else {
    $by_extension['_other'].count++
    $by_extension['_other'].size_bytes += $_.Length
  }
}

$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$result = [ordered]@{
  schema_version = 1
  measured_at = $now
  payload_dir = $resolved
  total_file_count = $totalCount
  total_size_bytes = $totalSize
  by_top_dir = $by_top_dir
  by_extension = $by_extension
}

if ($Format -eq 'Json') {
  $result | ConvertTo-Json -Depth 4
} else {
  # Human-readable table.
  Write-Output "Payload: $resolved"
  Write-Output "Measured: $now"
  Write-Output ""
  Write-Output "total_file_count: $totalCount"
  Write-Output ("total_size_bytes: {0} ({1:N2} MB)" -f $totalSize, ($totalSize / 1MB))
  Write-Output ""
  Write-Output "by_top_dir:"
  $by_top_dir.GetEnumerator() | Sort-Object Key | ForEach-Object {
    Write-Output ("  {0,-12} files={1,6}  size={2,10:N0} ({3,7:N2} MB)" -f $_.Key, $_.Value.file_count, $_.Value.size_bytes, ($_.Value.size_bytes / 1MB))
  }
  Write-Output ""
  Write-Output "by_extension:"
  $by_extension.GetEnumerator() | Sort-Object Key | ForEach-Object {
    Write-Output ("  {0,-8} count={1,6}  size={2,10:N0} ({3,7:N2} MB)" -f $_.Key, $_.Value.count, $_.Value.size_bytes, ($_.Value.size_bytes / 1MB))
  }
}
