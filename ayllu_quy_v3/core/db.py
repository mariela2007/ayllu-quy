# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Ayllu · capa de datos con degradación automática.

Si ``SUPABASE_URL`` y ``SUPABASE_KEY`` están presentes y el paquete
``supabase`` es importable, se usa Supabase (Postgres). En cualquier otro
caso se cae a ``MemoryStore``, un almacén en memoria thread-safe sembrado
desde ``core/seed.py``, de modo que la SPA arranque completa para el pitch.
"""

from __future__ import annotations

import copy
import itertools
import logging
import os
import threading
from typing import Any, Dict, Iterable, List, Optional

from . import seed as _seed

logger = logging.getLogger("ayllu.db")

TABLES = (
    "languages",
    "communities",
    "students",
    "glossary",
    "materials",
    "feedback",
    "events",
    "users",
    "messages",
    "threads",
)


def _seed_rows() -> Dict[str, List[dict]]:
    return {
        "languages": copy.deepcopy(_seed.LANGUAGES),
        "communities": copy.deepcopy(_seed.COMMUNITIES),
        "students": copy.deepcopy(_seed.STUDENTS),
        "glossary": copy.deepcopy(_seed.GLOSSARY),
        "materials": copy.deepcopy(_seed.MATERIALS),
        "feedback": [
            dict(row, createdAt=_seed.now_iso()) for row in copy.deepcopy(_seed.FEEDBACK)
        ],
        "events": [
            dict(row, id=None) for row in copy.deepcopy(_seed.EVENTS)
        ],
        # v3 · dos roles y aula bilingüe
        "users": copy.deepcopy(_seed.USERS),
        "messages": _seed.build_messages(),
        # v5 · mensajería: conversaciones (los mensajes van enlazados por threadId)
        "threads": _seed.build_threads(),
    }


class MemoryStore:
    """Almacén en memoria con la misma interfaz que ``SupabaseStore``."""

    mode = "memory"

    def __init__(self, seed: bool = True) -> None:
        self._lock = threading.RLock()
        self._data: Dict[str, List[dict]] = {t: [] for t in TABLES}
        self._seq: Dict[str, itertools.count] = {t: itertools.count(1) for t in TABLES}
        if seed:
            self.reset()

    # -- utilidades internas -------------------------------------------------
    @staticmethod
    def _check(table: str) -> None:
        if table not in TABLES:
            raise KeyError("tabla desconocida: %s" % table)

    def reset(self) -> None:
        """Reinicia el almacén con la muhu embebida (ids 1..n)."""
        with self._lock:
            fresh = _seed_rows()
            self._data = {}
            self._seq = {}
            for table in TABLES:
                counter = itertools.count(1)
                clean = []
                for row in fresh.get(table, []):
                    row = {k: v for k, v in row.items() if k != "id"}
                    row["id"] = next(counter)
                    clean.append(row)
                self._data[table] = clean
                self._seq[table] = counter

    # -- lectura -------------------------------------------------------------
    def select(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        query: Optional[str] = None,
        fields: Optional[Iterable[str]] = None,
    ) -> List[dict]:
        self._check(table)
        with self._lock:
            rows = copy.deepcopy(self._data[table])
        if filters:
            for key, value in filters.items():
                rows = [r for r in rows if str(r.get(key)) == str(value)]
        if query:
            needle = query.strip().lower()
            if needle:
                rows = [
                    r
                    for r in rows
                    if needle in " ".join(str(v).lower() for v in r.values())
                ]
        if offset:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        if fields:
            keep = set(fields)
            rows = [{k: v for k, v in r.items() if k in keep} for r in rows]
        return rows

    def get(self, table: str, row_id: Any) -> Optional[dict]:
        found = self.select(table, {"id": row_id}, limit=1)
        return found[0] if found else None

    def count(self, table: str, filters: Optional[Dict[str, Any]] = None) -> int:
        return len(self.select(table, filters))

    # -- escritura -----------------------------------------------------------
    def insert(self, table: str, row: Dict[str, Any]) -> dict:
        self._check(table)
        with self._lock:
            new_row = copy.deepcopy(row)
            new_row.pop("id", None)
            new_row["id"] = next(self._seq[table])
            self._data[table].append(new_row)
            return copy.deepcopy(new_row)

    def update(self, table: str, row_id: Any, patch: Dict[str, Any]) -> Optional[dict]:
        self._check(table)
        with self._lock:
            for row in self._data[table]:
                if str(row.get("id")) == str(row_id):
                    for key, value in patch.items():
                        if key != "id":
                            row[key] = copy.deepcopy(value)
                    return copy.deepcopy(row)
        return None

    def delete(self, table: str, row_id: Any) -> bool:
        self._check(table)
        with self._lock:
            before = len(self._data[table])
            self._data[table] = [
                r for r in self._data[table] if str(r.get("id")) != str(row_id)
            ]
            return len(self._data[table]) < before

    # -- estado --------------------------------------------------------------
    def healthy(self) -> bool:
        return True

    def info(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "tables": {t: len(self._data[t]) for t in TABLES},
            }


class SupabaseStore:
    """Envoltura mínima sobre el cliente oficial de Supabase."""

    mode = "supabase"

    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client  # import perezoso: sólo si se usa

        self._client = create_client(url, key)
        if key.startswith("sb_secret_"):
            # API keys nuevas no son JWT: sólo deben viajar como `apikey`.
            # supabase-py conserva Authorization: Bearer <key> por compatibilidad.
            self._client.postgrest.headers.pop("authorization", None)
            self._client.postgrest.session.headers.pop("authorization", None)
        self._lock = threading.RLock()

    def _table(self, table: str):
        MemoryStore._check(table)
        return self._client.table(table)

    def select(self, table, filters=None, limit=None, offset=0, query=None, fields=None):
        builder = self._table(table).select("*")
        if filters:
            for key, value in filters.items():
                builder = builder.eq(key, value)
        if offset:
            builder = builder.range(offset, offset + (limit or 100) - 1)
        elif limit:
            builder = builder.limit(limit)
        rows = builder.execute().data or []
        if query:
            needle = query.strip().lower()
            rows = [
                r for r in rows if needle in " ".join(str(v).lower() for v in r.values())
            ]
        if fields:
            keep = set(fields)
            rows = [{key: value for key, value in row.items() if key in keep} for row in rows]
        return rows

    def get(self, table, row_id):
        rows = self.select(table, {"id": row_id}, limit=1)
        return rows[0] if rows else None

    def count(self, table, filters=None):
        return len(self.select(table, filters))

    def insert(self, table, row):
        payload = {k: v for k, v in row.items() if k != "id"}
        data = self._table(table).insert(payload).execute().data
        return (data or [payload])[0]

    def update(self, table, row_id, patch):
        payload = {k: v for k, v in patch.items() if k != "id"}
        data = self._table(table).update(payload).eq("id", row_id).execute().data
        return (data or [None])[0]

    def delete(self, table, row_id):
        self._table(table).delete().eq("id", row_id).execute()
        return True

    def healthy(self) -> bool:
        try:
            for table in TABLES:
                self._client.table(table).select("id").limit(1).execute()
            return True
        except Exception:
            return False

    def info(self) -> dict:
        return {"mode": self.mode, "tables": {}, "healthy": self.healthy()}


_STORE: Optional[Any] = None


def _build_store():
    url = os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
    )
    if url and key:
        try:
            store = SupabaseStore(url, key)
            if store.healthy():
                return store
        except Exception as error:
            logger.warning("Supabase no está listo; se usará la semilla en memoria: %s", error)
    return MemoryStore()


def get_store():
    """Devuelve el almacén activo (singleton por proceso)."""
    global _STORE
    if _STORE is None:
        _STORE = _build_store()
    return _STORE


def reset_store() -> None:
    """Fuerza la reconstrucción del almacén (usado por el self-test)."""
    global _STORE
    _STORE = None
