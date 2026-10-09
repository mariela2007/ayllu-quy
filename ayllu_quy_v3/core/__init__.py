# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Paquete core de Ayllu: datos, autenticación, servicios y muhu."""

from __future__ import annotations

import os
from pathlib import Path


def _load_local_env() -> None:
    """Load simple KEY=VALUE settings without overriding the process env."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_local_env()

__all__ = ["db", "auth", "services", "seed"]
__version__ = "3.0.0"
