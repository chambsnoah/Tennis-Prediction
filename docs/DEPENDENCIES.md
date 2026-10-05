# Dependency Management

## Supported Environment

Python 3.11, 3.12, and 3.13 are supported. Use uv 0.12.23, matching the
`required-version` in `pyproject.toml`. uv can install these interpreters itself.
Run every command below from the repository root.
The isolated build backend is pinned to setuptools 83.0.0 in `build-system`;
update that pin deliberately when upgrading build tooling.
On macOS, the ML extra also requires the native OpenMP runtime for XGBoost:
install it with `brew install libomp` before selecting `ml` or `--all-extras`.
Python dependency locks do not provision system libraries.

`pyproject.toml` declares the package, direct dependencies, optional feature
extras, and development tools. `uv.lock` is the single generated universal lock:
it records exact versions, interpreter/platform markers, and artifact hashes.
Do not edit it manually. The former nested requirements files and `deps` helpers
are retired, not alternate installation workflows.

## Installation

```bash
# API, simulation, and pool rules only
uv sync --locked --python 3.13 --no-dev

# Optional features (extras may be combined)
uv sync --locked --python 3.13 --no-dev --extra ml
uv sync --locked --python 3.13 --no-dev --extra excel
uv sync --locked --python 3.13 --no-dev --extra web

# Complete development environment
uv sync --locked --python 3.13 --all-extras --group dev
```

Runtime includes both requests (synchronous HTTP) and aiohttp (asynchronous HTTP),
plus date parsing support. `ml` supplies NumPy, pandas, joblib,
scikit-learn, and the boosted-tree implementations used by the existing modules.
`excel` supplies openpyxl for .xlsx/.xlsm workbooks; workbook adapters remain
future work. `web` supplies Flask. `dev` supplies test and build
tools and is not a runtime requirement.

Web wheels do not bundle tournament or participant data. Set `TENNIS_DATA_ROOT`
to an absolute directory containing the `2023/` and/or `2024/` tournament folders;
the server and its subprocess wrappers use the same root. For editable checkout
installs it defaults to the repository root. For example:

```bash
TENNIS_DATA_ROOT=/path/to/tournament-data uv run --locked --extra web python -m web_interface.server
```

`uv sync` reconciles `.venv` exactly, removing unselected extras. Always include
all desired extras when syncing. `--locked` fails if metadata and lock disagree,
rather than silently resolving new versions.

## Tests

```bash
uv run --locked --all-extras --group dev python -m pytest
```

This runs the project suite selected by `pytest.ini` and returns a failing exit
status for test failures. The old report script with an 80% pass threshold is
not the test gate. Do not require API credentials or download live tennis data
to run the suite. Persistent-state isolation and CI gates are tracked in #6.

## Updating The Lock

```bash
# After editing dependency declarations
uv lock
uv lock --check

# Deliberately upgrade a dependency, then review and test the diff
uv lock --upgrade-package requests
```

Commit `pyproject.toml` and `uv.lock` together. Unused development/server packages
are not retained merely because they appeared in an old requirements file.

## Clean-Environment Validation

Run the complete installation matrix and test suites with:

```bash
uv run --locked --all-extras --group dev python scripts/validate_installations.py
```

This creates fifteen temporary, non-editable wheel environments, checks their
imports in isolated mode from outside the checkout, verifies that project
modules originate inside the installed environment, and exercises the web data
routes and subprocesses using temporary synthetic fixtures. Separately, it runs
the checkout test suite on each supported interpreter; that suite is not an
installed-artifact test because legacy tests adjust import paths. Environments
are deleted afterward. Downloads and
builds may use uv's artifact cache; no existing site-packages are reused.
The project wheel is explicitly rebuilt so a cached local wheel cannot hide
source changes made without modifying package metadata.

For each supported interpreter, sync the runtime, each optional extra, and the
complete development installation into a fresh environment. Set
`UV_PROJECT_ENVIRONMENT` to an empty directory outside the working environment
to keep this check independent of previously installed packages. For example:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/tennis-runtime-311 uv sync --locked --python 3.11 --no-dev
UV_PROJECT_ENVIRONMENT=/tmp/tennis-runtime-311 uv run --locked --no-dev python -c "import tennis_api, tennis_pool.rules, tennis_preds.tennis"
UV_PROJECT_ENVIRONMENT=/tmp/tennis-full-311 uv sync --locked --python 3.11 --all-extras --group dev
UV_PROJECT_ENVIRONMENT=/tmp/tennis-full-311 uv run --locked --all-extras --group dev python -m pytest
```

Repeat with 3.12 and 3.13. The import smoke checks in
`scripts/check_install.py` can validate the selected feature without credentials,
model artifacts, a running server, or persistent cache writes:

```bash
uv run --locked --no-dev python scripts/check_install.py runtime
uv run --locked --no-dev --extra ml python scripts/check_install.py ml
uv run --locked --no-dev --extra excel python scripts/check_install.py excel
uv run --locked --no-dev --extra web python scripts/check_install.py web
```

The installed wheel must also be smoke-tested from outside the repository so
source-tree imports cannot conceal missing package files. `uv build` creates
the wheel and source distribution. These are installation checks, not evidence
that legacy ML predictions or the legacy web optimizer meet the roadmap's
future validation requirements.
