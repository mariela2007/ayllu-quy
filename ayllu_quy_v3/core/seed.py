# Ayllu · núcleo v4 · escáner multi-lengua · catálogo 21 lenguas · varios docentes · ver CAMBIOS_V4_0.txt
"""Muhu embebida de Ayllu.

Permite que la SPA arranque completa (modo degradado) cuando Supabase no
está configurado o no responde.

AVISO DE HONESTIDAD: los textos en quechua/aimara/guaraní de esta muhu
son DEMOSTRATIVOS. Sirven para que la interfaz y las métricas se vean con
datos realistas, pero NO están validados por hablantes nativos y no deben
usarse como material didáctico definitivo.
"""

from __future__ import annotations

from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Simikuna del MVP (las 4 confirmadas en FLORES-200)
# --------------------------------------------------------------------------

LANGUAGES = [
    {
        "code": "spa_Latn",
        "name": "Español",
        "nativeName": "Castellano",
        "family": "Indoeuropea (romance)",
        "flores200": True,
        "speakers": "~600 M",
        "active": True,
        "group": "puente",
        "google": "es",
        "lexicon": True,
    },
    {
        "code": "quy_Latn",
        "name": "Quechua ayacuchano",
        "nativeName": "Runasimi",
        "family": "Quechua (quechumara)",
        "flores200": True,
        "speakers": "~1.0 M",
        "active": True,
        "group": "originaria",
        "google": "qu",
        "lexicon": True,
    },
    {
        "code": "quz_Latn",
        "name": "Quechua cusqueño",
        "nativeName": "Qusqu runasimi",
        "family": "Quechua (quechumara)",
        "flores200": True,
        "speakers": "~1.5 M",
        "active": True,
        "group": "originaria",
        "google": "qu",
        "lexicon": False,
    },
    {
        "code": "qub_Latn",
        "name": "Quechua ancashino",
        "nativeName": "Anqash qichwa",
        "family": "Quechua (quechumara)",
        "flores200": True,
        "speakers": "~0.9 M",
        "active": True,
        "group": "originaria",
        "google": "qu",
        "lexicon": False,
    },
    {
        "code": "quw_Latn",
        "name": "Quichua ecuatoriano",
        "nativeName": "Kichwa shimi",
        "family": "Quechua (quechumara)",
        "flores200": True,
        "speakers": "~0.5 M",
        "active": True,
        "group": "originaria",
        "google": "qu",
        "lexicon": False,
    },
    {
        "code": "ayr_Latn",
        "name": "Aimara",
        "nativeName": "Aymar aru",
        "family": "Aimara (quechumara)",
        "flores200": True,
        "speakers": "~1.7 M",
        "active": True,
        "group": "originaria",
        "google": "ay",
        "lexicon": True,
    },
    {
        "code": "grn_Latn",
        "name": "Guaraní",
        "nativeName": "Avañe'ẽ",
        "family": "Tupí-guaraní",
        "flores200": True,
        "speakers": "~6.5 M",
        "active": True,
        "group": "originaria",
        "google": "gn",
        "lexicon": True,
    },
    {
        "code": "nah_Latn",
        "name": "Náhuatl",
        "nativeName": "Nāhuatl",
        "family": "Uto-azteca",
        "flores200": True,
        "speakers": "~1.7 M",
        "active": True,
        "group": "originaria",
        "google": "nah",
        "lexicon": False,
    },
    {
        "code": "yua_Latn",
        "name": "Maya yucateco",
        "nativeName": "Maaya t'aan",
        "family": "Maya",
        "flores200": True,
        "speakers": "~0.8 M",
        "active": True,
        "group": "originaria",
        "google": "yua",
        "lexicon": False,
    },
    {
        "code": "eng_Latn",
        "name": "Inglés",
        "nativeName": "English",
        "family": "Indoeuropea (germánica)",
        "flores200": True,
        "speakers": "~1.5 B",
        "active": True,
        "group": "internacional",
        "google": "en",
        "lexicon": False,
    },
    {
        "code": "por_Latn",
        "name": "Portugués",
        "nativeName": "Português",
        "family": "Indoeuropea (romance)",
        "flores200": True,
        "speakers": "~260 M",
        "active": True,
        "group": "internacional",
        "google": "pt",
        "lexicon": False,
    },
    {
        "code": "fra_Latn",
        "name": "Francés",
        "nativeName": "Français",
        "family": "Indoeuropea (romance)",
        "flores200": True,
        "speakers": "~310 M",
        "active": True,
        "group": "internacional",
        "google": "fr",
        "lexicon": False,
    },
    {
        "code": "deu_Latn",
        "name": "Alemán",
        "nativeName": "Deutsch",
        "family": "Indoeuropea (germánica)",
        "flores200": True,
        "speakers": "~135 M",
        "active": True,
        "group": "internacional",
        "google": "de",
        "lexicon": False,
    },
    {
        "code": "ita_Latn",
        "name": "Italiano",
        "nativeName": "Italiano",
        "family": "Indoeuropea (romance)",
        "flores200": True,
        "speakers": "~68 M",
        "active": True,
        "group": "internacional",
        "google": "it",
        "lexicon": False,
    },
    {
        "code": "rus_Cyrl",
        "name": "Ruso",
        "nativeName": "Русский",
        "family": "Indoeuropea (eslava)",
        "flores200": True,
        "speakers": "~255 M",
        "active": True,
        "group": "internacional",
        "google": "ru",
        "lexicon": False,
    },
    {
        "code": "arb_Arab",
        "name": "Árabe",
        "nativeName": "العربية",
        "family": "Semítica",
        "flores200": True,
        "speakers": "~380 M",
        "active": True,
        "group": "internacional",
        "google": "ar",
        "lexicon": False,
    },
    {
        "code": "zho_Hans",
        "name": "Chino mandarín",
        "nativeName": "简体中文",
        "family": "Sino-tibetana",
        "flores200": True,
        "speakers": "~940 M",
        "active": True,
        "group": "internacional",
        "google": "zh-CN",
        "lexicon": False,
    },
    {
        "code": "jpn_Jpan",
        "name": "Japonés",
        "nativeName": "日本語",
        "family": "Japónica",
        "flores200": True,
        "speakers": "~125 M",
        "active": True,
        "group": "internacional",
        "google": "ja",
        "lexicon": False,
    },
    {
        "code": "kor_Hang",
        "name": "Coreano",
        "nativeName": "한국어",
        "family": "Coreana",
        "flores200": True,
        "speakers": "~80 M",
        "active": True,
        "group": "internacional",
        "google": "ko",
        "lexicon": False,
    },
    {
        "code": "hin_Deva",
        "name": "Hindi",
        "nativeName": "हिन्दी",
        "family": "Indoeuropea (indoaria)",
        "flores200": True,
        "speakers": "~610 M",
        "active": True,
        "group": "internacional",
        "google": "hi",
        "lexicon": False,
    },
    {
        "code": "swh_Latn",
        "name": "Suajili",
        "nativeName": "Kiswahili",
        "family": "Níger-congo",
        "flores200": True,
        "speakers": "~80 M",
        "active": True,
        "group": "internacional",
        "google": "sw",
        "lexicon": False,
    },
]

