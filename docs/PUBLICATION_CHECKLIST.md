# Public Publication Checklist

Use this checklist before pushing the repository publicly.

## Repository State

- [ ] `git status --short --ignored` has no unexpected tracked changes, generated caches or local config folders.
- [ ] `.gitignore` and `.gitattributes` are present.
- [ ] `LICENSE.md` is present and the license status is intentional.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md` and `SECURITY.md` are present.
- [ ] GitHub issue and pull request templates are present.
- [ ] `README.md` clearly states experimental prototype, solo maintainer, globally/broadly untested and no guarantee of any kind.
- [ ] FR/EN docs are present and aligned.

## Files That Must Not Be Published

- [ ] No tokens, API keys or credentials.
- [ ] No personal filesystem paths or local usernames.
- [ ] No private project names in logs or proof files.
- [ ] No model files.
- [ ] No generated meshes, rendered images or local Unity outputs.
- [ ] No `proof/*.json` local proof reports.
- [ ] No `__pycache__/`, `.pyc` or `.pyo`.
- [ ] No local `.codex/` project config is staged.
- [ ] No Unity `Library/`, `Temp/`, `Logs/`, `UserSettings/`.
- [ ] No local install roots, ComfyUI clones, downloads or cache folders.
- [ ] No generated Windows installer `dist/`, `bin/` or `obj/` folders are committed.

## Required Checks

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\test_runtime_validation.ps1
.\scripts\test_job_safety.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
.\installer\windows\build-installer.ps1
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe --validate-launcher --plugin-root <PLUGIN_ROOT>
```

Linux/WSL check when available:

```bash
./bootstrap/install.sh --help
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

## After Validation

Validation scripts can generate redacted proof JSON in `proof/`. Remove them before public push:

```powershell
Remove-Item -Force proof\*.json -ErrorAction SilentlyContinue
```

Then rerun:

```powershell
.\scripts\scan_private_leaks.ps1
```

## Public Wording

Make sure public pages state:

- solo-maintained experimental prototype,
- globally/broadly untested across machines,
- no guarantee of any kind,
- no stability guarantee,
- no installer reliability guarantee,
- Windows novice users can receive `AssetFactoryInstaller.exe` as an optional experimental convenience artifact, not only raw PowerShell scripts,
- external tools remain owned by their respective projects,
- users are responsible for licenses, model access, generated assets and local machine changes,
- issues, PRs, tips and documentation fixes are welcome.
