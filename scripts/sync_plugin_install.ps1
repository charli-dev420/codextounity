param(
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$AgentsPluginRoot = '',
  [string]$CodexLocalRoot = '',
  [string]$CodexCacheRoot = '',
  [string]$LegacyCodexCacheRoot = '',
  [switch]$DryRun,
  [switch]$Help
)
$ErrorActionPreference = 'Stop'
if ($Help) {
  @'
Sync the local plugin into Codex/agents plugin folders.

This is mainly a maintainer/local-development helper. It can write to:
  <AGENTS_HOME>/plugins/plugins/codex-unity-comfyui-pipeline
  <CODEX_HOME>/plugins/local/codex-unity-comfyui-pipeline
  <CODEX_HOME>/plugins/cache/local-codex-unity-comfyui-pipeline/...

Usage:
  .\scripts\sync_plugin_install.ps1 [-DryRun]

Options:
  -DryRun   Print target paths without copying or writing cachebuster files.
  -Help     Show this help.
'@ | Write-Host
  exit 0
}
$AgentsHome = if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { Join-Path $HOME '.agents' }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
if (!$AgentsPluginRoot) { $AgentsPluginRoot = Join-Path $AgentsHome 'plugins\plugins\codex-unity-comfyui-pipeline' }
if (!$CodexLocalRoot) { $CodexLocalRoot = Join-Path $CodexHome 'plugins\local\codex-unity-comfyui-pipeline' }
if (!$CodexCacheRoot) { $CodexCacheRoot = Join-Path $CodexHome 'plugins\cache\local-codex-unity-comfyui-pipeline\codex-unity-comfyui-pipeline\0.2.0' }
if (!$LegacyCodexCacheRoot) { $LegacyCodexCacheRoot = Join-Path $CodexHome 'plugins\cache\local-codex-unity-comfyui-pipeline\codex-unity-comfyui-pipeline\0.1.0' }
function Remove-GeneratedPythonCache([string]$Root) {
  if (!(Test-Path $Root)) { return }
  Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Recurse -Force -LiteralPath $_.FullName -ErrorAction SilentlyContinue
  }
  Get-ChildItem -LiteralPath $Root -Recurse -Force -File -Filter '*.pyc' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Force -LiteralPath $_.FullName -ErrorAction SilentlyContinue
  }
}
function Copy-PluginTree([string]$Source, [string]$Target) {
  if (!(Test-Path $Source)) { throw "Source plugin missing: $Source" }
  $sourceResolved = (Resolve-Path $Source).Path.TrimEnd('\')
  $targetResolved = if (Test-Path $Target) { (Resolve-Path $Target).Path.TrimEnd('\') } else { [System.IO.Path]::GetFullPath($Target).TrimEnd('\') }
  if ([string]::Equals($sourceResolved, $targetResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "Skip self-sync: $Target"
    return
  }
  if ($script:DryRun) {
    Write-Host "Dry-run copy: $Source -> $Target"
    return
  }
  New-Item -ItemType Directory -Force -Path $Target | Out-Null
  Get-ChildItem -LiteralPath $Source -Force | Where-Object { $_.Name -ne '__pycache__' } | ForEach-Object {
    Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination $Target
  }
  Remove-GeneratedPythonCache $Target
  Write-Host "Updated: $Target"
}
$manifest = Join-Path $PluginRoot '.codex-plugin\plugin.json'
if (!(Test-Path $manifest)) { $manifest = Join-Path $PluginRoot 'plugin.json' }
if (!(Test-Path $manifest)) { throw "plugin manifest missing in $PluginRoot" }
Remove-GeneratedPythonCache $PluginRoot
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
if (!$DryRun) {
  Set-Content -LiteralPath (Join-Path $PluginRoot '.codex-cachebuster') -Value $stamp -Encoding UTF8
} else {
  Write-Host "Dry-run cachebuster: $stamp"
}
Copy-PluginTree $PluginRoot $AgentsPluginRoot
Copy-PluginTree $PluginRoot $CodexLocalRoot
Copy-PluginTree $PluginRoot $CodexCacheRoot
if ($LegacyCodexCacheRoot) { Copy-PluginTree $PluginRoot $LegacyCodexCacheRoot }
if ($DryRun) {
  Write-Host "Dry-run complete; no files were copied and no cachebuster was written."
} else {
  Write-Host "Synced plugin to agents/local/cache with cachebuster $stamp"
}