# Lenguas solicitadas con frecuencia que siguen FUERA del catálogo: ni el
# motor público (Google) ni FLORES-200 las cubren, así que no se ofrecen en el
# selector para no prometer una traducción que no existe.
EXCLUDED_LANGUAGES = [
    {"code": "arn_Latn", "name": "Mapudungun", "reason": "Sin motor disponible (ni Google ni FLORES-200)"},
    {"code": "cni_Latn", "name": "Asháninka", "reason": "Sin motor disponible (ni Google ni FLORES-200)"},
    {"code": "shp_Latn", "name": "Shipibo-konibo", "reason": "Sin motor disponible (ni Google ni FLORES-200)"},
]

# --------------------------------------------------------------------------
# Ayllukuna (6) — andino / amazónico / chaqueño / urbano
# --------------------------------------------------------------------------

COMMUNITIES = [
    {
        "name": "Comunidad de Ayacucho",
        "ecosystem": "andino",
        "langCode": "quy_Latn",
        "family": "Quechua",
        "altitude": 2761,
        "students": 3,
        "description": "Zona rural andina; la escuela trabaja con material en runasimi y castellano.",
    },
    {
        "name": "Comunidad de Puno",
        "ecosystem": "andino",
        "langCode": "ayr_Latn",
        "family": "Aimara",
        "altitude": 3827,
        "students": 4,
        "description": "Altiplano peruano-boliviano; mayoría aimara hablante en el aula.",
    },
    {
        "name": "Comunidad de Pucallpa",
        "ecosystem": "amazónico",
        "langCode": "grn_Latn",
        "family": "Tupí-guaraní",
        "altitude": 154,
        "students": 4,
        "description": "Selva baja; se usa guaraní paraguayo como lengua puente en el material demo.",
    },
    {
        "name": "Comunidad del Chaco boliviano",
        "ecosystem": "chaqueño",
        "langCode": "grn_Latn",
        "family": "Tupí-guaraní",
        "altitude": 420,
        "students": 2,
        "description": "Zona chaqueña; variante guaraní chaqueña en proceso de documentación.",
    },
    {
        "name": "Lima Norte (urbano)",
        "ecosystem": "urbano",
        "langCode": "quy_Latn",
        "family": "Quechua",
        "altitude": 154,
        "students": 2,
        "description": "Estudiantes migrantes de segunda generación; quechua como lengua de casa.",
    },
    {
        "name": "Santa Cruz urbano",
        "ecosystem": "urbano",
        "langCode": "grn_Latn",
        "family": "Tupí-guaraní",
        "altitude": 416,
        "students": 2,
        "description": "Colegio urbano bilingüe castellano-guaraní.",
    },
]

