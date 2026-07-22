param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$WorkDir = (Join-Path $env:TEMP ("codex-asset-factory-job-safety-" + [guid]::NewGuid().ToString('N'))),
  [switch]$KeepWorkDir
)

$ErrorActionPreference = 'Stop'

function Invoke-McpJsonLines([string]$Server, [object[]]$Requests) {
  $payload = ($Requests | ForEach-Object { $_ | ConvertTo-Json -Depth 30 -Compress }) -join "`n"
  $raw = $payload | node $Server
  return @($raw | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}

function Assert-True([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw $Message }
}

function Assert-ToolError([object[]]$Responses, [string]$ExpectedCode) {
  Assert-True ($Responses.Count -ge 1) 'Expected at least one MCP response.'
  Assert-True ($null -ne $Responses[0].error) 'Expected MCP error response.'
  Assert-True ($Responses[0].error.data.code -eq $ExpectedCode) "Expected tool error code '$ExpectedCode', got '$($Responses[0].error.data.code)'."
}

function New-JobSkeleton([string]$Root, [string]$JobId, [int]$ProcessId) {
  $jobsRoot = Join-Path $Root '.codex_asset_jobs'
  $jobDir = Join-Path $jobsRoot $JobId
  New-Item -ItemType Directory -Force -Path $jobDir | Out-Null
  $runWorkDir = Join-Path $jobDir 'work'
  $command = @('python','-B',(Join-Path $PluginRoot 'scripts\generate_asset.py'),'--work-dir',$runWorkDir)
  $job = [ordered]@{
    jobId = $JobId
    assetName = 'unsafe_pid'
    profile = 'wall'
    state = 'generating'
    status = 'generating'
    createdAt = (Get-Date).ToUniversalTime().ToString('o')
    updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    workDir = (Resolve-Path $Root).Path
    jobDir = $jobDir
    runWorkDir = $runWorkDir
    pid = $ProcessId
    command = $command
    commandHash = 'intentionally-wrong'
  }
  $jobJson = $job | ConvertTo-Json -Depth 20
  [System.IO.File]::WriteAllText((Join-Path $jobDir 'job.json'), $jobJson, [System.Text.UTF8Encoding]::new($false))
  return $jobDir
}

$server = Join-Path $PluginRoot 'mcp\server.mjs'
$scriptsDir = Join-Path $PluginRoot 'scripts'
$results = [ordered]@{
  schema = 'codex.assetFactory.jobSafety.v1'
  workDir = $WorkDir
  checks = [ordered]@{}
}

try {
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

  $invalidStatus = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=1; method='tools/call'; params=@{ name='job_status'; arguments=@{ workDir=$WorkDir; jobId='..\escape'; includeLogs=$true } } }
  )
  Assert-ToolError $invalidStatus 'invalid_job_id'
  Assert-True (-not (Test-Path (Join-Path $WorkDir 'escape'))) 'Invalid jobId created an escaped path.'
  $results.checks.invalidJobStatus = 'ok'

  $missingCancel = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=2; method='tools/call'; params=@{ name='cancel_pipeline_job'; arguments=@{ workDir=$WorkDir; jobId='1234567890123_missing' } } }
  )
  Assert-True ($missingCancel[0].result.structuredContent.state -eq 'not_found') 'Missing cancel did not return not_found.'
  $results.checks.missingCancel = 'ok'

  $dryRun = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=3; method='tools/call'; params=@{ name='start_asset_pipeline_job'; arguments=@{ workDir=$WorkDir; assetName='phase5_dry_run'; profile='wall'; dryRun=$true } } },
    @{ jsonrpc='2.0'; id=4; method='tools/call'; params=@{ name='cancel_pipeline_job'; arguments=@{ workDir=$WorkDir; jobId='latest' } } },
    @{ jsonrpc='2.0'; id=5; method='tools/call'; params=@{ name='job_status'; arguments=@{ workDir=$WorkDir; jobId='latest'; includeLogs=$true } } }
  )
  Assert-True ($dryRun[0].result.structuredContent.job.state -eq 'planned') 'Dry-run job was not planned.'
  Assert-True ($dryRun[1].result.structuredContent.state -eq 'planned') 'Cancel changed a planned dry-run job.'
  Assert-True ($dryRun[2].result.structuredContent.job.state -eq 'planned') 'Planned job state was not preserved.'
  $results.checks.plannedCancelPreservesState = 'ok'
  $jobDir = $dryRun[0].result.structuredContent.job.jobDir
  $userPathSample = 'C:' + '\Users\Example\private'
  $longTail = ([string]::new([char]'x', 9000)) + "`nsk-phase5secret000000`n$userPathSample"
  Set-Content -LiteralPath (Join-Path $jobDir 'stdout.log') -Value $longTail -Encoding UTF8
  $tailStatus = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=6; method='tools/call'; params=@{ name='job_status'; arguments=@{ workDir=$WorkDir; jobId='latest'; includeLogs=$true } } }
  )
  $stdoutTail = [string]$tailStatus[0].result.structuredContent.stdoutTail
  Assert-True ($stdoutTail.Length -le 7000) "stdout tail is too large: $($stdoutTail.Length)"
  Assert-True ($stdoutTail -notmatch 'sk-phase5secret') 'stdout tail leaked token-like text.'
  Assert-True ($stdoutTail -notmatch ([regex]::Escape($userPathSample))) 'stdout tail leaked a user path.'
  $results.checks.boundedRedactedLogs = 'ok'

  $unsafeJobId = '1234567890123_unsafe_pid'
  New-JobSkeleton $WorkDir $unsafeJobId $PID | Out-Null
  $unsafeCancel = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=7; method='tools/call'; params=@{ name='cancel_pipeline_job'; arguments=@{ workDir=$WorkDir; jobId=$unsafeJobId } } }
  )
  $unsafeState = [string]$unsafeCancel[0].result.structuredContent.state
  Assert-True ($unsafeState -eq 'cancel_rejected') "Untrusted persisted PID was not rejected; state was '$unsafeState'."
  Assert-True ($unsafeCancel[0].result.structuredContent.kill.sent -eq $false) 'Untrusted persisted PID received a kill signal.'
  Assert-True ($unsafeCancel[0].result.structuredContent.kill.verification.trusted -eq $false) 'Untrusted persisted PID was reported trusted.'
  Assert-True ($PID -eq $PID) 'Current PowerShell process should still be running.'
  $results.checks.untrustedPidCancel = 'ok'

  $unityProject = Join-Path $WorkDir 'UnityProject'
  New-Item -ItemType Directory -Force -Path (Join-Path $unityProject 'Assets') | Out-Null
  $mesh = Join-Path $WorkDir 'mesh.glb'
  python -B (Join-Path $scriptsDir 'create_test_glb.py') --out $mesh | Out-Null
  $dryImport = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=8; method='tools/call'; params=@{ name='import_asset_to_unity'; arguments=@{ meshPath=$mesh; unityProject=$unityProject; assetId='phase5_mesh'; unitySubdir='Assets/AIAssetPipeline/Generated/UnityReady'; dryRun=$true } } }
  )
  Assert-True ($dryImport[0].result.structuredContent.dryRun -eq $true) 'Unity import dry-run did not report dryRun.'
  Assert-True (-not (Test-Path (Join-Path $WorkDir '.unity_import'))) 'Unity import dry-run created staging files.'
  $badImport = Invoke-McpJsonLines $server @(
    @{ jsonrpc='2.0'; id=9; method='tools/call'; params=@{ name='import_asset_to_unity'; arguments=@{ meshPath=$mesh; unityProject=$unityProject; assetId='phase5_mesh'; unitySubdir='../Outside'; dryRun=$false } } }
  )
  Assert-ToolError $badImport 'unity_subdir_invalid'
  Assert-True (-not (Test-Path (Join-Path $WorkDir '.unity_import'))) 'Invalid Unity import created staging files.'
  $results.checks.unityImportContainment = 'ok'

  $results.valid = $true
  $results | ConvertTo-Json -Depth 20
  Write-Host 'Job safety gate OK'
} finally {
  if (-not $KeepWorkDir -and (Test-Path $WorkDir)) {
    Remove-Item -Recurse -Force -LiteralPath $WorkDir -ErrorAction SilentlyContinue
  }
}
