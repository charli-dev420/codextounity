param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = '',
  [switch]$KeepWorkDir
)
$ErrorActionPreference = 'Stop'

if (!$WorkDir) {
  $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-normalization-invariants-" + [guid]::NewGuid().ToString('N'))
}

$scriptsDir = Join-Path $PluginRoot 'scripts'
$profilesDir = Join-Path $PluginRoot 'configs\asset-profiles'
$python = 'python'

function Invoke-External([string]$File, [string[]]$Arguments) {
  $output = & $File @Arguments 2>&1
  if ($LASTEXITCODE -ne 0) {
    $output | ForEach-Object { Write-Host $_ }
    throw "Command failed with exit code ${LASTEXITCODE}: $File $($Arguments -join ' ')"
  }
  return $output
}

function Invoke-ExpectedFailure([string]$Label, [string]$File, [string[]]$Arguments, [string]$ExpectedText = '') {
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $output = & $File @Arguments 2>&1
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $oldPreference
  }
  if ($exitCode -eq 0) {
    $output | ForEach-Object { Write-Host $_ }
    throw "Expected failure did not fail: $Label"
  }
  if ($ExpectedText -and (($output -join "`n") -notmatch [regex]::Escape($ExpectedText))) {
    $output | ForEach-Object { Write-Host $_ }
    throw "Expected failure text not found for ${Label}: $ExpectedText"
  }
  Write-Host "Expected failure OK: $Label"
}

