"""Static checks for the paired Windows installer."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_HYDRA_PS1 = REPO_ROOT / "setup" / "install-hydra.ps1"


def test_install_hydra_preflight_process_cleanup_is_python_only():
    """Do not match the running PowerShell installer by script text alone."""
    text = INSTALL_HYDRA_PS1.read_text(encoding="utf-8")

    assert "$_.Name -like 'python*'" in text
    assert "$_.CommandLine -and" in text
    assert "$_.CommandLine -match '-m\\s+worker(\\.|$)'" in text
    assert "$_.CommandLine -match 'python.*-m\\s+worker'" not in text
