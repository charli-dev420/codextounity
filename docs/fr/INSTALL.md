# Installation

## Avant de commencer

Ce projet est un prototype experimental, globalement non teste sur la diversite des machines. L'installeur peut cloner des repos officiels, installer des packages Python/npm, utiliser Docker, installer le template Unity et synchroniser le plugin Codex. Il n'y a aucune garantie que cela fonctionne sur votre machine.

Regle simple :

1. Lancer un `dry-run`.
2. Lire le plan.
3. Faire les etapes manuelles.
4. Installer seulement si vous comprenez ce qui va etre fait.
5. Valider.
6. Ouvrir Codex.

## Prerequis

Minimum conseille :

- Git pour cloner les sources officielles.
- Node.js LTS pour le serveur MCP.
- Python 3.11 ou 3.12 pour les scripts.
- Codex ou l'environnement Codex cible.
- PowerShell 7 pour utiliser le wrapper Linux/WSL complet.

Selon le profil :

- Docker pour le mode runtime/Blackwell.
- Driver NVIDIA et CUDA compatibles pour les generations GPU.
- Unity Hub/Editor et un projet Unity existant pour l'import.
- Acces Hugging Face et acceptation des conditions pour certains modeles.
- Espace disque suffisant pour ComfyUI, modeles et caches.

Si vous ne savez pas quoi choisir, utiliser `--profile cpu` pour valider le plugin sans generation GPU lourde. Le profil CPU peut valider le plugin et les dry-runs, mais une vraie generation TRELLIS2 demande toujours les modeles et le runtime requis par le workflow choisi.

## Installeur Windows (.exe)

Pour un utilisateur Windows novice, `AssetFactoryInstaller.exe` est seulement un point d'entree experimental optionnel. L'utilisateur doit pouvoir double-cliquer l'executable, lancer `Preflight and plan`, lire les composants, verifier les ecritures locales et les etapes manuelles, puis choisir `Install missing allowed items` et `Validate setup`.

Le bouton d'installation reste desactive tant qu'un preflight n'a pas reussi avec les champs actuels. Si la cible, le profil, le fallback, le plugin root, l'install root, le Codex home ou le projet Unity change, il faut relancer le preflight.

Pour construire cet executable depuis le depot :

```powershell
.\installer\windows\build-installer.ps1
```

Executable genere :

```text
installer/windows/dist/AssetFactoryInstaller-win-x64/AssetFactoryInstaller.exe
```

Verification silencieuse de l'executable :

```powershell
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe --validate-launcher --plugin-root <PLUGIN_ROOT>
```

Ne commitez pas `dist/`, `bin/` ou `obj/`. Partagez l'executable comme artefact telechargeable experimental si vous voulez un point d'entree novice.

Windows SmartScreen peut afficher un avertissement parce que cet executable MVP n'est pas signe. Traitez cet avertissement comme normal pour un artefact experimental non signe. Relisez la source, construisez localement si possible, et ne contournez pas l'avertissement sauf si vous acceptez explicitement le risque.

Gate local optionnel :

```powershell
.\installer\windows\test-installer.ps1
```

Le gate construit l'executable, valide le launcher, lance le dry-run et le validate-only, puis supprime les JSON de preuve generes.

## Interface web locale developpeur

Depuis la racine du projet :

```powershell
.\bootstrap\start-ui.ps1
```

Si le navigateur ne s'ouvre pas :

```powershell
.\bootstrap\start-ui.ps1 -NoBrowser
```

Puis ouvrir l'URL affichee dans le terminal.

Dans l'interface :

1. Choisir `Target`.
2. Choisir `Profile`.
3. Renseigner `Install root`, `Codex home` ou `Unity project` seulement si besoin.
4. Cliquer `Preflight and plan`.
5. Lire chaque composant, son statut et sa source officielle.
6. Verifier les ecritures locales et l'etat local.
7. Completer les etapes `manual_required` et `source_review_required`.
8. Cliquer `Install missing allowed items` uniquement si le plan est clair et si la confirmation experimentale est acceptable.
9. Cliquer `Validate setup`.

## CLI Windows

Afficher l'aide :

```powershell
.\bootstrap\install.ps1 --help
```

Parcours recommande :

