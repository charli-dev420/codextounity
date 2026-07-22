# Depannage

## Methode generale

1. Reproduire le probleme avec la commande la plus courte possible.
2. Relancer en `--dry-run` si c'est un probleme d'installation.
3. Copier uniquement des logs rediges.
4. Retirer tokens, chemins personnels, noms de projets prives et captures sensibles.
5. Indiquer OS, profil, GPU, Python, Node, Docker, Unity et version du plugin.

Commande de verification de base :

```powershell
.\scripts\scan_private_leaks.ps1
.\scripts\validate_plugin.ps1
```

## L'installeur ne s'ouvre pas

Symptomes :

- `AssetFactoryInstaller.exe` ne demarre pas ;
- l'executable ne trouve pas `bootstrap\install.ps1` ;
- l'executable n'a pas encore ete construit ;
- la fenetre navigateur de fallback ne s'ouvre pas ;
- PowerShell bloque le fallback script ;
- le port local semble deja utilise.

Actions :

```powershell
.\installer\windows\build-installer.ps1
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe --validate-launcher --plugin-root <PLUGIN_ROOT>
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe
```

Fallback developpeur :

```powershell
.\bootstrap\start-ui.ps1 -NoBrowser
```

Puis ouvrir l'URL affichee dans le terminal.

Verifier aussi :

```powershell
.\bootstrap\install.ps1 --help
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
```

## `install.sh` demande PowerShell 7

Le wrapper Linux/WSL utilise `pwsh` pour partager le meme moteur que Windows.

Actions :

1. Installer PowerShell 7 depuis la documentation Microsoft officielle.
2. Relancer :

```bash
./bootstrap/install.sh --dry-run --target linux --profile auto
```

Si `pwsh` manque, le dry-run doit retourner une action `manual_required` sans installer.

## Codex ne voit pas le plugin

Actions :

1. Fermer Codex.
2. Verifier le plugin :

```powershell
.\scripts\validate_plugin.ps1
```

3. Synchroniser localement si vous developpez ce plugin :

```powershell
.\scripts\sync_plugin_install.ps1 -DryRun
.\scripts\sync_plugin_install.ps1
```

4. Redemarrer Codex.

Note : `sync_plugin_install.ps1` est surtout un outil mainteneur/local. Il copie dans les dossiers Codex/agents locaux.

## `tools/list` ne montre pas les outils attendus

Verifier :

```powershell
node --check .\mcp\server.mjs
.\scripts\validate_plugin.ps1
```

Etat attendu : `Tools: 19`.

Si ce n'est pas le cas, joindre :

- sortie de `validate_plugin.ps1`,
- version du plugin,
- contenu redige du manifest `.codex-plugin/plugin.json`.

## ComfyUI ne repond pas

Verifier :

- ComfyUI est lance ;
- le port correspond au champ `ComfyUI server` ;
- aucun firewall ne bloque le port local ;
- le workflow choisi existe.

Commande typique :

```powershell
.\scripts\run_trellis2_assets.ps1 -InputDir "<WORK_DIR>\references" -OutputDir "<WORK_DIR>\out" -DryRun -Limit 1
```

Avec Docker, demarrer le service et verifier le port `8188` :

```bash
docker compose -f docker/compose.yaml up asset-factory-comfyui
docker compose -f docker/compose.yaml logs -f asset-factory-comfyui
```

Si Docker affiche un avertissement d'acces a son fichier de config local, corriger d'abord les permissions Docker Desktop/config. C'est un probleme machine, pas un echec du code plugin.

## TRELLIS2 ne renvoie pas de GLB

Verifier :

- image de reference lisible ;
- modele TRELLIS2 present ;
- DINOv3 present si le workflow le demande ;
- imports Python sans erreur ;
- logs ComfyUI ;
- VRAM suffisante ;
- compatibilite FlashAttention/xformers.

Action recommandee :

1. Tester avec un seul asset.
2. Baisser les options lourdes.
3. Lancer le pipeline en dry-run.
4. Joindre les logs ComfyUI rediges si l'erreur persiste.

## FlashAttention echoue

FlashAttention depend de PyTorch, CUDA, Python, GPU et wheels disponibles.

Actions :

- verifier le profil choisi (`ada`, `blackwell`, `cpu`) ;
- verifier PyTorch/CUDA ;
- utiliser un wheel officiel compatible si disponible ;
- compiler uniquement depuis la source officielle si vous savez le faire ;
- continuer sans FlashAttention si le workflow le permet.

## DINOv3 absent

C'est normal tant que l'etape manuelle n'a pas ete faite.

Action :

1. Ouvrir la page Hugging Face officielle.
2. Lire et accepter les conditions si necessaire.
3. Telecharger manuellement.
4. Placer le modele dans :

```text
<INSTALL_ROOT>/models/dinov3
```

Ne jamais commiter le modele.

## Unity ne compile pas

Verifier :

- le template est dans `<UNITY_PROJECT>/Assets/AIAssetPipeline` ;
- Unity a fini de compiler ;
- la Console Unity ne contient pas d'erreurs `AIAssetPipeline` ;
- le package MCP Unity est installe si vous voulez piloter Unity via MCP.

Reinstaller le template :

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot "<UNITY_PROJECT>"
```

## Le smoke utilise `-SkipUnityBatch`

`-SkipUnityBatch` valide le plugin sans lancer Unity en batchmode. Cela ne prouve pas un import Unity complet dans un vrai projet.

Pour une preuve Unity complete, il faut fournir :

- chemin `<UNITY_PROJECT>` valide ;
- executable Unity disponible ;
- logs Unity batch rediges ;
- absence d'erreurs Console.

## Fuite de chemin local ou secret

Avant partage :

```powershell
.\scripts\scan_private_leaks.ps1
```

Le scan doit etre vert. Sinon remplacer les valeurs par :

- `<INSTALL_ROOT>`
- `<CODEX_HOME>`
- `<PLUGIN_ROOT>`
- `<COMFYUI_ROOT>`
- `<UNITY_PROJECT>`
- `<WORK_DIR>`
