param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = '',
  [switch]$KeepWorkDir
)
$ErrorActionPreference = 'Stop'

if (!$WorkDir) {
  $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-room-demo-batch-" + [guid]::NewGuid().ToString('N'))
}

$runner = Join-Path $PluginRoot 'scripts\run_room_demo_batch.ps1'

function Write-JsonFile([string]$Path, [object]$Data) {
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $Data | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Read-JsonFile([string]$Path) {
  return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Assert-True([bool]$Condition, [string]$Message) {
  if (!$Condition) { throw $Message }
}

function Invoke-Runner([string[]]$Arguments, [int]$ExpectedExitCode = 0) {
  $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner @Arguments 2>&1
  if ($LASTEXITCODE -ne $ExpectedExitCode) {
    $output | ForEach-Object { Write-Host $_ }
    throw "run_room_demo_batch.ps1 exit code $LASTEXITCODE, expected $ExpectedExitCode"
  }
  return $output
}

function Remove-WorkDirSafely([string]$Path) {
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $tempRoot = [System.IO.Path]::GetTempPath().TrimEnd('\','/')
  $resolvedComparable = $resolved.TrimEnd('\','/')
  if ($resolvedComparable.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -Recurse -Force -LiteralPath $resolved
  } else {
    Write-Host "Keeping work dir outside temp safety root: $resolved"
  }
}

try {
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
  $planDir = Join-Path $WorkDir 'plan'
  $inputDir = Join-Path $planDir 'inputs'
  $outputDir = Join-Path $planDir 'trellis2'
  $rawDir = Join-Path $outputDir 'raw'
  $statusDir = Join-Path $outputDir 'status'
  New-Item -ItemType Directory -Force -Path $inputDir, (Join-Path $rawDir 'room_demo_batch'), $statusDir | Out-Null

  $existingInput = Join-Path $inputDir '01_floor_platform.png'
  $emptyInput = Join-Path $inputDir '02_plain_wall.png'
  $failedInput = Join-Path $inputDir '03_door.png'
  Set-Content -LiteralPath $existingInput -Value 'image-placeholder' -Encoding ASCII
  Set-Content -LiteralPath $emptyInput -Value 'image-placeholder' -Encoding ASCII
  Set-Content -LiteralPath $failedInput -Value 'image-placeholder' -Encoding ASCII

  Set-Content -LiteralPath (Join-Path $rawDir 'room_demo_batch\01_floor_platform_00001_.glb') -Value 'glb-placeholder' -Encoding ASCII
  New-Item -ItemType File -Force -Path (Join-Path $rawDir 'room_demo_batch\02_plain_wall_00001_.glb') | Out-Null
  Write-JsonFile (Join-Path $statusDir '03_door.json') ([ordered]@{
      assetName = '03_door'
      state = 'failed'
      reason = 'missingOutput'
      shortError = 'prior failure'
    })

  Write-JsonFile (Join-Path $planDir 'selected_references.json') @(
    @{ assetName = '01_floor_platform'; inputImage = $existingInput; profile = 'terrain_piece'; role = 'floor' },
    @{ assetName = '02_plain_wall'; inputImage = $emptyInput; profile = 'wall'; role = 'wall' },
    @{ assetName = '03_door'; inputImage = $failedInput; profile = 'door'; role = 'door' }
  )

  Invoke-Runner @('-PlanDir', $planDir, '-DryRun') | Out-Null
  $summary = Read-JsonFile (Join-Path $outputDir 'summary_room_demo_batch.json')
  Assert-True ($summary.counts.skipped -eq 2) "expected 2 skipped assets, got $($summary.counts.skipped)"
  Assert-True ($summary.counts.dryRun -eq 1) "expected 1 dry-run asset, got $($summary.counts.dryRun)"
  Assert-True ($summary.counts.failed -eq 0) "expected no failed assets"

  Invoke-Runner @('-PlanDir', $planDir, '-DryRun', '-RetryFailed', '-AssetName', '03_door') | Out-Null
  $retrySummary = Read-JsonFile (Join-Path $outputDir 'summary_room_demo_batch.json')
  Assert-True ($retrySummary.counts.dryRun -eq 1) 'RetryFailed should plan the failed asset'
  Assert-True ($retrySummary.counts.skipped -eq 0) 'RetryFailed asset should not be skipped'

  Invoke-Runner @('-PlanDir', $planDir, '-DryRun', '-Force', '-AssetName', '01_floor_platform') | Out-Null
  $forceSummary = Read-JsonFile (Join-Path $outputDir 'summary_room_demo_batch.json')
  Assert-True ($forceSummary.counts.dryRun -eq 1) 'Force should plan an asset even when a GLB exists'
  Assert-True ($forceSummary.counts.skipped -eq 0) 'Force should not skip existing GLB'

  $missingPlanDir = Join-Path $WorkDir 'missing-plan'
  New-Item -ItemType Directory -Force -Path $missingPlanDir | Out-Null
  Write-JsonFile (Join-Path $missingPlanDir 'selected_references.json') @(
    @{ assetName = '04_missing_asset'; inputImage = (Join-Path $missingPlanDir 'inputs\missing.png'); profile = 'prop'; role = 'missing' }
  )
  Invoke-Runner @('-PlanDir', $missingPlanDir, '-DryRun') 2 | Out-Null
  $missingSummary = Read-JsonFile (Join-Path $missingPlanDir 'trellis2\summary_room_demo_batch.json')
  Assert-True ($missingSummary.counts.failed -eq 1) 'missing input should fail'

  Write-Host 'Room demo TRELLIS2 batch gate OK'
  $global:LASTEXITCODE = 0
} finally {
  if (!$KeepWorkDir -and (Test-Path -LiteralPath $WorkDir)) {
    Remove-WorkDirSafely $WorkDir
  } elseif (Test-Path -LiteralPath $WorkDir) {
    Write-Host "Room demo batch work dir kept: $WorkDir"
  }
}
