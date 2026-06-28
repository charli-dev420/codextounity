from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

COMPONENT_FLOAT = 5126
COMPONENT_DTYPE = {
    COMPONENT_FLOAT: np.float32,
}
TYPE_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}
AXIS_NAMES = ("X", "Y", "Z")


class GlbError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssetPlan:
    source: Path
    output: Path
    asset_kind: str
    width_label: str
    target_width: float
    target_height: float
    target_thickness: float


@dataclass
class Bounds:
    minimum: np.ndarray
    maximum: np.ndarray

    @property
    def extent(self) -> np.ndarray:
        return self.maximum - self.minimum


def pad4(data: bytes, pad: bytes) -> bytes:
    remainder = len(data) % 4
    if remainder == 0:
        return data
    return data + pad * (4 - remainder)


def load_glb(path: Path) -> tuple[dict[str, Any], bytearray]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise GlbError(f"{path} is not a GLB file")

    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC or version != 2:
        raise GlbError(f"{path} is not a glTF 2.0 GLB")
    if declared_length != len(data):
        raise GlbError(f"{path} has an invalid GLB length")

    offset = 12
    gltf: dict[str, Any] | None = None
    bin_chunk: bytearray | None = None
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
        elif chunk_type == BIN_CHUNK:
            bin_chunk = bytearray(chunk)

    if gltf is None or bin_chunk is None:
        raise GlbError(f"{path} is missing JSON or BIN chunk")
    return gltf, bin_chunk


def save_glb(path: Path, gltf: dict[str, Any], bin_chunk: bytearray) -> None:
    json_data = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_data = pad4(json_data, b" ")
    bin_data = pad4(bytes(bin_chunk), b"\x00")
    total = 12 + 8 + len(json_data) + 8 + len(bin_data)

    out = bytearray()
    out.extend(struct.pack("<4sII", GLB_MAGIC, 2, total))
    out.extend(struct.pack("<II", len(json_data), JSON_CHUNK))
    out.extend(json_data)
    out.extend(struct.pack("<II", len(bin_data), BIN_CHUNK))
    out.extend(bin_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)


def quat_to_matrix(quat: list[float]) -> np.ndarray:
    x, y, z, w = quat
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return np.array(
        [
            [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy), 0],
            [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx), 0],
            [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy), 0],
            [0, 0, 0, 1],
        ],
        dtype=np.float64,
    )


