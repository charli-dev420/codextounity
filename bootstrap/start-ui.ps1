param(
  [int]$Port = 8798,
  [string]$PluginRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'

$listener = [System.Net.HttpListener]::new()
$prefix = "http://127.0.0.1:$Port/"
$listener.Prefixes.Add($prefix)

function Write-HttpResponse($Context, [int]$StatusCode, [string]$Body, [string]$ContentType = 'application/json') {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
  $Context.Response.StatusCode = $StatusCode
  $Context.Response.ContentType = "$ContentType; charset=utf-8"
  $Context.Response.ContentLength64 = $bytes.Length
  $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
  $Context.Response.Close()
}

function Read-RequestJson($Request) {
  $reader = [System.IO.StreamReader]::new($Request.InputStream, [System.Text.Encoding]::UTF8)
  $raw = $reader.ReadToEnd()
  if ([string]::IsNullOrWhiteSpace($raw)) { return @{} }
  return ConvertTo-HashtableObject ($raw | ConvertFrom-Json)
}

function ConvertTo-HashtableObject([AllowNull()]$Value) {
  if ($null -eq $Value) { return $null }
  if ($Value -is [System.Collections.IDictionary]) {
    $out = @{}
    foreach ($key in $Value.Keys) { $out[$key] = ConvertTo-HashtableObject $Value[$key] }
    return $out
  }
  if ($Value -is [pscustomobject]) {
    $out = @{}
    foreach ($property in $Value.PSObject.Properties) { $out[$property.Name] = ConvertTo-HashtableObject $property.Value }
    return $out
  }
  if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
    return @($Value | ForEach-Object { ConvertTo-HashtableObject $_ })
  }
  return $Value
}

function Get-PowerShellExe {
  $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
  if ($pwsh) { return $pwsh.Source }
  $powershell = Get-Command powershell -ErrorAction Stop
  return $powershell.Source
}

function Invoke-Bootstrap([hashtable]$Payload) {
  $mode = if ($Payload.mode) { [string]$Payload.mode } else { 'dry-run' }
  $target = if ($Payload.target) { [string]$Payload.target } else { 'auto' }
  $profile = if ($Payload.profile) { [string]$Payload.profile } else { 'auto' }
  $fallback = if ($Payload.fallback) { [string]$Payload.fallback } else { 'auto' }
  $module = Join-Path $PluginRoot 'bootstrap\lib\SetupPipeline.psm1'
  Import-Module $module -Force
  $params = @{
    PluginRoot = $PluginRoot
    Target = $target
    Profile = $profile
    Fallback = $fallback
    DryRun = ($mode -eq 'dry-run')
    ValidateOnly = ($mode -eq 'validate-only')
    NonInteractive = ($Payload.nonInteractive -ne $false)
    InstallRoot = [string]$Payload['installRoot']
    CodexHome = [string]$Payload['codexHome']
    UnityProject = [string]$Payload['unityProject']
    Json = $true
  }
  $output = Invoke-AssetFactorySetup @params 2>&1
  $stdout = ($output | ForEach-Object { $_.ToString() }) -join "`n"
  $data = $null
  try { $data = ConvertTo-HashtableObject ($stdout | ConvertFrom-Json) } catch {}
  return [ordered]@{
    ok = $true
    mode = $mode
    exitCode = 0
    data = $data
    output = $stdout
  }
}
$listener.Start()
Write-Host "Asset Factory Installer UI: $prefix"
Write-Host 'Close this PowerShell window or press Ctrl+C to stop the installer UI.'
if (!$NoBrowser) {
  try { Start-Process $prefix | Out-Null } catch { Write-Host "Open manually: $prefix" }
}

try {
  while ($listener.IsListening) {
    $context = $listener.GetContext()
    $path = $context.Request.Url.AbsolutePath
    try {
      if ($context.Request.HttpMethod -eq 'GET' -and ($path -eq '/' -or $path -eq '/index.html')) {
        $html = Get-Content -LiteralPath (Join-Path $PluginRoot 'bootstrap\ui\installer.html') -Raw
        Write-HttpResponse $context 200 $html 'text/html'
        continue
      }
      if ($context.Request.HttpMethod -eq 'GET' -and $path -eq '/api/health') {
        Write-HttpResponse $context 200 (@{ ok = $true; name = 'Asset Factory Installer'; pluginRoot = '<PLUGIN_ROOT>' } | ConvertTo-Json)
        continue
      }
      if ($context.Request.HttpMethod -eq 'POST' -and $path -eq '/api/run') {
        $payload = Read-RequestJson $context.Request
        $result = Invoke-Bootstrap $payload
        Write-HttpResponse $context 200 ($result | ConvertTo-Json -Depth 80)
        continue
      }
      Write-HttpResponse $context 404 (@{ ok = $false; error = 'not found' } | ConvertTo-Json)
    } catch {
      Write-HttpResponse $context 500 (@{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json)
    }
  }
} finally {
  $listener.Stop()
  $listener.Close()
}

