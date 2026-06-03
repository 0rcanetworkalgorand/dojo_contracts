"""Root conftest.py - Ensures project root is on sys.path for imports."""
import sys
from pathlib import Path

# Add project root to sys.path so `from projects.smart_contracts...` resolves
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
