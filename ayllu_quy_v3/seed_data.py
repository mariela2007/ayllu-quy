# Ayllu · quy_Latn · núcleo v3 · aula bilingüe con dos roles · ver CAMBIOS_V3_0.txt
#!/usr/bin/env python3
"""Siembra Supabase con los datos demo de Ayllu.

    python seed_data.py --check     # muestra el estado sin qillqay
    python seed_data.py --write     # inserta la muhu en Supabase
    python seed_data.py --reset     # reinicia el almacén en memoria

Requiere SUPABASE_URL y SUPABASE_SECRET_KEY (o una clave legacy) para ``--write``.
"""

from __future__ import annotations

import argparse
import sys

from core.db import TABLES, SupabaseStore, get_store, reset_store
from core.services import get_service, reset_service


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Semilla de datos de Ayllu")
    parser.add_argument("--check", action="store_true", help="estado actual")
    parser.add_argument("--write", action="store_true", help="escribe en Supabase")
    parser.add_argument("--reset", action="store_true", help="reinicia el almacén")
    args = parser.parse_args(argv)

    if args.reset:
        reset_store()
        reset_service()
        get_service()
        print("Almacén reiniciado con la semilla embebida.")
        return 0

    store = get_store()
    if args.write:
        if not isinstance(store, SupabaseStore):
            print("Sin SUPABASE_URL/SUPABASE_KEY: uso el modo degradado en memoria.")
            return 1
        from core import seed

        seed_plan = [
            ("languages", seed.LANGUAGES),
            ("communities", seed.COMMUNITIES),
            ("students", seed.STUDENTS),
            ("glossary", seed.GLOSSARY),
            ("materials", seed.MATERIALS),
            ("feedback", seed.FEEDBACK),
            ("events", seed.EVENTS),
            (
                "users",
                [
                    {key: value for key, value in row.items() if key != "password"}
                    for row in seed.USERS
                ],
            ),
            ("threads", seed.build_threads()),
            ("messages", seed.build_messages()),
        ]
        try:
            counts = {table: store.count(table) for table, _ in seed_plan}
        except Exception as error:
            print("No se pudo revisar el esquema de Supabase: %s" % error)
            return 1
        partial = [
            (table, counts[table], len(rows))
            for table, rows in seed_plan
            if counts[table] not in (0, len(rows))
        ]
        if partial:
            print(
                "No se escribieron datos: hay tablas parcialmente sembradas. "
                "Revisa tabla, filas actuales y filas esperadas: %s"
                % ", ".join("%s=%d/%d" % item for item in partial)
            )
            return 1

        inserted = []
        skipped = []
        for table, rows in seed_plan:
            if counts[table] == len(rows):
                skipped.append(table)
                continue
            for row in rows:
                store.insert(table, row)
            inserted.append(table)
        print(
            "Semilla lista en Supabase. Completadas: %s. Ya estaban completas: %s."
            % (", ".join(inserted) or "ninguna", ", ".join(skipped) or "ninguna")
        )
        return 0

    info = store.info()
    print("modo:", info.get("mode"))
    table_counts = info.get("tables") or {}
    if isinstance(store, SupabaseStore):
        table_counts = {table: store.count(table) for table in TABLES}
    for table, count in sorted(table_counts.items()):
        print("  %-12s %3d filas" % (table, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
