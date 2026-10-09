# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Adaptador cultural de Ayllu.

Construye un «prompt blindado» (rol, reglas, glosario obligatorio, formato
de salida y prohibiciones explícitas) y lo envía a un LLM externo
(``LLM_API_URL``). Si el LLM no está disponible, aplica un adaptador
determinista por reglas que:

1. respeta el glosario (sustituye el término castellano por el de la
   simi objetivo seguido de la glosa entre paréntesis la primera vez),
2. simplifica por nivel (básico / intermedio / avanzado),
3. ancla el ejemplo al contexto de la ayllu.

El resultado siempre declara ``provider`` y ``degraded``: nunca se presenta
una salida por reglas como si viniera del LLM.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from core.seed import COMMUNITIES

MAX_SENTENCE_WORDS = {"básico": 14, "intermedio": 22, "avanzado": 32}

RULES = [
    "Traduce únicamente con las palabras del glosario cuando el término exista.",
    "Si un término técnico no está en el glosario, CONSÉRVALO en castellano y anótalo.",
    "Prohibido inventar neologismos o préstamos no documentados.",
    "Prohibido cambiar cifras, unidades, nombres propios ni fórmulas.",
    "Ancla cada ejemplo a la vida cotidiana de la comunidad indicada.",
    "Devuelve SOLO el JSON del esquema; sin explicaciones fuera de él.",
]


def _normalize(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    ).lower()


def glossary_hits(text: str, glossary_rows: List[dict], target: str) -> List[dict]:
    """Términos del glosario presentes en el texto (insensible a acentos)."""
    haystack = _normalize(text)
    hits: List[dict] = []
    for row in glossary_rows:
        term = row.get("term") or ""
        if not term:
            continue
        if _normalize(term) in haystack:
            translated = (row.get("langs") or {}).get(target)
            hits.append(
                {
                    "term": term,
                    "target": translated,
                    "domain": row.get("domain"),
                    "validated": bool(row.get("validated")),
                }
            )
    return hits


def build_prompt(
    text: str,
    src: str,
    tgt: str,
    level: str,
    community: Optional[dict],
    glossary_rows: List[dict],
) -> str:
    """Prompt blindado: rol + reglas + contexto + glosario + esquema JSON."""
    context = "comunidad no especificada"
    if community:
        context = "%s (%s, %s m, familia %s)" % (
            community.get("name"),
            community.get("ecosystem"),
            community.get("altitude"),
            community.get("family"),
        )
    glossary_block = "\n".join(
        "- %s => %s (%s)" % (r.get("term"), (r.get("langs") or {}).get(tgt), r.get("domain"))
        for r in glossary_rows[:24]
    ) or "- (glosario vacío)"
    schema = {
        "adapted": "texto adaptado",
        "glossary": ["términos del glosario usados"],
        "notes": ["decisiones o dudas para el hablante nativo"],
    }
    return (
        "ROL\n"
        "Eres adaptador cultural y traductor pedagógico de lenguas andinas y amazónicas.\n\n"
        "TAREA\n"
        "Adapta el texto del par %s -> %s para nivel %s en la %s.\n\n"
        "REGLAS (obligatorias)\n%s\n\n"
        "GLOSARIO PREFERENTE\n%s\n\n"
        "ESQUEMA DE SALIDA (JSON estricto)\n%s\n\n"
        "TEXTO ORIGEN\n%s\n"
        % (
            src,
            tgt,
            level,
            context,
            "\n".join("- " + rule for rule in RULES),
            glossary_block,
            json.dumps(schema, ensure_ascii=False),
            text,
        )
    )


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _close(piece: str) -> str:
    """Cierra un fragmento con punto, sin duplicarlo."""
    piece = piece.rstrip(" ,;:")
    if not piece:
        return piece
    return piece if piece.endswith((".", "!", "?", "…")) else piece + "."


DANGLING = {
    "y", "e", "o", "u", "de", "del", "al", "a", "en", "con", "por", "para",
    "que", "como", "su", "sus", "lo", "se", "no", "si", "más", "menos",
    "entre", "sobre", "tras", "sin", "ni", "es", "son", "está", "están",
    "cuando", "donde", "porque", "el", "la", "los", "las", "un", "una",
}


