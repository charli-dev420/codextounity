#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE="${ASSET_FACTORY_RUNTIME_IMAGE:-codex-unity-comfyui-runtime:blackwell-cu128}"
BASE_IMAGE="${ASSET_FACTORY_BASE_IMAGE:-nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04}"
STAGE="${STAGE:-all}"
BUILD_JOBS="${BUILD_JOBS:-1}"
MIN_FREE_RAM_GB="${MIN_FREE_RAM_GB:-6}"
INCLUDE_TRELLIS2_MODELS="${INCLUDE_TRELLIS2_MODELS:-true}"

export MAX_JOBS="$BUILD_JOBS"
export CMAKE_BUILD_PARALLEL_LEVEL="$BUILD_JOBS"
export MAKEFLAGS="-j$BUILD_JOBS"
export NINJAFLAGS="-j$BUILD_JOBS"
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"

free_ram_gb() {
  awk '/MemAvailable/ { printf "%.2f", $2 / 1024 / 1024 }' /proc/meminfo 2>/dev/null || echo 999
}

build_stage() {
  local target_stage="$1"
  local free
  free="$(free_ram_gb)"
  awk -v free="$free" -v min="$MIN_FREE_RAM_GB" 'BEGIN { if (free < min) exit 1 }' || {
    echo "Free RAM is too low for Docker stage '$target_stage': ${free}GB available, ${MIN_FREE_RAM_GB}GB required." >&2
    exit 2
  }
  local tag="$IMAGE-$target_stage"
  if [[ "$target_stage" == "final" ]]; then tag="$IMAGE"; fi
  echo "[build] image=$tag target=$target_stage buildJobs=$BUILD_JOBS includeTrellis2Models=$INCLUDE_TRELLIS2_MODELS freeRamGB=$free"
  args=(
    build
    --progress plain
    --target "$target_stage"
    -f "$PLUGIN_ROOT/docker/runtime/Dockerfile.blackwell"
    -t "$tag"
    --build-arg "BASE_IMAGE=$BASE_IMAGE"
    --build-arg "BUILD_JOBS=$BUILD_JOBS"
    --build-arg "INCLUDE_TRELLIS2_MODELS=$INCLUDE_TRELLIS2_MODELS"
    "$PLUGIN_ROOT"
  )
  if [[ "${NO_CACHE:-false}" == "true" ]]; then
    args=(build --no-cache "${args[@]:1}")
  fi
  docker "${args[@]}"
}

if [[ "$STAGE" == "all" ]]; then
  for target_stage in apt-base venv-base torch-runtime attention-runtime comfyui-runtime trellis2-runtime models-runtime final; do
    build_stage "$target_stage"
  done
else
  build_stage "$STAGE"
fi
