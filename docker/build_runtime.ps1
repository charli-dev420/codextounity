param(
  [string]$Image = 'codex-unity-comfyui-runtime:blackwell-cu128',
  [string]$BaseImage = 'nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04',
  [ValidateSet('all','apt-base','venv-base','torch-runtime','attention-runtime','comfyui-runtime','trellis2-runtime','models-runtime','final')]
  [string]$Stage = 'all',
  [int]$BuildJobs = 1,
  [double]$MinFreeRamGB = 6,
  [switch]$IncludeTrellis2Models,
  [switch]$NoTrellis2Models,
  [switch]$NoCache
)
$ErrorActionPreference = 'Stop'
if ($BuildJobs -lt 1) { throw 'BuildJobs must be >= 1' }

$env:MAX_JOBS = [string]$BuildJobs
$env:CMAKE_BUILD_PARALLEL_LEVEL = [string]$BuildJobs
$env:MAKEFLAGS = "-j$BuildJobs"
$env:NINJAFLAGS = "-j$BuildJobs"
$env:DOCKER_BUILDKIT = if ($env:DOCKER_BUILDKIT) { $env:DOCKER_BUILDKIT } else { '1' }

$pluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dockerfile = Join-Path $pluginRoot 'docker\runtime\Dockerfile.blackwell'
$includeModels = if ($NoTrellis2Models) { 'false' } elseif ($IncludeTrellis2Models) { 'true' } else { 'true' }
$orderedStages = @('apt-base','venv-base','torch-runtime','attention-runtime','comfyui-runtime','trellis2-runtime','models-runtime','final')
$stagesToBuild = if ($Stage -eq 'all') { $orderedStages } else { @($Stage) }

function Get-FreeRamSnapshot {
  $windowsFree = $null
  try {
    $os = Get-CimInstance Win32_OperatingSystem
    $windowsFree = [math]::Round(($os.FreePhysicalMemory * 1KB) / 1GB, 2)
  } catch {}
  $dockerWslFree = $null
  if (Get-Command wsl -ErrorAction SilentlyContinue) {
    try {
      $raw = & wsl -d docker-desktop -u root -- sh -lc "awk '/MemAvailable/ { printf \"%.2f\", `$2 / 1024 / 1024 }' /proc/meminfo" 2>$null
      if ($LASTEXITCODE -eq 0 -and $raw) { $dockerWslFree = [double]($raw -join '') }
    } catch {}
  }
  $effective = if ($dockerWslFree -ne $null) { $dockerWslFree } elseif ($windowsFree -ne $null) { $windowsFree } else { 999 }
  return [ordered]@{ effectiveGB = $effective; dockerWslGB = $dockerWslFree; windowsGB = $windowsFree }
}

function Invoke-StageBuild([string]$TargetStage) {
  $mem = Get-FreeRamSnapshot
  $free = [double]$mem.effectiveGB
  Write-Host "[preflight] stage=$TargetStage effectiveFreeRamGB=$free dockerWslFreeRamGB=$($mem.dockerWslGB) windowsFreeRamGB=$($mem.windowsGB) minFreeRamGB=$MinFreeRamGB buildJobs=$BuildJobs"
  if ($free -lt $MinFreeRamGB) {
    throw "Free RAM is too low for Docker stage '$TargetStage': ${free}GB available, ${MinFreeRamGB}GB required. Stop Docker/WSL or close memory-heavy apps, then rerun this stage."
  }
  $tag = if ($TargetStage -eq 'final') { $Image } else { "$Image-$TargetStage" }
  $args = @(
    'build',
    '--progress', 'plain',
    '--target', $TargetStage,
    '-f', $dockerfile,
    '-t', $tag,
    '--build-arg', "BASE_IMAGE=$BaseImage",
    '--build-arg', "BUILD_JOBS=$BuildJobs",
    '--build-arg', "INCLUDE_TRELLIS2_MODELS=$includeModels",
    $pluginRoot
  )
  if ($NoCache) { $args = @('build','--no-cache') + $args[1..($args.Count - 1)] }
  Write-Host "[build] image=$tag target=$TargetStage includeTrellis2Models=$includeModels"
  docker @args
}

foreach ($targetStage in $stagesToBuild) {
  Invoke-StageBuild $targetStage
}

