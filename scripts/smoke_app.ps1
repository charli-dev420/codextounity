param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = (Join-Path $env:TEMP 'codex-asset-factory-smoke'),
  [string]$UnityProject = '',
  [string]$UnityExe = '',
  [switch]$SkipUnityBatch
)
$ErrorActionPreference = 'Stop'
if (!$UnityExe -and $env:UNITY_EXE) { $UnityExe = $env:UNITY_EXE }

function Invoke-McpJsonLines([string]$Server, [object[]]$Requests) {
  $payload = ($Requests | ForEach-Object { $_ | ConvertTo-Json -Depth 40 -Compress }) -join "`n"
  $raw = $payload | node $Server
  return @($raw | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}

function Add-Check([string]$Name, [object]$Value) {
  $script:checks[$Name] = $Value
}
function ConvertTo-RedactedPath([AllowNull()][string]$PathValue) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) { return $PathValue }
  $value = $PathValue
  $map = @{
    '<PLUGIN_ROOT>' = $PluginRoot
    '<WORK_DIR>' = $WorkDir
    '<UNITY_PROJECT>' = $UnityProject
  }
  foreach ($key in $map.Keys) {
    $raw = [string]$map[$key]
    if ($raw) {
      $value = $value.Replace($raw.TrimEnd('\','/'), $key)
      $value = $value.Replace($raw, $key)
    }
  }
  $value = $value -replace '\\','/'
  $value = $value -replace '(?i)[A-Z]:/Users/[^/]+','<USER_HOME>'
  return $value
}
function ConvertTo-RedactedObject([AllowNull()]$Value) {
  if ($null -eq $Value) { return $null }
  if ($Value -is [string]) { return ConvertTo-RedactedPath $Value }
  if ($Value -is [System.Collections.IDictionary]) {
    $out = [ordered]@{}
    foreach ($key in $Value.Keys) { $out[$key] = ConvertTo-RedactedObject $Value[$key] }
    return $out
  }
  if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
    return @($Value | ForEach-Object { ConvertTo-RedactedObject $_ })
  }
  if ($Value -is [pscustomobject]) {
    $out = [ordered]@{}
    foreach ($property in $Value.PSObject.Properties) { $out[$property.Name] = ConvertTo-RedactedObject $property.Value }
    return $out
  }
  return $Value
}

$server = Join-Path $PluginRoot 'mcp\server.mjs'
$proofDir = Join-Path $PluginRoot 'proof'
New-Item -ItemType Directory -Force -Path $WorkDir, $proofDir | Out-Null
$checks = [ordered]@{}
$artifacts = [ordered]@{}

& (Join-Path $PSScriptRoot 'validate_plugin.ps1') -PluginRoot $PluginRoot
Add-Check 'validate_plugin' 'ok'

$plans = Invoke-McpJsonLines $server @(
  @{jsonrpc='2.0';id=1;method='tools/call';params=@{name='plan_asset';arguments=@{workDir=$WorkDir;assetName='smoke_wall';profile='wall';description='clean modular wall'}}},
  @{jsonrpc='2.0';id=2;method='tools/call';params=@{name='plan_asset';arguments=@{workDir=$WorkDir;assetName='smoke_prop';profile='prop';description='single crate prop'}}},
  @{jsonrpc='2.0';id=3;method='tools/call';params=@{name='plan_asset';arguments=@{workDir=$WorkDir;assetName='smoke_weapon';profile='weapon';description='single sword weapon'}}},
  @{jsonrpc='2.0';id=4;method='tools/call';params=@{name='plan_asset';arguments=@{workDir=$WorkDir;assetName='smoke_character';profile='character';description='single humanoid character'}}}
)
if ($plans.Count -ne 4) { throw 'plan_asset smoke did not return 4 responses' }
Add-Check 'plan_asset_profiles' @($plans | ForEach-Object { $_.result.structuredContent.profile })

$referencePlan = Invoke-McpJsonLines $server @(
  @{jsonrpc='2.0';id=5;method='tools/call';params=@{name='plan_reference_image';arguments=@{assetName='smoke_wall';profile='wall';description='clean straight wall';style='stylized mobile';view='3/4 top-down';background='plain uniform'}}}
)
if ($referencePlan[0].result.structuredContent.prompt -notmatch '3/4') { throw 'reference plan missing expected camera guidance' }
Add-Check 'plan_reference_image' 'ok'

$box = Join-Path $WorkDir 'smoke_box.glb'
$adjusted = Join-Path $WorkDir 'smoke_box_adjusted.glb'
$normalizationReport = Join-Path $WorkDir 'normalization_report.json'
python (Join-Path $PluginRoot 'scripts\create_test_glb.py') --out $box | Out-Null
$adjust = Invoke-McpJsonLines $server @(
  @{jsonrpc='2.0';id=10;method='tools/call';params=@{name='adjust_generated_asset';arguments=@{inputMesh=$box;outputMesh=$adjusted;targetBounds='4,2,0.35';pivot='bottom-center';axisRemap='x,y,z';customPivot='0,0,0';tolerance=0.002;report=$normalizationReport}}}
)
if ($adjust[0].result.structuredContent.exitCode -ne 0) { throw 'adjust_generated_asset failed' }
$norm = Get-Content -Raw -LiteralPath $normalizationReport | ConvertFrom-Json
if (-not $norm.validation.valid) { throw 'normalization report invalid' }
Add-Check 'adjust_generated_asset' @{ extent = $norm.after.extent; valid = $norm.validation.valid }

