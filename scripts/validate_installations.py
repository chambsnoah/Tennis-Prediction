"""Check locked wheel installs and tests on every supported Python version."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def validate_installations(uv):
    root = Path(__file__).resolve().parents[1]
    subprocess.run([uv, "lock", "--check"], cwd=root, check=True)
    with tempfile.TemporaryDirectory(prefix="tennis-install-check-") as temporary:
        for version in ("3.11", "3.12", "3.13"):
            for feature in ("runtime", "ml", "excel", "web", "all"):
                environment = Path(temporary) / f"{version}-{feature}"
                options = ["--no-dev"]
                if feature == "all":
                    options = ["--all-extras", "--group", "dev"]
                elif feature != "runtime":
                    options += ["--extra", feature]
                print(f"Checking Python {version}: {feature}", flush=True)
                subprocess.run(
                    [uv, "sync", "--locked", "--no-editable", "--reinstall-package",
                     "tennis-prediction", "--quiet", "--python", version, *options],
                    cwd=root,
                    env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(environment)},
                    check=True,
                )
                python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                subprocess.run(
                    [str(python), "-I", str(root / "scripts/check_install.py"), feature, "--require-wheel"],
                    cwd=environment,
                    check=True,
                )
                if feature == "all":
                    print(f"Running checkout test suite on Python {version}", flush=True)
                    subprocess.run([str(python), "-m", "pytest", "-q"], cwd=root, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv", help="Path to the pinned uv executable")
    validate_installations(parser.parse_args().uv)
