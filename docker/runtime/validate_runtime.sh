#!/usr/bin/env bash
set -euo pipefail

echo "Asset Factory runtime validation"
echo "COMFYUI_ROOT=${COMFYUI_ROOT:-/opt/asset-factory/ComfyUI}"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,compute_cap,driver_version --format=csv,noheader || true
else
  echo "nvidia-smi unavailable"
fi

python - <<'PY'
import importlib.util
import os
from pathlib import Path

import torch

print("python ok")
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("cuda_device", torch.cuda.get_device_name(0))
    print("cuda_capability", torch.cuda.get_device_capability(0))

for module_name in ("xformers", "flash_attn", "huggingface_hub"):
    spec = importlib.util.find_spec(module_name)
    print(f"{module_name}_available", spec is not None)
    if spec is None:
        raise SystemExit(f"missing module: {module_name}")

comfy_root = Path(os.environ.get("COMFYUI_ROOT", "/opt/asset-factory/ComfyUI"))
trellis_node = comfy_root / "custom_nodes" / "ComfyUI-Trellis2"
print("comfyui_present", comfy_root.exists())
print("trellis2_node_present", trellis_node.exists())
if not comfy_root.exists() or not trellis_node.exists():
    raise SystemExit("ComfyUI or ComfyUI-Trellis2 missing")
PY

echo "runtime validation ok"
