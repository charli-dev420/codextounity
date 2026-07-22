# Guide utilisateur

## A lire d'abord

Ce projet est un prototype experimental, globalement non teste, sans aucune garantie. Il peut aider a generer et importer des assets, mais il ne remplace pas une verification humaine. Controlez les dimensions, le pivot, la rotation, la qualite du mesh, les textures et l'import Unity avant d'utiliser un asset dans un vrai projet.

## Role des pieces

- L'installeur prepare la machine avant Codex.
- Codex decide et orchestre sous vos consignes.
- ComfyUI genere localement.
- TRELLIS2 produit ou aide a produire les meshes 3D.
- Les scripts du plugin normalisent, choisissent les outputs, creent les manifests et preparent Unity.
- Unity consomme les assets Unity-ready.

## Premier parcours conseille

1. Lancer l'installeur Windows :

```powershell
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe
```

Si l'executable n'a pas encore ete fourni comme artefact experimental, le construire depuis le depot avec `.\installer\windows\build-installer.ps1`.

2. Cliquer `Preflight and plan`.
3. Lire les composants manquants.
4. Faire les etapes manuelles, notamment DINOv3 si demande.
5. Cliquer `Validate setup`.
6. Redemarrer Codex.
7. Ouvrir Asset Factory avec `open_asset_factory`.
8. Verifier que ComfyUI repond sur `http://127.0.0.1:8188`.
9. Faire un dry-run d'asset avant une generation reelle.

## Ouvrir l'app Codex

Apres validation, redemarrer Codex. L'app expose :

- `open_asset_factory` pour ouvrir l'interface,
- `plan_asset` pour choisir un profil et des contraintes,
- `plan_reference_image` pour preparer l'image de reference,
- `register_reference_image` et `validate_reference_image`,
- `start_asset_pipeline_job` pour lancer un job monitorable,
- `job_status`, `add_pipeline_instruction`, `cancel_pipeline_job`,
- `adjust_generated_asset` pour corriger bounds, pivot, rotation, scale,
- `import_asset_to_unity`,
- outils de sockets personnage.

## Creer un asset test

1. Ouvrir Asset Factory.
2. Choisir un profil : `wall`, `door`, `prop`, `weapon`, `pickup`, `character`, `equipment`, `terrain_piece`.
3. Donner un nom simple, par exemple `test_wall`.
4. Decrire l'asset avec une phrase courte.
5. Choisir les dimensions cible en metres.
6. Cliquer `Plan`.
7. Generer ou fournir une image de reference.
8. Valider l'image : objet unique, fond uni, pas de texte, vue lisible.
9. Lancer un `Dry-run`.
10. Si le plan est correct et ComfyUI pret, lancer `Start job`.
11. Lire `Status` pendant la generation.
12. Ajuster le GLB si necessaire.
13. Importer dans Unity.

Succes minimum avant import Unity :

- `job_status` indique `generated`, `adjusted` ou `unity_ready` ;
- un artefact mesh existe dans le dossier de travail du job ;
- `normalization_report.json` est valide si les bounds ont ete ajustes ;
- `import_asset_to_unity` ecrit un manifest Unity et un chemin mesh pret pour Unity.

Pour les details bas niveau TRELLIS2, voir `workflows/README_TRELLIS2_COMFYUI.md`.

## Conseils pour l'image de reference

Une bonne image de reference doit avoir :

- un seul objet,
- l'objet complet visible,
- un fond uni,
- pas d'ombres fortes,
- pas de texte, mesures, labels ou interface,
- une vue 3/4 legerement plongeante pour beaucoup d'objets,
- des proportions plausibles.

Les dimensions finales ne doivent pas etre ecrites dans l'image. Elles sont imposees apres generation par normalisation.

## Lire les statuts

- `planned` : job prepare, rien de long lance.
- `reference_ready` : image validee.
- `queued` : job pret a demarrer.
- `generating` : ComfyUI/TRELLIS2 tourne.
- `generated` : mesh present.
- `review_needed` : intervention requise.
- `adjusted` : mesh corrige.
- `unity_ready` : pret pour Unity.
- `imported` : import termine.
- `failed` : lire les logs et erreurs.
- `cancelled` : job annule.

## Ajuster un mesh

Utiliser `adjust_generated_asset` quand l'asset est trop grand, trop petit, tourne mal ou a un mauvais pivot.

La normalisation conserve les proportions. Les bounds cibles sont une enveloppe maximale, jamais une cible de stretch X/Y/Z. L'axe de fit vient du profil sauf override explicite : `terrain_piece`, `prop`, `pickup` et `equipment` utilisent `contain`, `wall` et `weapon` utilisent `x`, et `door` et `character` utilisent `y`. `window_wall` et `wall_mirror` sont des sous-profils muraux avec leurs propres bounds et axes. Le scale XYZ non uniforme est refuse car il deforme les meshes generes.

Exemple de bounds pour un mur :

```text
targetBounds = 4,2,0.35
fitAxis = x
pivot = bottom-center
axisRemap = x,y,z
rotateEuler = 0,0,0
scale = 1
```

Relire le `normalization_report.json` pour verifier les bounds avant/apres, `fitMode`, `fitAxis` et `proportionsPreserved`.

## Import Unity

1. Installer le template :

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot "<UNITY_PROJECT>"
```

2. Importer l'asset depuis Asset Factory ou via `import_asset_to_unity`.
3. Verifier dans Unity :
   - prefab cree,
   - scale correcte,
   - pivot attendu,
   - material et textures,
   - pas d'erreurs Console.

## Sockets personnage

Les equipements doivent etre rattaches a des slots stables : main hand, offhand, back, head, chest, hips, belt, feet, shoulders ou slots custom.

Chaque slot stocke :

- bone,
- position locale,
- rotation locale,
- scale,
- categorie d'equipement,
- pose de preview,
- notes.

Utiliser `characterId + slotId` pour retrouver un point d'attache sans dependre d'un nom fragile de mesh.

## Quand ouvrir une issue

Ouvrir une issue si :

- l'installeur echoue avec une commande claire,
- la documentation est confuse,
- un outil annonce comme present ne l'est pas,
- Unity compile mal apres installation du template,
- un dry-run ou smoke test echoue.

Retirer les secrets, tokens, chemins personnels et noms de projets prives avant de publier un log.