def node_local_matrix(node: dict[str, Any]) -> np.ndarray:
    if "matrix" in node:
        # glTF stores matrices column-major.
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T

    translation = np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
    rotation = np.array(node.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
    scale = np.array(node.get("scale", [1, 1, 1]), dtype=np.float64)

    t_matrix = np.eye(4, dtype=np.float64)
    t_matrix[:3, 3] = translation
    s_matrix = np.diag([scale[0], scale[1], scale[2], 1.0])
    return t_matrix @ quat_to_matrix(rotation.tolist()) @ s_matrix


def scene_roots(gltf: dict[str, Any]) -> list[int]:
    scenes = gltf.get("scenes") or []
    scene_index = int(gltf.get("scene", 0))
    if scenes and scene_index < len(scenes):
        return [int(node_id) for node_id in scenes[scene_index].get("nodes", [])]
    return list(range(len(gltf.get("nodes", []))))


def collect_world_matrices(gltf: dict[str, Any]) -> dict[int, np.ndarray]:
    nodes = gltf.get("nodes", [])
    result: dict[int, np.ndarray] = {}

    def walk(node_index: int, parent: np.ndarray) -> None:
        node = nodes[node_index]
        world = parent @ node_local_matrix(node)
        result[node_index] = world
        for child in node.get("children", []) or []:
            walk(int(child), world)

    for root in scene_roots(gltf):
        walk(root, np.eye(4, dtype=np.float64))
    return result


def accessor_info(gltf: dict[str, Any], accessor_index: int) -> tuple[dict[str, Any], dict[str, Any], int, int, np.dtype[Any], int]:
    accessor = gltf["accessors"][accessor_index]
    if accessor.get("sparse"):
        raise GlbError("Sparse accessors are not supported by this normalizer")
    component_type = int(accessor["componentType"])
    if component_type not in COMPONENT_DTYPE:
        raise GlbError(f"Unsupported accessor component type: {component_type}")
    accessor_type = accessor["type"]
    if accessor_type not in TYPE_COMPONENTS:
        raise GlbError(f"Unsupported accessor type: {accessor_type}")

    buffer_view = gltf["bufferViews"][accessor["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPE[component_type])
    components = TYPE_COMPONENTS[accessor_type]
    item_size = dtype.itemsize * components
    stride = int(buffer_view.get("byteStride", item_size))
    byte_offset = int(buffer_view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return accessor, buffer_view, byte_offset, stride, dtype, components


def read_accessor(gltf: dict[str, Any], bin_chunk: bytearray, accessor_index: int) -> np.ndarray:
    accessor, _view, byte_offset, stride, dtype, components = accessor_info(gltf, accessor_index)
    count = int(accessor["count"])
    values = np.empty((count, components), dtype=dtype)
    for index in range(count):
        start = byte_offset + index * stride
        raw = bin_chunk[start : start + dtype.itemsize * components]
        values[index] = np.frombuffer(raw, dtype=dtype, count=components)
    return values


def write_accessor(gltf: dict[str, Any], bin_chunk: bytearray, accessor_index: int, values: np.ndarray) -> None:
    accessor, _view, byte_offset, stride, dtype, components = accessor_info(gltf, accessor_index)
    if values.shape != (int(accessor["count"]), components):
        raise GlbError("Accessor value shape mismatch")
    typed = values.astype(dtype, copy=False)
    for index in range(typed.shape[0]):
        start = byte_offset + index * stride
        bin_chunk[start : start + dtype.itemsize * components] = typed[index].tobytes()
    if components in {3, 4} and accessor.get("type") in {"VEC3", "VEC4"}:
        accessor["min"] = [round_float(v) for v in typed.min(axis=0).tolist()]
        accessor["max"] = [round_float(v) for v in typed.max(axis=0).tolist()]


def round_float(value: float) -> float:
    if abs(value) < 1e-8:
        return 0.0
    return float(f"{float(value):.8g}")


def primitive_node_refs(gltf: dict[str, Any]) -> list[tuple[int, int, dict[str, Any]]]:
    refs: list[tuple[int, int, dict[str, Any]]] = []
    for node_index, node in enumerate(gltf.get("nodes", [])):
        mesh_index = node.get("mesh")
        if mesh_index is None:
            continue
        mesh = gltf["meshes"][int(mesh_index)]
        for primitive_index, primitive in enumerate(mesh.get("primitives", []) or []):
            refs.append((node_index, primitive_index, primitive))
    return refs


def compute_world_bounds(gltf: dict[str, Any], bin_chunk: bytearray, world_matrices: dict[int, np.ndarray]) -> Bounds:
    mins: list[np.ndarray] = []
    maxes: list[np.ndarray] = []
    for node_index, _primitive_index, primitive in primitive_node_refs(gltf):
        position_index = primitive.get("attributes", {}).get("POSITION")
        if position_index is None:
            continue
        positions = read_accessor(gltf, bin_chunk, int(position_index)).astype(np.float64)
        matrix = world_matrices[node_index]
        world_positions = transform_points(positions, matrix)
        mins.append(world_positions.min(axis=0))
        maxes.append(world_positions.max(axis=0))
    if not mins:
        raise GlbError("No POSITION accessors found")
    return Bounds(np.vstack(mins).min(axis=0), np.vstack(maxes).max(axis=0))


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.concatenate([points, np.ones((points.shape[0], 1), dtype=np.float64)], axis=1)
    return (homogeneous @ matrix.T)[:, :3]


def transform_vectors(vectors: np.ndarray, matrix3: np.ndarray) -> np.ndarray:
    return vectors @ matrix3.T


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(vectors, axis=1)
    safe = np.where(lengths > 1e-12, lengths, 1.0)
    return vectors / safe[:, None]


def infer_horizontal_axes(bounds: Bounds) -> tuple[int, int, int]:
    # glTF/Unity vertical is Y. Trellis outputs sometimes swap X/Z, so infer only
    # width vs thickness on the horizontal plane.
    horizontal = [0, 2]
    extent = bounds.extent
    width_axis = max(horizontal, key=lambda axis: float(extent[axis]))
    thickness_axis = 2 if width_axis == 0 else 0
    return width_axis, 1, thickness_axis


def normalization_linear(bounds: Bounds, target_width: float, target_height: float, target_thickness: float) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    width_axis, height_axis, thickness_axis = infer_horizontal_axes(bounds)
    extent = bounds.extent
    if min(float(extent[width_axis]), float(extent[height_axis]), float(extent[thickness_axis])) <= 1e-8:
        raise GlbError("Degenerate asset bounds")

    width_scale = target_width / float(extent[width_axis])
    height_scale = target_height / float(extent[height_axis])
    thickness_scale = target_thickness / float(extent[thickness_axis])
    thickness_sign = -1.0 if width_axis == 2 else 1.0

    linear = np.zeros((3, 3), dtype=np.float64)
    linear[0, width_axis] = width_scale
    linear[1, height_axis] = height_scale
    linear[2, thickness_axis] = thickness_sign * thickness_scale

    center = (bounds.minimum + bounds.maximum) * 0.5
    origin_old = np.array(
        [
            center[width_axis],
            bounds.minimum[height_axis],
            center[thickness_axis],
        ],
        dtype=np.float64,
    )
    old_anchor = np.zeros(3, dtype=np.float64)
    old_anchor[width_axis] = origin_old[0]
    old_anchor[height_axis] = origin_old[1]
    old_anchor[thickness_axis] = origin_old[2]
    translation = -(linear @ old_anchor)

    info = {
        "width_axis": AXIS_NAMES[width_axis],
        "height_axis": AXIS_NAMES[height_axis],
        "thickness_axis": AXIS_NAMES[thickness_axis],
        "width_scale": width_scale,
        "height_scale": height_scale,
        "thickness_scale": thickness_scale,
        "determinant": float(np.linalg.det(linear)),
    }
    return linear, translation, info


def normalize_asset(plan: AssetPlan) -> dict[str, Any]:
    gltf, bin_chunk = load_glb(plan.source)
    world_matrices = collect_world_matrices(gltf)
    source_bounds = compute_world_bounds(gltf, bin_chunk, world_matrices)
    linear, translation, axis_info = normalization_linear(
        source_bounds,
        plan.target_width,
        plan.target_height,
        plan.target_thickness,
    )
    normal_linear = np.linalg.inv(linear).T

    seen_positions: dict[int, np.ndarray] = {}
    for node_index, _primitive_index, primitive in primitive_node_refs(gltf):
        attributes = primitive.get("attributes", {})
        position_index = attributes.get("POSITION")
        if position_index is None:
            continue
        position_index = int(position_index)
        matrix = world_matrices[node_index]
        world_linear = matrix[:3, :3]

        if position_index in seen_positions:
            current_matrix = seen_positions[position_index]
            if not np.allclose(current_matrix, matrix, atol=1e-7):
                raise GlbError(f"POSITION accessor {position_index} is instanced with different transforms")
            continue
        seen_positions[position_index] = matrix.copy()

        positions = read_accessor(gltf, bin_chunk, position_index).astype(np.float64)
        world_positions = transform_points(positions, matrix)
        normalized_positions = transform_vectors(world_positions, linear) + translation
        write_accessor(gltf, bin_chunk, position_index, normalized_positions.astype(np.float32))

        normal_index = attributes.get("NORMAL")
        if normal_index is not None:
            normals = read_accessor(gltf, bin_chunk, int(normal_index)).astype(np.float64)
            world_normals = normalize_vectors(transform_vectors(normals, np.linalg.inv(world_linear).T))
            normalized_normals = normalize_vectors(transform_vectors(world_normals, normal_linear))
            write_accessor(gltf, bin_chunk, int(normal_index), normalized_normals.astype(np.float32))

        tangent_index = attributes.get("TANGENT")
        if tangent_index is not None:
            tangents = read_accessor(gltf, bin_chunk, int(tangent_index)).astype(np.float64)
            tangent_xyz = tangents[:, :3]
            world_tangents = normalize_vectors(transform_vectors(tangent_xyz, world_linear))
            normalized_tangents = normalize_vectors(transform_vectors(world_tangents, linear))
            tangents[:, :3] = normalized_tangents
            write_accessor(gltf, bin_chunk, int(tangent_index), tangents.astype(np.float32))

    for node in gltf.get("nodes", []):
        node.pop("translation", None)
        node.pop("rotation", None)
        node.pop("scale", None)
        node.pop("matrix", None)

    output_bounds = compute_world_bounds(gltf, bin_chunk, collect_world_matrices(gltf))
    save_glb(plan.output, gltf, bin_chunk)

    return {
        "source": str(plan.source),
        "output": str(plan.output),
        "asset_kind": plan.asset_kind,
        "width_label": plan.width_label,
        "target_width": plan.target_width,
        "target_height": plan.target_height,
        "target_thickness": plan.target_thickness,
        "source_min": vector_to_text(source_bounds.minimum),
        "source_extent": vector_to_text(source_bounds.extent),
        "output_min": vector_to_text(output_bounds.minimum),
        "output_extent": vector_to_text(output_bounds.extent),
        **axis_info,
    }


def vector_to_text(vector: np.ndarray) -> str:
    return ";".join(f"{float(value):.6f}" for value in vector.tolist())


def width_from_name(path: Path) -> tuple[str, float]:
    match = re.search(r"(?:^|_)([124])m(?:_|\.|$)", path.name, flags=re.IGNORECASE)
    if not match:
        raise GlbError(f"Cannot infer width from filename: {path}")
    nominal = int(match.group(1))
    return f"{nominal}m", float(nominal) + 0.1


def canonical_wall_name(path: Path, width_label: str) -> str:
    stem = path.stem
    stem = re.sub(r"_0+1_$", "", stem)
    stem = re.sub(r"_00001_$", "", stem)
    if not re.search(rf"_{re.escape(width_label)}$", stem):
        stem = re.sub(r"_(?:1m|2m|4m)(?:_\d+_)?$", f"_{width_label}", stem)
    return stem + ".glb"


def discover_plans(input_dir: Path, output_dir: Path, height: float, thickness: float, include_voutes: bool) -> list[AssetPlan]:
    plans: list[AssetPlan] = []
    arch_files = []
    wall_files = []
    for path in sorted(input_dir.rglob("*.glb")):
        is_arch = path.parent.name.lower() != input_dir.name.lower()
        if is_arch:
            arch_files.append(path)
        else:
            wall_files.append(path)

    for path in wall_files:
        width_label, target_width = width_from_name(path)
        plans.append(
            AssetPlan(
                source=path,
                output=output_dir / "murs" / canonical_wall_name(path, width_label),
                asset_kind="mur",
                width_label=width_label,
                target_width=target_width,
                target_height=height,
                target_thickness=thickness,
            )
        )

    if include_voutes:
        width_cycle = [("1m", 1.1), ("2m", 2.1), ("4m", 4.1)]
        for index, path in enumerate(arch_files):
            family = index // len(width_cycle) + 1
            width_label, target_width = width_cycle[index % len(width_cycle)]
            name = f"voute_noire_{family:02d}_{width_label}.glb"
            plans.append(
                AssetPlan(
                    source=path,
                    output=output_dir / "voutes" / name,
                    asset_kind="voute",
                    width_label=width_label,
                    target_width=target_width,
                    target_height=height,
                    target_thickness=thickness,
                )
            )
    return plans


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validate_rows(rows: list[dict[str, Any]], tolerance: float) -> list[str]:
    errors: list[str] = []
    for row in rows:
        extent = [float(value) for value in row["output_extent"].split(";")]
        expected = [float(row["target_width"]), float(row["target_height"]), float(row["target_thickness"])]
        for axis_name, actual, target in zip(AXIS_NAMES, extent, expected):
            if math.fabs(actual - target) > tolerance:
                errors.append(f"{row['output']} {axis_name}: {actual:.6f} != {target:.6f}")
        output_min = [float(value) for value in row["output_min"].split(";")]
        if abs(output_min[1]) > tolerance:
            errors.append(f"{row['output']} pivot Y min is not 0: {output_min[1]:.6f}")
    return errors


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def ensure_safe_clean_target(output_dir: Path, input_dir: Path) -> None:
    resolved_output = output_dir.resolve()
    resolved_input = input_dir.resolve()
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()
    drive_root = Path(resolved_output.anchor).resolve()

    forbidden = {drive_root, cwd, home, resolved_input}
    if resolved_output in forbidden:
        raise GlbError(f"Refusing to clean unsafe output directory: {resolved_output}")
    if is_relative_to(resolved_input, resolved_output):
        raise GlbError(f"Refusing to clean a parent of the input directory: {resolved_output}")
    if len(resolved_output.parts) <= len(drive_root.parts) + 1:
        raise GlbError(f"Refusing to clean a broad top-level directory: {resolved_output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize wall/vault GLB scale, orientation and bottom-center pivot.")
    parser.add_argument("--input-dir", required=True, help="Directory containing source GLB files to normalize.")
    parser.add_argument("--output-dir", required=True, help="Directory where normalized GLB files and the CSV manifest are written.")
    parser.add_argument("--height", type=float, default=3.0)
    parser.add_argument("--thickness", type=float, default=0.35)
    parser.add_argument("--tolerance", type=float, default=0.002)
    parser.add_argument("--clean-output", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-voutes", action="store_true", help="Also process GLB files in subfolders such as the misnamed vault folder.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if args.clean_output and output_dir.exists():
        ensure_safe_clean_target(output_dir, input_dir)
        shutil.rmtree(output_dir)

    plans = discover_plans(input_dir, output_dir, args.height, args.thickness, args.include_voutes)
    if args.dry_run:
        for plan in plans:
            print(f"{plan.asset_kind}: {plan.source} -> {plan.output}")
        print(f"Total: {len(plans)}")
        return 0

    rows: list[dict[str, Any]] = []
    for index, plan in enumerate(plans, start=1):
        print(f"[{index:02d}/{len(plans):02d}] {plan.source.name} -> {plan.output.relative_to(output_dir)}")
        rows.append(normalize_asset(plan))

    manifest_path = output_dir / "manifest_normalisation.csv"
    write_manifest(manifest_path, rows)

    errors = validate_rows(rows, args.tolerance)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2

    print(f"Normalized {len(rows)} GLB files")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GlbError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
