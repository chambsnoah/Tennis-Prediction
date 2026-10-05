"""Regression checks for the public installed-package import surface."""

import subprocess
import sys
from pathlib import Path


def test_public_imports_and_packaged_resources():
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_install.py"
    subprocess.run([sys.executable, str(script), "all"], check=True)


def test_runtime_models_do_not_import_optional_ml():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from tennis_api.models import PlayerStats; "
            "assert 'numpy' not in sys.modules; assert 'sklearn' not in sys.modules",
        ],
        check=True,
    )
