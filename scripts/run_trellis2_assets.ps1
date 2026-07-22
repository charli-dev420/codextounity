param(
  [string]$Profile = "",
  [string]$Server = "http://127.0.0.1:8188",
  [string]$InputDir = "",
  [string]$OutputDir = "",
  [string]$Workflow = "",
  [string]$WorkflowDir = "",
  [ValidateSet("simple", "mesh-with-texturing-hq", "mesh-with-texturing", "mesh-only-hq", "low-poly")]
  [string]$OfficialWorkflow = "simple",
  [string]$Prefix = "trellis2_assets",
  [ValidateSet("glb", "obj", "ply", "stl", "3mf", "dae")]
  [string]$FileFormat = "glb",
  [ValidateSet("", "microsoft/TRELLIS.2-4B", "visualbruno/TRELLIS.2-4B-FP8", "TencentARC/Pixal3D-T")]
  [string]$ModelName = "",
  [ValidateSet("", "flash_attn", "xformers", "sdpa", "flash_attn_3", "flash_attn_4")]
  [string]$AttentionBackend = "",
  [int]$TargetFaces = 18000,
  [int]$HighPolyFaces = 120000,
  [int]$TextureSize = 1024,
  [int]$SparseStructureSteps = 18,
  [int]$ShapeSteps = 18,
  [int]$TextureSteps = 18,
  [int]$MaxViews = 4,
  [string]$Sampler = "euler",
  [int]$GroupSize = 10,
  [int]$GroupIndex = 1,
  [Nullable[int]]$Seed = 2146628683,
  [int]$Limit = 0,
  [string]$ComfyOutputDir = "",
  [switch]$UseReconViaGen,
  [switch]$NoUseReconViaGen,
  [switch]$IncrementSeed,
  [switch]$Recursive,
  [switch]$DryRun,
  [switch]$RefreshWorkflow
)

$ErrorActionPreference = "Stop"

$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Script = Join-Path $PSScriptRoot "comfyui_trellis2_batch.py"
$BoundParameters = @{} + $PSBoundParameters

function Test-JsonProperty($Object, [string]$Name) {
  return $null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name -and $null -ne $Object.$Name
}

function Resolve-ConfigPath([string]$Value) {
  if (-not $Value) {
    return ""
  }
  if ([System.IO.Path]::IsPathRooted($Value)) {
    return $Value
  }
  return Join-Path (Get-Location) $Value
}

