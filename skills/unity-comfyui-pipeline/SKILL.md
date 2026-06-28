---
name: unity-comfyui-pipeline
description: Orchestrate local ComfyUI/TRELLIS image-to-3D generation for Unity while keeping Codex as the user-directed decision maker and post-generation processor.
---

# Unity ComfyUI Pipeline

Use this skill when the user asks Codex to generate, process, normalize, validate, or import Unity-ready 3D assets using local ComfyUI, TRELLIS/TRELLIS2, or this plugin.

## Operating Model

- Codex is the decision layer under the user's direction.
- ComfyUI is only a local generation engine. Do not treat it as the pipeline owner.
- Post-generation handling belongs to Codex: inventory outputs, choose the candidate set, copy/normalize/validate assets, write Unity manifests, and report evidence.
- Unity is a consumer: the included Editor template creates request JSON and imports Codex result manifests.
- Do not assume any project-specific folder, Unity project root, or local asset batch path unless the user provides it or the current workspace clearly contains it.

## Plugin Layout

Resolve paths relative to this skill's plugin root:

- `scripts/comfyui_trellis2_batch.py`: local ComfyUI batch runner. Requires explicit `--input-dir` and `--output-dir`.
- `scripts/run_trellis2_assets.ps1`: PowerShell wrapper around the batch runner.
- `scripts/prepare_trellis2_reference_image.py`: places a Codex-created reference image into the TRELLIS2 input directory and records metadata.
- `scripts/postprocess_generation.py`: Codex-owned post-generation mesh inventory, Unity copy, and manifest writer.
- `scripts/generate_asset.py`: end-to-end asset command: prepare reference image, run local TRELLIS2, normalize bounds, and optionally copy/import manifest for Unity.
- `scripts/adjust_glb_transform.py`: post-generation control for scale, pivot, rotation, offset, and target bounds when Codex or the user needs to correct a generated mesh before Unity import.
- `scripts/character_attachment_manifest.py`: character equipment/animation socket manifest tooling for stable attachment points on bones such as hands, back, head, chest, and hips.
- `scripts/normalize_wall_glbs.py`: optional wall/vault-specific GLB normalizer. Use only when the requested asset family really is walls/vaults.
- `scripts/install_unity_template.ps1`: copies the Unity Editor template into a Unity project.
- `workflows/`: bundled ComfyUI API/UI workflow JSON files.
- `unity/Assets/AIAssetPipeline/`: Unity Editor template payload.

## Workflow

1. Identify the user-approved target:
   - reference image/input directory,
   - output directory,
   - ComfyUI URL,
   - Unity project root if import is requested,
   - generation profile or workflow.

2. Preflight local generation:
   - Confirm the input directory exists and has images.
   - Confirm ComfyUI is reachable before non-dry-run generation.
   - Prefer a dry run before a long GPU job when scope is ambiguous.

3. If Codex created or selected the reference image, place it in the TRELLIS2 input directory first:

```powershell
python .\scripts\prepare_trellis2_reference_image.py `
  --image <codex-created-image> `
  --input-dir <reference-images> `
  --asset-name <asset-name>
```

For a complete single-asset pass, prefer the plugin orchestrator:

```powershell
python .\scripts\generate_asset.py `
  --asset-name <asset-name> `
  --reference-image <codex-created-or-selected-image> `
  --work-dir <job-work-dir> `
  --target-width <meters> `
  --target-height <meters> `
  --target-depth <meters> `
  --unity-project <unity-project-root>
```

4. Run generation through local ComfyUI:

```powershell
.\scripts\run_trellis2_assets.ps1 `
  -InputDir <reference-images> `
  -OutputDir <batch-output> `
  -Server http://127.0.0.1:8188 `
  -OfficialWorkflow simple
```

5. Post-process as Codex:

```powershell
python .\scripts\postprocess_generation.py `
  --batch-output-dir <batch-output> `
  --unity-project <unity-project-root> `
  --select newest `
  --limit 1
```

6. If Unity tooling is requested, install the template:

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot <unity-project-root>
```

7. Report concrete output paths:
   - placed TRELLIS2 reference image path,
   - selected mesh files,
   - copied Unity-ready files,
   - manifest paths,
   - validation errors or warnings.

## Decision Rules

- Ask the user before launching expensive or long GPU generation unless they already gave an explicit run command or batch scope.
- For app-driven work, prefer monitorable jobs: expose status, logs, cancellation, runtime instructions, and manual/Codex adjustments before final Unity import.
- Treat dimensions, pivot, orientation, triangle budget, texture size, and import placement as user/Codex-controlled post-generation decisions, not as promises made to TRELLIS through text in the image.
- For characters, create attachment manifests early. Equipment positions belong to explicit bone-local sockets that can be adjusted and revalidated, not to guessed mesh names or one-off Unity hierarchy searches.
- Keep seeds fixed by default for stable texture continuity between repeated runs. Use `--increment-seed` only when variation is explicitly desired.
- Use `postprocess_generation.py` after generation even when ComfyUI succeeds; the generated file alone is not the finished deliverable.
- Keep project-specific defaults in wrappers or configs, not in the core batch runner.
- Do not reintroduce a hidden local service on `127.0.0.1:8787`; this plugin is Codex-orchestrated, not service-orchestrated.
- For wall/vault packs, `normalize_wall_glbs.py` is allowed after generation. For generic props, use the generic postprocessor first and only add domain-specific normalization when requested.
- Preserve user files. If replacing an existing Unity template, use the install script's `-Force` only when the user has approved overwriting/merging.

## Verification

Before finishing:

- Run syntax checks on edited Python scripts:

```powershell
python -m py_compile .\scripts\comfyui_trellis2_batch.py .\scripts\postprocess_generation.py .\scripts\normalize_wall_glbs.py
```

- Run a dry-run batch when an input directory is available:

```powershell
.\scripts\run_trellis2_assets.ps1 -InputDir <reference-images> -OutputDir <batch-output> -DryRun -Limit 1
```

- Run postprocess dry-run when generated meshes are available:

```powershell
python .\scripts\postprocess_generation.py --batch-output-dir <batch-output> --dry-run --select newest --limit 1
```
