from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from asset_profile_defaults import resolve_sub_profile
from validate_reference_image import analyze_image

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IGNORED_EXTENSIONS = {".json"}
ALLOWED_FIT_AXES = {"contain", "x", "y", "z"}
CATEGORY_ORDER = ["floor", "wall", "door", "window", "furniture", "decor"]

CATEGORY_PRESETS: dict[str, dict[str, Any]] = {
    "floor": {
        "profile": "terrain_piece",
        "role": "floor/platform base",
        "assetBase": "floor_platform",
        "fitAxis": "contain",
    },
    "wall": {
        "profile": "wall",
        "role": "plain wall panel",
        "assetBase": "plain_wall",
        "fitAxis": "x",
    },
    "door": {
        "profile": "door",
        "role": "interior door",
        "assetBase": "door",
        "fitAxis": "y",
    },
    "window": {
        "profile": "wall",
        "subProfile": "window_wall",
        "role": "window wall panel",
        "assetBase": "window_wall",
    },
    "furniture": {
        "profile": "prop",
        "role": "furniture prop",
        "assetBase": "furniture_prop",
        "fitAxis": "contain",
    },
    "decor": {
        "profile": "prop",
        "role": "decor prop",
        "assetBase": "decor_prop",
        "fitAxis": "contain",
    },
}

ROLE_BOUNDS: list[tuple[tuple[str, ...], dict[str, float], str, str]] = [
    (("bed", "mattress"), {"x": 2.0, "y": 0.7, "z": 1.25}, "simple bed or mattress", "bed"),
    (("bench", "sofa", "couch"), {"x": 1.6, "y": 0.85, "z": 0.7}, "bench seating", "bench"),
    (("table", "desk"), {"x": 1.2, "y": 0.8, "z": 0.9}, "low table", "table"),
    (("chair", "stool", "seat"), {"x": 0.65, "y": 0.9, "z": 0.65}, "small stool or chair", "stool"),
    (("shelf", "cabinet", "wardrobe", "dresser"), {"x": 1.1, "y": 1.8, "z": 0.45}, "storage furniture", "cabinet"),
    (("mirror",), {"x": 0.75, "y": 1.2, "z": 0.12}, "wall mirror decor", "mirror"),
    (("lamp", "lantern"), {"x": 0.45, "y": 1.0, "z": 0.45}, "lamp decor", "lamp"),
    (("plant", "vase"), {"x": 0.55, "y": 1.0, "z": 0.55}, "plant decor", "plant"),
    (("rug", "carpet"), {"x": 1.6, "y": 0.08, "z": 1.1}, "floor rug decor", "rug"),
    (("painting", "picture", "frame"), {"x": 0.9, "y": 0.7, "z": 0.08}, "wall art decor", "wall_art"),
]

CLASSIFICATION_TERMS: dict[str, tuple[str, ...]] = {
    "door": ("door", "porte", "gate"),
    "window": ("window", "fenetre", "fenêtre"),
    "furniture": (
        "bed",
        "mattress",
        "bench",
        "sofa",
        "couch",
        "table",
        "desk",
        "chair",
        "stool",
        "seat",
        "shelf",
        "cabinet",
        "wardrobe",
        "dresser",
    ),
    "decor": (
        "mirror",
        "lamp",
        "lantern",
        "plant",
        "vase",
        "rug",
        "carpet",
        "painting",
        "picture",
        "frame",
        "decor",
        "deco",
    ),
    "floor": ("floor", "ground", "platform", "tile", "tiles", "sol", "terrain"),
    "wall": ("wall", "mur", "brick", "cloison", "panel", "plank"),
}

