from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def pad4(data: bytes, byte: bytes = b" ") -> bytes:
    return data + byte * ((4 - (len(data) % 4)) % 4)


def write_box(path: Path) -> None:
    positions = [
        0.0, 0.0, 0.0,
        2.0, 0.0, 0.0,
        2.0, 1.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
        2.0, 0.0, 1.0,
        2.0, 1.0, 1.0,
        0.0, 1.0, 1.0,
    ]
    indices = [
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
    gltf = {
        "asset": {"version": "2.0", "generator": "codex create_test_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "CodexTestBox"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [0, 0, 0], "max": [2, 1, 1]},
            {"bufferView": 1, "byteOffset": 0, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_blob = pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"))
    total_length = 12 + 8 + len(json_blob) + 8 + len(bin_blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total_length))
        handle.write(struct.pack("<I4s", len(json_blob), b"JSON"))
        handle.write(json_blob)
        handle.write(struct.pack("<I4s", len(bin_blob), b"BIN\x00"))
        handle.write(bin_blob)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic GLB box for plugin smoke tests.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    write_box(Path(args.out))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
