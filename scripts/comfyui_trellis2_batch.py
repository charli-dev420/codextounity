from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import os
import posixpath
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW_DIR = PLUGIN_ROOT / "workflows"

OFFICIAL_WORKFLOWS = {
    "simple": {
        "filename": "trellis2_simple.api.json",
        "url": None,
    },
    "mesh-only-hq": {
        "filename": "trellis2_mesh-only-hq.ui.json",
        "url": "https://raw.githubusercontent.com/visualbruno/ComfyUI-Trellis2/main/example_workflows/MeshOnly_HighQuality.json",
    },
    "mesh-with-texturing-hq": {
        "filename": "trellis2_mesh-with-texturing-hq.ui.json",
        "url": "https://raw.githubusercontent.com/visualbruno/ComfyUI-Trellis2/main/example_workflows/MeshTexturing_HighQuality.json",
    },
    "mesh-with-texturing": {
        "filename": "trellis2_mesh-with-texturing.ui.json",
        "url": "https://raw.githubusercontent.com/visualbruno/ComfyUI-Trellis2/main/example_workflows/MeshWithTexturing.json",
    },
    "low-poly": {
        "filename": "trellis2_low-poly.ui.json",
        "url": "https://raw.githubusercontent.com/visualbruno/ComfyUI-Trellis2/main/example_workflows/MeshWithTexturing_LowPoly.json",
    },
}

HTTP_HEADERS = {"User-Agent": "trellis2-batch/1.0"}

LOAD_IMAGE_CLASSES = {
    "LoadImage",
    "Trellis2LoadImageWithTransparency",
}

DROP_UI_NODE_CLASSES = {
    "Preview3D",
}

MESH_EXTENSIONS = (".glb", ".gltf", ".obj", ".mtl", ".png", ".jpg", ".jpeg", ".webp", ".ply", ".stl", ".fbx", ".dae", ".3mf")
EXPORT_MESH_EXTENSIONS = (".glb", ".gltf", ".obj", ".ply", ".stl", ".fbx", ".dae", ".3mf")

WIDGET_PRIMITIVE_TYPES = {
    "INT",
    "FLOAT",
    "STRING",
    "BOOLEAN",
    "IMAGEUPLOAD",
}

LINK_ONLY_TYPES = {
    "IMAGE",
    "MASK",
    "LATENT",
    "MODEL",
    "VAE",
    "CLIP",
    "CONDITIONING",
    "TRIMESH",
    "MESHWITHVOXEL",
    "TRELLIS2PIPELINE",
    "IMAGE_COND",
    "COORDS",
    "SHAPE_SLAT",
    "TEXTURE_SLAT",
    "BVH",
    "LOAD3D_CAMERA",
}


class ComfyError(RuntimeError):
    pass


def normalize_server(server: str) -> str:
    server = server.strip().rstrip("/")
    if not server.startswith(("http://", "https://")):
        server = "http://" + server
    return server


