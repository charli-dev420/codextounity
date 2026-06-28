from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp"}


def analyze_image(path: Path, expected_object: str, force: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    info: dict[str, Any] = {"path": str(path), "expectedObject": expected_object}
    if not path.is_file():
        errors.append(f"missing file: {path}")
        return result(path, expected_object, force, errors, warnings, info)
    ext = path.suffix.lower()
    info["format"] = ext.lstrip(".")
    info["bytes"] = path.stat().st_size
    if ext not in SUPPORTED:
        errors.append(f"unsupported image format: {ext or 'none'}")
    if path.stat().st_size < 1024:
        warnings.append("file is very small; verify it is not a placeholder")
    if path.stat().st_size > 30 * 1024 * 1024:
        warnings.append("file is large; resize before TRELLIS2 if memory is constrained")

    try:
        from PIL import Image, ImageStat
    except Exception as exc:  # pragma: no cover - environment fallback
        warnings.append(f"Pillow unavailable; only file-level validation was possible: {exc}")
        return result(path, expected_object, force, errors, warnings, info)

    try:
        with Image.open(path) as image:
            info["mode"] = image.mode
            info["width"], info["height"] = image.size
            if image.width < 256 or image.height < 256:
                errors.append("image dimensions are below 256px")
            if image.width > 4096 or image.height > 4096:
                warnings.append("image dimensions are above 4096px; resize for stable local processing")
            rgb = image.convert("RGB")
            sample = rgb.resize((min(512, rgb.width), min(512, rgb.height)))
            bg = background_stats(sample, ImageStat)
            info["background"] = bg
            if not bg["likelyUniform"]:
                warnings.append("border/background is not uniformly clean; Codex should visually review before TRELLIS2")
            shadow = shadow_stats(sample, ImageStat)
            info["shadow"] = shadow
            if shadow["possibleCastShadow"]:
                warnings.append("bottom band is darker than the border; possible cast/contact shadow")
            info["alphaPresent"] = "A" in image.getbands()
    except Exception as exc:
        errors.append(f"image decode failed: {exc}")

    warnings.append("Manual/Codex visual decision still required for single object, no text, no dimension marks, and correct style/proportions.")
    return result(path, expected_object, force, errors, warnings, info)


def background_stats(image, image_stat) -> dict[str, Any]:
    w, h = image.size
    band = max(2, min(w, h) // 24)
    strips = [
        image.crop((0, 0, w, band)),
        image.crop((0, h - band, w, h)),
        image.crop((0, 0, band, h)),
        image.crop((w - band, 0, w, h)),
    ]
    values: list[float] = []
    for strip in strips:
        stat = image_stat.Stat(strip)
        values.extend(stat.stddev)
    mean_std = sum(values) / max(1, len(values))
    max_std = max(values) if values else 0.0
    return {
        "borderBandPx": band,
        "meanStdDev": round(mean_std, 3),
        "maxStdDev": round(max_std, 3),
        "likelyUniform": mean_std <= 18.0 and max_std <= 45.0,
    }


def shadow_stats(image, image_stat) -> dict[str, Any]:
    w, h = image.size
    band = max(4, h // 8)
    bottom = image.crop((0, h - band, w, h)).convert("L")
    border = image.crop((0, 0, w, max(4, h // 16))).convert("L")
    bottom_mean = image_stat.Stat(bottom).mean[0]
    border_mean = image_stat.Stat(border).mean[0]
    bottom_std = image_stat.Stat(bottom).stddev[0]
    possible = bottom_mean + 18 < border_mean and bottom_std > 12
    return {
        "bottomMean": round(bottom_mean, 3),
        "topBorderMean": round(border_mean, 3),
        "bottomStdDev": round(bottom_std, 3),
        "possibleCastShadow": bool(possible),
    }


def result(path: Path, expected_object: str, force: bool, errors: list[str], warnings: list[str], info: dict[str, Any]) -> dict[str, Any]:
    return {
        "imagePath": str(path),
        "expectedObject": expected_object,
        "valid": bool(force or not errors),
        "forced": bool(force),
        "errors": errors,
        "warnings": warnings,
        "imageInfo": info,
        "reviewChecklist": [
            "single object only",
            "plain background",
            "no text",
            "no measurement marks",
            "no cast/contact shadow",
            "3/4 top-down or requested view",
            "style and proportions match target",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a reference image before TRELLIS2 image-to-3D generation.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-object", default="asset")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = analyze_image(Path(args.image).resolve(), args.expected_object, args.force)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
