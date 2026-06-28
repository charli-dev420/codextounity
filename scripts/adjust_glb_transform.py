from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from normalize_wall_glbs import (
    collect_world_matrices,
    compute_world_bounds,
    load_glb,
    primitive_node_refs,
    read_accessor,
    save_glb,
    transform_points,
    validate_rows,
    vector_to_text,
    write_accessor,
)

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def rotation_matrix_xyz(rx: float, ry: float, rz: float) -> np.ndarray:
    x, y, z = [math.radians(v) for v in (rx, ry, rz)]
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    return mz @ my @ mx


def parse_vec3(value: str, default: tuple[float, float, float]) -> np.ndarray:
    if not value:
        return np.array(default, dtype=np.float64)
    parts = [float(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]
    if len(parts) == 1:
        parts = parts * 3
    if len(parts) != 3:
        raise ValueError(f"Expected one value or three comma-separated numbers, got {value!r}")
    return np.array(parts, dtype=np.float64)


def axis_remap_matrix(value: str) -> np.ndarray:
    if not value:
        value = "x,y,z"
    tokens = [part.strip().lower() for part in value.replace(";", ",").split(",") if part.strip()]
    if len(tokens) != 3:
        raise ValueError("--axis-remap must contain three axes, e.g. x,y,z or x,z,-y")
    matrix = np.zeros((3, 3), dtype=np.float64)
    used: set[str] = set()
    for output_index, token in enumerate(tokens):
        sign = -1.0 if token.startswith("-") else 1.0
        axis = token[1:] if token.startswith(("-", "+")) else token
        if axis not in AXIS_INDEX:
            raise ValueError(f"Invalid axis in --axis-remap: {token}")
        if axis in used:
            raise ValueError(f"Duplicate axis in --axis-remap: {axis}")
        used.add(axis)
        matrix[output_index, AXIS_INDEX[axis]] = sign
    return matrix


def bounds_dict(bounds: Any) -> dict[str, Any]:
    return {
        "min": [float(v) for v in bounds.minimum.tolist()],
        "max": [float(v) for v in bounds.maximum.tolist()],
        "extent": [float(v) for v in bounds.extent.tolist()],
        "minText": vector_to_text(bounds.minimum),
        "extentText": vector_to_text(bounds.extent),
    }


def compute_array_bounds(arrays: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not arrays:
        raise ValueError("No POSITION accessors found in GLB")
    min_v = np.vstack([a.min(axis=0) for a in arrays]).min(axis=0)
    max_v = np.vstack([a.max(axis=0) for a in arrays]).max(axis=0)
    return min_v, max_v, max_v - min_v


def choose_pivot(mode: str, min_v: np.ndarray, max_v: np.ndarray, custom: np.ndarray) -> np.ndarray:
    center = (min_v + max_v) * 0.5
    if mode == "bottom-center":
        return np.array([center[0], min_v[1], center[2]], dtype=np.float64)
    if mode == "center":
        return center
    if mode == "custom":
        return custom
    return np.zeros(3, dtype=np.float64)


def normalize_normals(values: np.ndarray, linear: np.ndarray) -> np.ndarray:
    try:
        normal_linear = np.linalg.inv(linear)
    except np.linalg.LinAlgError:
        normal_linear = linear
    adjusted = values.astype(np.float64) @ normal_linear
    lengths = np.linalg.norm(adjusted, axis=1)
    safe = np.where(lengths > 1e-8, lengths, 1.0)
    return (adjusted / safe[:, None]).astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description="Adjust a GLB after generation: axis remap, rotation, scale, pivot, offset, and target bounds.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rotate-euler", default="0,0,0", help="Degrees XYZ, e.g. 0,90,0.")
    parser.add_argument("--scale", default="1,1,1", help="Uniform scalar or XYZ scale.")
    parser.add_argument("--offset", default="0,0,0", help="World offset XYZ after pivot placement.")
    parser.add_argument("--target-bounds", default="", help="Optional final XYZ bounds, e.g. 4,2,0.35.")
    parser.add_argument("--pivot", choices=["bottom-center", "center", "origin", "custom", "keep"], default="bottom-center")
    parser.add_argument("--custom-pivot", default="0,0,0", help="Pivot XYZ used when --pivot custom.")
    parser.add_argument("--axis-remap", default="x,y,z", help="Axis remap, e.g. x,y,z, x,z,-y, -x,y,z.")
    parser.add_argument("--tolerance", type=float, default=0.002)
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    source = Path(args.input)
    output = Path(args.output)
    gltf, bin_chunk = load_glb(source)
    before = compute_world_bounds(gltf, bin_chunk, collect_world_matrices(gltf))

    axis = axis_remap_matrix(args.axis_remap)
    rotation = rotation_matrix_xyz(*parse_vec3(args.rotate_euler, (0, 0, 0)).tolist())
    user_scale = np.diag(parse_vec3(args.scale, (1, 1, 1)))
    linear = rotation @ user_scale @ axis
    offset = parse_vec3(args.offset, (0, 0, 0))
    custom_pivot = parse_vec3(args.custom_pivot, (0, 0, 0))

    position_cache: dict[int, np.ndarray] = {}
    normal_cache: dict[int, np.ndarray] = {}
    transformed_arrays: list[np.ndarray] = []
    world_matrices = collect_world_matrices(gltf)
    for node_index, _primitive_index, primitive in primitive_node_refs(gltf):
        attrs = primitive.get("attributes", {})
        pos_index = attrs.get("POSITION")
        if pos_index is not None:
            pos_index = int(pos_index)
            if pos_index not in position_cache:
                positions = read_accessor(gltf, bin_chunk, pos_index).astype(np.float64)
                world_positions = transform_points(positions, world_matrices[node_index])
                transformed = world_positions @ linear.T
                position_cache[pos_index] = transformed
                transformed_arrays.append(transformed)
        normal_index = attrs.get("NORMAL")
        if normal_index is not None:
            normal_index = int(normal_index)
            if normal_index not in normal_cache:
                normals = read_accessor(gltf, bin_chunk, normal_index).astype(np.float64)
                normal_cache[normal_index] = normalize_normals(normals, linear)

    min_v, max_v, extent = compute_array_bounds(transformed_arrays)
    target_bounds = parse_vec3(args.target_bounds, (0, 0, 0)) if args.target_bounds else None
    target_scale = np.ones(3, dtype=np.float64)
    if target_bounds is not None:
        safe_extent = np.where(np.abs(extent) > 1e-8, extent, 1.0)
        target_scale = target_bounds / safe_extent
        scale_matrix = np.diag(target_scale)
        linear = scale_matrix @ linear
        position_cache = {index: values @ scale_matrix.T for index, values in position_cache.items()}
        transformed_arrays = list(position_cache.values())
        normal_cache = {index: normalize_normals(values, linear) for index, values in normal_cache.items()}
        min_v, max_v, extent = compute_array_bounds(transformed_arrays)

    pivot = choose_pivot(args.pivot, min_v, max_v, custom_pivot)
    for pos_index, adjusted in position_cache.items():
        write_accessor(gltf, bin_chunk, pos_index, (adjusted - pivot + offset).astype(np.float32))
    for normal_index, adjusted_normals in normal_cache.items():
        write_accessor(gltf, bin_chunk, normal_index, adjusted_normals.astype(np.float32))

    for node in gltf.get("nodes", []):
        node.pop("translation", None)
        node.pop("rotation", None)
        node.pop("scale", None)
        node.pop("matrix", None)

    output.parent.mkdir(parents=True, exist_ok=True)
    save_glb(output, gltf, bin_chunk)
    after = compute_world_bounds(gltf, bin_chunk, collect_world_matrices(gltf))
    row = {
        "output": str(output),
        "output_min": vector_to_text(after.minimum),
        "output_extent": vector_to_text(after.extent),
        "target_width": float(target_bounds[0]) if target_bounds is not None else float(after.extent[0]),
        "target_height": float(target_bounds[1]) if target_bounds is not None else float(after.extent[1]),
        "target_thickness": float(target_bounds[2]) if target_bounds is not None else float(after.extent[2]),
    }
    errors = validate_rows([row], args.tolerance) if target_bounds is not None and args.pivot == "bottom-center" else []
    report = {
        "schema": "codex.normalizationReport.v2",
        "input": str(source.resolve()),
        "output": str(output.resolve()),
        "before": bounds_dict(before),
        "after": bounds_dict(after),
        "transform": {
            "axisRemap": args.axis_remap,
            "rotationEuler": args.rotate_euler,
            "scale": args.scale,
            "targetScaleApplied": [float(v) for v in target_scale.tolist()],
            "offset": args.offset,
            "pivotMode": args.pivot,
            "customPivot": args.custom_pivot,
            "pivotApplied": [float(v) for v in pivot.tolist()],
            "targetBounds": args.target_bounds,
        },
        "validation": {"tolerance": args.tolerance, "errors": errors, "valid": not errors},
    }
    report_path = Path(args.report) if args.report else output.with_suffix(".normalization_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