```powershell
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
.\bootstrap\install.ps1 --target windows --profile auto
.\bootstrap\install.ps1 --validate-only --target windows --profile auto
```

Exemple avec chemins explicites :

```powershell
.\bootstrap\install.ps1 `
  --dry-run `
  --target windows `
  --profile blackwell `
  --install-root "<INSTALL_ROOT>" `
  --codex-home "<CODEX_HOME>" `
  --unity-project "<UNITY_PROJECT>"
```

## CLI Linux / WSL

Afficher l'aide :

```bash
./bootstrap/install.sh --help
```

Linux :

```bash
./bootstrap/install.sh --dry-run --target linux --profile auto
./bootstrap/install.sh --target linux --profile auto
./bootstrap/install.sh --validate-only --target linux --profile auto
```

WSL :

```bash
./bootstrap/install.sh --dry-run --target wsl --profile auto
./bootstrap/install.sh --target wsl --profile auto
./bootstrap/install.sh --validate-only --target wsl --profile auto
```

Le wrapper Linux/WSL utilise PowerShell 7 (`pwsh`) pour partager le meme moteur d'installation. Si `pwsh` manque, le dry-run retourne une action manuelle au lieu d'installer.

## Docker

Verifier la configuration :

```bash
docker compose -f docker/compose.yaml config
```

Validation runtime si l'image existe deja :

```bash
docker compose -f docker/compose.yaml run --rm asset-factory-runtime
```

Demarrer le service ComfyUI inclus et verifier l'endpoint public :

```bash
docker compose -f docker/compose.yaml up asset-factory-comfyui
```

Ouvrir `http://127.0.0.1:8188` ou lire les logs depuis un autre terminal :

```bash
docker compose -f docker/compose.yaml logs -f asset-factory-comfyui
```

Le build Docker Blackwell est lourd. Ne le lancez pas sur une machine limitee sans surveiller RAM, VRAM, CPU et espace disque.
Si l'image runtime manque, lancer d'abord le dry-run et lire l'action image/build prevue avant tout pull ou build.

## Profils

- `auto` detecte la machine et choisit un profil.
- `cpu` valide le plugin, les scripts, les docs, Unity et les dry-runs sans generation GPU lourde.
- `ada` cible une machine NVIDIA CUDA compatible Ada ou proche.
- `blackwell` ajoute un parcours Docker/runtime et des workarounds possibles pour RTX 50 / Blackwell.

## Ce que l'installeur peut faire

Selon le profil et le mode choisi, l'installeur peut :

- verifier `git`, `node`, `npm`, `python`, `codex`, `docker`, `pwsh` ;
- cloner ComfyUI depuis le repo officiel ;
- cloner ComfyUI-Trellis2 depuis le repo officiel ;
- installer PyTorch depuis l'index officiel PyTorch ;
- installer FlashAttention et xformers quand le profil le demande ;
- telecharger les modeles TRELLIS2 via Hugging Face si les droits sont disponibles ;
- installer ou valider le template Unity ;
- installer le package MCP Unity depuis sa source validee ;
- synchroniser le plugin dans les dossiers Codex/agents locaux.

## Etapes manuelles

DINOv3 reste manuel. Ouvrir la page officielle Hugging Face, verifier les conditions, accepter si necessaire, telecharger le modele et le placer dans :

```text
<INSTALL_ROOT>/models/dinov3
```

Ne pas commiter les modeles dans ce repo.

## Unity

Pour preparer Unity :

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot "<UNITY_PROJECT>"
```

Validation sans lancer Unity batch :

```powershell
.\scripts\smoke_app.ps1 -UnityProject "<UNITY_PROJECT>" -SkipUnityBatch
```

`-SkipUnityBatch` signifie que l'import batch Unity complet n'est pas prouve par cette commande.

## Validation avant push public

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
.\scripts\smoke_app.ps1 -SkipUnityBatch
docker compose -f docker\compose.yaml config
```

Avant une vraie premiere generation, verifier que ComfyUI repond sur la meme URL que dans Asset Factory, normalement `http://127.0.0.1:8188`.

Supprimer les preuves JSON locales apres validation si vous preparez un push public :

```powershell
Remove-Item -Force proof\*.json -ErrorAction SilentlyContinue
```
