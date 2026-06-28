$ErrorActionPreference = 'Stop'

function Get-CommandStatus([string]$Name, [string[]]$Args = @('--version')) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if (!$command) { return [ordered]@{ name = $Name; present = $false; path = $null; version = $null } }
  $version = $null
  try {
    $output = & $command.Source @Args 2>$null | Select-Object -First 1
    $version = ($output -join ' ').Trim()
  } catch { $version = 'present' }
  return [ordered]@{ name = $Name; present = $true; path = '<SYSTEM_PATH>'; version = $version }
}

function ConvertTo-RedactedPath([AllowNull()][string]$PathValue, [hashtable]$Map) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) { return $PathValue }
  $value = $PathValue
  foreach ($key in $Map.Keys) {
    $raw = [string]$Map[$key]
    if ([string]::IsNullOrWhiteSpace($raw)) { continue }
    $value = $value.Replace($raw.TrimEnd('\','/'), $key)
    $value = $value.Replace($raw, $key)
  }
  $value = $value -replace '\\','/'
  $value = $value -replace '(?i)[A-Z]:/Users/[^/]+','<USER_HOME>'
  $value = $value -replace '(?i)/home/[^/]+','<USER_HOME>'
  return $value
}

function ConvertTo-RedactedObject([AllowNull()]$Value, [hashtable]$Map) {
  if ($null -eq $Value) { return $null }
  if ($Value -is [string]) { return ConvertTo-RedactedPath $Value $Map }
  if ($Value -is [System.Collections.IDictionary]) {
    $out = [ordered]@{}
    foreach ($key in $Value.Keys) { $out[$key] = ConvertTo-RedactedObject $Value[$key] $Map }
    return $out
  }
  if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
    return @($Value | ForEach-Object { ConvertTo-RedactedObject $_ $Map })
  }
  return $Value
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

function ConvertTo-ArrayObject([AllowNull()]$Value) {
  if ($null -eq $Value) { return @() }
  if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string] -and $Value -isnot [System.Collections.IDictionary]) {
    return @($Value | ForEach-Object { $_ })
  }
  return @($Value)
}


function Get-RuntimeImageName([hashtable]$Environment) {
  if ($env:ASSET_FACTORY_RUNTIME_IMAGE) { return $env:ASSET_FACTORY_RUNTIME_IMAGE }
  if ($Environment -and $Environment.ContainsKey('runtimeImage') -and $Environment['runtimeImage']) { return [string]$Environment['runtimeImage'] }
  return 'codex-unity-comfyui-runtime:blackwell-cu128'
}

