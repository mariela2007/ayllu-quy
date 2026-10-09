# Ayllu · hack4edu reto #06 · v3

Aplicación web que **traduce y adapta** materiales y mensajes educativos a
lenguas originarias andinas y amazónicas, con **dos roles**: la profesora trabaja
en castellano y cada estudiante lee y escribe en su lengua. Flask + Supabase +
SPA sin dependencias de frontend.

> Ayllu no sólo traduce documentos: es un **puente de comunicación** del aula.

---

## ⚠️ Estado de esta entrega (ñawinchay antes de usarla)

- Los textos en quechua, aimara y guaraní de la muhu son **demostrativos** y
  **no están validados por hablantes nativos**. Sin `NLLB_API_URL` conectado, la
  salida es una **glosa de vocabulario**, no una traducción completa: así se
  declara en la interfaz (`degraded = true`).
- La **serie de actividad diaria** de la pantalla de Analítica es demostrativa;
  no proviene de telemetría real y la interfaz lo dice.
- Las **claves de acceso son de demostración y se muestran en la pantalla de
  acceso a propósito**: es un prototipo de hackatón, no un servicio endurecido.
  Con `AYLLU_REQUIRE_AUTH=1` las escrituras exigen token Bearer.

---

## 🚀 Arranque

```bash
unzip ayllu_quy_v3.zip && cd ayllu_quy_v3
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
SELFTEST=1 python app.py      # comprobaciones end-to-end
python seed_data.py --write   # sembrar Supabase (opcional)
```

### Acceso con dos roles

| Rol | Correo | Clave | Trabaja en |
|---|---|---|---|
| Docente | `docente@ayllu.pe` | `ayllu-docente` | Castellano |
| Estudiante | `estudiante@ayllu.pe` | `ayllu-estudiante` | Quechua ayacuchano |
| Estudiante | `marco@ayllu.pe` | `ayllu-estudiante` | Aimara |
| Estudiante | `sara@ayllu.pe` | `ayllu-estudiante` | Guaraní |

Abre **dos pestañas**: una como docente y otra como estudiante del mismo curso.
Lo que escribe una aparece traducido en la pantalla de la otra. Cada cuenta
declara su rol y su lengua en el token (`role`, `lang`).

---

## 🧭 Los módulos

| # | Módulo | Qué aporta al reto #06 | Rol |
|---|---|---|---|
| 1 | **Dashboard** | KPI de impacto (ayllukuna, simikuna activas, yachakuqkuna, eficacia chrF2, ganancia media) y cobertura por lengua. | Ambos |
| 2 | **Aula bilingüe** | El estudiante escribe en su lengua y recibe traducido lo que envía la profesora; su texto original nunca se modifica. | Estudiante |
| 3 | **Entrega y gestión** | El docente envía mensajes o documentos, ve qué llegó del aula, en qué lengua y con qué cobertura. | Docente |
| 4 | **Adaptador cultural** | Traduce y adapta con el glosario, resalta los términos y puntúa chrF2 / BERTScore / Flesch. | Docente |
| 5 | **Escáner de documentos** | Arrastra `.pdf` / `.txt`, extrae el texto y lo envía al Adaptador, a la Biblioteca o al aula. | Docente |
| 6 | **Comunidades** | Perfil sociocultural de 6 ayllukuna (andino, amazónico, chaqueño, urbano). | Ambos |
| 7 | **Mediciones** | 17 yachakuqkuna con recorrido pre/post y cohen d por cohorte y por simi. | Ambos |
| 8 | **Biblioteca** | 5 materiales base reutilizables; «Adaptar fragmento →» los envía al adaptador. | Ambos |
| 9 | **Analítica** | Cobertura, series diarias, nube de términos, TOP 10 chrF2 y alertas. | Docente |
| 10 | **Glosario** | 120 términos de demostración, búsqueda tolerante a typos e importación CSV masiva. | Docente |
| 11 | **Admin / Audit** | Feedback de hablantes nativos, estado de `/healthz` y trazabilidad. | Docente |

El menú se filtra por rol: el estudiante ve su aula, la biblioteca y las
mediciones; el docente ve la gestión, el adaptador, el escáner y la auditoría.

### 🔁 Flujo del aula (dos direcciones)

