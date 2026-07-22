# Architecture and Orchestration

## Goal

Codex Unity ComfyUI Pipeline is a local experimental prototype, not broadly tested across machines. It coordinates a 3D asset pipeline for Unity without making ComfyUI or Unity the decision layer.

The intended flow is:

```text
User
  -> Codex
  -> Asset Factory MCP
  -> ComfyUI / TRELLIS2
  -> post-processing scripts
  -> Unity
```

Codex remains responsible for decisions under the user's instructions. ComfyUI is a local generation engine. Unity consumes prepared assets.

## Components

| Component | Role |
| --- | --- |
| `bootstrap/` | Pre-Codex installer. Produces a plan, installs allowed items and validates the setup. |
| `mcp/server.mjs` | Plugin MCP server. Exposes tools and the Asset Factory widget to Codex. |
| `mcp/asset-factory-widget.html` | Local control UI: asset, reference image, generation, review, Unity import, sockets. |
| `scripts/` | Python/PowerShell scripts for generation, validation, normalization, Unity import and maintenance. |
| `configs/asset-profiles/` | Reusable asset profiles: wall, door, prop, weapon, character, etc. |
| `configs/install-profiles/` | Installation profiles: cpu, ada, blackwell. |
| `docker/` | Optional runtime for heavy setup work, especially Blackwell. |
| `unity/Assets/AIAssetPipeline/` | Unity Editor template installed into a target Unity project. |
| `skills/` | Codex instructions for using the plugin safely. |

## Asset Orchestration

1. `plan_asset` chooses a profile, bounds, face/texture budget and reference rules.
2. `plan_reference_image` prepares a reference-image brief.
3. `register_reference_image` copies or registers the image in the work folder.
4. `validate_reference_image` checks format and minimum constraints.
5. `start_asset_pipeline_job` creates a persistent job in `.codex_asset_jobs`.
6. ComfyUI/TRELLIS2 generates 3D outputs.
7. Codex scripts inventory, select and normalize files.
8. `adjust_generated_asset` corrects scale, pivot, rotation, offset or bounds without rerunning generation.
9. `import_asset_to_unity` prepares the manifest and Unity-ready files.
10. Unity imports the manifest through the Editor template.

## Job States

| State | Meaning |
| --- | --- |
| `planned` | Job prepared, no long process started. |
| `reference_ready` | Reference image validated. |
| `queued` | Job ready to start. |
| `generating` | Local generation is running. |
| `generated` | Mesh or generation artifacts exist. |
| `review_needed` | User or Codex intervention required. |
| `adjusted` | Mesh corrected after generation. |
| `unity_ready` | Ready for Unity import. |
| `imported` | Import finished. |
| `failed` | Failure to diagnose in logs. |
| `cancelled` | Job cancelled. |

## Persistent Data

Jobs are stored under:

```text
<WORK_DIR>/.codex_asset_jobs/<job_id>/
```

Each job may contain:

- `job.json`
- `events.jsonl`
- `instructions.jsonl`
- `stdout.log`
- `stderr.log`
- `artifacts.json`

These files are useful for resuming or diagnosing a job, but they must not be published in a public repository.

## Known Limits

- This project is an experimental prototype and is not broadly tested.
- No guarantee is provided.
- Installers are not guaranteed on every machine.
- GPU generation depends heavily on CUDA, PyTorch, drivers, ComfyUI nodes and model versions.
- `-SkipUnityBatch` does not prove a full Unity batch import.
- Generated assets must always be reviewed by a human before real use.

## Design Rules

- Codex decides, ComfyUI generates, Unity consumes.
- Final dimensions are enforced after generation.
- Local paths stay out of the public repository.
- Heavy models and dependencies are not sold or redistributed by this project.
- License-gated and model-gated manual steps remain visible.
