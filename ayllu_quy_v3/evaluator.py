# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Métricas de calidad de traducción para Ayllu.

- ``chr_f2``            — chrF2 (n-gramas de caracteres, F-beta con beta=2,
                          escala 0-100, como reporta sacrebleu).
- ``bertscore_like``    — BERTScore real si la librería ``bert-score`` está
                          instalada; si no, un proxy determinista por coseno
                          de bolsa de simikuna con hashing. El chakra ``kind``
                          dice cuál se usó: nunca se reporta el proxy como
                          BERTScore real.
- ``flesch_fernandez_huerta`` — índice de legibilidad para español.
- ``cohen_d``           — tamaño de efecto pre/post.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Dict, List

VOWELS = "aeiouáéíóúüAEIOUÁÉÍÓÚÜ"
DIPHTHONGS = (
    "ai", "au", "ei", "eu", "oi", "ou", "ia", "ie", "io", "iu", "ua", "ue",
    "ui", "uo", "ái", "áu", "éi", "éu", "ói", "óu", "ía", "ié", "ío", "iú",
    "uá", "ué", "uí", "uó",
)


def _fold(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def _chars(text: str, n: int) -> Counter:
    padded = " " + " ".join(_fold(text).split()) + " "
    return Counter(padded[i : i + n] for i in range(max(0, len(padded) - n + 1)))


def chr_f2(hypothesis: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    """chrF2 en escala 0-100. 0.0 si algún texto está vacío."""
    if not hypothesis or not reference:
        return 0.0
    hyp_grams = _chars(hypothesis, n)
    ref_grams = _chars(reference, n)
    overlap = sum((hyp_grams & ref_grams).values())
    if overlap == 0:
        return 0.0
    precision = overlap / max(1, sum(hyp_grams.values()))
    recall = overlap / max(1, sum(ref_grams.values()))
    b2 = beta * beta
    denominator = b2 * precision + recall
    if denominator == 0:
        return 0.0
    return round(100.0 * (1 + b2) * precision * recall / denominator, 2)


def _hash_vector(text: str, dim: int = 256) -> List[float]:
    vector = [0.0] * dim
    for token in _fold(text).split():
        token = token.strip(".,;:!?¡¿()[]«»\"'—–")
        if not token:
            continue
        # Python randomiza hash() en cada proceso; una semilla fija evita que
        # el proxy cambie de puntuación entre reinicios.
        index = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big") % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _cosine(a: List[float], b: List[float]) -> float:
    return round(sum(x * y for x, y in zip(a, b)), 4)


def bertscore_like(hypothesis: str, reference: str) -> Dict[str, object]:
    """BERTScore real si está disponible; si no, proxy declarado como tal."""
    if not hypothesis or not reference:
        return {"value": 0.0, "kind": "vacío"}
    try:  # pragma: no cover - depende de librería y modelo pesado
        from bert_score import score as _bert_score

        _, _, f1 = _bert_score([hypothesis], [reference], lang="es", verbose=False)
        return {"value": round(float(f1[0]), 4), "kind": "bert-score"}
    except Exception:
        return {
            "value": _cosine(_hash_vector(hypothesis), _hash_vector(reference)),
            "kind": "proxy-hashing",
        }


def _syllables(word: str) -> int:
    word = _fold(word).lower()
    groups = re.findall(r"[aeiou]+", word)
    count = len(groups)
    for group in groups:
        if len(group) == 2 and group not in DIPHTHONGS:
            count += 1  # hiato
    return max(1, count)


def flesch_fernandez_huerta(text: str) -> float:
    """Índice Fernández-Huerta: 206.84 - 0.60·P - 1.02·F (P y F por 100)."""
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text or "")
    if not words:
        return 0.0
    sentences = re.findall(r"[.!?]+", text or "")
    sentence_count = max(1, len(sentences))
    syllables = sum(_syllables(w) for w in words)
    p = syllables * 100.0 / len(words)
    f = sentence_count * 100.0 / len(words)
    return round(206.84 - 0.60 * p - 1.02 * f, 2)


def cohen_d(pre: List[float], post: List[float]) -> float:
    """Tamaño de efecto de Cohen para muestras pareadas."""
    if not pre or not post or len(pre) != len(post):
        return 0.0
    diffs = [b - a for a, b in zip(pre, post)]
    n = len(diffs)
    mean = sum(diffs) / n
    variance = sum((d - mean) ** 2 for d in diffs) / max(1, n - 1)
    sd = math.sqrt(variance)
    if sd == 0:
        return 0.0
    return round(mean / sd, 3)


def effect_label(d: float) -> str:
    """Etiqueta interpretativa del tamaño de efecto."""
    if d >= 0.8:
        return "impacto sólido"
    if d >= 0.5:
        return "impacto moderado"
    if d >= 0.2:
        return "impacto bajo"
    return "sin efecto apreciable"


def score_pair(hypothesis: str, reference: str) -> Dict[str, object]:
    """Bloque de métricas de un par traducido/adaptado."""
    bert = bertscore_like(hypothesis, reference)
    return {
        "chrF2": chr_f2(hypothesis, reference),
        "BERTScore": bert["value"],
        "BERTScoreKind": bert["kind"],
        "flesch": flesch_fernandez_huerta(hypothesis),
        "lengths": {"hypothesis": len(hypothesis or ""), "reference": len(reference or "")},
    }


def quality_band(chrf2: float) -> str:
    if chrf2 >= 75:
        return "ok"
    if chrf2 >= 60:
        return "warn"
    return "bad"
