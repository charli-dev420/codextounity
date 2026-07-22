param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = '',
  [switch]$KeepWorkDir
)
$ErrorActionPreference = 'Stop'

$createdDefaultWorkDir = $false
if (!$WorkDir) {
  $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-room-demo-planning-" + [guid]::NewGuid().ToString('N'))
  $createdDefaultWorkDir = $true
}

$python = 'python'
$scriptsDir = Join-Path $PluginRoot 'scripts'
$planner = Join-Path $scriptsDir 'plan_room_demo_batch.py'
$profilesDir = Join-Path $PluginRoot 'configs\asset-profiles'

function Invoke-External([string]$File, [string[]]$Arguments) {
  $output = & $File @Arguments 2>&1
  if ($LASTEXITCODE -ne 0) {
    $output | ForEach-Object { Write-Host $_ }
    throw "Command failed with exit code ${LASTEXITCODE}: $File $($Arguments -join ' ')"
  }
  return $output
}

function Invoke-ExpectedFailure([string]$Label, [string]$File, [string[]]$Arguments) {
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
  Write-Host "Expected failure OK: $Label"
}

function Assert-True([bool]$Condition, [string]$Message) {
  if (!$Condition) { throw $Message }
}

function Read-JsonFile([string]$Path) {
  $value = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  if ($value -is [array]) {
    foreach ($item in $value) { $item }
  } else {
    return $value
  }
}

