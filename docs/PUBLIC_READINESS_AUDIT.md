# Experimental Prototype Publication Audit

Date: 2026-06-28

## Current Verdict

The repository is suitable for experimental prototype sharing, not a release candidate, not a certified product release and not a supported installer product. The public packaging surface is mostly present: README, support policy, security policy, contribution guide, issue templates, PR template, publication checklist, ignored generated artifacts, explicit unlicensed prototype wording, and a Windows graphical installer executable built from source.

The Windows executable is an experimental onboarding convenience for novice users. It does not imply installer reliability, production support, broad testing, or machine compatibility.

The main remaining risk is product/runtime proof. The repo can validate the plugin surface and smoke major local paths, but it still lacks live ComfyUI/TRELLIS2 proof, Unity batch proof in a real project, and deeper mesh validation.

## Confirmed Strengths

- Public status is explicit: solo-maintained experimental prototype, globally untested/broadly untested across machines, no guarantee, no stability guarantee, no support SLA, no installer reliability guarantee.
- `LICENSE.md` clearly states that no open-source license is granted yet.
- `.gitignore` excludes secrets, local env files, models, generated meshes/images, proof JSON, Unity local folders, installer outputs, Python caches, and local `.codex/` config.
- `installer/windows/AssetFactoryInstaller` provides a novice-facing Windows executable front end over the bootstrap engine; experimental downloads can include `AssetFactoryInstaller.exe` rather than asking users to identify a PowerShell script.
- GitHub issue and PR templates request redacted logs and public hygiene checks.
- `validate_plugin.ps1` checks MCP syntax, Python syntax, profile validity, tool listing, UI resource loading, and persistent dry-run job recovery.
- `smoke_app.ps1 -SkipUnityBatch` exercises planning, profile selection, dry-run jobs, GLB adjustment, persistent job state, cancellation, character sockets, and optional Unity import staging.
- ComfyUI defaults are aligned on `http://127.0.0.1:8188` across Docker, configs, wrapper scripts, MCP server, widget, and generation CLI.
- Dry-run Python paths use bytecode-free execution and the TRELLIS2 batch dry-run no longer creates output/workflow directories or downloads workflow files.
- Single-asset generation now routes normalization through the generic bounds/pivot wrapper instead of the wall/vault-specific batch normalizer.

## Major Gaps

1. No live generation proof is recorded. A real ComfyUI/TRELLIS2 run still needs validation for workflow node compatibility, model loading, output discovery, long-running logs, and timeout behavior.
2. No Unity compile/import proof is recorded. `-SkipUnityBatch` is useful but does not prove C# compilation, AssetDatabase import, prefab creation, scene insertion, or socket placement.
3. Mesh validation is shallow after postprocess. Current checks prove file presence and manifest shape more than triangle count, texture size, bounds, material health, or profile-specific rules.
4. Profile-specific normalization still needs proof for characters, equipment and terrain pieces. The generic wrapper is safer, but not yet a semantic validator for every profile.
5. Persistent cancellation uses saved PIDs. It should verify command line or process ownership before killing a process restored from `job.json`.
6. Unity path conversion should prove imported assets are inside the active Unity project instead of relying on the first `Assets/` path segment.
7. Public onboarding still needs more real-user proof for Docker/Blackwell setup, first asset generation, and common Docker permission/config warnings.

## Experimental Publication Stop Rules

Do not publish the experimental prototype until all of these are true:

- `git status --short --ignored` has no unexpected tracked changes, local config, generated proof JSON, or `__pycache__`.
- `.\scripts\scan_private_leaks.ps1` passes.
- `.\scripts\validate_plugin.ps1` passes and fails hard if the leak scan fails.
- `.\scripts\smoke_app.ps1 -SkipUnityBatch` passes.
- `docker compose -f docker\compose.yaml config` passes.
- `.\installer\windows\build-installer.ps1` creates `AssetFactoryInstaller.exe`, and `AssetFactoryInstaller.exe --validate-launcher --plugin-root <PLUGIN_ROOT>` exits successfully.
- Any generated `proof/*.json` files are removed before public push.

## Continuation Plan

See `docs/ROADMAP.md` for the detailed continuation roadmap. The short plan below is only a summary.

### P0: Experimental Hygiene Gate

- Keep `.codex/` local-only and ignored.
- Keep blank GitHub issues disabled so reporters use templates with hygiene checks.
- Run and record the public checks above after every publication-facing edit.
- Build the Windows installer executable for optional experimental downloads, attach it only as a convenience artifact, and keep generated `dist/`, `bin/` and `obj/` folders out of git.
- Remove generated proof JSON and Python bytecode before final status.

### P1: Runtime Correctness

- Add profile-specific validation for bounds, allowed formats, approximate face budgets, texture size, and required manifest fields.
- Add profile-specific normalization/placement checks for characters, equipment, terrain, props and weapons.
- Make cancellation verify process identity before killing a persisted PID.
- Stream or cap foreground MCP process logs for long jobs.

### P2: Unity Proof

- Validate the template in a disposable Unity project.
- Add a batch import proof without `-SkipUnityBatch`.
- Harden Unity path conversion so manifests cannot import from outside the active project unintentionally.

### P3: Real Generation Proof

- Run one small reference image through live ComfyUI/TRELLIS2 on port `8188`.
- Confirm generated GLB discovery, postprocess, normalization report, Unity manifest output, and job status transitions.
- Add troubleshooting notes from the first live failure modes.

## Public Positioning

Publish as a local experimental prototype and contributor-feedback repository, globally untested across machines and provided with no guarantee of any kind. Do not position it as an RC, stable installer, or supported production asset pipeline. Keep wording factual: Codex orchestrates and post-processes; ComfyUI/TRELLIS2 are local generation engines; Unity consumes manifests and imported assets.
