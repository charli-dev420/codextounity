#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoProfile -ExecutionPolicy Bypass -File "$ROOT/scripts/scan_private_leaks.ps1" -Root "$ROOT"
  exit $?
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
find "$ROOT" -type f \
  ! -path '*/.git/*' ! -path '*/node_modules/*' ! -path '*/.venv/*' ! -path '*/venv/*' \
  \( -name '*.md' -o -name '*.json' -o -name '*.js' -o -name '*.mjs' -o -name '*.html' -o -name '*.ps1' -o -name '*.sh' -o -name '*.py' -o -name '*.cs' -o -name '*.yml' -o -name '*.yaml' \) \
  -print0 | xargs -0 grep -nEI '([A-Z]:\\Users\\[^\\[:space:]"'\'']+|/(home|Users)/[^[:space:]"'\'']+|sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|(ghp|github_pat)_[A-Za-z0-9_]{20,}|OPENAI_API_KEY[[:space:]]*=|HF_TOKEN[[:space:]]*=|GITHUB_TOKEN[[:space:]]*=)' > "$tmp" || true
if [[ -s "$tmp" ]]; then
  cat "$tmp"
  echo "Private leak scan FAILED" >&2
  exit 2
fi

if find "$ROOT" \
  \( -path '*/.git/*' -o -path '*/node_modules/*' -o -path '*/.venv/*' -o -path '*/venv/*' \) -prune -o \
  \( -type d -name '__pycache__' -o -type f \( -name '*.pyc' -o -name '*.pyo' \) \) -print -quit | grep -q .; then
  find "$ROOT" \
    \( -path '*/.git/*' -o -path '*/node_modules/*' -o -path '*/.venv/*' -o -path '*/venv/*' \) -prune -o \
    \( -type d -name '__pycache__' -o -type f \( -name '*.pyc' -o -name '*.pyo' \) \) -print
  echo "Generated Python cache found" >&2
  exit 2
fi
echo "Private leak scan OK"