function Test-DockerImagePresent([string]$Image) {
  if (!(Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
  try {
    $result = Invoke-ProcessCaptured 'docker' @('image','inspect',$Image)
    return $result.exitCode -eq 0
  } catch {
    return $false
  }
}

function Test-RuntimeImageCoveredInstallable([string]$InstallableId, [hashtable]$Environment) {
  if (!$Environment -or $Environment['profile'] -ne 'blackwell') { return $false }
  return @('comfyui','comfyui-trellis2','pytorch-cuda','flash-attention','xformers','trellis2-models') -contains $InstallableId
}

function Test-RuntimeImageShouldPull([string]$Image) {
  if ($env:ASSET_FACTORY_RUNTIME_PULL -match '^(1|true|yes)$') { return $true }
  if ($env:ASSET_FACTORY_RUNTIME_PULL -match '^(0|false|no)$') { return $false }
  return $Image -match '^(ghcr\.io|docker\.io|registry\.|[^/]+\.[^/]+)/'
}
function Get-DefaultInstallRoot {
  if ($env:ASSET_FACTORY_INSTALL_ROOT) { return $env:ASSET_FACTORY_INSTALL_ROOT }
  if ($env:LOCALAPPDATA) { return (Join-Path $env:LOCALAPPDATA 'CodexAssetFactory') }
  return (Join-Path $HOME '.local/share/codex-asset-factory')
}

function Get-SetupEnvironment([string]$Target, [string]$Profile, [string]$InstallRoot, [string]$CodexHome, [string]$UnityProject, [string]$PluginRoot) {
  $isWindows = $PSVersionTable.Platform -eq 'Win32NT' -or $env:OS -match 'Windows'
  $detectedTarget = if ($Target -ne 'auto') { $Target } elseif ($isWindows) { 'windows' } else { 'linux' }
  if ($detectedTarget -eq 'linux' -and (Test-Path '/proc/version')) {
    try { if ((Get-Content '/proc/version' -Raw) -match '(?i)microsoft|wsl') { $detectedTarget = 'wsl' } } catch {}
  }
  $installRootValue = if ($InstallRoot) { $InstallRoot } else { Get-DefaultInstallRoot }
  $codexHomeValue = if ($CodexHome) { $CodexHome } elseif ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
  $gpu = [ordered]@{ present = $false; name = $null; computeCapability = $null; driver = $null }
  $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
  if ($nvidia) {
    try {
      $line = & $nvidia.Source --query-gpu=name,compute_cap,driver_version --format=csv,noheader 2>$null | Select-Object -First 1
      if ($line) {
        $parts = $line -split ',\s*'
        $gpu.present = $true
        $gpu.name = $parts[0]
        $gpu.computeCapability = if ($parts.Count -gt 1) { $parts[1] } else { $null }
        $gpu.driver = if ($parts.Count -gt 2) { $parts[2] } else { $null }
      }
    } catch {}
  }
  $detectedProfile = $Profile
  if ($detectedProfile -eq 'auto') {
    if (!$gpu.present) { $detectedProfile = 'cpu' }
    elseif (($gpu.computeCapability -match '^12') -or ($gpu.name -match '(?i)blackwell|rtx\s*50')) { $detectedProfile = 'blackwell' }
    else { $detectedProfile = 'ada' }
  }
  return [ordered]@{
    target = $detectedTarget
    profile = $detectedProfile
    installRoot = $installRootValue
    codexHome = $codexHomeValue
    unityProject = $UnityProject
    pluginRoot = $PluginRoot
    runtimeImage = if ($env:ASSET_FACTORY_RUNTIME_IMAGE) { $env:ASSET_FACTORY_RUNTIME_IMAGE } else { 'codex-unity-comfyui-runtime:blackwell-cu128' }
    commands = [ordered]@{
      git = Get-CommandStatus 'git'
      node = Get-CommandStatus 'node'
      npm = Get-CommandStatus 'npm'
      python = Get-CommandStatus 'python'
      codex = Get-CommandStatus 'codex' @('--version')
      docker = Get-CommandStatus 'docker' @('--version')
      pwsh = Get-CommandStatus 'pwsh' @('-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()')
    }
    gpu = $gpu
  }
}

function Read-InstallProfile([string]$PluginRoot, [string]$Profile) {
  $path = Join-Path $PluginRoot "configs\install-profiles\$Profile.json"
  if (!(Test-Path -LiteralPath $path)) { throw "Install profile missing: $Profile" }
  $profileData = ConvertTo-HashtableObject (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)
  if ($profileData['extends']) {
    $base = Read-InstallProfile $PluginRoot ([string]$profileData['extends'])
    $profileData['installables'] = @($base['installables']) + @($profileData['installables'])
  }
  return $profileData
}

function Test-InstallablePresent([hashtable]$Item, [hashtable]$Environment) {
  $checks = @()
  $detect = $Item['detect']
  $commands = $Environment['commands']
  foreach ($commandName in (ConvertTo-ArrayObject $detect['commands'])) {
    if (!$commandName) { continue }
    $commandKey = [string]$commandName
    if (Get-Command $commandKey -ErrorAction SilentlyContinue) { $checks += $commandKey }
  }
  foreach ($relative in (ConvertTo-ArrayObject $detect['paths'])) {
    if (!$relative) { continue }
    $relativeText = [string]$relative
    $candidate = $relativeText.Replace('<INSTALL_ROOT>', $Environment['installRoot']).Replace('<CODEX_HOME>', $Environment['codexHome']).Replace('<PLUGIN_ROOT>', $Environment['pluginRoot']).Replace('<UNITY_PROJECT>', $Environment['unityProject'])
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $checks += $relative }
  }
  foreach ($moduleName in (ConvertTo-ArrayObject $detect['pythonModules'])) {
    if (!$moduleName) { continue }
    $pythonCandidates = @()
    $venvPython = if ($env:OS -match 'Windows') { Join-Path $Environment['installRoot'] 'venv\Scripts\python.exe' } else { Join-Path $Environment['installRoot'] 'venv/bin/python' }
    if (Test-Path -LiteralPath $venvPython) { $pythonCandidates += $venvPython }
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) { $pythonCandidates += $systemPython.Source }
    foreach ($python in $pythonCandidates) {
      $code = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$moduleName') else 1)"
      $result = Invoke-ProcessCaptured $python @('-c',$code)
      if ($result.exitCode -eq 0) {
        $checks += "python:$moduleName"
        break
      }
    }
  }
  return $checks
}