# --------------------------------------------------------------------------
# Yachakuqkuna (17) con medición pre / post
# --------------------------------------------------------------------------

_STUDENT_RAW = [
    ("Ana Quispe", 1, "quy_Latn", 42, 71, "A"),
    ("Luis Huamán", 1, "quy_Latn", 55, 78, "A"),
    ("Rosa Ccahuana", 1, "quy_Latn", 38, 66, "B"),
    ("Marco Condori", 2, "ayr_Latn", 47, 74, "A"),
    ("Elena Mamani", 2, "ayr_Latn", 51, 80, "A"),
    ("Julio Ticona", 2, "ayr_Latn", 33, 62, "B"),
    ("Nélida Choque", 2, "ayr_Latn", 60, 83, "B"),
    ("Sara Vásquez", 3, "grn_Latn", 44, 69, "A"),
    ("Iker Rengifo", 3, "grn_Latn", 49, 75, "A"),
    ("Dayana Panduro", 3, "grn_Latn", 36, 64, "B"),
    ("Kevin Ahuanari", 3, "grn_Latn", 58, 79, "B"),
    ("Mirian Yumbato", 4, "grn_Latn", 41, 70, "A"),
    ("Pablo Tórrez", 4, "grn_Latn", 52, 76, "A"),
    ("Andrea Cuéllar", 5, "quy_Latn", 45, 72, "A"),
    ("José Sullca", 5, "quy_Latn", 39, 67, "B"),
    ("Fiorela Chura", 6, "grn_Latn", 56, 81, "A"),
    ("Diego Salvatierra", 6, "grn_Latn", 48, 73, "B"),
]

STUDENTS = [
    {
        "name": name,
        "communityId": cid,
        "langCode": lang,
        "pre": pre,
        "post": post,
        "cohort": cohort,
        "attendance": 78 + ((i * 7) % 21),
    }
    for i, (name, cid, lang, pre, post, cohort) in enumerate(_STUDENT_RAW)
]

# --------------------------------------------------------------------------
# Glosario inicial (18 términos)
# --------------------------------------------------------------------------

