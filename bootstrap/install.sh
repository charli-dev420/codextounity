#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for arg in "$@"; do
  if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
    cat <<'EOF'
Asset Factory bootstrap installer

Usage:
  ./bootstrap/install.sh [options]

Options:
  --target auto|windows|linux|wsl|docker
  --profile auto|ada|blackwell|cpu
  --fallback auto|semi-auto|manual
  --install-root <path>
  --codex-home <path>
  --unity-project <path>
  --dry-run
  --validate-only
  --non-interactive
  --json
  --help, -h

Recommended first run:
  ./bootstrap/install.sh --dry-run --target linux --profile auto

Notes:
  This wrapper uses PowerShell 7 (pwsh) for the shared installer engine.
  If pwsh is missing, dry-run and validate-only return a manual-required
  result instead of installing anything.
EOF
    exit 0
  fi
done

if ! command -v pwsh >/dev/null 2>&1; then
  for arg in "$@"; do
    if [[ "$arg" == "--dry-run" || "$arg" == "--validate-only" ]]; then
      cat <<'JSON'
{
  "schema": "codex.assetFactory.bootstrapResult.v1",
  "dryRun": true,
  "plan": {
    "state": "partially_ready",
    "summary": {
      "present": 0,
      "installable": 0,
      "manualRequired": 1,
      "sourceReviewRequired": 0
    },
    "steps": [
      {
        "id": "powershell",
        "name": "PowerShell 7",
        "status": "manual_required",
        "officialSource": "https://learn.microsoft.com/powershell/scripting/install/installing-powershell",
        "licenseNote": "Install PowerShell 7 from the official Microsoft documentation, then rerun this script."
      }
    ]
  },
  "execution": {
    "mode": "bash-fallback",
    "note": "pwsh was not found, so no installer action was executed."
  }
}
JSON
      exit 0
    fi
  done
  echo "PowerShell 7 (pwsh) is required for the one-click bootstrap wrapper."
  echo "Install it from: https://learn.microsoft.com/powershell/scripting/install/installing-powershell"
  exit 127
fi

args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) args+=("-Target" "$2"); shift 2 ;;
    --profile) args+=("-Profile" "$2"); shift 2 ;;
    --fallback) args+=("-Fallback" "$2"); shift 2 ;;
    --dry-run) args+=("-DryRun"); shift ;;
    --validate-only) args+=("-ValidateOnly"); shift ;;
    --non-interactive) args+=("-NonInteractive"); shift ;;
    --install-root) args+=("-InstallRoot" "$2"); shift 2 ;;
    --codex-home) args+=("-CodexHome" "$2"); shift 2 ;;
    --unity-project) args+=("-UnityProject" "$2"); shift 2 ;;
    --json) args+=("-Json"); shift ;;
    *) args+=("$1"); shift ;;
  esac
done

pwsh -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/install.ps1" "${args[@]}"