def _cut_point(words: List[str], limit: int) -> int:
    """Punto de corte de una frase larga.

    1. La última coma antes del límite (corte natural).
    2. Si no hay coma, el propio límite, avanzando mientras la última simi
       sea funcional (artículo, preposición, conjunción): así no se cierra una
       frase con «…la q'uñichiy y.»
    """
    for i in range(min(limit, len(words)), max(4, limit // 2) - 1, -1):
        if words[i - 1].endswith((",", ";", ":")):
            return i
    cut = limit
    while cut < len(words) and cut < limit + 8:
        bare = re.sub(r"[^\wáéíóúüñ]+$", "", words[cut - 1].lower())
        if bare in DANGLING:
            cut += 1
        else:
            break
    return cut


def _simplify(text: str, level: str) -> str:
    """Acorta las frases largas cortando en la última coma natural antes del límite.

    La versión anterior añadía un punto a fragmentos que ya terminaban en ".",
    lo que producía ".." y cortes a mitad de cláusula.
    """
    limit = MAX_SENTENCE_WORDS.get(level, 22)
    if level == "avanzado":
        return text
    out: List[str] = []
    for sentence in _split_sentences(text):
        remaining = sentence
        while len(remaining.split()) > limit:
            words = remaining.split()
            cut = _cut_point(words, limit)
            out.append(_close(" ".join(words[:cut])))
            remaining = " ".join(words[cut:]).strip()
        if remaining:
            out.append(_close(remaining))
    return re.sub(r"[ ]{2,}", " ", " ".join(out)).strip()


def _apply_glossary(text: str, hits: List[dict], level: str) -> str:
    """Anota en el texto ya traducido los términos del glosario.

    El traductor sustituye el castellano por el término objetivo, así que aquí
    se busca el TÉRMINO OBJETIVO (no el castellano). En nivel básico se añade la
    glosa castellana entre paréntesis la primera vez. La guarda ``(?!\\s*\\()``
    evita anotar iskay veces si la función se kutiy a aplicar.
    """
    result = text
    for hit in hits:
        target = (hit.get("target") or "").strip()
        term = hit.get("term")
        # Los términos de una sola letra (p. ej. «y» = yaku en guaraní) se omiten
        # aquí: marcarían conjunciones y el interior de otras simikuna.
        if len(target) < 2 or not term:
            continue
        if level == "básico":
            replacement = "%s (%s)" % (target, term)
        else:
            replacement = target
        # (?!\w) evita coincidencias dentro de otra simi; (?!\s*\() evita
        # anotar iskay veces si la función se kutiy a aplicar.
        pattern = r"(?<![\wáéíóúüñ])%s(?![\wáéíóúüñ])(?!\s*\()" % re.escape(target)
        result = re.sub(pattern, replacement.replace("\\", "\\\\"), result)
    return result


def _anchor(community: Optional[dict], level: str) -> str:
    """Anclaje cultural desactivado.

    La interfaz ya no añade ninguna frase de ejemplo al final del texto
    adaptado (se retiró el catálogo de anclajes por ecosistema). La función se
    conserva con la misma firma para no romper a quien la llame.
    """
    return ""


def _remote_adapt(prompt: str) -> Optional[Dict[str, object]]:
    url = os.environ.get("LLM_API_URL")
    if not url:
        return None
    timeout = float(os.environ.get("LLM_TIMEOUT", "20"))
    body = json.dumps({"prompt": prompt, "temperature": 0.2, "max_tokens": 900}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % os.environ.get("LLM_API_KEY", ""),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    text = None
    if isinstance(payload, dict):
        for key in ("adapted", "text", "output", "completion"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break
    if not text:
        return None
    flagged = any(bad in _normalize(text) for bad in ("no puedo", "as an ai", "lo siento"))
    return {"adapted": text, "flagged": flagged}


def adapt(
    text: str,
    src: str = "spa_Latn",
    tgt: str = "quy_Latn",
    level: str = "básico",
    community: Optional[dict] = None,
    glossary_rows: Optional[List[dict]] = None,
    raw_translation: str = "",
) -> dict:
    """Adapta ``text`` a ``tgt`` y devuelve la traza completa del proceso."""
    glossary_rows = glossary_rows or []
    hits = glossary_hits(text, glossary_rows, tgt)
    prompt = build_prompt(text, src, tgt, level, community, glossary_rows)

    remote = _remote_adapt(prompt)
    if remote and not remote.get("flagged"):
        return {
            "adapted": str(remote["adapted"]),
            "prompt": prompt,
            "glossary": hits,
            "provider": "llm-externo",
            "degraded": False,
            "notes": ["Salida generada por el LLM externo con el prompt blindado."],
        }

    base = raw_translation or text
    simplified = _simplify(base, level)
    adapted = _apply_glossary(simplified, hits, level)
    anchor = _anchor(community, level)
    adapted = ("%s %s" % (adapted.strip(), anchor)).strip() if adapted.strip() else anchor
    notes: List[str] = []
    if hits:
        notes.append("%d término(s) del glosario aplicados." % len(hits))
    if level != "avanzado":
        notes.append("Oraciones recortadas a %d palabras por nivel %s." % (
            MAX_SENTENCE_WORDS.get(level, 22),
            level,
        ))
    notes.append(
        "Adaptador por reglas: sustituye vocabulario, no reescribe la sintaxis. "
        "Requiere revisión de hablante nativo."
    )
    return {
        "adapted": adapted,
        "prompt": prompt,
        "glossary": hits,
        "provider": "reglas-locales",
        "degraded": True,
        "notes": notes,
    }


def gloss(
    text: str,
    tgt: str,
    glossary_rows: Optional[List[dict]] = None,
    level: str = "básico",
) -> dict:
    """Anota el glosario sobre un texto YA traducido, sin recortar ni anclar.

    Se usa en los mensajes del aula: el docente escribe una línea corta y el
    estudiante la lee con el vocabulario de su lengua resaltado, sin el recorte
    por nivel ni el anclaje cultural que sí aplican a los materiales.
    """
    rows = glossary_rows or []
    hits = glossary_hits(text, rows, tgt)
    return {
        "text": _apply_glossary(text, hits, level),
        "glossary": hits,
        "provider": "reglas-locales",
        "degraded": True,
    }


def community_by_id(store, community_id) -> Optional[dict]:
    """Busca una ayllu en el almacén (None si no existe)."""
    if community_id in (None, ""):
        return None
    try:
        community_id = int(community_id)
    except (TypeError, ValueError):
        return None
    for row in store.select("communities"):
        if int(row.get("id", -1)) == community_id:
            return row
    return None


def default_community() -> dict:
    return dict(COMMUNITIES[0])
