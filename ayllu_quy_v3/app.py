# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
#!/usr/bin/env python3
"""Ayllu · backend Flask (fábrica de aplicación + API + SPA).

30+ endpoints REST sobre ``core.services.AylluService``, con servido
estático de la SPA y un self-test end-to-end activable con ``SELFTEST=1``.

    python app.py                # http://127.0.0.1:5000
    SELFTEST=1 python app.py     # 46 comprobaciones end-to-end y sale
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from typing import Any, Dict, Tuple

# Carga la configuración local antes de importar el cliente de BD y el traductor.
def _load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*$", "", value).strip()
        os.environ.setdefault(key, value)


_load_local_env()

from flask import Flask, Response, jsonify, request, send_from_directory

import evaluator
import translator
from core import auth, docscanner, messaging
from core.services import ADAPT_KEYS, get_service

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


def _body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _ok(payload: Any, code: int = 200) -> Tuple[Response, int]:
    return jsonify(payload), code


def _err(message: str, code: int = 400) -> Tuple[Response, int]:
    return jsonify({"error": message}), code


def _bearer() -> str:
    """Token Bearer de la cabecera Authorization (cadena vacía si no hay)."""
    return (request.headers.get("Authorization") or "").replace("Bearer ", "").strip()


def effective_user_id(value=None):
    """Devuelve el ID autenticado o el valor solicitado en modo demo."""
    if auth.require_auth():
        return request.environ.get("ayllu.user_id")
    return value


def effective_user_role(value=""):
    """Devuelve el rol autenticado o el valor solicitado en modo demo."""
    if auth.require_auth():
        return request.environ.get("ayllu.role", "")
    return value


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    service = get_service()

    @app.before_request
    def enforce_api_auth():
        """En modo protegido, valida escrituras y lecturas de mensajería."""
        if not auth.require_auth() or not request.path.startswith("/api/"):
            return None
        if request.path == "/api/auth/login":
            if not auth.secret_configured():
                return _err("configura AYLLU_SECRET con al menos 32 caracteres antes de activar autenticación", 503)
            return None
        # El directorio de demostración tampoco debe revelar usuarios en modo
        # protegido. Las lecturas generales siguen públicas; mensajería no.
        if request.path == "/api/auth/users":
            return _err("directorio deshabilitado", 403)
        private_reads = {
            "/api/messages",
            "/api/aula/messages",
            "/api/aula/users",
            "/api/insights",
            "/api/aula/insights",
        }
        private_read = request.path in private_reads or request.path.startswith("/api/export/")
        protected = (
            request.path.startswith("/api/messaging/")
            or private_read
            or request.method not in ("GET", "HEAD", "OPTIONS")
        )
        if not protected:
            return None
        if not auth.secret_configured():
            return _err("configura AYLLU_SECRET con al menos 32 caracteres antes de activar autenticación", 503)
        claims = auth.verify_token(_bearer())
        if not claims:
            return _err("se requiere un token válido", 401)
        record = auth.users().get(str(claims.get("sub") or "").strip().lower())
        if not record:
            return _err("cuenta del token no encontrada", 401)
        own_id = str(record.get("userId"))
        request.environ["ayllu.user_id"] = own_id
        request.environ["ayllu.role"] = str(record.get("role") or "")

        teacher_read = (
            request.path in ("/api/insights", "/api/aula/insights")
            or request.path.startswith("/api/export/")
        )
        teacher_write = request.method not in ("GET", "HEAD", "OPTIONS") and request.path.startswith(
            ("/api/communities", "/api/students", "/api/glossary", "/api/materials",
             "/api/adapt", "/api/prompt", "/api/quality", "/api/admin", "/api/scan",
             "/api/aula/documents")
        )
        if (teacher_read or teacher_write) and record.get("role") != "docente":
            return _err("esta acción está disponible solo para docentes", 403)

        # Los endpoints heredados reciben el ID por JSON, formulario o query.
        # Rechaza IDs ajenos y deja que la capa de mensajería valide membresía.
        supplied = []
        for key in ("userId", "fromUserId"):
            value = request.args.get(key)
            if value:
                supplied.append(value)
        if request.is_json:
            body = request.get_json(silent=True) or {}
            if isinstance(body, dict):
                supplied.extend(body.get(key) for key in ("userId", "fromUserId") if body.get(key) is not None)
        if request.form:
            supplied.extend(request.form.get(key) for key in ("userId", "fromUserId") if request.form.get(key))
        if any(str(value) != own_id for value in supplied):
            return _err("el token no corresponde a esa cuenta", 403)
        return None

    # ----------------------------------------------------------- SPA + allin kay
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(STATIC_DIR, "favicon.svg")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/healthz")
    def healthz():
        return jsonify(service.healthz())

    # ------------------------------------------------------------ dashboard
    @app.get("/api/dashboard")
    def dashboard():
        return jsonify(service.dashboard_summary())

    # ------------------------------------------------------------- simikuna
    @app.get("/api/languages")
    def languages():
        return jsonify({"languages": service.list_languages()})

    @app.get("/api/lexicon/sizes")
    def lexicon_sizes():
        """Cuántas entradas tiene el léxico embebido por simi (aviso de límite)."""
        from core.seed import LEXICON

        return jsonify({"sizes": {code: len(terms) for code, terms in LEXICON.items()}})

    @app.get("/api/lexicon")
    def lexicon():
        target = request.args.get("target", "quy_Latn")
        from core.services import lexicon_preview

        return jsonify({"target": target, "terms": lexicon_preview(target, 24)})

    # ---------------------------------------------------------- ayllukuna
    @app.get("/api/communities")
    def communities_list():
        return jsonify({"communities": service.list_communities()})

    @app.get("/api/communities/<int:community_id>")
    def communities_get(community_id: int):
        row = service.get_community(community_id)
        return jsonify(row) if row else _err("comunidad no encontrada", 404)

    @app.post("/api/communities")
    def communities_create():
        payload = _body()
        if not str(payload.get("name") or "").strip():
            return _err("el nombre es obligatorio")
        return _ok(service.create_community(payload), 201)

    @app.put("/api/communities/<int:community_id>")
    def communities_update(community_id: int):
        row = service.update_community(community_id, _body())
        return jsonify(row) if row else _err("comunidad no encontrada", 404)

    @app.delete("/api/communities/<int:community_id>")
    def communities_delete(community_id: int):
        return jsonify({"deleted": service.delete_community(community_id)})

    # ----------------------------------------------------------- yachakuqkuna
    @app.get("/api/students")
    def students_list():
        return jsonify({"students": service.list_students()})

    @app.post("/api/students")
    def students_create():
        payload = _body()
        if not str(payload.get("name") or "").strip():
            return _err("el nombre es obligatorio")
        return _ok(service.create_student(payload), 201)

    @app.get("/api/students/<int:student_id>")
    def students_get(student_id: int):
        row = service.store.get("students", student_id)
        return jsonify(row) if row else _err("estudiante no encontrado", 404)

    @app.put("/api/students/<int:student_id>")
    def students_update(student_id: int):
        row = service.update_student(student_id, _body())
        return jsonify(row) if row else _err("estudiante no encontrado", 404)

    @app.delete("/api/students/<int:student_id>")
    def students_delete(student_id: int):
        return jsonify({"deleted": service.delete_student(student_id)})

    # --------------------------------------------------------------- glosario
    @app.get("/api/glossary")
    def glossary_list():
        return jsonify(
            {
                "terms": service.list_glossary(
                    request.args.get("q", ""), request.args.get("target", "")
                )
            }
        )

    @app.post("/api/glossary")
    def glossary_create():
        payload = _body()
        if not str(payload.get("term") or "").strip():
            return _err("el término es obligatorio")
        return _ok(service.create_glossary_term(payload), 201)

    @app.get("/api/glossary/<int:term_id>")
    def glossary_get(term_id: int):
        row = service.store.get("glossary", term_id)
        return jsonify(row) if row else _err("término no encontrado", 404)

    @app.put("/api/glossary/<int:term_id>")
    def glossary_update(term_id: int):
        row = service.update_glossary_term(term_id, _body())
        return jsonify(row) if row else _err("término no encontrado", 404)

    @app.delete("/api/glossary/<int:term_id>")
    def glossary_delete(term_id: int):
        return jsonify({"deleted": service.delete_glossary_term(term_id)})

    @app.post("/api/glossary/import")
    def glossary_import():
        payload = _body()
        text = str(payload.get("csv") or payload.get("text") or "")
        if not text.strip():
            return _err("csv vacío")
        return jsonify(service.import_glossary_csv(text))

    @app.get("/api/glossary/suggest")
    def glossary_suggest():
        """Búsqueda tolerante a typos (rapidfuzz si está instalada)."""
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"query": query, "suggestions": []})
        terms = [str(r.get("term")) for r in service.store.select("glossary")]
        try:
            from rapidfuzz import process as _process

            matches = _process.extract(query, terms, limit=5)
            suggestions = [{"term": m[0], "score": round(float(m[1]), 1)} for m in matches]
            engine = "rapidfuzz"
        except Exception:
            needle = query.lower()
            suggestions = [
                {"term": t, "score": 100.0}
                for t in terms
                if needle in t.lower() or t.lower().startswith(needle[:2])
            ][:5]
            engine = "substring"
        return jsonify({"query": query, "engine": engine, "suggestions": suggestions})

    # -------------------------------------------------------------- materiales
    @app.get("/api/materials")
    def materials_list():
        return jsonify({"materials": service.list_materials()})

    @app.post("/api/materials")
    def materials_create():
        payload = _body()
        if not str(payload.get("title") or "").strip():
            return _err("el título es obligatorio")
        return _ok(service.create_material(payload), 201)

    @app.put("/api/materials/<int:material_id>")
    def materials_update(material_id: int):
        row = service.update_material(material_id, _body())
        return jsonify(row) if row else _err("material no encontrado", 404)

    @app.delete("/api/materials/<int:material_id>")
    def materials_delete(material_id: int):
        return jsonify({"deleted": service.delete_material(material_id)})

    # ------------------------------------------------------- adaptador / calidad
    @app.post("/api/adapt")
    def adapt():
        payload = _body()
        if not str(payload.get("text") or "").strip():
            return _err("el texto es obligatorio")
        result = service.public_adapt(payload)
        missing = [key for key in ADAPT_KEYS if key not in result]
        if missing:
            return _err("respuesta incompleta: %s" % ", ".join(missing), 500)
        return jsonify(result)

    @app.post("/api/prompt")
    def prompt_preview():
        """Prompt blindado sin invocar al LLM (botón «Rikuy prompt blindado»)."""
        return jsonify(service.prompt_preview(_body()))

    @app.post("/api/quality")
    def quality_post():
        payload = _body()
        hypothesis = str(payload.get("hypothesis") or payload.get("adapted") or "")
        reference = str(payload.get("reference") or payload.get("rawTranslation") or "")
        if not hypothesis or not reference:
            return _err("hypothesis y reference son obligatorios")
        return jsonify(service.evaluate(payload))

    @app.get("/api/quality")
    def quality_get():
        return jsonify(service.quality_report())

    @app.get("/api/quality/score")
    def quality_score():
        hypothesis = request.args.get("hypothesis", "")
        reference = request.args.get("reference", "")
        if not hypothesis or not reference:
            return _err("hypothesis y reference son obligatorios")
        return jsonify(
            {
                "scores": evaluator.score_pair(hypothesis, reference),
                "band": evaluator.quality_band(evaluator.chr_f2(hypothesis, reference)),
            }
        )

    # -------------------------------------------------------------- analítica
    @app.get("/api/analytics")
    def analytics():
        return jsonify(service.analytics())

    # --------------------------------------------------------- feedback / audit
    @app.get("/api/feedback")
    def feedback_list():
        return jsonify({"feedback": service.list_feedback()})

    @app.post("/api/feedback")
    def feedback_create():
        payload = _body()
        if not payload.get("rating"):
            return _err("rating es obligatorio")
        return _ok(service.submit_feedback(payload), 201)

    @app.get("/api/activity")
    def activity():
        limit = request.args.get("limit", type=int) or 20
        return jsonify({"activity": service.activity(limit)})

    # ---------------------------------------------------------------- búsqueda
    @app.get("/api/search")
    def search():
        return jsonify(service.search(request.args.get("q", "")))

    # --------------------------------------------------------- autenticación
    @app.get("/api/auth/users")
    def auth_directory():
        """Directorio de cuentas para el acceso rápido (sólo en modo demo)."""
        return jsonify({"users": service.list_users(), "demo": auth.demo_mode()})

    @app.post("/api/auth/login")
    def login():
        payload = _body()
        session = auth.login(str(payload.get("email") or ""), str(payload.get("password") or ""))
        if not session:
            return _err("credenciales inválidas", 401)
        return jsonify(session)

    @app.get("/api/auth/me")
    def me():
        payload = auth.verify_token(_bearer())
        return jsonify(payload) if payload else _err("token inválido", 401)

    # ---------------------------------------------- bandeja del aula (2 roles)
    @app.get("/api/messages")
    def messages_list():
        user_id = effective_user_id(request.args.get("userId", type=int))
        role = effective_user_role(str(request.args.get("role") or ""))
        limit = request.args.get("limit", type=int) or 60
        return jsonify({"messages": service.list_messages(user_id, role, limit)})

    @app.post("/api/messages")
    def messages_create():
        try:
            row = service.create_message(_body())
        except ValueError as error:
            return _err(str(error), 400)
        return _ok(row, 201)

    @app.put("/api/messages/<int:message_id>/read")
    def messages_read(message_id: int):
        if auth.require_auth():
            message = service.store.get("messages", message_id)
            user_id = effective_user_id()
            if not message:
                return _err("mensaje no encontrado", 404)
            if str(user_id) not in (str(message.get("fromUserId")), str(message.get("toUserId"))):
                return _err("no participas en este mensaje", 403)
        row = service.mark_message_read(message_id)
        return jsonify(row) if row else _err("mensaje no encontrado", 404)

    @app.delete("/api/messages/<int:message_id>")
    def messages_delete(message_id: int):
        if auth.require_auth() and effective_user_role() != "docente":
            return _err("solo una cuenta docente puede eliminar mensajes", 403)
        return jsonify({"deleted": service.store.delete("messages", message_id)})

    # ------------------------------------------- tablero de gestión (docente)
    @app.get("/api/insights")
    def insights():
        if auth.require_auth() and effective_user_role() != "docente":
            return _err("solo una cuenta docente puede ver este panel", 403)
        return jsonify(service.insights())

    # ------------------------------------------------------------- export CSV
    @app.get("/api/export/<table>.csv")
    def export_csv(table: str):
        try:
            rows = service.export_rows(table)
        except KeyError:
            return _err("tabla no exportable", 404)
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        k: (v if not isinstance(v, (dict, list)) else str(v))
                        for k, v in row.items()
                    }
                )
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=%s.csv" % table},
        )

    # ------------------------------------------------------------------ admin
    @app.post("/api/admin/reset")
    def admin_reset():
        if auth.require_auth() and effective_user_role() != "docente":
            return _err("solo una cuenta docente puede reiniciar la demo", 403)
        if getattr(service.store, "mode", "memory") != "memory":
            return _err("el reinicio solo está disponible en el modo de demostración", 409)
        service.reset()
        messaging.reset_messaging()
        return jsonify({"reset": True, "health": service.healthz()})

    # ------------------------------------------------------ escáner documentos
    @app.get("/api/scan/limits")
    def scan_limits():
        return jsonify(docscanner.limits())

    @app.post("/api/scan")
    def scan_document():
        """Chaskiy un PDF/TXT por multipart (chakra «file») y devuelve su texto."""
        upload = request.files.get("file")
        if upload is None or not (upload.filename or "").strip():
            return jsonify(
                {
                    "error": "Adjunta un archivo .pdf o .txt en el campo «file».",
                    "hint": "Formatos aceptados: %s." % ", ".join(docscanner.ALLOWED_EXT),
                }
            ), 400
        # se ñawinchay un byte de más para poder detectar el exceso de tamaño
        data = upload.read(docscanner.MAX_BYTES + 1)
        try:
            result = docscanner.inspect(upload.filename, data, upload.mimetype or "")
        except docscanner.ScanError as error:
            return jsonify(error.as_dict()), error.code
        return jsonify(result)

    # ------------------------------------------- v5 · mensajería (ambos roles)
    @app.get("/api/messaging/directory")
    def messaging_directory():
        """Directorio de cuentas para elegir destinatario, con sus simikuna."""
        users = messaging.directory()
        if auth.require_auth():
            for user in users:
                user.pop("password", None)
        return jsonify(
            {"users": users, "languages": service.list_languages()}
        )

    @app.get("/api/messaging/threads")
    def messaging_threads():
        """Conversaciones en las que participa ``userId``, con no leídos."""
        user_id = effective_user_id(request.args.get("userId"))
        return jsonify({"threads": messaging.list_threads(user_id)})

    @app.post("/api/messaging/threads")
    def messaging_thread_create():
        """Abre una conversación: docente → un estudiante o grupo del aula."""
        try:
            payload = _body()
            if auth.require_auth():
                payload.setdefault("fromUserId", effective_user_id())
            row = messaging.create_thread(payload)
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return _ok(row, 201)

    @app.get("/api/messaging/unread")
    def messaging_unread():
        """Contador de no leídos de una cuenta (insignia del menú)."""
        return jsonify(messaging.unread(effective_user_id(request.args.get("userId"))))

    @app.get("/api/messaging/threads/<int:thread_id>/messages")
    def messaging_messages(thread_id: int):
        try:
            rows = messaging.list_messages(
                thread_id,
                effective_user_id(request.args.get("userId")),
                request.args.get("limit", type=int) or 200,
            )
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return jsonify({"threadId": thread_id, "messages": rows})

    @app.post("/api/messaging/threads/<int:thread_id>/messages")
    def messaging_send(thread_id: int):
        """Mensaje de texto traducido a la lengua elegida por quien escribe."""
        try:
            payload = _body()
            if auth.require_auth():
                payload.setdefault("fromUserId", effective_user_id())
            row = messaging.send_message(thread_id, payload)
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return _ok(row, 201)

    @app.post("/api/messaging/threads/<int:thread_id>/documents")
    def messaging_send_document(thread_id: int):
        """Adjunta un .pdf / .txt: se valida, se extrae el texto y se traduce."""
        upload = request.files.get("file")
        if upload is None or not (upload.filename or "").strip():
            return _err("Adjunta un archivo .pdf o .txt en el campo «file».")
        data = upload.read(docscanner.MAX_BYTES + 1)
        form = request.form
        payload = {
            "fromUserId": form.get("fromUserId") or effective_user_id(),
            "src": form.get("src") or "",
            "targets": [t for t in re.split(r"[\s,;]+", form.get("targets") or "") if t],
            "level": form.get("level") or "básico",
            "title": form.get("title") or upload.filename,
        }
        try:
            row = messaging.send_attachment(thread_id, payload, upload.filename, data)
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return _ok(row, 201)

    @app.post("/api/messaging/messages/<int:message_id>/translate")
    def messaging_translate(message_id: int):
        """Botón «Traducir»: cualquiera de los dos roles pide la lengua que quiera."""
        try:
            payload = _body()
            if auth.require_auth():
                payload.setdefault("userId", effective_user_id())
            result = messaging.translate_message(message_id, payload)
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return jsonify(result)

    @app.put("/api/messaging/messages/<int:message_id>/read")
    def messaging_read(message_id: int):
        user_id = effective_user_id(_body().get("userId") or request.args.get("userId"))
        try:
            row = messaging.mark_read(message_id, user_id)
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return jsonify(row) if row else _err("mensaje no encontrado", 404)

    @app.put("/api/messaging/threads/<int:thread_id>/read")
    def messaging_thread_read(thread_id: int):
        user_id = effective_user_id(_body().get("userId") or request.args.get("userId"))
        try:
            return jsonify(messaging.mark_thread_read(thread_id, user_id))
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code

    @app.get("/api/messaging/messages/<int:message_id>/attachment")
    def messaging_attachment(message_id: int):
        """Descarga el documento adjunto (vive en memoria, nunca en disco)."""
        try:
            if auth.require_auth():
                row = service.store.get("messages", message_id)
                if not row:
                    return _err("mensaje no encontrado", 404)
                thread = messaging.get_messaging().get_thread(row.get("threadId"))
                if not thread or str(request.environ.get("ayllu.user_id")) not in [str(x) for x in thread.get("participants", [])]:
                    return _err("no participas en esta conversación", 403)
            data, mime, name = messaging.attachment_bytes(message_id)
        except messaging.MessagingError as error:
            return jsonify(error.as_dict()), error.code
        return Response(
            data,
            mimetype=mime,
            headers={
                "Content-Disposition": 'attachment; filename="%s"' % docscanner.safe_name(name)
            },
        )

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return _err("ruta no encontrada", 404)
        return send_from_directory(STATIC_DIR, "index.html")

    return app


# ---------------------------------------------------------------------------
# Flujo v3 · aula bilingüe con dos roles (docente / estudiante)
# ---------------------------------------------------------------------------


def register_aula_routes() -> Flask:
    """Añade el flujo del aula al núcleo de Ayllu.

    Mismo ``AylluService`` y mismo contrato REST: sólo se suman el directorio de
    cuentas, la bandeja traducida del aula y el tablero de gestión docente.
    """
    app = create_app()
    service = get_service()

    @app.get("/api/aula/users")
    def aula_users():
        """Directorio de cuentas por rol (público sólo en modo demo)."""
        users = service.list_users()
        if auth.require_auth():
            for user in users:
                user.pop("password", None)
        return jsonify({"users": users, "demo": auth.demo_mode() and not auth.require_auth()})

    @app.get("/api/aula/messages")
    def aula_messages():
        user_id = effective_user_id(request.args.get("userId", type=int))
        role = effective_user_role(str(request.args.get("role") or ""))
        limit = request.args.get("limit", type=int) or 60
        return jsonify({"messages": service.list_messages(user_id, role, limit)})

    @app.post("/api/aula/messages")
    def aula_send():
        """Traduce y entrega un mensaje: docente → estudiante y a la inversa."""
        try:
            row = service.create_message(_body())
        except ValueError as error:
            return _err(str(error))
        return _ok(row, 201)

    @app.post("/api/aula/documents")
    def aula_document():
        """Escáner: sube un .pdf o .txt y lo entrega en UNA o VARIAS lenguas.

        Campo ``targets`` (coma o espacio): lista de lenguas destino. Si viene
        vacío se conserva el comportamiento anterior de una sola entrega a la
        lengua del destinatario.
        """
        upload = request.files.get("file")
        if upload is None or not (upload.filename or "").strip():
            return _err("Adjunta un archivo .pdf o .txt en el campo «file».")
        data = upload.read(docscanner.MAX_BYTES + 1)
        try:
            scanned = docscanner.inspect(upload.filename, data, upload.mimetype or "")
        except docscanner.ScanError as error:
            return jsonify(error.as_dict()), error.code
        text = str(scanned.get("text") or "").strip()
        if not text:
            return _err("El documento no tiene texto extraíble: requiere OCR.")
        form = request.form
        raw_targets = str(form.get("targets") or form.get("tgt") or "")
        targets = [t for t in re.split(r"[\s,;]+", raw_targets) if t]
        document = {
            "name": scanned.get("name"),
            "pages": scanned.get("pages"),
            "chars": scanned.get("chars"),
            "words": scanned.get("words"),
            "sizeLabel": scanned.get("sizeLabel"),
        }

        if targets:
            # Varias lenguas destino: una entrega por cada una, con el original intacto.
            try:
                result = service.deliver_scanned_document(
                    scanned,
                    from_user_id=form.get("fromUserId"),
                    to_user_id=form.get("toUserId"),
                    targets=targets,
                    title=(form.get("title") or upload.filename or "Documento"),
                    level=str(form.get("level") or "básico"),
                )
            except ValueError as error:
                return _err(str(error))
            return _ok(
                {
                    "ok": True,
                    "fromUserId": form.get("fromUserId"),
                    "toUserId": form.get("toUserId"),
                    "targets": result.get("targets"),
                    "deliveries": result.get("deliveries"),
                    "document": result.get("document") or document,
                },
                201,
            )

        try:
            row = service.create_message(
                {
                    "fromUserId": form.get("fromUserId"),
                    "toUserId": form.get("toUserId"),
                    "kind": "material",
                    "title": (form.get("title") or upload.filename or "Documento").strip(),
                    "text": text[:8000],
                    "level": str(form.get("level") or "básico"),
                }
            )
        except ValueError as error:
            return _err(str(error))
        row["document"] = document
        return _ok(row, 201)

    @app.put("/api/aula/messages/<int:message_id>/read")
    def aula_read(message_id: int):
        row = service.mark_message_read(message_id)
        return jsonify(row) if row else _err("mensaje no encontrado", 404)

    @app.get("/api/aula/insights")
    def aula_insights():
        """Tablero del docente: bandeja, pares de lenguas y cobertura."""
        if auth.require_auth() and effective_user_role() != "docente":
            return _err("solo una cuenta docente puede ver este panel", 403)
        return jsonify(service.insights())

    return app


# ---------------------------------------------------------------------------
# Self-test end-to-end: SELFTEST=1 python app.py
# ---------------------------------------------------------------------------


def run_selftest() -> int:
    client = create_app().test_client()
    checks = []

    def check(label: str, condition: bool) -> None:
        checks.append((label, bool(condition)))
        if not condition:
            print("  ✗ %s" % label)

    # 1-2 · allin kay y modo
    health = client.get("/healthz").get_json()
    check("GET /healthz responde ok", health.get("status") in ("ok", "degraded"))
    check("modo degradado declarado", "mode" in health)
    # 3 · simikuna
    languages = client.get("/api/languages").get_json()["languages"]
    check("catálogo ampliado de lenguas (>= 12)", len(languages) >= 12)
    check(
        "cada lengua declara su código de motor y su grupo",
        all(row.get("google") and row.get("group") for row in languages),
    )
    # 4-5 · muhu
    communities = client.get("/api/communities").get_json()["communities"]
    check("6 comunidades sembradas", len(communities) == 6)
    students = client.get("/api/students").get_json()["students"]
    check("17 estudiantes sembrados", len(students) == 17)
    # 6 · dashboard
    dashboard = client.get("/api/dashboard").get_json()
    check(
        "dashboard con KPI de lenguas activas = catálogo",
        dashboard["kpis"]["activeLanguages"] == len(languages),
    )
    # 7-8 · CRUD ayllukuna
    created = client.post(
        "/api/communities",
        json={"name": "Comunidad de prueba", "ecosystem": "urbano", "langCode": "quy_Latn"},
    ).get_json()
    check("POST /api/communities crea", created.get("id") is not None)
    updated = client.put(
        "/api/communities/%s" % created["id"], json={"name": "Comunidad renombrada"}
    ).get_json()
    check("PUT /api/communities actualiza", updated.get("name") == "Comunidad renombrada")
    # 9 · DELETE
    check(
        "DELETE /api/communities borra",
        client.delete("/api/communities/%s" % created["id"]).get_json()["deleted"] is True,
    )
    # 10-11 · CRUD glosario
    term = client.post(
        "/api/glossary",
        json={"term": "prueba", "langs": {"spa_Latn": "prueba", "quy_Latn": "yachay"}, "domain": "test"},
    ).get_json()
    check("POST /api/glossary crea", term.get("term") == "prueba")
    check(
        "PUT /api/glossary actualiza",
        client.put("/api/glossary/%s" % term["id"], json={"domain": "test-2"}).get_json()["domain"]
        == "test-2",
    )
    # 12 · import CSV
    imported = client.post(
        "/api/glossary/import", json={"csv": "term;quy;ayr;grn;dominio\nluz;kancha;nakhaya;tesape;física"}
    ).get_json()
    check("POST /api/glossary/import inserta", imported["created"] == 1)
    # 13 · CRUD materiales
    material = client.post(
        "/api/materials", json={"title": "Ficha de prueba", "kind": "ficha"}
    ).get_json()
    check("POST /api/materials crea", material.get("id") is not None)
    # 14-17 · adaptación y contrato de 12 claves
    adapted = client.post(
        "/api/adapt",
        json={
            "text": "La fracción es una parte de un todo y la semilla germina en la tierra.",
            "src": "spa_Latn",
            "tgt": "quy_Latn",
            "level": "básico",
            "communityId": 1,
        },
    ).get_json()
    check("POST /api/adapt responde 200 con adapted", bool(adapted.get("adapted")))
    check("contrato de 12 claves exacto", all(k in adapted for k in ADAPT_KEYS) and len(ADAPT_KEYS) == 12)
    check("chrF2 calculado en adapt", adapted["scores"]["chrF2"] > 0)
    cached = client.post(
        "/api/adapt",
        json={
            "text": "La fracción es una parte de un todo y la semilla germina en la tierra.",
            "src": "spa_Latn",
            "tgt": "quy_Latn",
            "level": "básico",
            "communityId": 1,
        },
    ).get_json()
    check("segunda llamada a /api/adapt viene de caché", cached["cacheHit"] is True)
    # 18-19 · calidad
    quality = client.post(
        "/api/quality",
        json={"hypothesis": "la semilla germina en la tierra", "reference": "la semilla crece en el suelo"},
    ).get_json()
    check("POST /api/quality devuelve chrF2", quality["scores"]["chrF2"] > 0)
    report = client.get("/api/quality").get_json()
    check("cohen d etiquetado", report["label"] in (
        "impacto sólido", "impacto moderado", "impacto bajo", "sin efecto apreciable"
    ))
    # 20 · analítica
    analytics = client.get("/api/analytics").get_json()
    check("analítica con leaderboard", len(analytics["leaderboard"]) > 0)
    # 21 · feedback
    feedback = client.post(
        "/api/feedback", json={"studentId": 1, "rating": 5, "note": "ok", "reviewer": "selftest"}
    ).get_json()
    check("POST /api/feedback registra", feedback.get("rating") == 5)
    # 22 · CSV + búsqueda
    csv_response = client.get("/api/export/students.csv")
    search = client.get("/api/search?q=comunidad").get_json()
    check(
        "export CSV + búsqueda",
        csv_response.status_code == 200 and "name" in csv_response.get_data(as_text=True)
        and search["total"] >= 1,
    )

    # 23-26 · escáner de documentos (PDF / TXT) y rechazo de otros formatos
    txt_scan = client.post(
        "/api/scan",
        data={"file": (io.BytesIO("La semilla germina en la tierra húmeda.".encode("utf-8")), "muestra.txt")},
        content_type="multipart/form-data",
    ).get_json()
    check(
        "POST /api/scan extrae texto de TXT",
        txt_scan.get("ok") is True and txt_scan.get("chars", 0) > 10 and txt_scan.get("ext") == ".txt",
    )
    pdf_scan = client.post(
        "/api/scan",
        data={"file": (io.BytesIO(_sample_pdf("Ayllu prueba de escaneo PDF")), "muestra.pdf")},
        content_type="multipart/form-data",
    ).get_json()
    check(
        "POST /api/scan extrae texto de PDF",
        pdf_scan.get("ok") is True and "escaneo" in (pdf_scan.get("text") or "").lower(),
    )
    docx = client.post(
        "/api/scan",
        data={"file": (io.BytesIO(b"PK\x03\x04informe falso de word"), "informe.docx")},
        content_type="multipart/form-data",
    )
    check(
        "POST /api/scan rechaza .docx con 415",
        docx.status_code == 415 and "pdf" in docx.get_json().get("error", "").lower(),
    )
    limits = client.get("/api/scan/limits").get_json()
    check(
        "GET /api/scan/limits publica tipos y límite",
        ".pdf" in limits.get("extensions", []) and limits.get("maxBytes", 0) > 0,
    )

    # 27 · el botón «Rikuy prompt blindado» tiene su propio endpoint
    prompt = client.post(
        "/api/prompt",
        json={"text": "El agua y la semilla", "tgt": "quy_Latn", "level": "básico", "communityId": 1},
    ).get_json()
    check(
        "POST /api/prompt devuelve el prompt blindado con reglas y glosario",
        "ROL" in prompt.get("prompt", "") and "GLOSARIO PREFERENTE" in prompt.get("prompt", "")
        and prompt.get("glossarySize", 0) > 0,
    )

    # 28 · regresión: el término de una letra («y» = yaku en guaraní) NO debe
    # corromper conjunciones ni el interior de otras simikuna.
    grn = client.post(
        "/api/adapt",
        json={"text": "El agua del río y la semilla", "tgt": "grn_Latn", "level": "avanzado"},
    ).get_json()
    check(
        "glosa a guaraní sin corromper palabras",
        grn.get("adapted") is not None
        and "y (agua)syry" not in grn["adapted"]
        and "y (agua)vága" not in grn["adapted"],
    )

    # 29-35 · v3: login de dos roles y bandeja del aula bilingüe
    directory = client.get("/api/auth/users").get_json()
    check("GET /api/auth/users publica el directorio demo", len(directory.get("users", [])) >= 4)
    docente = auth.login("docente@ayllu.pe", "ayllu-docente")
    estudiante = auth.login("estudiante@ayllu.pe", "ayllu-estudiante")
    check(
        "login con dos roles devuelve rol y lengua de cada cuenta",
        (docente or {}).get("role") == "docente"
        and (estudiante or {}).get("role") == "estudiante"
        and (estudiante or {}).get("langCode") == "quy_Latn",
    )
    check("login con clave incorrecta se rechaza", auth.login("docente@ayllu.pe", "mala") is None)

    inbox = client.get("/api/messages?userId=%s" % estudiante["userId"]).get_json()["messages"]
    check("bandeja del estudiante con mensajes sembrados", len(inbox) >= 1)

    sent_docente = client.post(
        "/api/messages",
        json={
            "fromUserId": docente["userId"],
            "toUserId": estudiante["userId"],
            "kind": "mensaje",
            "text": "Hola Ana, hoy veremos el agua del río y la semilla de la tierra.",
        },
    ).get_json()
    check(
        "docente → estudiante: la salida está en la lengua del estudiante",
        sent_docente.get("tgt") == "quy_Latn" and "yaku" in sent_docente.get("outText", ""),
    )
    check(
        "docente → estudiante: el original queda intacto en castellano",
        "agua" in sent_docente.get("srcText", ""),
    )

    sent_estudiante = client.post(
        "/api/messages",
        json={
            "fromUserId": estudiante["userId"],
            "toUserId": docente["userId"],
            "kind": "mensaje",
            "text": "Mi wasi está cerca del mayu y del ñan de la yachay wasi.",
        },
    ).get_json()
    check(
        "estudiante → docente: el docente lee castellano y el original queda intacto",
        sent_estudiante.get("tgt") == "spa_Latn"
        and "casa" in sent_estudiante.get("outText", "")
        and "wasi" in sent_estudiante.get("srcText", ""),
    )
    insight = client.get("/api/insights").get_json()
    check(
        "GET /api/insights resume la bandeja y la cobertura",
        insight.get("messages", 0) > 0 and "coverage" in insight and "pairs" in insight,
    )

    # 36-38 · flujo v3: el mismo dominio expuesto por el router del aula
    aula = register_aula_routes().test_client()
    aula_users = aula.get("/api/aula/users").get_json()
    check(
        "flujo v3 registrado con su propio directorio de cuentas",
        len(aula_users.get("users", [])) >= 4,
    )
    check(
        "flujo v3 responde la bandeja del aula",
        len(aula.get("/api/aula/messages").get_json().get("messages", [])) >= 1,
    )
    insight_aula = aula.get("/api/aula/insights").get_json()
    check(
        "flujo v3 publica el tablero de gestión docente",
        insight_aula.get("messages", 0) > 0 and "coverage" in insight_aula,
    )

    # 39-46 · ampliación: más lenguas, varios profesores y escáner multi-lengua
    docentes = [u for u in directory.get("users", []) if u.get("role") == "docente"]
    check("varios profesores en el directorio del aula", len(docentes) >= 3)
    rosa = auth.login("rosa.docente@ayllu.pe", "ayllu-docente")
    check(
        "login del segundo profesor con su ayllu y su aula",
        (rosa or {}).get("role") == "docente"
        and (rosa or {}).get("communityId") == 2
        and (rosa or {}).get("langCode") == "spa_Latn",
    )
    quz = auth.login("yaku@ayllu.pe", "ayllu-estudiante")
    check(
        "estudiante de una variante nueva de quechua",
        (quz or {}).get("langCode") == "quz_Latn",
    )
    check(
        "el traductor mapea cada lengua del catálogo a su código de Google",
        translator.google_code_for("eng_Latn") == "en"
        and translator.google_code_for("arb_Arab") == "ar"
        and translator.google_code_for("quz_Latn") == "qu"
        and translator.google_code_for("zho_Hans") == "zh-CN",
    )
    multi = aula.post(
        "/api/aula/documents",
        data={
            "file": (
                io.BytesIO("El agua del río y la semilla de la tierra.".encode("utf-8")),
                "ficha.txt",
            ),
            "fromUserId": str(docente["userId"]),
            "toUserId": str(estudiante["userId"]),
            "targets": "quy_Latn,eng_Latn,ayr_Latn",
            "level": "básico",
            "title": "Ficha multilingüe",
        },
        content_type="multipart/form-data",
    ).get_json()
    deliveries = multi.get("deliveries") or []
    check("el escáner entrega el mismo documento en 3 lenguas", len(deliveries) == 3)
    check(
        "cada entrega tiene su lengua destino y su mensaje en la bandeja",
        {row.get("tgt") for row in deliveries} == {"quy_Latn", "eng_Latn", "ayr_Latn"}
        and all(row.get("messageId") for row in deliveries),
    )
    bad = aula.post(
        "/api/aula/documents",
        data={
            "file": (io.BytesIO("texto de prueba".encode("utf-8")), "x.txt"),
            "fromUserId": str(docente["userId"]),
            "toUserId": str(estudiante["userId"]),
            "targets": "klingon_Latn",
            "title": "idioma imposible",
        },
        content_type="multipart/form-data",
    )
    check("el escáner rechaza una lengua desconocida con 400", bad.status_code == 400)
    check(
        "el glosario conserva columnas de lenguas nuevas",
        "eng_Latn"
        in set(
            client.post(
                "/api/glossary",
                json={
                    "term": "agua",
                    "langs": {"eng_Latn": "water", "quy_Latn": "yaku"},
                    "domain": "ciencias naturales",
                },
            ).get_json()["langs"]
        ),
    )

    # 47-58 · v5 · mensajería docente ↔ estudiante: texto, documentos y traducción
    doc = auth.login("docente@ayllu.pe", "ayllu-docente")
    est = auth.login("estudiante@ayllu.pe", "ayllu-estudiante")
    threads = client.get(
        "/api/messaging/threads?userId=%s" % est["userId"]
    ).get_json()["threads"]
    check("mensajería: el estudiante ve sus conversaciones", len(threads) >= 2)
    check(
        "mensajería: existe la conversación grupal del aula",
        any(row.get("type") == "group" for row in threads),
    )
    direct = next((row for row in threads if row.get("type") == "direct"), None)
    check(
        "mensajería: el hilo directo lista a sus dos miembros y su último mensaje",
        len((direct or {}).get("members") or []) == 2
        and bool((direct or {}).get("lastPreview"))
        and (direct or {}).get("messageCount", 0) >= 1,
    )
    room = direct["id"] if direct else 1
    sent = client.post(
        "/api/messaging/threads/%s/messages" % room,
        json={
            "fromUserId": doc["userId"],
            "text": "Hoy veremos el agua del río y la semilla de la tierra.",
            "tgt": "quy_Latn",
            "level": "básico",
        },
    ).get_json()
    check(
        "mensajería docente → estudiante: la entrega va en la lengua del estudiante",
        sent.get("tgt") == "quy_Latn" and "yaku" in (sent.get("outText") or ""),
    )
    check(
        "mensajería: el texto original de quien escribe queda intacto",
        "agua" in (sent.get("srcText") or ""),
    )
    reply = client.post(
        "/api/messaging/threads/%s/messages" % room,
        json={
            "fromUserId": est["userId"],
            "text": "Mi wasi está cerca del mayu y del ñan de la yachay wasi.",
            "tgt": "spa_Latn",
        },
    ).get_json()
    check(
        "mensajería estudiante → docente: el docente lee castellano",
        reply.get("tgt") == "spa_Latn" and "casa" in (reply.get("outText") or ""),
    )
    unread = client.get("/api/messaging/unread?userId=%s" % est["userId"]).get_json()
    check("mensajería: insignia de no leídos para el destinatario", unread.get("total", 0) >= 1)
    for row in client.get(
        "/api/messaging/threads?userId=%s" % est["userId"]
    ).get_json()["threads"]:
        client.put(
            "/api/messaging/threads/%s/read" % row["id"], json={"userId": est["userId"]}
        )
    cleared = client.get("/api/messaging/unread?userId=%s" % est["userId"]).get_json()
    check("mensajería: marcar como leído limpia el contador", cleared.get("total", 1) == 0)
    translated = client.post(
        "/api/messaging/messages/%s/translate" % sent["id"],
        json={"userId": est["userId"], "tgt": "eng_Latn"},
    ).get_json()
    check(
        "mensajería: el estudiante traduce un mensaje a la lengua que elige",
        bool(translated.get("text")) and translated.get("tgt") == "eng_Latn",
    )
    cached = client.post(
        "/api/messaging/messages/%s/translate" % sent["id"],
        json={"userId": doc["userId"], "tgt": "eng_Latn"},
    ).get_json()
    # Una glosa de respaldo debe reintentarse; sólo la traducción completa se cachea.
    cache_expectation = translated.get("engine") != "lexicon"
    check(
        "mensajería: reutiliza traducción completa o reintenta glosa",
        cached.get("cached") is cache_expectation,
    )
    bad_lang = client.post(
        "/api/messaging/messages/%s/translate" % sent["id"],
        json={"userId": est["userId"], "tgt": "klingon_Latn"},
    )
    check("mensajería: lengua de traducción desconocida → 400", bad_lang.status_code == 400)
    attached = client.post(
        "/api/messaging/threads/%s/documents" % room,
        data={
            "file": (
                io.BytesIO("La semilla germina en la tierra húmeda del huerto.".encode("utf-8")),
                "tarea.txt",
            ),
            "fromUserId": str(doc["userId"]),
            "targets": "quy_Latn",
            "title": "Ficha de la semilla",
        },
        content_type="multipart/form-data",
    ).get_json()
    check(
        "mensajería: documento adjunto validado y entregado traducido",
        attached.get("kind") == "documento"
        and (attached.get("attachment") or {}).get("words", 0) > 3
        and attached.get("tgt") == "quy_Latn",
    )
    fake = client.post(
        "/api/messaging/threads/%s/documents" % room,
        data={
            "file": (io.BytesIO(b"PK\x03\x04word que no es pdf"), "informe.docx"),
            "fromUserId": str(doc["userId"]),
        },
        content_type="multipart/form-data",
    )
    check("mensajería: adjunto .docx rechazado con 415", fake.status_code == 415)
    download = client.get("/api/messaging/messages/%s/attachment" % attached["id"])
    check(
        "mensajería: el adjunto se descarga desde el propio mensaje",
        download.status_code == 200 and b"semilla" in download.data,
    )
    grouped = client.post(
        "/api/messaging/threads",
        json={
            "fromUserId": doc["userId"],
            "toUserIds": [est["userId"], 3],
            "title": "Aviso del lunes",
        },
    ).get_json()
    check(
        "mensajería: el docente abre una conversación con varios estudiantes",
        grouped.get("type") == "group" and len(grouped.get("participants") or []) == 3,
    )

    total = len(checks)
    passed = sum(1 for _, ok in checks if ok)
    print("SELFTEST %s | asserts=%d/%d" % ("OK" if passed == total else "FAIL", passed, total))
    print("|languages=%d" % len(languages))
    print("|adapt_keys=%s" % ",".join(ADAPT_KEYS))
    if passed != total:
        print("|failed=%s" % ",".join(label for label, ok in checks if not ok))
        return 1
    return 0


def _sample_pdf(text: str = "Ayllu prueba de escaneo PDF") -> bytes:
    """PDF mínimo válido (con tabla xref) usado por el self-test."""
    stream = "BT /F1 14 Tf 60 760 Td (%s) Tj ET" % text.replace("(", r"\(").replace(")", r"\)")
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (index, body)).encode("latin-1")
    xref_at = len(out)
    out += ("xref\n0 %d\n" % (len(objects) + 1)).encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode("latin-1")
    out += (
        "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref_at)
    ).encode("latin-1")
    return bytes(out)


app = register_aula_routes()


if __name__ == "__main__":
    if os.environ.get("SELFTEST") in ("1", "true", "yes"):
        sys.exit(run_selftest())
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