# Léxico escolar castellano → quechua / aimara / guaraní.
# AVISO: vocabulario de uso común recopilado para la demostración; NO está
# validado por hablantes nativos (rikuy README · Limitaciones).
_GLOSSARY_RAW = [
    ("fracción", "t'aqalla", "t'aqa", "vore", "matemática"),
    ("ecuación", "kikinchay", "kikpa", "jeha", "matemática"),
    ("número", "yupay", "jakhu", "papapy", "matemática"),
    ("gravedad", "llasaq kay", "jasa", "pohýi", "física"),
    ("energía", "kallpa", "ch'ama", "mbarete", "física"),
    ("movimiento", "kuyuy", "unxtawi", "mýi", "física"),
    ("célula", "kawsaylla", "jakawina", "rete", "biología"),
    ("ecosistema", "kawsay pacha", "jakawi uraqi", "tekoha", "biología"),
    ("planta", "yura", "qura", "ka'avo", "biología"),
    ("semilla", "muhu", "muju", "ta'ỹi", "agricultura"),
    ("agua", "yaku", "uma", "y", "ciencias naturales"),
    ("tierra", "allpa", "uraqi", "yvy", "ciencias naturales"),
    ("sol", "inti", "willka", "kuarahy", "ciencias naturales"),
    ("luna", "killa", "phaxsi", "jasy", "ciencias naturales"),
    ("salud", "allin kay", "k'umara", "tesãi", "salud"),
    ("tiempo", "pacha", "pacha", "ara", "ciencias sociales"),
    ("comunidad", "ayllu", "marka", "tekojoja", "ciencias sociales"),
    ("estudiante", "yachakuq", "yatiqiri", "temimbo'e", "educación"),
    # ---- ampliación: entorno natural -------------------------------------
    ("río", "mayu", "jawira", "ysyry", "ciencias naturales"),
    ("lluvia", "para", "jallu", "ama", "ciencias naturales"),
    ("viento", "wayra", "wayra", "yvytu", "ciencias naturales"),
    ("fuego", "nina", "nina", "tata", "ciencias naturales"),
    ("piedra", "rumi", "qala", "ita", "ciencias naturales"),
    ("árbol", "sach'a", "khoka", "yvyra", "ciencias naturales"),
    ("flor", "t'ika", "panqara", "yvoty", "ciencias naturales"),
    ("hoja", "raphi", "laphi", "togue", "ciencias naturales"),
    ("raíz", "saphi", "saphi", "rapo", "ciencias naturales"),
    ("fruto", "ruru", "achu", "yva", "ciencias naturales"),
    ("maíz", "sara", "tunqu", "avati", "agricultura"),
    ("papa", "papa", "ch'uqi", "papa", "agricultura"),
    ("cerro", "urqu", "qullu", "yvyty", "ciencias naturales"),
    ("cielo", "hanaq pacha", "alax pacha", "yvága", "ciencias naturales"),
    ("estrella", "ch'aska", "warawara", "mbyja", "ciencias naturales"),
    ("luz", "kancha", "qhantati", "tesape", "física"),
    ("día", "punchaw", "uru", "ára", "ciencias sociales"),
    ("noche", "tuta", "aruma", "pyhare", "ciencias sociales"),
    ("año", "wata", "mara", "ary", "ciencias sociales"),
    ("campo", "chakra", "yapu", "kokue", "agricultura"),
    # ---- yachay wasi y sociedad ---------------------------------------------
    ("casa", "wasi", "uta", "óga", "ciencias sociales"),
    ("escuela", "yachay wasi", "yatiqaña uta", "mbo'ehao", "educación"),
    ("libro", "liwru", "liwru", "kuatia", "educación"),
    ("palabra", "simi", "aru", "ñe'ẽ", "educación"),
    ("lengua", "simi", "aru", "ñe'ẽ", "educación"),
    ("pueblo", "llaqta", "marka", "táva", "ciencias sociales"),
    ("camino", "ñan", "thaki", "tape", "ciencias sociales"),
    ("nombre", "suti", "suti", "téra", "ciencias sociales"),
    ("madre", "mama", "mama", "sy", "ciencias sociales"),
    ("padre", "tata", "tata", "túva", "ciencias sociales"),
    ("hijo", "wawa", "wawa", "ra'y", "ciencias sociales"),
    ("hermano", "wawqi", "jilata", "kyvy", "ciencias sociales"),
    ("hermana", "ñaña", "kullaka", "kypy'y", "ciencias sociales"),
    ("amigo", "masi", "masi", "angirũ", "ciencias sociales"),
    ("maestro", "yachachiq", "yatichiri", "mbo'ehára", "educación"),
    # ---- uywakuna y kurku humano ----------------------------------------
    ("animal", "uywa", "uywa", "mymba", "biología"),
    ("ave", "pisqu", "jamach'i", "guyra", "biología"),
    ("pez", "challwa", "challwa", "pira", "biología"),
    ("perro", "allqu", "anu", "jagua", "biología"),
    ("gato", "misi", "phisi", "mbarakaja", "biología"),
    ("cuerpo", "kurku", "janchi", "rete", "biología"),
    ("cabeza", "uma", "p'iqi", "akã", "biología"),
    ("ojo", "ñawi", "nayra", "tesa", "biología"),
    ("oreja", "rinri", "jinchu", "nambi", "biología"),
    ("boca", "simi", "laka", "juru", "biología"),
    ("nariz", "sinqa", "nasa", "tĩ", "biología"),
    ("mano", "maki", "ampara", "po", "biología"),
    ("pie", "chaki", "kayu", "py", "biología"),
    ("corazón", "sunqu", "chuyma", "ñe'ã", "biología"),
    ("sangre", "yawar", "wila", "tuguy", "biología"),
    ("hueso", "tullu", "ch'aka", "kangue", "biología"),
    ("piel", "qara", "lip'ichi", "pire", "biología"),
    ("vida", "kawsay", "jakaña", "tekove", "biología"),
    # ---- números ---------------------------------------------------------
    ("uno", "huk", "maya", "peteĩ", "matemática"),
    ("dos", "iskay", "paya", "mokõi", "matemática"),
    ("tres", "kimsa", "kimsa", "mbohapy", "matemática"),
    ("cuatro", "tawa", "pusi", "irundy", "matemática"),
    ("cinco", "pichqa", "phisqa", "po", "matemática"),
    ("seis", "suqta", "suqta", "poteĩ", "matemática"),
    ("siete", "qanchis", "paqallqu", "pokõi", "matemática"),
    ("ocho", "pusaq", "kimsaqallqu", "poapy", "matemática"),
    ("nueve", "isqun", "llätunka", "porundy", "matemática"),
    ("diez", "chunka", "tunka", "pa", "matemática"),
    ("contar", "yupay", "jakhuña", "papapy", "matemática"),
    # ---- adjetivos -------------------------------------------------------
    ("grande", "hatun", "jach'a", "tuicha", "lengua"),
    ("pequeño", "huch'uy", "jisk'a", "michĩ", "lengua"),
    ("nuevo", "musuq", "machaqa", "pyahu", "lengua"),
    ("bueno", "allin", "suma", "porã", "lengua"),
    ("malo", "mana allin", "jan wali", "vai", "lengua"),
    ("blanco", "yuraq", "janq'u", "morotĩ", "lengua"),
    ("negro", "yana", "ch'iyara", "hũ", "lengua"),
    ("rojo", "puka", "wila", "pytã", "lengua"),
    ("verde", "q'umir", "ch'uxña", "hovyũ", "lengua"),
    ("amarillo", "q'illu", "q'illu", "sa'yju", "lengua"),
    ("mucho", "achka", "walja", "heta", "lengua"),
    ("poco", "pisi", "juk'a", "sa'i", "lengua"),
    ("todo", "llapan", "taqi", "opa", "lengua"),
    # ---- verbos ----------------------------------------------------------
    ("hablar", "rimay", "parlaña", "ñe'ẽ", "lengua"),
    ("comer", "mikhuy", "manq'aña", "karu", "lengua"),
    ("beber", "upyay", "umaña", "y'u", "lengua"),
    ("caminar", "puriy", "saraña", "guata", "lengua"),
    ("ver", "rikuy", "uñjaña", "hecha", "lengua"),
    ("saber", "yachay", "yatiña", "kuaa", "lengua"),
    ("querer", "munay", "munaña", "hayhu", "lengua"),
    ("hacer", "ruway", "luraña", "japo", "lengua"),
    ("escribir", "qillqay", "qillqaña", "hai", "lengua"),
    ("leer", "ñawinchay", "ullaraña", "moñe'ẽ", "lengua"),
    ("aprender", "yachakuy", "yatiqaña", "ñembo'e", "educación"),
    ("enseñar", "yachachiy", "yatichaña", "mbo'e", "educación"),
    # ---- vocabulario que aparece en el material de demostración ----------
    ("subir", "wichay", "mantaña", "jupi", "ciencias naturales"),
    ("volver", "kutiy", "kuttiña", "jevy", "lengua"),
    ("vuelve", "kutiy", "kuttiña", "jevy", "lengua"),
    ("calentar", "q'uñichiy", "junt'uña", "hakukuaa", "física"),
    ("calienta", "q'uñichiy", "junt'uña", "hakukuaa", "física"),
    ("germinar", "phutuy", "phutiña", "chity", "biología"),
    ("húmedo", "ch'aran", "ch'alla", "nuku", "ciencias naturales"),
    ("compartir", "rak'iy", "chikaña", "moirũ", "ciencias sociales"),
    ("cosecha", "pallay", "pallaña", "tapegua", "agricultura"),
    ("parte", "rak'i", "chika", "pehẽ", "matemática"),
    ("repartir", "rak'iy", "chikaña", "moirũ", "matemática"),
    ("persona", "runa", "jaqi", "yvypóra", "ciencias sociales"),
    ("recibir", "chaskiy", "katuqaña", "pyhy", "ciencias sociales"),
]

