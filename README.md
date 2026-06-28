# Codex Unity ComfyUI Pipeline

## Francais

Prototype local d'installeur et de plugin Codex pour generer, controler, normaliser et importer des assets Unity. Codex reste la couche de decision dirigee par l'utilisateur. ComfyUI et TRELLIS2 restent des moteurs locaux de generation.

### Statut du projet

Ce depot est maintenu par un seul developpeur et reste un prototype.

- Aucune promesse de stabilite.
- Aucune promesse que les installeurs fonctionnent sur toutes les machines.
- Aucun SLA de support.
- Aucune garantie que GPU, Docker, WSL, Unity ou les modeles fonctionneront sans correction manuelle.
- Issues, pull requests, retours d'installation, astuces et corrections de documentation sont bienvenus.

Lancez toujours un dry-run avant une installation reelle. Lisez le plan d'installation avant d'autoriser des telechargements ou des ecritures locales.

### Ce que fait le projet

- Verifie la machine avant l'ouverture de Codex.
- Prepare l'installation Windows, Linux, WSL et Docker.
- Utilise les sources officielles pour les outils externes lorsque l'automatisation est possible.
- Signale clairement les etapes manuelles, notamment les modeles soumis a licence ou acces controle.
- Installe ou synchronise le plugin Codex et le serveur MCP.
- Expose l'application Asset Factory dans Codex.
- Aide Codex a planifier les images de reference, lancer les jobs ComfyUI/TRELLIS2, suivre les jobs persistants, normaliser les GLB, preparer les manifests Unity et gerer les sockets d'attache personnage.

### Demarrage rapide

Interface d'installation :

```powershell
.\bootstrap\start-ui.ps1
```

Windows PowerShell :

```powershell
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
```

Linux / WSL :

```bash
./bootstrap/install.sh --help
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --target linux --profile auto
./bootstrap/install.sh --dry-run --target wsl --profile auto
./bootstrap/install.sh --target wsl --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

Validation Docker :

```powershell
docker compose -f docker\compose.yaml config
```

```bash
docker compose -f docker/compose.yaml config
```

### Verification avant publication

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

Ne publiez pas de tokens, secrets, chemins personnels, fichiers de modeles, meshes/images generes, preuves JSON locales, dossiers Unity `Library/`, caches Python ou sorties d'installeur. Le `.gitignore` couvre ces cas, mais la revue manuelle reste obligatoire.

## English

Local prototype installer and Codex plugin for generating, reviewing, normalizing and importing Unity assets. Codex remains the user-directed decision layer. ComfyUI and TRELLIS2 remain local generation engines.

### Project Status

This repository is maintained by a single developer and is currently a prototype.

- No stability guarantee.
- No promise that installers work on every machine.
- No support SLA.
- No guarantee that GPU, Docker, WSL, Unity or model setup will work without manual fixes.
- Issues, pull requests, setup feedback, setup tips and documentation improvements are welcome.

Always run dry-runs first. Read the installer plan before allowing downloads or local writes.

### What This Project Does

- Checks a local machine before Codex is opened.
- Plans installation for Windows, Linux, WSL and Docker targets.
- Uses official sources for external tools where automation is possible.
- Keeps license-gated or manually restricted model steps explicit.
- Installs or syncs the Codex plugin and MCP server.
- Exposes the Asset Factory app in Codex.
- Helps Codex plan reference images, run ComfyUI/TRELLIS2 jobs, monitor persistent jobs, normalize GLB bounds/pivot/rotation/scale, prepare Unity manifests and manage character attachment sockets.

### Quick Start

Installer UI:

```powershell
.\bootstrap\start-ui.ps1
```

Windows PowerShell:

```powershell
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
```

Linux / WSL:

```bash
./bootstrap/install.sh --help
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --target linux --profile auto
./bootstrap/install.sh --dry-run --target wsl --profile auto
./bootstrap/install.sh --target wsl --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

Docker validation:

```powershell
docker compose -f docker\compose.yaml config
```

```bash
docker compose -f docker/compose.yaml config
```

### Public Repo Checks

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

Do not publish tokens, secrets, personal paths, model files, generated meshes/images, local proof JSON, Unity `Library/`, Python caches or installer output folders. The `.gitignore` covers these cases, but manual review is still required.

## Documentation

- Francais : `docs/fr/README.md`
- English: `docs/en/README.md`
- Installation FR: `docs/fr/INSTALL.md`
- Installation EN: `docs/en/INSTALL.md`
- Guide utilisateur FR: `docs/fr/USER_GUIDE.md`
- User guide EN: `docs/en/USER_GUIDE.md`
- Architecture: `docs/fr/ARCHITECTURE.md` and `docs/en/ARCHITECTURE.md`
- Credits and disclaimer: `docs/fr/CREDITS_AND_DISCLAIMER.md` and `docs/en/CREDITS_AND_DISCLAIMER.md`
- Troubleshooting: `docs/fr/TROUBLESHOOTING.md` and `docs/en/TROUBLESHOOTING.md`
- Contributions: `CONTRIBUTING.md`
- Support: `SUPPORT.md`
- Security: `SECURITY.md`

## License Status / Statut de licence

This repository is currently published as an unlicensed prototype. See `LICENSE.md`. External tools, models and brands keep their own licenses and terms.

Ce depot est actuellement publie comme prototype sans licence open source. Voir `LICENSE.md`. Les outils externes, modeles et marques conservent leurs licences et conditions propres.
