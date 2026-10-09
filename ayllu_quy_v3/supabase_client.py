# Ayllu · quy_Latn · núcleo v3 · aula bilingüe con dos roles · ver CAMBIOS_V3_0.txt
"""Stub retrocompatible: en v2 el acceso a datos vive en ``core/db.py``."""

from core.db import SupabaseStore, get_store  # noqa: F401

__all__ = ["SupabaseStore", "get_store"]