GLOSSARY = [
    {
        "term": es,
        "langs": {"spa_Latn": es, "quy_Latn": quy, "ayr_Latn": ayr, "grn_Latn": grn},
        "domain": domain,
        "validated": False,
        "updatedBy": "semilla",
    }
    for (es, quy, ayr, grn, domain) in _GLOSSARY_RAW
    if es and quy and ayr and grn          # nunca introducir huecos: romperían la traducción
]

# --------------------------------------------------------------------------
# Biblioteca de materiales (5)
# --------------------------------------------------------------------------

MATERIALS = [
    {
        "title": "Lectura: el ciclo del agua",
        "kind": "lectura",
        "langCode": "grn_Latn",
        "level": "básico",
        "size": "3 pág.",
        "snippet": "El agua del río sube al cielo cuando el sol la calienta y vuelve como lluvia.",
    },
    {
        "title": "Ficha: fracciones con la papa",
        "kind": "ficha",
        "langCode": "quy_Latn",
        "level": "básico",
        "size": "2 pág.",
        "snippet": "Repartimos 8 papas entre 4 personas. ¿Cuántas toca a cada una?",
    },
    {
        "title": "Glosario escolar trilingüe",
        "kind": "glosario",
        "langCode": "spa_Latn",
        "level": "todos",
        "size": "18 términos",
        "snippet": "Términos base de matemática, física, biología y ciencias sociales.",
    },
    {
        "title": "Guía: el ecosistema de la chacra",
        "kind": "lectura",
        "langCode": "ayr_Latn",
        "level": "intermedio",
        "size": "5 pág.",
        "snippet": "La chacra es un ecosistema: la tierra, el agua y las plantas dependen entre sí.",
    },
    {
        "title": "Video: los números del 1 al 20",
        "kind": "video",
        "langCode": "grn_Latn",
        "level": "básico",
        "size": "4 min",
        "snippet": "Conteo bilingüe castellano-guaraní con apoyo visual de semillas.",
    },
]

# --------------------------------------------------------------------------
# Retroalimentación de hablantes nativos (3)
# --------------------------------------------------------------------------

