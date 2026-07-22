from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from validate_runtime_asset import validate_runtime_asset


MESH_EXTENSIONS = {".glb", ".gltf", ".obj", ".fbx", ".dae", ".stl"}


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned[:120] or "asset"


def discover_meshes(batch_output_dir: Path) -> list[Path]:
    meshes: list[Path] = []
    for path in batch_output_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in MESH_EXTENSIONS:
            continue
        meshes.append(path)
    return sorted(meshes, key=lambda p: str(p).lower())


def select_meshes(meshes: list[Path], mode: str, limit: int) -> list[Path]:
    if mode == "all":
        selected = meshes
    elif mode == "newest":
        selected = sorted(meshes, key=lambda p: (p.stat().st_mtime, p.stat().st_size), reverse=True)
    elif mode == "largest":
        selected = sorted(meshes, key=lambda p: (p.stat().st_size, p.stat().st_mtime), reverse=True)
    elif mode == "first":
        selected = meshes
    else:
        raise ValueError(f"Unsupported selection mode: {mode}")
    return selected[:limit] if limit > 0 else selected


def unity_ready_path(unity_project: Path, unity_subdir: str, source: Path) -> Path:
    relative_subdir = unity_subdir.replace("\\", "/").strip("/")
    if not relative_subdir.startswith("Assets/"):
        raise ValueError("--unity-subdir must be a Unity-relative path starting with Assets/")
    if ".." in relative_subdir.split("/"):
        raise ValueError("--unity-subdir cannot contain ..")
    unity_project = unity_project.resolve()
    candidate = (unity_project / relative_subdir / safe_name(source.stem) / source.name).resolve()
    assets_root = (unity_project / "Assets").resolve()
    if not is_relative_to(candidate, assets_root):
        raise ValueError("--unity-subdir resolves outside the Unity project Assets folder")
    return candidate


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def default_manifest_dir(args: argparse.Namespace) -> Path:
    if args.manifest_dir:
        return Path(args.manifest_dir).resolve()
    if args.unity_project:
        return Path(args.unity_project).resolve() / "Assets" / "AIAssetPipeline" / "Data" / "Results"
    return Path(args.batch_output_dir).resolve() / "_codex_postprocess"


def validate_manifest_dir(args: argparse.Namespace, manifest_dir: Path, batch_output_dir: Path) -> None:
    if not args.manifest_dir or args.allow_external_manifest_dir:
        return
    allowed_roots = [batch_output_dir.resolve()]
    if args.unity_project:
        allowed_roots.append((Path(args.unity_project).resolve() / "Assets").resolve())
    if not any(is_relative_to(manifest_dir, root) for root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots)
        raise ValueError(f"--manifest-dir must stay under one of: {roots}. Pass --allow-external-manifest-dir to override.")


def asset_id_for_source(source: Path, args: argparse.Namespace) -> str:
    asset_id = args.asset_id or safe_name(source.stem)
    if args.asset_id_prefix:
        asset_id = f"{safe_name(args.asset_id_prefix)}_{asset_id}"
    return asset_id


def manifest_bundle_dir(source: Path, args: argparse.Namespace, manifest_dir: Path) -> Path:
    return manifest_dir / safe_name(asset_id_for_source(source, args))