function Read-JsonFile([string]$Path) {
  return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Write-JsonFile([string]$Path, [object]$Data) {
  $Data | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Assert-True([bool]$Condition, [string]$Message) {
  if (!$Condition) { throw $Message }
}

function Assert-Near([double]$Actual, [double]$Expected, [double]$Tolerance, [string]$Message) {
  if ([Math]::Abs($Actual - $Expected) -gt $Tolerance) {
    throw "$Message actual=$Actual expected=$Expected tolerance=$Tolerance"
  }
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

function Get-ProfileTarget([string]$Profile, [string]$SubProfile = '') {
  $profileData = Read-JsonFile (Join-Path $profilesDir "$Profile.json")
  if ($SubProfile) {
    $sub = $profileData.subProfiles.$SubProfile
    return @([double]$sub.targetBounds.x, [double]$sub.targetBounds.y, [double]$sub.targetBounds.z)
  }
  return @([double]$profileData.targetBounds.x, [double]$profileData.targetBounds.y, [double]$profileData.targetBounds.z)
}

function Assert-NormalizationReport([string]$ReportPath, [string]$Profile, [string]$SubProfile, [string]$ExpectedFitAxis) {
  $report = Read-JsonFile $ReportPath
  Assert-True ($report.transform.proportionsPreserved -eq $true) "$Profile/$SubProfile did not preserve proportions"
  Assert-True ($report.transform.fitMode -eq 'preserve-aspect') "$Profile/$SubProfile fitMode is not preserve-aspect"
  Assert-True ($report.transform.fitAxis -eq $ExpectedFitAxis) "$Profile/$SubProfile fitAxis mismatch: $($report.transform.fitAxis)"
  $scale = @($report.transform.targetScaleApplied)
  Assert-True ($scale.Count -eq 3) "$Profile/$SubProfile targetScaleApplied must have 3 values"
  Assert-Near ([double]$scale[0]) ([double]$scale[1]) 0.000001 "$Profile/$SubProfile scale x/y is not uniform"
  Assert-Near ([double]$scale[1]) ([double]$scale[2]) 0.000001 "$Profile/$SubProfile scale y/z is not uniform"

  $target = Get-ProfileTarget $Profile $SubProfile
  $extent = @($report.after.extent | ForEach-Object { [double]$_ })
  $tolerance = [double]$report.validation.tolerance
  for ($i = 0; $i -lt 3; $i++) {
    Assert-True ($extent[$i] -le ($target[$i] + $tolerance + 0.000001)) "$Profile/$SubProfile extent $i exceeds target envelope"
  }
  $axisIndex = @{ x = 0; y = 1; z = 2 }
  if ($ExpectedFitAxis -eq 'contain') {
    $touches = $false
    for ($i = 0; $i -lt 3; $i++) {
      if ([Math]::Abs($extent[$i] - $target[$i]) -le ($tolerance + 0.000001)) { $touches = $true }
    }
    Assert-True $touches "$Profile/$SubProfile contain fit did not touch an envelope axis"
  } else {
    $index = $axisIndex[$ExpectedFitAxis]
    Assert-Near $extent[$index] $target[$index] ($tolerance + 0.000001) "$Profile/$SubProfile fit axis does not match target"
  }
}

try {
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
  $sourceDir = Join-Path $WorkDir 'source'
  $normalizedDir = Join-Path $WorkDir 'normalized'
  New-Item -ItemType Directory -Force -Path $sourceDir, $normalizedDir | Out-Null

  $cases = @(
    @{ Name='terrain_piece'; Profile='terrain_piece'; SubProfile=''; Size='4,0.4,4'; FitAxis='contain' },
    @{ Name='wall'; Profile='wall'; SubProfile=''; Size='4,2,0.35'; FitAxis='x' },
    @{ Name='door'; Profile='door'; SubProfile=''; Size='1.1,2.1,0.18'; FitAxis='y' },
    @{ Name='prop'; Profile='prop'; SubProfile=''; Size='2,1,1'; FitAxis='contain' },
    @{ Name='window_wall'; Profile='wall'; SubProfile='window_wall'; Size='4,2,0.35'; FitAxis='x' },
    @{ Name='wall_mirror'; Profile='wall'; SubProfile='wall_mirror'; Size='0.75,1.2,0.12'; FitAxis='y' }
  )

  foreach ($case in $cases) {
    $sourceMesh = Join-Path $sourceDir "$($case.Name).glb"
    $normalizedMesh = Join-Path $normalizedDir "$($case.Name).glb"
    $reportPath = Join-Path $normalizedDir "$($case.Name).normalization_report.json"
    Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $sourceMesh, '--size', $case.Size) | Out-Null
    $args = @(
      '-B', (Join-Path $scriptsDir 'normalize_asset_bounds.py'),
      '--input', $sourceMesh,
      '--output', $normalizedMesh,
      '--profile', $case.Profile,
      '--profiles-dir', $profilesDir,
      '--report', $reportPath
    )
    if ($case.SubProfile) { $args += @('--sub-profile', $case.SubProfile) }
    Invoke-External $python $args | Out-Null
    Assert-NormalizationReport $reportPath $case.Profile $case.SubProfile $case.FitAxis

    $validateArgs = @(
      '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
      '--mesh', $normalizedMesh,
      '--profile', $case.Profile,
      '--profiles-dir', $profilesDir,
      '--normalization-report', $reportPath,
      '--json'
    )
    if ($case.SubProfile) { $validateArgs += @('--sub-profile', $case.SubProfile) }
    Invoke-External $python $validateArgs | Out-Null
  }

  $badScaleMesh = Join-Path $sourceDir 'bad-scale.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $badScaleMesh) | Out-Null
  Invoke-ExpectedFailure 'non-uniform scale rejected' $python @(
    '-B', (Join-Path $scriptsDir 'normalize_asset_bounds.py'),
    '--input', $badScaleMesh,
    '--output', (Join-Path $normalizedDir 'bad-scale.glb'),
    '--scale', '1,2,1'
  ) 'Non-uniform scale would deform the asset'

  Invoke-ExpectedFailure 'fit-axis overflow rejected' $python @(
    '-B', (Join-Path $scriptsDir 'normalize_asset_bounds.py'),
    '--input', $badScaleMesh,
    '--output', (Join-Path $normalizedDir 'bad-overflow.glb'),
    '--target-bounds', '1,0.1,0.1',
    '--fit-axis', 'x',
    '--report', (Join-Path $normalizedDir 'bad-overflow.normalization_report.json')
  ) 'preserve-aspect overflow'

  $goodReport = Read-JsonFile (Join-Path $normalizedDir 'wall.normalization_report.json')
  $goodReport.transform.proportionsPreserved = $false
  $badReportPath = Join-Path $normalizedDir 'bad-proportions-report.json'
  Write-JsonFile $badReportPath $goodReport
  Invoke-ExpectedFailure 'runtime rejects report without preserved proportions' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', (Join-Path $normalizedDir 'wall.glb'),
    '--profile', 'wall',
    '--profiles-dir', $profilesDir,
    '--normalization-report', $badReportPath,
    '--json'
  ) 'non-uniform scale would deform the asset'

  Write-Host 'Normalization invariant gate OK'
  $global:LASTEXITCODE = 0
} finally {
  if (!$KeepWorkDir -and (Test-Path -LiteralPath $WorkDir)) {
    Remove-WorkDirSafely $WorkDir
  } elseif (Test-Path -LiteralPath $WorkDir) {
    Write-Host "Normalization invariant work dir kept: $WorkDir"
  }
}
