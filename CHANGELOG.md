# Changelog

## 0.2.0

- Removed the experimental facade-baker workstream and its app/tools/docs/installables from the 0.2.0 surface.
- Updated `bootstrap/install.ps1` to accept the documented `--target`, `--profile`, `--dry-run`, `--validate-only` and related long options.
- Added standalone pre-Codex bootstrap installer scripts for Windows, Linux, WSL and Docker.
- Added a local installer UI with system check, component plan, manual-license steps, install action and validation step.
- Added install profiles for Ada, Blackwell and CPU, including FlashAttention, xformers, PyTorch, ComfyUI, ComfyUI-Trellis2, TRELLIS2 models, DINOv3 manual setup, Unity and MCP Unity.
- Added bilingual French/English install, user, troubleshooting, credits and disclaimer documentation.
- Added private leak scanners and redacted proof handling for release safety.
- Added persistent job folders under `.codex_asset_jobs` with events, instructions, logs, artifacts, and recoverable status.
- Added asset profiles for walls, doors, props, weapons, pickups, characters, equipment, and terrain pieces.
- Added reference-image planning, registration, and validation tools.
- Added generic asset normalization support and character attachment slot management.
- Expanded the Asset Factory widget into a tabbed control surface.
- Added maintenance scripts for sync, validation, and smoke tests.
- Added Unity manifest bundles, prefab creation, batchmode manifest import, and scene-add validation.
- Added stable character socket metadata with `characterId:slotId` lookup.
- Added certifying `smoke_app.ps1` coverage for profiles, reference planning, jobs, normalization, sockets, Unity import and Unity batchmode.
