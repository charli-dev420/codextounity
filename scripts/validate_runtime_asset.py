from __future__ import annotations

import argparse
import base64
import json
import math
import re
import struct
from pathlib import Path
from typing import Any

import numpy as np

from normalize_wall_glbs import (
    GlbError,
    collect_world_matrices,
    load_glb,
    primitive_node_refs,
    read_accessor,
    transform_points,
)
from asset_profile_defaults import resolve_profile_target


REQUIRED_PROFILES = {"wall", "door", "prop", "weapon", "pickup", "character", "equipment", "terrain_piece"}
MANIFEST_REQUIRED_FIELDS = {
    "schema",
    "assetId",
    "jobId",
    "requestId",
    "unityReadyMesh",
    "validationPassed",
    "validationErrors",
    "validationWarnings",
    "assetManifestPath",
    "generationManifestPath",
    "unityImportManifestPath",
}
CHECK_FAMILIES = (
    "profile",
    "format",
    "glb",
    "bounds",
    "fitAxis",
    "pivot",
    "triangles",
    "textures",
    "meshNodes",
    "geometry",
    "semantics",
    "manifest",
    "normalization",
)
AXES = ("x", "y", "z")
FURNITURE_TOKENS = {"bed", "chair", "table", "sofa", "lamp", "cabinet", "shelf", "furniture"}
FLOOR_TOKENS = {"floor", "ground", "tile"}
DOOR_TOKENS = {"door", "gate"}
WALL_SUBPROFILE_TOKENS = {"window": "window_wall", "mirror": "wall_mirror"}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_profile(profile_id: str, profiles_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if profile_id not in REQUIRED_PROFILES:
        errors.append(f"unknown profile '{profile_id}'; expected one of {sorted(REQUIRED_PROFILES)}")
        return None, errors
    path = profiles_dir / f"{profile_id}.json"
    if not path.is_file():
        errors.append(f"profile file missing: {path}")
        return None, errors
    try:
        return load_json(path), errors
    except Exception as exc:
        errors.append(f"profile JSON parse failed for {path.name}: {exc}")
        return None, errors


def init_checks() -> dict[str, dict[str, Any]]:
    return {family: {"valid": True, "errors": [], "warnings": []} for family in CHECK_FAMILIES}


def add_error(checks: dict[str, dict[str, Any]], errors: list[str], family: str, message: str) -> None:
    entry = checks.setdefault(family, {"valid": True, "errors": [], "warnings": []})
    entry["valid"] = False
    entry["errors"].append(message)
    errors.append(message)


def add_warning(checks: dict[str, dict[str, Any]], warnings: list[str], family: str, message: str) -> None:
    entry = checks.setdefault(family, {"valid": True, "errors": [], "warnings": []})
    entry["warnings"].append(message)
    warnings.append(message)


def record_errors(checks: dict[str, dict[str, Any]], errors: list[str], family: str, messages: list[str]) -> None:
    for message in messages:
        add_error(checks, errors, family, message)


def record_warnings(checks: dict[str, dict[str, Any]], warnings: list[str], family: str, messages: list[str]) -> None:
    for message in messages:
        add_warning(checks, warnings, family, message)


def bounds_from_values(minimum: list[float], maximum: list[float]) -> dict[str, Any]:
    extent = [maximum[i] - minimum[i] for i in range(3)]
    center = [(minimum[i] + maximum[i]) / 2.0 for i in range(3)]
    return {"min": minimum, "max": maximum, "extent": extent, "center": center}


def axis_ratios(extent: list[float]) -> dict[str, float | None]:
    values = [float(v) for v in extent]
    positive = [v for v in values if v > 0]
    if not positive:
        return {"maxToMin": None, "xToY": None, "xToZ": None, "yToZ": None}
    return {
        "maxToMin": max(positive) / min(positive),
        "xToY": values[0] / values[1] if values[1] > 0 else None,
        "xToZ": values[0] / values[2] if values[2] > 0 else None,
        "yToZ": values[1] / values[2] if values[2] > 0 else None,
    }


def dominant_axes(extent: list[float]) -> list[str]:
    return [AXES[index] for index in sorted(range(3), key=lambda axis: float(extent[axis]), reverse=True)]


def inspect_glb_geometry(
    gltf: dict[str, Any],
    bin_chunk: bytearray,
    world_matrices: dict[int, np.ndarray],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    refs = primitive_node_refs(gltf)
    mesh_nodes = [node for node in gltf.get("nodes", []) or [] if node.get("mesh") is not None]
    geometry: dict[str, Any] = {
        "validGlb": True,
        "vertexCount": 0,
        "triangleCount": 0,
        "meshCount": len(gltf.get("meshes", []) or []),
        "materialCount": len(gltf.get("materials", []) or []),
        "nodeCount": len(gltf.get("nodes", []) or []),
        "meshNodeCount": len(mesh_nodes),
        "primitiveCount": len(refs),
        "positionPrimitiveCount": 0,
        "missingPositionPrimitiveCount": 0,
        "nonFinitePositionCount": 0,
        "bounds": None,
        "aspectRatios": {"maxToMin": None, "xToY": None, "xToZ": None, "yToZ": None},
        "dominantAxes": [],
        "degenerateDimensions": False,
        "flatDimensions": [],
        "aberrantDimensions": False,
        "readErrors": [],
    }
    world_positions: list[np.ndarray] = []
    for node_index, _primitive_index, primitive in refs:
        attributes = primitive.get("attributes") or {}
        position_index = attributes.get("POSITION")
        if position_index is None:
            geometry["missingPositionPrimitiveCount"] += 1
            continue
        geometry["positionPrimitiveCount"] += 1
        try:
            positions = read_accessor(gltf, bin_chunk, int(position_index)).astype(np.float64)
        except Exception as exc:
            geometry["readErrors"].append(f"POSITION accessor read failed: {exc}")
            continue
        geometry["vertexCount"] += int(positions.shape[0])
        if positions.size and not np.isfinite(positions).all():
            geometry["nonFinitePositionCount"] += int(np.size(positions) - np.isfinite(positions).sum())
        matrix = world_matrices.get(node_index)
        if matrix is None:
            warnings.append(f"mesh node {node_index} is not in the active scene; using local transform for validation")
            matrix = np.eye(4, dtype=np.float64)
        if positions.shape[0] > 0:
            transformed = transform_points(positions, matrix)
            world_positions.append(transformed)
            if not np.isfinite(transformed).all():
                geometry["nonFinitePositionCount"] += int(np.size(transformed) - np.isfinite(transformed).sum())

        mode = int(primitive.get("mode", 4))
        if mode != 4:
            warnings.append(f"primitive mode {mode} is not TRIANGLES; triangle count is approximate")
        if "indices" in primitive:
            accessor = gltf["accessors"][int(primitive["indices"])]
            geometry["triangleCount"] += int(int(accessor.get("count", 0)) // 3)
        else:
            geometry["triangleCount"] += int(positions.shape[0] // 3)

    if world_positions:
        combined = np.vstack(world_positions)
        minimum = [float(v) for v in combined.min(axis=0).tolist()]
        maximum = [float(v) for v in combined.max(axis=0).tolist()]
        bounds = bounds_from_values(minimum, maximum)
        extent = [float(value) for value in bounds["extent"]]
        max_extent = max(extent) if extent else 0.0
        flat_threshold = max(1e-7, max_extent * 0.0005)
        bounds["flatThreshold"] = flat_threshold
        geometry["bounds"] = bounds
        geometry["aspectRatios"] = axis_ratios(extent)
        geometry["dominantAxes"] = dominant_axes(extent)
        geometry["flatDimensions"] = [AXES[index] for index, value in enumerate(extent) if value <= flat_threshold]
        geometry["degenerateDimensions"] = bool(geometry["flatDimensions"])
        ratio = geometry["aspectRatios"].get("maxToMin")
        geometry["aberrantDimensions"] = bool(ratio is not None and ratio > 50.0)
    return geometry, warnings


def buffer_view_bytes(gltf: dict[str, Any], bin_chunk: bytearray, buffer_view_index: int) -> bytes:
    view = gltf["bufferViews"][buffer_view_index]
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", 0))
    return bytes(bin_chunk[offset : offset + length])


def png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", data[16:24])
    return None


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2:
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 <= len(data):
                height = int.from_bytes(data[index + 3 : index + 5], "big")
                width = int.from_bytes(data[index + 5 : index + 7], "big")
                return width, height
            return None
        index += segment_length
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    return png_size(data) or jpeg_size(data)


def data_uri_bytes(uri: str) -> bytes | None:
    if not uri.startswith("data:") or "," not in uri:
        return None
    _meta, payload = uri.split(",", 1)
    try:
        return base64.b64decode(payload)
    except Exception:
        return None


def detect_texture_sizes(gltf: dict[str, Any], bin_chunk: bytearray, mesh_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    textures: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, image in enumerate(gltf.get("images", []) or []):
        size: tuple[int, int] | None = None
        source = ""
        if isinstance(image.get("extras"), dict):
            width = image["extras"].get("width")
            height = image["extras"].get("height")
            if isinstance(width, int) and isinstance(height, int):
                size = (width, height)
                source = "extras"
        if size is None and image.get("bufferView") is not None:
            try:
                size = image_size(buffer_view_bytes(gltf, bin_chunk, int(image["bufferView"])))
                source = "bufferView"
            except Exception as exc:
                warnings.append(f"image {index}: could not inspect bufferView texture dimensions: {exc}")
        if size is None and isinstance(image.get("uri"), str):
            uri = image["uri"]
            data = data_uri_bytes(uri)
            if data is not None:
                size = image_size(data)
                source = "data-uri"
            elif not uri.startswith(("http://", "https://")):
                candidate = (mesh_path.parent / uri).resolve()
                if candidate.is_file():
                    try:
                        size = image_size(candidate.read_bytes())
                        source = str(candidate)
                    except Exception as exc:
                        warnings.append(f"image {index}: could not inspect texture file {candidate}: {exc}")
        entry: dict[str, Any] = {"index": index}
        if size is None:
            entry["detected"] = False
        else:
            entry.update({"detected": True, "width": size[0], "height": size[1], "source": source})
        textures.append(entry)
    return textures, warnings


def parse_target_bounds_text(value: Any) -> list[float] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parts = [float(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]
    return parts if len(parts) == 3 else None


def profile_target_bounds(profile: dict[str, Any]) -> list[float] | None:
    target = profile.get("targetBounds") or {}
    values: list[float] = []
    for axis in AXES:
        expected = target.get(axis)
        if not isinstance(expected, (int, float)):
            return None
        values.append(float(expected))
    return values


def validate_bounds(profile: dict[str, Any], bounds: dict[str, Any], normalization: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    bounds_errors: list[str] = []
    fit_axis_errors: list[str] = []
    tolerance = float((profile.get("validationRules") or {}).get("boundsTolerance") or 0.0)
    expected_values = profile_target_bounds(profile)
    if expected_values is None:
        bounds_errors.append(f"{profile.get('profileId')}: targetBounds must be numeric")
        return bounds_errors, fit_axis_errors

    actual_values = [float(value) for value in bounds["extent"]]
    for index, axis in enumerate(AXES):
        if actual_values[index] - expected_values[index] > tolerance:
            bounds_errors.append(
                f"{profile.get('profileId')}: {axis} extent {actual_values[index]:.6f} exceeds target envelope {expected_values[index]:.6f}"
            )

    transform = normalization.get("transform") if isinstance(normalization, dict) else None
    if isinstance(transform, dict) and transform.get("proportionsPreserved") is True:
        report_target = parse_target_bounds_text(transform.get("targetBounds"))
        if report_target is not None:
            for index, axis in enumerate(AXES):
                if abs(report_target[index] - expected_values[index]) > tolerance:
                    bounds_errors.append(
                        f"{profile.get('profileId')}: normalization report targetBounds {axis}={report_target[index]:.6f} does not match resolved profile target {expected_values[index]:.6f}"
                    )
        resolved_fit_axis = str(((profile.get("normalizationDefaults") or {}).get("fitAxis")) or "contain").lower()
        report_fit_axis = str(transform.get("fitAxis") or resolved_fit_axis).lower()
        if report_fit_axis != resolved_fit_axis:
            fit_axis_errors.append(
                f"{profile.get('profileId')}: normalization report fitAxis {report_fit_axis} does not match resolved profile fitAxis {resolved_fit_axis}"
            )
        fit_axis = report_fit_axis
        if fit_axis in AXES:
            index = AXES.index(fit_axis)
            if abs(actual_values[index] - expected_values[index]) > tolerance:
                fit_axis_errors.append(
                    f"{profile.get('profileId')}: fitAxis {fit_axis} extent {actual_values[index]:.6f} differs from target {expected_values[index]:.6f}"
                )
        elif fit_axis == "contain":
            if not any(abs(actual_values[index] - expected_values[index]) <= tolerance for index in range(3)):
                fit_axis_errors.append(f"{profile.get('profileId')}: contain fit does not reach any target envelope axis")
        else:
            fit_axis_errors.append(f"{profile.get('profileId')}: invalid fitAxis {fit_axis}")
    return bounds_errors, fit_axis_errors


def validate_pivot(profile: dict[str, Any], bounds: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tolerance = float((profile.get("validationRules") or {}).get("boundsTolerance") or 0.0)
    pivot = profile.get("pivotMode")
    minimum = bounds["min"]
    center = bounds["center"]
    if pivot == "bottom-center":
        if abs(minimum[1]) > tolerance:
            errors.append(f"{profile.get('profileId')}: bottom-center pivot expects min Y at 0, got {minimum[1]:.6f}")
        if abs(center[0]) > tolerance or abs(center[2]) > tolerance:
            errors.append(f"{profile.get('profileId')}: bottom-center pivot expects X/Z centered on origin, got center {center}")
    elif pivot == "center":
        if any(abs(value) > tolerance for value in center):
            errors.append(f"{profile.get('profileId')}: center pivot expects bounds centered on origin, got center {center}")
    elif pivot == "origin":
        if any(abs(value) > tolerance for value in minimum):
            errors.append(f"{profile.get('profileId')}: origin pivot expects min bounds at origin, got min {minimum}")
    return errors


def validate_geometry_integrity(profile_id: str, geometry: dict[str, Any], tolerance: float) -> list[str]:
    errors: list[str] = []
    if geometry.get("meshCount", 0) <= 0:
        errors.append(f"{profile_id}: GLB contains no meshes")
    if geometry.get("primitiveCount", 0) <= 0:
        errors.append(f"{profile_id}: GLB contains no mesh primitives")
    if geometry.get("missingPositionPrimitiveCount", 0) > 0:
        errors.append(f"{profile_id}: {geometry['missingPositionPrimitiveCount']} primitive(s) have no POSITION accessor")
    if geometry.get("positionPrimitiveCount", 0) <= 0:
        errors.append(f"{profile_id}: GLB contains no POSITION accessor")
    if geometry.get("vertexCount", 0) <= 0:
        errors.append(f"{profile_id}: mesh has zero vertices")
    if geometry.get("triangleCount", 0) <= 0:
        errors.append(f"{profile_id}: mesh has zero triangles")
    if geometry.get("nonFinitePositionCount", 0) > 0:
        errors.append(f"{profile_id}: mesh contains non-finite vertex positions")
    for read_error in geometry.get("readErrors", []) or []:
        errors.append(f"{profile_id}: {read_error}")

    bounds = geometry.get("bounds")
    if not isinstance(bounds, dict):
        errors.append(f"{profile_id}: mesh bounds could not be computed")
        return errors
    extent = [float(value) for value in bounds.get("extent", [])]
    if len(extent) != 3 or not all(math.isfinite(value) for value in extent):
        errors.append(f"{profile_id}: mesh bounds are not finite")
        return errors
    zero_threshold = max(1e-7, tolerance * 0.01)
    flat_axes = [AXES[index] for index, value in enumerate(extent) if value <= zero_threshold]
    if flat_axes:
        errors.append(f"{profile_id}: mesh has flat or zero dimensions on axis/axes {', '.join(flat_axes)}")
    if geometry.get("aberrantDimensions"):
        errors.append(f"{profile_id}: mesh dimensions are aberrant; max/min extent ratio exceeds 50")
    return errors


def validate_profile_geometry(profile_id: str, sub_profile_id: str, geometry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    bounds = geometry.get("bounds")
    if not isinstance(bounds, dict):
        return errors
    x, y, z = [float(value) for value in bounds["extent"]]
    sub = str(sub_profile_id or "").lower()
    if profile_id == "door":
        if y < x * 1.2 or y < z * 4.0:
            errors.append("door: semantic geometry expects a vertical door with height dominant on Y")
        if z > max(x, 1e-9) * 0.35:
            errors.append("door: semantic geometry expects a thin depth relative to width")
    elif profile_id == "terrain_piece":
        if y > max(x, z) * 0.35 or x < y * 2.0 or z < y * 2.0:
            errors.append("terrain_piece: semantic geometry expects a horizontal floor/terrain piece with low Y height")
    elif profile_id == "wall":
        if sub == "wall_mirror":
            if y < x * 1.2 or y < z * 4.0:
                errors.append("wall/wall_mirror: semantic geometry expects a vertical mirror with height dominant on Y")
        else:
            if x < y * 1.05 or y < z * 2.0:
                errors.append("wall: semantic geometry expects a wide vertical wall panel")
        if z > max(x, y, 1e-9) * 0.25:
            errors.append("wall: semantic geometry expects a thin depth")
    elif profile_id == "weapon":
        if x < max(y, z) * 1.5:
            errors.append("weapon: semantic geometry expects length dominant on X")
    elif profile_id == "character":
        if y < max(x, z) * 1.4:
            errors.append("character: semantic geometry expects height dominant on Y")
    return errors


def validate_manifest(path: Path) -> tuple[list[str], list[str], dict[str, Any] | None]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return [f"manifest not found: {path}"], warnings, None
    try:
        data = load_json(path)
    except Exception as exc:
        return [f"manifest JSON parse failed: {exc}"], warnings, None
    missing = sorted(field for field in MANIFEST_REQUIRED_FIELDS if field not in data)
    if missing:
        errors.append(f"manifest missing required fields: {', '.join(missing)}")
    if data.get("schema") != "codex.unityResultManifest.v2":
        errors.append("manifest schema must be codex.unityResultManifest.v2")
    for field in ("assetManifestPath", "generationManifestPath", "unityImportManifestPath"):
        value = data.get(field)
        if isinstance(value, str) and value:
            if not Path(value).is_file():
                errors.append(f"manifest bundle file missing: {field} -> {value}")
    return errors, warnings, data


def semantic_hints(mesh: Path, asset_name: str = "", manifest_data: dict[str, Any] | None = None) -> dict[str, Any]:
    sources: dict[str, str] = {"meshStem": mesh.stem}
    if asset_name:
        sources["assetName"] = asset_name
    if isinstance(manifest_data, dict):
        for key in ("assetId", "requestId"):
            value = manifest_data.get(key)
            if isinstance(value, str) and value:
                sources[key] = value
    tokens: set[str] = set()
    for value in sources.values():
        tokens.update(TOKEN_RE.findall(value.lower().replace("-", "_")))
    return {"sources": sources, "tokens": sorted(tokens)}


def validate_semantics(profile_id: str, sub_profile_id: str, hints: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tokens = set(hints.get("tokens") or [])
    sub = str(sub_profile_id or "").lower()
    furniture = sorted(tokens & FURNITURE_TOKENS)
    if furniture and profile_id in {"wall", "door", "terrain_piece"}:
        errors.append(f"{profile_id}: semantic token(s) {', '.join(furniture)} look like furniture/decor, not this profile")
    floor_tokens = sorted(tokens & FLOOR_TOKENS)
    if floor_tokens and profile_id != "terrain_piece":
        if not (profile_id == "wall" and sub in {"window_wall", "wall_mirror"}):
            errors.append(f"{profile_id}: semantic token(s) {', '.join(floor_tokens)} should use profile terrain_piece")
    door_tokens = sorted(tokens & DOOR_TOKENS)
    if door_tokens and profile_id != "door":
        errors.append(f"{profile_id}: semantic token(s) {', '.join(door_tokens)} should use profile door")
    for token, expected_sub in WALL_SUBPROFILE_TOKENS.items():
        if token in tokens and not (profile_id == "wall" and sub == expected_sub):
            errors.append(f"{profile_id}: semantic token '{token}' requires wall subProfile {expected_sub}")
    return errors


def validate_runtime_asset(
    mesh: Path,
    profile_id: str,
    profiles_dir: Path,
    sub_profile_id: str = "",
    normalization_report: Path | None = None,
    manifest: Path | None = None,
    asset_name: str = "",
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks = init_checks()
    geometry: dict[str, Any] | None = None
    profile, profile_errors = load_profile(profile_id, profiles_dir)
    record_errors(checks, errors, "profile", profile_errors)
    effective_profile = profile
    profile_resolution: dict[str, Any] | None = None
    if profile:
        try:
            profile_resolution = resolve_profile_target(profile_id, profiles_dir, sub_profile_id)
            effective_profile = {
                **profile,
                "targetBounds": profile_resolution["targetBounds"],
                "unityCategory": profile_resolution["unityCategory"],
                "normalizationDefaults": profile_resolution["normalizationDefaults"],
            }
        except Exception as exc:
            add_error(checks, errors, "profile", f"{profile_id}: profile/subProfile resolution failed: {exc}")
    resolved_sub_profile = profile_resolution["subProfileId"] if profile_resolution else sub_profile_id

    mesh = mesh.resolve()
    if not mesh.is_file():
        add_error(checks, errors, "glb", f"mesh not found: {mesh}")
        return build_report(
            mesh,
            profile_id,
            profiles_dir,
            effective_profile,
            errors,
            warnings,
            checks,
            mesh_summary={"path": str(mesh), "exists": False},
            sub_profile_id=resolved_sub_profile,
            profile_resolution=profile_resolution,
            geometry=geometry,
            semantic_hints_data=semantic_hints(mesh, asset_name),
        )

    manifest_data = None
    if manifest:
        manifest_errors, manifest_warnings, manifest_data = validate_manifest(manifest)
        record_errors(checks, errors, "manifest", manifest_errors)
        record_warnings(checks, warnings, "manifest", manifest_warnings)

    normalization_data: dict[str, Any] | None = None
    if normalization_report:
        if not normalization_report.is_file():
            add_error(checks, errors, "normalization", f"normalization report not found: {normalization_report}")
        else:
            try:
                normalization_data = load_json(normalization_report)
                validation = normalization_data.get("validation")
                if isinstance(validation, dict) and validation.get("valid") is False:
                    add_error(checks, errors, "normalization", f"normalization report is invalid: {validation.get('errors')}")
                transform = normalization_data.get("transform")
                if not isinstance(transform, dict) or transform.get("proportionsPreserved") is not True:
                    add_error(
                        checks,
                        errors,
                        "normalization",
                        "normalization report must prove proportionsPreserved=true; non-uniform scale would deform the asset",
                    )
            except Exception as exc:
                add_error(checks, errors, "normalization", f"normalization report JSON parse failed: {exc}")

    profile_rules = (effective_profile or {}).get("validationRules") or {}
    allowed_formats = {str(item).lower().lstrip(".") for item in profile_rules.get("allowedFormats", [])}
    suffix = mesh.suffix.lower().lstrip(".")
    if allowed_formats and suffix not in allowed_formats:
        add_error(checks, errors, "format", f"{profile_id}: format .{suffix or '<none>'} is not allowed; expected one of {sorted(allowed_formats)}")

    mesh_summary: dict[str, Any] = {"path": str(mesh), "exists": True, "format": suffix, "sizeBytes": mesh.stat().st_size}
    if mesh.stat().st_size <= 0:
        add_error(checks, errors, "glb", "mesh file is empty")

    if suffix == "glb" and mesh.stat().st_size > 0:
        try:
            gltf, bin_chunk = load_glb(mesh)
            world_matrices = collect_world_matrices(gltf)
            geometry, geometry_warnings = inspect_glb_geometry(gltf, bin_chunk, world_matrices)
            record_warnings(checks, warnings, "geometry", geometry_warnings)
            texture_sizes, texture_warnings = detect_texture_sizes(gltf, bin_chunk, mesh)
            record_warnings(checks, warnings, "textures", texture_warnings)
            geometry["textures"] = texture_sizes
            mesh_summary.update(
                {
                    "validGlb": True,
                    "triangleCount": geometry["triangleCount"],
                    "meshCount": geometry["meshCount"],
                    "meshNodeCount": geometry["meshNodeCount"],
                    "primitiveCount": geometry["primitiveCount"],
                    "bounds": geometry["bounds"],
                    "textures": texture_sizes,
                }
            )
            tolerance = float(profile_rules.get("boundsTolerance") or 0.002)
            record_errors(checks, errors, "geometry", validate_geometry_integrity(profile_id, geometry, tolerance))
            if effective_profile:
                max_triangles = profile_rules.get("maxTriangleCount")
                if isinstance(max_triangles, int) and geometry["triangleCount"] > max_triangles:
                    add_error(checks, errors, "triangles", f"{profile_id}: triangle count {geometry['triangleCount']} exceeds maxTriangleCount {max_triangles}")
                if profile_rules.get("singleObject") is True and geometry["meshNodeCount"] != 1:
                    add_error(checks, errors, "meshNodes", f"{profile_id}: singleObject expects exactly one mesh node, found {geometry['meshNodeCount']}")
                if profile_rules.get("singleObject") is True and geometry["primitiveCount"] > 1 and geometry["triangleCount"] > 0:
                    add_warning(checks, warnings, "meshNodes", f"{profile_id}: singleObject profile has {geometry['primitiveCount']} primitives; review material/object split")
                if isinstance(geometry.get("bounds"), dict):
                    bounds_errors, fit_axis_errors = validate_bounds(effective_profile, geometry["bounds"], normalization_data)
                    record_errors(checks, errors, "bounds", bounds_errors)
                    record_errors(checks, errors, "fitAxis", fit_axis_errors)
                    record_errors(checks, errors, "pivot", validate_pivot(effective_profile, geometry["bounds"]))
                    record_errors(checks, errors, "geometry", validate_profile_geometry(profile_id, resolved_sub_profile, geometry))
                max_texture = profile_rules.get("maxTextureSize")
                if isinstance(max_texture, int):
                    for texture in texture_sizes:
                        if texture.get("detected") and max(int(texture["width"]), int(texture["height"])) > max_texture:
                            add_error(checks, errors, "textures", f"{profile_id}: texture {texture['index']} exceeds maxTextureSize {max_texture}")
        except GlbError as exc:
            mesh_summary["validGlb"] = False
            add_error(checks, errors, "glb", f"GLB validation failed: {exc}")
        except Exception as exc:
            mesh_summary["validGlb"] = False
            add_error(checks, errors, "glb", f"GLB inspection failed: {exc}")
    elif suffix != "glb":
        add_warning(checks, warnings, "glb", "deep geometry validation is currently implemented for GLB files only")

    if normalization_report and normalization_report.is_file():
        mesh_summary["normalizationReport"] = str(normalization_report.resolve())
        if isinstance(normalization_data, dict):
            mesh_summary["normalization"] = {
                "fitMode": (normalization_data.get("transform") or {}).get("fitMode"),
                "fitAxis": (normalization_data.get("transform") or {}).get("fitAxis"),
                "proportionsPreserved": (normalization_data.get("transform") or {}).get("proportionsPreserved"),
            }

    hint_data = semantic_hints(mesh, asset_name, manifest_data)
    record_errors(checks, errors, "semantics", validate_semantics(profile_id, resolved_sub_profile, hint_data))

    return build_report(
        mesh,
        profile_id,
        profiles_dir,
        effective_profile,
        errors,
        warnings,
        checks,
        mesh_summary,
        manifest_data,
        sub_profile_id=resolved_sub_profile,
        profile_resolution=profile_resolution,
        geometry=geometry,
        semantic_hints_data=hint_data,
    )


def build_report(
    mesh: Path,
    profile_id: str,
    profiles_dir: Path,
    profile: dict[str, Any] | None,
    errors: list[str],
    warnings: list[str],
    checks: dict[str, dict[str, Any]],
    mesh_summary: dict[str, Any] | None = None,
    manifest_data: dict[str, Any] | None = None,
    sub_profile_id: str = "",
    profile_resolution: dict[str, Any] | None = None,
    geometry: dict[str, Any] | None = None,
    semantic_hints_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = (profile or {}).get("validationRules") or {}
    return {
        "schema": "codex.runtimeAssetValidation.v2",
        "valid": not errors,
        "profile": profile_id,
        "subProfile": profile_resolution["subProfileId"] if profile_resolution else sub_profile_id,
        "profilesDir": str(profiles_dir),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "semanticHints": semantic_hints_data or semantic_hints(mesh),
        "geometry": geometry,
        "mesh": mesh_summary or {"path": str(mesh), "exists": mesh.is_file()},
        "profileSummary": {
            "targetBounds": (profile or {}).get("targetBounds"),
            "faceBudget": (profile or {}).get("faceBudget"),
            "textureSize": (profile or {}).get("textureSize"),
            "pivotMode": (profile or {}).get("pivotMode"),
            "normalizationDefaults": (profile or {}).get("normalizationDefaults"),
            "resolvedFitAxis": ((profile or {}).get("normalizationDefaults") or {}).get("fitAxis"),
            "allowedFormats": rules.get("allowedFormats"),
            "maxTriangleCount": rules.get("maxTriangleCount"),
            "maxTextureSize": rules.get("maxTextureSize"),
            "boundsTolerance": rules.get("boundsTolerance"),
            "singleObject": rules.get("singleObject"),
            "boundsMode": "max-envelope",
        },
        "manifest": {
            "provided": manifest_data is not None,
            "assetId": manifest_data.get("assetId") if manifest_data else None,
            "status": manifest_data.get("status") if manifest_data else None,
            "validationPassed": manifest_data.get("validationPassed") if manifest_data else None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate one runtime mesh against a Codex Asset Factory profile without generation.")
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--profile", required=True, choices=sorted(REQUIRED_PROFILES))
    parser.add_argument("--sub-profile", default="")
    parser.add_argument("--asset-name", default="", help="Optional explicit asset name used for deterministic semantic checks.")
    parser.add_argument("--profiles-dir", default=str(Path(__file__).resolve().parents[1] / "configs" / "asset-profiles"))
    parser.add_argument("--normalization-report", default="")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default="", help="Optional path to write the JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_runtime_asset(
        mesh=Path(args.mesh),
        profile_id=args.profile,
        profiles_dir=Path(args.profiles_dir),
        sub_profile_id=args.sub_profile,
        normalization_report=Path(args.normalization_report) if args.normalization_report else None,
        manifest=Path(args.manifest) if args.manifest else None,
        asset_name=args.asset_name,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
    if args.json:
        print(payload)
    else:
        status = "OK" if report["valid"] else "FAILED"
        print(f"Runtime asset validation {status}: {report['profile']}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
