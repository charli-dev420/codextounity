from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned[:120] or "codex_reference"


def load_profile(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_config_path(value: str | None, base: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def resolve_input_dir(args: argparse.Namespace) -> Path:
    if args.input_dir:
        return Path(args.input_dir).resolve()
    if args.profile:
        profile_path = Path(args.profile).resolve()
        profile = load_profile(profile_path)
        input_dir = resolve_config_path(profile.get("inputDir"), Path.cwd())
        if input_dir:
            return input_dir
    raise ValueError("Input directory is required. Pass --input-dir or --profile with inputDir.")


def image_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    header = path.read_bytes()[:16]
    if suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if suffix == ".webp" and header.startswith(b"RIFF") and b"WEBP" in header:
        return "webp"
    raise ValueError(f"Not a supported PNG/JPG/WebP image or extension/header mismatch: {path}")


def unique_destination(input_dir: Path, stem: str, suffix: str, overwrite: bool) -> Path:
    destination = input_dir / f"{stem}{suffix}"
    if overwrite or not destination.exists():
        return destination
    for index in range(2, 1000):
        candidate = input_dir / f"{stem}_{index:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError(f"Could not find a free destination filename in {input_dir}")


def append_manifest(manifest_path: Path, entry: dict[str, Any]) -> None:
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Reference manifest must contain a JSON list: {manifest_path}")
    else:
        payload = []
    payload.append(entry)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def update_request_json(path: Path, destination: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    references = payload.get("referenceImages")
    if not isinstance(references, list):
        references = []
    destination_text = str(destination.resolve())
    if destination_text not in references:
        references.append(destination_text)
    payload["referenceImages"] = references
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place a Codex-created reference image into a TRELLIS2 input directory.",
    )
    parser.add_argument("--image", required=True, help="Path to the image produced or selected by Codex.")
    parser.add_argument("--input-dir", help="TRELLIS2 input directory. Overrides profile inputDir.")
    parser.add_argument("--profile", help="Profile JSON containing inputDir, such as configs/example.local.profile.json.")
    parser.add_argument("--asset-name", help="Destination filename stem. Defaults to the source image stem.")
    parser.add_argument("--prompt", default="", help="Prompt used to create the image, recorded in sidecar metadata.")
    parser.add_argument("--request-json", help="Optional Unity request JSON to update with the placed reference image path.")
    parser.add_argument("--manifest", help="Reference manifest path. Defaults to <input-dir>/_codex_reference_manifest.json.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target filename instead of creating a numeric suffix.")
    parser.add_argument("--dry-run", action="store_true", help="Report the resolved destination without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.image).resolve()
    if not source.is_file():
        print(f"ERROR: image not found: {source}", file=sys.stderr)
        return 2

    try:
        kind = image_kind(source)
        input_dir = resolve_input_dir(args)
        stem = safe_name(args.asset_name or source.stem)
        destination = unique_destination(input_dir, stem, source.suffix.lower(), args.overwrite)
        manifest_path = Path(args.manifest).resolve() if args.manifest else input_dir / "_codex_reference_manifest.json"
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    entry = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "destination": str(destination),
        "imageKind": kind,
        "prompt": args.prompt,
        "requestJson": "" if not args.request_json else str(Path(args.request_json).resolve()),
        "consumer": "ComfyUI-TRELLIS2",
    }

    print(f"Source image: {source}")
    print(f"TRELLIS2 input dir: {input_dir}")
    print(f"Destination image: {destination}")
    print(f"Reference manifest: {manifest_path}")
    if args.dry_run:
        print("DRY RUN: no files written")
        return 0

    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    sidecar_path = destination.with_suffix(destination.suffix + ".codex.json")
    sidecar_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    append_manifest(manifest_path, entry)

    if args.request_json:
        update_request_json(Path(args.request_json).resolve(), destination)

    print(f"Wrote image: {destination}")
    print(f"Wrote sidecar: {sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