FEEDBACK = [
    {
        "studentId": 1,
        "rating": 5,
        "note": "La ficha de fracciones se entendió al primer intento.",
        "reviewer": "Hab. nativo · quy",
    },
    {
        "studentId": 5,
        "rating": 4,
        "note": "Falta la palabra para «ecuación» en el glosario.",
        "reviewer": "Hab. nativo · ayr",
    },
    {
        "studentId": 9,
        "rating": 5,
        "note": "El ejemplo con la chacra funcionó muy bien.",
        "reviewer": "Hab. nativo · grn",
    },
]

# --------------------------------------------------------------------------
# Registro de adaptaciones (alimenta el leaderboard chrF2 y la nube)
# --------------------------------------------------------------------------

EVENTS = [
    {
        "kind": "adapt",
        "langCode": "grn_Latn",
        "snippet": "El agua del río sube al cielo",
        "chrF2": 83.1,
        "actor": "admin",
        "ts": "2026-10-01T14:02:00+00:00",
    },
    {
        "kind": "adapt",
        "langCode": "grn_Latn",
        "snippet": "Los números del 1 al 20",
        "chrF2": 80.7,
        "actor": "admin",
        "ts": "2026-10-01T14:20:00+00:00",
    },
    {
        "kind": "adapt",
        "langCode": "quy_Latn",
        "snippet": "Repartimos 8 papas entre 4 personas",
        "chrF2": 78.4,
        "actor": "admin",
        "ts": "2026-10-01T15:05:00+00:00",
    },
    {
        "kind": "adapt",
        "langCode": "grn_Latn",
        "snippet": "La semilla germina en la tierra húmeda",
        "chrF2": 75.6,
        "actor": "docente",
        "ts": "2026-10-01T18:41:00+00:00",
    },
    {
        "kind": "adapt",
        "langCode": "ayr_Latn",
        "snippet": "La gravedad hace caer los cuerpos",
        "chrF2": 71.9,
        "actor": "docente",
        "ts": "2026-10-02T09:12:00+00:00",
    },
    {
        "kind": "adapt",
        "langCode": "quy_Latn",
        "snippet": "Una fracción es una parte de un todo",
        "chrF2": 69.5,
        "actor": "admin",
        "ts": "2026-10-02T10:03:00+00:00",
    },
    {
        "kind": "adapt",
        "langCode": "ayr_Latn",
        "snippet": "La célula es la unidad de la vida",
        "chrF2": 66.2,
        "actor": "admin",
        "ts": "2026-10-02T11:37:00+00:00",
    },
]

# Serie demo de actividad diaria (14 días cerrados). Se documenta como demo
# en la interfaz y en el README: no proviene de telemetría real.
DAILY_ACTIVITY = [
    {"day": "2026-09-19", "adaptations": 3, "students": 1},
    {"day": "2026-09-20", "adaptations": 5, "students": 2},
    {"day": "2026-09-21", "adaptations": 2, "students": 1},
    {"day": "2026-09-22", "adaptations": 7, "students": 4},
    {"day": "2026-09-23", "adaptations": 6, "students": 3},
    {"day": "2026-09-24", "adaptations": 9, "students": 5},
    {"day": "2026-09-25", "adaptations": 4, "students": 2},
    {"day": "2026-09-26", "adaptations": 8, "students": 4},
    {"day": "2026-09-27", "adaptations": 11, "students": 6},
    {"day": "2026-09-28", "adaptations": 7, "students": 3},
    {"day": "2026-09-29", "adaptations": 12, "students": 6},
    {"day": "2026-09-30", "adaptations": 10, "students": 5},
    {"day": "2026-10-01", "adaptations": 14, "students": 7},
    {"day": "2026-10-02", "adaptations": 6, "students": 3},
]

# --------------------------------------------------------------------------
# Léxico ilustrativo para el traductor de respaldo (glosa término a término)
# --------------------------------------------------------------------------

# Lenguas que se traducen con el léxico embebido (columna del glosario).
# Las demás usan los motores externos (Google / NLLB) y, si no hay red, se
# declaran degradadas en lugar de inventar vocabulario.
LEXICON_LANGS = tuple(row["code"] for row in LANGUAGES if row.get("lexicon"))

LEXICON = {
    code: {
        row["term"]: row["langs"].get(code, "")
        for row in GLOSSARY
        if row["langs"].get(code)
    }
    for code in LEXICON_LANGS
}

LANG_NAME = {row["code"]: row["name"] for row in LANGUAGES}
LANG_BY_CODE = {row["code"]: row for row in LANGUAGES}
GOOGLE_CODE = {row["code"]: row["google"] for row in LANGUAGES if row.get("google")}

# Niveles de adaptación que acepta el aula y la mensajería.
LEVELS = ("básico", "intermedio", "avanzado")

# --------------------------------------------------------------------------
# Cuentas de la demo (dos roles)
# El docente trabaja en castellano; el estudiante escribe y lee en su lengua.
# AVISO: cuentas y claves de demostración, no de producción.
# --------------------------------------------------------------------------

