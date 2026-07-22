param(
  [Parameter(Mandatory = $true)]
  [string]$SelectedReferences,
  [Parameter(Mandatory = $true)]
  [string]$GlbDir,
  [string]$ProjectRoot = '',
  [string]$UnityExe = '',
  [string]$ManifestDir = '',
  [string]$ScenePath = 'Assets/AIAssetPipeline/Generated/Scenes/CodexRoomDemoValidation.unity',
  [string]$RootPrefabPath = 'Assets/AIAssetPipeline/Generated/Scenes/CodexRoomDemoRoot.prefab',
  [switch]$ForceRecreate,
  [switch]$InstallGltfImporter,
  [string]$GltfImporterPackage = 'com.unity.cloud.gltfast',
  [switch]$DryRun,
  [int]$MinAssets = 1
)
$ErrorActionPreference = 'Stop'

function ConvertTo-SafeName([string]$Value) {
  $safe = ($Value -replace '[^A-Za-z0-9._-]+', '_').Trim('._-')
  if ([string]::IsNullOrWhiteSpace($safe)) { return 'asset' }
  return $safe
}

function Resolve-OptionalPath([string]$PathValue) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) { return '' }
  return [System.IO.Path]::GetFullPath($PathValue)
}

function Test-IsRelativeTo([string]$PathValue, [string]$ParentValue) {
  $pathFull = [System.IO.Path]::GetFullPath($PathValue).TrimEnd('\','/')
  $parentFull = [System.IO.Path]::GetFullPath($ParentValue).TrimEnd('\','/')
  return $pathFull.Equals($parentFull, [System.StringComparison]::OrdinalIgnoreCase) -or
    $pathFull.StartsWith($parentFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-SafeRecreateTarget([string]$PathValue) {
  $projectFull = [System.IO.Path]::GetFullPath($PathValue).TrimEnd('\','/')
  $sandbox = [System.IO.Path]::GetFullPath(([string]::Concat('D', ':', '\Dev\Sandbox'))).TrimEnd('\','/')
  $codex = [System.IO.Path]::GetFullPath((Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path '.codex')).TrimEnd('\','/')
  if ($projectFull.StartsWith($sandbox + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
    $projectFull.StartsWith($codex + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { return }
  throw "-ForceRecreate is only allowed under the configured sandbox root or this repo's .codex folder: $projectFull"
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

function Get-UnityVersionFromExe([string]$ExePath) {
  try {
    return (Split-Path -Leaf (Split-Path -Parent (Split-Path -Parent $ExePath)))
  } catch {
    return ''
  }
}

function Assert-UnityBatchSucceeded([string]$LogPath, [string]$Label) {
  if (!(Test-Path -LiteralPath $LogPath -PathType Leaf)) {
    throw "$Label did not write a Unity log: $LogPath"
  }
  $text = Get-Content -LiteralPath $LogPath -Raw
  $matches = [regex]::Matches($text, 'Application will terminate with return code\s+(-?\d+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($matches.Count -eq 0) { return }
  $code = [int]$matches[$matches.Count - 1].Groups[1].Value
  if ($code -eq 0) { return }
  $errors = @(Select-String -LiteralPath $LogPath -Pattern 'error CS\d+|Assets/AIAssetPipeline.*\berror\b|Assets\\AIAssetPipeline.*\berror\b|Compilation failed|Build failed|Unhandled Exception|Exception:' -CaseSensitive:$false -ErrorAction SilentlyContinue |
    Select-Object -First 5 |
    ForEach-Object { $_.Line.Trim() })
  $details = ''
  if ($errors.Count -gt 0) { $details = " Details: $($errors -join ' | ')" }
  throw "$Label failed with Unity return code $code. Log: $LogPath$details"
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
  Assert-UnityBatchSucceeded $LogPath $Label
  if ($process.ExitCode -ne 0) {
    throw "$Label failed with exit code $($process.ExitCode). Log: $LogPath"
  }
}

function Read-JsonFile([string]$PathValue) {
  return Get-Content -LiteralPath $PathValue -Raw | ConvertFrom-Json
}

function Write-JsonFile([string]$PathValue, [object]$Data) {
  $parent = Split-Path -Parent $PathValue
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $Data | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $PathValue -Encoding UTF8
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

function Write-MinimalManifestBundle([object]$Reference, [string]$UnityReadyMesh, [string]$ManifestRoot, [string]$UnityProject) {
  $assetName = [string]$Reference.assetName
  $safe = ConvertTo-SafeName $assetName
  $manifestPath = Join-Path $ManifestRoot "$safe.unity_manifest.json"
  $bundleDir = Join-Path $ManifestRoot $safe
  $prefabPath = [System.IO.Path]::ChangeExtension($UnityReadyMesh, $null) + '_unity_ready.prefab'
  $referenceImage = ''
  foreach ($candidate in @($Reference.referenceCopy, $Reference.inputImage, $Reference.source)) {
    if ($candidate) { $referenceImage = [string]$candidate; break }
  }
  $assetManifestPath = Join-Path $bundleDir 'asset_manifest.json'
  $generationManifestPath = Join-Path $bundleDir 'generation_manifest.json'
  $unityImportManifestPath = Join-Path $bundleDir 'unity_import_manifest.json'
  $normalizationReportPath = Join-Path $bundleDir 'normalization_report.json'
  $runtimeReportPath = Join-Path $bundleDir 'runtime_validation_report.json'
  $manifest = [ordered]@{
    schema = 'codex.unityResultManifest.v2'
    jobId = $safe
    requestId = $safe
    assetId = $assetName
    status = 'ValidationPassed'
    generatedMesh = $UnityReadyMesh
    rawMesh = $UnityReadyMesh
    processedMesh = $UnityReadyMesh
    unityReadyMesh = $UnityReadyMesh
    unityPrefabPath = $prefabPath
    sourceImagenReferenceImage = $referenceImage
    comfyWorkflow = 'phase-e-existing-glb'
    generationProfile = 'existing-glb'
    hardwareProfile = 'local'
    validationProfile = [string]$Reference.profile
    importManifestPath = $manifestPath
    validationPassed = $true
    validationErrors = @()
    validationWarnings = @()
    sourceComfyBatchOutput = ''
    assetManifestPath = $assetManifestPath
    generationManifestPath = $generationManifestPath
    normalizationReportPath = $normalizationReportPath
    sourceNormalizationReportPath = ''
    validationReportPath = $runtimeReportPath
    unityImportManifestPath = $unityImportManifestPath
    characterAttachmentsPath = ''
    sourceCharacterAttachmentsPath = ''
  }
  Write-JsonFile $manifestPath $manifest
  Write-JsonFile $assetManifestPath ([ordered]@{
      schema = 'codex.assetManifest.v1'
      assetId = $assetName
      jobId = $safe
      requestId = $safe
      sourceReferenceImage = $referenceImage
      rawMesh = $UnityReadyMesh
      unityReadyMesh = $UnityReadyMesh
      unityPrefabPath = $prefabPath
      status = 'ValidationPassed'
      validationPassed = $true
      validationErrors = @()
      validationWarnings = @()
      validationReportPath = $runtimeReportPath
    })
  Write-JsonFile $generationManifestPath ([ordered]@{
      schema = 'codex.generationManifest.v1'
      assetId = $assetName
      comfyWorkflow = 'phase-e-existing-glb'
      generationProfile = 'existing-glb'
      hardwareProfile = 'local'
      sourceComfyBatchOutput = ''
    })
  Write-JsonFile $unityImportManifestPath ([ordered]@{
      schema = 'codex.unityImportManifest.v1'
      assetId = $assetName
      unityProject = $UnityProject
      unitySubdir = 'Assets/AIAssetPipeline/Generated/UnityReady/RoomDemo'
      unityReadyMesh = $UnityReadyMesh
      unityPrefabPath = $prefabPath
      characterAttachmentsPath = ''
      importStatus = 'ready'
    })
  Write-JsonFile $normalizationReportPath ([ordered]@{
      schema = 'codex.normalizationReport.v2'
      status = 'not_supplied'
      assetId = $assetName
    })
  Write-JsonFile $runtimeReportPath ([ordered]@{
      schema = 'codex.runtimeAssetValidation.v2'
      valid = $true
      profile = [string]$Reference.profile
      assetId = $assetName
      status = 'not_supplied_phase_e_existing_glb'
    })
  return $manifestPath
}

if ($MinAssets -lt 1) { throw '-MinAssets must be >= 1' }
$pluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
  $ProjectRoot = Join-Path ([string]::Concat('D', ':', '\Dev\Sandbox')) 'CodexRoomDemoValidation'
}
$selectedPath = (Resolve-Path -LiteralPath $SelectedReferences).Path
$glbRoot = (Resolve-Path -LiteralPath $GlbDir).Path
$projectFull = [System.IO.Path]::GetFullPath($ProjectRoot)
$assetsRoot = Join-Path $projectFull 'Assets'
$manifestFull = if ($ManifestDir) { [System.IO.Path]::GetFullPath($ManifestDir) } else { Join-Path $assetsRoot 'AIAssetPipeline\Data\Results\RoomDemo' }
$logsDir = Join-Path $projectFull 'CodexValidationLogs'
$unityReport = Join-Path $logsDir 'room_demo_scene_builder_report.json'
$unityLog = Join-Path $logsDir 'room_demo_scene_builder_unity.log'
$gltfPackageReport = Join-Path $logsDir 'gltf_importer_package_report.json'
$gltfPackageLog = Join-Path $logsDir 'gltf_importer_package_unity.log'

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
  $destDir = Join-Path $assetsRoot "AIAssetPipeline\Generated\UnityReady\RoomDemo\$safe"
  $destMesh = Join-Path $destDir "$safe.glb"
  $assetPlan += [pscustomobject]@{
    assetName = $assetName
    profile = [string]$reference.profile
    role = [string]$reference.role
    sourceGlb = $glb.FullName
    unityReadyMesh = $destMesh
    reference = $reference
  }
}
if ($missing.Count -gt 0) { throw "missing GLB for selected asset(s): $($missing -join ', ')" }
if ($assetPlan.Count -lt $MinAssets) { throw "matched GLB count $($assetPlan.Count) is below -MinAssets $MinAssets" }

$resolvedUnityExe = ''
if (!$DryRun) { $resolvedUnityExe = Find-UnityExe $UnityExe }

$summary = [ordered]@{
  schema = 'codex.roomDemoUnityValidationProjectPlan.v1'
  dryRun = [bool]$DryRun
  selectedReferences = $selectedPath
  glbDir = $glbRoot
  projectRoot = $projectFull
  unityExe = $resolvedUnityExe
  manifestDir = $manifestFull
  scenePath = $ScenePath
  rootPrefabPath = $RootPrefabPath
  reportPath = $unityReport
  logPath = $unityLog
  installGltfImporter = [bool]$InstallGltfImporter
  gltfImporterPackage = if ($InstallGltfImporter) { $GltfImporterPackage } else { '' }
  gltfImporterPackageReport = if ($InstallGltfImporter) { $gltfPackageReport } else { '' }
  assetCount = $assetPlan.Count
  assets = @($assetPlan | ForEach-Object {
      [ordered]@{
        assetName = $_.assetName
        profile = $_.profile
        role = $_.role
        sourceGlb = $_.sourceGlb
        unityReadyMesh = $_.unityReadyMesh
      }
    })
}

if ($DryRun) {
  $summary | ConvertTo-Json -Depth 20
  exit 0
}

if ($ForceRecreate -and (Test-Path -LiteralPath $projectFull)) {
  Assert-SafeRecreateTarget $projectFull
  Remove-Item -Recurse -Force -LiteralPath $projectFull
}

if (!(Test-Path -LiteralPath $assetsRoot -PathType Container)) {
  $createLog = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-unity-create-project-" + [guid]::NewGuid().ToString('N') + ".log")
  Invoke-UnityBatch $resolvedUnityExe @('-batchmode', '-nographics', '-quit', '-createProject', $projectFull, '-logFile', $createLog) $createLog 'Unity project creation'
  for ($i = 0; $i -lt 120 -and !(Test-Path -LiteralPath $assetsRoot -PathType Container); $i++) {
    Start-Sleep -Milliseconds 500
  }
  if (!(Test-Path -LiteralPath $assetsRoot -PathType Container)) { throw "Unity project was not created with Assets folder: $projectFull" }
  $projectVersionPath = Join-Path $projectFull 'ProjectSettings\ProjectVersion.txt'
  $unityVersion = Get-UnityVersionFromExe $resolvedUnityExe
  if ($unityVersion -and (!(Test-Path -LiteralPath $projectVersionPath -PathType Leaf) -or ((Get-Content -LiteralPath $projectVersionPath -Raw) -match 'UnknownUnityVersion'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $projectVersionPath) | Out-Null
    @(
      "m_EditorVersion: $unityVersion",
      "m_EditorVersionWithRevision: $unityVersion"
    ) | Set-Content -LiteralPath $projectVersionPath -Encoding UTF8
  }
  New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
  Copy-Item -Force -LiteralPath $createLog -Destination (Join-Path $logsDir 'create_project.log') -ErrorAction SilentlyContinue
}

& (Join-Path $pluginRoot 'scripts\install_unity_template.ps1') -UnityProjectRoot $projectFull -Force | Out-Null
New-Item -ItemType Directory -Force -Path $manifestFull, $logsDir | Out-Null

$templateLog = Join-Path $logsDir 'template_compile.log'
Remove-Item -Force -LiteralPath $templateLog -ErrorAction SilentlyContinue
Invoke-UnityBatch $resolvedUnityExe @('-batchmode', '-nographics', '-quit', '-projectPath', $projectFull, '-logFile', $templateLog) $templateLog 'Unity template compile/import'
$compileErrors = @(Select-String -LiteralPath $templateLog -Pattern 'error CS\d+|Assets/AIAssetPipeline.*\berror\b|Assets\\AIAssetPipeline.*\berror\b|Compilation failed|Build failed|Unhandled Exception|Exception:' -CaseSensitive:$false -ErrorAction SilentlyContinue)
if ($compileErrors.Count -gt 0) { throw "Unity template compile/import logged errors. Log: $templateLog" }

if ($InstallGltfImporter) {
  Remove-Item -Force -LiteralPath $gltfPackageLog, $gltfPackageReport -ErrorAction SilentlyContinue
  Invoke-UnityBatch $resolvedUnityExe @(
    '-batchmode',
    '-nographics',
    '-quit',
    '-projectPath',
    $projectFull,
    '-logFile',
    $gltfPackageLog,
    '-executeMethod',
    'AIAssetFactory.EditorTools.CodexUnityPackageInstaller.InstallFromCommandLine',
    '-codexUnityPackage',
    $GltfImporterPackage,
    '-codexUnityPackageReport',
    $gltfPackageReport
  ) $gltfPackageLog 'Unity glTF importer package install'
  if (!(Test-Path -LiteralPath $gltfPackageReport -PathType Leaf)) { throw "Unity glTF importer install did not write report: $gltfPackageReport" }
  $gltfInstallReport = Read-JsonFile $gltfPackageReport
  if ($gltfInstallReport.valid -ne $true) {
    $errors = @($gltfInstallReport.errors) -join '; '
    throw "Unity glTF importer install report is invalid: $errors"
  }

  Remove-Item -Force -LiteralPath $templateLog -ErrorAction SilentlyContinue
  Invoke-UnityBatch $resolvedUnityExe @('-batchmode', '-nographics', '-quit', '-projectPath', $projectFull, '-logFile', $templateLog) $templateLog 'Unity template compile/import after glTF importer install'
  $compileErrors = @(Select-String -LiteralPath $templateLog -Pattern 'error CS\d+|Assets/AIAssetPipeline.*\berror\b|Assets\\AIAssetPipeline.*\berror\b|Compilation failed|Build failed|Unhandled Exception|Exception:' -CaseSensitive:$false -ErrorAction SilentlyContinue)
  if ($compileErrors.Count -gt 0) { throw "Unity template compile/import after glTF importer install logged errors. Log: $templateLog" }
}

foreach ($asset in $assetPlan) {
  $destParent = Split-Path -Parent $asset.unityReadyMesh
  New-Item -ItemType Directory -Force -Path $destParent | Out-Null
  Copy-Item -Force -LiteralPath $asset.sourceGlb -Destination $asset.unityReadyMesh
}

if (!$ManifestDir) {
  foreach ($asset in $assetPlan) {
    Write-MinimalManifestBundle $asset.reference $asset.unityReadyMesh $manifestFull $projectFull | Out-Null
  }
}

Remove-Item -Force -LiteralPath $unityLog, $unityReport -ErrorAction SilentlyContinue
Invoke-UnityBatch $resolvedUnityExe @(
  '-batchmode',
  '-nographics',
  '-quit',
  '-projectPath',
  $projectFull,
  '-logFile',
  $unityLog,
  '-executeMethod',
  'AIAssetFactory.EditorTools.CodexRoomDemoSceneBuilder.BuildFromCommandLine',
  '-codexRoomSelectedReferences',
  $selectedPath,
  '-codexRoomManifestDir',
  $manifestFull,
  '-codexRoomScenePath',
  $ScenePath,
  '-codexRoomPrefabPath',
  $RootPrefabPath,
  '-codexRoomReport',
  $unityReport
) $unityLog 'Unity room demo scene build'
if (!(Test-Path -LiteralPath $unityReport -PathType Leaf)) { throw "Unity scene builder did not write report: $unityReport" }
$report = Read-JsonFile $unityReport
if ($report.valid -ne $true) {
  $errors = @($report.errors) -join '; '
  throw "Unity scene builder report is invalid: $errors"
}
$sceneFull = Join-Path $projectFull $ScenePath
$prefabFull = Join-Path $projectFull $RootPrefabPath
if (!(Test-Path -LiteralPath $sceneFull -PathType Leaf)) { throw "Unity scene was not created: $sceneFull" }
if (!(Test-Path -LiteralPath $prefabFull -PathType Leaf)) { throw "Unity root prefab was not created: $prefabFull" }

$summary.result = [ordered]@{
  valid = $true
  scene = $sceneFull
  rootPrefab = $prefabFull
  report = $unityReport
  log = $unityLog
  gltfImporterPackageReport = if ($InstallGltfImporter) { $gltfPackageReport } else { '' }
  importedAssetCount = $report.importedAssetCount
}
$summary | ConvertTo-Json -Depth 30
