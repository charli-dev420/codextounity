#!/usr/bin/env bash
set -euo pipefail

IMAGE="${ASSET_FACTORY_RUNTIME_IMAGE:-codex-unity-comfyui-runtime:blackwell-cu128}"
docker run --rm --gpus all "$IMAGE" asset-factory-validate-runtime
