param(
  [Parameter(Mandatory = $true)]
  [string]$BatchProofDir,
  [string]$SelectedReferences = '',
  [string]$GlbDir = '',
  [string]$OutputDir = '',
  [string]$ProjectRoot = '',
  [string]$UnityExe = '',
  [string]$ManifestDir = '',
  [int]$MinAssets = 7,
  [switch]$ForceUnityRecreate,
  [switch]$SkipUnity,
  [switch]$NoGltfImporterInstall,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

function ConvertTo-SafeName([string]$Value) {
  $safe = ($Value -replace '[^A-Za-z0-9._-]+', '_').Trim('._-')
  if ([string]::IsNullOrWhiteSpace($safe)) { return 'asset' }
  return $safe
}

function Test-IsRelativeTo([string]$PathValue, [string]$ParentValue) {
  $pathFull = [System.IO.Path]::GetFullPath($PathValue).TrimEnd('\','/')
  $parentFull = [System.IO.Path]::GetFullPath($ParentValue).TrimEnd('\','/')
  return $pathFull.Equals($parentFull, [System.StringComparison]::OrdinalIgnoreCase) -or
    $pathFull.StartsWith($parentFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-OutputAllowed([string]$PathValue, [string]$PluginRoot) {
  $proofRoot = Join-Path $PluginRoot 'proof'
  if (Test-IsRelativeTo $PathValue $proofRoot) {
    throw "Phase F proof packs must not be written under the public proof folder: $PathValue"
  }
}

function Read-JsonFile([string]$PathValue) {
  $value = Get-Content -LiteralPath $PathValue -Raw | ConvertFrom-Json
  if ($value -is [array]) {
    foreach ($item in $value) { $item }
  } else {
    return $value
  }
}

function Write-JsonFile([string]$PathValue, [object]$Data) {
  $parent = Split-Path -Parent $PathValue
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $Data | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $PathValue -Encoding UTF8
}

function Find-SelectedReferences([string]$BatchRoot, [string]$Requested) {
  if ($Requested) {
    $resolved = (Resolve-Path -LiteralPath $Requested).Path
    if (!(Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "selected_references.json not found: $resolved" }
    return $resolved
  }
  $direct = Join-Path $BatchRoot 'selected_references.json'
  if (Test-Path -LiteralPath $direct -PathType Leaf) { return (Resolve-Path -LiteralPath $direct).Path }
  $matches = @(Get-ChildItem -LiteralPath $BatchRoot -Recurse -File -Filter 'selected_references.json' -ErrorAction SilentlyContinue |
    Sort-Object @{ Expression = { $_.FullName.Length }; Ascending = $true }, FullName)
  if ($matches.Count -eq 0) { throw "selected_references.json not found under batch proof dir: $BatchRoot" }
  return $matches[0].FullName
}

function Find-GlbRoot([string]$BatchRoot, [string]$Requested) {
  if ($Requested) {
    $resolved = (Resolve-Path -LiteralPath $Requested).Path
    if (!(Test-Path -LiteralPath $resolved -PathType Container)) { throw "GLB directory not found: $resolved" }
    return $resolved
  }
  foreach ($relative in @('normalized', 'glbs', 'model3d', 'trellis2\raw', 'raw')) {
    $candidate = Join-Path $BatchRoot $relative
    if (Test-Path -LiteralPath $candidate -PathType Container) {
      $glbs = @(Get-ChildItem -LiteralPath $candidate -Recurse -File -Filter '*.glb' -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 0 })
      if ($glbs.Count -gt 0) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
  }
  $rootGlbs = @(Get-ChildItem -LiteralPath $BatchRoot -Recurse -File -Filter '*.glb' -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 0 })
  if ($rootGlbs.Count -eq 0) { throw "no non-empty GLB found under batch proof dir: $BatchRoot" }
  return $BatchRoot
}

function Find-AssetGlb([string]$Root, [string]$AssetName) {
  $safe = ConvertTo-SafeName $AssetName
  $matches = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.glb' -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Length -gt 0 -and (
        $_.BaseName.Equals($AssetName, [System.StringComparison]::OrdinalIgnoreCase) -or
        $_.BaseName.Equals($safe, [System.StringComparison]::OrdinalIgnoreCase) -or
        $_.BaseName.StartsWith($safe, [System.StringComparison]::OrdinalIgnoreCase)
      )
    } |
    Sort-Object @{ Expression = 'LastWriteTimeUtc'; Descending = $true }, @{ Expression = 'Length'; Descending = $true }, FullName)
  if ($matches.Count -eq 0) { return $null }
  return $matches[0]
}

function Get-ReferenceImagePath([object]$Reference) {
  foreach ($key in @('referenceCopy', 'inputImage', 'source')) {
    $value = [string]$Reference.$key
    if (![string]::IsNullOrWhiteSpace($value) -and (Test-Path -LiteralPath $value -PathType Leaf)) {
      return (Resolve-Path -LiteralPath $value).Path
    }
  }
  return ''
}

function Copy-SelectedReferenceSheet([string]$BatchRoot, [array]$References, [string]$TargetPath) {
  $sheetNames = @('selected_room_assets_sheet.jpg','selected_room_assets_sheet.png','candidate_contact_sheet.jpg')
  $existing = @(Get-ChildItem -LiteralPath $BatchRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $sheetNames -contains $_.Name } |
    Sort-Object @{ Expression = { $_.Name -eq 'selected_room_assets_sheet.jpg' }; Descending = $true }, FullName)
  if ($existing.Count -gt 0) {
    Copy-Item -Force -LiteralPath $existing[0].FullName -Destination $TargetPath
    return
  }

  Add-Type -AssemblyName System.Drawing
  $imagePaths = @($References | ForEach-Object { Get-ReferenceImagePath $_ } | Where-Object { $_ })
  $columns = 4
  $thumbW = 220
  $thumbH = 170
  $labelH = 36
  $headerH = 42
  $rows = [Math]::Max(1, [Math]::Ceiling([double][Math]::Max(1, $imagePaths.Count) / $columns))
  $sheet = [System.Drawing.Bitmap]::new($columns * $thumbW, $headerH + ($rows * ($thumbH + $labelH)))
  $graphics = [System.Drawing.Graphics]::FromImage($sheet)
  $graphics.Clear([System.Drawing.Color]::White)
  $font = [System.Drawing.Font]::new('Arial', 10)
  $titleFont = [System.Drawing.Font]::new('Arial', 14, [System.Drawing.FontStyle]::Bold)
  try {
    $graphics.DrawString('Selected room demo references', $titleFont, [System.Drawing.Brushes]::Black, 12, 10)
    if ($imagePaths.Count -eq 0) {
      $graphics.DrawString('No reference images were available in selected_references.json.', $font, [System.Drawing.Brushes]::Black, 12, $headerH + 20)
    }
    for ($i = 0; $i -lt $imagePaths.Count; $i++) {
      $column = $i % $columns
      $row = [Math]::Floor($i / $columns)
      $x = $column * $thumbW
      $y = $headerH + ($row * ($thumbH + $labelH))
      $image = [System.Drawing.Image]::FromFile($imagePaths[$i])
      try {
        $scale = [Math]::Min(($thumbW - 18) / $image.Width, ($thumbH - 18) / $image.Height)
        $w = [int]($image.Width * $scale)
        $h = [int]($image.Height * $scale)
        $dx = $x + [int](($thumbW - $w) / 2)
        $dy = $y + [int](($thumbH - $h) / 2)
        $graphics.DrawImage($image, $dx, $dy, $w, $h)
      } finally {
        $image.Dispose()
      }
      $assetName = [string]$References[$i].assetName
      if ([string]::IsNullOrWhiteSpace($assetName)) { $assetName = [System.IO.Path]::GetFileNameWithoutExtension($imagePaths[$i]) }
      $graphics.DrawString(("{0}. {1}" -f ($i + 1), $assetName), $font, [System.Drawing.Brushes]::Black, $x + 8, $y + $thumbH + 5)
    }
    $parent = Split-Path -Parent $TargetPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $sheet.Save($TargetPath, [System.Drawing.Imaging.ImageFormat]::Jpeg)
  } finally {
    $font.Dispose()
    $titleFont.Dispose()
    $graphics.Dispose()
    $sheet.Dispose()
  }
}

function Invoke-RuntimeValidation([string]$PluginRoot, [string]$MeshPath, [string]$Profile, [string]$AssetName, [string]$ReportPath) {
  if ([string]::IsNullOrWhiteSpace($Profile)) {
    $report = [ordered]@{
      schema = 'codex.runtimeAssetValidation.v2'
      valid = $false
      assetId = $AssetName
      errors = @('profile is missing in selected_references.json')
      warnings = @()
    }
    Write-JsonFile $ReportPath $report
    return $report
  }
  $validator = Join-Path $PluginRoot 'scripts\validate_runtime_asset.py'
  $profilesDir = Join-Path $PluginRoot 'configs\asset-profiles'
  $raw = & python -B $validator --mesh $MeshPath --profile $Profile --profiles-dir $profilesDir --asset-name $AssetName --json 2>&1
  $text = ($raw -join "`n").Trim()
  try {
    $report = $text | ConvertFrom-Json
  } catch {
    $report = [ordered]@{
      schema = 'codex.runtimeAssetValidation.v2'
      valid = $false
      assetId = $AssetName
      errors = @("runtime validation did not return JSON: $text")
      warnings = @()
    }
  }
  Write-JsonFile $ReportPath $report
  return $report
}

function ConvertFrom-JsonOutput([object[]]$OutputLines) {
  $text = ($OutputLines | ForEach-Object { [string]$_ }) -join "`n"
  $start = $text.IndexOf('{')
  $end = $text.LastIndexOf('}')
  if ($start -lt 0 -or $end -lt $start) { throw "command did not emit JSON: $text" }
  return $text.Substring($start, $end - $start + 1) | ConvertFrom-Json
}

function Find-UnityExe([string]$Requested) {
  if ($Requested) {
    $candidate = [System.IO.Path]::GetFullPath($Requested)
    if (!(Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Unity executable not found: $candidate" }
    return $candidate
  }
  if ($env:UNITY_EXE) {
    $candidate = [System.IO.Path]::GetFullPath($env:UNITY_EXE)
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
  }
  $hubRoot = 'C:\Program Files\Unity\Hub\Editor'
  if (Test-Path -LiteralPath $hubRoot -PathType Container) {
    $editors = @(Get-ChildItem -LiteralPath $hubRoot -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -notmatch '(?i)(alpha|beta|a\d+$|b\d+$)' } |
      ForEach-Object {
        $exe = Join-Path $_.FullName 'Editor\Unity.exe'
        if (Test-Path -LiteralPath $exe -PathType Leaf) {
          [pscustomobject]@{ Version = $_.Name; Path = $exe }
        }
      } |
      Sort-Object Version -Descending)
    if ($editors.Count -gt 0) { return $editors[0].Path }
  }
  throw 'Unity executable not found. Pass -UnityExe or set UNITY_EXE.'
}

function ConvertTo-ProcessArgumentString([string[]]$Arguments) {
  return (($Arguments | ForEach-Object {
        $value = [string]$_
        if ([string]::IsNullOrEmpty($value)) { return '""' }
        if ($value -notmatch '[\s"]') { return $value }
        '"' + ($value.Replace('"', '\"')) + '"'
      }) -join ' ')
}

function Invoke-UnityBatch([string]$ExePath, [string[]]$Arguments, [string]$LogPath, [string]$Label) {
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $ExePath
  $psi.Arguments = ConvertTo-ProcessArgumentString $Arguments
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $process = [System.Diagnostics.Process]::Start($psi)
  if ($null -eq $process) { throw "$Label failed to start Unity executable: $ExePath" }
  $process.WaitForExit()
  if ($process.ExitCode -ne 0) {
    throw "$Label failed with exit code $($process.ExitCode). Log: $LogPath"
  }
}

function Get-ProofHashes([string]$OutputRoot) {
  $hashes = @()
  foreach ($relative in @('model3d', 'captures', 'reports')) {
    $dir = Join-Path $OutputRoot $relative
    if (!(Test-Path -LiteralPath $dir -PathType Container)) { continue }
    $hashes += @(Get-ChildItem -LiteralPath $dir -Recurse -File | Sort-Object FullName | ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        [ordered]@{
          path = $_.FullName
          relativePath = (Resolve-Path -LiteralPath $_.FullName -Relative).Replace('.\', '').Replace('\','/')
          sha256 = $hash.Hash.ToLowerInvariant()
          bytes = $_.Length
        }
      })
  }
  return $hashes
}

function Write-ProofMarkdown([string]$PathValue, [object]$Proof) {
  $lines = @()
  $lines += '# Room Demo Proof Pack'
  $lines += ''
  $lines += "Status: $($Proof.status)"
  $lines += ''
  $lines += 'This proof pack documents an experimental prototype. It is broadly untested and comes with no guarantee of any kind.'
  $lines += ''
  $lines += '## Inputs'
  $lines += ('- Batch proof dir: `{0}`' -f $Proof.batchProofDir)
  $lines += ('- Selected references: `{0}`' -f $Proof.selectedReferences)
  $lines += ('- Minimum assets: `{0}`' -f $Proof.minAssets)
  $lines += ''
  $lines += '## Outputs'
  $lines += '- Model copies: `model3d/`'
  $lines += '- Captures: `captures/`'
  $lines += '- Reports: `reports/`'
  $lines += ''
  $lines += '## Assets'
  foreach ($asset in @($Proof.assets)) {
    $state = if ($asset.runtimeValid) { 'valid' } else { 'review' }
    $lines += ('- {0} [{1}] {2} - `{3}`' -f $asset.assetName, $asset.profile, $state, $asset.copyRelativePath)
  }
  $lines += ''
  $lines += '## Captures'
  foreach ($property in @('selectedReferences','unityImport','cleanScene')) {
    $value = $Proof.captures.$property
    if ($value) { $lines += ('- {0}: `{1}`' -f $property, $value) }
  }
  if ($Proof.errors.Count -gt 0) {
    $lines += ''
    $lines += '## Errors'
    foreach ($error in @($Proof.errors)) { $lines += "- $error" }
  }
  if ($Proof.warnings.Count -gt 0) {
    $lines += ''
    $lines += '## Warnings'
    foreach ($warning in @($Proof.warnings)) { $lines += "- $warning" }
  }
  Set-Content -LiteralPath $PathValue -Encoding UTF8 -Value $lines
}

if ($MinAssets -lt 1) { throw '-MinAssets must be >= 1' }
$pluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$batchRoot = (Resolve-Path -LiteralPath $BatchProofDir).Path
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path (Join-Path $pluginRoot '.codex\room-demo-proof-packs') ((Split-Path -Leaf $batchRoot) + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$outputFull = [System.IO.Path]::GetFullPath($OutputDir)
Assert-OutputAllowed $outputFull $pluginRoot

$selectedPath = Find-SelectedReferences $batchRoot $SelectedReferences
$glbRoot = Find-GlbRoot $batchRoot $GlbDir
$referencesRaw = Read-JsonFile $selectedPath
$references = @($referencesRaw)
if ($references.Count -lt $MinAssets) { throw "selected references count $($references.Count) is below -MinAssets $MinAssets" }

$assetPlan = @()
$missing = @()
foreach ($reference in $references) {
  $assetName = [string]$reference.assetName
  if ([string]::IsNullOrWhiteSpace($assetName)) {
    $missing += '<missing assetName>'
    continue
  }
  $glb = Find-AssetGlb $glbRoot $assetName
  if ($null -eq $glb) {
    $missing += $assetName
    continue
  }
  $safe = ConvertTo-SafeName $assetName
  $assetPlan += [pscustomobject]@{
    assetName = $assetName
    safeName = $safe
    profile = [string]$reference.profile
    role = [string]$reference.role
    sourceGlb = $glb.FullName
    copyGlb = Join-Path (Join-Path $outputFull 'model3d') "$safe.glb"
    reference = $reference
  }
}
if ($missing.Count -gt 0) { throw "missing GLB for selected asset(s): $($missing -join ', ')" }
if ($assetPlan.Count -lt $MinAssets) { throw "matched GLB count $($assetPlan.Count) is below -MinAssets $MinAssets" }

$dryPlan = [ordered]@{
  schema = 'codex.roomDemoProofPackPlan.v1'
  dryRun = [bool]$DryRun
  batchProofDir = $batchRoot
  selectedReferences = $selectedPath
  glbDir = $glbRoot
  outputDir = $outputFull
  minAssets = $MinAssets
  skipUnity = [bool]$SkipUnity
  installGltfImporter = -not [bool]$NoGltfImporterInstall
  assetCount = $assetPlan.Count
  assets = @($assetPlan | ForEach-Object {
      [ordered]@{
        assetName = $_.assetName
        profile = $_.profile
        role = $_.role
        sourceGlb = $_.sourceGlb
        copyGlb = $_.copyGlb
      }
    })
}
if ($DryRun) {
  $dryPlan | ConvertTo-Json -Depth 30
  exit 0
}

$capturesDir = Join-Path $outputFull 'captures'
$modelDir = Join-Path $outputFull 'model3d'
$reportsDir = Join-Path $outputFull 'reports'
New-Item -ItemType Directory -Force -Path $capturesDir, $modelDir, $reportsDir | Out-Null

$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$assets = @()

$referenceSheet = Join-Path $capturesDir 'selected_references.jpg'
Copy-SelectedReferenceSheet $batchRoot $references $referenceSheet

foreach ($asset in $assetPlan) {
  Copy-Item -Force -LiteralPath $asset.sourceGlb -Destination $asset.copyGlb
  $hash = Get-FileHash -LiteralPath $asset.copyGlb -Algorithm SHA256
  $runtimeReport = Join-Path $reportsDir "$($asset.safeName).runtime_validation.json"
  $validation = Invoke-RuntimeValidation $pluginRoot $asset.copyGlb $asset.profile $asset.assetName $runtimeReport
  if ($validation.valid -ne $true) {
    $warnings.Add("runtime validation requires review for $($asset.assetName)") | Out-Null
  }
  $assets += [ordered]@{
    assetName = $asset.assetName
    profile = $asset.profile
    role = $asset.role
    sourceGlb = $asset.sourceGlb
    copyGlb = $asset.copyGlb
    copyRelativePath = ('model3d/' + (Split-Path -Leaf $asset.copyGlb))
    sha256 = $hash.Hash.ToLowerInvariant()
    bytes = (Get-Item -LiteralPath $asset.copyGlb).Length
    runtimeReport = $runtimeReport
    runtimeValid = ($validation.valid -eq $true)
  }
}
Write-JsonFile (Join-Path $reportsDir 'glb_manifest.json') ([ordered]@{
    schema = 'codex.roomDemoGlbManifest.v1'
    assetCount = $assets.Count
    assets = $assets
  })

$unity = [ordered]@{
  attempted = -not [bool]$SkipUnity
  valid = $false
  projectRoot = ''
  scene = ''
  rootPrefab = ''
  sceneBuilderReport = ''
  proofCaptureReport = ''
  gltfImporterPackage = ''
  gltfImporterPackageReport = ''
  log = ''
}
$captures = [ordered]@{
  selectedReferences = $referenceSheet
  unityImport = ''
  cleanScene = ''
}

if ($SkipUnity) {
  $warnings.Add('Unity capture skipped by -SkipUnity; proof pack status is partial.') | Out-Null
} else {
  try {
    $builder = Join-Path $pluginRoot 'scripts\build_unity_validation_project.ps1'
    $builderArgs = @(
      '-NoProfile',
      '-ExecutionPolicy',
      'Bypass',
      '-File',
      $builder,
      '-SelectedReferences',
      $selectedPath,
      '-GlbDir',
      $modelDir,
      '-MinAssets',
      ([string]$MinAssets)
    )
    if ($ProjectRoot) { $builderArgs += @('-ProjectRoot', $ProjectRoot) }
    if ($UnityExe) { $builderArgs += @('-UnityExe', $UnityExe) }
    if ($ManifestDir) { $builderArgs += @('-ManifestDir', $ManifestDir) }
    if ($ForceUnityRecreate) { $builderArgs += '-ForceRecreate' }
    if (!$NoGltfImporterInstall) { $builderArgs += '-InstallGltfImporter' }
    $builderOutput = & powershell @builderArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw (($builderOutput | ForEach-Object { [string]$_ }) -join "`n")
    }
    $builderSummary = ConvertFrom-JsonOutput $builderOutput
    $unity.projectRoot = [string]$builderSummary.projectRoot
    $unity.scene = [string]$builderSummary.result.scene
    $unity.rootPrefab = [string]$builderSummary.result.rootPrefab
    $unity.sceneBuilderReport = [string]$builderSummary.result.report
    $unity.gltfImporterPackage = [string]$builderSummary.gltfImporterPackage
    $unity.gltfImporterPackageReport = [string]$builderSummary.result.gltfImporterPackageReport
    $unity.log = [string]$builderSummary.result.log
    if ($unity.sceneBuilderReport -and (Test-Path -LiteralPath $unity.sceneBuilderReport -PathType Leaf)) {
      Copy-Item -Force -LiteralPath $unity.sceneBuilderReport -Destination (Join-Path $reportsDir 'unity_scene_builder_report.json')
    }
    if ($unity.gltfImporterPackageReport -and (Test-Path -LiteralPath $unity.gltfImporterPackageReport -PathType Leaf)) {
      $packageReportCopy = Join-Path $reportsDir 'gltf_importer_package_report.json'
      Copy-Item -Force -LiteralPath $unity.gltfImporterPackageReport -Destination $packageReportCopy
      $unity.gltfImporterPackageReport = $packageReportCopy
    }

    $resolvedUnityExe = if ($builderSummary.unityExe) { [string]$builderSummary.unityExe } else { Find-UnityExe $UnityExe }
    $captureReport = Join-Path $reportsDir 'unity_proof_capture_report.json'
    $captureLog = Join-Path $reportsDir 'unity_proof_capture.log'
    $unityImportCapture = Join-Path $capturesDir 'unity_import.png'
    $cleanSceneCapture = Join-Path $capturesDir 'clean_scene.png'
    Remove-Item -Force -LiteralPath $captureReport, $captureLog, $unityImportCapture, $cleanSceneCapture -ErrorAction SilentlyContinue
    Invoke-UnityBatch $resolvedUnityExe @(
      '-batchmode',
      '-quit',
      '-projectPath',
      $unity.projectRoot,
      '-logFile',
      $captureLog,
      '-executeMethod',
      'AIAssetFactory.EditorTools.CodexRoomDemoProofCapture.CaptureFromCommandLine',
      '-codexProofSelectedReferences',
      $selectedPath,
      '-codexProofManifestDir',
      [string]$builderSummary.manifestDir,
      '-codexProofScenePath',
      [string]$builderSummary.scenePath,
      '-codexProofImportCapture',
      $unityImportCapture,
      '-codexProofCleanSceneCapture',
      $cleanSceneCapture,
      '-codexProofReport',
      $captureReport
    ) $captureLog 'Unity proof capture'
    if (!(Test-Path -LiteralPath $captureReport -PathType Leaf)) { throw "Unity proof capture did not write report: $captureReport" }
    $captureResult = Read-JsonFile $captureReport
    if ($captureResult.valid -ne $true) {
      $captureErrors = @($captureResult.errors) -join '; '
      throw "Unity proof capture report is invalid: $captureErrors"
    }
    foreach ($capturePath in @($unityImportCapture, $cleanSceneCapture)) {
      if (!(Test-Path -LiteralPath $capturePath -PathType Leaf) -or ((Get-Item -LiteralPath $capturePath).Length -le 0)) {
        throw "Unity capture is missing or empty: $capturePath"
      }
    }
    $captures.unityImport = $unityImportCapture
    $captures.cleanScene = $cleanSceneCapture
    $unity.valid = $true
    $unity.proofCaptureReport = $captureReport
  } catch {
    $errors.Add("Unity proof step failed: $($_.Exception.Message)") | Out-Null
  }
}

$status = 'complete'
if ($errors.Count -gt 0 -or $SkipUnity -or -not $unity.valid -or @($assets | Where-Object { -not $_.runtimeValid }).Count -gt 0) {
  $status = if ($assets.Count -gt 0) { 'partial' } else { 'failed' }
}

$proof = [ordered]@{
  schema = 'codex.roomDemoProofPack.v1'
  generatedAt = (Get-Date).ToUniversalTime().ToString('o')
  status = $status
  experimentalStatus = 'experimental prototype, broadly untested, no guarantee of any kind'
  batchProofDir = $batchRoot
  selectedReferences = $selectedPath
  glbDir = $glbRoot
  outputDir = $outputFull
  minAssets = $MinAssets
  assets = $assets
  captures = $captures
  unity = $unity
  warnings = @($warnings.ToArray())
  errors = @($errors.ToArray())
}
$proof.hashes = Get-ProofHashes $outputFull

$proofJson = Join-Path $outputFull 'ROOM_DEMO_PROOF.json'
$proofMd = Join-Path $outputFull 'ROOM_DEMO_PROOF.md'
Write-JsonFile $proofJson $proof
Write-ProofMarkdown $proofMd $proof

$proof | ConvertTo-Json -Depth 100
if (($errors.Count -gt 0 -and !$SkipUnity) -or $status -eq 'failed') { exit 2 }
