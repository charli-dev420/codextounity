# Public Publication Checklist

Use this checklist before pushing the repository publicly.

## Repository State

- [ ] `.gitignore` and `.gitattributes` are present.
- [ ] `LICENSE.md` is present and the license status is intentional.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md` and `SECURITY.md` are present.
- [ ] GitHub issue and pull request templates are present.
- [ ] `README.md` clearly states prototype, solo maintainer and no stability guarantee.
- [ ] FR/EN docs are present and aligned.

## Files That Must Not Be Published

- [ ] No tokens, API keys or credentials.
- [ ] No personal filesystem paths or local usernames.
- [ ] No private project names in logs or proof files.
- [ ] No model files.
- [ ] No generated meshes, rendered images or local Unity outputs.
- [ ] No `proof/*.json` local proof reports.
- [ ] No `__pycache__/`, `.pyc` or `.pyo`.
- [ ] No Unity `Library/`, `Temp/`, `Logs/`, `UserSettings/`.
- [ ] No local install roots, ComfyUI clones, downloads or cache folders.

## Required Checks

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
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

- solo-maintained prototype,
- no stability guarantee,
- no installer reliability guarantee,
- external tools remain owned by their respective projects,
- users are responsible for licenses, model access, generated assets and local machine changes,
- issues, PRs, tips and documentation fixes are welcome.
