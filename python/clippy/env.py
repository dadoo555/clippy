"""Load environment variables from a .env file, for both dev and prod.

Reads `python/.env` (gitignored) so the API key never has to be set by hand in the shell.
Real environment variables always win (override=False), so prod/systemd/App Lab can override
the file. python-dotenv is optional: if it is not installed, real env vars still work.
"""

from __future__ import annotations

from .settings import PYTHON_ROOT

_loaded = False


def load_env() -> None:
    """Populate os.environ from python/.env once. Idempotent; safe to call from anywhere."""
    global _loaded
    if _loaded:
        return
    _loaded = True

    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # python-dotenv not installed; rely on real environment variables

    # override=False: a real env var (e.g. set by systemd in prod) takes precedence over the file.
    load_dotenv(dotenv_path=PYTHON_ROOT / ".env", override=False)