function New-InstallStep([hashtable]$Item, [hashtable]$Environment, [string]$Fallback) {
  $presentChecks = Test-InstallablePresent $Item $Environment
  if ($presentChecks.Count -eq 0) {
    $fallbackCommandById = @{
      git = 'git'
      nodejs = 'node'
      python = 'python'
      codex = 'codex'
      docker = 'docker'
      cuda = 'nvidia-smi'
      wsl = 'wsl'
    }
    $idForFallback = [string]$Item['id']
    if ($fallbackCommandById.ContainsKey($idForFallback) -and (Get-Command $fallbackCommandById[$idForFallback] -ErrorAction SilentlyContinue)) {
      $presentChecks += $fallbackCommandById[$idForFallback]
    }
    if ($idForFallback -eq 'codex-unity-comfyui-pipeline' -and (Test-Path -LiteralPath (Join-Path $Environment['pluginRoot'] 'mcp\server.mjs'))) {
      $presentChecks += '<PLUGIN_ROOT>/mcp/server.mjs'
    }
    if ($idForFallback -eq 'docker-runtime-image' -and (Test-DockerImagePresent (Get-RuntimeImageName $Environment))) {
      $presentChecks += '<RUNTIME_IMAGE>'
    }
  }
  $manual = [bool]$Item['manualRequired']
  $status = if ($presentChecks.Count -gt 0) { 'present' } elseif ($manual) { 'manual_required' } else { 'installable' }
  if (Test-RuntimeImageCoveredInstallable ([string]$Item['id']) $Environment) { $status = 'covered_by_runtime_image' }
  $sourceStatus = if ($Item['sourceStatus']) { $Item['sourceStatus'] } else { 'official' }
  if ($sourceStatus -ne 'official') { $status = 'source_review_required' }
  return [ordered]@{
    id = $Item['id']
    name = $Item['name']
    role = $Item['role']
    status = $status
    sourceStatus = $sourceStatus
    officialSource = $Item['officialSource']
    licenseNote = $Item['licenseNote']
    presentChecks = $presentChecks
    fallback = $Fallback
    manual = $Item['manual']
    commands = $Item['commands']
    validation = $Item['validation']
  }
}

function New-SetupPlan([hashtable]$ProfileData, [hashtable]$Environment, [string]$Fallback) {
  $steps = @()
  foreach ($item in @($ProfileData['installables'])) { $steps += New-InstallStep $item $Environment $Fallback }
  $blocked = @($steps | Where-Object { $_.status -in @('manual_required','source_review_required') })
  $missing = @($steps | Where-Object { $_.status -eq 'installable' })
  return [ordered]@{
    schema = 'codex.assetFactory.bootstrapPlan.v1'
    createdAt = (Get-Date).ToUniversalTime().ToString('o')
    target = $Environment.target
    profile = $Environment.profile
    fallback = $Fallback
    state = if ($blocked.Count -gt 0) { 'partially_ready' } elseif ($missing.Count -gt 0) { 'installable' } else { 'ready' }
    summary = [ordered]@{
      present = @($steps | Where-Object { $_.status -eq 'present' }).Count
      installable = $missing.Count
      manualRequired = @($steps | Where-Object { $_.status -eq 'manual_required' }).Count
      sourceReviewRequired = @($steps | Where-Object { $_.status -eq 'source_review_required' }).Count
      coveredByRuntimeImage = @($steps | Where-Object { $_.status -eq 'covered_by_runtime_image' }).Count
    }
    environment = $Environment
    steps = $steps
    nextActions = @(
      'Read docs/<lang>/INSTALL.md before non-dry-run installation.',
      'Run bootstrap/install.ps1 --dry-run first.',
      'Complete manual DINOv3/Hugging Face steps if marked manual_required.',
      'Run bootstrap/install.ps1 --validate-only after installation.'
    )
  }
}

