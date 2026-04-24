"""Smoke test: third-party provider discoverable after isolated install.

Verifies PLUGIN-01, PLUGIN-02, PLUGIN-03:
- A minimal external package is installable in an isolated venv (PLUGIN-01)
- discover_providers() finds it via entry points without touching maestro source (PLUGIN-02)
- The test uses tmp_path and does not mutate the global Python environment (PLUGIN-03)

This test is marked 'integration' and is skipped by default.
Run with: MAESTRO_RUN_INTEGRATION=1 pytest tests/test_provider_install_smoke.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest


def _is_integration_enabled() -> bool:
    return os.environ.get("MAESTRO_RUN_INTEGRATION", "") == "1"


@pytest.mark.integration
@pytest.mark.skipif(
    not _is_integration_enabled(),
    reason="Set MAESTRO_RUN_INTEGRATION=1 to run isolated-install smoke tests",
)
def test_third_party_provider_discoverable_after_isolated_install(
    tmp_path: Path,
) -> None:
    """A third-party provider installed in an isolated venv is discoverable
    by maestro's registry without any source edits to the main package."""

    # 1. Create isolated venv
    venv_dir = tmp_path / "smoke_venv"
    venv.create(str(venv_dir), with_pip=True, clear=True)

    # Resolve venv pip and python executables (cross-platform)
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
        venv_pip = venv_dir / "Scripts" / "pip.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
        venv_pip = venv_dir / "bin" / "pip"

    repo_root = Path(__file__).parent.parent
    fixture_dir = repo_root / "tests" / "fixtures" / "hello_provider"

    # 2. Install maestro into the isolated venv
    result = subprocess.run(
        [str(venv_pip), "install", "--quiet", "-e", str(repo_root)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Failed to install maestro into venv:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # 3. Install hello_provider fixture into the same venv
    result = subprocess.run(
        [str(venv_pip), "install", "--quiet", "-e", str(fixture_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Failed to install hello_provider fixture:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # 4. Verify discovery via subprocess (fresh process = no lru_cache pollution)
    discovery_script = (
        "from maestro.providers.registry import discover_providers; "
        "p = discover_providers(); "
        "assert 'hello' in p, f'expected hello in {list(p.keys())}'; "
        "print('SMOKE_OK')"
    )
    result = subprocess.run(
        [str(venv_python), "-c", discovery_script],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # 5. Assert success
    assert result.returncode == 0, (
        f"discover_providers() subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "SMOKE_OK" in result.stdout, (
        f"Expected 'SMOKE_OK' in stdout, got:\n{result.stdout}"
    )
