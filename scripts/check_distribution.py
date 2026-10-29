"""Inspect archives and smoke-test a wheel installed outside the source checkout."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path


def main() -> int:
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Build one wheel and one source archive."
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        for required in (
            "promptstyler_next/profiles.json",
            "promptstyler_next/py.typed",
            "promptstyler_next/web/index.html",
            "promptstyler_next/schemas/pack.schema.json",
        ):
            assert required in names, required
        assert any(name.startswith("promptstyler_next/packs/") for name in names)
        source_root = Path(__file__).resolve().parents[1]
        expected_package_files = set()
        for source in (source_root / "promptstyler_next").rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            relative = source.relative_to(source_root).as_posix()
            expected_package_files.add(relative)
            assert relative in names, relative
            assert archive.read(relative) == source.read_bytes(), f"Wheel differs: {relative}"
        assert {
            name for name in names if name.startswith("promptstyler_next/") and not name.endswith("/")
        } == expected_package_files, "Wheel contains stale or unexpected package files"
        metadata = archive.read(next(name for name in names if name.endswith(".dist-info/METADATA"))).decode()
        assert not any(
            line.startswith("Requires-Dist:") and "extra ==" not in line for line in metadata.splitlines()
        ), "Unexpected runtime dependency"
    with tarfile.open(sources[0]) as archive:
        names = archive.getnames()
        for required in (
            "/__init__.py",
            "/comfyui/nodes.py",
            "/web/promptstyler.js",
            "/web/style-picker.mjs",
            "/studio/bridge.mjs",
            "/tests/test_engine.py",
            "/docs/architecture.md",
            "/STYLE-LICENSE",
            "/scripts/write_schemas.py",
        ):
            assert any(name.endswith(required) for name in names), required
        assert not any("/node_modules/" in name or "/.git/" in name for name in names)
        prefix = names[0].split("/", 1)[0]
        for source_directory in (
            "promptstyler_next",
            "comfyui",
            "web",
            "studio",
            "tests",
            "docs",
            "examples",
            "scripts",
            "custom_packs",
            "llm-prompts",
            ".github",
        ):
            for source in (source_root / source_directory).rglob("*"):
                if not source.is_file() or any(
                    part in {"__pycache__", "node_modules", ".pytest_cache"} for part in source.parts
                ):
                    continue
                relative = source.relative_to(source_root).as_posix()
                member = archive.extractfile(f"{prefix}/{relative}")
                assert member is not None, f"Missing from source archive: {relative}"
                assert member.read() == source.read_bytes(), f"Source archive differs: {relative}"
    with tempfile.TemporaryDirectory(prefix="promptstyler-wheel-") as temp:
        root = Path(temp)
        venv.create(root / "venv", with_pip=True)
        executable = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [str(executable), "-m", "pip", "install", "--no-deps", "--no-index", str(wheels[0])],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        code = """
import json, sys
from importlib.resources import files
from promptstyler_next import Engine
assert 'comfy_api' not in sys.modules
engine = Engine.builtin()
matches = engine.list_styles(query='noir')
assert matches
result = engine.compose({'prompt':'An orchard', 'model':'flux', 'styles':[{'id':matches[0]['id']}]})
assert result.positive.startswith('An orchard')
assert engine.compose(result.recipe).fingerprint == result.fingerprint
assert files('promptstyler_next').joinpath('web/index.html').read_text()
styles = []
offset = 0
while True:
    page = engine.list_styles(limit=1000, offset=offset)
    styles.extend(page)
    if len(page) < 1000:
        break
    offset += len(page)
pack_count = sum(1 for item in files('promptstyler_next').joinpath('packs').iterdir() if item.name.endswith('.json'))
print(json.dumps({'styles': len(styles), 'packs': pack_count, 'profiles':len(engine.profiles()), 'fingerprint':result.catalog_fingerprint}))
"""
        env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        subprocess.run([str(executable), "-I", "-c", code], cwd=root, env=env, check=True)
    sums = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in [*wheels, *sources]]
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