function Write-JsonFile([string]$Path, [object]$Data) {
  $Data | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $Path -Encoding UTF8
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

function New-TestImages([string]$TargetDir, [string[]]$Names, [int]$Size = 512) {
  New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
  $makeScript = Join-Path $WorkDir 'make_room_demo_images.py'
  @'
import sys
from pathlib import Path
from PIL import Image, ImageDraw

target = Path(sys.argv[1])
size = int(sys.argv[2])
names = sys.argv[3:]
target.mkdir(parents=True, exist_ok=True)
palette = [(140, 120, 95), (165, 168, 160), (120, 84, 56), (80, 130, 165), (135, 98, 75), (95, 126, 88), (150, 110, 150)]
for idx, name in enumerate(names):
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    color = palette[idx % len(palette)]
    pad = max(48, size // 6)
    draw.rounded_rectangle((pad, pad, size - pad, size - pad), radius=12, fill=color, outline=(55, 55, 55), width=4)
    if "door" in name:
        draw.rectangle((size // 2 - 55, pad, size // 2 + 55, size - pad), fill=color, outline=(40, 40, 40), width=5)
    elif "window" in name:
        draw.rectangle((pad + 40, pad + 30, size - pad - 40, size - pad - 30), fill=(190, 220, 235), outline=(45, 60, 70), width=5)
    elif "table" in name or "chair" in name:
        draw.ellipse((pad + 50, pad + 50, size - pad - 50, size - pad - 50), fill=color, outline=(45, 45, 45), width=5)
    image.save(target / name)
'@ | Set-Content -LiteralPath $makeScript -Encoding UTF8
  $imageArgs = @('-B', $makeScript, $TargetDir, ([string]$Size)) + $Names
  Invoke-External $python $imageArgs | Out-Null
}

try {
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

  $validInput = Join-Path $WorkDir 'valid-input'
  New-TestImages $validInput @(
    'floor_platform.png',
    'wall_panel.png',
    'brick_wall.png',
    'door.png',
    'window_wall.png',
    'table.png',
    'mirror_decor.png'
  )
  $validOutput = Join-Path $WorkDir 'valid-output'
  Invoke-External $python @(
    '-B', $planner,
    '--input-dir', $validInput,
    '--output-dir', $validOutput,
    '--profiles-dir', $profilesDir,
    '--json'
  ) | Out-Null
  foreach ($required in @('candidate_images.json','candidate_contact_sheet.jpg','room_ready_report.json','selected_references.json','selected_room_assets_sheet.jpg')) {
    Assert-True (Test-Path -LiteralPath (Join-Path $validOutput $required)) "missing expected output: $required"
  }
  $selected = @(Read-JsonFile (Join-Path $validOutput 'selected_references.json'))
  Assert-True ($selected.Count -eq 7) "expected 7 selected assets, got $($selected.Count)"
  foreach ($asset in $selected) {
    Assert-True (![string]::IsNullOrWhiteSpace($asset.assetName)) 'assetName missing'
    Assert-True (![string]::IsNullOrWhiteSpace($asset.profile)) "profile missing for $($asset.assetName)"
    Assert-True (![string]::IsNullOrWhiteSpace($asset.role)) "role missing for $($asset.assetName)"
    Assert-True ($asset.targetBounds.x -gt 0 -and $asset.targetBounds.y -gt 0 -and $asset.targetBounds.z -gt 0) "invalid bounds for $($asset.assetName)"
    Assert-True (@('contain','x','y','z') -contains $asset.fitAxis) "invalid fitAxis for $($asset.assetName)"
    Assert-True ($null -ne $asset.unityPlacement.position -and $null -ne $asset.unityPlacement.rotationEuler) "unityPlacement incomplete for $($asset.assetName)"
    Assert-True (Test-Path -LiteralPath $asset.inputImage) "input copy missing for $($asset.assetName)"
    Assert-True (Test-Path -LiteralPath $asset.referenceCopy) "reference copy missing for $($asset.assetName)"
  }

  $hashInput = Join-Path $WorkDir 'hash-input'
  New-TestImages $hashInput @('a94f03e71d32c4b099b1520448f0d9c2.png') 512
  $hashOutput = Join-Path $WorkDir 'hash-output'
  Invoke-ExpectedFailure 'hash name without selection is ambiguous' $python @(
    '-B', $planner,
    '--input-dir', $hashInput,
    '--output-dir', $hashOutput,
    '--profiles-dir', $profilesDir,
    '--min-assets', '1',
    '--json'
  )
  Assert-True (Test-Path -LiteralPath (Join-Path $hashOutput 'candidate_contact_sheet.jpg')) 'ambiguous contact sheet missing'
  Assert-True (Test-Path -LiteralPath (Join-Path $hashOutput 'room_ready_report.json')) 'ambiguous report missing'

  $selectionInput = Join-Path $WorkDir 'selection-input'
  New-TestImages $selectionInput @('0a0b0c0d0e0f.png','1a1b1c1d1e1f.png') 512
  $selectionPath = Join-Path $WorkDir 'selection.json'
  Write-JsonFile $selectionPath @(
    @{ name = '0a0b0c0d0e0f.png'; assetName = 'floor_platform'; category = 'floor'; role = 'floor/platform base' },
    @{ name = '1a1b1c1d1e1f.png'; assetName = 'plain_wall'; category = 'wall'; role = 'plain wall panel' }
  )
  $selectionOutput = Join-Path $WorkDir 'selection-output'
  Invoke-External $python @(
    '-B', $planner,
    '--input-dir', $selectionInput,
    '--output-dir', $selectionOutput,
    '--profiles-dir', $profilesDir,
    '--selection', $selectionPath,
    '--min-assets', '2',
    '--max-assets', '2',
    '--json'
  ) | Out-Null
  $selectionRefs = @(Read-JsonFile (Join-Path $selectionOutput 'selected_references.json'))
  Assert-True ($selectionRefs.Count -eq 2) "selection should produce 2 assets"

  foreach ($badName in @('person.png','shirt.png','multi_chairs.png','room_scene.png')) {
    $badInput = Join-Path $WorkDir ("bad-" + [System.IO.Path]::GetFileNameWithoutExtension($badName))
    New-TestImages $badInput @($badName) 512
    Invoke-ExpectedFailure "reject $badName" $python @(
      '-B', $planner,
      '--input-dir', $badInput,
      '--output-dir', (Join-Path $WorkDir ("bad-output-" + [System.IO.Path]::GetFileNameWithoutExtension($badName))),
      '--profiles-dir', $profilesDir,
      '--min-assets', '1',
      '--json'
    )
  }

  $tinyInput = Join-Path $WorkDir 'tiny-input'
  New-TestImages $tinyInput @('floor_platform.png') 128
  Invoke-ExpectedFailure 'reject too-small image' $python @(
    '-B', $planner,
    '--input-dir', $tinyInput,
    '--output-dir', (Join-Path $WorkDir 'tiny-output'),
    '--profiles-dir', $profilesDir,
    '--min-assets', '1',
    '--json'
  )

  $badFormatInput = Join-Path $WorkDir 'bad-format-input'
  New-Item -ItemType Directory -Force -Path $badFormatInput | Out-Null
  Set-Content -LiteralPath (Join-Path $badFormatInput 'wall_panel.bmp') -Value 'not a supported image' -Encoding ASCII
  Invoke-ExpectedFailure 'reject unsupported format' $python @(
    '-B', $planner,
    '--input-dir', $badFormatInput,
    '--output-dir', (Join-Path $WorkDir 'bad-format-output'),
    '--profiles-dir', $profilesDir,
    '--min-assets', '1',
    '--json'
  )

  Write-Host 'Room demo planning gate OK'
  $global:LASTEXITCODE = 0
} finally {
  if (!$KeepWorkDir -and (Test-Path -LiteralPath $WorkDir)) {
    Remove-WorkDirSafely $WorkDir
  } elseif (Test-Path -LiteralPath $WorkDir) {
    Write-Host "Room demo planning work dir kept: $WorkDir"
  }
}