def http_json(server: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    url = server + path
    data = None
    headers = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = request.Request(url, data=data, headers={**HTTP_HEADERS, **headers}, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ComfyError(f"HTTP {exc.code} for {url}: {body}") from exc
    except error.URLError as exc:
        raise ComfyError(f"Cannot reach ComfyUI at {url}: {exc}") from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def download_url(url: str, out_path: Path, timeout: int = 120) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = request.Request(url, headers=HTTP_HEADERS)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            out_path.write_bytes(response.read())
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ComfyError(f"Could not download {url}: HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise ComfyError(f"Could not download {url}: {exc}") from exc
    return out_path


def multipart_post(server: str, path: str, fields: dict[str, str], file_field: str, file_path: Path) -> Any:
    boundary = "----trellis2batch" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    for key, value in fields.items():
        add_field(key, value)

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = request.Request(
        server + path,
        data=bytes(body),
        headers={**HTTP_HEADERS, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=180) as response:
            raw = response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ComfyError(f"Upload failed for {file_path}: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise ComfyError(f"Upload failed for {file_path}: {exc}") from exc
    return json.loads(raw.decode("utf-8")) if raw else {}


def upload_image(server: str, image_path: Path, subfolder: str, overwrite: bool) -> str:
    response = multipart_post(
        server,
        "/upload/image",
        {
            "type": "input",
            "subfolder": subfolder,
            "overwrite": "true" if overwrite else "false",
        },
        "image",
        image_path,
    )
    name = response.get("name") or response.get("filename") or image_path.name
    returned_subfolder = response.get("subfolder", subfolder) or ""
    if returned_subfolder:
        return posixpath.join(returned_subfolder.replace("\\", "/"), name)
    return name


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned[:120] or "asset"


def load_workflow(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def is_ui_workflow(workflow: dict[str, Any]) -> bool:
    return isinstance(workflow.get("nodes"), list)


def strip_ignored_api_nodes(prompt: dict[str, Any]) -> dict[str, Any]:
    ignored = {
        node_id
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") in DROP_UI_NODE_CLASSES
    }
    if not ignored:
        return prompt

    cleaned: dict[str, Any] = {}
    for node_id, node in prompt.items():
        if node_id in ignored:
            continue
        if not isinstance(node, dict):
            cleaned[node_id] = node
            continue
        node = copy.deepcopy(node)
        inputs = node.get("inputs")
        if isinstance(inputs, dict):
            for key, value in list(inputs.items()):
                if isinstance(value, list) and value and str(value[0]) in ignored:
                    del inputs[key]
        cleaned[node_id] = node
    return cleaned


def node_title(node: dict[str, Any]) -> str:
    return str(node.get("title") or node.get("_meta", {}).get("title") or "")


def spec_kind(spec: Any) -> Any:
    if isinstance(spec, (list, tuple)) and spec:
        return spec[0]
    return spec


def is_widget_spec(spec: Any) -> bool:
    kind = spec_kind(spec)
    if isinstance(kind, list):
        return True
    if isinstance(kind, str):
        if kind in WIDGET_PRIMITIVE_TYPES:
            return True
        if kind in LINK_ONLY_TYPES:
            return False
        if "," in kind and "FILE_3D" in kind:
            return True
    if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict):
        return True
    return False


def is_seed_control_value(value: Any) -> bool:
    return isinstance(value, str) and value.lower() in {"fixed", "randomize", "increment", "decrement"}


def coerce_widget_value(value: Any, spec: Any) -> Any:
    kind = spec_kind(spec)
    if isinstance(kind, list):
        if kind and all(isinstance(option, int) and not isinstance(option, bool) for option in kind):
            return int(value)
        if kind and all(isinstance(option, (int, float)) and not isinstance(option, bool) for option in kind):
            return float(value)
        return value
    if kind == "INT":
        return int(value)
    if kind == "FLOAT":
        return float(value)
    if kind == "BOOLEAN" and isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value


def ordered_input_specs(object_info: dict[str, Any], class_type: str) -> list[tuple[str, Any]]:
    node_info = object_info.get(class_type)
    if not node_info:
        raise ComfyError(
            f"ComfyUI does not expose node class '{class_type}'. "
            "Verify that ComfyUI-Trellis2 is installed and loaded."
        )
    input_info = node_info.get("input", {})
    ordered: list[tuple[str, Any]] = []
    for section in ("required", "optional"):
        values = input_info.get(section, {})
        ordered.extend(values.items())
    return ordered


def convert_ui_workflow_to_api(ui_workflow: dict[str, Any], object_info: dict[str, Any]) -> dict[str, Any]:
    link_by_id: dict[int, tuple[int, int]] = {}
    for link in ui_workflow.get("links", []):
        if isinstance(link, list) and len(link) >= 5:
            link_by_id[int(link[0])] = (int(link[1]), int(link[2]))

    prompt: dict[str, Any] = {}
    for node in ui_workflow.get("nodes", []):
        class_type = node.get("type")
        if not class_type or class_type in DROP_UI_NODE_CLASSES or node.get("mode") == 2:
            continue

        inputs: dict[str, Any] = {}
        linked_widget_inputs: set[str] = set()
        for input_slot in node.get("inputs", []) or []:
            link_id = input_slot.get("link")
            if link_id is None:
                continue
            if int(link_id) not in link_by_id:
                continue
            src_node, src_slot = link_by_id[int(link_id)]
            inputs[input_slot["name"]] = [str(src_node), int(src_slot)]
            if input_slot.get("widget"):
                linked_widget_inputs.add(input_slot["name"])

        widget_values = list(node.get("widgets_values") or [])
        widget_index = 0
        for input_name, input_spec in ordered_input_specs(object_info, class_type):
            if not is_widget_spec(input_spec):
                continue
            if input_name in inputs:
                if input_name in linked_widget_inputs and widget_index < len(widget_values):
                    widget_index += 1
                continue
            if widget_index >= len(widget_values):
                continue
            inputs[input_name] = coerce_widget_value(widget_values[widget_index], input_spec)
            widget_index += 1
            if input_name == "seed" and widget_index < len(widget_values) and is_seed_control_value(widget_values[widget_index]):
                widget_index += 1

        prompt[str(node["id"])] = {
            "class_type": class_type,
            "inputs": inputs,
            "_meta": {"title": node_title(node) or class_type},
        }
    return prompt


def patch_ui_workflow(
    workflow: dict[str, Any],
    image_name: str,
    filename_prefix: str,
    file_format: str,
    target_faces: int | None,
    high_poly_faces: int | None,
    texture_size: int | None,
) -> None:
    first_string_node: dict[str, Any] | None = None
    for node in workflow.get("nodes", []):
        class_type = node.get("type", "")
        widgets = node.setdefault("widgets_values", [])
        title = node_title(node).lower()

        if class_type in LOAD_IMAGE_CLASSES or class_type.endswith("LoadImageWithTransparency"):
            if widgets:
                widgets[0] = image_name

        if class_type == "Trellis2ExportMesh":
            if len(widgets) >= 1:
                widgets[0] = filename_prefix
            if len(widgets) >= 2:
                widgets[1] = file_format

        if class_type == "PrimitiveString":
            if first_string_node is None:
                first_string_node = node
            if "name" in title or "prefix" in title or "filename" in title:
                if widgets:
                    widgets[0] = filename_prefix

        if class_type == "PrimitiveInt" and widgets:
            if texture_size is not None and "texture" in title:
                widgets[0] = int(texture_size)
            elif high_poly_faces is not None and "high poly" in title and "face" in title:
                widgets[0] = int(high_poly_faces)
            elif target_faces is not None and ("low poly" in title or "face" in title or "target" in title):
                widgets[0] = int(target_faces)

        if target_faces is not None and class_type == "Trellis2SimplifyMesh":
            if widgets:
                widgets[0] = int(target_faces)

    if first_string_node is not None:
        widgets = first_string_node.setdefault("widgets_values", [])
        if widgets:
            widgets[0] = filename_prefix


def patch_api_prompt(
    prompt: dict[str, Any],
    image_name: str,
    filename_prefix: str,
    file_format: str,
    seed: int | None,
    target_faces: int | None,
    high_poly_faces: int | None,
    texture_size: int | None,
    sparse_structure_steps: int | None,
    shape_steps: int | None,
    texture_steps: int | None,
    max_views: int | None,
    sampler: str | None,
    use_reconviagen: bool,
    model_name: str | None,
    attention_backend: str | None,
) -> None:
    string_nodes: list[dict[str, Any]] = []
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        inputs = node.setdefault("inputs", {})
        title = node_title(node).lower()

        if class_type in LOAD_IMAGE_CLASSES or class_type.endswith("LoadImageWithTransparency"):
            if "image" in inputs or class_type == "LoadImage":
                inputs["image"] = image_name

        if class_type == "Trellis2ExportMesh":
            if not isinstance(inputs.get("filename_prefix"), list):
                inputs["filename_prefix"] = filename_prefix
            inputs["file_format"] = file_format

        if class_type == "PrimitiveString":
            string_nodes.append(node)
            if "name" in title or "prefix" in title or "filename" in title:
                inputs["value"] = filename_prefix

        if target_faces is not None:
            for key in ("target_face_num", "target_faces", "face_count", "max_faces", "faces"):
                if key in inputs:
                    inputs[key] = int(target_faces)
            if class_type == "PrimitiveInt":
                if high_poly_faces is not None and "high poly" in title and "face" in title:
                    inputs["value"] = int(high_poly_faces)
                elif "low poly" in title or "face" in title or "target" in title:
                    inputs["value"] = int(target_faces)

        if texture_size is not None:
            for key in ("texture_size", "texture_resolution", "atlas_size"):
                if key in inputs:
                    inputs[key] = int(texture_size)
            if class_type == "PrimitiveInt" and "texture" in title:
                inputs["value"] = int(texture_size)

        generation_overrides = {
            "sparse_structure_steps": sparse_structure_steps,
            "shape_steps": shape_steps,
            "texture_steps": texture_steps,
            "max_views": max_views,
        }
        for key, value in generation_overrides.items():
            if value is not None and key in inputs:
                inputs[key] = int(value)
        if sampler and "sampler" in inputs:
            inputs["sampler"] = sampler

        for key in list(inputs.keys()):
            key_lower = key.lower()
            if key_lower in {"simplify", "simplify_mesh", "enable_simplify"}:
                inputs[key] = True
            if key_lower in {"texture_size", "texture_resolution", "atlas_size"} and isinstance(inputs[key], int):
                inputs[key] = min(int(inputs[key]), int(texture_size or 1024))

        if class_type == "Trellis2LoadModel":
            if model_name:
                inputs["modelname"] = model_name
            if attention_backend:
                inputs["backend"] = attention_backend
            if "use_reconviagen" in inputs:
                inputs["use_reconviagen"] = bool(use_reconviagen)

        if seed is not None:
            for key in list(inputs.keys()):
                if "seed" in key.lower() and not isinstance(inputs[key], list):
                    inputs[key] = int(seed)

        prompt[node_id] = node

    if string_nodes:
        string_nodes[0].setdefault("inputs", {})["value"] = filename_prefix


def queue_prompt(server: str, prompt: dict[str, Any], client_id: str) -> str:
    response = http_json(server, "/prompt", {"prompt": prompt, "client_id": client_id}, timeout=120)
    prompt_id = response.get("prompt_id")
    if not prompt_id:
        raise ComfyError(f"ComfyUI did not return prompt_id. Response: {response}")
    return prompt_id


def wait_for_prompt(server: str, prompt_id: str, poll_seconds: float, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    while True:
        history = http_json(server, f"/history/{prompt_id}", timeout=60)
        if isinstance(history, dict) and prompt_id in history:
            item = history[prompt_id]
            status = item.get("status", {})
            if status.get("completed"):
                return item
            if status.get("status_str") == "error":
                raise ComfyError(f"ComfyUI failed prompt {prompt_id}: {json.dumps(status, ensure_ascii=False)}")
        if time.time() - started > timeout_seconds:
            raise ComfyError(f"Timed out waiting for prompt {prompt_id} after {timeout_seconds}s")
        time.sleep(poll_seconds)


def walk_outputs(value: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def rec(item: Any) -> None:
        if isinstance(item, dict):
            if "filename" in item:
                found.append(
                    {
                        "filename": str(item.get("filename", "")),
                        "subfolder": str(item.get("subfolder", "")),
                        "type": str(item.get("type", "output")),
                    }
                )
            for val in item.values():
                rec(val)
        elif isinstance(item, list):
            for val in item:
                rec(val)
        elif isinstance(item, str) and item.lower().endswith(MESH_EXTENSIONS):
            found.append({"path": item})

    rec(value)
    return found


def download_history_files(server: str, files: list[dict[str, str]], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    seen: set[tuple[str, str, str]] = set()
    for item in files:
        if "filename" not in item:
            continue
        key = (item.get("filename", ""), item.get("subfolder", ""), item.get("type", "output"))
        if key in seen:
            continue
        seen.add(key)
        query = parse.urlencode({"filename": key[0], "subfolder": key[1], "type": key[2]})
        url = server + "/view?" + query
        out_path = output_dir / key[0]
        if key[1]:
            out_path = output_dir / Path(key[1]) / key[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = request.Request(url, headers=HTTP_HEADERS)
            with request.urlopen(req, timeout=180) as response:
                out_path.write_bytes(response.read())
            downloaded.append(out_path)
        except Exception:
            # Some custom output strings are not served by /view. Keep going;
            # local output-dir copying may still find the generated mesh.
            continue
    return downloaded


def copy_prefixed_outputs(comfy_output_dir: Path, filename_prefix: str, output_dir: Path, started_at: float) -> list[Path]:
    prefix_path = Path(filename_prefix.replace("/", os.sep))
    search_dir = comfy_output_dir / prefix_path.parent
    stem = prefix_path.name
    if not search_dir.exists():
        return []
    copied: list[Path] = []
    for path in search_dir.glob(stem + "_*"):
        if path.suffix.lower() not in MESH_EXTENSIONS:
            continue
        if path.stat().st_mtime + 2 < started_at:
            continue
        rel = path.relative_to(comfy_output_dir)
        dest = output_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        copied.append(dest)
    return copied


def target_mesh_paths(paths: list[Path], file_format: str) -> list[Path]:
    target_suffix = "." + file_format.lower().lstrip(".")
    if target_suffix not in EXPORT_MESH_EXTENSIONS:
        return []
    return [path for path in paths if path.suffix.lower() == target_suffix]


def non_empty_existing(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        try:
            if path.is_file() and path.stat().st_size > 0:
                found.append(path)
        except OSError:
            continue
    return found


def empty_existing(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        try:
            if path.is_file() and path.stat().st_size <= 0:
                found.append(path)
        except OSError:
            continue
    return found


def raw_target_refs(raw_files: list[dict[str, str]], file_format: str) -> list[dict[str, str]]:
    target_suffix = "." + file_format.lower().lstrip(".")
    refs: list[dict[str, str]] = []
    for item in raw_files:
        filename = str(item.get("filename") or item.get("path") or "")
        if filename.lower().endswith(target_suffix):
            refs.append(item)
    return refs


def classify_output_status(
    raw_files: list[dict[str, str]],
    downloaded: list[Path],
    copied: list[Path],
    file_format: str,
    comfy_output_dir: Path | None,
) -> dict[str, Any]:
    downloaded_targets = target_mesh_paths(downloaded, file_format)
    copied_targets = target_mesh_paths(copied, file_format)
    usable_downloaded = non_empty_existing(downloaded_targets)
    usable_copied = non_empty_existing(copied_targets)
    usable_meshes = usable_downloaded + [path for path in usable_copied if path not in usable_downloaded]
    output_sources: list[str] = []
    if usable_downloaded:
        output_sources.append("history_download")
    if usable_copied:
        output_sources.append("comfy_output_copy")

    problems: list[str] = []
    target_refs = raw_target_refs(raw_files, file_format)
    if not raw_files:
        problems.append("history_without_files")
    elif not target_refs and not downloaded_targets and not copied_targets:
        problems.append("output_missing")

    if empty_existing(downloaded_targets):
        problems.append("download_empty")
    if empty_existing(copied_targets):
        problems.append("empty_mesh_file")
    if target_refs and not downloaded_targets and not copied_targets:
        problems.append("missing_local_output")
    if target_refs and comfy_output_dir is None and not usable_meshes:
        problems.append("missing_comfy_output_dir")

    status = "generated" if usable_meshes else "failed"
    return {
        "status": status,
        "output_source": output_sources,
        "output_problem": sorted(set(problems)),
        "generated_meshes": [str(path) for path in usable_meshes],
        "downloaded_target_meshes": [str(path) for path in downloaded_targets],
        "copied_target_meshes": [str(path) for path in copied_targets],
    }


def infer_comfy_output_dir(system_stats: Any) -> Path | None:
    if not isinstance(system_stats, dict):
        return None
    system = system_stats.get("system")
    if not isinstance(system, dict):
        return None
    argv = system.get("argv")
    if isinstance(argv, list):
        for index, value in enumerate(argv):
            text = str(value)
            if text == "--output-directory" and index + 1 < len(argv):
                candidate = Path(str(argv[index + 1])).expanduser()
                return candidate if candidate.exists() else None
            if text.startswith("--output-directory="):
                candidate = Path(text.split("=", 1)[1]).expanduser()
                return candidate if candidate.exists() else None
    return None


def discover_inputs(input_dir: Path, pattern: str, recursive: bool) -> list[Path]:
    iterator = input_dir.rglob(pattern) if recursive else input_dir.glob(pattern)
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})


def select_input_group(inputs: list[Path], group_size: int, group_index: int, limit: int | None) -> tuple[list[Path], int, int]:
    if group_size <= 0:
        selected = inputs
        start = 0
    else:
        start = (group_index - 1) * group_size
        selected = inputs[start : start + group_size]
    if limit:
        selected = selected[:limit]
    return selected, start, start + len(selected)


def ensure_workflow(args: argparse.Namespace) -> Path:
    if args.workflow:
        return Path(args.workflow).resolve()

    key = args.official_workflow
    workflow_info = OFFICIAL_WORKFLOWS[key]
    workflow_dir = Path(args.workflow_dir).resolve()
    local_path = workflow_dir / workflow_info["filename"]
    if args.dry_run:
        return local_path
    workflow_dir.mkdir(parents=True, exist_ok=True)
    if not local_path.exists() or args.refresh_workflow:
        url = workflow_info["url"]
        if not url:
            raise ComfyError(f"Bundled workflow is missing and cannot be downloaded: {local_path}")
        print(f"Downloading official TRELLIS2 workflow: {key}")
        download_url(url, local_path)
    return local_path


def build_prompt_for_asset(
    args: argparse.Namespace,
    base_workflow: dict[str, Any],
    object_info: dict[str, Any] | None,
    image_name: str,
    asset_name: str,
    seed: int | None,
) -> tuple[dict[str, Any], str]:
    workflow = copy.deepcopy(base_workflow)
    filename_prefix = posixpath.join(args.prefix.strip("/"), asset_name) if args.prefix else asset_name

    if is_ui_workflow(workflow):
        if object_info is None:
            raise ComfyError("A UI workflow needs a running ComfyUI server so /object_info can convert it to API format.")
        patch_ui_workflow(
            workflow,
            image_name,
            filename_prefix,
            args.file_format,
            args.target_faces,
            args.high_poly_faces,
            args.texture_size,
        )
        prompt = convert_ui_workflow_to_api(workflow, object_info)
    else:
        prompt = strip_ignored_api_nodes(workflow)

    patch_api_prompt(
        prompt,
        image_name,
        filename_prefix,
        args.file_format,
        seed,
        args.target_faces,
        args.high_poly_faces,
        args.texture_size,
        args.sparse_structure_steps,
        args.shape_steps,
        args.texture_steps,
        args.max_views,
        args.sampler,
        args.use_reconviagen,
        args.model_name,
        args.attention_backend,
    )
    return prompt, filename_prefix


def run_batch(args: argparse.Namespace) -> int:
    server = normalize_server(args.server)
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    inputs = discover_inputs(input_dir, args.pattern, args.recursive)
    workflow_path = ensure_workflow(args)
    selected_inputs, group_start, group_end = select_input_group(inputs, args.group_size, args.group_index, args.limit)

    if args.use_reconviagen is None:
        args.use_reconviagen = (
            args.official_workflow == "mesh-only-hq"
            and not args.workflow
            and args.model_name != "visualbruno/TRELLIS.2-4B-FP8"
        )
    if args.model_name == "visualbruno/TRELLIS.2-4B-FP8" and args.use_reconviagen:
        raise ComfyError("visualbruno/TRELLIS.2-4B-FP8 is not compatible with --use-reconviagen.")

    if not inputs:
        raise ComfyError(f"No input images found in {input_dir} with pattern {args.pattern}")
    if not selected_inputs:
        raise ComfyError(
            f"No images selected for group {args.group_index} "
            f"(group_size={args.group_size}, total_inputs={len(inputs)})"
        )

    print(f"ComfyUI server: {server}")
    print(f"Workflow: {workflow_path}")
    print(f"Input images: {len(inputs)} from {input_dir}")
    print(f"Selected group: {args.group_index} ({group_start + 1}-{group_end} of {len(inputs)}, group_size={args.group_size})")
    print(f"Output dir: {output_dir}")
    print(f"Seed: {args.seed} ({'incremented per asset' if args.increment_seed else 'fixed'})")
    print(
        "Generation controls: "
        f"sparse_steps={args.sparse_structure_steps}, "
        f"shape_steps={args.shape_steps}, "
        f"texture_steps={args.texture_steps}, "
        f"max_views={args.max_views}, "
        f"sampler={args.sampler}, "
        f"target_faces={args.target_faces}, "
        f"texture_size={args.texture_size}"
    )
    if args.use_reconviagen:
        print("ReconViaGen: enabled")
    if args.model_name:
        print(f"Model override: {args.model_name}")
    if args.attention_backend:
        print(f"Attention backend override: {args.attention_backend}")

    if args.dry_run:
        for path in selected_inputs:
            print(f"DRY {path.name} -> {args.prefix}/{safe_name(path.stem)}.{args.file_format}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    base_workflow = load_workflow(workflow_path)

    system_stats = http_json(server, "/system_stats", timeout=30)
    comfy_output_dir = Path(args.comfy_output_dir).resolve() if args.comfy_output_dir else infer_comfy_output_dir(system_stats)
    if comfy_output_dir:
        print(f"Comfy local output copy: {comfy_output_dir}")
    object_info = http_json(server, "/object_info", timeout=60) if is_ui_workflow(base_workflow) else None
    client_id = args.client_id or str(uuid.uuid4())
    manifest: list[dict[str, Any]] = []
    failed_assets: list[str] = []

    for local_index, image_path in enumerate(selected_inputs, start=1):
        index = group_start + local_index
        asset_name = safe_name(image_path.stem)

        seed = None if args.seed is None else int(args.seed)
        if seed is not None and args.increment_seed:
            seed += index - 1
        print(f"[group {args.group_index} {local_index}/{len(selected_inputs)} | asset {index}/{len(inputs)}] upload {image_path.name}")
        image_name = upload_image(server, image_path, args.upload_subfolder, overwrite=True)
        prompt, filename_prefix = build_prompt_for_asset(args, base_workflow, object_info, image_name, asset_name, seed)

        api_prompt_path = output_dir / "_api_prompts" / f"{asset_name}.json"
        api_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        api_prompt_path.write_text(json.dumps(prompt, indent=2, ensure_ascii=False), encoding="utf-8")

        started_at = time.time()
        prompt_id = queue_prompt(server, prompt, client_id)
        print(f"[group {args.group_index} {local_index}/{len(selected_inputs)}] queued {prompt_id} -> {filename_prefix}")
        history = wait_for_prompt(server, prompt_id, args.poll, args.timeout)

        raw_files = walk_outputs(history.get("outputs", history))
        downloaded = download_history_files(server, raw_files, output_dir) if args.download_outputs else []
        copied: list[Path] = []
        if comfy_output_dir:
            copied = copy_prefixed_outputs(comfy_output_dir, filename_prefix, output_dir, started_at)
        output_status = classify_output_status(raw_files, downloaded, copied, args.file_format, comfy_output_dir)

        job = {
            "source": str(image_path),
            "asset_name": asset_name,
            "prompt_id": prompt_id,
            "uploaded_image": image_name,
            "filename_prefix": filename_prefix,
            "seed": seed,
            "raw_outputs": raw_files,
            "downloaded": [str(path) for path in downloaded],
            "copied": [str(path) for path in copied],
            "status": output_status["status"],
            "output_source": output_status["output_source"],
            "output_problem": output_status["output_problem"],
            "generated_meshes": output_status["generated_meshes"],
            "downloaded_target_meshes": output_status["downloaded_target_meshes"],
            "copied_target_meshes": output_status["copied_target_meshes"],
        }
        manifest.append(job)
        (output_dir / f"{asset_name}.history.json").write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
        if output_status["status"] != "generated":
            failed_assets.append(asset_name)
            problems = ", ".join(output_status["output_problem"]) or "output_missing"
            print(
                f"[group {args.group_index} {local_index}/{len(selected_inputs)}] ERROR no non-empty .{args.file_format} output: {problems}",
                file=sys.stderr,
            )
        else:
            sources = ", ".join(output_status["output_source"]) or "unknown"
            print(
                f"[group {args.group_index} {local_index}/{len(selected_inputs)}] done, "
                f"mesh files: {len(output_status['generated_meshes'])}, source: {sources}"
            )

    manifest_path = output_dir / f"manifest_trellis2_batch_group_{args.group_index:02d}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    if failed_assets:
        print(f"ERROR: missing non-empty .{args.file_format} output for: {', '.join(failed_assets)}", file=sys.stderr)
        return 2
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-generate local 3D assets with ComfyUI + ComfyUI-Trellis2.",
    )
    parser.add_argument("--server", default="http://127.0.0.1:8188", help="ComfyUI server URL.")
    parser.add_argument("--input-dir", required=True, help="Directory containing PNG/JPG/WebP reference images.")
    parser.add_argument("--output-dir", required=True, help="Local directory for prompts, manifests and downloaded outputs.")
    parser.add_argument("--pattern", default="*.png", help="Input glob pattern.")
    parser.add_argument("--recursive", action="store_true", help="Scan input dir recursively.")
    parser.add_argument("--workflow", help="Path to an exported ComfyUI API workflow JSON, or a UI workflow JSON.")
    parser.add_argument("--workflow-dir", default=str(DEFAULT_WORKFLOW_DIR), help="Directory used for cached bundled workflows.")
    parser.add_argument(
        "--official-workflow",
        choices=sorted(OFFICIAL_WORKFLOWS),
        default="simple",
        help="Official ComfyUI-Trellis2 example workflow to download when --workflow is omitted.",
    )
    parser.add_argument("--refresh-workflow", action="store_true", help="Re-download the selected official workflow.")
    parser.add_argument("--prefix", default="trellis2_assets", help="ComfyUI output filename prefix/subfolder.")
    parser.add_argument("--file-format", default="glb", choices=["glb", "obj", "ply", "stl", "3mf", "dae"], help="Mesh export format.")
    parser.add_argument("--target-faces", type=int, default=18000, help="Final mobile-friendly target face count.")
    parser.add_argument("--high-poly-faces", type=int, default=120000, help="Intermediate high-poly cleanup face count for low-poly workflows.")
    parser.add_argument("--texture-size", type=int, default=1024, help="Texture atlas size for mobile-friendly GLB exports.")
    parser.add_argument("--seed", type=int, default=2146628683, help="Fixed seed used for deterministic generation.")
    parser.add_argument("--increment-seed", action="store_true", help="Increment --seed per selected asset. Off by default for stable texture continuity.")
    parser.add_argument("--sparse-structure-steps", type=int, default=18, help="Sparse structure steps. Balanced down to keep runtime stable.")
    parser.add_argument("--shape-steps", type=int, default=18, help="Shape generation steps.")
    parser.add_argument("--texture-steps", type=int, default=18, help="Texture generation steps. Balanced up for texture stability without increasing total steps.")
    parser.add_argument("--max-views", type=int, default=4, help="Maximum generated views. Keep at 4 for mobile-friendly runtime.")
    parser.add_argument("--sampler", default="euler", help="Sampler override for workflows exposing a sampler input.")
    parser.add_argument(
        "--model-name",
        choices=["microsoft/TRELLIS.2-4B", "visualbruno/TRELLIS.2-4B-FP8", "TencentARC/Pixal3D-T"],
        help="Override the Trellis2LoadModel modelname from the workflow.",
    )
    parser.add_argument(
        "--attention-backend",
        choices=["flash_attn", "xformers", "sdpa", "flash_attn_3", "flash_attn_4"],
        help="Override the Trellis2LoadModel full-attention backend from the workflow.",
    )
    parser.add_argument(
        "--use-reconviagen",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable Trellis2LoadModel use_reconviagen when the local model only has reconviagen_pipeline.json. Defaults on for mesh-only-hq.",
    )
    parser.add_argument("--upload-subfolder", default="trellis2_asset_inputs", help="ComfyUI input subfolder for uploaded images.")
    parser.add_argument("--poll", type=float, default=5.0, help="Polling delay while waiting for each prompt.")
    parser.add_argument("--timeout", type=int, default=7200, help="Timeout per asset in seconds.")
    parser.add_argument("--group-size", type=int, default=10, help="Number of images to process per group. Use 0 for all images.")
    parser.add_argument("--group-index", type=int, default=1, help="1-based group index to process.")
    parser.add_argument("--limit", type=int, help="Optional cap applied after group selection.")
    parser.add_argument("--client-id", help="Optional fixed ComfyUI client id.")
    parser.add_argument("--download-outputs", action=argparse.BooleanOptionalAction, default=True, help="Try to download outputs exposed in /history via /view.")
    parser.add_argument(
        "--comfy-output-dir",
        help="Optional local/mounted ComfyUI output directory. Useful when custom mesh outputs are not downloadable via /view.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List jobs without contacting ComfyUI.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        return run_batch(args)
    except ComfyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
