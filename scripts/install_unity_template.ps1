param(
  [Parameter(Mandatory = $true)]
  [string]$UnityProjectRoot,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path $UnityProjectRoot
$AssetsRoot = Join-Path $ProjectRoot "Assets"
if (-not (Test-Path -LiteralPath $AssetsRoot -PathType Container)) {
  throw "Unity project root must contain an Assets folder: $ProjectRoot"
}

$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Source = Join-Path $PluginRoot "unity\Assets\AIAssetPipeline"
$Destination = Join-Path $AssetsRoot "AIAssetPipeline"

if ((Test-Path -LiteralPath $Destination) -and -not $Force) {
  throw "Destination already exists: $Destination. Re-run with -Force to merge/overwrite template files."
}

Copy-Item -LiteralPath $Source -Destination $AssetsRoot -Recurse -Force:$Force

Write-Host "Installed Unity editor template:"
Write-Host "  Source:      $Source"
Write-Host "  Destination: $Destination"
