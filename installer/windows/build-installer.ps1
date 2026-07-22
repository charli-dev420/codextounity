param(
  [ValidateSet('Debug','Release')] [string]$Configuration = 'Release',
  [string]$Runtime = 'win-x64',
  [switch]$FrameworkDependent
)
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Join-Path $scriptRoot 'AssetFactoryInstaller\AssetFactoryInstaller.csproj'
$output = Join-Path $scriptRoot "dist\AssetFactoryInstaller-$Runtime"

if (!(Get-Command dotnet -ErrorAction SilentlyContinue)) {
  throw 'dotnet SDK is required to build the Windows installer executable.'
}

$publishArgs = @(
  'publish',
  $project,
  '--configuration', $Configuration,
  '--runtime', $Runtime,
  '--output', $output,
  '-p:PublishSingleFile=true',
  '-p:IncludeNativeLibrariesForSelfExtract=true',
  '-p:EnableCompressionInSingleFile=true',
  '-p:DebugType=none',
  '-p:DebugSymbols=false'
)

if ($FrameworkDependent) {
  $publishArgs += '--self-contained'
  $publishArgs += 'false'
} else {
  $publishArgs += '--self-contained'
  $publishArgs += 'true'
}

& dotnet @publishArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Remove-Item -Force (Join-Path $output '*.pdb') -ErrorAction SilentlyContinue

$exe = Join-Path $output 'AssetFactoryInstaller.exe'
if (!(Test-Path -LiteralPath $exe)) {
  throw "Installer executable was not created: $exe"
}

Write-Host "Installer executable created:"
Write-Host $exe
