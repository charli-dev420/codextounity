from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def pad4(data: bytes, byte: bytes = b" ") -> bytes:
    return data + byte * ((4 - (len(data) % 4)) % 4)


def parse_size(value: str) -> tuple[float, float, float]:
    parts = [float(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]
    if len(parts) != 3 or any(part <= 0 for part in parts):
        raise ValueError("--size must contain three positive numbers, e.g. 2,1,1")
    return parts[0], parts[1], parts[2]


def parse_texture_size(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    parts = [int(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]
    if len(parts) != 2 or any(part <= 0 for part in parts):
        raise ValueError("--texture-size must contain two positive integers, e.g. 1024,1024")
    return parts[0], parts[1]


def write_glb(path: Path, gltf: dict, bin_blob: bytes) -> None:
    json_blob = pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"))
    bin_blob = pad4(bin_blob, b"\x00")
    total_length = 12 + 8 + len(json_blob) + 8 + len(bin_blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total_length))
        handle.write(struct.pack("<I4s", len(json_blob), b"JSON"))
        handle.write(json_blob)
        handle.write(struct.pack("<I4s", len(bin_blob), b"BIN\x00"))
        handle.write(bin_blob)


def add_texture_metadata(gltf: dict, texture_size: tuple[int, int] | None) -> None:
    if not texture_size:
        return
    width, height = texture_size
    gltf["images"] = [{"name": "CodexTestTexture", "extras": {"width": width, "height": height}}]
    gltf["textures"] = [{"source": 0}]
    gltf["materials"] = [{"name": "CodexTestMaterial", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            primitive["material"] = 0


def write_empty(path: Path, texture_size: tuple[int, int] | None = None) -> None:
    gltf = {
        "asset": {"version": "2.0", "generator": "codex create_test_glb.py empty"},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "meshes": [],
        "buffers": [{"byteLength": 0}],
    }
    add_texture_metadata(gltf, texture_size)
    write_glb(path, gltf, b"")


def write_box(
    path: Path,
    size: tuple[float, float, float] = (2.0, 1.0, 1.0),
    *,
    zero_triangles: bool = False,
    multi_node: bool = False,
    texture_size: tuple[int, int] | None = None,
) -> None:
    sx, sy, sz = size
    positions = [
        0.0, 0.0, 0.0,
        sx, 0.0, 0.0,
        sx, sy, 0.0,
        0.0, sy, 0.0,
        0.0, 0.0, sz,
        sx, 0.0, sz,
        sx, sy, sz,
        0.0, sy, sz,
    ]
    indices = [] if zero_triangles else [
        0, 1, 2, 0, 2, 3,
        4, 6, 5, 4, 7, 6,
        0, 4, 5, 0, 5, 1,
        3, 2, 6, 3, 6, 7,
        1, 5, 6, 1, 6, 2,
        0, 3, 7, 0, 7, 4,
    ]
    position_bytes = struct.pack("<" + "f" * len(positions), *positions)
    index_offset = len(position_bytes)
    index_bytes = struct.pack("<" + "H" * len(indices), *indices)
    bin_blob = pad4(position_bytes + index_bytes, b"\x00")
    nodes = [{"mesh": 0, "name": "CodexTestBox"}]
    scene_nodes = [0]
    if multi_node:
        nodes.append({"mesh": 0, "name": "CodexTestBoxDuplicate"})
        scene_nodes.append(1)
    gltf = {
        "asset": {"version": "2.0", "generator": "codex create_test_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": scene_nodes}],
        "nodes": nodes,
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [0, 0, 0], "max": [sx, sy, sz]},
            {"bufferView": 1, "byteOffset": 0, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
    }
    add_texture_metadata(gltf, texture_size)
    write_glb(path, gltf, bin_blob)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic GLB box for plugin smoke tests.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--size", default="2,1,1", help="Box size XYZ before normalization.")
    parser.add_argument("--variant", choices=["box", "empty", "zero-triangle", "flat", "multi-node"], default="box")
    parser.add_argument("--texture-size", default="", help="Optional declared texture dimensions WIDTH,HEIGHT in image extras.")
    args = parser.parse_args()
    texture_size = parse_texture_size(args.texture_size)
    if args.variant == "empty":
        write_empty(Path(args.out), texture_size)
    elif args.variant == "zero-triangle":
        write_box(Path(args.out), parse_size(args.size), zero_triangles=True, texture_size=texture_size)
    elif args.variant == "flat":
        sx, _sy, sz = parse_size(args.size)
        write_box(Path(args.out), (sx, 0.0, sz), texture_size=texture_size)
    elif args.variant == "multi-node":
        write_box(Path(args.out), parse_size(args.size), multi_node=True, texture_size=texture_size)
    else:
        write_box(Path(args.out), parse_size(args.size), texture_size=texture_size)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
