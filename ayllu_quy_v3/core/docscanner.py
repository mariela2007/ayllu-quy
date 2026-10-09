# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Ayllu · escáner de documentos (PDF con capa de texto y TXT).

Extrae el texto de un archivo que wichay el docente para alimentar el
Adaptador cultural. Reglas duras:

- Sólo se aceptan ``.pdf`` y ``.txt``. Se comprueba **la extensión y el
  contenido real** (bytes mágicos ``%PDF-`` en PDF; texto imprimible en
  TXT). Cualquier otro formato se rechaza con un mensaje en español.
- Límite de tamaño configurable con ``AYLLU_MAX_UPLOAD_MB`` (8 MB).
- Los PDF **escaneados** (sin capa de texto) devuelven 0 caracteres: se
  avisa explícitamente de que ruway falta OCR, nunca se falla en silencio.
- El texto se trunca a ``MAX_CHARS`` y el truncado se declara en ``notes``.

El módulo no guarda nada: devuelve el resultado y la capa superior decide
(sesión, biblioteca, adaptador).
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logging.getLogger("pypdf").setLevel(logging.ERROR)

MAX_BYTES = int(float(os.environ.get("AYLLU_MAX_UPLOAD_MB", "8")) * 1024 * 1024)
MAX_CHARS = 400_000
PREVIEW_CHARS = 900
ALLOWED_EXT = (".pdf", ".txt")
PDF_MAGIC = b"%PDF-"
MIME_BY_EXT = {".pdf": "application/pdf", ".txt": "text/plain"}

BINARY_EXT_HINT = (
    ".doc, .docx, .odt, .rtf, .xls, .xlsx, .ppt, .pptx, .zip, .rar, .7z, "
    ".png, .jpg, .jpeg, .webp, .gif, .mp3, .mp4, .csv, .json"
)

SPANISH_STOPWORDS = {
    "de", "la", "el", "que", "y", "en", "los", "las", "un", "una", "con",
    "por", "para", "del", "al", "es", "son", "como", "más", "pero", "sin",
    "sobre", "entre", "cuando", "muy", "ser", "está", "este", "esta", "sus",
}

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ScanError(Exception):
    """Error de escaneo con mensaje listo para mostrar al usuario."""

    def __init__(self, message: str, code: int = 400, hint: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"error": self.message}
        if self.hint:
            payload["hint"] = self.hint
        return payload


# --------------------------------------------------------------------------- #
# utilidades
# --------------------------------------------------------------------------- #


def extension_of(filename: str) -> str:
    """Extensión normalizada ('' si el archivo no tiene)."""
    name = os.path.basename((filename or "").strip())
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def safe_name(filename: str) -> str:
    """Suti base saneado, sin rutas ni caracteres raros."""
    name = os.path.basename((filename or "").strip().replace("\\", "/"))
    name = _CONTROL.sub("", name)
    return re.sub(r"[^\w.\-() áéíóúÁÉÍÓÚñÑ]", "_", name)[:120] or "documento"


def human_size(size: int) -> str:
    size = int(size or 0)
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KB" % (size / 1024.0)
    return "%.2f MB" % (size / (1024.0 * 1024.0))


