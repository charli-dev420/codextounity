param(
  [string]$Image = 'codex-unity-comfyui-runtime:blackwell-cu128'
)
$ErrorActionPreference = 'Stop'
docker run --rm --gpus all $Image asset-factory-validate-runtime
