# Repository Guidelines

## Project Structure & Module Organization

This repository packages a Codex plugin and local Unity/ComfyUI asset pipeline. Core surfaces are:

- `mcp/`: Node.js MCP server and Asset Factory widget.
- `scripts/`: Python and PowerShell helpers for generation, validation, GLB normalization, Unity import, and publication checks.
- `unity/Assets/AIAssetPipeline/`: Unity C# editor/runtime template.
- `configs/`: install profiles, asset profiles, and JSON schemas.
- `workflows/`: TRELLIS2/ComfyUI workflow definitions.
- `bootstrap/` and `docker/`: installer and runtime setup entry points.
- `docs/`: mirrored French/English user and architecture documentation.

Generated outputs belong in ignored folders such as `proof/*.json`, `.codex_asset_jobs/`, Unity `Library/`, local `outputs/`, and temporary work directories.

## Build, Test, and Development Commands

Use PowerShell from the repository root on Windows:

```powershell
.\bootstrap\start-ui.ps1
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

`validate_plugin.ps1` syntax-checks Node/Python, validates asset profiles, checks MCP tools/resources, and writes redacted proof. `smoke_app.ps1` exercises planning, persistent jobs, GLB adjustment, and socket manifests. Use `-UnityProject` and `UNITY_EXE` only when validating Unity batch import.

## Coding Style & Naming Conventions

Keep existing language conventions: ESM JavaScript with two-space indentation, semicolons, and double quotes; Python with four-space indentation and CLI-friendly JSON output; PowerShell scripts with `param(...)` blocks and `$ErrorActionPreference = 'Stop'`; Unity C# types named `AIAsset...`. Preserve LF/CRLF rules from `.gitattributes`.

Use stable, descriptive snake_case for asset profiles (`configs/asset-profiles/wall.json`) and lower_snake_case for MCP tool names.

## Testing Guidelines

There is no single package-level test runner. Treat the validation scripts above as the required test suite. When changing profile schemas, run `.\scripts\validate_plugin.ps1`; when changing pipeline behavior, run `.\scripts\smoke_app.ps1 -SkipUnityBatch`; when changing installers, add the dry-run and validate-only installer commands. Remove generated `proof/*.json` before submitting.

## Commit & Pull Request Guidelines

Git history currently uses concise prototype-summary subjects, for example `Initial private prototype release`. Prefer short imperative or experimental-prototype summary subjects and keep each commit focused.

Pull requests should describe the change, list exact commands run, call out untested areas, and include screenshots only with secrets removed. Follow `CONTRIBUTING.md`: avoid local paths, usernames, tokens, model files, generated meshes/images, and machine-specific logs.

## Security & Configuration Tips

Never commit secrets, model weights, generated GLB/media assets, local proof reports, installer output, or Unity cache folders. Keep public wording aligned with the experimental prototype, globally untested, no-guarantee status in `README.md`, `SECURITY.md`, and `docs/PUBLICATION_CHECKLIST.md`.
