# Roadmap de completion du pipeline

Ce document decrit la poursuite du depot comme prototype experimental, globalement non teste sur la diversite des machines et fourni sans aucune garantie. Il ne transforme pas le projet en release candidate, produit certifie, installeur stable ou pipeline de production.

L'objectif n'est pas d'ajouter des promesses, mais de rendre le pipeline completement demontrable sur une machine connue : selection des images, generation, multiview, mesh texture, normalisation sans deformation, validation GLB, import Unity propre, scene de demo, captures et preuve locale reproductible.

## Principes non negociables

- Codex reste l'orchestrateur et le validateur ; ComfyUI reste un moteur local de generation.
- Aucun modele, asset genere, image de preuve, GLB, log brut ou chemin personnel ne doit etre publie.
- La normalisation ne doit jamais deformer les proportions : scale uniforme uniquement.
- Chaque etape lourde doit etre reprise asset par asset, avec logs, statuts JSON et resume final.
- Les decisions d'asset doivent etre explicites : dimensions, fit axis, pivot, placement Unity et profil.
- Les preuves completes restent sous `.codex/` ou hors repo ; `proof/` public garde seulement `README.md`.
- Les workflows externes restent soumis aux licences, comptes, modeles et preconditions locales de l'utilisateur.

## Etat actuel du depot

Le depot contient deja les surfaces principales :

- plugin MCP et widget Asset Factory ;
- profils d'assets et validation de profils ;
- selection room-demo avec planches contact ;
- runner TRELLIS2 robuste asset par asset ;
- normalisation preserve-aspect ;
- validation runtime GLB v2 ;
- projet Unity sandbox et scene builder dedie ;
- proof pack local avec captures et hashes ;
- installeur Windows experimental ;
- scan anti-fuite et gates non lourds.

Les zones encore incompletes sont :

- absence de gate end-to-end unique A-F/G rejouable ;
- absence de vraie chaine Hunyuan multiview vers TRELLIS textured mesh ;
- validation texture/material/UV encore insuffisante ;
- controls utilisateur de normalisation encore trop disperses ;
- preuve complete 7-20 assets non encore stabilisee ;
- UX installateur non encore reliee au parcours room-demo complet.

## Definition de "pipeline complet"

Un pipeline est considere complet uniquement quand une commande unique peut produire un proof pack `complete` a partir d'un dossier d'images room-ready :

```powershell
.\scripts\test_room_demo_pipeline.ps1 `
  -FullGeneration `
  -ImageDir <room-images> `
  -Server http://127.0.0.1:8000 `
  -ProjectRoot <UNITY_SANDBOX_PROJECT> `
  -MinAssets 7
```

Le proof pack doit contenir :

- images source utilisees ;
- planche de selection ;
- multiviews Hunyuan par asset quand ce mode est active ;
- GLB textured mesh ;
- rapports runtime par asset ;
- normalisation report par asset ;
- hashes SHA256 ;
- manifests Unity ;
- scene Unity propre ;
- prefab root ;
- `captures/unity_import.png` ;
- `captures/clean_scene.png` ;
- `ROOM_DEMO_PROOF.md` ;
- `ROOM_DEMO_PROOF.json` avec `status: complete`.

## Phase 0 - Hygiene continue

Objectif : garder le depot publiable pendant les travaux.

Actions :

- Nettoyer tout `__pycache__/`, `.pyc`, `.pyo`, proof JSON, GLB, image ou log brut avant chaque statut final.
- Relancer `.\scripts\scan_private_leaks.ps1 -Root . -Json`.
- Relancer `git diff --check`.
- Verifier `git ls-files -ci --exclude-standard`.
- Verifier que `proof/` contient seulement `README.md`.

Criteres d'acceptation :

- scan anti-fuite vert ;
- aucun fichier ignore suivi ;
- aucun artefact local dans `proof/` ;
- docs publiques toujours coherentes : prototype experimental, globalement non teste, aucune garantie.

## Phase G - Gate end-to-end room-demo

Objectif : ajouter un orchestrateur unique pour rejouer A-F sans deviner les chemins.

Nouveau CLI :

```powershell
.\scripts\test_room_demo_pipeline.ps1 `
  -BatchProofDir <existing-batch> `
  -SkipGeneration `
  -MinAssets 7
```

```powershell
.\scripts\test_room_demo_pipeline.ps1 `
  -ImageDir <images> `
  -Server http://127.0.0.1:8000 `
  -FullGeneration `
  -ProjectRoot <UNITY_SANDBOX_PROJECT> `
  -MinAssets 7
