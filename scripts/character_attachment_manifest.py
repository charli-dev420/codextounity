from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_SLOTS: dict[str, dict[str, Any]] = {
    "main_hand": {"bone": "RightHand", "position": [0.08, -0.02, 0.02], "rotationEuler": [0.0, 90.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "weapon_or_handheld", "previewPose": "combat_idle", "notes": "Primary held item."},
    "offhand": {"bone": "LeftHand", "position": [-0.08, -0.02, 0.02], "rotationEuler": [0.0, -90.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "shield_or_handheld", "previewPose": "combat_idle", "notes": "Secondary held item."},
    "back": {"bone": "Spine2", "position": [0.0, 0.18, -0.12], "rotationEuler": [35.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "back_equipment", "previewPose": "locomotion_idle", "notes": "Back carried equipment."},
    "head": {"bone": "Head", "position": [0.0, 0.12, 0.0], "rotationEuler": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "headgear", "previewPose": "neutral_idle", "notes": "Helmet, hat, mask, hair accessory."},
    "chest": {"bone": "Chest", "position": [0.0, 0.0, 0.04], "rotationEuler": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "armor", "previewPose": "neutral_idle", "notes": "Chest armor or torso equipment."},
    "hips": {"bone": "Hips", "position": [0.0, -0.04, 0.02], "rotationEuler": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "hip_equipment", "previewPose": "locomotion_idle", "notes": "Center hip anchor."},
    "belt": {"bone": "Hips", "position": [0.18, -0.04, 0.02], "rotationEuler": [0.0, 0.0, -8.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "belt_item", "previewPose": "locomotion_idle", "notes": "Belt pouch, potion, small side item."},
    "feet": {"bone": "RightFoot", "position": [0.0, 0.02, 0.0], "rotationEuler": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "footwear", "previewPose": "locomotion_idle", "notes": "Boot or foot equipment. Mirror if required in Unity."},
    "shoulders": {"bone": "RightShoulder", "position": [0.04, 0.02, 0.0], "rotationEuler": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "shoulder_armor", "previewPose": "combat_idle", "notes": "Shoulder armor. Mirror if required in Unity."},
    "right_hand_weapon": {"aliasOf": "main_hand"},
    "left_hand_offhand": {"aliasOf": "offhand"},
    "back_weapon": {"aliasOf": "back"},
    "headgear": {"aliasOf": "head"},
    "chest_armor": {"aliasOf": "chest"},
    "belt_right": {"aliasOf": "belt"},
    "belt_left": {"bone": "Hips", "position": [-0.18, -0.04, 0.02], "rotationEuler": [0.0, 0.0, 8.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "belt_item", "previewPose": "locomotion_idle", "notes": "Left belt side item."},
}


def resolve_slot(slot_id: str) -> dict[str, Any]:
    preset = DEFAULT_SLOTS.get(slot_id)
    if preset and "aliasOf" in preset:
        preset = DEFAULT_SLOTS[preset["aliasOf"]]
    if preset:
        return dict(preset)
    return {"bone": "", "position": [0.0, 0.0, 0.0], "rotationEuler": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "equipmentCategory": "equipment", "previewPose": "neutral_idle", "notes": "Custom attachment slot."}


def parse_vec(value: str, fallback: list[float]) -> list[float]:
    if not value:
        return fallback
    parts = [float(part.strip()) for part in value.replace(";", ",").split(",")]
    if len(parts) != 3:
        raise ValueError(f"Expected 3 values, got {value!r}")
    return parts


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slot_key(character_id: str, slot_id: str) -> str:
    return f"{character_id}:{slot_id}"


def sync_slot_identity(slot: dict[str, Any], character_id: str) -> dict[str, Any]:
    slot_id = slot.get("slotId", "")
    key = slot_key(character_id, slot_id) if character_id and slot_id else ""
    slot.setdefault("name", f"Socket_{slot_id}" if slot_id else "Socket")
    slot["attachmentKey"] = key
    slot["stableKey"] = key
    slot["lookup"] = {"characterId": character_id, "slotId": slot_id, "key": key}
    if "localPosition" not in slot and "position" in slot:
        slot["localPosition"] = slot["position"]
    if "position" not in slot and "localPosition" in slot:
        slot["position"] = slot["localPosition"]
    if "localRotationEuler" not in slot and "rotationEuler" in slot:
        slot["localRotationEuler"] = slot["rotationEuler"]
    if "rotationEuler" not in slot and "localRotationEuler" in slot:
        slot["rotationEuler"] = slot["localRotationEuler"]
    if "localScale" not in slot and "scale" in slot:
        slot["localScale"] = slot["scale"]
    if "scale" not in slot and "localScale" in slot:
        slot["scale"] = slot["localScale"]
    return slot


def finalize_manifest(manifest: dict[str, Any], created: bool = False) -> dict[str, Any]:
    character_id = manifest.get("characterId", "")
    manifest.setdefault("schema", "codex.characterAttachmentManifest.v1")
    if created:
        manifest.setdefault("createdAt", now_iso())
    manifest["updatedAt"] = now_iso()
    slots = manifest.get("slots") or []
    for slot in slots:
        sync_slot_identity(slot, character_id)
    manifest["slotLookup"] = {slot.get("slotId", ""): slot.get("attachmentKey", "") for slot in slots if slot.get("slotId")}
    return manifest


def validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not data.get("characterId"):
        errors.append("characterId is required")
    slots = data.get("slots")
    if not isinstance(slots, list) or not slots:
        errors.append("slots must be a non-empty list")
        return errors
    seen: set[str] = set()
    for index, slot in enumerate(slots):
        slot_id = slot.get("slotId")
        if not slot_id:
            errors.append(f"slots[{index}].slotId is required")
        elif slot_id in seen:
            errors.append(f"duplicate slotId: {slot_id}")
        else:
            seen.add(slot_id)
        if not slot.get("bone"):
            errors.append(f"slots[{index}].bone is required")
        for field, fallback in (("localPosition", "position"), ("localRotationEuler", "rotationEuler"), ("localScale", "scale")):
            value = slot.get(field) or slot.get(fallback)
            if not isinstance(value, list) or len(value) != 3 or not all(isinstance(v, (int, float)) for v in value):
                errors.append(f"slots[{index}].{field} must be [x,y,z]")
        if data.get("characterId") and slot_id:
            expected = slot_key(data["characterId"], slot_id)
            key = slot.get("attachmentKey") or slot.get("stableKey")
            if key and key != expected:
                errors.append(f"slots[{index}].attachmentKey must be {expected}")
    return errors


def make_slot(slot_id: str) -> dict[str, Any]:
    preset = resolve_slot(slot_id)
    return {
        "slotId": slot_id,
        "bone": preset["bone"],
        "localPosition": preset["position"],
        "position": preset["position"],
        "localRotationEuler": preset["rotationEuler"],
        "rotationEuler": preset["rotationEuler"],
        "localScale": preset["scale"],
        "scale": preset["scale"],
        "equipmentCategory": preset["equipmentCategory"],
        "previewPose": preset["previewPose"],
        "notes": preset["notes"],
        "space": "bone-local",
    }


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    selected = args.slots or ["main_hand", "offhand", "back", "head", "chest", "hips", "belt", "feet", "shoulders"]
    return finalize_manifest({
        "schema": "codex.characterAttachmentManifest.v1",
        "characterId": args.character_id,
        "rigName": args.rig_name,
        "coordinateSystem": {"upAxis": "+Y", "forwardAxis": "+Z", "rightAxis": "+X", "unit": "meter"},
        "slots": [make_slot(slot_id) for slot_id in selected],
        "notes": args.notes or "",
    }, created=True)


def update_slot(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.manifest)
    manifest = load_manifest(path)
    slots = manifest.setdefault("slots", [])
    current = next((slot for slot in slots if slot.get("slotId") == args.slot_id), None)
    if current is None:
        current = make_slot(args.slot_id)
        slots.append(current)
    if args.bone:
        current["bone"] = args.bone
    current["localPosition"] = parse_vec(args.position, current.get("localPosition") or current.get("position") or [0.0, 0.0, 0.0])
    current["position"] = current["localPosition"]
    current["localRotationEuler"] = parse_vec(args.rotation_euler, current.get("localRotationEuler") or current.get("rotationEuler") or [0.0, 0.0, 0.0])
    current["rotationEuler"] = current["localRotationEuler"]
    current["scale"] = parse_vec(args.scale, current.get("scale") or [1.0, 1.0, 1.0])
    if args.equipment_category:
        current["equipmentCategory"] = args.equipment_category
    if args.preview_pose:
        current["previewPose"] = args.preview_pose
    if args.notes:
        current["notes"] = args.notes
    finalize_manifest(manifest)
    errors = validate_manifest(manifest)
    if errors:
        raise SystemExit(json.dumps({"valid": False, "errors": errors}, indent=2))
    write_manifest(path, manifest)
    return {"valid": True, "manifest": str(path.resolve()), "slot": current}


def unity_socket_data(manifest: dict[str, Any]) -> dict[str, Any]:
    finalize_manifest(manifest)
    return {
        "schema": "codex.unitySocketPrefabData.v1",
        "characterId": manifest.get("characterId", ""),
        "rigName": manifest.get("rigName", ""),
        "sockets": [
            {
                "name": slot.get("name") or f"Socket_{slot.get('slotId')}",
                "attachmentKey": slot.get("attachmentKey") or slot.get("stableKey"),
                "stableKey": slot.get("stableKey") or slot.get("attachmentKey"),
                "slotId": slot.get("slotId"),
                "bone": slot.get("bone"),
                "localPosition": slot.get("localPosition") or slot.get("position"),
                "localRotationEuler": slot.get("localRotationEuler") or slot.get("rotationEuler"),
                "localScale": slot.get("scale"),
                "equipmentCategory": slot.get("equipmentCategory", "equipment"),
                "previewPose": slot.get("previewPose", ""),
                "notes": slot.get("notes", ""),
            }
            for slot in manifest.get("slots", [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create, update, list and validate character equipment attachment manifests.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--character-id", required=True)
    create.add_argument("--rig-name", default="Humanoid")
    create.add_argument("--out", required=True)
    create.add_argument("--slots", nargs="*")
    create.add_argument("--notes", default="")

    validate = sub.add_parser("validate")
    validate.add_argument("--manifest", required=True)

    update = sub.add_parser("update")
    update.add_argument("--manifest", required=True)
    update.add_argument("--slot-id", required=True)
    update.add_argument("--bone", default="")
    update.add_argument("--position", default="")
    update.add_argument("--rotation-euler", default="")
    update.add_argument("--scale", default="")
    update.add_argument("--equipment-category", default="")
    update.add_argument("--preview-pose", default="")
    update.add_argument("--notes", default="")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--manifest", required=True)

    export = sub.add_parser("export-unity")
    export.add_argument("--manifest", required=True)
    export.add_argument("--out", required=True)

    args = parser.parse_args()
    if args.cmd == "create":
        manifest = build_manifest(args)
        errors = validate_manifest(manifest)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, indent=2))
            return 2
        out = Path(args.out)
        write_manifest(out, manifest)
        print(json.dumps({"valid": True, "manifest": str(out.resolve()), "slots": len(manifest["slots"])}, indent=2))
        return 0
    if args.cmd == "update":
        print(json.dumps(update_slot(args), indent=2, ensure_ascii=False))
        return 0
    data = load_manifest(Path(args.manifest))
    finalize_manifest(data)
    errors = validate_manifest(data)
    if args.cmd == "validate":
        print(json.dumps({"valid": not errors, "errors": errors, "slotCount": len(data.get("slots") or [])}, indent=2))
        return 2 if errors else 0
    if args.cmd == "list":
        print(json.dumps({"valid": not errors, "slots": data.get("slots") or [], "errors": errors}, indent=2, ensure_ascii=False))
        return 2 if errors else 0
    export_data = unity_socket_data(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"valid": not errors, "out": str(out.resolve()), "socketCount": len(export_data["sockets"]), "errors": errors}, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