def _clean_text(text: str) -> str:
    """Normaliza saltos, quita controles y colapsa líneas vacías."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = _CONTROL.sub("", text)
    text = unicodedata.normalize("NFC", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _looks_binary(data: bytes) -> bool:
    """Heurística para un .txt que en realidad es binario."""
    if not data:
        return False
    if b"\x00" in data[:4096]:
        return True
    sample = data[:4096]
    printable = sum(1 for byte in sample if 9 <= byte <= 13 or 32 <= byte <= 126 or byte > 127)
    return (printable / float(len(sample))) < 0.75


def _decode_txt(data: bytes) -> Tuple[str, str, List[str]]:
    """Decodifica TXT: UTF-8 (con BOM) → cp1252 → latin-1. Nunca falla."""
    notes: List[str] = []
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig", ["Se detectó y quitó el BOM UTF-8."]
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding), encoding, notes
        except UnicodeDecodeError:
            continue
    notes.append("No era UTF-8 ni Windows-1252: se leyó como latin-1 (puede haber caracteres raros).")
    return data.decode("latin-1", errors="replace"), "latin-1", notes


def _metrics(text: str) -> Dict[str, Any]:
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9'-]+", text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    word_count = len(words)
    return {
        "chars": len(text),
        "words": word_count,
        "sentences": max(1, len(sentences)) if word_count else 0,
        "paragraphs": len(paragraphs),
        "readingMinutes": round(word_count / 200.0, 1) if word_count else 0.0,
    }


def _lang_hint(text: str) -> str:
    """Pista de idioma por simikuna funcionales del castellano (estimación)."""
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text.lower())[:800]
    if not tokens:
        return "sin texto"
    hits = sum(1 for token in tokens if token in SPANISH_STOPWORDS)
    ratio = hits / float(len(tokens))
    if ratio > 0.12:
        return "probable castellano"
    if ratio > 0.03:
        return "castellano poco probable"
    return "indeterminado"


def _flesch(text: str) -> Optional[float]:
    """Legibilidad Fernández-Huerta reutilizando el evaluador del proyecto."""
    try:
        import evaluator

        return evaluator.flesch_fernandez_huerta(text)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# extractores
# --------------------------------------------------------------------------- #


def _scan_pdf(data: bytes) -> Tuple[str, int, List[str]]:
    """Extrae texto de un PDF con capa de texto. Avisa si está escaneado."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover
        raise ScanError(
            "Falta la librería pypdf en el servidor y no se puede leer el PDF.",
            500,
            "Instala las dependencias: pip install -r requirements.txt",
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ScanError(
                    "El PDF está protegido con contraseña: quita la protección y vuelve a subirlo.",
                    422,
                )
        pages = list(reader.pages)
    except ScanError:
        raise
    except PdfReadError as exc:
        raise ScanError(
            "El archivo tiene cabecera de PDF pero está dañado o incompleto.",
            422,
            "Prueba a exportarlo de nuevo desde tu editor.",
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise ScanError("No se pudo abrir el PDF: %s" % exc, 422) from exc

    chunks: List[str] = []
    empty_pages = 0
    for page in pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if len(text.strip()) < 5:
            empty_pages += 1
        chunks.append(text)

    text = _clean_text("\n\n".join(chunks))
    notes: List[str] = []
    if not text:
        notes.append(
            "El PDF no tiene capa de texto: casi seguro es un documento escaneado (imágenes). "
            "Se necesita OCR para leerlo; no se extrajo nada."
        )
    elif empty_pages:
        notes.append(
            "%d de %d páginas no tenían texto seleccionable (probablemente imágenes)."
            % (empty_pages, len(pages))
        )
    return text, len(pages), notes


def _scan_txt(data: bytes) -> Tuple[str, int, List[str]]:
    """Decodifica un TXT con UTF-8 → cp1252 → latin-1."""
    text, encoding, notes = _decode_txt(data)
    text = _clean_text(text)
    if encoding != "utf-8":
        notes.insert(0, "Codificación detectada: %s." % encoding)
    if not text:
        notes.append("El archivo está vacío o sólo contiene espacios en blanco.")
    return text, 1, notes


# --------------------------------------------------------------------------- #
# API pública del módulo
# --------------------------------------------------------------------------- #


def limits() -> Dict[str, Any]:
    """Límites y tipos aceptados, para que la interfaz los muestre."""
    return {
        "extensions": list(ALLOWED_EXT),
        "mimes": dict(MIME_BY_EXT),
        "maxBytes": MAX_BYTES,
        "maxLabel": human_size(MAX_BYTES),
        "maxChars": MAX_CHARS,
        "previewChars": PREVIEW_CHARS,
        "rejected": BINARY_EXT_HINT,
    }


def inspect(filename: str, data: bytes, mimetype: str = "") -> Dict[str, Any]:
    """Valida y extrae el texto de un documento subido.

    Lanza ``ScanError`` si el tipo, el tamaño o el contenido no son válidos.
    """
    name = safe_name(filename)
    ext = extension_of(name)
    size = len(data or b"")

    if ext not in ALLOWED_EXT:
        raise ScanError(
            "Formato no permitido («%s»). Sólo se aceptan documentos .pdf o .txt." % (ext or "sin extensión"),
            415,
            "Formatos rechazados, entre otros: %s." % BINARY_EXT_HINT,
        )
    if size == 0:
        raise ScanError("El archivo «%s» está vacío." % name, 400)
    if size > MAX_BYTES:
        raise ScanError(
            "El archivo pesa %s y el límite es %s." % (human_size(size), human_size(MAX_BYTES)),
            413,
            "Divide el documento o comprímelo antes de subirlo.",
        )

    if ext == ".pdf":
        if not data.lstrip()[:5].startswith(PDF_MAGIC):
            raise ScanError(
                "«%s» tiene extensión .pdf pero su contenido no es un PDF real." % name,
                415,
                "Si renombraste otro formato (por ejemplo .docx) a .pdf, vuelve a exportarlo como PDF.",
            )
        text, pages, notes = _scan_pdf(data)
    else:
        if _looks_binary(data):
            raise ScanError(
                "«%s» tiene extensión .txt pero su contenido es binario, no texto plano." % name,
                415,
                "Guarda el documento como texto plano (UTF-8) o súbelo en PDF.",
            )
        text, pages, notes = _scan_txt(data)

    truncated = False
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        truncated = True
        notes.append(
            "Texto truncado a %s caracteres (el documento era más largo)." % format(MAX_CHARS, ",")
        )

    metrics = _metrics(text)
    flesch = _flesch(text) if metrics["words"] >= 12 else None
    digest = hashlib.sha256(data).hexdigest()[:16]

    return {
        "ok": True,
        "name": name,
        "ext": ext,
        "mime": mimetype or MIME_BY_EXT.get(ext, "application/octet-stream"),
        "expectedMime": MIME_BY_EXT[ext],
        "size": size,
        "sizeLabel": human_size(size),
        "sha256": digest,
        "pages": pages,
        "chars": metrics["chars"],
        "words": metrics["words"],
        "sentences": metrics["sentences"],
        "paragraphs": metrics["paragraphs"],
        "readingMinutes": metrics["readingMinutes"],
        "flesch": flesch,
        "langHint": _lang_hint(text),
        "truncated": truncated,
        "textless": metrics["chars"] == 0,
        "preview": text[:PREVIEW_CHARS],
        "text": text,
        "notes": notes,
    }