USERS = [
    {
        "email": "docente@ayllu.pe",
        "password": "ayllu-docente",
        "role": "docente",
        "name": "Prof. Charlen Calero Huamán",
        "jobTitle": "Docente EIB · SENATI Huánuco",
        "langCode": "spa_Latn",
        "communityId": 1,
        "studentName": None,
    },
    {
        "email": "estudiante@ayllu.pe",
        "password": "ayllu-estudiante",
        "role": "estudiante",
        "name": "Ana Quispe",
        "jobTitle": "Estudiante · quechua ayacuchano",
        "langCode": "quy_Latn",
        "communityId": 1,
        "studentName": "Ana Quispe",
    },
    {
        "email": "marco@ayllu.pe",
        "password": "ayllu-estudiante",
        "role": "estudiante",
        "name": "Marco Condori",
        "jobTitle": "Estudiante · aimara",
        "langCode": "ayr_Latn",
        "communityId": 2,
        "studentName": "Marco Condori",
    },
    {
        "email": "sara@ayllu.pe",
        "password": "ayllu-estudiante",
        "role": "estudiante",
        "name": "Sara Vásquez",
        "jobTitle": "Estudiante · guaraní",
        "langCode": "grn_Latn",
        "communityId": 3,
        "studentName": "Sara Vásquez",
    },
    {
        "email": "yaku@ayllu.pe",
        "password": "ayllu-estudiante",
        "role": "estudiante",
        "name": "Yaku Quispe",
        "jobTitle": "Estudiante · quechua cusqueño",
        "langCode": "quz_Latn",
        "communityId": 1,
        "studentName": "Yaku Quispe",
    },
    # --- Más de un profesor: el aula permite elegir a quién se entrega ---------
    {
        "email": "rosa.docente@ayllu.pe",
        "password": "ayllu-docente",
        "role": "docente",
        "name": "Prof. Rosa Ancco Quispe",
        "jobTitle": "Docente EIB · aimara · Puno",
        "langCode": "spa_Latn",
        "communityId": 2,
        "studentName": None,
    },
    {
        "email": "julian.docente@ayllu.pe",
        "password": "ayllu-docente",
        "role": "docente",
        "name": "Prof. Julián Soria Méndez",
        "jobTitle": "Docente EIB · guaraní · Santa Cruz",
        "langCode": "spa_Latn",
        "communityId": 6,
        "studentName": None,
    },
]

# --------------------------------------------------------------------------
# Bandeja del aula (semilla). ``text`` es lo que escribe el REMITENTE.
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# v5 · Conversaciones de la mensajería (hilos docente ↔ estudiante).
# ``participants`` son correos de ``USERS``; el id del hilo es su posición 1..n.
# --------------------------------------------------------------------------

THREAD_SEED = [
    {
        "key": "quy",
        "title": "Aula · quechua ayacuchano",
        "participants": ["docente@ayllu.pe", "estudiante@ayllu.pe"],
        "communityId": 1,
    },
    {
        "key": "ayr",
        "title": "Aula · aimara",
        "participants": ["docente@ayllu.pe", "marco@ayllu.pe"],
        "communityId": 2,
    },
    {
        "key": "grn",
        "title": "Aula · guaraní",
        "participants": ["docente@ayllu.pe", "sara@ayllu.pe"],
        "communityId": 3,
    },
    {
        "key": "grupo",
        "title": "Avisos para toda el aula",
        "type": "group",
        "participants": [
            "docente@ayllu.pe",
            "estudiante@ayllu.pe",
            "marco@ayllu.pe",
            "sara@ayllu.pe",
            "yaku@ayllu.pe",
        ],
        "communityId": 1,
    },
]

