param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = '',
  [switch]$KeepWorkDir
)
$ErrorActionPreference = 'Stop'

$createdDefaultWorkDir = $false
if (!$WorkDir) {
  $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-runtime-validation-" + [guid]::NewGuid().ToString('N'))
  $createdDefaultWorkDir = $true
}

$scriptsDir = Join-Path $PluginRoot 'scripts'
$profilesDir = Join-Path $PluginRoot 'configs\asset-profiles'
$python = 'python'
$profiles = @('wall','door','prop','weapon','pickup','character','equipment','terrain_piece')

function Invoke-External([string]$File, [string[]]$Arguments) {
  $output = & $File @Arguments 2>&1
  if ($LASTEXITCODE -ne 0) {
    $output | ForEach-Object { Write-Host $_ }
    throw "Command failed with exit code ${LASTEXITCODE}: $File $($Arguments -join ' ')"
  }
  return $output
}

function Invoke-ExpectedFailure([string]$Label, [string]$File, [string[]]$Arguments) {
  $output = & $File @Arguments 2>&1
  if ($LASTEXITCODE -eq 0) {
    $output | ForEach-Object { Write-Host $_ }
    throw "Expected failure did not fail: $Label"
  }
  Write-Host "Expected failure OK: $Label"
}

function Read-JsonFile([string]$Path) {
  return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Write-JsonFile([string]$Path, [object]$Data) {
  $Data | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Assert-True([bool]$Condition, [string]$Message) {
  if (!$Condition) { throw $Message }
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
  $sourceDir = Join-Path $WorkDir 'source'
  $normalizedDir = Join-Path $WorkDir 'normalized'
  $profileSizes = @{
    wall = '4,2,0.35'
    door = '1.1,2.1,0.18'
    prop = '1,1,1'
    weapon = '1,0.25,0.18'
    pickup = '0.45,0.45,0.45'
    character = '0.8,1.8,0.5'
    equipment = '0.8,0.8,0.4'
    terrain_piece = '4,0.4,4'
  }

  foreach ($profile in $profiles) {
    $sourceMesh = Join-Path $sourceDir "$profile.source.glb"
    $normalizedMesh = Join-Path $normalizedDir "$profile.glb"
    $normalizationReport = Join-Path $normalizedDir "$profile.normalization_report.json"
    Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $sourceMesh, '--size', $profileSizes[$profile]) | Out-Null
    Invoke-External $python @(
      '-B', (Join-Path $scriptsDir 'normalize_asset_bounds.py'),
      '--input', $sourceMesh,
      '--output', $normalizedMesh,
      '--profile', $profile,
      '--profiles-dir', $profilesDir,
      '--report', $normalizationReport
    ) | Out-Null
    $validationRaw = Invoke-External $python @(
      '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
      '--mesh', $normalizedMesh,
      '--profile', $profile,
      '--profiles-dir', $profilesDir,
      '--normalization-report', $normalizationReport,
      '--json'
    )
    $validation = ($validationRaw -join "`n") | ConvertFrom-Json
    Assert-True ($validation.schema -eq 'codex.runtimeAssetValidation.v2') "$profile runtime validation schema is not v2"
    foreach ($family in @('format','glb','bounds','fitAxis','pivot','triangles','textures','meshNodes','geometry','semantics')) {
      Assert-True ($null -ne $validation.checks.$family) "$profile missing check family $family"
    }
    Assert-True ([int]$validation.geometry.vertexCount -gt 0) "$profile geometry vertex count missing"
    Assert-True ([int]$validation.geometry.triangleCount -gt 0) "$profile geometry triangle count missing"
  }

  $postprocessDir = Join-Path $WorkDir 'postprocess-positive'
  New-Item -ItemType Directory -Force -Path $postprocessDir | Out-Null
  Copy-Item -Force -LiteralPath (Join-Path $normalizedDir 'wall.glb') -Destination (Join-Path $postprocessDir 'wall.glb')
  Invoke-External $python @(
    '-B', (Join-Path $scriptsDir 'postprocess_generation.py'),
    '--batch-output-dir', $postprocessDir,
    '--select', 'all',
    '--require-single',
    '--asset-profile', 'wall',
    '--profiles-dir', $profilesDir,
    '--normalization-report', (Join-Path $normalizedDir 'wall.normalization_report.json'),
    '--manifest-dir', (Join-Path $postprocessDir '_codex_postprocess')
  )

  Invoke-ExpectedFailure 'missing mesh' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', (Join-Path $WorkDir 'missing.glb'),
    '--profile', 'wall',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $badObj = Join-Path $WorkDir 'bad.obj'
  Set-Content -LiteralPath $badObj -Value 'o bad' -Encoding ASCII
  Invoke-ExpectedFailure 'forbidden format' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $badObj,
    '--profile', 'wall',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $budgetProfilesDir = Join-Path $WorkDir 'budget-profiles'
  Copy-Item -Recurse -Force -LiteralPath $profilesDir -Destination $budgetProfilesDir
  $budgetWall = Join-Path $budgetProfilesDir 'wall.json'
  $budgetProfile = Read-JsonFile $budgetWall
  $budgetProfile.validationRules.maxTriangleCount = 1
  Write-JsonFile $budgetWall $budgetProfile
  Invoke-ExpectedFailure 'triangle budget exceeded' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', (Join-Path $normalizedDir 'wall.glb'),
    '--profile', 'wall',
    '--profiles-dir', $budgetProfilesDir,
    '--json'
  )

  $emptyMesh = Join-Path $sourceDir 'empty.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $emptyMesh, '--variant', 'empty') | Out-Null
  Invoke-ExpectedFailure 'empty GLB has no mesh' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $emptyMesh,
    '--profile', 'prop',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $zeroTriangleMesh = Join-Path $sourceDir 'zero_triangle.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $zeroTriangleMesh, '--size', '1,1,1', '--variant', 'zero-triangle') | Out-Null
  Invoke-ExpectedFailure 'zero triangle mesh' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $zeroTriangleMesh,
    '--profile', 'prop',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $flatMesh = Join-Path $sourceDir 'flat.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $flatMesh, '--size', '1,1,1', '--variant', 'flat') | Out-Null
  Invoke-ExpectedFailure 'flat mesh' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $flatMesh,
    '--profile', 'prop',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $aberrantMesh = Join-Path $sourceDir 'aberrant.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $aberrantMesh, '--size', '100,1,1') | Out-Null
  Invoke-ExpectedFailure 'aberrant dimensions' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $aberrantMesh,
    '--profile', 'prop',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $multiNodeMesh = Join-Path $sourceDir 'multi_node.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $multiNodeMesh, '--size', '1,1,1', '--variant', 'multi-node') | Out-Null
  Invoke-ExpectedFailure 'multi-node singleObject violation' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $multiNodeMesh,
    '--profile', 'prop',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $largeTextureMesh = Join-Path $sourceDir 'large_texture.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $largeTextureMesh, '--size', '1,1,1', '--texture-size', '4096,4096') | Out-Null
  Invoke-ExpectedFailure 'texture budget exceeded' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $largeTextureMesh,
    '--profile', 'prop',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $badDoorMesh = Join-Path $sourceDir 'bad_door.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $badDoorMesh, '--size', '2.1,1.1,0.18') | Out-Null
  Invoke-ExpectedFailure 'door not vertical' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $badDoorMesh,
    '--profile', 'door',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $badTerrainMesh = Join-Path $sourceDir 'bad_terrain.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $badTerrainMesh, '--size', '0.4,4,4') | Out-Null
  Invoke-ExpectedFailure 'terrain not horizontal' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $badTerrainMesh,
    '--profile', 'terrain_piece',
    '--profiles-dir', $profilesDir,
    '--json'
  )

  $bedAsWallMesh = Join-Path $sourceDir 'bed_wall.glb'
  Invoke-External $python @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $bedAsWallMesh, '--size', '4,2,0.35') | Out-Null
  Invoke-ExpectedFailure 'bed cannot validate as wall' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', $bedAsWallMesh,
    '--profile', 'wall',
    '--profiles-dir', $profilesDir,
    '--asset-name', 'bed_wall',
    '--json'
  )

  $incompleteManifest = Join-Path $WorkDir 'incomplete_manifest.json'
  Set-Content -LiteralPath $incompleteManifest -Value '{}' -Encoding ASCII
  Invoke-ExpectedFailure 'incomplete manifest' $python @(
    '-B', (Join-Path $scriptsDir 'validate_runtime_asset.py'),
    '--mesh', (Join-Path $normalizedDir 'wall.glb'),
    '--profile', 'wall',
    '--profiles-dir', $profilesDir,
    '--manifest', $incompleteManifest,
    '--json'
  )

  $emptyDir = Join-Path $WorkDir 'empty-output'
  New-Item -ItemType Directory -Force -Path $emptyDir | Out-Null
  Invoke-ExpectedFailure 'missing postprocess mesh' $python @(
    '-B', (Join-Path $scriptsDir 'postprocess_generation.py'),
    '--batch-output-dir', $emptyDir,
    '--require-single'
  )

  $multiDir = Join-Path $WorkDir 'multi-output'
  New-Item -ItemType Directory -Force -Path $multiDir | Out-Null
  Copy-Item -Force -LiteralPath (Join-Path $normalizedDir 'wall.glb') -Destination (Join-Path $multiDir 'wall_a.glb')
  Copy-Item -Force -LiteralPath (Join-Path $normalizedDir 'prop.glb') -Destination (Join-Path $multiDir 'wall_b.glb')
  Invoke-ExpectedFailure 'ambiguous mesh selection' $python @(
    '-B', (Join-Path $scriptsDir 'postprocess_generation.py'),
    '--batch-output-dir', $multiDir,
    '--require-single'
  )

  $invalidUnity = Join-Path $WorkDir 'not-a-unity-project'
  New-Item -ItemType Directory -Force -Path $invalidUnity | Out-Null
  Invoke-ExpectedFailure 'invalid Unity project' $python @(
    '-B', (Join-Path $scriptsDir 'postprocess_generation.py'),
    '--batch-output-dir', $postprocessDir,
    '--select', 'all',
    '--require-single',
    '--unity-project', $invalidUnity
  )

  Write-Host 'Runtime validation gate OK'
  $global:LASTEXITCODE = 0
} finally {
  if (!$KeepWorkDir -and (Test-Path -LiteralPath $WorkDir)) {
    Remove-WorkDirSafely $WorkDir
  } elseif (Test-Path -LiteralPath $WorkDir) {
    Write-Host "Runtime validation work dir kept: $WorkDir"
  }
}
