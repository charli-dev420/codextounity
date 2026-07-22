param(
  [string]$PlanDir = "",
  [string]$SelectedReferences = "",
  [string]$InputDir = "",
  [string]$OutputDir = "",
  [string]$Server = "http://127.0.0.1:8188",
  [string]$ComfyOutputDir = "",
  [ValidateSet("simple", "mesh-with-texturing-hq", "mesh-with-texturing", "mesh-only-hq", "low-poly")]
  [string]$OfficialWorkflow = "simple",
  [int]$StartAt = 1,
  [int]$Limit = 0,
  [string]$AssetName = "",
  [switch]$Force,
  [switch]$RetryFailed,
  [switch]$DryRun,
  [int]$Timeout = 7200,
  [int]$TargetFaces = 9000,
  [int]$HighPolyFaces = 120000,
  [int]$TextureSize = 1024,
  [int]$SparseStructureSteps = 18,
  [int]$ShapeSteps = 18,
  [int]$TextureSteps = 18,
  [int]$MaxViews = 4,
  [string]$Sampler = "euler",
  [Nullable[int]]$Seed = 2146628683,
  [string]$Prefix = "room_demo_batch"
)
$ErrorActionPreference = 'Stop'

$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BatchScript = Join-Path $PSScriptRoot 'comfyui_trellis2_batch.py'
$WorkflowDir = Join-Path $PluginRoot 'workflows'

function Resolve-OptionalPath([string]$Value, [string]$BaseDir) {
  if ([string]::IsNullOrWhiteSpace($Value)) { return "" }
  if ([System.IO.Path]::IsPathRooted($Value)) { return $Value }
  return Join-Path $BaseDir $Value
}

function Read-JsonFile([string]$Path) {
  return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Write-JsonFile([string]$Path, [object]$Data) {
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $Data | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function ConvertTo-SafeName([string]$Value) {
  $clean = ($Value -replace '[^A-Za-z0-9._-]+', '_').Trim('._-')
  if (!$clean) { return 'asset' }
  if ($clean.Length -gt 120) { return $clean.Substring(0, 120) }
  return $clean
}

function Find-SelectedReferencesPath() {
  if ($SelectedReferences) {
    $path = Resolve-OptionalPath $SelectedReferences (Get-Location).Path
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "SelectedReferences not found: $path" }
    return (Resolve-Path -LiteralPath $path).Path
  }
  if (!$PlanDir) { throw 'PlanDir or SelectedReferences is required.' }
  $planPath = Resolve-OptionalPath $PlanDir (Get-Location).Path
  if (!(Test-Path -LiteralPath $planPath -PathType Container)) { throw "PlanDir not found: $planPath" }
  foreach ($candidate in @(
      (Join-Path $planPath 'selected_references.json'),
      (Join-Path $planPath 'images\selected_references.json')
    )) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
  }
  throw "selected_references.json not found under PlanDir: $planPath"
}

function Resolve-AssetInput($Asset, [string]$PlanRoot) {
  $assetName = [string]$Asset.assetName
  $candidateValues = @($Asset.inputImage, $Asset.referenceCopy, $Asset.source) | Where-Object { $_ }
  if ($InputDir) {
    $inputRoot = Resolve-OptionalPath $InputDir $PlanRoot
    foreach ($value in $candidateValues) {
      $leaf = Split-Path -Leaf ([string]$value)
      if ($leaf) {
        $candidate = Join-Path $inputRoot $leaf
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
      }
    }
    foreach ($ext in @('png','jpg','jpeg','webp')) {
      $candidate = Join-Path $inputRoot "$assetName.$ext"
      if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
  }
  foreach ($value in $candidateValues) {
    $candidate = Resolve-OptionalPath ([string]$value) $PlanRoot
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return (Resolve-Path -LiteralPath $candidate).Path }
  }
  return ""
}

function Find-ExistingGlb([string]$RawDir, [string]$AssetName) {
  if (!(Test-Path -LiteralPath $RawDir -PathType Container)) { return @() }
  $safe = ConvertTo-SafeName $AssetName
  return @(
    Get-ChildItem -LiteralPath $RawDir -Recurse -File -Filter '*.glb' -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Length -gt 0 -and (
          $_.BaseName.StartsWith($safe, [System.StringComparison]::OrdinalIgnoreCase) -or
          $_.DirectoryName.IndexOf($safe, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        )
      } |
      Sort-Object FullName
  )
}

