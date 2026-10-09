# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Traducción automática para Ayllu.

Jerarquía de motores (la primera que funcione gana):

1. **Google Translate** por endpoint público ``translate_a/single?client=gtx``
   (código ``qu`` para Quechua sureño genérico). No requiere API key,
   sujeto a rate-limit (~5 req/s, 200k req/día por IP). Back-off
   exponencial automático ante 429/503.
2. **NLLB-200** servido por la Inference API de Hugging Face
   (``HF_API_URL`` + ``HF_API_TOKEN``) o por una API genérica
   (``NLLB_API_URL``). Sin HF_TOKEN configurado no se invoca; pasamos
   directamente al lexicón de respaldo.
3. **Respaldo determinista**: glosa término a término con el léxico
   embebido (``core.seed.LEXICON``). Sólo se usa cuando (1) y (2) no
   responden. Marca explícitamente lo que no pudo traducir en
   ``untranslated``.

El resultado declara ``provider``, ``degraded``, ``engine``
(``google|nllb|lexicon|noop``) y ``engineCode`` para que la UI pueda
mostrar la procedencia y nunca presente el glosario como traducción
neuronal.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from core.seed import GOOGLE_CODE, LEXICON

logger = logging.getLogger("ayllu.translator")

_CACHE: Dict[str, dict] = {}
_LOCK = threading.RLock()

GOOGLE_QH_CODE = "qu"          # código ISO de Google Translate para Quechua
NLLB_QY_CODE = "quy_Latn"      # código FLORES-200 de Quechua ayacuchano

# Simi funcionales del castellano (no se glosan a propósito).
GRAMMAR_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "en", "con", "por", "para", "y", "e", "o", "u", "que", "se", "su",
    "sus", "lo", "le", "les", "me", "te", "nos", "es", "son", "era", "fue",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel",
    "aquella", "mi", "tu", "nuestro", "nuestra", "más", "menos", "muy", "no",
    "si", "ya", "aún", "también", "tampoco", "cuando", "como", "donde",
    "porque", "aunque", "pero", "sino", "entre", "sobre", "tras", "desde",
    "hasta", "hacia", "sin", "ni", "mientras", "pues", "así", "tan", "les",
}

PUNCT = ".,;:!?¡¿()[]«»\"'—–…"

SUFFIXES = (
    "ciones", "mientos", "mente", "dores", "ción", "ando", "iendo",
    "ados", "adas", "aban", "aron", "amos", "emos", "imos", "ado",
    "ada", "ido", "ida", "ar", "er", "ir", "an", "en", "as", "es",
    "os", "a", "e", "o", "s",
)
MIN_STEM = 4


# ---------------------------------------------------------------- result type
@dataclass
class TranslationResult:
    text: str
    provider: str
    degraded: bool
    engine: str = "none"
    engine_code: str = ""
    hits: List[str] = field(default_factory=list)
    misses: List[str] = field(default_factory=list)
    grammar_kept: int = 0
    coverage: float = 0.0
    lexicon_size: int = 0
    latency_ms: int = 0
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "provider": self.provider,
            "degraded": self.degraded,
            "engine": self.engine,
            "engineCode": self.engine_code,
            "hits": self.hits,
            "untranslated": self.misses,
            "grammarKept": self.grammar_kept,
            "coverage": self.coverage,
            "lexiconSize": self.lexicon_size,
            "latencyMs": self.latency_ms,
            "error": self.error,
        }


# =================================================================== helpers
def _open_translation_url(request, timeout: float):
    """Evita el proxy local de bloqueo usado en el entorno de desarrollo.

    Se conserva cualquier proxy real configurado por la escuela/servidor; solo
    se omite el proxy loopback en puerto 9, que rechaza todas las conexiones.
    """
    scheme = urllib.parse.urlsplit(request.full_url).scheme.lower()
    proxy = urllib.request.getproxies().get(scheme) or urllib.request.getproxies().get("all")
    if proxy:
        parsed = urllib.parse.urlsplit(proxy if "://" in proxy else "//" + proxy)
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def _normalize(word: str) -> str:
    return _strip_accents(word).lower()


def _clean_word(word: str) -> str:
    return word.strip(PUNCT).strip()


def _stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_STEM:
            return word[: len(word) - len(suffix)]
    return word


def _affixes(word: str):
    start = 0
    while start < len(word) and word[start] in PUNCT:
        start += 1
    end = len(word)
    while end > start and word[end - 1] in PUNCT:
        end -= 1
    return word[:start], word[start:end], word[end:]


