# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""AylluService · 22 métodos de dominio + soporte.

Punto único de acceso a los datos para la API. Cada método devuelve
estructuras listas para JSON (sin objetos de base de datos).

Dominio (22): healthz, dashboard_summary, list_languages, list_communities,
get_community, create_community, update_community, delete_community,
list_students, create_student, update_student, delete_student, list_glossary,
create_glossary_term, update_glossary_term, delete_glossary_term,
import_glossary_csv, list_materials, create_material, update_material,
delete_material, adapt_text.
Soporte: evaluate, quality_report, analytics, submit_feedback,
list_feedback, activity, search.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Dict, List, Optional

import cultural_adapter
import evaluator
import translator
from core import auth
from core.db import MemoryStore, get_store
from core.seed import (
    DAILY_ACTIVITY,
    EXCLUDED_LANGUAGES,
    LANGUAGES,
    LEXICON,
)

WRITABLE_TABLES = ("communities", "students", "glossary", "materials", "feedback", "events")

LEVELS = ("básico", "intermedio", "avanzado")

ADAPT_KEYS = (
    "adapted",
    "cacheHit",
    "cacheId",
    "context",
    "degraded",
    "flesch",
    "glossary",
    "level",
    "rawTranslation",
    "scores",
    "src",
    "tgt",
)


