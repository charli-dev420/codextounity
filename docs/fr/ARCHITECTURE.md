# Architecture et orchestration

## Objectif

Codex Unity ComfyUI Pipeline est un prototype local experimental, globalement non teste sur la diversite des machines. Il sert a coordonner un pipeline d'assets 3D pour Unity sans transformer ComfyUI ou Unity en centre de decision.

Le principe est volontairement simple :

```text
Utilisateur
  -> Codex
  -> Asset Factory MCP
  -> ComfyUI / TRELLIS2
  -> scripts de post-traitement
  -> Unity
```

Codex reste responsable des decisions sous les consignes utilisateur. ComfyUI est un moteur de generation local. Unity consomme les assets prepares.

## Composants

| Composant | Role |
| --- | --- |
| `bootstrap/` | Installeur amont a lancer avant Codex. Produit un plan, installe ce qui est autorise et valide le setup. |
| `mcp/server.mjs` | Serveur MCP du plugin. Expose les outils et le widget Asset Factory a Codex. |
| `mcp/asset-factory-widget.html` | Interface locale de pilotage : asset, reference image, generation, review, import Unity, sockets. |
| `scripts/` | Scripts Python/PowerShell de generation, validation, normalisation, import Unity et maintenance. |
| `configs/asset-profiles/` | Profils d'assets reutilisables : wall, door, prop, weapon, character, etc. |
| `configs/install-profiles/` | Profils d'installation : cpu, ada, blackwell. |
| `docker/` | Runtime optionnel pour le setup lourd, surtout Blackwell. |
| `unity/Assets/AIAssetPipeline/` | Template Unity Editor installe dans un projet Unity cible. |
| `skills/` | Instructions Codex pour utiliser le plugin proprement. |

## Orchestration d'un asset

1. `plan_asset` choisit un profil, des bounds, un budget faces/textures et des regles de reference.
2. `plan_reference_image` prepare une consigne d'image de reference.
3. `register_reference_image` copie ou enregistre l'image dans le dossier de travail.
4. `validate_reference_image` verifie le format et les contraintes minimales.
5. `start_asset_pipeline_job` cree un job persistant dans `.codex_asset_jobs`.
6. ComfyUI/TRELLIS2 genere les outputs 3D.
7. Les scripts Codex inventorient, selectionnent et normalisent les fichiers.
8. `adjust_generated_asset` corrige scale, pivot, rotation, offset ou bounds sans relancer la generation.
9. `import_asset_to_unity` prepare le manifest et les fichiers Unity-ready.
10. Unity importe le manifest via le template Editor.

## Etats de job

| Etat | Signification |
| --- | --- |
| `planned` | Job prepare, aucune operation longue lancee. |
| `reference_ready` | Image de reference validee. |
| `queued` | Job pret a demarrer. |
| `generating` | Generation locale en cours. |
| `generated` | Mesh ou artefacts de generation presents. |
| `review_needed` | Intervention utilisateur ou Codex requise. |
| `adjusted` | Mesh corrige apres generation. |
| `unity_ready` | Pret pour import Unity. |
| `imported` | Import termine. |
| `failed` | Echec a diagnostiquer dans les logs. |
| `cancelled` | Job annule. |

## Donnees persistantes

Les jobs sont stockes dans :

```text
<WORK_DIR>/.codex_asset_jobs/<job_id>/
```

Chaque job peut contenir :

- `job.json`
- `events.jsonl`
- `instructions.jsonl`
- `stdout.log`
- `stderr.log`
- `artifacts.json`

Ces fichiers sont utiles pour reprendre ou diagnostiquer un job, mais ils ne doivent pas etre publies dans un repo public.

## Limites connues

- Ce projet est un prototype experimental globalement non teste.
- Aucune garantie n'est fournie.
- Les installeurs ne sont pas garantis sur toutes les machines.
- Les generations GPU dependent fortement des versions CUDA, PyTorch, drivers, nodes ComfyUI et modeles.
- Le mode `-SkipUnityBatch` ne prouve pas un import Unity batch complet.
- Les assets generes doivent toujours etre controles humainement avant usage.

## Regles de conception

- Codex decide, ComfyUI genere, Unity consomme.
- Les dimensions finales sont imposees apres generation.
- Les chemins locaux restent hors repo public.
- Les modeles et dependances lourdes ne sont pas vendus ni redistribues par ce projet.
- Les etapes manuelles liees aux licences et aux modeles restent visibles.
