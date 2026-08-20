"""Make `tools/explainer` importable without installing it as a package.

The explainer is a standalone stdlib-only script, deliberately outside the uv
workspace, so there is no distribution to install and no `-e .` to lean on.
"""

import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))