```

Options attendues :

- `-PlanDir`, `-SelectedReferences`, `-GlbDir`, `-OutputDir`;
- `-SkipGeneration`, `-SkipUnity`, `-SkipProof`;
- `-UseMultiview`, `-UseTexturedMesh`;
- `-StartAt`, `-Limit`, `-AssetName`, `-RetryFailed`, `-Force`;
- `-KeepWorkDir`, `-DryRun`.

Sorties :

- `pipeline_status.json` schema `codex.roomDemoPipelineGate.v1`;
- `pipeline_summary.md`;
- liens vers plan A, batch generation, normalisation, validations, Unity et proof pack.

Acceptance :

- mode `-SkipGeneration` passe avec des GLB existants ;
- mode dry-run liste chaque etape sans creer d'artefact lourd ;
- echec si moins de `-MinAssets` assets valides ;
- echec si proof pack manque captures ou scene Unity quand Unity n'est pas skippee.

## Phase H - Decisions d'asset explicites

Objectif : exposer les controles de normalisation et placement avant generation lourde.

Nouveau fichier :

```text
asset_decisions.json
```

Schema minimal :

```json
{
  "schema": "codex.roomDemoAssetDecisions.v1",
  "assets": [
    {
      "assetName": "01_table",
      "profile": "prop",
      "subProfile": "",
      "role": "furniture",
      "targetBounds": { "x": 1.2, "y": 0.8, "z": 0.9 },
      "fitAxis": "contain",
      "pivot": "bottom-center",
      "allowNonUniformScale": false,
      "unityPlacement": {
        "position": { "x": 0, "y": 0, "z": 0 },
        "rotationEuler": { "x": 0, "y": 0, "z": 0 },
        "uniformScale": 1.0
      }
    }
  ]
}
```

Nouveaux scripts :

- `scripts/create_asset_decisions.py`;
- `scripts/validate_asset_decisions.py`;
- `scripts/apply_asset_decisions.py`.

Acceptance :

- tout asset a `targetBounds`, `fitAxis`, `pivot`, `profile`, `role`, `unityPlacement`;
- `allowNonUniformScale` doit etre `false`;
- les decisions sont reprises par normalisation, validation runtime et scene Unity ;
- le gate echoue si une decision contredit le profil.

## Phase I - Generation Hunyuan multiview

Objectif : ajouter une etape de generation multiview controlee avant le mesh texture.

Nouveaux fichiers :

- `workflows/hunyuan_multiview.api.json`;
- `scripts/hunyuan_multiview_batch.py`;
- `scripts/run_hunyuan_multiview_batch.ps1`;
- `scripts/validate_multiview_set.py`;
- `scripts/test_multiview_planning.ps1`.

Interface :

```powershell
.\scripts\run_hunyuan_multiview_batch.ps1 `
  -SelectedReferences <plan>\selected_references.json `
  -OutputDir <workdir>\multiview `
  -Server http://127.0.0.1:8000
```

Sorties par asset :

```text
multiview\<assetName>\
  front.png
  back.png
  left.png
  right.png
  multiview_manifest.json
  stdout.log
  stderr.log
```

Manifest :

```json
{
  "schema": "codex.multiviewReferences.v1",
  "assetName": "01_table",
  "profile": "prop",
  "sourceImage": "...",
  "sourceImageSha256": "...",
  "views": {
    "front": "...",
    "back": "...",
    "left": "...",
    "right": "..."
  },
  "seed": 1234,
  "cameraConvention": "front-back-left-right"
}
```

Validation :

- 4 vues minimum ;
- dimensions coherentes ;
- fichiers non vides ;
- meme asset et meme role sur toutes les vues ;
- refus des vues avec personnage, texte, scene complete ou multi-objet manifeste ;
- resume `summary_hunyuan_multiview_batch.json`.

Acceptance :

- reprise possible asset par asset ;
- `-RetryFailed` relance seulement les assets en erreur ;
- `-DryRun` valide le plan sans appeler ComfyUI ;
- aucune multiview n'est commitee.

## Phase J - TRELLIS textured mesh depuis multiview

Objectif : produire un mesh texture a partir des multiviews plutot qu'un mesh brut depuis une seule image.

Nouveaux fichiers :

- `workflows/trellis_texturedmesh_multiview.api.json`;
- `scripts/trellis_textured_mesh_batch.py`;
- `scripts/run_trellis_textured_mesh_batch.ps1`;
- `scripts/test_textured_mesh_batch.ps1`.

Interface :

```powershell
.\scripts\run_trellis_textured_mesh_batch.ps1 `
  -MultiviewDir <workdir>\multiview `
  -SelectedReferences <plan>\selected_references.json `
  -OutputDir <workdir>\texturedmesh `
  -Server http://127.0.0.1:8000
```

Sorties :

```text
texturedmesh\raw\<assetName>.glb
texturedmesh\logs\<assetName>.stdout.log
texturedmesh\logs\<assetName>.stderr.log
texturedmesh\status\<assetName>.json
texturedmesh\summary_textured_mesh_batch.json
```

