"""Load YAML configuration.

Reads config.yaml directly (no local_config copy) so edits always take effect immediately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PYTHON_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PYTHON_ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config dict from YAML. Defaults to python/config.yaml."""
    cfg_path = Path(path) if path else CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
