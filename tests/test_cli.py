from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from promptstyler_next.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_and_version(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == "0.3.0"


def test_cli_discovery_and_profiles(capsys):
    assert main(["styles", "--query", "noir", "--limit", "1"]) == 0
    styles = json.loads(capsys.readouterr().out)
    assert styles and "noir" in styles[0]["name"].lower()
    assert main(["profiles"]) == 0
    assert any(profile["id"] == "fibo" for profile in json.loads(capsys.readouterr().out))
    assert main(["recommend", "monochrome ink", "--limit", "2"]) == 0
    assert len(json.loads(capsys.readouterr().out)) <= 2


def test_cli_compose_file_and_typed_error(tmp_path, capsys):
    path = tmp_path / "recipe.json"
    path.write_text('{"prompt":"A moth","model":"anima"}')
    assert main(["compose", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["positive"] == "A moth"
    path.write_text('{"prompt":"A moth","schema_version":2}')
    assert main(["compose", str(path)]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "unsupported_schema"
    assert main(["compose", str(tmp_path / "missing.json")]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "io_error"


def test_module_cli_reads_stdin():
    completed = subprocess.run(
        [sys.executable, "-m", "promptstyler_next", "compose"],
        input='{"prompt":"Sea cliffs"}',
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout)["positive"] == "Sea cliffs"


def test_cli_validates_builtin_and_custom_packs(tmp_path, capsys):
    from conftest import make_pack

    builtin = next((ROOT / "promptstyler_next" / "packs").glob("*.json"))
    assert main(["validate", str(builtin)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["styles"] > 0
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(make_pack()))
    assert main(["validate", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == "test.pack"
    assert main(["--pack", str(path), "styles", "--query", "botanical"]) == 0
    assert any(style["id"] == "test.ink" for style in json.loads(capsys.readouterr().out))


def test_cli_rejects_invalid_service_configuration_without_traceback(capsys):
    assert main(["serve", "--port", "-1"]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["path"] == "port"
    assert main(["serve", "--host", "0.0.0.0"]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_host"