def _candidates(word: str):
    base = _normalize(word)
    out = [base]
    if base.endswith("es") and len(base) > 4:
        out.append(base[:-2])
    if base.endswith("s") and len(base) > 3:
        out.append(base[:-1])
    for candidate in list(out):
        stem = _stem(candidate)
        if stem not in out:
            out.append(stem)
    return out


_INDEXES: Dict[str, Dict[str, str]] = {}
_REVERSE_INDEXES: Dict[str, Dict[str, str]] = {}


def _reverse_index(source: str) -> Dict[str, str]:
    """Índice invertido: término de la lengua originaria → castellano.

    Lo usa la dirección estudiante → docente del aula: el estudiante escribe en
    su lengua y el docente necesita leer castellano.
    """
    if source not in _REVERSE_INDEXES:
        index: Dict[str, str] = {}
        for spanish, translated in LEXICON.get(source, {}).items():
            if not translated:
                continue
            key = _normalize(translated)
            index.setdefault(key, spanish)
            stem = _stem(key)
            if stem != key:
                index.setdefault(stem, spanish)
        _REVERSE_INDEXES[source] = index
    return _REVERSE_INDEXES[source]


def _index(target: str) -> Dict[str, str]:
    if target not in _INDEXES:
        index: Dict[str, str] = {}
        for spanish, translated in LEXICON.get(target, {}).items():
            if not translated:
                continue
            key = _normalize(spanish)
            index.setdefault(key, translated)
            stem = _stem(key)
            if stem != key:
                index.setdefault(stem, translated)
        _INDEXES[target] = index
    return _INDEXES[target]


# =================================================================== engine 1
class _GoogleEngine:
    """Motor primario: Google Translate por endpoint público + back-off.

    Variables de entorno:
      - ``GOOGLE_BACKOFF`` (default ``1.2``)
      - ``GOOGLE_MAX_RETRIES`` (default ``2``)
      - ``GOOGLE_TIMEOUT`` (default ``8`` seconds per attempt)
      - ``GOOGLE_THROTTLE_SECONDS`` (default ``1.2``)
    """

    _LAST_CALL_AT = 0.0
    _LOCK_GUARD = threading.RLock()

    def __init__(self, source: str = "es", target: str = GOOGLE_QH_CODE):
        self._source = source
        self._target = target
        self._max_retries = max(1, int(os.environ.get("GOOGLE_MAX_RETRIES", "2")))
        self._backoff = float(os.environ.get("GOOGLE_BACKOFF", "1.2"))
        self._throttle = float(os.environ.get("GOOGLE_THROTTLE_SECONDS", "1.2"))
        self._timeout = max(1.0, float(os.environ.get("GOOGLE_TIMEOUT", "8")))

    def _throttle_wait(self) -> None:
        with _GoogleEngine._LOCK_GUARD:
            now = time.monotonic()
            gap = self._throttle - (now - _GoogleEngine._LAST_CALL_AT)
            if gap > 0:
                time.sleep(gap)
            _GoogleEngine._LAST_CALL_AT = time.monotonic()

    @staticmethod
    def _call(text: str, source: str, target: str, timeout: float = 8) -> str:
        params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            },
            method="GET",
        )
        with _open_translation_url(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        chunks = data[0] if isinstance(data, list) and data else []
        out = "".join(seg[0] for seg in chunks if seg and isinstance(seg[0], str))
        if not out.strip():
            raise RuntimeError("Google devolvió respuesta vacía")
        return out

    def translate(self, text: str) -> TranslationResult:
        start = time.monotonic()
        last_error: Optional[str] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._throttle_wait()
                translated = self._call(text, self._source, self._target, self._timeout)
                return TranslationResult(
                    text=translated.strip(),
                    provider="google-translate",
                    degraded=False,
                    engine="google",
                    engine_code=self._target,
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
            except urllib.error.HTTPError as exc:
                last_error = f"HTTPError {exc.code}: {exc.reason}"
                logger.warning("Google intento %s -> %s", attempt, last_error)
                if exc.code in (429, 503) and attempt < self._max_retries:
                    sleep = self._backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.4)
                    time.sleep(sleep)
                    continue
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Google intento %s -> %s", attempt, last_error)
                if attempt < self._max_retries:
                    sleep = self._backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.4)
                    time.sleep(sleep)
                    continue
                break
        return TranslationResult(
            text="",
            provider="google-translate",
            degraded=True,
            engine="google",
            engine_code=self._target,
            latency_ms=int((time.monotonic() - start) * 1000),
            error=last_error or "GoogleTranslator no respondió",
        )