function Resolve-SetupPath([AllowNull()][string]$Value, [hashtable]$Environment, [string]$PluginRoot) {
  if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }
  return $Value.Replace('<INSTALL_ROOT>', $Environment['installRoot']).Replace('<CODEX_HOME>', $Environment['codexHome']).Replace('<PLUGIN_ROOT>', $PluginRoot).Replace('<COMFYUI_ROOT>', (Join-Path $Environment['installRoot'] 'ComfyUI')).Replace('<UNITY_PROJECT>', $Environment['unityProject'])
}

function ConvertTo-ProcessArgument([AllowNull()][string]$Argument) {
  if ($null -eq $Argument) { return '""' }
  if ($Argument -notmatch '[\s"]') { return $Argument }
  return '"' + ($Argument -replace '([\\]*)"', '$1$1\"' -replace '([\\]+)$', '$1$1') + '"'
}

function Invoke-ProcessCaptured([string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory = '') {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $FilePath
  $psi.Arguments = (($Arguments | ForEach-Object { ConvertTo-ProcessArgument ([string]$_) }) -join ' ')
  if ($WorkingDirectory) { $psi.WorkingDirectory = $WorkingDirectory }
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $psi
  [void]$process.Start()
  $stdout = $process.StandardOutput.ReadToEnd()
  $stderr = $process.StandardError.ReadToEnd()
  $process.WaitForExit()
  return [ordered]@{ exitCode = $process.ExitCode; stdout = $stdout; stderr = $stderr }
}

function Get-VenvPython([hashtable]$Environment) {
  $root = $Environment['installRoot']
  if ($env:OS -match 'Windows') { return Join-Path $root 'venv\Scripts\python.exe' }
  return Join-Path $root 'venv/bin/python'
}

function Ensure-Venv([hashtable]$Environment) {
  $venvPython = Get-VenvPython $Environment
  if (Test-Path -LiteralPath $venvPython) { return [ordered]@{ status = 'present'; python = $venvPython } }
  New-Item -ItemType Directory -Force -Path $Environment['installRoot'] | Out-Null
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (!$python) { return [ordered]@{ status = 'failed'; error = 'python command missing' } }
  $created = Invoke-ProcessCaptured $python.Source @('-m','venv',(Join-Path $Environment['installRoot'] 'venv'))
  if ($created.exitCode -ne 0) { return [ordered]@{ status = 'failed'; command = 'python -m venv <INSTALL_ROOT>/venv'; result = $created } }
  return [ordered]@{ status = 'created'; python = $venvPython }
}

function Invoke-GitCloneIfMissing([string]$Repo, [string]$Destination) {
  if (Test-Path -LiteralPath $Destination) { return [ordered]@{ status = 'present'; path = $Destination } }
  $git = Get-Command git -ErrorAction SilentlyContinue
  if (!$git) { return [ordered]@{ status = 'failed'; error = 'git command missing' } }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
  $result = Invoke-ProcessCaptured $git.Source @('clone',$Repo,$Destination)
  return [ordered]@{ status = if ($result.exitCode -eq 0) { 'installed' } else { 'failed' }; repo = $Repo; path = $Destination; result = $result }
}

function Invoke-PipInstall([hashtable]$Environment, [string[]]$Packages, [string[]]$ExtraArgs = @()) {
  $venv = Ensure-Venv $Environment
  if ($venv.status -eq 'failed') { return $venv }
  $python = $venv.python
  $args = @('-m','pip','install') + $Packages + $ExtraArgs
  $result = Invoke-ProcessCaptured $python $args
  return [ordered]@{ status = if ($result.exitCode -eq 0) { 'installed' } else { 'failed' }; command = 'python -m pip install'; packages = $Packages; result = $result }
}

function Invoke-InstallStep([hashtable]$Step, [hashtable]$Environment, [string]$PluginRoot, [string]$Target, [string]$Fallback) {
  $id = [string]$Step['id']
  if ($Step['status'] -eq 'present') { return [ordered]@{ id = $id; status = 'skipped_present' } }
  if ($Step['status'] -eq 'covered_by_runtime_image') { return [ordered]@{ id = $id; status = 'skipped_covered_by_runtime_image'; runtimeImage = Get-RuntimeImageName $Environment } }
  if ($Step['status'] -in @('manual_required','source_review_required')) { return [ordered]@{ id = $id; status = $Step['status']; officialSource = $Step['officialSource']; manual = $Step['manual'] } }
  switch ($id) {
    'git' {
      if ($Target -eq 'windows' -and (Get-Command winget -ErrorAction SilentlyContinue)) { $r = Invoke-ProcessCaptured 'winget' @('install','--id','Git.Git','-e','--accept-package-agreements','--accept-source-agreements'); return [ordered]@{ id=$id; status=if($r.exitCode -eq 0){'installed'}else{'failed'}; result=$r } }
      return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource'] }
    }
    'nodejs' {
      if ($Target -eq 'windows' -and (Get-Command winget -ErrorAction SilentlyContinue)) { $r = Invoke-ProcessCaptured 'winget' @('install','--id','OpenJS.NodeJS.LTS','-e','--accept-package-agreements','--accept-source-agreements'); return [ordered]@{ id=$id; status=if($r.exitCode -eq 0){'installed'}else{'failed'}; result=$r } }
      return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource'] }
    }
    'python' {
      if ($Target -eq 'windows' -and (Get-Command winget -ErrorAction SilentlyContinue)) { $r = Invoke-ProcessCaptured 'winget' @('install','--id','Python.Python.3.11','-e','--accept-package-agreements','--accept-source-agreements'); return [ordered]@{ id=$id; status=if($r.exitCode -eq 0){'installed'}else{'failed'}; result=$r } }
      return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource'] }
    }
    'codex' { return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource']; reason='Codex install is account/app-channel dependent and must be completed from the official OpenAI entry point.' } }
    'codex-unity-comfyui-pipeline' { $sync = Invoke-PluginSync $PluginRoot; return [ordered]@{ id=$id; status=$sync.status; result=$sync } }
    'docker-runtime-image' {
      if (!(Get-Command docker -ErrorAction SilentlyContinue)) { return [ordered]@{ id=$id; status='manual_required'; officialSource='https://docs.docker.com/get-started/get-docker/'; reason='Docker is required before pulling or building the runtime image.' } }
      $image = Get-RuntimeImageName $Environment
      if (Test-DockerImagePresent $image) {
        $validation = Invoke-ProcessCaptured 'docker' @('run','--rm','--gpus','all',$image,'asset-factory-validate-runtime')
        return [ordered]@{ id=$id; status=if($validation.exitCode -eq 0){'validated'}else{'failed'}; image=$image; action='inspect'; validation=$validation }
      }
      if (Test-RuntimeImageShouldPull $image) {
        $pull = Invoke-ProcessCaptured 'docker' @('pull',$image)
        if ($pull.exitCode -eq 0) {
          $validation = Invoke-ProcessCaptured 'docker' @('run','--rm','--gpus','all',$image,'asset-factory-validate-runtime')
          return [ordered]@{ id=$id; status=if($validation.exitCode -eq 0){'installed'}else{'failed'}; image=$image; action='pull'; pull=$pull; validation=$validation }
        }
        if ($Fallback -eq 'manual') { return [ordered]@{ id=$id; status='failed_manual_fallback'; image=$image; action='pull'; result=$pull } }
      }
      $script = Join-Path $PluginRoot 'docker\build_runtime.ps1'
      $build = Invoke-ProcessCaptured 'powershell' @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script,'-Image',$image,'-Stage','all','-BuildJobs','1','-IncludeTrellis2Models') $PluginRoot
      if ($build.exitCode -ne 0) { return [ordered]@{ id=$id; status='failed'; image=$image; action='build-staged'; result=$build } }
      $validation = Invoke-ProcessCaptured 'docker' @('run','--rm','--gpus','all',$image,'asset-factory-validate-runtime')
      return [ordered]@{ id=$id; status=if($validation.exitCode -eq 0){'installed'}else{'failed'}; image=$image; action='build-staged'; build=$build; validation=$validation }
    }    'comfyui' { return Invoke-GitCloneIfMissing 'https://github.com/comfyanonymous/ComfyUI' (Join-Path $Environment['installRoot'] 'ComfyUI') }
    'comfyui-trellis2' { return Invoke-GitCloneIfMissing 'https://github.com/visualbruno/ComfyUI-Trellis2' (Join-Path $Environment['installRoot'] 'ComfyUI\custom_nodes\ComfyUI-Trellis2') }
    'pytorch-cuda' { return Invoke-PipInstall $Environment @('torch','torchvision') @('--index-url','https://download.pytorch.org/whl/cu128') }
    'pytorch-cpu' { return Invoke-PipInstall $Environment @('torch','torchvision') @('--index-url','https://download.pytorch.org/whl/cpu') }
    'flash-attention' { return Invoke-PipInstall $Environment @('flash-attn') @('--no-build-isolation') }
    'xformers' { return Invoke-PipInstall $Environment @('xformers') }
    'trellis2-models' {
      $venv = Ensure-Venv $Environment
      if ($venv.status -eq 'failed') { return $venv }
      $pip = Invoke-ProcessCaptured $venv.python @('-m','pip','install','huggingface_hub')
      if ($pip.exitCode -ne 0) { return [ordered]@{ id=$id; status='failed'; result=$pip } }
      $local = Join-Path $Environment['installRoot'] 'models\TRELLIS.2-4B'
      New-Item -ItemType Directory -Force -Path $local | Out-Null
      $code = "from huggingface_hub import snapshot_download; snapshot_download(repo_id='microsoft/TRELLIS.2-4B', local_dir=r'$local')"
      $r = Invoke-ProcessCaptured $venv.python @('-c',$code)
      return [ordered]@{ id=$id; status=if($r.exitCode -eq 0){'installed'}else{'failed_manual_fallback'}; path=$local; result=$r; officialSource=$Step['officialSource'] }
    }
    'unity' {
      if ($Environment['unityProject'] -and (Test-Path -LiteralPath (Join-Path $Environment['unityProject'] 'Assets'))) { $r = Invoke-ProcessCaptured 'powershell' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PluginRoot 'scripts\install_unity_template.ps1'),'-UnityProjectRoot',$Environment['unityProject']); return [ordered]@{ id=$id; status=if($r.exitCode -eq 0){'installed'}else{'failed'}; result=$r } }
      return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource']; reason='Unity project path missing or invalid.' }
    }
    'mcp-unity' {
      if (!$Environment['unityProject']) { return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource']; reason='Unity project path is required.' } }
      $packageDest = Join-Path $Environment['unityProject'] 'Packages\com.gamelovers.mcp-unity'
      if (Test-Path -LiteralPath $packageDest) { return [ordered]@{ id=$id; status='present'; path='<UNITY_PROJECT>/Packages/com.gamelovers.mcp-unity' } }
      $sourceRoot = Join-Path $Environment['installRoot'] 'sources\mcp-unity'
      $clone = Invoke-GitCloneIfMissing 'https://github.com/CoderGamester/mcp-unity' $sourceRoot
      if ($clone.status -eq 'failed') { return [ordered]@{ id=$id; status='failed'; result=$clone } }
      $candidate = Get-ChildItem -LiteralPath $sourceRoot -Recurse -Directory -Filter 'com.gamelovers.mcp-unity' -ErrorAction SilentlyContinue | Select-Object -First 1
      if (!$candidate) { return [ordered]@{ id=$id; status='source_review_required'; officialSource=$Step['officialSource']; reason='Could not locate com.gamelovers.mcp-unity folder in cloned repository.' } }
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $packageDest) | Out-Null
      Copy-Item -Recurse -Force -LiteralPath $candidate.FullName -Destination $packageDest
      return [ordered]@{ id=$id; status='installed'; path='<UNITY_PROJECT>/Packages/com.gamelovers.mcp-unity' }
    }
    default { return [ordered]@{ id=$id; status='manual_required'; officialSource=$Step['officialSource']; reason='No automated installer implemented for this component yet.' } }
  }
}

