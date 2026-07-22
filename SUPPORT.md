# Support / Support

This is a solo-maintained experimental prototype that is not broadly tested across machines. Support is best effort only. There is no service-level agreement, no guaranteed response time and no guarantee of any kind, including that installers or GPU workflows work on any given machine.

Ce projet est un prototype experimental maintenu par un seul developpeur, globalement non teste sur la diversite des machines. Le support est fait au mieux. Il n'y a pas de SLA, pas de delai de reponse garanti et aucune garantie, notamment aucune garantie que les installeurs ou workflows GPU fonctionnent sur une machine donnee.

## Open An Issue For

- installer failures;
- missing or confusing setup steps;
- ComfyUI/TRELLIS2 integration problems;
- Unity import/template issues;
- documentation fixes;
- reproducible bugs;
- practical setup tips that may help other users.

## Ouvrir une issue pour

- erreurs d'installation ;
- etapes de setup manquantes ou confuses ;
- problemes d'integration ComfyUI/TRELLIS2 ;
- problemes d'import ou template Unity ;
- corrections de documentation ;
- bugs reproductibles ;
- astuces de setup utiles a d'autres utilisateurs.

## Include In A Bug Report

- OS and target mode: `windows`, `linux`, `wsl` or `docker`;
- profile: `cpu`, `ada`, `blackwell` or `auto`;
- GPU and driver when relevant;
- Python, Node, Docker and Unity versions;
- exact command that failed;
- whether this was dry-run, install, validate-only or runtime generation;
- redacted logs;
- expected result and actual result.

## Inclure dans un rapport de bug

- OS et cible : `windows`, `linux`, `wsl` ou `docker` ;
- profil : `cpu`, `ada`, `blackwell` ou `auto` ;
- GPU et driver si pertinent ;
- versions Python, Node, Docker et Unity ;
- commande exacte qui echoue ;
- mode utilise : dry-run, install, validate-only ou generation runtime ;
- logs rediges ;
- resultat attendu et resultat obtenu.

## Do Not Post

- API keys or tokens;
- Hugging Face tokens;
- Unity credentials;
- personal filesystem paths;
- private project names;
- paid or gated model files;
- generated proprietary assets;
- screenshots containing secrets.

## Ne pas publier

- cles API ou tokens ;
- tokens Hugging Face ;
- identifiants Unity ;
- chemins personnels ;
- noms de projets prives ;
- fichiers de modeles payants ou sous acces restreint ;
- assets proprietaires generes ;
- captures contenant des secrets.

## Before Sharing Logs

Run:

```powershell
.\scripts\scan_private_leaks.ps1
```

Replace local values with placeholders:

- `<INSTALL_ROOT>`
- `<CODEX_HOME>`
- `<PLUGIN_ROOT>`
- `<COMFYUI_ROOT>`
- `<UNITY_PROJECT>`
- `<WORK_DIR>`

## Avant de partager des logs

Lancer :

```powershell
.\scripts\scan_private_leaks.ps1
```

Remplacer les valeurs locales par les placeholders :

- `<INSTALL_ROOT>`
- `<CODEX_HOME>`
- `<PLUGIN_ROOT>`
- `<COMFYUI_ROOT>`
- `<UNITY_PROJECT>`
- `<WORK_DIR>`
