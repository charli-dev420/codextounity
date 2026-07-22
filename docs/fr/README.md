# Asset Factory Installer et Codex Unity ComfyUI Pipeline

Ce projet fournit un installeur local autonome, puis un plugin Codex pour piloter un pipeline Unity + ComfyUI/TRELLIS2.

## Statut du projet

Ce depot est un prototype experimental maintenu par un seul developpeur, globalement non teste sur la diversite des machines.

- Aucune garantie, de quelque nature que ce soit.
- Aucune promesse de stabilite.
- Aucune promesse que les installeurs fonctionnent sur toutes les machines.
- Support au mieux, sans SLA.
- Les setups GPU, Docker, WSL, Unity, modeles et nodes peuvent demander des corrections manuelles.
- Issues, PR, retours d'installation, astuces et corrections de documentation sont bienvenus.

Toujours commencer par un `dry-run`. Lire le plan d'installation avant de lancer des telechargements ou ecritures locales.

## Ordre recommande

1. Lancer l'installeur avant Codex.
2. Verifier la machine et les dependances.
3. Lire les sources officielles et les etapes manuelles.
4. Installer uniquement ce qui manque et ce qui est autorise.
5. Faire les etapes manuelles, notamment DINOv3 si le workflow le demande.
6. Valider le setup.
7. Ouvrir Codex et utiliser l'app Asset Factory.

Codex reste le maitre de decision sous la direction de l'utilisateur. ComfyUI et TRELLIS2 sont des moteurs locaux de generation. Le traitement apres generation, la normalisation, les pivots, l'echelle, les manifests Unity et l'import sont controles par Codex et/ou l'utilisateur.

## Demarrage rapide

Executable Windows experimental :

```powershell
.\installer\windows\build-installer.ps1
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe
```

Interface web locale developpeur :

```powershell
.\bootstrap\start-ui.ps1
```

CLI Windows :

```powershell
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
```

CLI Linux/WSL :

```bash
./bootstrap/install.sh --help
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --target linux --profile auto
./bootstrap/install.sh --dry-run --target wsl --profile auto
./bootstrap/install.sh --target wsl --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

## Documentation

- Installation complete : `docs/fr/INSTALL.md`
- Guide utilisateur : `docs/fr/USER_GUIDE.md`
- Architecture et orchestration : `docs/fr/ARCHITECTURE.md`
- Depannage : `docs/fr/TROUBLESHOOTING.md`
- Credits et avertissement : `docs/fr/CREDITS_AND_DISCLAIMER.md`
- Contribution : `CONTRIBUTING.md`
- Support : `SUPPORT.md`
- Securite : `SECURITY.md`

## Verification avant partage

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

Ne pas publier de tokens, chemins personnels, noms de projets prives, logs bruts, preuves JSON locales, assets generes lourds, modeles, caches Python ou dossiers Unity generes.

## Placeholders

Les exemples utilisent uniquement :

- `<INSTALL_ROOT>`
- `<CODEX_HOME>`
- `<PLUGIN_ROOT>`
- `<COMFYUI_ROOT>`
- `<UNITY_PROJECT>`
- `<WORK_DIR>`
