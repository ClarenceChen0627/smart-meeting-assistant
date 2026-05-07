import os
import sys
from pathlib import Path


def pytest_configure(config):
    backend_dir = Path(__file__).resolve().parents[1]
    venv_python = backend_dir / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )

    if not venv_python.exists():
        raise RuntimeError(
            "Backend tests must use the backend virtual environment, but the "
            f"expected interpreter is missing: {venv_python}"
        )

    current_python = Path(sys.executable).resolve()
    expected_python = venv_python.resolve()

    if current_python != expected_python:
        raise RuntimeError(
            "Backend tests must run through backend/.venv.\n"
            f"Current interpreter: {current_python}\n"
            f"Expected interpreter: {expected_python}\n"
            "Use: cd backend && .\\.venv\\Scripts\\python.exe -m pytest"
        )
