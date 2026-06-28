# Troubleshooting

## General Method

1. Reproduce the problem with the shortest possible command.
2. Rerun with `--dry-run` when it is an installation problem.
3. Copy only redacted logs.
4. Remove tokens, personal paths, private project names and sensitive screenshots.
5. Include OS, profile, GPU, Python, Node, Docker, Unity and plugin version.

Base verification command:

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
```

## Installer Does Not Open

Symptoms:

- the browser window does not open;
- PowerShell blocks script execution;
- the local port seems already used.

Actions:

```powershell
.\bootstrap\start-ui.ps1 -NoBrowser
```

Then open the URL shown in the terminal.

Also verify:

```powershell
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
```

## `install.sh` Requires PowerShell 7

The Linux/WSL wrapper uses `pwsh` so Windows and Linux share the same installer engine.

Actions:

1. Install PowerShell 7 from the official Microsoft documentation.
2. Rerun:

```bash
./bootstrap/install.sh --dry-run --target linux --profile auto
```

If `pwsh` is missing, dry-run should return a `manual_required` action without installing anything.

## Codex Does Not See the Plugin

Actions:

1. Close Codex.
2. Validate the plugin:

```powershell
.\scripts\validate_plugin.ps1
```

3. Sync locally if you are developing this plugin:

```powershell
.\scripts\sync_plugin_install.ps1 -DryRun
.\scripts\sync_plugin_install.ps1
```

4. Restart Codex.

Note: `sync_plugin_install.ps1` is mainly a maintainer/local-development helper. It copies into local Codex/agents folders.

## `tools/list` Does Not Show Expected Tools

Verify:

```powershell
node --check .\mcp\server.mjs
.\scripts\validate_plugin.ps1
```

Expected state: `Tools: 19`.

If not, include:

- `validate_plugin.ps1` output,
- plugin version,
- redacted `.codex-plugin/plugin.json` content.

## ComfyUI Is Not Reachable

Check:

- ComfyUI is running;
- the port matches the `ComfyUI server` field;
- no firewall blocks the local port;
- the selected workflow exists.

Typical command:

```powershell
.\scripts\run_trellis2_assets.ps1 -InputDir "<WORK_DIR>\references" -OutputDir "<WORK_DIR>\out" -DryRun -Limit 1
```

## TRELLIS2 Does Not Return a GLB

Check:

- readable reference image;
- TRELLIS2 model present;
- DINOv3 present when the workflow requires it;
- Python imports without errors;
- ComfyUI logs;
- enough VRAM;
- FlashAttention/xformers compatibility.

Recommended action:

1. Test with a single asset.
2. Lower heavy options.
3. Run the pipeline in dry-run.
4. Include redacted ComfyUI logs if the issue persists.

## FlashAttention Fails

FlashAttention depends on PyTorch, CUDA, Python, GPU and available wheels.

Actions:

- verify the selected profile (`ada`, `blackwell`, `cpu`);
- verify PyTorch/CUDA;
- use an official compatible wheel when available;
- build only from the official source if you know how;
- continue without FlashAttention when the workflow allows it.

## DINOv3 Missing

This is expected until the manual step is complete.

Action:

1. Open the official Hugging Face page.
2. Read and accept terms if required.
3. Download manually.
4. Place the model under:

```text
<INSTALL_ROOT>/models/dinov3
```

Never commit the model.

## Unity Does Not Compile

Check:

- the template is under `<UNITY_PROJECT>/Assets/AIAssetPipeline`;
- Unity finished compiling;
- the Unity Console has no `AIAssetPipeline` errors;
- MCP Unity is installed if you want to operate Unity through MCP.

Reinstall the template:

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot "<UNITY_PROJECT>"
```

## Smoke Uses `-SkipUnityBatch`

`-SkipUnityBatch` validates the plugin without launching Unity batchmode. It does not prove a full Unity import in a real project.

For complete Unity proof, provide:

- valid `<UNITY_PROJECT>` path;
- available Unity executable;
- redacted Unity batch logs;
- no Console errors.

## Local Path or Secret Leak

Before sharing:

```powershell
.\scripts\scan_private_leaks.ps1
```

The scan must pass. Otherwise replace values with:

- `<INSTALL_ROOT>`
- `<CODEX_HOME>`
- `<PLUGIN_ROOT>`
- `<COMFYUI_ROOT>`
- `<UNITY_PROJECT>`
- `<WORK_DIR>`
