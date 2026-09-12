"""Execute the dependency-free frontend smoke test when Node is installed."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_frontend_smoke():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is only required for the optional frontend smoke test")
    script = Path(__file__).parents[1] / "frontend/smoke.cjs"
    subprocess.run([node, str(script)], check=True, timeout=10, capture_output=True)