# =================================================================== engine 2
def _hf_inference_translate(text: str, src: str, tgt: str) -> Optional[str]:
    """Inference API de Hugging Face (modelo NLLB-200-distilled-600M)."""
    url = os.environ.get("HF_API_URL", "").strip()
    token = os.environ.get("HF_API_TOKEN", "").strip()
    if not url or not token:
        return None
    body = json.dumps(
        {"inputs": text,
         "parameters": {"src_lang": src, "tgt_lang": tgt}}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with _open_translation_url(request, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if isinstance(payload, list) and payload:
        item = payload[0]
        if isinstance(item, dict):
            return str(item.get("translation_text") or item.get("generated_text") or "").strip()
    if isinstance(payload, dict):
        return str(payload.get("translation_text") or payload.get("generated_text") or "").strip()
    return None


def _generic_nllb_translate(text: str, src: str, tgt: str) -> Optional[str]:
    """Endpoint genérico conservado por compatibilidad con tu configuración previa."""
    url = os.environ.get("NLLB_API_URL", "").strip()
    if not url:
        return None
    timeout = float(os.environ.get("NLLB_TIMEOUT", "8"))
    body = json.dumps(
        {"source": src, "target": tgt, "text": text,
         "model": "nllb-200-distilled-600M"}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with _open_translation_url(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if isinstance(payload, dict):
        for key in ("translation", "text", "output", "translated_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _nllb_translate(text: str, src: str, tgt: str) -> TranslationResult:
    start = time.monotonic()
    out = _hf_inference_translate(text, src, tgt) or _generic_nllb_translate(text, src, tgt)
    latency = int((time.monotonic() - start) * 1000)
    if out:
        return TranslationResult(
            text=out, provider="nllb-200-api", degraded=False,
            engine="nllb", engine_code=tgt, latency_ms=latency,
        )
    return TranslationResult(
        text="", provider="nllb-200-api", degraded=True,
        engine="nllb", engine_code=tgt, latency_ms=latency,
        error="NLLB no disponible (sin HF_API_URL/TOKEN ni NLLB_API_URL)",
    )


# =================================================================== engine 3
def fallback_translate(text: str, src: str, tgt: str) -> TranslationResult:
    """Glosa término a término con el léxico embebido.

    En la dirección estudiante → docente (``tgt == "spa_Latn"``) se usa el
    índice invertido del léxico de ``src``.
    """
    reverse = tgt == "spa_Latn" and src != "spa_Latn"
    index = _reverse_index(src) if reverse else _index(tgt)
    working_text = text or ""
    # El respaldo palabra por palabra rompía términos compuestos: por ejemplo,
    # traducía "yachay wasi" como "saber casa" aunque el glosario conoce
    # la expresión completa como "escuela". Sustituye primero las frases más
    # largas y luego procesa las palabras restantes con la lógica existente.
    if reverse:
        phrases = sorted(
            (
                (str(translated), str(spanish))
                for spanish, translated in LEXICON.get(src, {}).items()
                if translated and re.search(r"\s", str(translated).strip())
            ),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
        for source_phrase, spanish_phrase in phrases:
            pattern = r"(?<!\w)" + r"\s+".join(
                re.escape(part) for part in source_phrase.split()
            ) + r"(?!\w)"

            def replace_phrase(match, replacement=spanish_phrase):
                if match.group(0)[:1].isupper():
                    return replacement[:1].upper() + replacement[1:]
                return replacement

            working_text = re.sub(pattern, replace_phrase, working_text, flags=re.IGNORECASE)
    output: List[str] = []
    hits: List[str] = []
    misses: List[str] = []
    grammar: List[str] = []
    for word in working_text.split():
        prefix, core, suffix = _affixes(word)
        clean = _clean_word(word)
        translated = None
        if core:
            for candidate in _candidates(core):
                if candidate in index:
                    translated = index[candidate]
                    break
        if translated:
            if core[:1].isupper():
                translated = translated[:1].upper() + translated[1:]
            output.append(prefix + translated + suffix)
            hits.append(clean)
            continue
        output.append(word)
        if not (clean and clean.isalpha()):
            continue
        if _normalize(clean) in GRAMMAR_WORDS:
            grammar.append(clean)
        else:
            misses.append(clean)
    total = len(hits) + len(misses)
    coverage = round(100.0 * len(hits) / total, 1) if total else 0.0
    return TranslationResult(
        text=" ".join(output),
        provider="lexico-embebido-inverso" if reverse else "lexico-embebido",
        degraded=True,
        engine="lexicon",
        engine_code=tgt,
        hits=hits,
        misses=misses,
        grammar_kept=len(grammar),
        coverage=coverage,
        lexicon_size=len(LEXICON.get(src if reverse else tgt, {})),
    )


# =================================================================== dispatcher


def google_code_for(code: str) -> str:
    """Código ISO de Google Translate para un código FLORES de la interfaz.

    El mapa vive en ``core.seed.LANGUAGES`` (campo ``google``): añadir una
    lengua al catálogo la habilita también en el motor primario, sin tocar
    este archivo. Si la lengua no declara código se usa su familia ISO
    (``eng_Latn`` → ``en``).
    """
    if not code:
        return "es"
    if code in GOOGLE_CODE:
        return GOOGLE_CODE[code]
    return code.split("_")[0].lower()


def _resolve_target_codes(tgt: str) -> tuple[str, str]:
    """Compatibilidad: (código Google de destino, código NLLB de destino)."""
    return google_code_for(tgt), tgt


def translate(
    text: str,
    src: str = "spa_Latn",
    tgt: str = "quy_Latn",
    *,
    prefer_engine: Optional[str] = None,
    use_lexicon: bool = True,
) -> dict:
    """Punto de entrada público. Preserva la firma original.

    ``prefer_engine``: ``"google"``, ``"nllb"`` o ``None`` (cascada automática).
    ``use_lexicon``: si ``True`` y el motor preferido falla, baja al lexicón.
    """
    text = (text or "").strip()
    if not text:
        return {
            "text": "", "provider": "noop", "degraded": True,
            "engine": "none", "engineCode": "",
            "hits": [], "untranslated": [], "grammarKept": 0,
            "coverage": 0.0, "lexiconSize": 0, "latencyMs": 0,
            "cached": False, "error": None,
        }

    cache_key = f"{src}|{tgt}|{prefer_engine or 'auto'}|{text}"
    with _LOCK:
        if cache_key in _CACHE:
            cached = dict(_CACHE[cache_key])
            # Una salida del léxico es un respaldo incompleto. No la reutilices
            # como caché definitiva: al reintentar, vuelve a consultar Google o
            # NLLB por si el motor ya está disponible.
            if cached.get("engine") != "lexicon" or prefer_engine == "lexicon":
                cached["cached"] = True
                return cached

    google_src, nllb_code = google_code_for(src), tgt
    google_tgt = google_code_for(tgt)
    if prefer_engine is None:
        # Google soporta castellano y quechua (código qu) en ambas direcciones.
        # Omitirlo en la traducción inversa hacía que el aula dependiera de un
        # endpoint NLLB opcional y, si faltaba, dejaba casi todo el texto igual.
        engines = ["google", "nllb", "lexicon"]
    else:
        engines = [prefer_engine]
        if prefer_engine not in ("lexicon",) and use_lexicon:
            engines.append("lexicon")

    chosen: Optional[TranslationResult] = None
    for name in engines:
        if name == "google":
            # El motor se instancia por llamada para poder combinar cualquier
            # par de lenguas del catálogo (el estado de throttling sí es global).
            chosen = _GoogleEngine(google_src, google_tgt).translate(text)
        elif name == "nllb":
            chosen = _nllb_translate(text, src, nllb_code)
        elif name == "lexicon":
            chosen = fallback_translate(text, src, tgt)
        else:
            continue
        if chosen and chosen.text.strip():
            break

    if chosen is None or not chosen.text.strip():
        chosen = fallback_translate(text, src, tgt)

    result = chosen.as_dict()
    result["cached"] = False
    with _LOCK:
        _CACHE[cache_key] = result
    return dict(result)


def engine_status() -> dict:
    """Diagnóstico para Admin / Audit."""
    status = {
        "google": {
            "available": True, "code": GOOGLE_QH_CODE,
            "cost": "free+rate-limit", "engine": "translate_a/single (gtx)",
            "languages": len(GOOGLE_CODE),
        },
        "nllb": {
            "available": bool(os.environ.get("HF_API_URL") or os.environ.get("NLLB_API_URL")),
            "code": NLLB_QY_CODE,
            "cost": "free tier HF o self-hosted",
        },
        "lexicon": {
            "available": True, "code": "internal-fallback", "cost": "free (offline)",
            "entries": sum(len(v) for v in LEXICON.values()),
        },
    }
    try:
        import transformers  # noqa: F401
        status["nllb"]["localModel"] = "facebook/nllb-200-distilled-600M"
    except ImportError:
        status["nllb"]["localModel"] = None
    return status


def cache_stats() -> dict:
    with _LOCK:
        return {"entries": len(_CACHE), "keys": list(_CACHE.keys())[-5:]}


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def known_terms(target: str) -> Iterable[str]:
    return tuple(LEXICON.get(target, {}).keys())