if ($Profile) {
  $ProfilePath = Resolve-ConfigPath $Profile
  if (-not (Test-Path -Path $ProfilePath -PathType Leaf)) {
    throw "Profile JSON not found: $ProfilePath"
  }

  $ProfileData = Get-Content -Raw -Path $ProfilePath | ConvertFrom-Json
  $ComfyProfile = $ProfileData.comfyui

  if (-not $BoundParameters.ContainsKey("InputDir") -and (Test-JsonProperty $ProfileData "inputDir")) {
    $InputDir = Resolve-ConfigPath $ProfileData.inputDir
  }
  if (-not $BoundParameters.ContainsKey("OutputDir") -and (Test-JsonProperty $ProfileData "outputDir")) {
    $OutputDir = Resolve-ConfigPath $ProfileData.outputDir
  }
  if (-not $BoundParameters.ContainsKey("Server") -and (Test-JsonProperty $ComfyProfile "server")) {
    $Server = [string]$ComfyProfile.server
  }
  if (-not $BoundParameters.ContainsKey("OfficialWorkflow") -and (Test-JsonProperty $ComfyProfile "officialWorkflow")) {
    $OfficialWorkflow = [string]$ComfyProfile.officialWorkflow
  }
  if (-not $BoundParameters.ContainsKey("Prefix") -and (Test-JsonProperty $ComfyProfile "prefix")) {
    $Prefix = [string]$ComfyProfile.prefix
  }
  if (-not $BoundParameters.ContainsKey("FileFormat") -and (Test-JsonProperty $ComfyProfile "fileFormat")) {
    $FileFormat = [string]$ComfyProfile.fileFormat
  }
  if (-not $BoundParameters.ContainsKey("TargetFaces") -and (Test-JsonProperty $ComfyProfile "targetFaces")) {
    $TargetFaces = [int]$ComfyProfile.targetFaces
  }
  if (-not $BoundParameters.ContainsKey("HighPolyFaces") -and (Test-JsonProperty $ComfyProfile "highPolyFaces")) {
    $HighPolyFaces = [int]$ComfyProfile.highPolyFaces
  }
  if (-not $BoundParameters.ContainsKey("TextureSize") -and (Test-JsonProperty $ComfyProfile "textureSize")) {
    $TextureSize = [int]$ComfyProfile.textureSize
  }
  if (-not $BoundParameters.ContainsKey("SparseStructureSteps") -and (Test-JsonProperty $ComfyProfile "sparseStructureSteps")) {
    $SparseStructureSteps = [int]$ComfyProfile.sparseStructureSteps
  }
  if (-not $BoundParameters.ContainsKey("ShapeSteps") -and (Test-JsonProperty $ComfyProfile "shapeSteps")) {
    $ShapeSteps = [int]$ComfyProfile.shapeSteps
  }
  if (-not $BoundParameters.ContainsKey("TextureSteps") -and (Test-JsonProperty $ComfyProfile "textureSteps")) {
    $TextureSteps = [int]$ComfyProfile.textureSteps
  }
  if (-not $BoundParameters.ContainsKey("MaxViews") -and (Test-JsonProperty $ComfyProfile "maxViews")) {
    $MaxViews = [int]$ComfyProfile.maxViews
  }
  if (-not $BoundParameters.ContainsKey("Sampler") -and (Test-JsonProperty $ComfyProfile "sampler")) {
    $Sampler = [string]$ComfyProfile.sampler
  }
  if (-not $BoundParameters.ContainsKey("Seed") -and (Test-JsonProperty $ComfyProfile "seed")) {
    $Seed = [int]$ComfyProfile.seed
  }
  if (-not $BoundParameters.ContainsKey("GroupSize") -and (Test-JsonProperty $ComfyProfile "groupSize")) {
    $GroupSize = [int]$ComfyProfile.groupSize
  }
}

if (-not $WorkflowDir) {
  $WorkflowDir = Join-Path $PluginRoot "workflows"
}

if (-not $InputDir) {
  throw "InputDir is required. Pass -InputDir or use -Profile with inputDir."
}

if (-not $OutputDir) {
  throw "OutputDir is required. Pass -OutputDir or use -Profile with outputDir."
}

$ArgsList = @(
  $Script,
  "--server", $Server,
  "--input-dir", $InputDir,
  "--output-dir", $OutputDir,
  "--workflow-dir", $WorkflowDir,
  "--official-workflow", $OfficialWorkflow,
  "--prefix", $Prefix,
  "--file-format", $FileFormat,
  "--target-faces", $TargetFaces,
  "--high-poly-faces", $HighPolyFaces,
  "--texture-size", $TextureSize,
  "--sparse-structure-steps", $SparseStructureSteps,
  "--shape-steps", $ShapeSteps,
  "--texture-steps", $TextureSteps,
  "--max-views", $MaxViews,
  "--sampler", $Sampler,
  "--group-size", $GroupSize,
  "--group-index", $GroupIndex
)

if ($Workflow) {
  $ArgsList += @("--workflow", $Workflow)
}

if ($Seed -ne $null) {
  $ArgsList += @("--seed", $Seed.Value)
}

if ($ModelName) {
  $ArgsList += @("--model-name", $ModelName)
}

if ($AttentionBackend) {
  $ArgsList += @("--attention-backend", $AttentionBackend)
}

if ($Limit -gt 0) {
  $ArgsList += @("--limit", $Limit)
}

if ($ComfyOutputDir) {
  $ArgsList += @("--comfy-output-dir", $ComfyOutputDir)
}

if ($UseReconViaGen) {
  $ArgsList += "--use-reconviagen"
}

if ($NoUseReconViaGen) {
  $ArgsList += "--no-use-reconviagen"
}

if ($IncrementSeed) {
  $ArgsList += "--increment-seed"
}

if ($Recursive) {
  $ArgsList += "--recursive"
}

if ($DryRun) {
  $ArgsList += "--dry-run"
}

if ($RefreshWorkflow) {
  $ArgsList += "--refresh-workflow"
}

python -B @ArgsList
exit $LASTEXITCODE
