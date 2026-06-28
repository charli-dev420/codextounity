# Security Policy / Politique securite

This is a prototype maintained by a single developer. There is no formal security SLA. The installer and plugin can run local commands, clone repositories, install packages and interact with Unity. Review commands before running anything outside dry-run mode.

Ce projet est un prototype maintenu par un seul developpeur. Il n'y a pas de SLA securite formel. L'installeur et le plugin peuvent executer des commandes locales, cloner des repos, installer des packages et interagir avec Unity. Relisez les commandes avant de lancer autre chose qu'un dry-run.

## Reporting

If the hosting platform supports private security advisories, use that first. Otherwise, open an issue without posting secrets or exploit-ready details, and state that the report needs a private follow-up.

## Signalement

Si la plateforme d'hebergement permet les advisories privees, utilisez-les en priorite. Sinon, ouvrez une issue sans publier de secret ni de details directement exploitables, et indiquez qu'un suivi prive est necessaire.

## Never Include

- API keys or tokens;
- Hugging Face tokens;
- Unity credentials;
- personal filesystem paths;
- private model files;
- proprietary assets;
- logs containing account names or secrets;
- proof JSON files generated on your machine.

## Ne jamais inclure

- cles API ou tokens ;
- tokens Hugging Face ;
- identifiants Unity ;
- chemins personnels ;
- fichiers de modeles prives ;
- assets proprietaires ;
- logs contenant noms de compte ou secrets ;
- fichiers JSON de preuve generes sur votre machine.

## Local Execution Warning

Before installing or building:

```powershell
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
```

Read the plan. Confirm official sources. Complete manual license/model steps yourself. Do not run heavy GPU or Docker builds on constrained machines without monitoring RAM, VRAM, CPU and disk usage.

## Avertissement execution locale

Avant installation ou build :

```powershell
.\bootstrap\install.ps1 --dry-run --target windows --profile auto
```

Lire le plan. Verifier les sources officielles. Faire vous-meme les etapes manuelles de licence/modeles. Ne pas lancer de builds GPU ou Docker lourds sur une machine limitee sans surveiller RAM, VRAM, CPU et espace disque.

## Public Release Check

Before publishing:

```powershell
.\scripts\scan_private_leaks.ps1
```

The scan must pass and `proof/` should contain only `README.md`.

## Verification avant publication

Avant publication :

```powershell
.\scripts\scan_private_leaks.ps1
```

Le scan doit passer et `proof/` doit contenir uniquement `README.md`.
