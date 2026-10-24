"""Benchmark an existing local MiniCPM deployment; no download or server startup."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfyui-root", required=True, type=Path)
    parser.add_argument("--model-name", default="minicpm-v4.7-1b-heretic-int8-convrot.safetensors")
    parser.add_argument("--image", type=Path, help="Optional reference; otherwise use two synthetic shapes")
    parser.add_argument("--detail-mode", choices=("expanded", "faithful"), default="expanded")
    parser.add_argument("--repeats", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--output", type=Path, help="Optional JSON evidence file")
    args = parser.parse_args()
    sys.path.insert(0, str(args.comfyui_root.resolve()))
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "psnext_benchmark", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    assert spec is not None and spec.loader is not None
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    runtime = importlib.import_module("psnext_benchmark.comfyui.upscaler.runtime")
    import torch
    from PIL import Image, ImageDraw

    if args.image:
        with Image.open(args.image) as opened:
            picture = opened.convert("RGB")
    else:
        picture = Image.new("RGB", (512, 384), "white")
        draw = ImageDraw.Draw(picture)
        draw.rectangle((100, 100, 250, 230), fill="red")
        draw.ellipse((300, 140, 420, 260), fill="blue")
    pixels = torch.frombuffer(bytearray(picture.tobytes()), dtype=torch.uint8)
    image = pixels.reshape(1, picture.height, picture.width, 3).float() / 255
    handle = runtime.load_upscaler(args.model_name)
    records = []
    try:
        for iteration in range(args.repeats):
            for prompt, reference in (
                ("two foxes sharing a yellow umbrella", None),
                ("", image),
                (
                    "Replace the red rectangle with a green triangle."
                    if not args.image
                    else "Describe the main subject and preserve its visible attributes.",
                    image,
                ),
            ):
                _, inspection = runtime.upscale(handle, prompt, reference, detail_mode=args.detail_mode)
                record = {"iteration": iteration, **json.loads(inspection)}
                records.append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
    finally:
        runtime.mm.unload_model_and_clones(handle.owner)
    if args.output:
        args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
