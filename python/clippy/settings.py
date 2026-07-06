"""Load and save YAML configuration.

Mirrors the sibling pigeon_detection project: `config.yaml` is the versioned template,
`local_config.yaml` is created from it on first run and is gitignored so users can tune
model/persona without touching the template.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

PYTHON_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PYTHON_ROOT / "local_config.yaml"
TEMPLATE_CONFIG_PATH = PYTHON_ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config dict from YAML. Defaults to python/local_config.yaml.

    If local_config.yaml does not exist, it is created from the template config.yaml.
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not path and not cfg_path.exists():
        if TEMPLATE_CONFIG_PATH.exists():
            try:
                with TEMPLATE_CONFIG_PATH.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                save_config(data, cfg_path)
            except Exception:
                cfg_path = TEMPLATE_CONFIG_PATH
        else:
            cfg_path = TEMPLATE_CONFIG_PATH

    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(data: dict[str, Any], path: str | Path | None = None) -> None:
    """Write config atomically to avoid partial files on crash."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=cfg_path.parent, suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, cfg_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
