"""
Shared test fixtures. The chatbot_backend package uses bare imports
(`from config import …`, `from services import …`) which need the package
root on sys.path.
"""
import sys
from pathlib import Path

# Insert chatbot_backend root one level up from this file so bare imports work
# whether pytest is invoked from the repo root or from chatbot_backend/.
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