function Invoke-SetupActions([hashtable]$Plan, [hashtable]$Environment, [string]$PluginRoot, [string]$Target, [string]$Fallback) {
  $results = @()
  foreach ($step in @($Plan['steps'])) { $results += Invoke-InstallStep $step $Environment $PluginRoot $Target $Fallback }
  return $results
}

function Invoke-ValidationSuite([string]$PluginRoot) {
  $checks = [ordered]@{}
  $scan = Invoke-ProcessCaptured 'powershell' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PluginRoot 'scripts\scan_private_leaks.ps1'),'-Root',$PluginRoot)
  $checks.privateLeakScan = [ordered]@{ status = if($scan.exitCode -eq 0){'ok'}else{'failed'}; result = $scan }
  $validate = Invoke-ProcessCaptured 'powershell' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PluginRoot 'scripts\validate_plugin.ps1'),'-PluginRoot',$PluginRoot)
  $checks.pluginValidation = [ordered]@{ status = if($validate.exitCode -eq 0){'ok'}else{'failed'}; result = $validate }
  return $checks
}
function Invoke-PluginSync([string]$PluginRoot, [switch]$DryRun) {
  $script = Join-Path $PluginRoot 'scripts\sync_plugin_install.ps1'
  if (!(Test-Path -LiteralPath $script)) { return [ordered]@{ status = 'missing'; script = '<PLUGIN_ROOT>/scripts/sync_plugin_install.ps1' } }
  if ($DryRun) { return [ordered]@{ status = 'planned'; command = 'scripts/sync_plugin_install.ps1' } }
  & powershell -NoProfile -ExecutionPolicy Bypass -File $script -PluginRoot $PluginRoot | Out-Null
  return [ordered]@{ status = 'ok'; command = 'scripts/sync_plugin_install.ps1' }
}

