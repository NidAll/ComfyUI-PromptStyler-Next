# Development and release

## Environments

The engine supports Python 3.11–3.14 and has no runtime dependencies. Create an
isolated development environment and install the optional tools:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest --ignore=tests/test_comfy.py
python -m coverage run -m pytest --ignore=tests/test_comfy.py
python -m coverage report --fail-under=85
ruff check .
ruff format --check .
mypy
node --test studio/tests/*.test.mjs
```

HTTP and Node tests need permission to open IPv4 loopback sockets. A restricted
sandbox may deny sockets; that is an environment restriction, not a passing test.
Use an approved local execution context rather than skipping the HTTP tests.

Run actual host tests with an existing ComfyUI environment and source checkout:

```sh
PYTHONPATH=/path/to/ComfyUI /path/to/ComfyUI/venv/bin/python -m pytest tests/test_comfy.py
```

These use real V3 schema registration and native text previews. Encoder delegation
uses a clearly named test double. No test downloads weights, starts the ComfyUI
server, runs a sampler, or proves image-generation equivalence.

## Quality gates

CI has standalone Python 3.11, 3.12, 3.13 and 3.14 jobs; a Node transport job with a
real Python sidecar; and a pinned ComfyUI CPU host-contract job. It also checks
strict typing, lint/format, schema reproducibility, archive contents and an isolated
installed-wheel smoke test. Runtime coverage must be at least 85%, including
branches. Hosted checks are only verified after a repository push and completed
runs; a workflow file is not itself evidence of hosted success.

The property suite generates Unicode prompts, intensities and protected-axis sets.
Regression tests cover numeric JSON edge cases and partially suppressed negative
clauses. Library tests check identities, schema, claim/variant integrity, unique
visual directions, profile eligibility and deterministic composition. API tests
use real HTTP. UI acceptance includes keyboard/narrow layout and browser actions.

## Update contracts

Edit schema generation in `scripts/write_schemas.py`, regenerate, then verify the
runtime validators against matching valid/invalid fixtures. Schema changes that
break existing version-1 recipes require a new protocol version. Stable published
style IDs and node IDs must not change meaning without a documented release.
Increase pack versions for authored content changes, and adapter/engine revisions
for behavior changes. Keep golden expectations tied to concrete output behavior.

## Build and inspect

```sh
python -m build
python scripts/check_distribution.py dist
```

The inspector checks data/assets/licenses, rejects runtime dependency creep,
installs the wheel without dependencies into a temporary environment outside the
checkout, composes a recipe and writes `dist/SHA256SUMS`. The source archive includes
ComfyUI, Studio, examples, tests, schema tooling and documentation. The wheel is the
standalone engine/workbench distribution. Do not confuse the two installation paths.

Before publication: run all applicable checks on the final source, inspect the
wheel/sdist, verify portable docs and licenses, and retain private evidence outside
the public repository. A release needs tested installation, clear change notes and
honest acceptance limits. Model-specific image-quality review should use controlled
prompts and a documented workflow/seed grid; structural tests cannot replace it.

Version 0.1.0 is prepared locally. This task does not publish a remote repository,
tag, registry entry or package-index upload automatically.
