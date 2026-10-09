# Ayllu · núcleo v5 · mensajería docente ↔ estudiante (texto, documentos y traducción)
"""Ayllu · servicio de mensajería del aula.

Módulo que añade el **apartado de mensajería** al núcleo v4: conversaciones
(``threads``) donde el docente y el estudiante intercambian en las dos
direcciones mensajes de texto y documentos (``.pdf`` / ``.txt``), y donde
**cualquiera de los dos roles puede traducir cada mensaje** a cualquier lengua
del catálogo con el botón «Traducir» (con selector de lengua).

Reglas de honestidad heredadas del núcleo:

- El texto que escribió una persona **nunca se modifica**: queda intacto en
  ``srcText`` y la traducción que lee el destinatario en ``outText``.
- La traducción usa la cascada de ``translator.translate`` (Google → NLLB →
  léxico embebido) y declara ``degraded`` cuando no hay motor conectado.
- Los adjuntos se validan con :mod:`core.docscanner` (extensión, bytes mágicos
  y tamaño máximo) y **no se escriben en disco**: viajan en memoria dentro de la
  fila codificados en base64 y se descargan por su propio endpoint.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict, List, Optional, Tuple

import cultural_adapter
import evaluator
import translator
from core import auth, docscanner
from core.db import get_store
from core.seed import LANG_NAME, LANGUAGES, LEVELS, now_iso  # LEVELS vive en seed.py

# Tope del texto de un adjunto que se traduce (el original completo sí se guarda).
TRANSLATE_CHARS = 4000
# Tope del texto extraído que se conserva en la fila del mensaje.
STORED_TEXT_CHARS = 8000


class MessagingError(ValueError):
    """Error de mensajería con mensaje listo para mostrar y código HTTP."""

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
# utilidades de cuentas
# --------------------------------------------------------------------------- #


def account(user_id: Any = None, email: str = "") -> Optional[Dict[str, Any]]:
    """Cuenta de la semilla por ``userId`` (posición 1..n) o por correo."""
    from core import seed

    if email:
        low = str(email).strip().lower()
        for index, row in enumerate(seed.USERS, start=1):
            if str(row.get("email", "")).lower() == low:
                return dict(row, userId=index)
        return None
    for index, row in enumerate(seed.USERS, start=1):
        if str(index) == str(user_id):
            return dict(row, userId=index)
    return None


def public_account(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not record:
        return None
    code = record.get("langCode")
    return {
        "userId": record.get("userId"),
        "email": record.get("email"),
        "name": record.get("name"),
        "role": record.get("role"),
        "jobTitle": record.get("jobTitle"),
        "langCode": code,
        "langName": LANG_NAME.get(code, code),
        "communityId": record.get("communityId"),
    }


def known_codes() -> List[str]:
    return [str(row.get("code")) for row in LANGUAGES]


def lang_name(code: str) -> str:
    return LANG_NAME.get(code, code)


# --------------------------------------------------------------------------- #
# traducción de una entrega
# --------------------------------------------------------------------------- #


def translate_for_delivery(
    text: str,
    src: str,
    tgt: str,
    level: str,
    glossary_rows: List[dict],
) -> Dict[str, Any]:
    """Traduce y glosa un texto con la misma cascada que usa el aula."""
    text = (text or "").strip()
    if not text:
        return {
            "text": "",
            "provider": "noop",
            "degraded": True,
            "engine": "none",
            "coverage": 0.0,
            "chrF2": 0.0,
            "glossary": [],
        }
    raw = translator.translate(text, src, tgt)
    raw_text = raw.get("text") or ""
    reverse = tgt == "spa_Latn" and src != "spa_Latn"
    if reverse:
        # Lengua originaria → castellano: conserva la salida del motor inverso
        # sin aplicar el adaptador de vocabulario castellano → lengua meta.
        out_text = raw_text
        glossed: Dict[str, Any] = {"glossary": []}
    else:
        glossed = cultural_adapter.gloss(raw_text, tgt, glossary_rows, level) or {}
        out_text = glossed.get("text") or raw_text
    scores = evaluator.score_pair(out_text, raw_text)
    return {
        "text": out_text,
        "provider": raw.get("provider"),
        "degraded": bool(raw.get("degraded")),
        "engine": raw.get("engine"),
        "coverage": raw.get("coverage"),
        "chrF2": scores.get("chrF2", 0.0),
        "glossary": glossed.get("glossary") or [],
    }


# --------------------------------------------------------------------------- #
# servicio
# --------------------------------------------------------------------------- #


class MessagingService:
    """Conversaciones, mensajes, adjuntos y traducción bajo demanda."""

    def __init__(self, store=None) -> None:
        self._store = store

    @property
    def store(self):
        """Almacén activo (se resuelve en cada llamada: el reset lo reemplaza)."""
        return self._store or get_store()

    # -- lectura ------------------------------------------------------------

    def directory(self) -> List[dict]:
        """Directorio de cuentas para elegir destinatario (docente y estudiante)."""
        return [row for row in auth.public_users() if row.get("role")]

    def get_thread(self, thread_id: Any) -> Optional[dict]:
        row = self.store.get("threads", thread_id)
        if not row:
            return None
        row["participants"] = [int(p) for p in (row.get("participants") or [])]
        return row

    def _is_member(self, thread: dict, user_id: Any) -> bool:
        return str(user_id) in [str(p) for p in (thread.get("participants") or [])]

    def _thread_messages(self, thread_id: Any) -> List[dict]:
        rows = self.store.select("messages", {"threadId": thread_id})
        rows.sort(key=lambda row: str(row.get("createdAt") or ""))
        return rows

    @staticmethod
    def _is_unread(row: dict, user_id: Any) -> bool:
        if str(row.get("fromUserId")) == str(user_id):
            return False
        read_by = [str(x) for x in (row.get("readBy") or [])]
        return str(user_id) not in read_by

    def list_threads(self, user_id: Any = None) -> List[dict]:
        """Conversaciones en las que participa ``user_id``, con no leídos."""
        out: List[dict] = []
        for row in self.store.select("threads"):
            parts = [int(p) for p in (row.get("participants") or [])]
            if user_id not in (None, "", 0, "0") and str(user_id) not in [str(p) for p in parts]:
                continue
            messages = self._thread_messages(row.get("id"))
            unread = sum(1 for m in messages if self._is_unread(m, user_id))
            last = messages[-1] if messages else None
            members = [public_account(account(pid)) for pid in parts]
            out.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title") or "Conversación",
                    "type": row.get("type") or ("group" if len(parts) > 2 else "direct"),
                    "createdBy": row.get("createdBy"),
                    "createdByName": (account(row.get("createdBy")) or {}).get("name"),
                    "participants": parts,
                    "members": [m for m in members if m],
                    "communityId": row.get("communityId"),
                    "createdAt": row.get("createdAt"),
                    "messageCount": len(messages),
                    "unread": unread,
                    "lastAt": (last or {}).get("createdAt") or row.get("createdAt"),
                    "lastFrom": (last or {}).get("fromName"),
                    "lastPreview": str((last or {}).get("srcText") or (last or {}).get("title") or "")[:90],
                    "lastKind": (last or {}).get("kind"),
                }
            )
        out.sort(key=lambda item: str(item.get("lastAt") or ""), reverse=True)
        return out

    def unread(self, user_id: Any) -> Dict[str, Any]:
        by_thread: Dict[str, int] = {}
        total = 0
        for thread in self.list_threads(user_id):
            by_thread[str(thread["id"])] = thread["unread"]
            total += thread["unread"]
        return {"userId": user_id, "total": total, "byThread": by_thread}

    @staticmethod
    def public_message(row: Dict[str, Any]) -> Dict[str, Any]:
        """Fila de mensaje lista para JSON: el adjunto viaja sin bytes."""
        clean = dict(row)
        attachment = clean.get("attachment")
        if isinstance(attachment, dict):
            clean["attachment"] = {
                key: value for key, value in attachment.items() if key != "b64"
            }
        return clean

    def list_messages(
        self, thread_id: Any, user_id: Any = None, limit: int = 200
    ) -> List[dict]:
        thread = self.get_thread(thread_id)
        if not thread:
            raise MessagingError("conversación no encontrada", 404)
        if user_id not in (None, "", 0, "0") and not self._is_member(thread, user_id):
            raise MessagingError("no participas en esta conversación", 403)
        rows = self._thread_messages(thread_id)
        rows = rows[-int(limit):] if limit else rows
        return [self.public_message(row) for row in rows]

    # -- escritura ----------------------------------------------------------

    def create_thread(self, payload: Dict[str, Any]) -> dict:
        """Crea una conversación docente → estudiante (o grupal)."""
        sender = account(payload.get("fromUserId"), str(payload.get("fromEmail") or ""))
        if not sender:
            raise MessagingError("remitente desconocido")

        raw_targets = payload.get("toUserIds") or payload.get("participants") or []
        if isinstance(raw_targets, (str, int)):
            raw_targets = [raw_targets]
        targets = []
        for item in raw_targets:
            record = account(item)
            if record and str(record["userId"]) not in [str(p) for p in targets]:
                targets.append(record["userId"])
        if not targets:
            raise MessagingError("elige al menos un destinatario")

        is_group = bool(payload.get("group")) or len(targets) > 1
        if is_group and sender.get("role") != "docente":
            raise MessagingError("sólo el docente puede abrir una conversación grupal", 403)

        participants = [sender["userId"]] + targets
        recipients = [public_account(account(pid)) for pid in targets]
        title = str(payload.get("title") or "").strip()
        if not title:
            title = (
                "Avisos para toda el aula"
                if is_group
                else "Conversación con %s" % ", ".join(
                    str((r or {}).get("name") or "") for r in recipients
                )
            )
        row = self.store.insert(
            "threads",
            {
                "title": title[:120],
                "type": "group" if is_group else "direct",
                "createdBy": sender["userId"],
                "createdByName": sender.get("name"),
                "participants": participants,
                "communityId": sender.get("communityId"),
                "createdAt": now_iso(),
            },
        )
        self.store.insert(
            "events",
            {
                "kind": "conversacion",
                "langCode": sender.get("langCode"),
                "snippet": title[:120],
                "chrF2": 0.0,
                "actor": sender.get("email") or "api",
                "ts": now_iso(),
            },
        )
        return self.get_thread(row["id"]) or row

    def _default_target(self, thread: dict, sender: Dict[str, Any], explicit: str = "") -> str:
        code = str(explicit or "").strip()
        if code:
            if code not in known_codes():
                raise MessagingError("lengua de destino desconocida: %s" % code)
            return code
        for pid in thread.get("participants") or []:
            member = account(pid)
            if member and str(pid) != str(sender["userId"]):
                return str(member.get("langCode") or "spa_Latn")
        return "spa_Latn"

    def _save(
        self,
        thread: dict,
        sender: Dict[str, Any],
        *,
        text: str,
        level: str,
        kind: str,
        title: str,
        targets: List[str],
        src: str = "",
        attachment: Optional[dict] = None,
    ) -> dict:
        """Traduce a cada lengua pedida y guarda una sola fila de mensaje."""
        level = level if level in LEVELS else "básico"
        src_code = str(src or sender.get("langCode") or "spa_Latn")
        if src_code not in known_codes():
            raise MessagingError("elige una lengua de origen válida")
        glossary_rows = self.store.select("glossary")
        translations: Dict[str, Any] = {}
        first_tgt = ""
        for tgt in targets:
            result = translate_for_delivery(text, src_code, tgt, level, glossary_rows)
            translations[tgt] = result
            if not first_tgt:
                first_tgt = tgt
        first = translations.get(first_tgt) or {}
        notes = [
            "Mensajería: el texto original de %s se conserva intacto en «srcText»."
            % sender.get("name")
        ]
        if attachment:
            notes.append(
                "Documento adjunto «%s» validado (%s): el archivo se guarda en memoria y se "
                "descarga desde el propio mensaje." % (attachment.get("name"), attachment.get("sizeLabel"))
            )
        if first and first.get("degraded"):
            notes.append(
                "Traducción marcada como glosa de vocabulario: requiere revisión de un hablante "
                "nativo antes de usarse en aula."
            )
        row = self.store.insert(
            "messages",
            {
                "threadId": thread.get("id"),
                "fromUserId": sender["userId"],
                "toUserId": None,
                "fromRole": sender.get("role"),
                "toRole": "grupo" if thread.get("type") == "group" else "contraparte",
                "fromName": sender.get("name"),
                "toName": thread.get("title") if thread.get("type") == "group" else ", ".join(
                    str((public_account(account(pid)) or {}).get("name") or "")
                    for pid in (thread.get("participants") or [])
                    if str(pid) != str(sender["userId"])
                ),
                "studentName": sender.get("studentName") or sender.get("name"),
                "kind": kind,
                "title": title,
                "src": src_code,
                "tgt": first_tgt,
                "srcText": text,
                "outText": first.get("text") or "",
                "originEs": "",
                "provider": first.get("provider"),
                "engine": first.get("engine"),
                "degraded": bool(first.get("degraded")),
                "coverage": first.get("coverage"),
                "chrF2": first.get("chrF2") or 0.0,
                "glossary": first.get("glossary") or [],
                "notes": notes,
                "translations": translations,
                "attachment": attachment,
                "readBy": [sender["userId"]],
                "createdAt": now_iso(),
                "readAt": None,
            },
        )
        self.store.insert(
            "events",
            {
                "kind": "mensaje",
                "langCode": first_tgt,
                "snippet": text[:120],
                "chrF2": first.get("chrF2") or 0.0,
                "actor": sender.get("email") or "api",
                "ts": now_iso(),
            },
        )
        return self.public_message(row)

    def send_message(self, thread_id: Any, payload: Dict[str, Any]) -> dict:
        """Mensaje de texto: se traduce a la lengua elegida (o a la del otro)."""
        thread = self.get_thread(thread_id)
        if not thread:
            raise MessagingError("conversación no encontrada", 404)
        sender = account(payload.get("fromUserId"), str(payload.get("fromEmail") or ""))
        if not sender:
            raise MessagingError("remitente desconocido")
        if not self._is_member(thread, sender["userId"]):
            raise MessagingError("no participas en esta conversación", 403)
        text = str(payload.get("text") or "").strip()
        if not text:
            raise MessagingError("el mensaje está vacío")
        src = str(payload.get("src") or sender.get("langCode") or "spa_Latn").strip()
        if src not in known_codes():
            raise MessagingError("elige una lengua de origen válida")
        requested_tgt = str(payload.get("tgt") or "").strip()
        if thread.get("type") == "group" and requested_tgt == "auto":
            # En grupos, una entrega automática debe servir a cada participante
            # en su lengua de perfil, no solo en la del primer miembro.
            targets = []
            for user_id in [sender["userId"]] + (thread.get("participants") or []):
                member = account(user_id)
                code = str((member or {}).get("langCode") or "spa_Latn")
                if code not in targets:
                    targets.append(code)
        else:
            targets = [self._default_target(thread, sender, requested_tgt)]
        return self._save(
            thread,
            sender,
            text=text[:STORED_TEXT_CHARS],
            level=str(payload.get("level") or "básico"),
            kind="material" if str(payload.get("kind")) == "material" else "mensaje",
            title=str(payload.get("title") or "").strip()[:120],
            src=src,
            targets=targets,
        )

    def send_attachment(
        self,
        thread_id: Any,
        payload: Dict[str, Any],
        filename: str,
        data: bytes,
    ) -> dict:
        """Documento adjunto: valida, extrae el texto y lo entrega traducido."""
        thread = self.get_thread(thread_id)
        if not thread:
            raise MessagingError("conversación no encontrada", 404)
        sender = account(payload.get("fromUserId"), str(payload.get("fromEmail") or ""))
        if not sender:
            raise MessagingError("remitente desconocido")
        if not self._is_member(thread, sender["userId"]):
            raise MessagingError("no participas en esta conversación", 403)

        try:
            scanned = docscanner.inspect(filename, data, "")
        except docscanner.ScanError as error:
            raise MessagingError(error.message, error.code, error.hint)

        text = str(scanned.get("text") or "").strip()
        if not text:
            raise MessagingError(
                "El documento no tiene texto extraíble: un PDF escaneado requiere OCR.", 415
            )

        raw_targets = payload.get("targets") or []
        src = str(payload.get("src") or sender.get("langCode") or "spa_Latn").strip()
        if src not in known_codes():
            raise MessagingError("elige una lengua de origen válida")
        if isinstance(raw_targets, str):
            raw_targets = [item for item in raw_targets.replace(";", ",").split(",") if item.strip()]
        codes = [str(item).strip() for item in raw_targets if str(item).strip()]
        if thread.get("type") == "group" and codes == ["auto"]:
            codes = []
            for user_id in [sender["userId"]] + (thread.get("participants") or []):
                member = account(user_id)
                code = str((member or {}).get("langCode") or "spa_Latn")
                if code not in codes:
                    codes.append(code)
        if not codes:
            codes = [self._default_target(thread, sender)]
        for code in codes:
            if code not in known_codes():
                raise MessagingError("lengua de destino desconocida: %s" % code)

        attachment = {
            "name": scanned.get("name") or filename,
            "ext": scanned.get("ext"),
            "mime": scanned.get("mime") or "application/octet-stream",
            "size": scanned.get("size") or len(data),
            "sizeLabel": scanned.get("sizeLabel"),
            "pages": scanned.get("pages"),
            "chars": scanned.get("chars"),
            "words": scanned.get("words"),
            "sentences": scanned.get("sentences"),
            "sha256": scanned.get("sha256"),
            "textless": bool(scanned.get("textless")),
            "text": text[:STORED_TEXT_CHARS],
            "b64": base64.b64encode(data).decode("ascii"),
        }
        return self._save(
            thread,
            sender,
            text=text[:TRANSLATE_CHARS],
            level=str(payload.get("level") or "básico"),
            kind="documento",
            title=str(payload.get("title") or attachment["name"]).strip()[:120],
            src=src,
            targets=codes[:6],
            attachment=attachment,
        )

    def translate_message(self, message_id: Any, payload: Dict[str, Any]) -> dict:
        """Botón «Traducir»: traduce un mensaje a la lengua pedida y la cachea."""
        row = self.store.get("messages", message_id)
        if not row:
            raise MessagingError("mensaje no encontrado", 404)
        thread = self.get_thread(row.get("threadId"))
        if not thread:
            raise MessagingError("la conversación del mensaje no existe", 404)
        user_id = payload.get("userId")
        if user_id not in (None, "", 0, "0") and not self._is_member(thread, user_id):
            raise MessagingError("no participas en esta conversación", 403)

        tgt = str(payload.get("tgt") or "").strip()
        if tgt not in known_codes():
            raise MessagingError("elige una lengua de destino válida")
        level = str(payload.get("level") or "básico")
        if level not in LEVELS:
            level = "básico"

        src = str(row.get("src") or "spa_Latn")
        attachment = row.get("attachment") or {}
        source_text = str(attachment.get("text") or row.get("srcText") or "").strip()
        if not source_text:
            raise MessagingError("el mensaje no tiene texto que traducir")

        cached = (row.get("translations") or {}).get(tgt)
        # Las glosas del respaldo pueden ser casi idénticas al original. No las
        # tratamos como una traducción definitiva: al volver a pedirla,
        # intentamos Google/NLLB con la cascada vigente antes de repetirlas.
        cached_is_lexicon = (cached or {}).get("engine") == "lexicon"
        if cached and cached.get("text") and not cached_is_lexicon:
            return dict(cached, messageId=message_id, tgt=tgt, cached=True)

        result = translate_for_delivery(
            source_text[:TRANSLATE_CHARS], src, tgt, level, self.store.select("glossary")
        )
        result["level"] = level
        translations = dict(row.get("translations") or {})
        translations[tgt] = result
        self.store.update("messages", message_id, {"translations": translations})
        return dict(result, messageId=message_id, tgt=tgt, cached=False)

    # -- lectura / adjuntos -------------------------------------------------

    def mark_read(self, message_id: Any, user_id: Any) -> Optional[dict]:
        row = self.store.get("messages", message_id)
        if not row:
            return None
        thread = self.get_thread(row.get("threadId"))
        if not thread or not self._is_member(thread, user_id):
            raise MessagingError("no participas en esta conversación", 403)
        read_by = [str(x) for x in (row.get("readBy") or [])]
        if str(user_id) not in read_by:
            read_by.append(str(user_id))
        updated = self.store.update(
            "messages", message_id, {"readBy": read_by, "readAt": now_iso()}
        )
        return self.public_message(updated) if updated else None

    def mark_thread_read(self, thread_id: Any, user_id: Any) -> Dict[str, Any]:
        thread = self.get_thread(thread_id)
        if not thread:
            raise MessagingError("conversación no encontrada", 404)
        if not self._is_member(thread, user_id):
            raise MessagingError("no participas en esta conversación", 403)
        marked = 0
        for row in self._thread_messages(thread_id):
            if self._is_unread(row, user_id):
                self.mark_read(row.get("id"), user_id)
                marked += 1
        return {"threadId": thread_id, "marked": marked, "unread": self.unread(user_id)}

    def attachment_bytes(self, message_id: Any) -> Tuple[bytes, str, str]:
        row = self.store.get("messages", message_id)
        if not row:
            raise MessagingError("mensaje no encontrado", 404)
        attachment = row.get("attachment") or {}
        encoded = attachment.get("b64")
        if not encoded:
            raise MessagingError("este mensaje no tiene un documento adjunto", 404)
        try:
            data = base64.b64decode(encoded)
        except (binascii.Error, ValueError):
            raise MessagingError("el adjunto está dañado", 500)
        return data, attachment.get("mime") or "application/octet-stream", attachment.get("name") or "documento"


_SERVICE: Optional[MessagingService] = None


def get_messaging() -> MessagingService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MessagingService()
    return _SERVICE


def reset_messaging() -> None:
    global _SERVICE
    _SERVICE = None


# --------------------------------------------------------------------------- #
# API de módulo: la usan ``app.py`` y el self-test. Cada llamada resuelve el
# servicio del proceso actual, de modo que ``/api/admin/reset`` lo reconstruye.
# --------------------------------------------------------------------------- #


def directory() -> List[dict]:
    return get_messaging().directory()


def list_threads(user_id: Any = None) -> List[dict]:
    return get_messaging().list_threads(user_id)


def create_thread(payload: Dict[str, Any]) -> dict:
    return get_messaging().create_thread(payload)


def unread(user_id: Any) -> Dict[str, Any]:
    return get_messaging().unread(user_id)


def list_messages(thread_id: Any, user_id: Any = None, limit: int = 200) -> List[dict]:
    return get_messaging().list_messages(thread_id, user_id, limit)


def send_message(thread_id: Any, payload: Dict[str, Any]) -> dict:
    return get_messaging().send_message(thread_id, payload)


def send_attachment(
    thread_id: Any, payload: Dict[str, Any], filename: str, data: bytes
) -> dict:
    return get_messaging().send_attachment(thread_id, payload, filename, data)


def translate_message(message_id: Any, payload: Dict[str, Any]) -> dict:
    return get_messaging().translate_message(message_id, payload)


def mark_read(message_id: Any, user_id: Any) -> Optional[dict]:
    return get_messaging().mark_read(message_id, user_id)


def mark_thread_read(thread_id: Any, user_id: Any) -> Dict[str, Any]:
    return get_messaging().mark_thread_read(thread_id, user_id)


def attachment_bytes(message_id: Any) -> Tuple[bytes, str, str]:
    return get_messaging().attachment_bytes(message_id)
