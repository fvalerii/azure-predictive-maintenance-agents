"""Make the challenge folders importable as plain modules for the test suite.

These folders aren't packages (no __init__.py) since they're meant to be run
directly as scripts (`python agents.py`), so tests add them to sys.path
explicitly instead of using package-relative imports.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for folder in ("challenge-1-build", "challenge-4-deploy"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)
