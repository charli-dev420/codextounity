param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = '',
  [switch]$KeepWorkDir
)
$ErrorActionPreference = 'Stop'

if (!$WorkDir) {
  $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-room-demo-proof-" + [guid]::NewGuid().ToString('N'))
}

$scriptsDir = Join-Path $PluginRoot 'scripts'
$proofScript = Join-Path $scriptsDir 'build_room_demo_proof.ps1'

function Assert-True([bool]$Condition, [string]$Message) {
  if (!$Condition) { throw $Message }
}

function Read-JsonFile([string]$Path) {
  return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Write-JsonFile([string]$Path, [object]$Data) {
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $Data | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $Path -Encoding UTF8
}

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

function New-TestImage([string]$Path) {
  Add-Type -AssemblyName System.Drawing
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $bitmap = [System.Drawing.Bitmap]::new(256, 256)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.Clear([System.Drawing.Color]::White)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(120, 140, 115))
    try {
      $graphics.FillRectangle($brush, 48, 72, 160, 96)
    } finally {
      $brush.Dispose()
    }
    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $graphics.Dispose()
    $bitmap.Dispose()
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

try {
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
  $batchDir = Join-Path $WorkDir 'batch'
  $imagesDir = Join-Path $batchDir 'inputs'
  $glbDir = Join-Path $batchDir 'glbs'
  $outputDir = Join-Path $WorkDir 'proof-pack'
  New-Item -ItemType Directory -Force -Path $imagesDir, $glbDir | Out-Null

  $imagePath = Join-Path $imagesDir '01_floor_platform.png'
  $imagePath2 = Join-Path $imagesDir '02_plain_wall.png'
  New-TestImage $imagePath
  New-TestImage $imagePath2
  $glbPath = Join-Path $glbDir '01_floor_platform.glb'
  $glbPath2 = Join-Path $glbDir '02_plain_wall.glb'
  Invoke-External 'python' @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $glbPath, '--size', '4,0.4,4') | Out-Null
  Invoke-External 'python' @('-B', (Join-Path $scriptsDir 'create_test_glb.py'), '--out', $glbPath2, '--size', '4,2,0.25') | Out-Null

  @'
[
  {
    "assetName": "01_floor_platform",
    "profile": "terrain_piece",
    "role": "floor",
    "targetBounds": { "x": 4.0, "y": 0.4, "z": 4.0 },
    "fitAxis": "contain",
    "unityPlacement": {
      "position": { "x": 0, "y": 0, "z": 0 },
      "rotationEuler": { "x": 0, "y": 0, "z": 0 },
      "uniformScale": 1.0
    },
    "source": "phase-f-fixture",
    "inputImage": "__IMAGE__",
    "referenceCopy": "__IMAGE__"
  },
  {
    "assetName": "02_plain_wall",
    "profile": "wall",
    "role": "wall",
    "targetBounds": { "x": 4.0, "y": 2.0, "z": 0.35 },
    "fitAxis": "x",
    "unityPlacement": {
      "position": { "x": 0, "y": 1, "z": 2 },
      "rotationEuler": { "x": 0, "y": 0, "z": 0 },
      "uniformScale": 1.0
    },
    "source": "phase-f-fixture",
    "inputImage": "__IMAGE2__",
    "referenceCopy": "__IMAGE2__"
  }
]
'@.Replace('__IMAGE2__', ($imagePath2 -replace '\\','\\')).Replace('__IMAGE__', ($imagePath -replace '\\','\\')) | Set-Content -LiteralPath (Join-Path $batchDir 'selected_references.json') -Encoding UTF8

  Invoke-External 'powershell' @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    $proofScript,
    '-BatchProofDir',
    $batchDir,
    '-OutputDir',
    $outputDir,
    '-SkipUnity',
    '-MinAssets',
    '2'
  ) | Out-Null

  foreach ($required in @(
      'ROOM_DEMO_PROOF.json',
      'ROOM_DEMO_PROOF.md',
      'captures\selected_references.jpg',
      'model3d\01_floor_platform.glb',
      'model3d\02_plain_wall.glb',
      'reports\01_floor_platform.runtime_validation.json',
      'reports\02_plain_wall.runtime_validation.json',
      'reports\glb_manifest.json'
    )) {
    Assert-True (Test-Path -LiteralPath (Join-Path $outputDir $required) -PathType Leaf) "missing proof output: $required"
  }

  $proof = Read-JsonFile (Join-Path $outputDir 'ROOM_DEMO_PROOF.json')
  Assert-True ($proof.schema -eq 'codex.roomDemoProofPack.v1') 'proof schema mismatch'
  Assert-True ($proof.status -eq 'partial') "SkipUnity proof should be partial, got $($proof.status)"
  Assert-True ($proof.assets.Count -eq 2) "expected 2 proof assets, got $($proof.assets.Count)"
  Assert-True (![string]::IsNullOrWhiteSpace($proof.assets[0].sha256)) 'asset sha256 missing'
  Assert-True (@($proof.hashes).Count -ge 3) 'proof hashes missing'
  Assert-True ($proof.unity.attempted -eq $false) 'SkipUnity should not attempt Unity'

  Invoke-ExpectedFailure 'public proof output rejected' 'powershell' @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    $proofScript,
    '-BatchProofDir',
    $batchDir,
    '-OutputDir',
    (Join-Path $PluginRoot 'proof\bad-room-demo-proof'),
    '-SkipUnity',
    '-MinAssets',
    '1',
    '-DryRun'
  )

  Write-Host 'Room demo proof pack gate OK'
  $global:LASTEXITCODE = 0
} finally {
  if (!$KeepWorkDir -and (Test-Path -LiteralPath $WorkDir)) {
    Remove-WorkDirSafely $WorkDir
  } elseif (Test-Path -LiteralPath $WorkDir) {
    Write-Host "Room demo proof work dir kept: $WorkDir"
  }
}