def build_manifest(
    source: Path,
    unity_ready: Path,
    manifest_path: Path,
    args: argparse.Namespace,
    validation_errors: list[str],
    validation_warnings: list[str],
) -> dict[str, Any]:
    asset_id = asset_id_for_source(source, args)
    validation_passed = not validation_errors
    bundle_dir = manifest_path.parent / safe_name(asset_id)
    asset_manifest_path = bundle_dir / "asset_manifest.json"
    generation_manifest_path = bundle_dir / "generation_manifest.json"
    unity_import_manifest_path = bundle_dir / "unity_import_manifest.json"
    normalization_report_path = bundle_dir / "normalization_report.json"
    runtime_validation_report_path = bundle_dir / "runtime_validation_report.json"
    character_attachments_path = bundle_dir / "character_attachments.json"
    prefab_path = unity_ready.with_name(f"{safe_name(unity_ready.stem)}_unity_ready.prefab")
    return {
        "schema": "codex.unityResultManifest.v2",
        "jobId": asset_id,
        "requestId": args.request_id or asset_id,
        "assetId": asset_id,
        "status": "ValidationPassed" if validation_passed else "NeedsManualReview",
        "generatedMesh": str(unity_ready),
        "rawMesh": str(source),
        "processedMesh": str(unity_ready),
        "unityReadyMesh": str(unity_ready),
        "unityPrefabPath": str(prefab_path),
        "sourceImagenReferenceImage": args.reference_image or "",
        "comfyWorkflow": args.workflow_label,
        "generationProfile": args.generation_profile,
        "hardwareProfile": "local_comfyui",
        "validationProfile": args.validation_profile,
        "importManifestPath": str(manifest_path),
        "validationPassed": validation_passed,
        "validationErrors": validation_errors,
        "validationWarnings": validation_warnings,
        "sourceComfyBatchOutput": str(Path(args.batch_output_dir).resolve()),
        "assetManifestPath": str(asset_manifest_path.resolve()),
        "generationManifestPath": str(generation_manifest_path.resolve()),
        "normalizationReportPath": str(normalization_report_path),
        "sourceNormalizationReportPath": args.normalization_report or "",
        "validationReportPath": str(runtime_validation_report_path.resolve()) if args.asset_profile else "",
        "unityImportManifestPath": str(unity_import_manifest_path.resolve()),
        "characterAttachmentsPath": str(character_attachments_path.resolve()) if args.character_attachments else "",
        "sourceCharacterAttachmentsPath": args.character_attachments or "",
    }


