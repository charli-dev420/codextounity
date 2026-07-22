from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VALID_FIT_AXES = {"contain", "x", "y", "z"}
DEFAULT_FIT_AXIS = {
    "terrain_piece": "contain",
    "wall": "x",
    "door": "y",
    "prop": "contain",
    "pickup": "contain",
    "equipment": "contain",
    "weapon": "x",
    "character": "y",
}
DEFAULT_NORMALIZATION = {
    "fitMode": "preserve-aspect",
    "targetBoundsMode": "max-envelope",
    "allowNonUniformScale": False,
    "scale": 1,
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profiles(profiles_dir: Path) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = load_json(path)
        except Exception:
            continue
        profile_id = str(data.get("profileId") or path.stem)
        profiles[profile_id] = data
    return profiles


def normalize_alias(value: Any) -> str:
    return str(value or "").lower().strip().replace("-", "_").replace(" ", "_")


def bounds_dict_to_list(bounds: Any) -> list[float] | None:
    if not isinstance(bounds, dict):
        return None
    values: list[float] = []
    for axis in ("x", "y", "z"):
        value = bounds.get(axis)
        if not isinstance(value, (int, float)) or value <= 0:
            return None
        values.append(float(value))
    return values


def bounds_list_to_dict(bounds: list[float]) -> dict[str, float]:
    return {"x": float(bounds[0]), "y": float(bounds[1]), "z": float(bounds[2])}


def bounds_to_text(bounds: list[float]) -> str:
    return ",".join(f"{value:g}" for value in bounds)


def profile_path(profiles_dir: Path, profile_id: str) -> Path:
    return Path(profiles_dir) / f"{profile_id}.json"


def load_profile(profiles_dir: Path, profile_id: str) -> dict[str, Any]:
    path = profile_path(profiles_dir, profile_id)
    if not path.is_file():
        raise ValueError(f"profile file missing: {path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"profile JSON must be an object: {path}")
    return data


def resolve_sub_profile(profile: dict[str, Any], sub_profile_id: str = "") -> tuple[str, dict[str, Any] | None]:
    requested = normalize_alias(sub_profile_id)
    if not requested:
        return "", None
    subprofiles = profile.get("subProfiles") or {}
    if not isinstance(subprofiles, dict):
        return requested, None
    if requested in subprofiles and isinstance(subprofiles[requested], dict):
        return requested, subprofiles[requested]
    for key, value in subprofiles.items():
        if not isinstance(value, dict):
            continue
        aliases = [key, value.get("displayName"), *(value.get("aliases") or [])]
        if requested in {normalize_alias(alias) for alias in aliases}:
            return str(key), value
    return requested, None


def normalization_defaults(profile_id: str, profile: dict[str, Any], sub_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = dict(DEFAULT_NORMALIZATION)
    defaults["fitAxis"] = DEFAULT_FIT_AXIS.get(profile_id, "contain")
    profile_defaults = profile.get("normalizationDefaults")
    if isinstance(profile_defaults, dict):
        defaults.update(profile_defaults)
    if isinstance(sub_profile, dict):
        sub_defaults = sub_profile.get("normalizationDefaults")
        if isinstance(sub_defaults, dict):
            defaults.update(sub_defaults)
    return defaults


def resolve_profile_target(
    profile_id: str,
    profiles_dir: Path,
    sub_profile_id: str = "",
) -> dict[str, Any]:
    profile = load_profile(Path(profiles_dir), profile_id)
    resolved_sub_id, sub_profile = resolve_sub_profile(profile, sub_profile_id)
    if resolved_sub_id and sub_profile is None:
        raise ValueError(f"unknown subProfile '{sub_profile_id}' for profile '{profile_id}'")

    source = sub_profile or profile
    target_bounds = bounds_dict_to_list(source.get("targetBounds")) or bounds_dict_to_list(profile.get("targetBounds"))
    if target_bounds is None:
        raise ValueError(f"{profile_id}: targetBounds must contain positive numeric x,y,z")
    defaults = normalization_defaults(profile_id, profile, sub_profile)
    fit_axis = str(defaults.get("fitAxis") or "").lower()
    if fit_axis not in VALID_FIT_AXES:
        raise ValueError(f"{profile_id}: normalizationDefaults.fitAxis must be one of {sorted(VALID_FIT_AXES)}")
    return {
        "profileId": profile_id,
        "profile": profile,
        "subProfileId": resolved_sub_id,
        "subProfile": sub_profile,
        "displayName": source.get("displayName") or profile.get("displayName") or profile_id,
        "targetBounds": bounds_list_to_dict(target_bounds),
        "targetBoundsList": target_bounds,
        "fitAxis": fit_axis,
        "pivotMode": source.get("pivotMode") or profile.get("pivotMode") or "bottom-center",
        "unityCategory": source.get("unityCategory") or profile.get("unityCategory") or "props",
        "validationRules": profile.get("validationRules") or {},
        "normalizationDefaults": defaults,
    }


def resolve_fit_axis(
    profile_id: str,
    requested: str = "auto",
    profiles_dir: Path | None = None,
    sub_profile_id: str = "",
) -> str:
    value = str(requested or "auto").lower().strip()
    if value and value != "auto":
        if value not in VALID_FIT_AXES:
            raise ValueError(f"fitAxis must be one of auto, {', '.join(sorted(VALID_FIT_AXES))}")
        return value
    if not profile_id:
        return "contain"
    if profiles_dir:
        return str(resolve_profile_target(profile_id, profiles_dir, sub_profile_id)["fitAxis"])
    return DEFAULT_FIT_AXIS.get(profile_id, "contain")
