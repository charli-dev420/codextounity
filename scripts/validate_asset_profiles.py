from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_PROFILES = ["wall", "door", "prop", "weapon", "pickup", "character", "equipment", "terrain_piece"]
REQUIRED_TOP_LEVEL = [
    "schema", "profileId", "displayName", "profileType", "aliases", "promptRules", "negativePromptRules",
    "targetBounds", "faceBudget", "textureSize", "pivotMode", "unityCategory", "generationDefaults",
    "importDefaults", "validationRules",
]
VALID_PIVOTS = {"bottom-center", "center", "origin", "custom", "keep"}
VALID_TEXTURES = {256, 512, 1024, 2048}


def validate_profile(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"{path.name}: missing {key}")
    if data.get("schema") != "codex.assetProfile.v1":
        errors.append(f"{path.name}: schema must be codex.assetProfile.v1")
    if data.get("profileId") != path.stem:
        errors.append(f"{path.name}: profileId must match filename")
    aliases = data.get("aliases")
    if not isinstance(aliases, list) or not aliases:
        errors.append(f"{path.name}: aliases must be non-empty list")
    elif path.stem not in [str(a).lower() for a in aliases]:
        errors.append(f"{path.name}: aliases must include profile id")
    for list_key, min_len in (("promptRules", 3), ("negativePromptRules", 2)):
        value = data.get(list_key)
        if not isinstance(value, list) or len(value) < min_len or not all(isinstance(x, str) and x.strip() for x in value):
            errors.append(f"{path.name}: {list_key} must contain at least {min_len} non-empty strings")
    bounds = data.get("targetBounds")
    if not isinstance(bounds, dict):
        errors.append(f"{path.name}: targetBounds must be object")
    else:
        for axis in ("x", "y", "z"):
            value = bounds.get(axis)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"{path.name}: targetBounds.{axis} must be positive number")
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
    imports = data.get("importDefaults") or {}
    for key in ("unitySubdir", "prefabNaming"):
        if key not in imports:
            errors.append(f"{path.name}: importDefaults.{key} missing")
    rules = data.get("validationRules") or {}
    for key in ("singleObject", "maxTriangleCount", "maxTextureSize", "allowedFormats", "boundsTolerance"):
        if key not in rules:
            errors.append(f"{path.name}: validationRules.{key} missing")
    if isinstance(face_budget, int) and isinstance(rules.get("maxTriangleCount"), int) and rules["maxTriangleCount"] > face_budget:
        errors.append(f"{path.name}: validationRules.maxTriangleCount cannot exceed faceBudget")
    if rules.get("maxTextureSize") and texture and rules["maxTextureSize"] > texture:
        errors.append(f"{path.name}: validationRules.maxTextureSize cannot exceed textureSize")
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
            key = str(alias).lower().strip()
            if key in alias_owner and alias_owner[key] != profile_id:
                errors.append(f"alias collision: {key} in {alias_owner[key]} and {profile_id}")
            alias_owner[key] = profile_id
    report = {
        "schema": "codex.assetProfilesValidation.v1",
        "profilesDir": str(profiles_dir),
        "requiredProfiles": REQUIRED_PROFILES,
        "profileCount": len(profiles),
        "aliasCount": len(alias_owner),
        "valid": not errors,
        "errors": errors,
        "profiles": {k: {"unityCategory": v.get("unityCategory"), "faceBudget": v.get("faceBudget"), "textureSize": v.get("textureSize"), "pivotMode": v.get("pivotMode"), "aliases": v.get("aliases", [])} for k, v in profiles.items()},
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.proof:
        proof = Path(args.proof)
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