def write_manifest_bundle(manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    asset_manifest_path = Path(manifest["assetManifestPath"])
    generation_manifest_path = Path(manifest["generationManifestPath"])
    normalization_report_path = Path(manifest["normalizationReportPath"])
    unity_import_manifest_path = Path(manifest["unityImportManifestPath"])
    asset_manifest = {
        "schema": "codex.assetManifest.v1",
        "assetId": manifest["assetId"],
        "jobId": manifest["jobId"],
        "requestId": manifest["requestId"],
        "sourceReferenceImage": manifest["sourceImagenReferenceImage"],
        "rawMesh": manifest["rawMesh"],
        "unityReadyMesh": manifest["unityReadyMesh"],
        "unityPrefabPath": manifest["unityPrefabPath"],
        "status": manifest["status"],
        "validationPassed": manifest["validationPassed"],
        "validationErrors": manifest["validationErrors"],
        "validationWarnings": manifest["validationWarnings"],
        "validationReportPath": manifest["validationReportPath"],
    }
    generation_manifest = {
        "schema": "codex.generationManifest.v1",
        "assetId": manifest["assetId"],
        "comfyWorkflow": manifest["comfyWorkflow"],
        "generationProfile": manifest["generationProfile"],
        "hardwareProfile": manifest["hardwareProfile"],
        "sourceComfyBatchOutput": manifest["sourceComfyBatchOutput"],
    }
    unity_import_manifest = {
        "schema": "codex.unityImportManifest.v1",
        "assetId": manifest["assetId"],
        "unityProject": str(Path(args.unity_project).resolve()) if args.unity_project else "",
        "unitySubdir": args.unity_subdir,
        "unityReadyMesh": manifest["unityReadyMesh"],
        "unityPrefabPath": manifest["unityPrefabPath"],
        "characterAttachmentsPath": manifest["characterAttachmentsPath"],
        "importStatus": "ready" if manifest["validationPassed"] else "review_needed",
    }
    for path, data in (
        (asset_manifest_path, asset_manifest),
        (generation_manifest_path, generation_manifest),
        (unity_import_manifest_path, unity_import_manifest),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.normalization_report and Path(args.normalization_report).is_file():
        normalization_report_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.normalization_report, normalization_report_path)
    elif not normalization_report_path.exists():
        normalization_report_path.parent.mkdir(parents=True, exist_ok=True)
        normalization_report_path.write_text(json.dumps({"schema": "codex.normalizationReport.v2", "status": "not_supplied", "assetId": manifest["assetId"]}, indent=2), encoding="utf-8")
    if args.character_attachments and Path(args.character_attachments).is_file():
        target = Path(manifest["characterAttachmentsPath"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.character_attachments, target)
    return {
        "assetManifestPath": str(asset_manifest_path.resolve()),
        "generationManifestPath": str(generation_manifest_path.resolve()),
        "normalizationReportPath": str(normalization_report_path.resolve()),
        "unityImportManifestPath": str(unity_import_manifest_path.resolve()),
    }


def process_mesh(source: Path, args: argparse.Namespace, manifest_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if source.stat().st_size <= 0:
        errors.append("mesh file is empty")

    unity_ready = source
    if args.unity_project and args.copy_to_unity:
        unity_project = Path(args.unity_project).resolve()
        unity_ready = unity_ready_path(unity_project, args.unity_subdir, source)
        if not args.dry_run:
            unity_ready.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, unity_ready)
    elif not args.unity_project:
        warnings.append("no Unity project supplied; manifest points to the generated mesh in place")

    manifest_path = manifest_dir / f"{safe_name(source.stem)}.unity_manifest.json"
    runtime_report_path = manifest_bundle_dir(source, args, manifest_dir) / "runtime_validation_report.json"
    if args.asset_profile:
        runtime_report = validate_runtime_asset(
            mesh=source,
            profile_id=args.asset_profile,
            profiles_dir=Path(args.profiles_dir),
            sub_profile_id=args.sub_profile,
            normalization_report=Path(args.normalization_report) if args.normalization_report else None,
            manifest=None,
        )
        errors.extend(runtime_report["errors"])
        warnings.extend(runtime_report["warnings"])
        if not args.dry_run:
            runtime_report_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_report_path.write_text(json.dumps(runtime_report, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = build_manifest(source.resolve(), unity_ready.resolve(), manifest_path.resolve(), args, errors, warnings)
    if not args.dry_run:
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        bundle_paths = write_manifest_bundle(manifest, args)
        if args.asset_profile:
            runtime_report = validate_runtime_asset(
                mesh=source,
                profile_id=args.asset_profile,
                profiles_dir=Path(args.profiles_dir),
                sub_profile_id=args.sub_profile,
                normalization_report=Path(args.normalization_report) if args.normalization_report else None,
                manifest=manifest_path,
            )
            errors = list(runtime_report["errors"])
            warnings = list(runtime_report["warnings"])
            runtime_report_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_report_path.write_text(json.dumps(runtime_report, indent=2, ensure_ascii=False), encoding="utf-8")
            manifest = build_manifest(source.resolve(), unity_ready.resolve(), manifest_path.resolve(), args, errors, warnings)
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            bundle_paths = write_manifest_bundle(manifest, args)
    else:
        bundle_paths = {
            "assetManifestPath": manifest["assetManifestPath"],
            "generationManifestPath": manifest["generationManifestPath"],
            "normalizationReportPath": manifest["normalizationReportPath"],
            "unityImportManifestPath": manifest["unityImportManifestPath"],
        }
    return {
        "source": str(source.resolve()),
        "unityReadyMesh": str(unity_ready.resolve()),
        "unityPrefabPath": manifest["unityPrefabPath"],
        "manifestPath": str(manifest_path.resolve()),
        **bundle_paths,
        "validationReportPath": manifest["validationReportPath"],
        "validationPassed": manifest["validationPassed"],
        "validationErrors": errors,
        "validationWarnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Codex-side post-processing for local ComfyUI mesh generation.",
    )
    parser.add_argument("--batch-output-dir", required=True, help="ComfyUI batch output directory to inspect.")
    parser.add_argument("--unity-project", help="Unity project root. When set, meshes are copied under Assets/.")
    parser.add_argument("--unity-subdir", default="Assets/AIAssetPipeline/Generated/UnityReady", help="Unity-relative destination for copied meshes.")
    parser.add_argument("--manifest-dir", help="Directory for Unity import manifests. Defaults to the Unity project results folder.")
    parser.add_argument("--select", choices=["all", "newest", "largest", "first"], default="all", help="Mesh selection strategy.")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap after selection. 0 means no cap.")
    parser.add_argument("--asset-id", help="Override jobId/requestId when exactly one mesh is selected.")
    parser.add_argument("--asset-id-prefix", default="", help="Optional prefix added to generated manifest IDs.")
    parser.add_argument("--request-id", default="", help="Unity requestId to associate with generated manifests.")
    parser.add_argument("--reference-image", default="", help="Reference image path recorded in the Unity manifest.")
    parser.add_argument("--workflow-label", default="trellis2", help="Workflow label recorded in the Unity manifest.")
    parser.add_argument("--generation-profile", default="LocalComfyUI", help="Generation profile recorded in the Unity manifest.")
    parser.add_argument("--validation-profile", default="CodexPostGeneration", help="Validation profile recorded in the Unity manifest.")
    parser.add_argument("--asset-profile", default="", help="Asset profile id used for runtime mesh validation.")
    parser.add_argument("--sub-profile", default="", help="Optional asset sub-profile id used for runtime mesh validation.")
    parser.add_argument("--profiles-dir", default=str(Path(__file__).resolve().parents[1] / "configs" / "asset-profiles"))
    parser.add_argument("--normalization-report", default="", help="Optional normalization_report.json to copy/link into the manifest bundle.")
    parser.add_argument("--character-attachments", default="", help="Optional character_attachments.json path recorded for Unity socket import.")
    parser.add_argument("--require-single", action="store_true", help="Fail when selection does not resolve to exactly one mesh.")
    parser.add_argument("--allow-external-manifest-dir", action="store_true", help="Allow --manifest-dir outside batch output or Unity Assets.")
    parser.add_argument("--copy-to-unity", action=argparse.BooleanOptionalAction, default=True, help="Copy selected meshes into the Unity project when --unity-project is set.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned manifests without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    batch_output_dir = Path(args.batch_output_dir).resolve()
    if not batch_output_dir.exists():
        print(f"ERROR: batch output directory not found: {batch_output_dir}")
        return 2
    if args.unity_project:
        unity_project = Path(args.unity_project).resolve()
        if not (unity_project / "Assets").is_dir():
            print(f"ERROR: Unity project root must contain an Assets folder: {unity_project}")
            return 2

    meshes = discover_meshes(batch_output_dir)
    selected = select_meshes(meshes, args.select, args.limit)
    if not selected:
        print(f"ERROR: no mesh files found in {batch_output_dir}; expected one of {sorted(MESH_EXTENSIONS)}")
        return 2
    if args.require_single and len(selected) != 1:
        print(f"ERROR: ambiguous mesh selection: expected exactly one mesh, selected {len(selected)} from {len(meshes)} discovered")
        return 2
    if args.asset_id and len(selected) != 1:
        print("ERROR: --asset-id can only be used when exactly one mesh is selected.")
        return 2

    manifest_dir = default_manifest_dir(args)
    try:
        validate_manifest_dir(args, manifest_dir, batch_output_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    entries = [process_mesh(source, args, manifest_dir) for source in selected]
    index_path = manifest_dir / "codex_postprocess_index.json"
    if not args.dry_run:
        index_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Meshes discovered: {len(meshes)}")
    print(f"Meshes selected:   {len(selected)}")
    print(f"Manifest dir:      {manifest_dir}")
    for entry in entries:
        print(f"manifest: {entry['manifestPath']}")
    if any(not entry["validationPassed"] for entry in entries):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
