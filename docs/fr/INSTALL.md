# Installation

## Avant de commencer

Ce projet est un prototype. L'installeur peut cloner des repos officiels, installer des packages Python/npm, utiliser Docker, installer le template Unity et synchroniser le plugin Codex. Il n'y a pas de garantie que tout fonctionne sur votre machine.

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

Si vous ne savez pas quoi choisir, utiliser `--profile cpu` pour valider le plugin sans generation GPU lourde.

## Interface graphique

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
6. Completer les etapes `manual_required`.
7. Cliquer `Install missing allowed items` uniquement si le plan est clair.
8. Cliquer `Validate setup`.

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

Le build Docker Blackwell est lourd. Ne le lancez pas sur une machine limitee sans surveiller RAM, VRAM, CPU et espace disque.

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

Supprimer les preuves JSON locales apres validation si vous preparez un push public :

```powershell
Remove-Item -Force proof\*.json -ErrorAction SilentlyContinue
```
