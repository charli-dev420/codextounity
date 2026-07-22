from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from asset_profile_defaults import DEFAULT_FIT_AXIS, VALID_FIT_AXES, normalize_alias

REQUIRED_PROFILES = ["wall", "door", "prop", "weapon", "pickup", "character", "equipment", "terrain_piece"]
REQUIRED_TOP_LEVEL = [
    "schema", "profileId", "displayName", "profileType", "aliases", "promptRules", "negativePromptRules",
    "targetBounds", "normalizationDefaults", "faceBudget", "textureSize", "pivotMode", "unityCategory", "generationDefaults",
    "importDefaults", "validationRules",
]
VALID_PIVOTS = {"bottom-center", "center", "origin", "custom", "keep"}
VALID_TEXTURES = {256, 512, 1024, 2048}
VALID_FORMATS = {"glb", "gltf", "obj", "fbx", "dae", "stl"}
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


def validate_bounds(path_name: str, label: str, bounds: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(bounds, dict):
        return [f"{path_name}: {label} must be object"]
    for axis in ("x", "y", "z"):
        value = bounds.get(axis)
        if not isinstance(value, (int, float)) or value <= 0:
            errors.append(f"{path_name}: {label}.{axis} must be positive number")
    return errors


def validate_normalization_defaults(path_name: str, label: str, defaults: Any, expected_fit_axis: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(defaults, dict):
        return [f"{path_name}: {label} must be object"]
    required = ("fitMode", "targetBoundsMode", "allowNonUniformScale", "scale", "fitAxis")
    for key in required:
        if key not in defaults:
            errors.append(f"{path_name}: {label}.{key} missing")
    if defaults.get("fitMode") != "preserve-aspect":
        errors.append(f"{path_name}: {label}.fitMode must be preserve-aspect")
    if defaults.get("targetBoundsMode") != "max-envelope":
        errors.append(f"{path_name}: {label}.targetBoundsMode must be max-envelope")
    if defaults.get("allowNonUniformScale") is not False:
        errors.append(f"{path_name}: {label}.allowNonUniformScale must be false; non-uniform scale would deform the asset")
    if not isinstance(defaults.get("scale"), (int, float)) or defaults.get("scale") <= 0:
        errors.append(f"{path_name}: {label}.scale must be positive uniform number")
    fit_axis = defaults.get("fitAxis")
    if fit_axis not in VALID_FIT_AXES:
        errors.append(f"{path_name}: {label}.fitAxis must be one of {sorted(VALID_FIT_AXES)}")
    if expected_fit_axis and fit_axis != expected_fit_axis:
        errors.append(f"{path_name}: {label}.fitAxis must default to {expected_fit_axis}")
    return errors


def validate_alias_list(path_name: str, label: str, aliases: Any, required_alias: str | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    normalized_aliases: list[str] = []
    if not isinstance(aliases, list) or not aliases:
        return [f"{path_name}: {label} must be non-empty list"], normalized_aliases
    for alias in aliases:
        if not isinstance(alias, str) or not alias.strip():
            errors.append(f"{path_name}: {label} must contain only non-empty strings")
            continue
        normalized_aliases.append(normalize_alias(alias))
    if required_alias and normalize_alias(required_alias) not in normalized_aliases:
        errors.append(f"{path_name}: {label} must include {required_alias}")
    if len(normalized_aliases) != len(set(normalized_aliases)):
        errors.append(f"{path_name}: {label} contains duplicates after normalization")
    return errors, normalized_aliases


def validate_profile(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"{path.name}: missing {key}")
    if data.get("schema") != "codex.assetProfile.v1":
        errors.append(f"{path.name}: schema must be codex.assetProfile.v1")
    if data.get("profileId") != path.stem:
        errors.append(f"{path.name}: profileId must match filename")
    alias_errors, _normalized_aliases = validate_alias_list(path.name, "aliases", data.get("aliases"), path.stem)
    errors.extend(alias_errors)
    for list_key, min_len in (("promptRules", 3), ("negativePromptRules", 2)):
        value = data.get(list_key)
        if not isinstance(value, list) or len(value) < min_len or not all(isinstance(x, str) and x.strip() for x in value):
            errors.append(f"{path.name}: {list_key} must contain at least {min_len} non-empty strings")
    errors.extend(validate_bounds(path.name, "targetBounds", data.get("targetBounds")))
    errors.extend(validate_normalization_defaults(path.name, "normalizationDefaults", data.get("normalizationDefaults"), DEFAULT_FIT_AXIS.get(path.stem)))
    face_budget = data.get("faceBudget")
    if not isinstance(face_budget, int) or face_budget <= 0:
        errors.append(f"{path.name}: faceBudget must be positive integer")
    texture = data.get("textureSize")
    if texture not in VALID_TEXTURES:
        errors.append(f"{path.name}: textureSize must be one of {sorted(VALID_TEXTURES)}")
    if data.get("pivotMode") not in VALID_PIVOTS:
        errors.append(f"{path.name}: pivotMode invalid")
    generation = data.get("generationDefaults") or {}
    for key in ("workflow", "seed", "maxViews"):
        if key not in generation:
            errors.append(f"{path.name}: generationDefaults.{key} missing")
    if "workflow" in generation and not isinstance(generation.get("workflow"), str):
        errors.append(f"{path.name}: generationDefaults.workflow must be string")
    if "seed" in generation and not isinstance(generation.get("seed"), int):
        errors.append(f"{path.name}: generationDefaults.seed must be integer")
    if "maxViews" in generation and (not isinstance(generation.get("maxViews"), int) or generation.get("maxViews") <= 0):
        errors.append(f"{path.name}: generationDefaults.maxViews must be positive integer")
    imports = data.get("importDefaults") or {}
    for key in ("unitySubdir", "prefabNaming"):
        if key not in imports:
            errors.append(f"{path.name}: importDefaults.{key} missing")
    unity_subdir = imports.get("unitySubdir")
    if not isinstance(unity_subdir, str) or not unity_subdir.replace("\\", "/").startswith("Assets/") or ".." in unity_subdir.replace("\\", "/").split("/"):
        errors.append(f"{path.name}: importDefaults.unitySubdir must be under Assets/ and cannot contain ..")
    prefab_naming = imports.get("prefabNaming")
    if not isinstance(prefab_naming, str) or not prefab_naming.strip():
        errors.append(f"{path.name}: importDefaults.prefabNaming must be non-empty string")
    elif "{assetName}" not in prefab_naming:
        errors.append(f"{path.name}: importDefaults.prefabNaming must contain {{assetName}}")
    rules = data.get("validationRules") or {}
    for key in ("singleObject", "maxTriangleCount", "maxTextureSize", "allowedFormats", "boundsTolerance"):
        if key not in rules:
            errors.append(f"{path.name}: validationRules.{key} missing")
    if "singleObject" in rules and not isinstance(rules.get("singleObject"), bool):
        errors.append(f"{path.name}: validationRules.singleObject must be boolean")
    if "maxTriangleCount" in rules and (not isinstance(rules.get("maxTriangleCount"), int) or rules.get("maxTriangleCount") <= 0):
        errors.append(f"{path.name}: validationRules.maxTriangleCount must be positive integer")
    if "maxTextureSize" in rules and rules.get("maxTextureSize") not in VALID_TEXTURES:
        errors.append(f"{path.name}: validationRules.maxTextureSize must be one of {sorted(VALID_TEXTURES)}")
    allowed_formats = rules.get("allowedFormats")
    if not isinstance(allowed_formats, list) or not allowed_formats:
        errors.append(f"{path.name}: validationRules.allowedFormats must be non-empty list")
    else:
        normalized_formats = []
        for fmt in allowed_formats:
            if not isinstance(fmt, str) or not fmt.strip():
                errors.append(f"{path.name}: validationRules.allowedFormats must contain only non-empty strings")
                continue
            normalized = fmt.lower().strip().lstrip(".")
            normalized_formats.append(normalized)
            if normalized not in VALID_FORMATS:
                errors.append(f"{path.name}: validationRules.allowedFormats contains unsupported format: {fmt}")
        if len(normalized_formats) != len(set(normalized_formats)):
            errors.append(f"{path.name}: validationRules.allowedFormats contains duplicates after normalization")
    bounds_tolerance = rules.get("boundsTolerance")
    if not isinstance(bounds_tolerance, (int, float)) or bounds_tolerance <= 0:
        errors.append(f"{path.name}: validationRules.boundsTolerance must be positive number")
    elif bounds_tolerance > 0.25:
        errors.append(f"{path.name}: validationRules.boundsTolerance is too permissive")
    if isinstance(face_budget, int) and isinstance(rules.get("maxTriangleCount"), int) and rules["maxTriangleCount"] > face_budget:
        errors.append(f"{path.name}: validationRules.maxTriangleCount cannot exceed faceBudget")
    if rules.get("maxTextureSize") and texture and rules["maxTextureSize"] > texture:
        errors.append(f"{path.name}: validationRules.maxTextureSize cannot exceed textureSize")
    subprofiles = data.get("subProfiles")
    if subprofiles is not None:
        if not isinstance(subprofiles, dict):
            errors.append(f"{path.name}: subProfiles must be object")
        else:
            sub_alias_owner: dict[str, str] = {}
            for sub_id, subprofile in subprofiles.items():
                label = f"subProfiles.{sub_id}"
                if not isinstance(sub_id, str) or not PROFILE_ID_PATTERN.match(sub_id):
                    errors.append(f"{path.name}: subProfile id must match ^[a-z0-9_]+$: {sub_id}")
                    continue
                if not isinstance(subprofile, dict):
                    errors.append(f"{path.name}: {label} must be object")
                    continue
                if not isinstance(subprofile.get("displayName"), str) or not subprofile.get("displayName", "").strip():
                    errors.append(f"{path.name}: {label}.displayName must be non-empty string")
                alias_errors, aliases = validate_alias_list(path.name, f"{label}.aliases", subprofile.get("aliases"), sub_id)
                errors.extend(alias_errors)
                errors.extend(validate_bounds(path.name, f"{label}.targetBounds", subprofile.get("targetBounds")))
                errors.extend(validate_normalization_defaults(path.name, f"{label}.normalizationDefaults", subprofile.get("normalizationDefaults")))
                category = subprofile.get("unityCategory")
                if category is not None and (not isinstance(category, str) or not category.strip()):
                    errors.append(f"{path.name}: {label}.unityCategory must be non-empty string when provided")
                for alias in aliases + [normalize_alias(sub_id)]:
                    if alias in sub_alias_owner and sub_alias_owner[alias] != sub_id:
                        errors.append(f"{path.name}: subProfile alias collision: {alias} in {sub_alias_owner[alias]} and {sub_id}")
                    sub_alias_owner[alias] = sub_id
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Codex Asset Factory asset profiles.")
    parser.add_argument("--profiles-dir", default=str(Path(__file__).resolve().parents[1] / "configs" / "asset-profiles"))
    parser.add_argument("--proof", default="")
    args = parser.parse_args()
    profiles_dir = Path(args.profiles_dir)
    errors: list[str] = []
    profiles: dict[str, Any] = {}
    for required in REQUIRED_PROFILES:
        path = profiles_dir / f"{required}.json"
        if not path.is_file():
            errors.append(f"missing required profile: {required}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: JSON parse failed: {exc}")
            continue
        profiles[required] = data
        errors.extend(validate_profile(path, data))
    alias_owner: dict[str, str] = {}
    for profile_id, data in profiles.items():
        for alias in data.get("aliases") or []:
            key = normalize_alias(alias)
            if key in alias_owner and alias_owner[key] != profile_id:
                errors.append(f"alias collision: {key} in {alias_owner[key]} and {profile_id}")
            alias_owner[key] = profile_id
        for sub_id, subprofile in (data.get("subProfiles") or {}).items():
            if not isinstance(subprofile, dict):
                continue
            for alias in [sub_id, *(subprofile.get("aliases") or [])]:
                key = normalize_alias(alias)
                owner = f"{profile_id}.{sub_id}"
                if key in alias_owner and alias_owner[key] != owner:
                    errors.append(f"alias collision: {key} in {alias_owner[key]} and {owner}")
                alias_owner[key] = owner
    report = {
        "schema": "codex.assetProfilesValidation.v1",
        "profilesDir": str(profiles_dir),
        "requiredProfiles": REQUIRED_PROFILES,
        "profileCount": len(profiles),
        "aliasCount": len(alias_owner),
        "valid": not errors,
        "errors": errors,
        "profiles": {
            k: {
                "profileType": v.get("profileType"),
                "unityCategory": v.get("unityCategory"),
                "targetBounds": v.get("targetBounds"),
                "faceBudget": v.get("faceBudget"),
                "textureSize": v.get("textureSize"),
                "pivotMode": v.get("pivotMode"),
                "normalizationDefaults": v.get("normalizationDefaults"),
                "allowedFormats": (v.get("validationRules") or {}).get("allowedFormats", []),
                "maxTriangleCount": (v.get("validationRules") or {}).get("maxTriangleCount"),
                "maxTextureSize": (v.get("validationRules") or {}).get("maxTextureSize"),
                "boundsTolerance": (v.get("validationRules") or {}).get("boundsTolerance"),
                "singleObject": (v.get("validationRules") or {}).get("singleObject"),
                "aliases": v.get("aliases", []),
                "subProfiles": {
                    sub_id: {
                        "targetBounds": sub.get("targetBounds"),
                        "fitAxis": ((sub.get("normalizationDefaults") or {}).get("fitAxis")),
                        "unityCategory": sub.get("unityCategory"),
                        "aliases": sub.get("aliases", []),
                    }
                    for sub_id, sub in (v.get("subProfiles") or {}).items()
                    if isinstance(sub, dict)
                },
            }
            for k, v in profiles.items()
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.proof:
        proof = Path(args.proof)
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
