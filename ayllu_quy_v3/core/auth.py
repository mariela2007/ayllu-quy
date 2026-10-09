# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Autenticación de Ayllu con dos roles: docente y estudiante.

Los usuarios viven en ``core.seed.USERS`` y cada uno declara su ``role`` y su
``langCode``: el docente trabaja en castellano y el estudiante escribe y lee en
su lengua originaria. El token es un JWT HS256 firmado con la biblioteca
estándar (``hmac`` + ``hashlib`` + ``base64``), sin PyJWT.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional

from . import seed as _seed

_DEFAULT_SECRET = "ayllu-demo-secret-cambiar-en-produccion"


def _secret() -> bytes:
    return os.environ.get("AYLLU_SECRET", _DEFAULT_SECRET).encode("utf-8")


def secret_configured() -> bool:
    """Require a non-demo signing secret before protected mode is usable."""
    value = os.environ.get("AYLLU_SECRET", "")
    return len(value) >= 32 and value != _DEFAULT_SECRET


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _password(row: Dict[str, Any]) -> str:
    """Clave de la cuenta; se puede sobreescribir por entorno."""
    if row.get("role") == "docente":
        return str(os.environ.get("AYLLU_DOCENTE_PASSWORD") or row.get("password"))
    return str(os.environ.get("AYLLU_ESTUDIANTE_PASSWORD") or row.get("password"))


def users() -> Dict[str, Dict[str, Any]]:
    """Usuarios indexados por correo. ``userId`` = posición en la semilla."""
    out: Dict[str, Dict[str, Any]] = {}
    for index, row in enumerate(_seed.USERS, start=1):
        record = dict(row)
        record["password"] = _password(row)
        record["userId"] = index
        record["langName"] = _seed.LANG_NAME.get(record.get("langCode"), record.get("langCode"))
        out[record["email"]] = record
    return out


def demo_mode() -> bool:
    """En modo demo (por omisión) el directorio publica las claves de acceso.

    Desactívalo con ``AYLLU_DEMO_LOGIN=0`` cuando la app deje de ser pública.
    """
    return os.environ.get("AYLLU_DEMO_LOGIN", "1") in ("1", "true", "yes")


def profile(record: Dict[str, Any]) -> Dict[str, Any]:
    """Datos públicos de una cuenta: rol, lengua y comunidad."""
    return {
        "userId": record.get("userId"),
        "email": record.get("email"),
        "name": record.get("name"),
        "role": record.get("role"),
        "jobTitle": record.get("jobTitle"),
        "langCode": record.get("langCode"),
        "langName": record.get("langName"),
        "communityId": record.get("communityId"),
        "studentName": record.get("studentName"),
    }


def public_users() -> List[Dict[str, Any]]:
    """Directorio para la pantalla de acceso (login rápido de la sustentación)."""
    rows: List[Dict[str, Any]] = []
    for record in users().values():
        item = profile(record)
        if demo_mode():
            item["password"] = record.get("password")
        rows.append(item)
    return rows


def issue_token(
    subject: str,
    role: str = "estudiante",
    lang: str = "quy_Latn",
    ttl: int = 86400,
) -> str:
    """Firma un JWT HS256 con ``sub``, ``role``, ``lang``, ``iat`` y ``exp``."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "lang": lang,
        "iat": now,
        "exp": now + int(ttl),
    }
    parts = [
        _b64(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(parts).encode("ascii")
    signature = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    return ".".join(parts + [_b64(signature)])


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Devuelve el payload si la firma y la expiración son válidas."""
    if not token or token.count(".") != 2:
        return None
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_unb64(header_b64).decode("utf-8"))
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            return None
        signing_input = ("%s.%s" % (header_b64, payload_b64)).encode("ascii")
        expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
        provided = _unb64(signature_b64)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload = json.loads(_unb64(payload_b64).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        expires = int(payload.get("exp", 0))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if expires <= int(time.time()):
        return None
    return payload


def login(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Valida credenciales y devuelve el perfil + token (o ``None``)."""
    record = users().get((email or "").strip().lower())
    if not record or record["password"] != password:
        return None
    session = profile(record)
    session["token"] = issue_token(
        record["email"], record.get("role", "estudiante"), record.get("langCode", "quy_Latn")
    )
    return session


def require_auth() -> bool:
    """La exigencia de token en escrituras se activa con AYLLU_REQUIRE_AUTH=1."""
    return os.environ.get("AYLLU_REQUIRE_AUTH", "0") in ("1", "true", "yes")
