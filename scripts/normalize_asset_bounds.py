from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from asset_profile_defaults import bounds_to_text, resolve_profile_target


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic GLB bounds/pivot/rotation/scale normalizer for Codex Asset Factory.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rotate-euler", default="0,0,0")
    parser.add_argument("--scale", default="1")
    parser.add_argument("--offset", default="0,0,0")
    parser.add_argument("--target-bounds", default="")
    parser.add_argument("--fit-axis", choices=["contain", "x", "y", "z"], default=None)
    parser.add_argument("--pivot", choices=["bottom-center", "center", "origin", "custom", "keep"], default=None)
    parser.add_argument("--custom-pivot", default="0,0,0")
    parser.add_argument("--axis-remap", default="x,y,z", help="Axis remap, e.g. x,y,z or x,z,-y.")
    parser.add_argument("--tolerance", type=float, default=None)
    parser.add_argument("--report", default="")
    parser.add_argument("--profile", default="", help="Asset profile id used to resolve target bounds, pivot, tolerance and fit axis.")
    parser.add_argument("--sub-profile", default="", help="Optional asset sub-profile id or alias, e.g. window_wall or wall_mirror.")
    parser.add_argument("--profiles-dir", default=str(Path(__file__).resolve().parents[1] / "configs" / "asset-profiles"))
    args = parser.parse_args()

    profile_resolution = None
    target_bounds = args.target_bounds
    fit_axis = args.fit_axis
    pivot = args.pivot
    tolerance = args.tolerance
    if args.profile:
        try:
            profile_resolution = resolve_profile_target(args.profile, Path(args.profiles_dir), args.sub_profile)
        except Exception as exc:
            print(f"ERROR: profile resolution failed: {exc}", file=sys.stderr)
            return 2
        if not target_bounds:
            target_bounds = bounds_to_text(profile_resolution["targetBoundsList"])
        if fit_axis is None:
            fit_axis = profile_resolution["fitAxis"]
        if pivot is None:
            pivot = profile_resolution["pivotMode"]
        if tolerance is None:
            tolerance = float((profile_resolution["validationRules"] or {}).get("boundsTolerance") or 0.002)
    if fit_axis is None:
        fit_axis = "contain"
    if pivot is None:
        pivot = "bottom-center"
    if tolerance is None:
        tolerance = 0.002

    script = Path(__file__).with_name("adjust_glb_transform.py")
    report = Path(args.report) if args.report else Path(args.output).with_suffix(".normalization_report.json")
    command = [
        sys.executable,
        "-B",
        str(script),
        "--input",
        args.input,
        "--output",
        args.output,
        "--rotate-euler",
        args.rotate_euler,
        "--scale",
        args.scale,
        "--offset",
        args.offset,
        "--pivot",
        pivot,
        "--custom-pivot",
        args.custom_pivot,
        "--axis-remap",
        args.axis_remap,
        "--tolerance",
        str(tolerance),
        "--report",
        str(report),
    ]
    if target_bounds:
        command.extend(["--target-bounds", target_bounds])
    command.extend(["--fit-axis", fit_axis])
    completed = subprocess.run(command, text=True, capture_output=True)
    metadata = {
        "schema": "codex.normalizationWrapperReport.v1",
        "command": command,
        "input": str(Path(args.input).resolve()),
        "output": str(Path(args.output).resolve()),
        "profile": args.profile,
        "subProfile": profile_resolution["subProfileId"] if profile_resolution else args.sub_profile,
        "normalizationDefaults": profile_resolution["normalizationDefaults"] if profile_resolution else {},
        "pivotRequested": args.pivot or "",
        "pivotResolved": pivot,
        "customPivot": args.custom_pivot,
        "axisRemap": args.axis_remap,
        "fitAxisRequested": args.fit_axis or "",
        "fitAxis": fit_axis,
        "tolerance": tolerance,
        "targetBoundsRequested": args.target_bounds,
        "targetBounds": target_bounds,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exitCode": completed.returncode,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        try:
            existing = json.loads(report.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                metadata = {**existing, "wrapper": metadata}
        except Exception:
            pass
    report.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    print(f"normalization report: {report}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
