# TRELLIS2 ComfyUI Workflows

Bundled workflow JSON files for local ComfyUI + ComfyUI-TRELLIS2 generation.

Default workflow:

- `trellis2_simple.api.json`: API workflow based on the supplied `Simple.json`.

Mobile/stability defaults:

- fixed seed `2146628683`;
- `18/18/18` sparse, shape and texture steps;
- 4 views;
- 18k target faces;
- 1024 texture atlas.

Use them through the plugin runner instead of editing project-specific paths into the workflow files:

First place the Codex-created reference image where TRELLIS2 will read it:

```powershell
python .\scripts\prepare_trellis2_reference_image.py `
  --image <codex-created-image> `
  --input-dir <reference-images> `
  --asset-name <asset-name>
```

```powershell
.\scripts\run_trellis2_assets.ps1 `
  -InputDir <reference-images> `
  -OutputDir <batch-output> `
  -OfficialWorkflow simple
```

Profiles can also provide repeatable defaults:

```powershell
.\scripts\run_trellis2_assets.ps1 -Profile .\configs\default.profile.json -InputDir <reference-images> -OutputDir <batch-output>
```

The runner patches image inputs, output prefixes, face targets, texture size, model name, attention backend, and export format before queueing prompts through the local ComfyUI API.

ComfyUI prerequisites remain local:

- ComfyUI reachable, normally `http://127.0.0.1:8188`.
- `visualbruno/ComfyUI-Trellis2` custom nodes installed.
- Required TRELLIS2/DINO model files present in the local ComfyUI models directory.

After generation, run Codex-side post-processing:

```powershell
python .\scripts\postprocess_generation.py --batch-output-dir <batch-output> --select newest --limit 1
```
