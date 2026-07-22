# Asset Factory Installer and Codex Unity ComfyUI Pipeline

This project provides a local standalone installer first, then a Codex plugin for a Unity + ComfyUI/TRELLIS2 pipeline.

## Project Status

This repository is an experimental prototype maintained by a single developer and is not broadly tested across machines.

- No guarantee of any kind.
- No stability guarantee.
- No promise that installers work on every machine.
- Best-effort support only, with no SLA.
- GPU, Docker, WSL, Unity, model and node setups may require manual fixes.
- Issues, pull requests, setup tips and documentation fixes are welcome.

Always start with a dry-run. Read the installation plan before allowing downloads or local writes.

## Recommended Order

1. Run the installer before Codex.
2. Check the machine and dependencies.
3. Read official sources and manual steps.
4. Install only missing and allowed items.
5. Complete required manual steps, especially DINOv3 when a workflow needs it.
6. Validate the setup.
7. Open Codex and use the Asset Factory app.

Codex remains the decision layer under the user's direction. ComfyUI and TRELLIS2 are local generation engines. Post-generation processing, normalization, pivots, scale, Unity manifests and imports are controlled by Codex and/or the user.

## Quick Start

Experimental Windows executable:

```powershell
.\installer\windows\build-installer.ps1
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe
```

Local developer web UI:

```powershell
.\bootstrap\start-ui.ps1
```

Windows CLI:

```powershell
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
```

Linux/WSL CLI:

```bash
./bootstrap/install.sh --help
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --target linux --profile auto
./bootstrap/install.sh --dry-run --target wsl --profile auto
./bootstrap/install.sh --target wsl --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

## Documentation

- Full installation: `docs/en/INSTALL.md`
- User guide: `docs/en/USER_GUIDE.md`
- Architecture and orchestration: `docs/en/ARCHITECTURE.md`
- Troubleshooting: `docs/en/TROUBLESHOOTING.md`
- Credits and disclaimer: `docs/en/CREDITS_AND_DISCLAIMER.md`
- Contributing: `CONTRIBUTING.md`
- Support: `SUPPORT.md`
- Security: `SECURITY.md`

## Checks Before Sharing

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

Do not publish tokens, personal paths, private project names, raw logs, local proof JSON, generated heavy assets, models, Python caches or generated Unity folders.

## Placeholders

Examples use only:

- `<INSTALL_ROOT>`
- `<CODEX_HOME>`
- `<PLUGIN_ROOT>`
- `<COMFYUI_ROOT>`
- `<UNITY_PROJECT>`
- `<WORK_DIR>`