Regles :

- le runner reste foreground, jamais process cache ;
- skip si GLB textured mesh non vide existe deja ;
- echec si history ComfyUI ne fournit aucun mesh cible ;
- echec si GLB sans material/texture quand le workflow annonce textured mesh ;
- distinguer `history_without_files`, `missing_local_output`, `empty_mesh_file`, `missing_texture`, `invalid_material`.

Acceptance :

- dry-run sur fixture multiview ;
- tests avec GLB existant, GLB vide, status failed, retry et force ;
- sortie non zero si un asset attendu ne produit pas de mesh texture.

## Phase K - Normalisation et postprocess unifies

Objectif : appliquer les decisions d'asset et garantir l'invariant sans deformation.

Changements :

- `postprocess_generation.py` accepte `--asset-decisions`;
- `normalize_asset_bounds.py` ecrit toujours `proportionsPreserved: true|false`;
- refus dur de tout scale non uniforme ;
- `targetBounds` reste une enveloppe max, jamais une cible de stretch XYZ ;
- `fitAxis` vient du profil, du sous-profil ou de `asset_decisions.json`.

Acceptance :

- test positif sur `floor`, `wall`, `door`, `window_wall`, `wall_mirror`, `prop`;
- test negatif `scale 1,2,1`;
- test negatif fit axis qui deborde l'enveloppe ;
- validation runtime refuse un rapport sans `proportionsPreserved: true`.

## Phase L - Validation runtime GLB v3

Objectif : valider geometriquement et techniquement un asset texture utilisable.

Extension de `validate_runtime_asset.py` :

- schema `codex.runtimeAssetValidation.v3`;
- verification materials ;
- verification textures ;
- verification UV ;
- texture max par profil ;
- triangle budget ;
- bounds enveloppe ;
- pivot ;
- mesh nodes ;
- primitives ;
- dimensions degeneres ;
- coherence role/profil/nom ;
- presence et validite du rapport multiview si fourni.

Nouvelle interface :

```powershell
python -B .\scripts\validate_runtime_asset.py `
  --mesh <asset.glb> `
  --profile prop `
  --asset-name 01_table `
  --normalization-report <report.json> `
  --multiview-manifest <manifest.json> `
  --json
```

Acceptance :

- fixtures GLB avec material/texture/UV valides ;
- cas negatifs : texture absente, UV absents, material absent, texture trop grande, role incompatible ;
- rapport v3 exploitable par le proof pack.

## Phase M - Unity scene room-demo complete

Objectif : produire une scene de demo acceptable, pas seulement importer des prefabs.

Extensions Unity :

- ameliorer `CodexRoomDemoSceneBuilder.cs`;
- ajouter placement par role depuis `asset_decisions.json`;
- verifier que chaque prefab importe est un `GameObject`;
- creer sol neutre, murs, porte, fenetre, mobilier, decor ;
- cadrage camera base sur bounds globales ;
- lumiere directionnelle et ambient ;
- prefab root stable ;
- rapport avec objets rendus, manquants, warnings et erreurs.

Acceptance :

- au moins `MinAssets` instances presentes dans la scene ;
- captures non vides ;
- prefab root cree ;
- scene lisible sans dependance au projet Unity ouvert par l'utilisateur ;
- echec clair si glTFast, Unity ou import GLB manque.

## Phase N - Proof pack complet

Objectif : passer de preuve partielle a preuve complete pour un batch reel.

Extensions `build_room_demo_proof.ps1` :

- inclure multiviews ;
- inclure `asset_decisions.json`;
- inclure rapports v3 ;
- inclure version du workflow utilise ;
- inclure version du package glTFast ;
- inclure table des assets valides, en revue, echoues ;
- declarer `status: complete` seulement si toutes les preuves obligatoires existent.

Acceptance :

- `ROOM_DEMO_PROOF.json` schema `codex.roomDemoProofPack.v2`;
- `ROOM_DEMO_PROOF.md` lisible novice ;
- hashes SHA256 pour images, multiviews, GLB, captures, rapports ;
- echec si capture Unity absente ;
- echec si moins de `MinAssets` runtime-valid.

## Phase O - UX installeur et widget

Objectif : rendre le parcours complet utilisable par un novice sans cacher la complexite.

Installeur Windows :

- onglet `Room demo proof`;
- selection dossier images ;
- selection dossier de sortie local ignore ;
- preflight ComfyUI, Hunyuan, TRELLIS, Unity, glTFast ;
- panneau "Local writes" ;
- bouton generation desactive tant que preflight invalide ;
- confirmation experimentale obligatoire ;
- ouverture du proof pack final.

Widget MCP :