$jobCreate = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=20;method='tools/call';params=@{name='start_asset_pipeline_job';arguments=@{workDir=$WorkDir;assetName='smoke_wall';profile='wall';dryRun=$true}}})
$jobInstruction = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=21;method='tools/call';params=@{name='add_pipeline_instruction';arguments=@{workDir=$WorkDir;jobId='latest';instruction='keep bounds straight and mobile friendly';author='manual'}}})
$jobStatus = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=22;method='tools/call';params=@{name='job_status';arguments=@{workDir=$WorkDir;jobId='latest';includeLogs=$true}}})
$jobCancel = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=23;method='tools/call';params=@{name='cancel_pipeline_job';arguments=@{workDir=$WorkDir;jobId='latest'}}})
Add-Check 'persistent_job' @{ created = $jobCreate[0].result.structuredContent.job.state; instruction = $jobInstruction[0].result.structuredContent.entry.instruction; status = $jobStatus[0].result.structuredContent.job.state; cancelled = $jobCancel[0].result.structuredContent.state }

$characterManifest = Join-Path $WorkDir 'character_attachments.json'
$socketExport = Join-Path $WorkDir 'unity_sockets.json'
$socketCreate = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=30;method='tools/call';params=@{name='create_character_attachment_manifest';arguments=@{characterId='smoke_hero';rigName='Humanoid';outPath=$characterManifest}}})
$socketUpdate = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=31;method='tools/call';params=@{name='update_character_attachment_slot';arguments=@{manifestPath=$characterManifest;slotId='belt_left_potion';bone='Hips';position='-0.2,-0.05,0.03';rotationEuler='0,0,12';scale='1,1,1';equipmentCategory='consumable';previewPose='locomotion_idle'}}})
$socketList = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=32;method='tools/call';params=@{name='list_character_attachment_slots';arguments=@{manifestPath=$characterManifest}}})
$socketExportResponse = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=33;method='tools/call';params=@{name='export_unity_socket_prefab_data';arguments=@{manifestPath=$characterManifest;outPath=$socketExport}}})
$socketValidate = Invoke-McpJsonLines $server @(@{jsonrpc='2.0';id=34;method='tools/call';params=@{name='validate_character_attachment_manifest';arguments=@{manifestPath=$characterManifest}}})
if ($socketValidate[0].result.structuredContent.exitCode -ne 0) { throw 'character socket validation failed' }
Add-Check 'character_sockets' 'ok'

if ($UnityProject -and (Test-Path (Join-Path $UnityProject 'Assets'))) {
  $import = Invoke-McpJsonLines $server @(
    @{jsonrpc='2.0';id=40;method='tools/call';params=@{name='import_asset_to_unity';arguments=@{meshPath=$adjusted;unityProject=$UnityProject;assetId='smoke_wall_4x2x035';unitySubdir='Assets/AIAssetPipeline/Generated/UnityReady';normalizationReport=$normalizationReport;characterAttachments=$characterManifest}}}
  )
  if ($import[0].result.structuredContent.exitCode -ne 0) { throw 'import_asset_to_unity failed' }
  Add-Check 'import_asset_to_unity' 'ok'
  if (!$SkipUnityBatch -and (Test-Path $UnityExe)) {
    & (Join-Path $PluginRoot 'scripts\install_unity_template.ps1') -UnityProjectRoot $UnityProject -Force | Out-Null
    $manifest = Join-Path $UnityProject 'Assets\AIAssetPipeline\Data\Results\smoke_box_adjusted.unity_manifest.json'
    $unityLog = Join-Path $WorkDir 'unity_import_manifest.log'
    Remove-Item -Force -LiteralPath $unityLog -ErrorAction SilentlyContinue
    & $UnityExe -batchmode -nographics -quit -projectPath $UnityProject -logFile $unityLog -executeMethod AIAssetFactory.EditorTools.AIAssetResultImporter.ImportManifestFromCommandLine -aiAssetManifest $manifest -aiAssetAddToScene
    for ($i = 0; $i -lt 60 -and !(Test-Path -LiteralPath $unityLog); $i++) {
      Start-Sleep -Milliseconds 500
    }
    if (!(Test-Path -LiteralPath $unityLog)) { throw "Unity batch import log was not written: $unityLog" }
    $errors = Select-String -LiteralPath $unityLog -Pattern 'error CS|Assets\\AIAssetPipeline.*error|AIAssetFactory.*error|Compilation failed|Build failed|Exception' -CaseSensitive:$false
    if (($errors | Measure-Object).Count -gt 0) { throw "Unity batch import logged errors: $unityLog" }
    Add-Check 'unity_batch_import' 'ok'
    $artifacts.unityBatchLog = $unityLog
  }
}

$artifacts.workDir = $WorkDir
$artifacts.testGlb = $box
$artifacts.adjustedGlb = $adjusted
$artifacts.normalizationReport = $normalizationReport
$artifacts.characterManifest = $characterManifest
$artifacts.socketExport = $socketExport
$proof = [ordered]@{
  schema = 'codex.assetFactory.smokeProof.v1'
  createdAt = (Get-Date).ToUniversalTime().ToString('o')
  pluginRoot = '<PLUGIN_ROOT>'
  unityProject = if ($UnityProject) { '<UNITY_PROJECT>' } else { '' }
  checks = $checks
  artifacts = $artifacts
}
$proofPath = Join-Path $proofDir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-smoke-app-proof.json')
(ConvertTo-RedactedObject $proof) | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $proofPath -Encoding UTF8
Write-Host "Smoke app OK: $proofPath"
