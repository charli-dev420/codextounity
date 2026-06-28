from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic GLB bounds/pivot/rotation/scale normalizer for Codex Asset Factory.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rotate-euler", default="0,0,0")
    parser.add_argument("--scale", default="1,1,1")
    parser.add_argument("--offset", default="0,0,0")
    parser.add_argument("--target-bounds", default="")
    parser.add_argument("--pivot", choices=["bottom-center", "center", "origin", "custom", "keep"], default="bottom-center")
    parser.add_argument("--custom-pivot", default="0,0,0")
    parser.add_argument("--axis-remap", default="x,y,z", help="Axis remap, e.g. x,y,z or x,z,-y.")
    parser.add_argument("--tolerance", type=float, default=0.002)
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    script = Path(__file__).with_name("adjust_glb_transform.py")
    report = Path(args.report) if args.report else Path(args.output).with_suffix(".normalization_report.json")
    command = [
        sys.executable,
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
        args.pivot,
        "--custom-pivot",
        args.custom_pivot,
        "--axis-remap",
        args.axis_remap,
        "--tolerance",
        str(args.tolerance),
        "--report",
        str(report),
    ]
    if args.target_bounds:
        command.extend(["--target-bounds", args.target_bounds])
    completed = subprocess.run(command, text=True, capture_output=True)
    metadata = {
        "schema": "codex.normalizationWrapperReport.v1",
        "command": command,
        "input": str(Path(args.input).resolve()),
        "output": str(Path(args.output).resolve()),
        "pivotRequested": args.pivot,
        "customPivot": args.custom_pivot,
        "axisRemap": args.axis_remap,
        "tolerance": args.tolerance,
        "targetBounds": args.target_bounds,
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
