param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$MarketplacePath = '',
  [string]$SmokeWorkDir = (Join-Path $env:TEMP ("codex-asset-factory-validate-" + [guid]::NewGuid().ToString('N'))),
  [string]$ProofDir = (Join-Path $PluginRoot 'proof')
)
$ErrorActionPreference = 'Stop'
if (!$MarketplacePath) {
  $agentsHome = if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { Join-Path $HOME '.agents' }
  $MarketplacePath = Join-Path $agentsHome 'plugins\marketplace.json'
}
$expectedTools = @(
  'open_asset_factory','plan_asset','plan_reference_image','register_reference_image','validate_reference_image','run_asset_pipeline','start_asset_pipeline_job','job_status','add_pipeline_instruction','cancel_pipeline_job','adjust_generated_asset','import_asset_to_unity','install_unity_template','plan_character_attachments','create_character_attachment_manifest','update_character_attachment_slot','list_character_attachment_slots','export_unity_socket_prefab_data','validate_character_attachment_manifest'
)
function ConvertTo-RedactedPath([AllowNull()][string]$PathValue) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) { return $PathValue }
  $value = $PathValue
  $map = @{
    '<PLUGIN_ROOT>' = $PluginRoot
    '<WORK_DIR>' = $SmokeWorkDir
    '<CODEX_HOME>' = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
    '<AGENTS_HOME>' = if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { Join-Path $HOME '.agents' }
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
function Invoke-McpJsonLines([string]$Server, [object[]]$Requests) {
  $payload = ($Requests | ForEach-Object { $_ | ConvertTo-Json -Depth 30 -Compress }) -join "`n"
  $raw = $payload | node $Server
  return @($raw | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}
$proof = [ordered]@{
  schema = 'codex.assetFactory.pluginValidation.v2'
  validatedAt = (Get-Date).ToUniversalTime().ToString('o')
  pluginRoot = '<PLUGIN_ROOT>'
  checks = [ordered]@{}
}
$server = Join-Path $PluginRoot 'mcp\server.mjs'
$pluginManifest = Join-Path $PluginRoot '.codex-plugin\plugin.json'
if (!(Test-Path $pluginManifest)) { $pluginManifest = Join-Path $PluginRoot 'plugin.json' }
if (!(Test-Path $pluginManifest)) { throw 'plugin manifest missing' }
$manifest = Get-Content -LiteralPath $pluginManifest -Raw | ConvertFrom-Json
$proof.version = $manifest.version
$changelog = Join-Path $PluginRoot 'CHANGELOG.md'
if (Test-Path $changelog) {
  $changelogText = Get-Content -LiteralPath $changelog -Raw
  if ($changelogText -notmatch "##\s+$([regex]::Escape($manifest.version))") { throw "CHANGELOG missing version $($manifest.version)" }
  $proof.checks.changelogVersion = 'ok'
}
if (!(Test-Path $server)) { throw 'mcp/server.mjs missing' }
if (Test-Path $MarketplacePath) {
  $market = Get-Content -LiteralPath $MarketplacePath -Raw | ConvertFrom-Json
  $entry = @($market.plugins | Where-Object { $_.name -eq 'codex-unity-comfyui-pipeline' })[0]
  if (!$entry) { throw 'marketplace entry missing: codex-unity-comfyui-pipeline' }
  if ($entry.source.path -ne './plugins/codex-unity-comfyui-pipeline') { throw "marketplace path mismatch: $($entry.source.path)" }
  $marketRoot = Split-Path -Parent $MarketplacePath
  $resolvedMarketPlugin = Resolve-Path (Join-Path $marketRoot $entry.source.path)
  $proof.marketplace = [ordered]@{ path = (ConvertTo-RedactedPath $MarketplacePath); pluginPath = $entry.source.path; resolvedPluginPath = (ConvertTo-RedactedPath $resolvedMarketPlugin.Path) }
}
node --check $server
$proof.checks.nodeCheck = 'ok'
$scriptsDir = Join-Path $PluginRoot 'scripts'
$pyFiles = @(Get-ChildItem -LiteralPath $scriptsDir -Filter '*.py')
foreach ($file in $pyFiles) {
  python -B -c "import ast,pathlib,sys; p=pathlib.Path(sys.argv[1]); ast.parse(p.read_text(encoding='utf-8'), filename=str(p))" $file.FullName
}
$proof.checks.pythonSyntax = @($pyFiles | ForEach-Object { $_.Name })
$profileValidationRaw = python -B (Join-Path $PluginRoot 'scripts\validate_asset_profiles.py') --profiles-dir (Join-Path $PluginRoot 'configs\asset-profiles')
$profileValidation = $profileValidationRaw | ConvertFrom-Json
if (-not $profileValidation.valid) { throw "asset profile validation failed: $($profileValidation.errors -join '; ')" }
$proof.assetProfiles = $profileValidation
$normalizationInvariantRaw = & (Join-Path $PluginRoot 'scripts\test_normalization_invariants.ps1') -PluginRoot $PluginRoot 2>&1
if ($LASTEXITCODE -ne 0) {
  $normalizationInvariantRaw | ForEach-Object { Write-Host $_ }
  throw 'normalization invariant gate failed'
}
$proof.checks.normalizationInvariants = 'ok'
$roomPlanningRaw = & (Join-Path $PluginRoot 'scripts\test_room_demo_planning.ps1') -PluginRoot $PluginRoot 2>&1
if ($LASTEXITCODE -ne 0) {
  $roomPlanningRaw | ForEach-Object { Write-Host $_ }
  throw 'room demo planning gate failed'
}
$proof.checks.roomDemoPlanning = 'ok'
$roomBatchRaw = & (Join-Path $PluginRoot 'scripts\test_room_demo_batch.ps1') -PluginRoot $PluginRoot 2>&1
if ($LASTEXITCODE -ne 0) {
  $roomBatchRaw | ForEach-Object { Write-Host $_ }
  throw 'room demo batch gate failed'
}
$proof.checks.roomDemoBatch = 'ok'
$roomProofRaw = & (Join-Path $PluginRoot 'scripts\test_room_demo_proof.ps1') -PluginRoot $PluginRoot 2>&1
if ($LASTEXITCODE -ne 0) {
  $roomProofRaw | ForEach-Object { Write-Host $_ }
  throw 'room demo proof gate failed'
}
$proof.checks.roomDemoProof = 'ok'
$runtimeValidationRaw = & (Join-Path $PluginRoot 'scripts\test_runtime_validation.ps1') -PluginRoot $PluginRoot 2>&1
if ($LASTEXITCODE -ne 0) {
  $runtimeValidationRaw | ForEach-Object { Write-Host $_ }
  throw 'runtime validation gate failed'
}
$proof.checks.runtimeValidation = 'ok'
$jobSafetyRaw = & (Join-Path $PluginRoot 'scripts\test_job_safety.ps1') -PluginRoot $PluginRoot 2>&1
if ($LASTEXITCODE -ne 0) {
  $jobSafetyRaw | ForEach-Object { Write-Host $_ }
  throw 'job safety gate failed'
}
$proof.checks.jobSafety = 'ok'
$responses = Invoke-McpJsonLines $server @(@{ jsonrpc='2.0'; id=1; method='tools/list'; params=@{} })
$toolNames = @($responses[0].result.tools | ForEach-Object { $_.name })
$missing = @($expectedTools | Where-Object { $toolNames -notcontains $_ })
if ($missing.Count) { throw "tools/list missing: $($missing -join ', ')" }
$proof.tools = $toolNames
$uiResponses = Invoke-McpJsonLines $server @(
  @{ jsonrpc='2.0'; id=2; method='resources/list'; params=@{} },
  @{ jsonrpc='2.0'; id=3; method='resources/read'; params=@{ uri='ui://codex-unity-comfyui-pipeline/asset-factory.html' } },
  @{ jsonrpc='2.0'; id=4; method='tools/call'; params=@{ name='open_asset_factory'; arguments=@{ defaultWorkDir=$SmokeWorkDir } } }
)
$uiText = $uiResponses[1].result.contents[0].text
foreach ($needle in @('Asset Factory','Image / Reference','Generation','Review / Adjust','Unity Import','Character Sockets')) {
  if ($uiText -notmatch [regex]::Escape($needle)) { throw "UI resource missing: $needle" }
}
if ($uiResponses[2].result.content[0].text -notmatch 'Asset Factory opened') { throw 'open_asset_factory did not return opened state' }
$proof.checks.uiResource = 'ok'
$proof.checks.openAssetFactory = 'ok'
New-Item -ItemType Directory -Force -Path $SmokeWorkDir | Out-Null
$smokeResponses = Invoke-McpJsonLines $server @(
  @{ jsonrpc='2.0'; id=10; method='tools/call'; params=@{ name='start_asset_pipeline_job'; arguments=@{ workDir=$SmokeWorkDir; assetName='validate_wall'; profile='wall'; dryRun=$true } } },
  @{ jsonrpc='2.0'; id=11; method='tools/call'; params=@{ name='job_status'; arguments=@{ workDir=$SmokeWorkDir; jobId='latest'; includeLogs=$true } } }
)
if ($smokeResponses[0].result.structuredContent.job.state -ne 'planned') { throw 'dry-run job was not persisted as planned' }
if ($smokeResponses[1].result.structuredContent.job.state -ne 'planned') { throw 'job_status did not recover planned persistent job' }
$proof.persistentJob = [ordered]@{ jobId = $smokeResponses[0].result.structuredContent.job.jobId; state = $smokeResponses[1].result.structuredContent.job.state; jobDir = $smokeResponses[1].result.structuredContent.job.jobDir }
$leakScanRaw = & (Join-Path $PSScriptRoot 'scan_private_leaks.ps1') -Root $PluginRoot -Json 2>&1
if ($LASTEXITCODE -ne 0) {
  $leakScan = $null
  try { $leakScan = ($leakScanRaw -join "`n") | ConvertFrom-Json } catch {}
  if ($leakScan) {
    Write-Host "Private leak scan FAILED: $($leakScan.findingCount) finding(s)"
    $leakScan.findings | Format-Table -AutoSize | Out-String | Write-Host
  } else {
    $leakScanRaw | ForEach-Object { Write-Host $_ }
  }
  throw 'private leak scan failed'
}
$proof.checks.privateLeakScan = 'ok'
New-Item -ItemType Directory -Force -Path $ProofDir | Out-Null
$proofPath = Join-Path $ProofDir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-plugin-validation-proof.json')
(ConvertTo-RedactedObject $proof) | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $proofPath -Encoding UTF8
Write-Host 'Plugin validation OK'
Write-Host "Version: $($manifest.version)"
Write-Host "Tools: $($toolNames.Count)"
Write-Host "Profiles: $($profileValidation.profileCount)"
Write-Host "Smoke job: $($proof.persistentJob.jobId)"
Write-Host "Proof: $proofPath"
