$ErrorActionPreference = 'Stop'

$Target = 'auto'
$Profile = 'auto'
$Fallback = 'auto'
$DryRun = $false
$ValidateOnly = $false
$NonInteractive = $false
$InstallRoot = ''
$CodexHome = ''
$UnityProject = ''
$Json = $false

function Write-InstallerHelp {
  @'
Asset Factory bootstrap installer

Usage:
  .\bootstrap\install.ps1 [options]

Options:
  --target auto|windows|linux|wsl|docker
  --profile auto|ada|blackwell|cpu
  --fallback auto|semi-auto|manual
  --install-root <path>
  --codex-home <path>
  --unity-project <path>
  --dry-run
  --validate-only
  --non-interactive
  --json
  --help, -h

Recommended first run:
  .\bootstrap\install.ps1 --dry-run --target windows --profile auto

Notes:
  This is a prototype installer. It installs only allowed/missing items,
  reports manual steps, and should be validated before opening Codex.
'@ | Write-Host
}

for ($i = 0; $i -lt $args.Count; $i++) {
  $arg = [string]$args[$i]
  switch -Regex ($arg) {
    '^(--help|-h|/\\?)$' { Write-InstallerHelp; exit 0 }
    '^(--target|-Target|-target)$' { $i++; $Target = [string]$args[$i]; continue }
    '^(--profile|-Profile|-profile)$' { $i++; $Profile = [string]$args[$i]; continue }
    '^(--fallback|-Fallback|-fallback)$' { $i++; $Fallback = [string]$args[$i]; continue }
    '^(--install-root|-InstallRoot|-install-root)$' { $i++; $InstallRoot = [string]$args[$i]; continue }
    '^(--codex-home|-CodexHome|-codex-home)$' { $i++; $CodexHome = [string]$args[$i]; continue }
    '^(--unity-project|-UnityProject|-unity-project)$' { $i++; $UnityProject = [string]$args[$i]; continue }
    '^(--dry-run|-DryRun|-dry-run)$' { $DryRun = $true; continue }
    '^(--validate-only|-ValidateOnly|-validate-only)$' { $ValidateOnly = $true; continue }
    '^(--non-interactive|-NonInteractive|-non-interactive)$' { $NonInteractive = $true; continue }
    '^(--json|-Json|-json)$' { $Json = $true; continue }
    default { throw "Unknown installer argument: $arg" }
  }
}

if (@('auto','windows','linux','wsl','docker') -notcontains $Target) { throw "Invalid target: $Target" }
if (@('auto','ada','blackwell','cpu') -notcontains $Profile) { throw "Invalid profile: $Profile" }
if (@('auto','semi-auto','manual') -notcontains $Fallback) { throw "Invalid fallback: $Fallback" }

$module = Join-Path $PSScriptRoot 'lib\SetupPipeline.psm1'
Import-Module $module -Force
Invoke-AssetFactorySetup -PluginRoot (Resolve-Path (Join-Path $PSScriptRoot '..')).Path `
  -Target $Target `
  -Profile $Profile `
  -Fallback $Fallback `
  -DryRun:$DryRun `
  -ValidateOnly:$ValidateOnly `
  -NonInteractive:$NonInteractive `
  -InstallRoot $InstallRoot `
  -CodexHome $CodexHome `
  -UnityProject $UnityProject `
  -Json:$Json
