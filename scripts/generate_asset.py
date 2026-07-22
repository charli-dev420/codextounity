from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from asset_profile_defaults import resolve_fit_axis


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"


@dataclass(frozen=True)
class StepResult:
    name: str
    command: list[str]


def run_command(command: list[str], *, dry_run: bool) -> StepResult:
    print("RUN:", " ".join(quote(part) for part in command))
    if not dry_run:
        subprocess.run(command, check=True)
    return StepResult(name=Path(command[1]).stem if len(command) > 1 else command[0], command=command)


def quote(value: str) -> str:
    if any(ch.isspace() for ch in value) or "\\" in value:
        return f'"{value}"'
    return value


def ensure_reference_image(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"ERROR: reference image not found: {path}")


def find_newest_mesh(output_dir: Path) -> Path | None:
    meshes = [p for p in output_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".glb", ".gltf", ".obj", ".fbx", ".dae", ".stl"}]
    if not meshes:
        return None
    return max(meshes, key=lambda p: (p.stat().st_mtime, p.stat().st_size))


def normalize_single_glb(
    source: Path,
    output: Path,
    width: float,
    height: float,
    depth: float,
    args: argparse.Namespace,
) -> None:
    report = output.parent / "normalization_report.json"
    command = [
        sys.executable,
        "-B",
        str(SCRIPTS_DIR / "normalize_asset_bounds.py"),
        "--input",
        str(source),
        "--output",
        str(output),
        "--target-bounds",
        f"{width:g},{height:g},{depth:g}",
        "--pivot",
        args.pivot,
        "--rotate-euler",
        args.rotate_euler,
        "--scale",
        args.scale,
        "--offset",
        args.offset,
        "--axis-remap",
        args.axis_remap,
        "--fit-axis",
        resolve_fit_axis(args.asset_profile, args.fit_axis, Path(args.profiles_dir), args.sub_profile),
        "--custom-pivot",
        args.custom_pivot,
        "--tolerance",
        f"{args.tolerance:g}",
        "--report",
        str(report),
    ]
    if args.asset_profile:
        command.extend(["--profile", args.asset_profile, "--profiles-dir", args.profiles_dir])
    if args.sub_profile:
        command.extend(["--sub-profile", args.sub_profile])
    run_command(command, dry_run=args.dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one Unity-ready asset through Codex + local ComfyUI/TRELLIS2.")
    parser.add_argument("--asset-name", required=True, help="Stable asset id/name.")
    parser.add_argument("--reference-image", required=True, help="Codex-created or selected reference image.")
    parser.add_argument("--work-dir", required=True, help="Per-job working directory.")
    parser.add_argument("--target-width", type=float, required=True, help="Final normalized width in Unity meters.")
    parser.add_argument("--target-height", type=float, required=True, help="Final normalized height in Unity meters.")
    parser.add_argument("--target-depth", type=float, required=True, help="Final normalized depth/thickness in Unity meters.")
    parser.add_argument("--asset-profile", default="", help="Asset profile used for validation and manifest metadata.")
    parser.add_argument("--sub-profile", default="", help="Optional asset sub-profile, e.g. window_wall or wall_mirror.")
    parser.add_argument("--profiles-dir", default=str(PLUGIN_ROOT / "configs" / "asset-profiles"))
    parser.add_argument("--pivot", choices=["bottom-center", "center", "origin", "custom", "keep"], default="bottom-center")
    parser.add_argument("--rotate-euler", default="0,0,0", help="Post-generation rotation XYZ in degrees.")
    parser.add_argument("--scale", default="1", help="Uniform post-generation scale before target bounds. Non-uniform scale is rejected.")
    parser.add_argument("--offset", default="0,0,0", help="Post-generation offset XYZ after pivot/bounds.")
    parser.add_argument("--axis-remap", default="x,y,z", help="Axis remap, e.g. x,y,z or x,z,-y.")
    parser.add_argument("--fit-axis", choices=["auto", "contain", "x", "y", "z"], default="auto", help="Uniform fit rule. auto chooses by asset profile; contain fits inside the target envelope.")
    parser.add_argument("--custom-pivot", default="0,0,0", help="Custom pivot XYZ when --pivot custom is used.")
    parser.add_argument("--tolerance", type=float, default=0.002, help="Bounds validation tolerance after normalization.")
    parser.add_argument("--unity-project", help="Unity project root for import/copy.")
    parser.add_argument("--unity-subdir", default="Assets/AIAssetPipeline/Generated/UnityReady")
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--workflow", default="simple", choices=["simple", "low-poly", "mesh-only-hq", "mesh-with-texturing", "mesh-with-texturing-hq"])
    parser.add_argument("--seed", type=int, default=2146628683)
    parser.add_argument("--target-faces", type=int, default=18000)
    parser.add_argument("--texture-size", type=int, default=1024)
    parser.add_argument("--max-views", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-generation", action="store_true", help="Use the newest mesh already present in work-dir/raw.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reference = Path(args.reference_image).resolve()
    ensure_reference_image(reference)

    work_dir = Path(args.work_dir).resolve()
    input_dir = work_dir / "trellis2_inputs"
    raw_dir = work_dir / "raw"
    normalized_dir = work_dir / "normalized"
    reports_dir = work_dir / "reports"
    normalized_mesh = normalized_dir / f"{args.asset_name}.glb"

    if not args.dry_run:
        input_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

    prepare_cmd = [
        sys.executable,
        "-B",
        str(SCRIPTS_DIR / "prepare_trellis2_reference_image.py"),
        "--image",
        str(reference),
        "--input-dir",
        str(input_dir),
        "--asset-name",
        args.asset_name,
        "--overwrite",
    ]
    if args.dry_run:
        prepare_cmd.append("--dry-run")
    run_command(prepare_cmd, dry_run=args.dry_run)

    if not args.skip_generation:
        run_command(
            [
                sys.executable,
                "-B",
                str(SCRIPTS_DIR / "comfyui_trellis2_batch.py"),
                "--server",
                args.server,
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(raw_dir),
                "--official-workflow",
                args.workflow,
                "--prefix",
                args.asset_name,
                "--file-format",
                "glb",
                "--seed",
                str(args.seed),
                "--target-faces",
                str(args.target_faces),
                "--texture-size",
                str(args.texture_size),
                "--max-views",
                str(args.max_views),
                "--timeout",
                str(args.timeout),
                "--limit",
                "1",
            ],
            dry_run=args.dry_run,
        )

    raw_mesh = find_newest_mesh(raw_dir)
    if raw_mesh is None and not args.dry_run:
        raise SystemExit(f"ERROR: no mesh generated/found in {raw_dir}")
    if raw_mesh is None:
        raw_mesh = raw_dir / f"{args.asset_name}.glb"

    normalize_single_glb(raw_mesh, normalized_mesh, args.target_width, args.target_height, args.target_depth, args)

    if args.unity_project:
        post_cmd = [
            sys.executable,
            "-B",
            str(SCRIPTS_DIR / "postprocess_generation.py"),
            "--batch-output-dir",
            str(normalized_dir),
            "--unity-project",
            str(Path(args.unity_project).resolve()),
            "--unity-subdir",
            args.unity_subdir,
            "--select",
            "newest",
            "--limit",
            "1",
            "--asset-id",
            args.asset_name,
            "--reference-image",
            str(reference),
            "--workflow-label",
            f"trellis2_{args.workflow}",
            "--generation-profile",
            "CodexPluginLocalComfyUI",
            "--validation-profile",
            f"{args.asset_profile or 'custom'}_{args.sub_profile or 'base'}_{args.target_width:g}x{args.target_height:g}x{args.target_depth:g}_{args.pivot}_{resolve_fit_axis(args.asset_profile, args.fit_axis, Path(args.profiles_dir), args.sub_profile)}",
            "--normalization-report",
            str(normalized_dir / "normalization_report.json"),
        ]
        if args.asset_profile:
            post_cmd.extend(["--asset-profile", args.asset_profile, "--profiles-dir", args.profiles_dir])
        if args.sub_profile:
            post_cmd.extend(["--sub-profile", args.sub_profile])
        run_command(post_cmd, dry_run=args.dry_run)

    if not args.dry_run:
        summary = {
            "assetName": args.asset_name,
            "referenceImage": str(reference),
            "rawMesh": str(raw_mesh),
            "normalizedMesh": str(normalized_mesh),
            "targetBounds": [args.target_width, args.target_height, args.target_depth],
            "assetProfile": args.asset_profile,
            "subProfile": args.sub_profile,
            "normalization": {
                "pivot": args.pivot,
                "rotateEuler": args.rotate_euler,
                "scale": args.scale,
                "offset": args.offset,
                "axisRemap": args.axis_remap,
                "fitAxis": resolve_fit_axis(args.asset_profile, args.fit_axis, Path(args.profiles_dir), args.sub_profile),
                "fitMode": "preserve-aspect",
                "customPivot": args.custom_pivot,
                "tolerance": args.tolerance,
            },
            "unityProject": args.unity_project or "",
        }
        summary_path = reports_dir / f"{args.asset_name}.codex_asset_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"summary: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
