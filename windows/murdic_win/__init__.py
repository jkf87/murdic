"""murdic for Windows: hold a key, speak Korean, get cleaned text at the cursor."""
import sys
from pathlib import Path

__version__ = "0.3.1"

# The shared cleanup rules live in the repository's `dictate` package. A frozen
# build bundles it; a source checkout imports it from the repository root.
if not getattr(sys, "frozen", False):
    _root = str(Path(__file__).resolve().parents[2])
    if _root not in sys.path:
        sys.path.append(_root)
