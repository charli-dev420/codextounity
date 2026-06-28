# Installation

## Before You Start

This project is a prototype. The installer can clone official repositories, install Python/npm packages, use Docker, install the Unity template and sync the Codex plugin. There is no guarantee that everything works on your machine.

Simple rule:

1. Run a dry-run.
2. Read the plan.
3. Complete manual steps.
4. Install only when you understand what will happen.
5. Validate.
6. Open Codex.

## Prerequisites

Recommended minimum:

- Git to clone official sources.
- Node.js LTS for the MCP server.
- Python 3.11 or 3.12 for scripts.
- Codex or the target Codex environment.
- PowerShell 7 for the full Linux/WSL wrapper.

Depending on profile:

- Docker for runtime/Blackwell mode.
- Compatible NVIDIA driver and CUDA for GPU generation.
- Unity Hub/Editor and an existing Unity project for import.
- Hugging Face access and accepted terms for some models.
- Enough disk space for ComfyUI, models and caches.

If you are unsure, use `--profile cpu` to validate the plugin without heavy GPU generation.

## Graphical Installer

From the project root:

```powershell
.\bootstrap\start-ui.ps1
```

If the browser does not open:

```powershell
.\bootstrap\start-ui.ps1 -NoBrowser
```

Then open the URL shown in the terminal.

In the UI:

1. Choose `Target`.
2. Choose `Profile`.
3. Fill `Install root`, `Codex home` or `Unity project` only when needed.
4. Click `Preflight and plan`.
5. Read each component, status and official source.
6. Complete `manual_required` steps.
7. Click `Install missing allowed items` only if the plan is clear.
8. Click `Validate setup`.

## Windows CLI

Show help:

```powershell
.\bootstrap\install.ps1 --help
```

Recommended path:

```powershell
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
```

Example with explicit paths:

```powershell
.\bootstrap\install.ps1 `
  --dry-run `
  --target windows `
  --profile blackwell `
  --install-root "<INSTALL_ROOT>" `
  --codex-home "<CODEX_HOME>" `
  --unity-project "<UNITY_PROJECT>"
```

## Linux / WSL CLI

Show help:

```bash
./bootstrap/install.sh --help
```

Linux:

```bash
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --target linux --profile auto
./bootstrap/install.sh --validate-only --target linux --profile auto
```

WSL:

```bash
./bootstrap/install.sh --dry-run --target wsl --profile auto
./bootstrap/install.sh --target wsl --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

The Linux wrapper uses PowerShell 7 (`pwsh`) so both platforms share the same installer engine. If `pwsh` is missing, dry-run returns a manual action instead of installing anything.

## Docker

Check the Compose file:

```bash
docker compose -f docker/compose.yaml config
```

Runtime validation when the image already exists:

```bash
docker compose -f docker/compose.yaml run --rm asset-factory-runtime
```

The Blackwell Docker build is heavy. Do not run it on a constrained machine without watching RAM, VRAM, CPU and disk usage.

## Profiles

- `auto` detects the machine and chooses a profile.
- `cpu` validates the plugin, scripts, docs, Unity and dry-runs without heavy GPU generation.
- `ada` targets NVIDIA CUDA systems compatible with Ada-class setups.
- `blackwell` adds a Docker/runtime route and possible workarounds for RTX 50 / Blackwell.

## What The Installer May Do

Depending on profile and mode, the installer may:

- check `git`, `node`, `npm`, `python`, `codex`, `docker`, `pwsh`;
- clone ComfyUI from the official repository;
- clone ComfyUI-Trellis2 from the official repository;
- install PyTorch from the official PyTorch index;
- install FlashAttention and xformers when the profile requires them;
- download TRELLIS2 models through Hugging Face when rights are available;
- install or validate the Unity template;
- install the MCP Unity package from the validated source;
- sync the plugin into local Codex/agents folders.

## Manual Steps

DINOv3 remains manual. Open the official Hugging Face page, review terms, accept if required, download the model and place it under:

```text
<INSTALL_ROOT>/models/dinov3
```

Do not commit models to this repository.

## Unity

Prepare Unity:

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot "<UNITY_PROJECT>"
```

Validate without running Unity batch mode:

```powershell
.\scripts\smoke_app.ps1 -UnityProject "<UNITY_PROJECT>" -SkipUnityBatch
```

`-SkipUnityBatch` means the full Unity batch import is not proven by that command.

## Validation Before Public Push

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

Remove local proof JSON after validation when preparing a public push:

```powershell
Remove-Item -Force proof\*.json -ErrorAction SilentlyContinue
```
