param(
  [ValidateSet('Debug','Release')] [string]$Configuration = 'Release',
  [string]$Runtime = 'win-x64',
  [string]$PluginRoot = '',
  [switch]$SkipBootstrapChecks
)
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$PluginRoot) {
  $PluginRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
}

$buildScript = Join-Path $scriptRoot 'build-installer.ps1'
& $buildScript -Configuration $Configuration -Runtime $Runtime
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$distRoot = Join-Path $scriptRoot "dist\AssetFactoryInstaller-$Runtime"
$exe = Join-Path $distRoot 'AssetFactoryInstaller.exe'
if (!(Test-Path -LiteralPath $exe)) {
  throw "Installer executable missing: $exe"
}

& $exe --validate-launcher --plugin-root $PluginRoot
if ($LASTEXITCODE -ne 0) {
  throw "Installer launcher validation failed for plugin root: $PluginRoot"
}

$distFiles = @(Get-ChildItem -LiteralPath $distRoot -Force -File)
if ($distFiles.Count -ne 1 -or $distFiles[0].Name -ne 'AssetFactoryInstaller.exe') {
  throw "Installer dist should contain only AssetFactoryInstaller.exe in this experimental single-file gate."
}

if (!$SkipBootstrapChecks) {
  $bootstrap = Join-Path $PluginRoot 'bootstrap\install.ps1'
  try {
    & $bootstrap --dry-run --target windows --profile auto --json | Out-Null
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $bootstrap --validate-only --target windows --profile auto --json | Out-Null
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } finally {
    Remove-Item -Force (Join-Path $PluginRoot 'proof\*.json') -ErrorAction SilentlyContinue
  }
}

Write-Host 'Windows installer gate OK'
Write-Host $exe