function Invoke-AssetFactorySetup {
  param(
    [string]$PluginRoot,
    [ValidateSet('auto','windows','linux','wsl','docker')] [string]$Target = 'auto',
    [ValidateSet('auto','ada','blackwell','cpu')] [string]$Profile = 'auto',
    [ValidateSet('auto','semi-auto','manual')] [string]$Fallback = 'auto',
    [switch]$DryRun,
    [switch]$ValidateOnly,
    [switch]$NonInteractive,
    [string]$InstallRoot = '',
    [string]$CodexHome = '',
    [string]$UnityProject = '',
    [switch]$Json
  )
  $environment = Get-SetupEnvironment $Target $Profile $InstallRoot $CodexHome $UnityProject $PluginRoot
  $profileData = Read-InstallProfile $PluginRoot $environment.profile
  $plan = New-SetupPlan $profileData $environment $Fallback
  $map = @{
    '<PLUGIN_ROOT>' = $PluginRoot
    '<CODEX_HOME>' = $environment.codexHome
    '<INSTALL_ROOT>' = $environment.installRoot
    '<UNITY_PROJECT>' = $environment.unityProject
    '<RUNTIME_IMAGE>' = Get-RuntimeImageName $environment
  }
  $execution = [ordered]@{}
  if ($ValidateOnly) {
    $execution.mode = 'validate-only'
    $execution.pluginManifest = Test-Path -LiteralPath (Join-Path $PluginRoot '.codex-plugin\plugin.json')
    $execution.mcpServer = Test-Path -LiteralPath (Join-Path $PluginRoot 'mcp\server.mjs')
    $execution.validation = Invoke-ValidationSuite $PluginRoot
  } elseif ($DryRun) {
    $execution.mode = 'dry-run'
    $execution.actions = @('No downloads or installers executed.', 'Official commands are listed per step.', 'Plugin sync is planned only.')
  } else {
    $execution.mode = 'install'
    $execution.steps = Invoke-SetupActions $plan $environment $PluginRoot $environment.target $Fallback
    $failed = @($execution.steps | Where-Object { $_.status -in @('failed','failed_manual_fallback') })
    $manual = @($execution.steps | Where-Object { $_.status -in @('manual_required','source_review_required') })
    $execution.state = if ($failed.Count -gt 0) { 'failed' } elseif ($manual.Count -gt 0) { 'partial_manual_required' } else { 'installed' }
    $execution.note = 'Automated steps were executed only for components that are legally and technically automatable. Manual/license-gated items were left visible.'
  }
  $result = [ordered]@{
    schema = 'codex.assetFactory.bootstrapResult.v1'
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    nonInteractive = [bool]$NonInteractive
    validateOnly = [bool]$ValidateOnly
    dryRun = [bool]$DryRun
    plan = $plan
    execution = $execution
  }
  $redacted = ConvertTo-RedactedObject $result $map
  if ($Json) {
    $redacted | ConvertTo-Json -Depth 60
    return
  } else {
    Write-Host "Asset Factory bootstrap: $($redacted.plan.state)"
    Write-Host "Target/profile: $($redacted.plan.target) / $($redacted.plan.profile)"
    Write-Host "Present: $($redacted.plan.summary.present), installable: $($redacted.plan.summary.installable), manual: $($redacted.plan.summary.manualRequired)"
    foreach ($step in $redacted.plan.steps) { Write-Host ("- {0}: {1} ({2})" -f $step.id, $step.status, $step.officialSource) }
  }
}

Export-ModuleMember -Function Invoke-AssetFactorySetup, Get-SetupEnvironment, New-SetupPlan








