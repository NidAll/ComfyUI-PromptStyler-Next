"""Model discovery does not import Torch, Transformers, or model management."""

from __future__ import annotations

import json
from pathlib import Path

import folder_paths

MODEL_KIND = "anima_prompt_architect"
DEFAULT_MODEL = "minicpm-v4.7-1b-heretic-int8-convrot.safetensors"


def _roots() -> list[Path]:
    folder_paths.add_model_folder_path(MODEL_KIND, str(Path(folder_paths.models_dir) / MODEL_KIND))
    folder_paths.folder_names_and_paths[MODEL_KIND][1].add(".safetensors")
    return [Path(root).resolve() for root in folder_paths.get_folder_paths(MODEL_KIND)]


def resolve_bundle(name: str) -> Path:
    if (
        not isinstance(name, str)
        or not name
        or ".." in Path(name).parts
        or Path(name).is_absolute()
        or "\\" in name
        or Path(name).suffix != ".safetensors"
    ):
        raise ValueError("Select a safetensors file inside models/anima_prompt_architect")
    for root in _roots():
        path = (root / name).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    raise FileNotFoundError(f"Install {name} in models/anima_prompt_architect, then refresh the model list")


def model_choices() -> list[str]:
    from safetensors import SafetensorError, safe_open

    _roots()
    choices = []
    for name in folder_paths.get_filename_list(MODEL_KIND):
        try:
            with safe_open(resolve_bundle(name), framework="pt") as reader:
                manifest = json.loads((reader.metadata() or {}).get("anima_prompt_architect", "{}"))
                if (
                    isinstance(manifest, dict)
                    and manifest.get("kind") == "minicpm"
                    and manifest.get("version") == 1
                ):
                    choices.append(name)
        except (ValueError, OSError, SafetensorError):
            continue
    # Keep the node visible before installation, with an actionable execute-time error.
    return choices or [DEFAULT_MODEL]


def bundle_fingerprint(name: str) -> tuple:
    path = resolve_bundle(name)
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns, stat.st_ino