FORBIDDEN_TERMS: dict[str, tuple[str, ...]] = {
    "person_or_body": (
        "person",
        "people",
        "human",
        "humanoid",
        "character",
        "man",
        "woman",
        "boy",
        "girl",
        "face",
        "head",
        "hand",
        "hands",
        "body",
    ),
    "clothing": (
        "shirt",
        "pants",
        "dress",
        "jacket",
        "coat",
        "shoe",
        "shoes",
        "hat",
        "helmet",
        "clothing",
        "cloth",
        "wearable",
    ),
    "multi_object": (
        "multi",
        "multiple",
        "group",
        "set",
        "collection",
        "assorted",
        "pair",
        "bundle",
        "chairs",
        "tables",
    ),
    "scene": (
        "room scene",
        "full room",
        "complete room",
        "bedroom",
        "kitchen",
        "living room",
        "scene",
        "environment",
    ),
    "text_or_measurements": (
        "text",
        "label",
        "logo",
        "letters",
        "measurement",
        "measurements",
        "dimension",
        "dimensions",
        "ruler",
        "annotated",
    ),
}


def normalize_text(value: str) -> str:
    clean = value.lower()
    clean = re.sub(r"[^a-z0-9]+", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def has_term(text: str, term: str) -> bool:
    needle = normalize_text(term)
    if not needle:
        return False
    return re.search(rf"(^| ){re.escape(needle)}($| )", text) is not None


def safe_name(value: str, fallback: str) -> str:
    base = normalize_text(value).replace(" ", "_").strip("_")
    if not base:
        base = fallback
    if not re.match(r"^[a-z]", base):
        base = f"asset_{base}"
    return base[:80]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_profiles(profiles_dir: Path) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in profiles_dir.glob("*.json"):
        try:
            data = load_json(path)
        except Exception:
            continue
        profile_id = str(data.get("profileId") or path.stem)
        profiles[profile_id] = data
    return profiles


def target_bounds_from_profile(profiles: dict[str, dict[str, Any]], profile: str) -> dict[str, float]:
    return target_bounds_from_profile_target(profiles, profile, "")


def target_bounds_from_profile_target(profiles: dict[str, dict[str, Any]], profile: str, sub_profile: str = "") -> dict[str, float]:
    profile_data = profiles.get(profile) or {}
    _resolved_sub_id, subprofile = resolve_sub_profile(profile_data, sub_profile)
    raw = (subprofile or profile_data).get("targetBounds") or {}
    return {"x": float(raw.get("x", 1.0)), "y": float(raw.get("y", 1.0)), "z": float(raw.get("z", 1.0))}


def fit_axis_from_profile(profiles: dict[str, dict[str, Any]], profile: str, sub_profile: str = "") -> str:
    profile_data = profiles.get(profile) or {}
    _resolved_sub_id, subprofile = resolve_sub_profile(profile_data, sub_profile)
    defaults = (profile_data.get("normalizationDefaults") or {}).copy()
    if isinstance(subprofile, dict):
        defaults.update(subprofile.get("normalizationDefaults") or {})
    fit_axis = str(defaults.get("fitAxis") or "contain").lower()
    return fit_axis if fit_axis in ALLOWED_FIT_AXES else "contain"


def parse_bounds(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            return {"x": float(value["x"]), "y": float(value["y"]), "z": float(value["z"])}
        except Exception:
            return None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return {"x": float(value[0]), "y": float(value[1]), "z": float(value[2])}
        except Exception:
            return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        if len(parts) == 3:
            try:
                return {"x": float(parts[0]), "y": float(parts[1]), "z": float(parts[2])}
            except Exception:
                return None
    return None


def load_sidecar(image: Path) -> dict[str, Any]:
    paths = [image.with_suffix(image.suffix + ".json"), image.with_suffix(".json")]
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def load_selection(path: Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    if not path:
        return [], []
    errors: list[str] = []
    try:
        data = load_json(path)
    except Exception as exc:
        return [], [f"selection JSON could not be read: {exc}"]
    if isinstance(data, dict):
        raw_items = data.get("assets") or data.get("selection") or data.get("references") or data.get("items")
    else:
        raw_items = data
    if not isinstance(raw_items, list):
        return [], ["selection JSON must be a list or contain assets/selection/references/items"]
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, dict):
            copied = dict(item)
            copied["_selectionOrder"] = index
            items.append(copied)
        else:
            errors.append(f"selection item {index} must be an object")
    return items, errors


def enumerate_files(input_dir: Path) -> list[Path]:
    files = []
    for path in input_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() in IGNORED_EXTENSIONS:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.name.lower())


def selection_lookup(items: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_index: dict[int, dict[str, Any]] = {}
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        has_file_key = False
        for key in ("source", "path", "imagePath", "inputImage", "referenceCopy", "file", "filename", "name"):
            value = item.get(key)
            if not value:
                continue
            has_file_key = True
            text = str(value)
            by_key[text.lower()] = item
            by_key[Path(text).name.lower()] = item
        if not has_file_key:
            for key in ("index", "candidateIndex"):
                if key in item:
                    try:
                        by_index[int(item[key])] = item
                    except Exception:
                        pass
    return by_index, by_key


def match_selection(path: Path, index: int, by_index: dict[int, dict[str, Any]], by_key: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if index in by_index:
        return by_index[index]
    return by_key.get(str(path).lower()) or by_key.get(path.name.lower())


def explicit_category(data: dict[str, Any]) -> str:
    for key in ("roomCategory", "category", "class"):
        value = normalize_text(str(data.get(key) or ""))
        if value in CATEGORY_PRESETS:
            return value
    profile = normalize_text(str(data.get("profile") or ""))
    if profile == "terrain_piece":
        return "floor"
    if profile == "door":
        return "door"
    if profile == "wall":
        role_text = normalize_text(str(data.get("subProfile") or data.get("role") or data.get("assetName") or ""))
        if has_term(role_text, "window"):
            return "window"
        return "wall"
    return ""


def classify(text: str, explicit: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    explicit_value = explicit_category(explicit)
    for reason, terms in FORBIDDEN_TERMS.items():
        matches = [term for term in terms if has_term(text, term)]
        if matches:
            errors.append(f"room-ready reject {reason}: {', '.join(matches[:3])}")
    if explicit.get("roomReady") is False:
        errors.append("room-ready reject: sidecar/selection marks roomReady=false")
    if explicit_value:
        return explicit_value, errors, warnings
    detected = [category for category in CATEGORY_ORDER if any(has_term(text, term) for term in CLASSIFICATION_TERMS[category])]
    if not detected:
        errors.append("room-ready reject ambiguous: category could not be inferred deterministically")
        return "", errors, warnings
    category = detected[0]
    if len(detected) > 1 and category not in {"door", "window", "furniture", "decor"}:
        warnings.append(f"multiple category hints found: {', '.join(detected)}")
    return category, errors, warnings


def role_details(category: str, text: str, explicit: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    preset = CATEGORY_PRESETS[category]
    role = str(explicit.get("role") or "").strip() or preset["role"]
    asset_base = str(explicit.get("assetName") or "").strip() or preset["assetBase"]
    profile = str(explicit.get("profile") or preset["profile"]).strip() or preset["profile"]
    sub_profile = str(explicit.get("subProfile") or preset.get("subProfile") or "").strip()
    target_bounds = parse_bounds(explicit.get("targetBounds"))
    if target_bounds is None:
        if category in {"furniture", "decor"}:
            for terms, bounds, role_label, base in ROLE_BOUNDS:
                if any(has_term(text, term) for term in terms):
                    target_bounds = dict(bounds)
                    if not explicit.get("role"):
                        role = role_label
                    if not explicit.get("assetName"):
                        asset_base = base
                    if base == "mirror":
                        profile = str(explicit.get("profile") or "wall").strip() or "wall"
                        sub_profile = str(explicit.get("subProfile") or "wall_mirror").strip() or "wall_mirror"
                    break
        if target_bounds is None:
            target_bounds = target_bounds_from_profile_target(profiles, profile, sub_profile)
    if sub_profile and not explicit.get("targetBounds"):
        target_bounds = target_bounds_from_profile_target(profiles, profile, sub_profile)
    fit_axis = str(explicit.get("fitAxis") or fit_axis_from_profile(profiles, profile, sub_profile)).strip().lower()
    if fit_axis not in ALLOWED_FIT_AXES:
        fit_axis = fit_axis_from_profile(profiles, profile, sub_profile)
    return {
        "category": category,
        "profile": profile,
        "subProfile": sub_profile,
        "role": role,
        "assetBase": asset_base,
        "targetBounds": target_bounds,
        "fitAxis": fit_axis,
    }


def unity_placement(category: str, sequence_by_category: dict[str, int], explicit: dict[str, Any]) -> dict[str, Any]:
    explicit_value = explicit.get("unityPlacement")
    if isinstance(explicit_value, dict):
        return explicit_value
    slot = sequence_by_category.get(category, 0)
    if category == "floor":
        position, rotation = {"x": 0.0, "y": 0.0, "z": 0.0}, {"x": 0.0, "y": 0.0, "z": 0.0}
    elif category == "wall":
        placements = [
            ({"x": 0.0, "y": 0.0, "z": 2.0}, {"x": 0.0, "y": 0.0, "z": 0.0}),
            ({"x": -2.0, "y": 0.0, "z": 0.0}, {"x": 0.0, "y": 90.0, "z": 0.0}),
            ({"x": 2.0, "y": 0.0, "z": 0.0}, {"x": 0.0, "y": -90.0, "z": 0.0}),
        ]
        position, rotation = placements[slot % len(placements)]
    elif category == "window":
        position, rotation = {"x": 2.0, "y": 0.0, "z": 0.35}, {"x": 0.0, "y": -90.0, "z": 0.0}
    elif category == "door":
        position, rotation = {"x": 0.0, "y": 0.0, "z": -2.0}, {"x": 0.0, "y": 180.0, "z": 0.0}
    elif category == "furniture":
        placements = [
            ({"x": 0.0, "y": 0.0, "z": 0.35}, {"x": 0.0, "y": 0.0, "z": 0.0}),
            ({"x": -0.9, "y": 0.0, "z": -0.45}, {"x": 0.0, "y": 25.0, "z": 0.0}),
            ({"x": 0.9, "y": 0.0, "z": -0.45}, {"x": 0.0, "y": -25.0, "z": 0.0}),
            ({"x": -1.1, "y": 0.0, "z": 0.95}, {"x": 0.0, "y": 0.0, "z": 0.0}),
        ]
        position, rotation = placements[slot % len(placements)]
    else:
        placements = [
            ({"x": -1.55, "y": 0.95, "z": 1.85}, {"x": 0.0, "y": 0.0, "z": 0.0}),
            ({"x": 1.35, "y": 0.0, "z": 1.05}, {"x": 0.0, "y": -30.0, "z": 0.0}),
        ]
        position, rotation = placements[slot % len(placements)]
    return {
        "position": position,
        "rotationEuler": rotation,
        "uniformScale": 1.0,
        "placementSpace": "room-demo-local",
    }


def analysis_text(path: Path, sidecar: dict[str, Any], selection: dict[str, Any] | None) -> str:
    parts = [path.stem]
    for data in (sidecar, selection or {}):
        for key in ("assetName", "role", "category", "roomCategory", "profile", "description"):
            value = data.get(key)
            if value:
                parts.append(str(value))
    return normalize_text(" ".join(parts))


def analyze_candidate(path: Path, index: int, sidecar: dict[str, Any], selection: dict[str, Any] | None, profiles: dict[str, dict[str, Any]], force: bool) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    merged.update(sidecar)
    if selection:
        merged.update(selection)
    text = analysis_text(path, sidecar, selection)
    errors: list[str] = []
    warnings: list[str] = []
    image_report: dict[str, Any] | None = None
    image_info: dict[str, Any] = {}
    ext = path.suffix.lower()

    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        errors.append(f"unsupported image format: {ext or '<none>'}")
    else:
        image_report = analyze_image(path, str(merged.get("assetName") or path.stem), force=False)
        image_info = image_report.get("imageInfo") or {}
        errors.extend(str(item) for item in image_report.get("errors") or [])
        warnings.extend(str(item) for item in image_report.get("warnings") or [])
        background = image_info.get("background") or {}
        shadow = image_info.get("shadow") or {}
        if background.get("likelyUniform") is False:
            errors.append("room-ready reject background: border/background is not uniformly clean")
        if shadow.get("possibleCastShadow") is True:
            errors.append("room-ready reject shadow: possible cast/contact shadow")

    category, classification_errors, classification_warnings = classify(text, merged)
    errors.extend(classification_errors)
    warnings.extend(classification_warnings)
    details: dict[str, Any] | None = None
    if category:
        details = role_details(category, text, merged, profiles)
        if details["profile"] not in profiles:
            errors.append(f"profile not found: {details['profile']}")

    selected_requested = selection is not None
    valid_room_ready = bool(details and not errors)
    return {
        "index": index,
        "path": str(path),
        "name": path.name,
        "bytes": path.stat().st_size,
        "mtime": path.stat().st_mtime,
        "format": ext.lstrip("."),
        "selectedRequested": selected_requested,
        "validRoomReady": bool(force or valid_room_ready),
        "category": category,
        "profile": details["profile"] if details else "",
        "subProfile": details["subProfile"] if details else "",
        "role": details["role"] if details else "",
        "targetBounds": details["targetBounds"] if details else None,
        "fitAxis": details["fitAxis"] if details else "",
        "assetBase": details["assetBase"] if details else "",
        "errors": errors,
        "warnings": warnings,
        "imageInfo": image_info,
        "_selection": selection or {},
    }


def stable_asset_name(order: int, base: str) -> str:
    clean = safe_name(base, f"asset_{order:02d}")
    if re.match(r"^\d{2}_", clean):
        return clean
    return f"{order:02d}_{clean}"


def selected_reference(candidate: dict[str, Any], order: int, output_dir: Path, sequence_by_category: dict[str, int]) -> dict[str, Any]:
    category = candidate["category"]
    sequence_by_category[category] = sequence_by_category.get(category, 0) + 1
    explicit = candidate.get("_selection") or {}
    source = Path(candidate["path"])
    asset_name = stable_asset_name(order, str(explicit.get("assetName") or candidate["assetBase"]))
    suffix = source.suffix.lower() if source.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS else ".png"
    input_path = output_dir / "inputs" / f"{asset_name}{suffix}"
    reference_path = output_dir / "references" / f"{asset_name}_reference{suffix}"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, input_path)
    shutil.copy2(source, reference_path)
    return {
        "assetName": asset_name,
        "candidateIndex": candidate["index"],
        "profile": candidate["profile"],
        "subProfile": candidate.get("subProfile") or "",
        "category": category,
        "role": candidate["role"],
        "targetBounds": candidate["targetBounds"],
        "fitAxis": candidate["fitAxis"],
        "unityPlacement": unity_placement(category, sequence_by_category, explicit),
        "source": str(source),
        "inputImage": str(input_path),
        "referenceCopy": str(reference_path),
        "bytes": candidate["bytes"],
    }


def create_contact_sheet(candidates: list[dict[str, Any]], path: Path, title: str, selected_only: bool = False) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"Pillow is required to write contact sheets: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = max(1, math.ceil(max(1, len(candidates)) / 4))
    cell_w, cell_h = 300, 300
    header_h = 42
    sheet = Image.new("RGB", (cell_w * 4, header_h + rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.rectangle((0, 0, sheet.width, header_h), fill=(25, 31, 40))
    draw.text((12, 14), title, fill="white", font=font)
    if not candidates:
        draw.text((12, header_h + 20), "No candidates.", fill=(40, 40, 40), font=font)
        sheet.save(path, quality=92)
        return

    for offset, candidate in enumerate(candidates):
        row, col = divmod(offset, 4)
        x = col * cell_w
        y = header_h + row * cell_h
        status_color = (49, 132, 78) if candidate.get("validRoomReady") else (176, 52, 52)
        if selected_only:
            status_color = (42, 92, 170)
        draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(210, 210, 210))
        draw.rectangle((x, y, x + cell_w, y + 8), fill=status_color)
        thumb_box = (x + 12, y + 18, x + cell_w - 12, y + 190)
        try:
            with Image.open(candidate["path"]) as image:
                rgb = image.convert("RGBA")
                background = Image.new("RGBA", rgb.size, "white")
                background.alpha_composite(rgb)
                rgb = background.convert("RGB")
                rgb.thumbnail((thumb_box[2] - thumb_box[0], thumb_box[3] - thumb_box[1]))
                tx = thumb_box[0] + ((thumb_box[2] - thumb_box[0]) - rgb.width) // 2
                ty = thumb_box[1] + ((thumb_box[3] - thumb_box[1]) - rgb.height) // 2
                sheet.paste(rgb, (tx, ty))
        except Exception:
            draw.rectangle(thumb_box, outline=(160, 160, 160))
            draw.text((thumb_box[0] + 8, thumb_box[1] + 70), "No preview", fill=(90, 90, 90), font=font)
        label_lines = [
            f"#{candidate.get('index')} {candidate.get('name')}",
            f"{candidate.get('category') or 'rejected'} / {candidate.get('profile') or '-'}",
            str(candidate.get("role") or "-"),
        ]
        reasons = candidate.get("errors") or candidate.get("warnings") or []
        if reasons:
            label_lines.append(str(reasons[0])[:64])
        text_y = y + 202
        for line in label_lines:
            for wrapped in wrap_text(line, 42)[:2]:
                draw.text((x + 12, text_y), wrapped, fill=(30, 30, 30), font=font)
                text_y += 14
    sheet.save(path, quality=92)


def wrap_text(value: str, width: int) -> list[str]:
    words = value.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = f"{current} {word}".strip()
        if len(proposed) <= width:
            current = proposed
        else:
            if current:
                lines.append(current)
            current = word[:width]
    if current:
        lines.append(current)
    return lines


def select_candidates(candidates: list[dict[str, Any]], has_selection: bool) -> list[dict[str, Any]]:
    if has_selection:
        return [candidate for candidate in candidates if candidate.get("selectedRequested") and candidate.get("validRoomReady")]
    valid = [candidate for candidate in candidates if candidate.get("validRoomReady")]
    return sorted(valid, key=lambda item: (CATEGORY_ORDER.index(item["category"]), item["index"]))


def build_plan(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    profiles_dir = Path(args.profiles_dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not input_dir.is_dir():
        return {"valid": False, "errors": [f"input directory missing: {input_dir}"]}, 2

    profiles = load_profiles(profiles_dir)
    for required in ("terrain_piece", "wall", "door", "prop"):
        if required not in profiles:
            errors.append(f"required profile missing: {required}")

    selection_items, selection_errors = load_selection(Path(args.selection).resolve() if args.selection else None)
    errors.extend(selection_errors)
    by_index, by_key = selection_lookup(selection_items)
    paths = enumerate_files(input_dir)
    if not paths:
        errors.append("no candidate files found")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    matched_selection_ids: set[int] = set()
    for index, path in enumerate(paths, start=1):
        sidecar = load_sidecar(path)
        selection = match_selection(path, index, by_index, by_key)
        if selection:
            matched_selection_ids.add(id(selection))
        candidates.append(analyze_candidate(path, index, sidecar, selection, profiles, bool(args.force)))

    unmatched = [item for item in selection_items if id(item) not in matched_selection_ids]
    for item in unmatched:
        errors.append(f"selection item did not match any candidate: {item.get('assetName') or item.get('name') or item.get('path') or item.get('index')}")

    selected = select_candidates(candidates, bool(selection_items))
    if len(selected) < int(args.min_assets):
        errors.append(f"selected room-ready asset count {len(selected)} is below --min-assets {args.min_assets}")
    if len(selected) > int(args.max_assets):
        errors.append(f"selected room-ready asset count {len(selected)} exceeds --max-assets {args.max_assets}")
    if selection_items and not selected:
        errors.append("selection did not produce any room-ready assets")

    candidate_sheet = output_dir / "candidate_contact_sheet.jpg"
    selected_sheet = output_dir / "selected_room_assets_sheet.jpg"
    create_contact_sheet(candidates, candidate_sheet, "Room Demo Candidate Images")
    create_contact_sheet(selected, selected_sheet, "Selected Room Demo Assets", selected_only=True)

    sequence_by_category: dict[str, int] = {}
    selected_refs = [
        selected_reference(candidate, order, output_dir, sequence_by_category)
        for order, candidate in enumerate(selected, start=1)
    ]

    for reference in selected_refs:
        bounds = reference.get("targetBounds") or {}
        if sorted(bounds.keys()) != ["x", "y", "z"]:
            errors.append(f"{reference['assetName']}: targetBounds must contain x,y,z")
        if reference.get("fitAxis") not in ALLOWED_FIT_AXES:
            errors.append(f"{reference['assetName']}: unsupported fitAxis {reference.get('fitAxis')}")
        placement = reference.get("unityPlacement") or {}
        if not isinstance(placement, dict) or "position" not in placement or "rotationEuler" not in placement:
            errors.append(f"{reference['assetName']}: unityPlacement must include position and rotationEuler")

    public_candidates = [{key: value for key, value in candidate.items() if not key.startswith("_")} for candidate in candidates]
    valid = not errors or bool(args.force and selected_refs)
    report = {
        "schema": "codex.roomDemoBatchPlan.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "valid": bool(valid),
        "forced": bool(args.force),
        "inputDir": str(input_dir),
        "outputDir": str(output_dir),
        "profilesDir": str(profiles_dir),
        "minAssets": int(args.min_assets),
        "maxAssets": int(args.max_assets),
        "candidateCount": len(candidates),
        "selectedCount": len(selected_refs),
        "rejectedCount": len([candidate for candidate in candidates if not candidate.get("validRoomReady")]),
        "errors": errors,
        "warnings": warnings,
        "outputs": {
            "candidateImages": str(output_dir / "candidate_images.json"),
            "candidateContactSheet": str(candidate_sheet),
            "roomReadyReport": str(output_dir / "room_ready_report.json"),
            "selectedReferences": str(output_dir / "selected_references.json"),
            "selectedContactSheet": str(selected_sheet),
            "inputsDir": str(output_dir / "inputs"),
            "referencesDir": str(output_dir / "references"),
        },
    }

    write_json(output_dir / "candidate_images.json", public_candidates)
    write_json(output_dir / "selected_references.json", selected_refs)
    write_json(output_dir / "room_ready_report.json", report)
    return report, 0 if valid else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan a deterministic room-demo image batch before TRELLIS2 generation.")
    parser.add_argument("--input-dir", required=True, help="Directory containing candidate reference images.")
    parser.add_argument("--output-dir", required=True, help="Directory that receives planning JSON, contact sheets, and copied references.")
    parser.add_argument("--profiles-dir", default=str(Path(__file__).resolve().parents[1] / "configs" / "asset-profiles"))
    parser.add_argument("--selection", default="", help="Optional JSON selection for hash-named or manually reviewed inputs.")
    parser.add_argument("--min-assets", type=int, default=7)
    parser.add_argument("--max-assets", type=int, default=20)
    parser.add_argument("--copy-inputs", action="store_true", help="Accepted for explicitness; selected inputs are copied by default.")
    parser.add_argument("--force", action="store_true", help="Write selected outputs even when count/background checks would otherwise fail.")
    parser.add_argument("--json", action="store_true", help="Print the room-ready report as JSON.")
    args = parser.parse_args()

    report, exit_code = build_plan(args)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        status = "OK" if report.get("valid") else "FAILED"
        print(f"Room demo planning {status}: {report.get('selectedCount', 0)} selected / {report.get('candidateCount', 0)} candidates")
        for error in report.get("errors") or []:
            print(f"ERROR: {error}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