```
Docente (spa_Latn)  ──escribe/escribe o sube un .pdf──▶  Ayllu  ──▶  Estudiante (quy_Latn)
Estudiante (quy_Latn) ──escribe en su lengua────────▶  Ayllu  ──▶  Docente (spa_Latn)
```

- El texto que escribió cada persona se guarda **intacto** en `srcText`.
- La traducción que lee el destinatario se guarda en `outText`.
- `coverage` indica qué porcentaje del vocabulario cubrió el glosario y `chrF2`
  la similitud con la traducción base.

### 📄 Escáner de documentos

Acepta **sólo `.pdf` y `.txt`**, y la validación se hace dos veces: en el
navegador (extensión y tamaño) y en el servidor (extensión, tamaño y **bytes
mágicos** `%PDF-`). Un `.docx` renombrado a `.pdf` se rechaza con `415`; un PDF
escaneado devuelve `textless: true` y avisa de que necesita OCR. **Ningún archivo
se guarda en disco**.

---

## 🔌 API

**Autenticación:** `GET /api/auth/users` (directorio, sólo en modo demo),
`POST /api/auth/login`, `GET /api/auth/me`.

**Aula bilingüe:** `GET /api/aula/messages?userId=&role=`,
`POST /api/aula/messages`, `POST /api/aula/documents` (multipart `.pdf`/`.txt`),
`PUT /api/aula/messages/<id>/read`, `GET /api/aula/insights`.
Los mismos endpoints existen sin el prefijo del aula (`/api/messages`,
`/api/insights`).

**Lectura:** `/healthz`, `/api/dashboard`, `/api/languages`, `/api/lexicon`,
`/api/communities`, `/api/students`, `/api/glossary`, `/api/glossary/suggest`,
`/api/materials`, `/api/quality`, `/api/quality/score`, `/api/analytics`,
`/api/feedback`, `/api/activity`, `/api/search`, `/api/export/<tabla>.csv`.

**Escritura:** `POST/PUT/DELETE` sobre `communities`, `students`, `glossary`,
`materials`; `POST /api/glossary/import`; `POST /api/adapt`;
`POST /api/quality`; `POST /api/feedback`; `POST /api/admin/reset`.

**Escáner:** `GET /api/scan/limits` y `POST /api/scan` (multipart, campo `file`).

`POST /api/adapt` responde **exactamente 12 claves**: `adapted`, `cacheHit`,
`cacheId`, `context`, `degraded`, `flesch`, `glossary`, `level`,
`rawTranslation`, `scores`, `src`, `tgt`.

---

## ⚙️ Configuración

Copia `.env.example` a `.env`; la app carga ese archivo al iniciar. Nada es
obligatorio: sin variables la app arranca en **modo degradado** con la muhu en
memoria.