class AylluService:
    """Fachada de dominio de Ayllu."""

    def __init__(self, store=None) -> None:
        self.store = store or get_store()
        self._lock = threading.RLock()
        self._adapt_cache: Dict[str, dict] = {}

    # ------------------------------------------------------------------ 1
    def healthz(self) -> dict:
        healthy = self.store.healthy()
        info = self.store.info()
        return {
            "status": "ok" if healthy else "degraded",
            "mode": info.get("mode", "memory"),
            "degraded": info.get("mode") != "supabase",
            "tables": info.get("tables", {}),
            "translator": {
                "primary": "google-translate",
                "fallback": "nllb-200-api → lexicon",
                "cache": translator.cache_stats()["entries"],
            },
        }

    # ------------------------------------------------------------------ 2
    def dashboard_summary(self) -> dict:
        communities = self.store.select("communities")
        students = self.store.select("students")
        languages = self.languages()
        active = [lang for lang in languages if lang.get("active")]
        adaptations = self._adapt_events()
        effective = [event for event in adaptations if float(event.get("chrF2", 0)) >= 60]
        pre = [float(s.get("pre", 0)) for s in students]
        post = [float(s.get("post", 0)) for s in students]
        kpis = {
            "communities": len(communities),
            "languages": len(languages),
            "activeLanguages": len(active),
            "students": len(students),
            "adaptations": len(adaptations),
            "glossaryTerms": self.store.count("glossary"),
            "materials": self.store.count("materials"),
            "effectiveRate": round(100.0 * len(effective) / max(1, len(adaptations)), 1),
            "avgGain": round(
                sum(post) / max(1, len(post)) - sum(pre) / max(1, len(pre)), 2
            ),
        }
        coverage = []
        for lang in languages:
            rows = [s for s in students if s.get("langCode") == lang["code"]]
            communities_of = [
                c for c in communities if c.get("langCode") == lang["code"]
            ]
            coverage.append(
                {
                    "code": lang["code"],
                    "name": lang["name"],
                    "nativeName": lang.get("nativeName"),
                    "students": len(rows),
                    "communities": len(communities_of),
                    "share": round(100.0 * len(rows) / max(1, len(students)), 1),
                }
            )
        return {
            "kpis": kpis,
            "coverage": coverage,
            "recent": sorted(
                adaptations, key=lambda e: str(e.get("ts", "")), reverse=True
            )[:6],
            "excluded": EXCLUDED_LANGUAGES,
        }

    # ------------------------------------------------------------------ 3
    def list_languages(self) -> List[dict]:
        rows = self.store.select("languages")
        return rows or list(LANGUAGES)

    def languages(self) -> List[dict]:
        return self.list_languages()

    # ------------------------------------------------------------------ 4
    def list_communities(self) -> List[dict]:
        rows = self.store.select("communities")
        for row in rows:
            row["studentCount"] = self.store.count("students", {"communityId": row["id"]})
        return rows

    # ------------------------------------------------------------------ 5
    def get_community(self, community_id: Any) -> Optional[dict]:
        row = self.store.get("communities", community_id)
        if not row:
            return None
        row["studentCount"] = self.store.count("students", {"communityId": row["id"]})
        row["students"] = self.store.select("students", {"communityId": row["id"]})
        return row

    # ------------------------------------------------------------------ 6
    def create_community(self, payload: Dict[str, Any]) -> dict:
        row = self._clean_community(payload)
        return self.store.insert("communities", row)

    # ------------------------------------------------------------------ 7
    def update_community(self, community_id: Any, payload: Dict[str, Any]) -> Optional[dict]:
        if not self.store.get("communities", community_id):
            return None
        return self.store.update("communities", community_id, self._clean_community(payload, partial=True))

    # ------------------------------------------------------------------ 8
    def delete_community(self, community_id: Any) -> bool:
        return self.store.delete("communities", community_id)

    # ------------------------------------------------------------------ 9
    def list_students(self) -> List[dict]:
        rows = self.store.select("students")
        communities = {c["id"]: c for c in self.store.select("communities")}
        for row in rows:
            row["delta"] = round(float(row.get("post", 0)) - float(row.get("pre", 0)), 1)
            community = communities.get(row.get("communityId"))
            row["communityName"] = (community or {}).get("name", "—")
        return rows

    # ----------------------------------------------------------------- 10
    def create_student(self, payload: Dict[str, Any]) -> dict:
        return self.store.insert("students", self._clean_student(payload))

    # ----------------------------------------------------------------- 11
    def update_student(self, student_id: Any, payload: Dict[str, Any]) -> Optional[dict]:
        if not self.store.get("students", student_id):
            return None
        return self.store.update("students", student_id, self._clean_student(payload, partial=True))

    # ----------------------------------------------------------------- 12
    def delete_student(self, student_id: Any) -> bool:
        return self.store.delete("students", student_id)

    # ----------------------------------------------------------------- 13
    def list_glossary(self, query: str = "", target: str = "") -> List[dict]:
        rows = self.store.select("glossary")
        if query:
            needle = query.strip().lower()
            rows = [
                r
                for r in rows
                if needle
                in " ".join(
                    [str(r.get("term", "")), str(r.get("domain", ""))]
                    + [str(v) for v in (r.get("langs") or {}).values()]
                ).lower()
            ]
        return rows

    # ----------------------------------------------------------------- 14
    def create_glossary_term(self, payload: Dict[str, Any]) -> dict:
        return self.store.insert("glossary", self._clean_term(payload))

    # ----------------------------------------------------------------- 15
    def update_glossary_term(self, term_id: Any, payload: Dict[str, Any]) -> Optional[dict]:
        if not self.store.get("glossary", term_id):
            return None
        return self.store.update("glossary", term_id, self._clean_term(payload, partial=True))

    # ----------------------------------------------------------------- 16
    def delete_glossary_term(self, term_id: Any) -> bool:
        return self.store.delete("glossary", term_id)

    # ----------------------------------------------------------------- 17
    def import_glossary_csv(self, text: str) -> dict:
        """Importa líneas ``es;quy;ayr;grn;dominio`` (cabecera opcional)."""
        created, skipped = [], []
        for index, raw in enumerate((text or "").splitlines()):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.replace(",", ";").split(";")]
            if index == 0 and parts[0].lower() in ("es", "term", "termino", "término"):
                continue
            if len(parts) < 2 or not parts[0]:
                skipped.append(line)
                continue
            parts += [""] * (5 - len(parts))
            created.append(
                self.store.insert(
                    "glossary",
                    self._clean_term(
                        {
                            "term": parts[0],
                            "langs": {
                                "spa_Latn": parts[0],
                                "quy_Latn": parts[1],
                                "ayr_Latn": parts[2],
                                "grn_Latn": parts[3],
                            },
                            "domain": parts[4] or "general",
                            "updatedBy": "import-csv",
                        }
                    ),
                )
            )
        return {"created": len(created), "skipped": skipped, "rows": created}

    # ----------------------------------------------------------------- 18
    def list_materials(self) -> List[dict]:
        return self.store.select("materials")

    # ----------------------------------------------------------------- 19
    def create_material(self, payload: Dict[str, Any]) -> dict:
        return self.store.insert("materials", self._clean_material(payload))

    # ----------------------------------------------------------------- 20
    def update_material(self, material_id: Any, payload: Dict[str, Any]) -> Optional[dict]:
        if not self.store.get("materials", material_id):
            return None
        return self.store.update("materials", material_id, self._clean_material(payload, partial=True))

    # ----------------------------------------------------------------- 21
    def delete_material(self, material_id: Any) -> bool:
        return self.store.delete("materials", material_id)

    # ----------------------------------------------------------------- 22
    def adapt_text(self, payload: Dict[str, Any]) -> dict:
        """Traduce + adapta y devuelve exactamente las 12 claves públicas."""
        text = str(payload.get("text") or "").strip()
        src = str(payload.get("src") or "spa_Latn")
        tgt = str(payload.get("tgt") or "quy_Latn")
        level = str(payload.get("level") or "básico")
        if level not in LEVELS:
            level = "básico"
        glossary_rows = self.store.select("glossary")
        community = cultural_adapter.community_by_id(self.store, payload.get("communityId"))
        if community is None and payload.get("communityName"):
            for row in self.store.select("communities"):
                if str(row.get("name")) == str(payload.get("communityName")):
                    community = row
                    break

        cache_id = hashlib.sha1(
            ("%s|%s|%s|%s" % (src, tgt, level, text[:120])).encode("utf-8")
        ).hexdigest()[:12]
        if not text:
            return {
                "adapted": "",
                "cacheHit": False,
                "cacheId": cache_id,
                "context": {"community": None, "language": tgt, "level": level},
                "degraded": True,
                "flesch": 0.0,
                "glossary": [],
                "level": level,
                "rawTranslation": "",
                "scores": {"chrF2": 0.0, "BERTScore": 0.0, "BERTScoreKind": "vacío"},
                "src": src,
                "tgt": tgt,
            }

        with self._lock:
            cached = self._adapt_cache.get(cache_id)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result

        raw = translator.translate(text, src, tgt)
        adapted = cultural_adapter.adapt(
            text,
            src=src,
            tgt=tgt,
            level=level,
            community=community,
            glossary_rows=glossary_rows,
            raw_translation=raw["text"],
        )
        scores = evaluator.score_pair(adapted["adapted"], raw["text"])
        result = {
            "adapted": adapted["adapted"],
            "cacheHit": False,
            "cacheId": cache_id,
            "context": {
                "community": (community or {}).get("name"),
                "ecosystem": (community or {}).get("ecosystem"),
                "language": tgt,
                "level": level,
            },
            "degraded": bool(raw.get("degraded") and adapted.get("degraded")),
            "flesch": evaluator.flesch_fernandez_huerta(adapted["adapted"]),
            "glossary": adapted["glossary"],
            "level": level,
            "rawTranslation": raw["text"],
            "scores": {
                "chrF2": scores["chrF2"],
                "BERTScore": scores["BERTScore"],
                "BERTScoreKind": scores["BERTScoreKind"],
            },
            "src": src,
            "tgt": tgt,
        }
        # datos de proceso que no forman rak'i del contrato público
        result["_debug"] = {
            "provider": "%s + %s" % (raw.get("provider"), adapted.get("provider")),
            "prompt": adapted.get("prompt"),
            "notes": adapted.get("notes", []),
            "coverage": raw.get("coverage"),
            "untranslated": raw.get("untranslated", []),
            "lexiconSize": raw.get("lexiconSize", len(LEXICON.get(tgt, {}))),
            "grammarKept": raw.get("grammarKept", 0),
        }
        with self._lock:
            self._adapt_cache[cache_id] = result
        self.store.insert(
            "events",
            {
                "kind": "adapt",
                "langCode": tgt,
                "snippet": text[:120],
                "chrF2": result["scores"]["chrF2"],
                "actor": str(payload.get("actor") or "api"),
                "ts": self._now(),
            },
        )
        return result

    # -- soporte -------------------------------------------------------------
    def public_adapt(self, payload: Dict[str, Any]) -> dict:
        """Adaptación sin chakrakuna internos, para el contrato de la API."""
        result = self.adapt_text(payload)
        debug = result.pop("_debug", None)
        if debug:
            result["provider"] = debug["provider"]
            result["coverage"] = debug["coverage"]
            result["lexiconSize"] = debug.get("lexiconSize")
            result["grammarKept"] = debug.get("grammarKept", 0)
            notes = list(debug["notes"])
            if result["degraded"]:
                notes.append(
                    "Glosa palabra por palabra: se traduce vocabulario; la gramática se mantiene "
                    "en castellano porque la morfología de la lengua destino no se puede reproducir "
                    "término a término. Cobertura de vocabulario: %s%% (%s palabras funcionales "
                    "conservadas a propósito)."
                    % (debug["coverage"], debug.get("grammarKept", 0))
                )
            result["notes"] = notes
        return result

    def evaluate(self, payload: Dict[str, Any]) -> dict:
        hypothesis = str(payload.get("hypothesis") or payload.get("adapted") or "")
        reference = str(payload.get("reference") or payload.get("rawTranslation") or "")
        return {
            "scores": evaluator.score_pair(hypothesis, reference),
            "band": evaluator.quality_band(evaluator.chr_f2(hypothesis, reference)),
            "flesch": evaluator.flesch_fernandez_huerta(hypothesis),
        }

    def quality_report(self) -> dict:
        students = self.store.select("students")
        pre = [float(s.get("pre", 0)) for s in students]
        post = [float(s.get("post", 0)) for s in students]
        d = evaluator.cohen_d(pre, post)
        per_language: List[dict] = []
        for lang in self.list_languages():
            rows = [s for s in students if s.get("langCode") == lang["code"]]
            if not rows:
                continue
            lp = [float(s.get("pre", 0)) for s in rows]
            lq = [float(s.get("post", 0)) for s in rows]
            ld = evaluator.cohen_d(lp, lq)
            per_language.append(
                {
                    "code": lang["code"],
                    "name": lang["name"],
                    "students": len(rows),
                    "preAvg": round(sum(lp) / len(lp), 1),
                    "postAvg": round(sum(lq) / len(lq), 1),
                    "cohenD": ld,
                    "label": evaluator.effect_label(ld),
                }
            )
        cohorts = []
        for cohort in sorted({str(s.get("cohort", "—")) for s in students}):
            rows = [s for s in students if str(s.get("cohort")) == cohort]
            cp = [float(s.get("pre", 0)) for s in rows]
            cq = [float(s.get("post", 0)) for s in rows]
            cd = evaluator.cohen_d(cp, cq)
            cohorts.append(
                {
                    "cohort": cohort,
                    "students": len(rows),
                    "delta": round(sum(cq) / len(cq) - sum(cp) / len(cp), 1),
                    "cohenD": cd,
                    "label": evaluator.effect_label(cd),
                }
            )
        return {
            "students": len(students),
            "preAvg": round(sum(pre) / max(1, len(pre)), 1),
            "postAvg": round(sum(post) / max(1, len(post)), 1),
            "cohenD": d,
            "label": evaluator.effect_label(d),
            "perLanguage": per_language,
            "cohorts": cohorts,
            "legend": [
                "cohen d >= 0.8 → impacto sólido",
                "cohen d >= 0.5 → impacto moderado",
                "cohen d >= 0.2 → impacto bajo",
            ],
        }

    def analytics(self) -> dict:
        events = self._adapt_events()
        glossary = self.store.select("glossary")
        word_pool: Dict[str, int] = {}
        for term in glossary:
            count = 0
            for event in events:
                if str(term.get("term", "")).lower() in str(event.get("snippet", "")).lower():
                    count += 1
            if count:
                word_pool[str(term.get("term"))] = count
        for term in glossary[:6]:
            word_pool.setdefault(str(term.get("term")), 1)
        cloud = [
            {"term": term, "count": count}
            for term, count in sorted(word_pool.items(), key=lambda kv: -kv[1])[:18]
        ]
        leaderboard = sorted(
            (
                {
                    "snippet": str(e.get("snippet", ""))[:70],
                    "langCode": e.get("langCode"),
                    "chrF2": float(e.get("chrF2", 0)),
                    "actor": e.get("actor"),
                    "ts": e.get("ts"),
                }
                for e in events
            ),
            key=lambda item: -item["chrF2"],
        )[:10]
        avg = round(sum(item["chrF2"] for item in leaderboard) / max(1, len(leaderboard)), 2)
        alerts = []
        if avg < 70:
            alerts.append({"level": "warn", "text": "chrF2 promedio por debajo de 70."})
        if not glossary:
            alerts.append({"level": "bad", "text": "Glosario vacío: el adaptador degrada."})
        for language in self.list_languages():
            if not language.get("active"):
                alerts.append(
                    {"level": "warn", "text": "Lengua %s desactivada." % language["code"]}
                )
        if not alerts:
            alerts.append({"level": "ok", "text": "Sin alertas operacionales."})
        return {
            "coverage": self.dashboard_summary()["coverage"],
            "daily": DAILY_ACTIVITY,
            "cloud": cloud,
            "leaderboard": leaderboard,
            "avgChrF2": avg,
            "alerts": alerts,
            "note": "La serie diaria es demonstrativa (ver README · Limitaciones).",
        }

    def submit_feedback(self, payload: Dict[str, Any]) -> dict:
        rating = payload.get("rating", 0)
        try:
            rating = max(1, min(5, int(rating)))
        except (TypeError, ValueError):
            rating = 1
        return self.store.insert(
            "feedback",
            {
                "studentId": payload.get("studentId"),
                "rating": rating,
                "note": str(payload.get("note") or "").strip(),
                "reviewer": str(payload.get("reviewer") or "anónimo"),
                "createdAt": self._now(),
            },
        )

    def list_feedback(self) -> List[dict]:
        rows = self.store.select("feedback")
        return sorted(rows, key=lambda r: str(r.get("createdAt", "")), reverse=True)

    def activity(self, limit: int = 20) -> List[dict]:
        events = self.store.select("events")
        activity = sorted(events, key=lambda e: str(e.get("ts", "")), reverse=True)[:limit]
        for row in activity:
            row["type"] = row.get("kind", "evento")
        return activity

    def search(self, query: str) -> dict:
        needle = (query or "").strip().lower()
        if not needle:
            return {"query": query, "results": [], "total": 0}
        groups = (
            ("comunidad", "communities", ("name", "ecosystem", "family", "description")),
            ("estudiante", "students", ("name", "cohort")),
            ("glosario", "glossary", ("term", "domain")),
            ("material", "materials", ("title", "kind", "snippet")),
        )
        results: List[dict] = []
        for label, table, fields in groups:
            for row in self.store.select(table):
                haystack = " ".join(str(row.get(f, "")) for f in fields).lower()
                if needle in haystack:
                    results.append(
                        {
                            "type": label,
                            "id": row.get("id"),
                            "title": row.get(fields[0]),
                            "detail": str(row.get(fields[-1], ""))[:90],
                        }
                    )
        return {"query": query, "results": results[:40], "total": len(results)}

    def prompt_preview(self, payload: Dict[str, Any]) -> dict:
        """Prompt blindado SIN llamar al LLM (botón «Rikuy prompt blindado»).

        No entra en el contrato de 12 claves de /api/adapt: tiene su propio
        endpoint para no alterar la respuesta pública de la adaptación.
        """
        text = str(payload.get("text") or "").strip()
        src = str(payload.get("src") or "spa_Latn")
        tgt = str(payload.get("tgt") or "quy_Latn")
        level = str(payload.get("level") or "básico")
        if level not in LEVELS:
            level = "básico"
        community = cultural_adapter.community_by_id(self.store, payload.get("communityId"))
        glossary_rows = self.store.select("glossary")
        return {
            "prompt": cultural_adapter.build_prompt(text, src, tgt, level, community, glossary_rows),
            "src": src,
            "tgt": tgt,
            "level": level,
            "community": (community or {}).get("name"),
            "glossary": cultural_adapter.glossary_hits(text, glossary_rows, tgt),
            "glossarySize": len(glossary_rows),
            "rules": list(cultural_adapter.RULES),
            "lexiconSize": len(LEXICON.get(tgt, {})),
        }

    def export_rows(self, table: str) -> List[dict]:
        if table not in WRITABLE_TABLES and table != "languages":
            raise KeyError(table)
        return self.store.select(table)

    def reset(self) -> None:
        if isinstance(self.store, MemoryStore):
            self.store.reset()
        with self._lock:
            self._adapt_cache.clear()
        translator.clear_cache()

    # -------------------------------------------------------------- 24 · v3
    def list_users(self) -> List[dict]:
        """Directorio de cuentas (docente y estudiantes) para el login."""
        from . import auth as _auth

        return _auth.public_users()

    # ----------------------------------------------------------------- 25
    def list_messages(self, user_id: Any = None, role: str = "", limit: int = 60) -> List[dict]:
        """Bandeja del aula: los mensajes en los que participa ``user_id``."""
        rows = self.store.select("messages")
        if user_id not in (None, "", 0, "0"):
            rows = [
                row
                for row in rows
                if str(row.get("fromUserId")) == str(user_id)
                or str(row.get("toUserId")) == str(user_id)
            ]
        if role:
            rows = [row for row in rows if role in (row.get("fromRole"), row.get("toRole"))]
        rows.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
        return rows[: int(limit)] if limit else rows

    # ----------------------------------------------------------------- 26
    def create_message(self, payload: Dict[str, Any]) -> dict:
        """Traduce y encola un mensaje entre los dos roles.

        Dirección estudiante → docente: el estudiante escribe en su lengua y se
        guarda además la traducción al castellano. Dirección docente →
        estudiante: se conserva el original castellano y se traduce a la lengua
        del estudiante. Nunca se altera el texto que escribió la persona: el
        original queda en ``srcText`` y la traducción en ``outText``.
        """
        from . import auth as _auth
        from . import seed as _seed

        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("el mensaje está vacío")

        directory = _auth.users()
        sender = None
        for index, row in enumerate(_seed.USERS, start=1):
            if str(index) == str(payload.get("fromUserId")):
                sender = dict(row, userId=index)
                break
        if sender is None:
            for record in directory.values():
                if record.get("email") == str(payload.get("fromEmail") or ""):
                    sender = record
                    break
        if sender is None:
            raise ValueError("remitente desconocido")

        recipient = None
        if payload.get("toUserId") not in (None, "", 0, "0"):
            for index, row in enumerate(_seed.USERS, start=1):
                if str(index) == str(payload.get("toUserId")):
                    recipient = dict(row, userId=index)
                    break
        if recipient is None:
            recipient = next(
                (
                    record
                    for record in directory.values()
                    if record.get("role") != sender.get("role")
                ),
                None,
            )
        if recipient is None:
            raise ValueError("destinatario desconocido")
        if str(recipient.get("userId")) == str(sender.get("userId")):
            raise ValueError("el remitente y el destinatario deben tener roles distintos")

        kind = str(payload.get("kind") or "mensaje").strip().lower()
        if kind == "actividad":
            if sender.get("role") != "docente":
                raise ValueError("solo un docente puede enviar actividades")
            if recipient.get("role") != "estudiante":
                raise ValueError("una actividad debe dirigirse a un estudiante")

        student = next(
            (
                row
                for row in self.store.select("students")
                if str(row.get("name")) == str(sender.get("studentName") or recipient.get("studentName"))
            ),
            None,
        )

        # El idioma de destino puede fijarse de forma explícita (el escáner
        # entrega el mismo documento en varias lenguas a la vez). Si no se
        # indica, se usa el de la cuenta destinataria; el origen, por omisión,
        # es el de quien escribe.
        src = str(payload.get("src") or sender.get("langCode") or "spa_Latn")
        if src not in {str(row.get("code")) for row in self.list_languages()}:
            raise ValueError("Elige una lengua de origen válida.")
        tgt = str(payload.get("tgt") or recipient.get("langCode") or "spa_Latn")
        level = str(payload.get("level") or "básico")
        if level not in LEVELS:
            level = "básico"
        # El texto que escribió la persona NUNCA se modifica: se guarda tal cual
        # en ``srcText`` y lo que se traduce es la entrega al otro lado.
        original = text
        origin_es = ""
        notes: List[str] = [
            "Original intacto: el texto que escribió %s se conserva tal cual." % sender.get("name"),
        ]

        # La dirección la decide el par de lenguas, no el rol: así el aula
        # funciona igual con un profesor aimara, con una lengua internacional
        # o con un estudiante que escribe en una variante de quechua.
        reverse = tgt == "spa_Latn" and src != "spa_Latn"
        if reverse:
            # Lengua originaria → castellano: el docente necesita leerlo.
            raw = translator.translate(original, src, "spa_Latn")
            out_text = raw.get("text") or ""
            glossed = {"glossary": []}
            notes.append(
                "Dirección aula → castellano: se tradujo del %s al castellano con la "
                "cascada de motores disponible." % src
            )
        else:
            # Castellano → lengua del aula (o hacia otra lengua internacional):
            # mensaje o documento adaptado.
            raw = translator.translate(original, src, tgt)
            glossed = cultural_adapter.gloss(
                raw.get("text") or "", tgt, self.store.select("glossary"), level
            )
            out_text = glossed.get("text") or ""
            notes.append(
                "Dirección castellano → %s: se tradujo y se anotó el vocabulario "
                "del glosario." % tgt
            )

        lexicon_language = src if reverse else tgt
        if raw.get("engine") == "lexicon" and not raw.get("lexiconSize"):
            # Honestidad: sin motor conectado y sin columna en el glosario no hay
            # nada que glosar. Se declara en lugar de presentar el original como
            # si fuera una traducción.
            notes.append(
                "La lengua %s no tiene léxico embebido: sin motor de traducción conectado "
                "no se puede glosar el texto (se muestra el original sin cambios)." % lexicon_language
            )

        if raw.get("degraded"):
            notes.append(
                "Salida de respaldo: glosa automática, no es una traducción completa; "
                "requiere revisión de una persona hablante."
            )

        if str(payload.get("kind")) == "material":
            notes.append("Documento adaptado: el destinatario recibe el contenido en su lengua.")
        elif str(payload.get("kind")) == "actividad":
            notes.append("Actividad asignada por el docente; la respuesta se registra en la bandeja del aula.")

        scores = evaluator.score_pair(out_text, raw.get("text") or "")

        row = {
            "fromUserId": sender.get("userId"),
            "toUserId": recipient.get("userId"),
            "fromRole": sender.get("role"),
            "toRole": recipient.get("role"),
            "fromName": sender.get("name"),
            "toName": recipient.get("name"),
            "studentId": (student or {}).get("id"),
            "studentName": (student or {}).get("name") or recipient.get("name"),
            "kind": kind if kind in ("mensaje", "material", "actividad") else "mensaje",
            "title": str(payload.get("title") or "").strip(),
            "src": src,
            "tgt": tgt,
            "srcText": original,
            "outText": out_text,
            "originEs": origin_es,
            "provider": raw.get("provider"),
            "engine": raw.get("engine"),
            "degraded": bool(raw.get("degraded")),
            "coverage": raw.get("coverage"),
            "chrF2": scores["chrF2"],
            "glossary": glossed.get("glossary") or [],
            "notes": notes,
            "createdAt": self._now(),
            "readAt": None,
        }
        saved = self.store.insert("messages", row)
        self.store.insert(
            "events",
            {
                "kind": "mensaje",
                "langCode": tgt,
                "snippet": text[:120],
                "chrF2": scores["chrF2"],
                "actor": sender.get("email") or "api",
                "ts": self._now(),
            },
        )
        return saved

    def deliver_scanned_document(
        self,
        scanned: Dict[str, Any],
        *,
        from_user_id: Any,
        to_user_id: Any,
        targets: List[str],
        title: str = "",
        level: str = "básico",
    ) -> Dict[str, Any]:
        """Entrega un documento ya escaneado en UNA o VARIAS lenguas.

        Reutiliza ``create_message``: el original queda intacto en ``srcText`` y
        cada lengua destino produce su propia entrega en la bandeja del aula.
        Solo se usa cuando el usuario eligió destino(s) en el escáner.
        """
        text = str(scanned.get("text") or "").strip()
        if not text:
            raise ValueError("El documento no tiene texto extraíble: requiere OCR.")
        known = {str(row.get("code")) for row in self.list_languages()}
        clean_targets = [str(t).strip() for t in (targets or []) if str(t).strip() in known]
        if not clean_targets:
            raise ValueError("Elige al menos una lengua de destino válida.")
        deliveries: List[dict] = []
        for tgt in clean_targets[:6]:
            row = self.create_message(
                {
                    "fromUserId": from_user_id,
                    "toUserId": to_user_id,
                    "kind": "material",
                    "title": (title or scanned.get("name") or "Documento").strip()[:120],
                    "text": text[:8000],
                    "tgt": tgt,
                    "level": level,
                }
            )
            deliveries.append(
                {
                    "tgt": tgt,
                    "messageId": row.get("id"),
                    "messageTitle": row.get("title"),
                    "outText": row.get("outText"),
                    "coverage": row.get("coverage"),
                    "degraded": row.get("degraded"),
                    "chrF2": row.get("chrF2"),
                    "glossaryHits": len(row.get("glossary") or []),
                }
            )
        return {
            "deliveries": deliveries,
            "chars": len(text),
            "targets": clean_targets[:6],
            "document": {
                "name": scanned.get("name"),
                "pages": scanned.get("pages"),
                "chars": scanned.get("chars"),
                "words": scanned.get("words"),
                "sizeLabel": scanned.get("sizeLabel"),
            },
        }

    # ----------------------------------------------------------------- 27
    def mark_message_read(self, message_id: Any) -> Optional[dict]:
        if not self.store.get("messages", message_id):
            return None
        return self.store.update("messages", message_id, {"readAt": self._now()})

    # ----------------------------------------------------------------- 28
    def insights(self) -> dict:
        """Tablero de gestión del aula: cobertura, pares de lenguas y actividad."""
        messages = self.store.select("messages")
        events = self.store.select("events")
        hits = [float(row.get("coverage") or 0) for row in messages if row.get("coverage")]
        pairs: Dict[str, int] = {}
        for row in messages:
            key = "%s → %s" % (row.get("src"), row.get("tgt"))
            pairs[key] = pairs.get(key, 0) + 1
        return {
            "messages": len(messages),
            "adaptations": len([e for e in events if e.get("kind") == "adapt"]),
            "coverage": round(sum(hits) / len(hits), 1) if hits else 0.0,
            "pairs": sorted(
                ({"pair": key, "count": value} for key, value in pairs.items()),
                key=lambda item: -item["count"],
            ),
            "languages": len([lang for lang in self.store.select("languages") if lang.get("active")]),
            "images": [],
        }

    # -- utilidades ----------------------------------------------------------
    @staticmethod
    def _now() -> str:
        from core.seed import now_iso

        return now_iso()

    def _adapt_events(self) -> List[dict]:
        return [e for e in self.store.select("events") if e.get("kind") == "adapt"]

    @staticmethod
    def _clean_community(payload: Dict[str, Any], partial: bool = False) -> dict:
        row: Dict[str, Any] = {}
        for key in ("name", "ecosystem", "langCode", "family", "description"):
            if key in payload:
                row[key] = str(payload.get(key) or "").strip()
        if "altitude" in payload:
            try:
                row["altitude"] = int(payload.get("altitude") or 0)
            except (TypeError, ValueError):
                row["altitude"] = 0
        if not partial:
            row.setdefault("name", "Comunidad sin nombre")
            row.setdefault("ecosystem", "andino")
            row.setdefault("langCode", "quy_Latn")
            row.setdefault("family", "Quechua")
            row.setdefault("altitude", 0)
            row.setdefault("description", "")
        return row

    @staticmethod
    def _clean_student(payload: Dict[str, Any], partial: bool = False) -> dict:
        row: Dict[str, Any] = {}
        if "name" in payload:
            row["name"] = str(payload.get("name") or "").strip()
        if "langCode" in payload:
            row["langCode"] = str(payload.get("langCode") or "quy_Latn")
        if "cohort" in payload:
            row["cohort"] = str(payload.get("cohort") or "A")
        for key in ("communityId", "pre", "post", "attendance"):
            if key in payload:
                try:
                    row[key] = int(payload.get(key) or 0)
                except (TypeError, ValueError):
                    row[key] = 0
        if not partial:
            row.setdefault("name", "Estudiante")
            row.setdefault("langCode", "quy_Latn")
            row.setdefault("cohort", "A")
            row.setdefault("communityId", 1)
            row.setdefault("pre", 0)
            row.setdefault("post", 0)
            row.setdefault("attendance", 0)
        return row

    @staticmethod
    def _clean_term(payload: Dict[str, Any], partial: bool = False) -> dict:
        row: Dict[str, Any] = {}
        if "term" in payload:
            row["term"] = str(payload.get("term") or "").strip()
        if "langs" in payload and isinstance(payload.get("langs"), dict):
            langs = payload["langs"]
            # Se conservan las cuatro lenguas del MVP y, además, cualquier otra
            # clave de lengua que envíe la interfaz: el catálogo creció más allá
            # de las cuatro iniciales y el glosario no debe perder columnas.
            row["langs"] = {str(k): str(v or "").strip() for k, v in langs.items()}
            for core in ("spa_Latn", "quy_Latn", "ayr_Latn", "grn_Latn"):
                row["langs"].setdefault(core, "")
        if "domain" in payload:
            row["domain"] = str(payload.get("domain") or "general")
        if "validated" in payload:
            row["validated"] = bool(payload.get("validated"))
        if "updatedBy" in payload:
            row["updatedBy"] = str(payload.get("updatedBy") or "api")
        if not partial:
            row.setdefault("term", "término")
            row.setdefault(
                "langs",
                {"spa_Latn": row.get("term", ""), "quy_Latn": "", "ayr_Latn": "", "grn_Latn": ""},
            )
            row.setdefault("domain", "general")
            row.setdefault("validated", False)
            row.setdefault("updatedBy", "api")
        return row

    @staticmethod
    def _clean_material(payload: Dict[str, Any], partial: bool = False) -> dict:
        row: Dict[str, Any] = {}
        for key in ("title", "kind", "langCode", "level", "snippet", "size"):
            if key in payload:
                row[key] = str(payload.get(key) or "").strip()
        if not partial:
            row.setdefault("title", "Material sin título")
            row.setdefault("kind", "lectura")
            row.setdefault("langCode", "spa_Latn")
            row.setdefault("level", "todos")
            row.setdefault("snippet", "")
            row.setdefault("size", "—")
        return row


_SERVICE: Optional[AylluService] = None


def get_service() -> AylluService:
    """Singleton del servicio de dominio."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AylluService()
    return _SERVICE


def reset_service() -> None:
    global _SERVICE
    _SERVICE = None


def lexicon_preview(target: str = "quy_Latn", limit: int = 8) -> List[dict]:
    """Vista previa del léxico embebido (para la pantalla de Admin)."""
    return [
        {"es": es, "target": value}
        for es, value in list(LEXICON.get(target, {}).items())[:limit]
    ]


def auth_users() -> Dict[str, Dict[str, str]]:
    return auth.users()
