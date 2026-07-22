# Installation

## Before You Start

This project is an experimental prototype that is not broadly tested across machines. The installer can clone official repositories, install Python/npm packages, use Docker, install the Unity template and sync the Codex plugin. There is no guarantee that it works on your machine.

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

If you are unsure, use `--profile cpu` to validate the plugin without heavy GPU generation. The CPU profile can validate the plugin and dry-runs, but real TRELLIS2 generation still needs the model/runtime requirements requested by the selected workflow.

## Windows Installer (.exe)

For novice Windows users, `AssetFactoryInstaller.exe` is only an optional experimental entry point. The user should be able to double-click the executable, run `Preflight and plan`, read the components, review local writes and manual steps, then choose `Install missing allowed items` and `Validate setup`.

The install button stays disabled until preflight succeeds with the current fields. If target, profile, fallback, plugin root, install root, Codex home or Unity project changes, run preflight again.

Build that executable from the repository:

```powershell
.\installer\windows\build-installer.ps1
```

Generated executable:

```text
installer/windows/dist/AssetFactoryInstaller-win-x64/AssetFactoryInstaller.exe
```

Silent executable check:

```powershell
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe --validate-launcher --plugin-root <PLUGIN_ROOT>
```

Do not commit `dist/`, `bin/` or `obj/`. Share the executable as an experimental download artifact when you want a novice-facing entry point.

Windows SmartScreen may warn because this MVP executable is not code-signed. Treat that warning as expected for an unsigned experimental artifact. Review the source, build locally when possible, and do not bypass warnings unless you knowingly accept the risk.

Optional local gate:

```powershell
.\installer\windows\test-installer.ps1
```

The gate builds the executable, validates the launcher, runs dry-run and validate-only, then removes generated proof JSON.

## Local Developer Web UI

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
6. Review local writes and local state.
7. Complete `manual_required` and `source_review_required` steps.
8. Click `Install missing allowed items` only if the plan is clear and you accept the experimental confirmation.
9. Click `Validate setup`.

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

Start the bundled ComfyUI service and verify the public endpoint:

```bash
docker compose -f docker/compose.yaml up asset-factory-comfyui
```

Open `http://127.0.0.1:8188` or check logs from another terminal:

```bash
docker compose -f docker/compose.yaml logs -f asset-factory-comfyui
```

The Blackwell Docker build is heavy. Do not run it on a constrained machine without watching RAM, VRAM, CPU and disk usage.
If the runtime image is missing, run the dry-run first and read the planned image/build action before pulling or building anything.

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

Before a real first generation, confirm ComfyUI is reachable on the same URL shown in Asset Factory, normally `http://127.0.0.1:8188`.

Remove local proof JSON after validation when preparing a public push:

```powershell
Remove-Item -Force proof\*.json -ErrorAction SilentlyContinue
```