| Variable | Para qué |
|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY` | Persistencia real. Sin ellas, `MemoryStore`. |
| `GOOGLE_TIMEOUT`, `GOOGLE_MAX_RETRIES` | Tiempo y reintentos del motor público de Google. |
| `NLLB_API_URL`, `HF_API_URL`, `HF_API_TOKEN` | Respaldo NLLB. Sin motor externo disponible, glosa léxica. |
| `LLM_API_URL`, `LLM_API_KEY` | LLM adaptador externo. Sin él, adaptador por reglas. |
| `AYLLU_SECRET` | Secreto de firma JWT. **Cámbialo en producción.** |
| `AYLLU_DOCENTE_PASSWORD`, `AYLLU_ESTUDIANTE_PASSWORD` | Claves por rol. |
| `AYLLU_DEMO_LOGIN=0` | Deja de publicar el directorio de cuentas. |
| `AYLLU_REQUIRE_AUTH=1` | Exige token Bearer en las escrituras. |
| `AYLLU_MAX_UPLOAD_MB`, `PORT`, `FLASK_DEBUG` | Escáner y runtime. |

Esquema de base de datos: `schema_supabase.sql` (10 tablas + 8 índices).
Deploy: `render.yaml` define el Web Service Free con
`gunicorn app:app --bind 0.0.0.0:$PORT --timeout 60`.

`bert-score` es opcional porque instala dependencias pesadas. Si necesitas la
métrica real, instálalo por separado con `pip install bert-score`; sin él se
usa el proxy de vocabulario, identificado como tal en la respuesta.

---

## 🔬 Comprobación disponible

```
SELFTEST=1 python app.py
```

El comando ejecuta las comprobaciones end-to-end y muestra cuántas pasaron.

El self-test cubre la muhu, el CRUD, el contrato de 12 claves de `/api/adapt`,
la caché, las métricas, el escáner (TXT, PDF, rechazo de `.docx` con 415) y el
**flujo v3**: directorio de cuentas, login con dos roles —incluida la clave
incorrecta—, bandeja sembrada, traducción docente → estudiante, traducción
estudiante → docente, tablero de gestión y router `/api/aula/*`.

---

## 🚧 Limitaciones conocidas

1. La muhu lingüística es demostrativa y **requiere validación** de hablantes
   nativos antes de usarse en aula.
2. Sin `NLLB_API_URL`, la salida es una **glosa de vocabulario, no una
   traducción completa**: las palabras funcionales se conservan en castellano
   porque una glosa término a término no reproduce la morfología del quechua,
   el aimara ni el guaraní.
3. El proxy de BERTScore (`proxy-hashing`) sólo mide solapamiento de vocabulario.
4. La serie diaria de Analítica es demostrativa, no telemetría.
5. El escáner lee **capa de texto**: un PDF escaneado requiere OCR
   (por ejemplo `ocrmypdf`). No se inventa texto a partir de la imagen.
6. Límite de subida: **8 MB por archivo** (`AYLLU_MAX_UPLOAD_MB`).
7. Las claves demo se publican en modo demo: es el precio de un login usable en
   la sustentación, y está declarado en la propia pantalla.

---

## 📁 Estructura

```
ayllu_quy_v3/
├── app.py                  # Flask factory · router del aula · 40+ endpoints · self-test
├── core/
│   ├── __init__.py
│   ├── db.py               # SupabaseStore + MemoryStore (10 tablas)
│   ├── auth.py             # login con dos roles · JWT HS256 con la stdlib
│   ├── services.py         # AylluService · 27 métodos (CRUD + aula + métricas)
│   ├── docscanner.py       # escáner PDF/TXT: validación + extracción + métricas
│   └── seed.py             # muhu: 21 lenguas · 6 ayllukuna · 17 alumnos · 7 cuentas · bandeja
├── translator.py           # NLLB/Google por API + glosa léxica directa e inversa
├── cultural_adapter.py     # prompt blindado + LLM externo + reglas + gloss()
├── evaluator.py            # chrF2 · BERTScore · Flesch-FH · cohen d
├── supabase_client.py      # stub retrocompatible
├── seed_data.py            # CLI de siembra (incluye cuentas y bandeja)
├── requirements.txt · render.yaml · schema_supabase.sql · .env.example
├── prompt_ayllu.txt        # prompt regenerable v3
├── CAMBIOS_V2_1.txt · CAMBIOS_V3_0.txt
└── static/
    ├── index.html · favicon.svg
    ├── css/ayllu.css       # design system + bloque v3 del aula
    └── js/ayllu.js         # router hash · 10 vistas · sesión de dos roles · charts SVG
```

---

## 🆕 v4 · escáner multi-lengua, catálogo ampliado y varios docentes

Tres cambios sobre el núcleo v3, sin retirar nada de lo anterior:

1. **Escáner de documentos**: sigue aceptando arrastre de `.pdf` / `.txt`, pero
   ahora permite elegir **una o varias lenguas de destino** (selección múltiple
   agrupada en «Lenguas originarias» y «Otras lenguas»). Con lenguas elegidas el
   documento se traduce y queda en el aula, **una entrega por lengua**, con su
   cobertura y su chrF2; sin lenguas elegidas sólo se extrae el texto.
2. **Catálogo de lenguas**: pasa de 4 a **21** (quechua ayacuchano, cusqueño,
   ancashino y quichua ecuatoriano; aimara; guaraní; náhuatl; maya yucateco;
   castellano, inglés, portugués, francés, alemán, italiano, ruso, árabe, chino,
   japonés, coreano, hindi y suajili). Cada lengua declara su `code` FLORES-200,
   su `google` ISO, su `group` y si tiene columna en el glosario (`lexicon`).
3. **Varios profesores**: el directorio trae 3 docentes (Charlen, Rosa, Julián) y
   5 estudiantes. El escáner y el aula permiten **elegir a qué estudiante o a qué
   profesor** se entrega; por omisión se propone el interlocutor de la misma
   comunidad.

### Honestidad de la traducción

- Google Translate cubre las lenguas con código ISO; el quechua se pide como
  `qu`, que **no distingue variantes**: para las variantes la salida de Google es
  aproximada y se declara como tal.
- Sólo el quechua ayacuchano, el aimara y el guaraní tienen **léxico embebido**
  (glosa sin red). Para el resto, sin motor conectado, la entrega conserva el
  original y lo **declara en las notas** en lugar de presentarlo como traducción.
- Los PDF escaneados siguen requiriendo OCR: se avisa, no se inventa texto.

### Verificación ejecutada

```
python -m py_compile app.py core/*.py translator.py cultural_adapter.py evaluator.py
node --check static/js/ayllu.js
SELFTEST=1 python app.py     # asserts end-to-end, incluido el escáner multi-lengua
```

---

## 🆕 v5 · apartado de mensajería (docente ↔ estudiante)

Módulo nuevo **sin retirar nada** de lo anterior: la mensajería del aula.

### Qué añade

1. **Conversaciones**: directas (docente ↔ un estudiante) y **grupales**
   («Avisos para toda el aula»). El docente escribe a un estudiante o a varios a
   la vez; el estudiante responde a su profesor. El módulo lo ven **los dos
   roles** y el menú muestra los **mensajes sin leer**.
2. **Dos direcciones**: el docente escribe en castellano y el estudiante lee en
   su lengua; el estudiante escribe en su lengua y el docente lee castellano.
   El texto que escribió cada persona queda **intacto** en `srcText` y la
   traducción que lee el otro en `outText`.
3. **Botón «Traducir» para los dos roles**: cada mensaje trae su propio selector
   con las 21 lenguas del catálogo, así que el profesor y el estudiante pueden
   pedir cualquier lengua (no sólo la suya). La traducción queda guardada en el
   mensaje y la segunda petición se sirve de su caché.
4. **Documentos adjuntos `.pdf` / `.txt`**: se validan con el mismo escáner
   (extensión, bytes mágicos `%PDF-` y `AYLLU_MAX_UPLOAD_MB`), se traduce su
   texto y se descargan desde el propio mensaje. Un `.docx` renombrado se rechaza
   con `415`. **Ningún archivo se guarda en disco**: viaja en memoria.

### Arranque

```bash
unzip ayllu_quy_v5_FULL_multilengua_visor.zip && cd ayllu_quy_v3
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
SELFTEST=1 python app.py      # asserts end-to-end (incluye mensajería)
```

Abre **dos pestañas**: entra como docente en una y como estudiante en otra, abre
**Mensajería** y verás lo que escribe cada uno traducido al otro lado.

### Motores de traducción (nada obligatorio)

La cascada es la del núcleo y funciona **sin claves**: Google Translate público →
NLLB/Hugging Face si defines `HF_API_URL` + `HF_API_TOKEN` (o `NLLB_API_URL`) →
**glosa con el léxico embebido** cuando no hay red. Ninguna clave va en el código:
se leen del entorno (`.env`, ver `.env.example`). Si cae al léxico, la respuesta
llega con `degraded = true` y la interfaz lo declara como glosa.

### API de la mensajería

```
GET  /api/messaging/directory
GET  /api/messaging/threads?userId=
POST /api/messaging/threads
GET  /api/messaging/unread?userId=
GET  /api/messaging/threads/<id>/messages?userId=
POST /api/messaging/threads/<id>/messages
POST /api/messaging/threads/<id>/documents     # multipart: file, fromUserId, targets, level, title
POST /api/messaging/messages/<id>/translate    # userId, tgt, level
PUT  /api/messaging/messages/<id>/read
PUT  /api/messaging/threads/<id>/read
GET  /api/messaging/messages/<id>/attachment
```

### Verificación ejecutada

```
python -m py_compile app.py core/*.py translator.py cultural_adapter.py evaluator.py
node --check static/js/ayllu.js
SELFTEST=1 python app.py     # asserts end-to-end, incluida la mensajería
```

### Limitaciones de la mensajería

1. Las conversaciones sembradas y sus traducciones son **demostrativas**: no
   están validadas por hablantes nativos.
2. El adjunto viaja en la fila del mensaje (base64) porque el núcleo no escribe
   en disco: sirve para la demo, no para archivos muy grandes.
3. El texto traducido del adjunto se corta a 4000 caracteres por entrega; el
   texto extraído completo se guarda en el mensaje.