function Read-Status([string]$StatusDir, [string]$AssetName) {
  $path = Join-Path $StatusDir ((ConvertTo-SafeName $AssetName) + '.json')
  if (!(Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
  return Read-JsonFile $path
}

function Write-Status([string]$StatusDir, [string]$AssetName, [object]$Status) {
  $path = Join-Path $StatusDir ((ConvertTo-SafeName $AssetName) + '.json')
  Write-JsonFile $path $Status
}

function Read-History([string]$RawDir, [string]$AssetName) {
  $path = Join-Path $RawDir ((ConvertTo-SafeName $AssetName) + '.history.json')
  if (!(Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
  return Read-JsonFile $path
}

function Get-ShortError([string]$StdoutLog, [string]$StderrLog, [int]$ExitCode) {
  $stderr = if (Test-Path -LiteralPath $StderrLog) { Get-Content -LiteralPath $StderrLog -ErrorAction SilentlyContinue } else { @() }
  $stdout = if (Test-Path -LiteralPath $StdoutLog) { Get-Content -LiteralPath $StdoutLog -ErrorAction SilentlyContinue } else { @() }
  $line = @($stderr + $stdout | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1)[0]
  if ($line) { return [string]$line }
  return "process exited with code $ExitCode"
}

$SelectedReferencesPath = Find-SelectedReferencesPath
$PlanRoot = if ($PlanDir) {
  (Resolve-Path -LiteralPath (Resolve-OptionalPath $PlanDir (Get-Location).Path)).Path
} else {
  Split-Path -Parent $SelectedReferencesPath
}
if (!$OutputDir) { $OutputDir = Join-Path $PlanRoot 'trellis2' }
$OutputDir = Resolve-OptionalPath $OutputDir $PlanRoot
$RawDir = Join-Path $OutputDir 'raw'
$LogsDir = Join-Path $OutputDir 'logs'
$StatusDir = Join-Path $OutputDir 'status'
$WorkDir = Join-Path $OutputDir 'work'
$SummaryPath = Join-Path $OutputDir 'summary_room_demo_batch.json'
New-Item -ItemType Directory -Force -Path $RawDir, $LogsDir, $StatusDir, $WorkDir | Out-Null

$referencesRaw = Get-Content -LiteralPath $SelectedReferencesPath -Raw | ConvertFrom-Json
$references = if ($referencesRaw -is [System.Array]) { @($referencesRaw) } else { @($referencesRaw) }
if ($AssetName) {
  $references = @($references | Where-Object { $_.assetName -eq $AssetName })
  if (!$references.Count) { throw "AssetName not found in selected references: $AssetName" }
}
if ($StartAt -lt 1) { throw 'StartAt must be >= 1.' }
$references = @($references | Select-Object -Skip ($StartAt - 1))
if ($Limit -gt 0) { $references = @($references | Select-Object -First $Limit) }
if (!$references.Count) { throw 'No selected references to process after filters.' }

$items = @()
foreach ($asset in $references) {
  $assetName = [string]$asset.assetName
  if ([string]::IsNullOrWhiteSpace($assetName)) { throw 'selected_references.json contains an asset without assetName.' }
  $safeAsset = ConvertTo-SafeName $assetName
  $startedAt = (Get-Date).ToUniversalTime()
  $stdoutLog = Join-Path $LogsDir "$safeAsset.stdout.log"
  $stderrLog = Join-Path $LogsDir "$safeAsset.stderr.log"
  $status = [ordered]@{
    assetName = $assetName
    startedAt = $startedAt.ToString('o')
    endedAt = $null
    durationSeconds = 0
    state = ''
    reason = ''
    exitCode = $null
    inputImage = ''
    outputGlbs = @()
    outputSource = @()
    promptId = ''
    stdoutLog = $stdoutLog
    stderrLog = $stderrLog
    shortError = ''
    dryRun = [bool]$DryRun
  }

  $inputImage = Resolve-AssetInput $asset $PlanRoot
  $status.inputImage = $inputImage
  if (!$inputImage) {
    $status.state = 'failed'
    $status.reason = 'input_missing'
    $status.shortError = "input image missing for $assetName"
    $status.endedAt = (Get-Date).ToUniversalTime().ToString('o')
    Write-Status $StatusDir $assetName $status
    $items += [pscustomobject]$status
    Write-Host "FAILED ${assetName}: input image missing"
    continue
  }

  $existingGlbs = @(Find-ExistingGlb $RawDir $assetName)
  $previousStatus = Read-Status $StatusDir $assetName
  if ($existingGlbs.Count -gt 0 -and !$Force) {
    $status.state = 'skipped'
    $status.reason = 'existing_glb'
    $status.outputGlbs = @($existingGlbs | ForEach-Object { $_.FullName })
    $status.endedAt = (Get-Date).ToUniversalTime().ToString('o')
    Write-Status $StatusDir $assetName $status
    $items += [pscustomobject]$status
    Write-Host "SKIP ${assetName}: existing GLB"
    continue
  }
  if ($previousStatus -and $previousStatus.state -eq 'failed' -and !$RetryFailed -and !$Force) {
    $status.state = 'skipped'
    $status.reason = 'previous_failed'
    $status.shortError = 'previous status failed; use -RetryFailed or -Force'
    $status.endedAt = (Get-Date).ToUniversalTime().ToString('o')
    Write-Status $StatusDir $assetName $status
    $items += [pscustomobject]$status
    Write-Host "SKIP ${assetName}: previous failure"
    continue
  }

  if ($DryRun) {
    $status.state = 'dry_run'
    $status.reason = 'planned_foreground_asset_run'
    $status.endedAt = (Get-Date).ToUniversalTime().ToString('o')
    Write-Status $StatusDir $assetName $status
    $items += [pscustomobject]$status
    Write-Host "DRY $assetName -> $RawDir"
    continue
  }

  $assetInputDir = Join-Path $WorkDir $safeAsset
  New-Item -ItemType Directory -Force -Path $assetInputDir | Out-Null
  $ext = [System.IO.Path]::GetExtension($inputImage)
  if (!$ext) { $ext = '.png' }
  $preparedInput = Join-Path $assetInputDir "$safeAsset$ext"
  Copy-Item -Force -LiteralPath $inputImage -Destination $preparedInput

  $argsList = @(
    '-B', $BatchScript,
    '--server', $Server,
    '--input-dir', $assetInputDir,
    '--output-dir', $RawDir,
    '--pattern', "*$ext",
    '--workflow-dir', $WorkflowDir,
    '--official-workflow', $OfficialWorkflow,
    '--prefix', $Prefix,
    '--file-format', 'glb',
    '--target-faces', ([string]$TargetFaces),
    '--high-poly-faces', ([string]$HighPolyFaces),
    '--texture-size', ([string]$TextureSize),
    '--sparse-structure-steps', ([string]$SparseStructureSteps),
    '--shape-steps', ([string]$ShapeSteps),
    '--texture-steps', ([string]$TextureSteps),
    '--max-views', ([string]$MaxViews),
    '--sampler', $Sampler,
    '--group-size', '1',
    '--group-index', '1',
    '--limit', '1',
    '--timeout', ([string]$Timeout)
  )
  if ($Seed -ne $null) { $argsList += @('--seed', ([string]$Seed.Value)) }
  if ($ComfyOutputDir) { $argsList += @('--comfy-output-dir', (Resolve-OptionalPath $ComfyOutputDir $PlanRoot)) }

  Write-Host "RUN $assetName"
  $stdout = & python @argsList 2> $stderrLog
  $exitCode = $LASTEXITCODE
  $stdout | Set-Content -LiteralPath $stdoutLog -Encoding UTF8

  $endedAt = (Get-Date).ToUniversalTime()
  $history = Read-History $RawDir $safeAsset
  $outputGlbs = @(Find-ExistingGlb $RawDir $safeAsset)
  $status.exitCode = $exitCode
  $status.endedAt = $endedAt.ToString('o')
  $status.durationSeconds = [math]::Round(($endedAt - $startedAt).TotalSeconds, 3)
  $status.outputGlbs = @($outputGlbs | ForEach-Object { $_.FullName })
  if ($history) {
    $status.promptId = [string]$history.prompt_id
    $status.outputSource = @($history.output_source)
  }
  if ($exitCode -eq 0 -and $outputGlbs.Count -gt 0) {
    if (@($status.outputSource) -contains 'comfy_output_copy' -and @($status.outputSource) -notcontains 'history_download') {
      $status.state = 'recovered'
      $status.reason = 'comfy_output_copy'
    } else {
      $status.state = 'generated'
      $status.reason = 'history_download'
    }
    Write-Host "$($status.state.ToUpperInvariant()) $assetName"
  } else {
    $status.state = 'failed'
    $status.reason = if ($outputGlbs.Count -eq 0) { 'missingOutput' } else { 'process_failed' }
    $status.shortError = Get-ShortError $stdoutLog $stderrLog $exitCode
    Write-Host "FAILED ${assetName}: $($status.shortError)"
  }
  Write-Status $StatusDir $assetName $status
  $items += [pscustomobject]$status
}

$counts = [ordered]@{
  generated = @($items | Where-Object { $_.state -eq 'generated' }).Count
  failed = @($items | Where-Object { $_.state -eq 'failed' }).Count
  skipped = @($items | Where-Object { $_.state -eq 'skipped' }).Count
  recoveredFromComfyOutput = @($items | Where-Object { $_.state -eq 'recovered' }).Count
  missingOutput = @($items | Where-Object { $_.reason -eq 'missingOutput' }).Count
  dryRun = @($items | Where-Object { $_.state -eq 'dry_run' }).Count
}
$summary = [ordered]@{
  schema = 'codex.roomDemoTrellis2Batch.v1'
  generatedAt = (Get-Date).ToUniversalTime().ToString('o')
  dryRun = [bool]$DryRun
  planDir = $PlanRoot
  selectedReferences = $SelectedReferencesPath
  outputDir = $OutputDir
  rawDir = $RawDir
  logsDir = $LogsDir
  statusDir = $StatusDir
  server = $Server
  counts = $counts
  items = $items
}
Write-JsonFile $SummaryPath $summary
Write-Host "Summary: $SummaryPath"
Write-Host "Generated=$($counts.generated) Recovered=$($counts.recoveredFromComfyOutput) Skipped=$($counts.skipped) Failed=$($counts.failed) MissingOutput=$($counts.missingOutput) DryRun=$($counts.dryRun)"

if ($counts.failed -gt 0) { exit 2 }
exit 0
