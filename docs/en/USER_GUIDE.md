# User Guide

## Read First

This project is an experimental prototype, not broadly tested, with no guarantee of any kind. It can help generate and import assets, but it does not replace human review. Check dimensions, pivot, rotation, mesh quality, textures and Unity import before using an asset in a real project.

## Roles

- The installer prepares the machine before Codex.
- Codex decides and orchestrates under your instructions.
- ComfyUI generates locally.
- TRELLIS2 produces or helps produce 3D meshes.
- Plugin scripts normalize, select outputs, create manifests and prepare Unity.
- Unity consumes Unity-ready assets.

## First Recommended Flow

1. Start the Windows installer:

```powershell
.\installer\windows\dist\AssetFactoryInstaller-win-x64\AssetFactoryInstaller.exe
```

If the executable has not been provided as an experimental artifact yet, build it from the repository with `.\installer\windows\build-installer.ps1`.

2. Click `Preflight and plan`.
3. Read missing components.
4. Complete manual steps, especially DINOv3 when required.
5. Click `Validate setup`.
6. Restart Codex.
7. Open Asset Factory with `open_asset_factory`.
8. Confirm ComfyUI is reachable at `http://127.0.0.1:8188`.
9. Run an asset dry-run before real generation.

## Open the Codex App

After validation, restart Codex. The app exposes:

- `open_asset_factory` to open the UI,
- `plan_asset` to choose a profile and constraints,
- `plan_reference_image` to prepare the reference image,
- `register_reference_image` and `validate_reference_image`,
- `start_asset_pipeline_job` for monitorable jobs,
- `job_status`, `add_pipeline_instruction`, `cancel_pipeline_job`,
- `adjust_generated_asset` to correct bounds, pivot, rotation and scale,
- `import_asset_to_unity`,
- character socket tools.

## Create a Test Asset

1. Open Asset Factory.
2. Choose a profile: `wall`, `door`, `prop`, `weapon`, `pickup`, `character`, `equipment`, `terrain_piece`.
3. Give it a simple name, for example `test_wall`.
4. Describe the asset in one short sentence.
5. Choose target dimensions in meters.
6. Click `Plan`.
7. Generate or provide a reference image.
8. Validate the image: one object, plain background, no text, readable view.
9. Run a `Dry-run`.
10. If the plan is correct and ComfyUI is ready, click `Start job`.
11. Read `Status` during generation.
12. Adjust the GLB when needed.
13. Import into Unity.

Minimum success before Unity import:

- `job_status` shows `generated`, `adjusted` or `unity_ready`;
- a mesh artifact exists under the job work directory;
- `normalization_report.json` is valid when bounds were adjusted;
- `import_asset_to_unity` writes a Unity manifest and Unity-ready mesh path.

For lower-level TRELLIS2 workflow details, see `workflows/README_TRELLIS2_COMFYUI.md`.

## Reference Image Tips

A good reference image should have:

- one object,
- the whole object visible,
- plain background,
- no strong shadows,
- no text, measurements, labels or UI,
- a slightly top-down 3/4 view for many objects,
- plausible proportions.

Do not write final dimensions into the image. Dimensions are enforced after generation through normalization.

## Read Statuses

- `planned`: job prepared, no long process started.
- `reference_ready`: reference image validated.
- `queued`: job ready to start.
- `generating`: ComfyUI/TRELLIS2 is running.
- `generated`: mesh exists.
- `review_needed`: user or Codex review required.
- `adjusted`: mesh corrected.
- `unity_ready`: ready for Unity.
- `imported`: import finished.
- `failed`: inspect logs and errors.
- `cancelled`: job cancelled.

## Adjust a Mesh

Use `adjust_generated_asset` when the asset is too large, too small, rotated incorrectly or has the wrong pivot.

Normalization preserves proportions. Target bounds are treated as a maximum envelope, never as a stretch target for X/Y/Z. The fit axis comes from the asset profile unless you override it: `terrain_piece`, `prop`, `pickup` and `equipment` use `contain`, `wall` and `weapon` use `x`, and `door` and `character` use `y`. `window_wall` and `wall_mirror` are wall sub-profiles with their own fit axis and bounds. Non-uniform XYZ scale is rejected because it deforms generated meshes.

Example wall bounds:

```text
targetBounds = 4,2,0.35
fitAxis = x
pivot = bottom-center
axisRemap = x,y,z
rotateEuler = 0,0,0
scale = 1
```

Read `normalization_report.json` to verify before/after bounds, `fitMode`, `fitAxis` and `proportionsPreserved`.

## Unity Import

1. Install the template:

```powershell
.\scripts\install_unity_template.ps1 -UnityProjectRoot "<UNITY_PROJECT>"
```

2. Import the asset from Asset Factory or through `import_asset_to_unity`.
3. Check in Unity:
   - prefab created,
   - correct scale,
   - expected pivot,
   - material and textures,
   - no Console errors.

## Character Sockets

Equipment should attach to stable slots: main hand, offhand, back, head, chest, hips, belt, feet, shoulders or custom slots.

Each slot stores:

- bone,
- local position,
- local rotation,
- scale,
- equipment category,
- preview pose,
- notes.

Use `characterId + slotId` to retrieve an attachment point without depending on a fragile mesh name.

## When To Open An Issue

Open an issue when:

- the installer fails with a clear command,
- documentation is confusing,
- a tool reported as present is not available,
- Unity fails to compile after template installation,
- a dry-run or smoke test fails.

Remove secrets, tokens, personal paths and private project names before posting logs.
