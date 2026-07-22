param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [switch]$Json
)
$ErrorActionPreference = 'Stop'

$excludeDirs = @(
  '.git', '.codex', 'node_modules', '.venv', 'venv', 'env', '__pycache__',
  'bin', 'obj', 'dist', 'build', 'Library', 'Temp', 'Logs', 'UserSettings'
)
$textExtensions = @(
  '.md','.txt','.json','.jsonl','.js','.mjs','.cjs','.ts','.tsx','.html','.css',
  '.ps1','.psm1','.sh','.py','.cs','.yaml','.yml','.xml','.toml','.ini','.cfg'
)
$patterns = @(
  @{ name = 'windows_personal_path'; regex = '(?i)\b[A-Z]:\\Users\\(?!Public\\|Default\\|All Users\\|<)[^\\\s"''<>]+' },
  @{ name = 'windows_project_path'; regex = '(?i)\b[A-Z]:\\(?!Program Files\\|Program Files \(x86\)\\|Windows\\|Temp\\|tmp\\|<)[^"''`r`n<>]+' },
  @{ name = 'unix_home_path'; regex = '(?i)(^|[\s"''])/(home|Users)/(?!(?:runner|actions|Public|Shared|<)(?:/|$))[^"''\s<>]+' },
  @{ name = 'openai_key'; regex = '\bsk-[A-Za-z0-9_\-]{20,}\b' },
  @{ name = 'huggingface_token'; regex = '\bhf_[A-Za-z0-9]{20,}\b' },
  @{ name = 'github_token'; regex = '\b(ghp|github_pat)_[A-Za-z0-9_]{20,}\b' },
  @{ name = 'env_secret_assignment'; regex = '(?i)\b(OPENAI_API_KEY|HF_TOKEN|GITHUB_TOKEN|GITLAB_TOKEN|NPM_TOKEN|UNITY_SERIAL|UNITY_PASSWORD)\s*=\s*[^<\s][^\s]+' }
)

$localUser = @($env:USERNAME, (Split-Path $HOME -Leaf)) |
  Where-Object { $_ -and $_.Length -ge 3 -and $_ -notmatch '^(Public|Default|runner|actions)$' } |
  Select-Object -First 1
if ($localUser) {
  $patterns += @{ name = 'local_user_name'; regex = '(?i)\b' + [regex]::Escape($localUser) + '\b' }
}

function Test-Skip([string]$Path) {
  foreach ($part in ($Path -split '[\\/]')) {
    if ($excludeDirs -contains $part) { return $true }
  }
  return $false
}
function Test-SkipGeneratedArtifact([string]$Path) {
  foreach ($part in ($Path -split '[\\/]')) {
    if (@('.git', 'node_modules', '.venv', 'venv', 'env') -contains $part) { return $true }
  }
  return $false
}
function ConvertTo-RelativePath([string]$BasePath, [string]$ChildPath) {
  $baseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\','/') + [System.IO.Path]::DirectorySeparatorChar
  $childFull = [System.IO.Path]::GetFullPath($ChildPath)
  try {
    return [System.IO.Path]::GetRelativePath($baseFull, $childFull)
  } catch {
    $baseUri = [System.Uri]::new($baseFull)
    $childUri = [System.Uri]::new($childFull)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($childUri).ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
  }
}

$findings = New-Object System.Collections.Generic.List[object]
$files = Get-ChildItem -LiteralPath $Root -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object {
  -not (Test-Skip $_.FullName) -and ($textExtensions -contains $_.Extension.ToLowerInvariant())
}
foreach ($file in $files) {
  $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
  if ($null -eq $content) { continue }
  $lines = $content -split "`r?`n"
  for ($lineIndex = 0; $lineIndex -lt $lines.Count; $lineIndex++) {
    foreach ($pattern in $patterns) {
      $matches = [regex]::Matches($lines[$lineIndex], $pattern.regex)
      foreach ($match in $matches) {
        $value = $match.Value
        if ($value -match '<[A-Z_]+>') { continue }
        $relative = ConvertTo-RelativePath $Root $file.FullName
        $findings.Add([ordered]@{
          file = $relative.Replace('\','/')
          line = $lineIndex + 1
          type = $pattern.name
          sample = if ($value.Length -gt 120) { $value.Substring(0, 120) + '...' } else { $value }
        }) | Out-Null
      }
    }
  }
}

$findingArray = @($findings.ToArray())
$cacheFindings = @()
Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Where-Object { -not (Test-SkipGeneratedArtifact $_.FullName) } | ForEach-Object {
  $cacheFindings += [ordered]@{
    file = (ConvertTo-RelativePath $Root $_.FullName).Replace('\','/')
    line = 0
    type = 'generated_python_cache'
    sample = '__pycache__'
  }
}
Get-ChildItem -LiteralPath $Root -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @('.pyc', '.pyo') -and -not (Test-SkipGeneratedArtifact $_.FullName) } | ForEach-Object {
  $cacheFindings += [ordered]@{
    file = (ConvertTo-RelativePath $Root $_.FullName).Replace('\','/')
    line = 0
    type = 'generated_python_bytecode'
    sample = $_.Name
  }
}
$findingArray = @($findingArray + $cacheFindings)
$result = [ordered]@{
  schema = 'codex.assetFactory.privateLeakScan.v1'
  scannedAt = (Get-Date).ToUniversalTime().ToString('o')
  root = '<PLUGIN_ROOT>'
  ok = ($findingArray.Count -eq 0)
  findingCount = $findingArray.Count
  findings = $findingArray
}

if ($Json) {
  $result | ConvertTo-Json -Depth 20
} else {
  if ($result.ok) {
    Write-Host 'Private leak scan OK'
  } else {
    Write-Host "Private leak scan FAILED: $($findingArray.Count) finding(s)"
    $findingArray | Format-Table -AutoSize
  }
}

if (-not $result.ok) { exit 2 }