- afficher et editer les decisions d'asset ;
- afficher etapes manuelles requises ;
- afficher statuts multiview/textured mesh/validation/proof ;
- boutons de copie des chemins et commandes ;
- aucun lancement lourd sans action explicite.

Acceptance :

- aucun process cache ;
- logs visibles ;
- erreurs novice lisibles ;
- pas de promesse de support ou garantie.

## Phase P - Documentation issue de runs reels

Objectif : transformer les preuves en documentation exploitable.

Docs a mettre a jour :

- `docs/fr/USER_GUIDE.md`;
- `docs/en/USER_GUIDE.md`;
- `docs/fr/TROUBLESHOOTING.md`;
- `docs/en/TROUBLESHOOTING.md`;
- `workflows/README_TRELLIS2_COMFYUI.md`;
- `skills/unity-comfyui-pipeline/SKILL.md`;
- `docs/PUBLICATION_CHECKLIST.md`.

Contenu attendu :

- recette ComfyUI `127.0.0.1:8000` et `8188`;
- recette Hunyuan multiview ;
- recette TRELLIS textured mesh ;
- preconditions modeles/nodes ;
- limites VRAM ;
- erreurs connues ;
- statut "teste localement / non teste / manuel".

Acceptance :

- docs FR/EN alignees ;
- aucun chemin personnel ;
- aucun modele ni asset publie ;
- limitations explicites.

## Phase Q - Batches dataset et reprise longue

Objectif : reutiliser l'experience des batchs dataset pour rendre les longues generations controlables.

Actions :

- support `GroupSize`, `PauseSeconds`, `StartGroup`, `LimitGroups`;
- statut `run_state.json`;
- publication locale par categorie et asset ;
- resumes par groupe ;
- stop propre a frontiere de groupe ;
- reprise sans regenerer les assets publies ;
- verification `/queue` ComfyUI comme source rapide d'activite.

Acceptance :

- dry-run imprime le plan de publication final ;
- reprise groupe 2-N sans toucher au groupe 1 ;
- aucun asset partiel presente comme valide ;
- layouts publics et techniques separes.

## Ordre conseille

1. Phase 0 : nettoyer hygiene locale.
2. Phase G : gate end-to-end avec `-SkipGeneration`.
3. Phase H : decisions d'asset explicites.
4. Phase I : Hunyuan multiview dry-run puis live `Limit 1`.
5. Phase J : TRELLIS textured mesh dry-run puis live `Limit 1`.
6. Phase K : normalisation appliquee aux decisions.
7. Phase L : validation runtime v3.
8. Phase M : scene Unity complete.
9. Phase N : proof pack v2 complet.
10. Phase O : UX installeur/widget.
11. Phase P : documentation issue de runs reels.
12. Phase Q : batches longs et reprise dataset.

## Gates de validation

Gates non lourds :

```powershell
python -B -m py_compile .\scripts\*.py
.\scripts\test_room_demo_planning.ps1
.\scripts\test_room_demo_batch.ps1
.\scripts\test_room_demo_proof.ps1
.\scripts\test_runtime_validation.ps1
.\scripts\test_normalization_invariants.ps1
.\scripts\test_job_safety.ps1
.\scripts\validate_plugin.ps1
.\scripts\scan_private_leaks.ps1 -Root . -Json
git diff --check
git ls-files -ci --exclude-standard
```

Gates lourds manuels :

```powershell
.\scripts\run_hunyuan_multiview_batch.ps1 -SelectedReferences <plan> -OutputDir <out> -Server http://127.0.0.1:8000 -Limit 1
.\scripts\run_trellis_textured_mesh_batch.ps1 -MultiviewDir <out>\multiview -SelectedReferences <plan> -OutputDir <out>\texturedmesh -Server http://127.0.0.1:8000 -Limit 1
.\scripts\test_room_demo_pipeline.ps1 -FullGeneration -ImageDir <images> -Server http://127.0.0.1:8000 -MinAssets 7
```

## Stop rules

Arreter la progression et corriger avant de passer a la phase suivante si :

- un asset est normalise avec scale non uniforme ;
- un GLB sans material/texture est presente comme textured mesh valide ;
- une scene Unity est generee sans `MinAssets` valides ;
- un proof pack `complete` manque une capture ;
- un fichier sous `proof/` autre que `README.md` reapparait ;
- un modele, GLB, image ou log brut devient suivi par git ;
- une etape lourde tourne en process cache ou impossible a interrompre.

## Non-objectifs

- Pas de garantie de compatibilite multi-machines.
- Pas de support commercial implicite.
- Pas de distribution de modeles.
- Pas de publication d'assets generes.
- Pas de signature code obligatoire a ce stade.
- Pas de MSI/NSIS obligatoire.
- Pas de promesse de qualite artistique automatique.
- Pas de generation lourde dans les gates publics non lourds.
