"""Application environment loading without mutating system-level configuration."""

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def load_backend_env(path: Path | None = None) -> None:
    """Load backend/.env values that are not already present in the process."""
    env_path = path or BACKEND_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def is_development_environment() -> bool:
    """Return whether development-only diagnostic endpoints may be registered."""
    return os.getenv("APP_ENV", "development").strip().lower() in {
        "dev",
        "development",
        "local",
        "test",
    }