# ``thread`` enlaza cada mensaje sembrado con su conversación de mensajería.
_MESSAGE_SEED = [
    {
        "fromEmail": "docente@ayllu.pe",
        "toEmail": "estudiante@ayllu.pe",
        "thread": "quy",
        "kind": "mensaje",
        "createdAt": "2026-10-05T13:10:00+00:00",
        "text": "Hola Ana, hoy veremos el agua del río y la semilla de la tierra.",
    },
    {
        "fromEmail": "estudiante@ayllu.pe",
        "toEmail": "docente@ayllu.pe",
        "thread": "quy",
        "kind": "mensaje",
        "createdAt": "2026-10-05T13:24:00+00:00",
        "text": "Profesora, mi casa está cerca del río y el camino de la escuela.",
    },
    {
        "fromEmail": "docente@ayllu.pe",
        "toEmail": "marco@ayllu.pe",
        "thread": "ayr",
        "kind": "material",
        "title": "Ficha de fracciones",
        "createdAt": "2026-10-06T09:05:00+00:00",
        "text": "Una fracción es una parte de un todo. Si repartimos una papa entre cuatro, cada parte es un cuarto.",
    },
    {
        "fromEmail": "docente@ayllu.pe",
        "toEmail": "sara@ayllu.pe",
        "thread": "grn",
        "kind": "mensaje",
        "createdAt": "2026-10-06T15:40:00+00:00",
        "text": "Hola Sara, mañana trabajamos con las plantas y el agua de la lluvia.",
    },
    {
        "fromEmail": "sara@ayllu.pe",
        "toEmail": "docente@ayllu.pe",
        "thread": "grn",
        "kind": "mensaje",
        "createdAt": "2026-10-06T16:02:00+00:00",
        "text": "Profesora, en mi casa hablamos de la tierra y del sol.",
    },
    {
        "fromEmail": "docente@ayllu.pe",
        "toEmail": "estudiante@ayllu.pe",
        "thread": "grupo",
        "kind": "material",
        "title": "Aviso: traer el cuaderno el lunes",
        "createdAt": "2026-10-07T11:00:00+00:00",
        "text": "Buenos días, el lunes trabajamos con el agua y las plantas: traigan el cuaderno y una semilla.",
    },
]


def _user_index(email: str) -> int:
    """Id numérico de una cuenta (USERS se inserta en orden → 1..n)."""
    for index, row in enumerate(USERS, start=1):
        if row["email"] == email:
            return index
    raise KeyError(email)


def _student_row(name):
    for row in STUDENTS:
        if row["name"] == name:
            return row
    return None


def _thread_index(key) -> int:
    """Id numérico de un hilo de la semilla (THREAD_SEED se inserta 1..n)."""
    for index, row in enumerate(THREAD_SEED, start=1):
        if row["key"] == key:
            return index
    return 0


def build_threads() -> list:
    """Conversaciones de la mensajería sembradas (ids 1..n en el almacén)."""
    rows = []
    for item in THREAD_SEED:
        participants = [_user_index(email) for email in item["participants"]]
        creator = _user_index(item["participants"][0])
        rows.append(
            {
                "title": item["title"],
                "type": item.get("type") or "direct",
                "createdBy": creator,
                "createdByName": (accounts_by_email().get(item["participants"][0]) or {}).get("name"),
                "participants": participants,
                "communityId": item.get("communityId"),
                "createdAt": item.get("createdAt") or "2026-10-05T13:00:00+00:00",
            }
        )
    return rows


def accounts_by_email() -> dict:
    return {row["email"]: row for row in USERS}


def build_messages() -> list:
    """Bandeja del aula, glosada con el mismo motor léxico que usa la aplicación.

    Dirección estudiante → docente: el estudiante escribe en su lengua (la glosa
    se construye con el léxico) y el docente lee la traducción al castellano.
    Dirección docente → estudiante: el texto castellano se traduce a la lengua
    del estudiante. Ninguna de estas líneas está validada por hablantes nativos:
    es material de demostración (rikuy README · Limitaciones).
    """
    # import absoluto: translator.py vive en la raíz del proyecto, no en core/
    import translator as _tr

    accounts = {row["email"]: row for row in USERS}
    rows = []
    for item in _MESSAGE_SEED:
        sender = accounts[item["fromEmail"]]
        recipient = accounts[item["toEmail"]]
        student = _student_row(recipient.get("studentName") or sender.get("studentName"))
        src, tgt = sender["langCode"], recipient["langCode"]
        text = item["text"]
        origin = ""
        if sender["role"] == "estudiante":
            origin = text
            text = _tr.fallback_translate(text, "spa_Latn", src).text
            out = _tr.fallback_translate(text, src, tgt).text
        else:
            out = _tr.fallback_translate(text, src, tgt).text
        rows.append(
            {
                "threadId": _thread_index(item.get("thread") or ""),
                "fromUserId": _user_index(item["fromEmail"]),
                "toUserId": _user_index(item["toEmail"]),
                "fromRole": sender["role"],
                "toRole": recipient["role"],
                "fromName": sender["name"],
                "toName": recipient["name"],
                "studentId": (student or {}).get("id"),
                "studentName": (student or {}).get("name") or recipient["name"],
                "kind": item.get("kind", "mensaje"),
                "title": item.get("title", ""),
                "src": src,
                "tgt": tgt,
                "srcText": text,
                "outText": out,
                "originEs": origin,
                "provider": "lexico-embebido",
                "degraded": True,
                "coverage": 0.0,
                "chrF2": 0.0,
                "glossary": [],
                "notes": ["Mensaje de demostración (semilla); requiere revisión de hablantes nativos."],
                "translations": {},
                "attachment": None,
                "readBy": [_user_index(item["fromEmail"])],
                "createdAt": item["createdAt"],
                "readAt": None,
            }
        )
    return rows


def now_iso() -> str:
    """Marca de pacha UTC en ISO-8601 con segundos."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
