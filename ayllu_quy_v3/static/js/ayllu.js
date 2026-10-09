/* ============================================================
   Ayllu · SPA v4 (router hash + 10 módulos + login de dos roles + i18n + visor de documento)
   Sin frameworks: 0 KB de dependencias de frontend.
   ============================================================ */
"use strict";

/* ------------------------------- utilidades ------------------------------- */

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  health: null,
  languages: [],
  communities: [],
  glossary: [],
  materials: [],
  students: [],
  theme: "dark",
  page: {},
  q: {},
  scanLimits: null,
  lastDoc: null,
  docs: [],
  scanTargets: [],
  libraryStudentId: null,
  scanPendingFile: null,
  session: null,
  demoUsers: [],
  aulaLocal: {},
  // v5 · mensajería
  msgThreads: [],
  msgThreadId: null,
  msgMessages: [],
  msgMore: {},
  msgDirLoaded: false,
  lang: "es",
  dict: {},
  fileSrc: null,
};

function esc(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmt(value, digits = 1) {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  return n.toFixed(digits);
}

/* ==========================================================================
   v4 · IDIOMA DE LA INTERFAZ (es / en / pt / qu)
   Traducción por diccionario: un JSON por lengua en /static/i18n/<código>.json.
   El castellano es la lengua base (el texto ya escrito en el código) y sólo se
   traduce el texto visible, nunca lo que escribe el usuario ni el contenido de
   los documentos.
   ========================================================================== */

const LANGS = [
  { code: "es", label: "Español" },
  { code: "en", label: "English" },
  { code: "pt", label: "Português" },
  { code: "qu", label: "Runasimi (Quechua)" },
];

/* Zonas que NUNCA se traducen: texto del usuario, documentos y código. */
const SKIP_I18N = "textarea,pre,code,script,style,.body,.doc-preview,.doc-full,.mono,mark,input,select.multi,[data-no-i18n]";

async function loadLang() {
  let saved = null;
  try { saved = localStorage.getItem("ayllu.lang"); } catch (err) { saved = null; }
  state.lang = LANGS.some((l) => l.code === saved) ? saved : "es";
  await loadDict();
  paintLangPicker();
}

async function loadDict() {
  state.dict = {};
  if (state.lang === "es") return;
  try {
    const response = await fetch("/static/i18n/" + state.lang + ".json", { cache: "no-store" });
    state.dict = response.ok ? await response.json() : {};
  } catch (err) {
    state.dict = {};
  }
}

/* Traduce una cadena exacta si está en el diccionario. */
function t(text) {
  if (text === null || text === undefined) return text;
  const key = String(text).trim();
  if (!key) return text;
  return state.dict[key] || text;
}

function paintLangPicker() {
  $$("[data-lang-select]").forEach((select) => {
    select.innerHTML = LANGS.map(
      (l) => '<option value="' + l.code + '"' + (l.code === state.lang ? " selected" : "") + ">" + esc(l.label) + "</option>"
    ).join("");
  });
}

function translateNode(node) {
  if (state.lang === "es" || !node) return;
  if (node.nodeType === 3) {
    const parent = node.parentElement;
    if (!parent || (parent.closest && parent.closest(SKIP_I18N))) return;
    const raw = node.nodeValue;
    const key = raw.trim();
    if (!key || key.length < 2) return;
    const hit = state.dict[key];
    if (hit) node.nodeValue = raw.replace(key, hit);
    return;
  }
  if (node.nodeType !== 1) return;
  if (node.closest && node.closest(SKIP_I18N)) return;
  ["placeholder", "title", "aria-label"].forEach((attr) => {
    const value = node.getAttribute ? node.getAttribute(attr) : null;
    if (!value) return;
    const hit = state.dict[value.trim()];
    if (hit) node.setAttribute(attr, hit);
  });
  const kids = node.childNodes || [];
  for (let i = 0; i < kids.length; i++) translateNode(kids[i]);
}

function applyI18n(root) {
  if (state.lang === "es") return;
  ["app", "login-overlay", "modal", "toasts"].forEach((id) => {
    const host = document.getElementById(id);
    if (host) translateNode(host);
  });
  if (root && root.nodeType) translateNode(root);
}

async function changeLang(code) {
  if (!LANGS.some((l) => l.code === code)) return;
  state.lang = code;
  try { localStorage.setItem("ayllu.lang", code); } catch (err) { /* almacenamiento bloqueado */ }
  await loadDict();
  paintLangPicker();
  const label = (LANGS.find((l) => l.code === code) || {}).label || code;
  paintLogin();
  paintWho();
  paintNav();
  applyI18n();
  await render();
  toast("Idioma de la interfaz: " + label, "ok", 2000);
}


async function api(path, options = {}) {
  const { method = "GET", body = null } = options;
  const init = { method, headers: {} };
  if (state.session && state.session.token) {
    init.headers["Authorization"] = "Bearer " + state.session.token;
  }
  if (body !== null) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (err) { data = { raw: text }; }
  if (!response.ok) {
    throw new Error((data && data.error) || ("HTTP " + response.status));
  }
  return data;
}

/* --------------------------------- toasts --------------------------------- */

function toast(message, kind = "ok", ttl = 3200) {
  const host = $("#toasts");
  const node = document.createElement("div");
  node.className = "toast " + kind;
  node.innerHTML = esc(t(message));
  host.appendChild(node);
  applyI18n(node);
  setTimeout(() => node.remove(), ttl);
}

/* --------------------------------- modal ---------------------------------- */

let modalSubmit = null;

function openModal(title, bodyHtml, footerHtml) {
  $("#modal-title").innerHTML = esc(title);
  $("#modal-body").innerHTML = bodyHtml;
  $("#modal-foot").innerHTML = footerHtml || "";
  $("#modal").hidden = false;
  applyI18n($("#modal"));
}

function closeModal() {
  $("#modal").hidden = true;
  $("#modal-body").innerHTML = "";
  $("#modal-foot").innerHTML = "";
  modalSubmit = null;
}

function confirmModal(title, message, onConfirm) {
  modalSubmit = onConfirm;
  openModal(
    title,
    '<div class="alert alert-warn"><strong>Atención</strong><span>' + esc(message) + "</span></div>",
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-danger" data-modal-confirm>Confirmar</button>'
  );
}

/* --------------------------------- charts --------------------------------- */

const PALETTE = ["#22d3ee", "#5eead4", "#a78bfa", "#fbbf24", "#34d399", "#f87171", "#60a5fa"];

function chartDonut(items, size = 148, thickness = 20) {
  const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0);
  if (!total) return '<div class="empty">Sin datos para graficar.</div>';
  const radius = (size - thickness) / 2;
  const cx = size / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = items.map((item, index) => {
    const share = Number(item.value || 0) / total;
    const length = share * circumference;
    const color = item.color || PALETTE[index % PALETTE.length];
    const arc =
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + radius + '" fill="none" stroke="' + color +
      '" stroke-width="' + thickness + '" stroke-dasharray="' + length.toFixed(2) + " " +
      (circumference - length).toFixed(2) + '" stroke-dashoffset="' + (-offset).toFixed(2) +
      '" transform="rotate(-90 ' + cx + " " + cx + ')"/>';
    offset += length;
    return arc;
  });
  const legend = items.map((item, index) =>
    '<div class="legend-item"><span class="legend-swatch" style="background:' +
    (item.color || PALETTE[index % PALETTE.length]) + '"></span>' + esc(item.label) +
    " · <b>" + esc(item.value) + "</b> (" + fmt((100 * item.value) / total, 0) + "%)</div>"
  ).join("");
  return (
    '<div class="donut-wrap"><svg class="spark" width="' + size + '" height="' + size +
    '" viewBox="0 0 ' + size + " " + size + '">' + arcs.join("") +
    '<text x="' + cx + '" y="' + (cx - 2) + '" text-anchor="middle" fill="currentColor" font-size="20" font-weight="700">' +
    total + '</text><text x="' + cx + '" y="' + (cx + 15) +
    '" text-anchor="middle" fill="currentColor" font-size="10" opacity=".6">total</text></svg>' +
    '<div class="legend">' + legend + "</div></div>"
  );
}

function chartBars(rows, unit = "") {
  if (!rows.length) return '<div class="empty">Sin datos para graficar.</div>';
  const max = Math.max.apply(null, rows.map((r) => Number(r.value || 0)).concat([1]));
  return (
    '<div class="chart-bars">' +
    rows.map((row) =>
      '<div class="bar-row"><span title="' + esc(row.label) + '">' + esc(row.label) +
      '</span><span class="bar-track"><span class="bar-fill" style="width:' +
      fmt((100 * Number(row.value || 0)) / max, 1) + '%"></span></span>' +
      '<span class="bar-value">' + esc(row.value) + esc(unit) + "</span></div>"
    ).join("") + "</div>"
  );
}

function chartSparkline(pre, post, width = 120, height = 30) {
  const clamp = (v) => Math.max(0, Math.min(100, Number(v) || 0));
  const y = (v) => height - (clamp(v) / 100) * (height - 4) - 2;
  const x1 = 4, x2 = width - 4;
  const rising = clamp(post) >= clamp(pre);
  const color = rising ? "#34d399" : "#f87171";
  return (
    '<svg class="spark" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + " " + height + '">' +
    '<line x1="' + x1 + '" y1="' + y(pre) + '" x2="' + x2 + '" y2="' + y(post) +
    '" stroke="' + color + '" stroke-width="2" stroke-linecap="round"/>' +
    '<circle cx="' + x1 + '" cy="' + y(pre) + '" r="2.6" fill="#9fb0c9"/>' +
    '<circle cx="' + x2 + '" cy="' + y(post) + '" r="3" fill="' + color + '"/></svg>'
  );
}

function chartCloud(terms) {
  if (!terms.length) return '<div class="empty">Aún no hay términos adaptados.</div>';
  const max = Math.max.apply(null, terms.map((t) => Number(t.count || 0)).concat([1]));
  return (
    '<div class="cloud">' +
    terms.map((t) => {
      const ratio = Number(t.count || 0) / max;
      const size = ratio > 0.75 ? "a" : ratio > 0.4 ? "b" : "c";
      return '<span class="' + size + '" title="' + esc(t.count) + ' adaptaciones">' + esc(t.term) + "</span>";
    }).join("") + "</div>"
  );
}

function scoreBand(chrf2) {
  const value = Number(chrf2 || 0);
  if (value >= 75) return "tag tag-ok";
  if (value >= 60) return "tag tag-warn";
  return "tag tag-bad";
}

/* ========================= v3 · SESIÓN Y DOS ROLES ======================== */

/* Dos roles: la docente trabaja en castellano; el estudiante lee y escribe en
   su lengua originaria. El rol y la lengua vienen del token de la sesión. */

const AUX_MODULES = [
  { id: "mensajeria",   label: "Mensajería · chat", icon: "mail",   count: () => msgUnreadTotal() },
  { id: "aula",         label: "Aula · actividades", icon: "list",   count: null },
  { id: "aula_docente", label: "Aula · docente", icon: "shield", count: null },
];

/* Contador total de mensajes sin leer (insignia del menú). */
function msgUnreadTotal() {
  return (state.msgThreads || []).reduce((sum, row) => sum + (row.unread || 0), 0) || null;
}

function isDocente() {
  return !!state.session && state.session.role === "docente";
}

function moduleVisible(id) {
  // La mensajería la ven los DOS roles: el docente escribe a estudiantes y el
  // estudiante responde a su profesor desde el mismo apartado.
  if (id === "mensajeria") return !!state.session;
  if (id === "aula") return !!state.session && !isDocente();
  if (id === "aula_docente") return isDocente();
  if (id === "adapt" || id === "scan" || id === "admin") return isDocente();
  return !!state.session;
}

function communityName(id) {
  const row = state.communities.find((c) => String(c.id) === String(id));
  return row ? row.name : "comunidad " + id;
}

function langLabel(code) {
  const row = state.languages.find((l) => l.code === code);
  return row ? row.name : (code || "—");
}

function paintWho() {
  const host = $("#who");
  const logoutBtn = $("#logout");
  if (!host) return;
  if (logoutBtn) logoutBtn.hidden = !state.session;
  if (!state.session) { host.innerHTML = ""; return; }
  const role = isDocente() ? "Docente" : "Estudiante";
  host.innerHTML =
    '<span class="role-chip role-' + esc(state.session.role) + '">' + esc(role) + "</span>" +
    "<span>" + esc(state.session.name) + "</span>" +
    '<span class="chip-lang">' + esc(state.session.langName || state.session.langCode) + "</span>" +
    (state.session.communityId
      ? '<span class="chip-lang">' + esc(communityName(state.session.communityId)) + "</span>"
      : "");
}

function paintLogin() {
  const overlay = $("#login-overlay");
  if (!overlay) return;
  const open = !state.session;
  overlay.hidden = !open;
  overlay.style.display = open ? "grid" : "none";
  document.body.style.overflow = open ? "hidden" : "";
  if (!open) return;
  const host = $("#login-roles");
  if (!host) return;
  const users = state.demoUsers || [];
  if (!users.length) {
    host.innerHTML = '<div class="empty">Escribe tu correo y tu clave para entrar.</div>';
    return;
  }
  host.innerHTML = users.map((user) =>
    '<button type="button" class="login-role is-' + esc(user.role) + '" data-login-email="' +
    esc(user.email) + '" data-login-pass="' + esc(user.password || "") + '">' +
    '<span class="role-chip role-' + esc(user.role) + '">' +
    (user.role === "docente" ? "Docente" : "Estudiante") + "</span>" +
    "<b>" + esc(user.name) + "</b>" +
    '<span class="muted">' + esc(user.email) + " · clave " + esc(user.password || "—") + "</span>" +
    '<span class="muted">Trabaja en ' + esc(user.langName || user.langCode) +
    (user.communityId ? " · " + esc(communityName(user.communityId)) : "") + "</span>" +
    "</button>"
  ).join("");
}

async function loadSession() {
  try {
    const data = await api("/api/aula/users");
    state.demoUsers = data.users || [];
  } catch (err) {
    state.demoUsers = [];
  }
  try {
    const raw = sessionStorage.getItem("ayllu.session");
    state.session = raw ? JSON.parse(raw) : null;
  } catch (err) {
    state.session = null;
  }
  if (!state.session) {
    try {
      const saved = localStorage.getItem("ayllu.email");
      const field = $("#login-email");
      if (saved && field) field.value = saved;
    } catch (err) { /* almacenamiento bloqueado: se ignora */ }
  }
  paintLogin();
  paintWho();
}

async function doLogin(email, password) {
  const error = $("#login-error");
  if (error) error.textContent = "";
  try {
    const session = await api("/api/auth/login", {
      method: "POST",
      body: { email: email, password: password },
    });
    state.session = session;
    try { sessionStorage.setItem("ayllu.session", JSON.stringify(session)); } catch (err) { /* ignorado */ }
    try { localStorage.setItem("ayllu.email", email); } catch (err) { /* ignorado */ }
    paintLogin();
    await loadCommon();
    paintWho();
    navigate(session.role === "docente" ? "dashboard" : "aula");
    await render();
    toast(
      "Hola " + session.name + " · rol " + session.role + " · " +
      (session.langName || session.langCode),
      "ok",
      4600
    );
  } catch (err) {
    if (error) error.textContent = err.message;
    toast("No se pudo entrar: " + err.message, "bad");
  }
}

function logout() {
  state.session = null;
  state.aulaLocal = {};
  try { sessionStorage.removeItem("ayllu.session"); } catch (err) { /* ignorado */ }
  paintLogin();
  paintWho();
  toast("Sesión cerrada", "ok", 1600);
}

/* -------------------------------- navegación ------------------------------ */

const MODULES = [
  { id: "dashboard",   label: "Dashboard",          icon: "grid",   count: null },
  { id: "adapt",       label: "Adaptador cultural", icon: "spark",  count: null },
  { id: "scan",        label: "Escáner de documentos", icon: "scan", count: () => state.docs.length },
  { id: "communities", label: "Comunidades",        icon: "globe",  count: () => state.communities.length },
  { id: "students",    label: "Mediciones",         icon: "chart",  count: () => state.students.length },
  { id: "library",     label: "Biblioteca",         icon: "book",   count: () => state.materials.length },
  { id: "analytics",   label: "Analítica",          icon: "pie",    count: null },
  { id: "glossary",    label: "Glosario",           icon: "list",   count: () => state.glossary.length },
  { id: "admin",       label: "Admin / Audit",      icon: "shield", count: null },
  ...AUX_MODULES,
];

const ICONS = {
  grid:  '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/>',
  globe: '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 12h16M12 4c2.6 2.4 1.6 13.6 0 16M12 4c-2.6 2.4-1.6 13.6 0 16" fill="none" stroke="currentColor" stroke-width="1.6"/>',
  chart: '<path d="M4 20V9M10 20V4M16 20v-7M22 20H2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  book:  '<path d="M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  pie:   '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 12V4M12 12l7 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  list:  '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  mail:  '<path d="M3 6.5h18v11H3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M3.5 7.5l8.5 5.5 8.5-5.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  shield:'<path d="M12 3l7 3v6c0 4.2-2.9 7.4-7 9-4.1-1.6-7-4.8-7-9V6z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  scan:  '<path d="M4 8V5.5A1.5 1.5 0 015.5 4H8M16 4h2.5A1.5 1.5 0 0120 5.5V8M20 16v2.5A1.5 1.5 0 0118.5 20H16M8 20H5.5A1.5 1.5 0 014 18.5V16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M4 12h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
};

function route() {
  const raw = (location.hash || "#/dashboard").replace(/^#\//, "");
  const id = MODULES.some((m) => m.id === raw) ? raw : "dashboard";
  return id;
}

function navigate(id) {
  location.hash = "#/" + id;
}

function paintNav() {
  const active = route();
  $("#nav").innerHTML = MODULES.filter((module) => moduleVisible(module.id)).map((module) => {
    const count = module.count ? module.count() : null;
    return (
      '<button class="nav-item' + (module.id === active ? " active" : "") +
      '" data-route="' + module.id + '" title="' + esc(module.label) + '">' +
      '<svg viewBox="0 0 24 24" width="18" height="18">' + ICONS[module.icon] + "</svg>" +
      '<span class="nav-label">' + esc(module.label) + "</span>" +
      (count === null ? "" : '<span class="nav-count">' + count + "</span>") +
      "</button>"
    );
  }).join("");
  const module = MODULES.find((m) => m.id === active);
  $("#crumb").textContent = module ? module.label : "Dashboard";
}

/* ------------------------------- carga de datos ---------------------------- */

async function loadCommon() {
  const [languages, communities, students, glossary, materials] = await Promise.all([
    api("/api/languages").then((r) => r.languages || []).catch(() => []),
    api("/api/communities").then((r) => r.communities || []).catch(() => []),
    api("/api/students").then((r) => r.students || []).catch(() => []),
    api("/api/glossary").then((r) => r.terms || []).catch(() => []),
    api("/api/materials").then((r) => r.materials || []).catch(() => []),
  ]);
  state.languages = languages;
  state.communities = communities;
  state.students = students;
  state.glossary = glossary;
  state.materials = materials;
  await loadMsgThreads();
}

/* Conversaciones del usuario en sesión (comparten la insignia del menú). */
async function loadMsgThreads() {
  if (!state.session) { state.msgThreads = []; return []; }
  try {
    const data = await api("/api/messaging/threads?userId=" + encodeURIComponent(state.session.userId));
    state.msgThreads = data.threads || [];
  } catch (err) {
    state.msgThreads = [];
  }
  return state.msgThreads;
}

function languageName(code) {
  const row = state.languages.find((l) => l.code === code);
  return row ? row.name : (code || "—");
}

/* =============================== MÓDULO 1 ================================ */

async function viewDashboard() {
  const data = await api("/api/dashboard");
  const k = data.kpis;
  const coverage = chartDonut(
    data.coverage.map((row) => ({ label: row.name, value: row.students })), 150, 20
  );
  const activity = (data.recent || []).map((event) =>
    '<div class="alert alert-accent"><span class="' + scoreBand(event.chrF2) + '">chrF2 ' +
    fmt(event.chrF2) + '</span><span style="flex:1">' + esc(event.snippet) + "</span>" +
    '<span class="muted mono">' + esc(languageName(event.langCode)) + "</span></div>"
  ).join("") || '<div class="empty">Aún no hay adaptaciones registradas.</div>';
  const excluded = (data.excluded || []).map((row) =>
    '<span class="tag tag-warn" title="' + esc(row.reason) + '">' + esc(row.name) + "</span>"
  ).join(" ");
  return (
    '<div class="page-head"><div><h2>Dashboard</h2><p>Impacto del proyecto en una vista: cobertura por lengua, ' +
    "eficacia del adaptador y actividad reciente con chrF2 en línea.</p></div>" +
    '<div class="page-actions"><button class="btn" data-route="adapt">Ir al adaptador</button>' +
    '<button class="btn" data-export="students">Exportar estudiantes CSV</button></div></div>' +
    '<div class="grid grid-kpi">' +
      kpi("Comunidades", k.communities, "andino · amazónico · chaqueño · urbano") +
      kpi("Lenguas activas", k.activeLanguages + " / " + k.languages, "de FLORES-200") +
      kpi("Estudiantes", k.students, "con medición pre/post") +
      kpi("Adaptaciones", k.adaptations, "registradas en el log") +
      kpi("Eficacia del adaptador", fmt(k.effectiveRate, 1) + "%", "chrF2 ≥ 60") +
      kpi("Ganancia media", "+" + fmt(k.avgGain, 1), "puntos pre → post") +
    "</div>" +
    '<div class="grid grid-2" style="margin-top:14px">' +
      '<div class="card"><div class="card-head"><h3>Cobertura por lengua</h3>' +
      '<span class="tag">' + k.glossaryTerms + " términos · " + k.materials + " materiales</span></div>" +
      coverage + "</div>" +
      '<div class="card"><div class="card-head"><h3>Actividad reciente</h3>' +
      '<span class="tag tag-accent">tiempo real</span></div>' + activity +
      '<div style="margin-top:12px"><small class="muted">Lenguas solicitadas fuera del MVP: </small>' +
      excluded + "</div></div>" +
    "</div>"
  );
}

function kpi(label, value, sub) {
  return (
    '<div class="card kpi"><span class="kpi-label">' + esc(label) + '</span>' +
    '<span class="kpi-value">' + esc(value) + '</span><span class="kpi-sub">' + esc(sub) + "</span></div>"
  );
}

/* =============================== MÓDULO 2 ================================ */

let lastAdapt = null;

async function viewAdapt() {
  const communities = state.communities.map((row) =>
    '<option value="' + row.id + '">' + esc(row.name) + " · " + esc(row.ecosystem) + "</option>"
  ).join("");
  const selectedStudent = state.students.find((s) => String(s.id) === String(state.libraryStudentId));
  const preferredTarget = (lastAdapt && lastAdapt.tgt) ||
    (selectedStudent && selectedStudent.langCode) ||
    (state.students.find((s) => s.langCode) || {}).langCode || "quy_Latn";
  const languages = state.languages
    .map((l) => '<option value="' + l.code + '"' + (l.code === preferredTarget ? " selected" : "") + '>' + esc(l.name) + " (" + esc(l.code) + ")</option>")
    .join("");
  return (
    '<div class="page-head"><div><h2>Adaptador cultural</h2><p>Traduce y adapta un fragmento entre cualquiera de ' +
    "las lenguas del catálogo, revisa el " +
    "antes/después con los términos del glosario resaltados y valida la calidad con chrF2, BERTScore y " +
    "legibilidad Fernández-Huerta.</p></div>" +
    '<div class="page-actions"><button class="btn" data-fill-demo>Usar ejemplo</button>' +
    '<button class="btn" data-route="library">Traer de biblioteca</button></div></div>' +
    '<div class="grid grid-2">' +
      '<div class="card"><h3>Entrada</h3>' +
      '<label class="field">Texto origen (castellano)<textarea id="adapt-text" placeholder="Escribe o pega el fragmento del material…">' +
      esc((lastAdapt && lastAdapt._src) || "") + "</textarea></label>" +
      '<div class="form-grid">' +
      '<label class="field">Lengua destino<select id="adapt-tgt">' + languages + "</select></label>" +
      (lastAdapt && lastAdapt.tgt ? "" : "") +
      '<label class="field">Nivel<select id="adapt-level"><option>básico</option><option>intermedio</option>' +
      "<option>avanzado</option></select></label>" +
      '<label class="field">Comunidad<select id="adapt-community">' + communities + "</select></label>" +
      "</div>" +
      '<div class="row"><button class="btn btn-primary" id="adapt-run">Adaptar y evaluar</button>' +
      '<button class="btn" id="adapt-prompt">Ver prompt blindado</button>' +
      '<button class="btn" id="adapt-feedback">Feedback de hablante</button></div></div>' +
      '<div class="card"><h3>Resultado</h3><div id="adapt-out">' +
      '<div class="empty">Aún no has adaptado nada. Pulsa «Adaptar y evaluar».</div></div></div>' +
    "</div>"
  );
}

function renderAdapt(result) {
  const glossary = (result.glossary || []).map((hit) =>
    '<span class="tag tag-accent" title="' + esc(hit.domain) + '">' + esc(hit.term) +
    (hit.target ? " → " + esc(hit.target) : "") + "</span>"
  ).join(" ");
  let adapted = esc(result.adapted);
  (result.glossary || []).forEach((hit) => {
    // los términos de 1 letra (p. ej. «y» = agua en guaraní) no se resaltan:
    // marcarían cada conjunción «y» del texto.
    if (hit.target && hit.target.trim().length >= 2) {
      adapted = adapted.split(esc(hit.target)).join("<mark>" + esc(hit.target) + "</mark>");
    }
  });
  const band = scoreBand(result.scores.chrF2);
  const scoreMarkup = result.evaluationAvailable === false
    ? '<div class="alert alert-warn" style="margin-top:12px"><strong>Evaluaci\u00f3n no disponible</strong><span>No se obtuvo una traducci\u00f3n autom\u00e1tica confiable para comparar. No se mostrara una puntuaci\u00f3n enga\u00f1osa.</span></div>'
    : '<div class="score-strip">' +
      scoreCell("chrF2", fmt(result.scores.chrF2, 2), band) +
      scoreCell("BERTScore", fmt(result.scores.BERTScore, 4) + "", "tag") +
      scoreCell("Flesch-FH", fmt(result.flesch, 1), "tag") +
      scoreCell("Cach\u00e9", result.cacheHit ? "HIT" : "MISS", "tag") +
      '</div><small class="muted">Las m\u00e9tricas comparan la adaptaci\u00f3n con el borrador autom\u00e1tico; no sustituyen la revisi\u00f3n de un hablante.</small>';
  return (
    '<div class="split"><div class="pane"><h4>Original</h4><div class="body">' +
    esc(lastAdapt && lastAdapt._src || "") + '</div></div>' +
    '<div class="pane"><h4>Adaptado · ' + esc(languageName(result.tgt)) + " · " + esc(result.level) +
    '</h4><div class="body">' + adapted + "</div></div></div>" +
    scoreMarkup +
    '<div class="row" style="margin-top:12px">' + (glossary || '<span class="muted">Sin términos del glosario en el fragmento.</span>') + "</div>" +
    '<div style="margin-top:12px"><small class="muted">Proveedor: ' + esc(result.provider || "—") +
    " · trazas: " + esc((result.notes || []).join(" ")) + "</small></div>" +
    '<div class="alert ' + (result.degraded ? "alert-warn" : "alert-ok") + '" style="margin-top:10px">' +
    "<strong>" + (result.degraded ? "Modo degradado" : "Modelos activos") + "</strong><span>" +
    (result.degraded
      ? "Se usó el traductor léxico y/o el adaptador por reglas: la salida requiere revisión de un hablante nativo."
      : "La salida autom\u00e1tica est\u00e1 lista para revisi\u00f3n docente.") +
    "</span></div>"
  );
}

function scoreCell(label, value, tagClass) {
  return (
    '<div class="score-cell"><span>' + esc(label) + "</span><b>" + esc(value) + "</b>" +
    '<div style="margin-top:6px"><span class="' + tagClass + '">' +
    (Number(value) >= 75 ? "ok" : Number(value) >= 60 ? "revisar" : "bajo") + "</span></div></div>"
  );
}

async function runAdapt() {
  const text = $("#adapt-text").value.trim();
  if (!text) { toast("Escribe un texto para adaptar", "warn"); return; }
  const button = $("#adapt-run");
  const payload = {
    text: text,
    src: "spa_Latn",
    tgt: $("#adapt-tgt").value,
    level: $("#adapt-level").value,
    communityId: Number($("#adapt-community").value || 0),
  };
  if (button) { button.disabled = true; button.textContent = "Adaptando…"; }
  $("#adapt-out").innerHTML = '<div class="empty">Traduciendo y adaptando…</div>';
  try {
    const result = await api("/api/adapt", { method: "POST", body: payload });
    lastAdapt = Object.assign({}, result, { _src: text });
    $("#adapt-out").innerHTML = renderAdapt(result);
    const tgtOption = document.querySelector("#adapt-tgt option:checked");
    const tgtName = tgtOption ? tgtOption.textContent.replace(/\s*\([^)]*\)\s*$/, "") : result.tgt;
    if (result.evaluationAvailable === false) {
      toast("No se obtuvo una traducci\u00f3n confiable a " + tgtName + "; se conserva el original.", "warn", 5200);
    } else {
      toast(
        "Adaptado a " + tgtName + " - similitud chrF2 " + fmt(result.scores.chrF2, 2),
        result.degraded ? "warn" : "ok",
        4600
      );
    }
    if (result.translationDegraded || result.evaluationAvailable === false) {
      const count = Number(result.lexiconSize || 0);
      toast(count
        ? "El traductor en l\u00ednea no respondi\u00f3. Se aplic\u00f3 el l\u00e9xico de respaldo (" + count + " t\u00e9rminos); requiere revisi\u00f3n."
        : "El traductor en l\u00ednea no respondi\u00f3 y no hay vocabulario para esta variante. Se conserv\u00f3 el original.",
        "warn", 6200);
    }
  } catch (err) {
    $("#adapt-out").innerHTML = '<div class="alert alert-bad"><strong>Error</strong><span>' + esc(err.message) + "</span></div>";
    toast(err.message, "bad");
  } finally {
    if (button) { button.disabled = false; button.textContent = "Adaptar y evaluar"; }
  }
}

function promptModal() {
  openModal(
    "Prompt blindado",
    '<div id="prompt-out"><div class="empty">Generando el prompt…</div></div>',
    '<button class="btn btn-ghost" data-modal-cancel>Cerrar</button>'
  );
  const text = ($("#adapt-text") && $("#adapt-text").value.trim()) || "";
  const payload = {
    text: text,
    src: "spa_Latn",
    tgt: $("#adapt-tgt") ? $("#adapt-tgt").value : "quy_Latn",
    level: $("#adapt-level") ? $("#adapt-level").value : "básico",
    communityId: $("#adapt-community") ? Number($("#adapt-community").value || 0) : 0,
  };
  api("/api/prompt", { method: "POST", body: payload })
    .then((data) => {
      const out = $("#prompt-out");
      if (!out) return;
      out.innerHTML =
        '<div class="chips"><span class="tag tag-accent">' + esc(data.src) + " → " + esc(data.tgt) + "</span>" +
        '<span class="tag">nivel ' + esc(data.level) + "</span>" +
        '<span class="tag">' + esc(data.glossarySize) + " términos restringidos por el glosario</span>" +
        (data.community ? '<span class="tag">' + esc(data.community) + "</span>" : "") + "</div>" +
        '<div class="prompt-box">' + esc(data.prompt) + "</div>";
    })
    .catch((err) => {
      const out = $("#prompt-out");
      if (out) {
        out.innerHTML = '<div class="alert alert-bad"><strong>Error</strong><span>' + esc(err.message) + "</span></div>";
      }
    });
}

/* =============================== MÓDULO 3 ================================ */

async function viewCommunities() {
  const rows = state.communities.map((row) =>
    "<tr><td><b>" + esc(row.name) + "</b><div class=\"muted\">" + esc(row.description || "") + "</div></td>" +
    '<td><span class="tag">' + esc(row.ecosystem) + "</span></td>" +
    "<td>" + esc(languageName(row.langCode)) + "</td>" +
    "<td>" + esc(row.family || "—") + "</td>" +
    "<td>" + esc(row.altitude) + " m</td>" +
    '<td><span class="tag tag-accent">' + esc(row.studentCount) + "</span></td>" +
    '<td><div class="actions"><button class="btn btn-sm" data-edit-community="' + row.id +
    '">Editar</button><button class="btn btn-sm btn-danger" data-del-community="' + row.id + '">Borrar</button></div></td></tr>'
  ).join("");
  return (
    '<div class="page-head"><div><h2>Comunidades</h2><p>Perfil sociocultural de cada comunidad: ecosistema, ' +
    "lengua, familia lingüística y altitud. Cada lengua se enseña con su contexto, no en abstracto.</p></div>" +
    '<div class="page-actions"><button class="btn btn-primary" data-new-community>Nueva comunidad</button>' +
    '<button class="btn" data-export="communities">Exportar CSV</button></div></div>' +
    '<div class="table-wrap"><table><thead><tr><th>Comunidad</th><th>Ecosistema</th><th>Lengua</th>' +
    "<th>Familia</th><th>Altitud</th><th>Alumnos</th><th></th></tr></thead><tbody>" +
    rows + "</tbody></table></div>"
  );
}

function communityForm(row) {
  row = row || {};
  const langs = state.languages.map((l) =>
    '<option value="' + l.code + '"' + (row.langCode === l.code ? " selected" : "") + ">" + esc(l.name) + "</option>"
  ).join("");
  const ecosystems = ["andino", "amazónico", "chaqueño", "urbano"].map((e) =>
    '<option value="' + e + '"' + (row.ecosystem === e ? " selected" : "") + ">" + e + "</option>"
  ).join("");
  return (
    '<label class="field">Nombre<input type="text" id="f-name" value="' + esc(row.name || "") + '"></label>' +
    '<div class="form-grid">' +
    '<label class="field">Ecosistema<select id="f-ecosystem">' + ecosystems + "</select></label>" +
    '<label class="field">Lengua<select id="f-lang">' + langs + "</select></label>" +
    '<label class="field">Familia lingüística<input type="text" id="f-family" value="' + esc(row.family || "") + '"></label>' +
    '<label class="field">Altitud (m)<input type="number" id="f-altitude" value="' + esc(row.altitude || 0) + '"></label>' +
    "</div>" +
    '<label class="field">Descripción<textarea id="f-description" style="min-height:90px">' + esc(row.description || "") + "</textarea></label>"
  );
}

function communityModal(row) {
  const editing = !!row;
  modalSubmit = async () => {
    const payload = {
      name: $("#f-name").value.trim(),
      ecosystem: $("#f-ecosystem").value,
      langCode: $("#f-lang").value,
      family: $("#f-family").value.trim(),
      altitude: Number($("#f-altitude").value || 0),
      description: $("#f-description").value.trim(),
    };
    if (!payload.name) { toast("El nombre es obligatorio", "warn"); return; }
    try {
      if (editing) { await api("/api/communities/" + row.id, { method: "PUT", body: payload }); }
      else { await api("/api/communities", { method: "POST", body: payload }); }
      closeModal();
      await refresh("communities");
      toast(editing ? "Comunidad actualizada" : "Comunidad creada", "ok");
    } catch (err) { toast(err.message, "bad"); }
  };
  openModal(
    editing ? "Editar comunidad" : t("Nueva comunidad"),
    communityForm(row),
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Guardar</button>'
  );
}

/* =============================== MÓDULO 4 ================================ */

async function viewStudents() {
  const quality = await api("/api/quality");
  const perPage = 10;
  const page = state.page.students || 1;
  const slice = state.students.slice((page - 1) * perPage, page * perPage);
  const rows = slice.map((row) =>
    "<tr><td>" + esc(row.name) + '</td><td><span class="tag">' + esc(row.communityName) + "</span></td>" +
    "<td>" + esc(row.cohort) + "</td><td class=\"mono\">" + esc(row.pre) + "</td>" +
    '<td class="mono">' + esc(row.post) + "</td>" +
    '<td class="mono" style="color:' + (row.delta >= 0 ? "var(--ok)" : "var(--bad)") + '">' +
    (row.delta >= 0 ? "+" : "") + fmt(row.delta) + "</td>" +
    "<td>" + chartSparkline(row.pre, row.post) + "</td>" +
    '<td><div class="actions"><button class="btn btn-sm" data-edit-student="' + row.id + '">Editar</button>' +
    '<button class="btn btn-sm btn-danger" data-del-student="' + row.id + '">Borrar</button></div></td></tr>'
  ).join("");
  const totalPages = Math.max(1, Math.ceil(state.students.length / perPage));
  const languages = chartBars(
    quality.perLanguage.map((row) => ({ label: row.name, value: row.postAvg })), ""
  );
  const cohorts = quality.cohorts.map((row) =>
    '<div class="alert ' + (row.cohenD >= 0.8 ? "alert-ok" : row.cohenD >= 0.5 ? "alert-accent" : "alert-warn") +
    '"><strong>Cohorte ' + esc(row.cohort) + "</strong><span>n=" + esc(row.students) +
    " · Δ" + fmt(row.delta) + " puntos</span>" +
    '<span class="tag">' + esc(row.label) + " · d=" + fmt(row.cohenD, 2) + "</span></div>"
  ).join("");
  return (
    '<div class="page-head"><div><h2>Mediciones</h2><p>Evidencia numérica para el docente: recorrido pre/post ' +
    "por estudiante, promedio por lengua y tamaño de efecto (cohen d) por cohorte.</p></div>" +
    '<div class="page-actions"><button class="btn btn-primary" data-new-student>Nuevo estudiante</button>' +
    '<button class="btn" data-export="students">Exportar CSV</button></div></div>' +
    '<div class="grid grid-3">' +
      kpi(t("Estudiantes"), quality.students, "en 6 comunidades") +
      kpi("Promedio pre → post", fmt(quality.preAvg) + " → " + fmt(quality.postAvg), "escala 0-100") +
      kpi("Tamaño de efecto", fmt(quality.cohenD, 2), quality.label) +
    "</div>" +
    '<div class="grid grid-2" style="margin-top:14px">' +
      '<div class="card"><h3>Promedio post por lengua</h3>' + languages + "</div>" +
      '<div class="card"><h3>Impacto por cohorte</h3>' + cohorts +
      '<div style="margin-top:10px"><small class="muted">' + esc(quality.legend.join(" · ")) + "</small></div></div>" +
    "</div>" +
    '<h3 style="margin:20px 0 10px">Recorrido individual</h3>' +
    '<div class="table-wrap"><table><thead><tr><th>Estudiante</th><th>Comunidad</th><th>Cohorte</th>' +
    "<th>Pre</th><th>Post</th><th>Δ</th><th>Recorrido</th><th></th></tr></thead><tbody>" +
    (rows || '<tr><td colspan="8"><div class="empty">Sin estudiantes.</div></td></tr>') +
    "</tbody></table></div>" +
    '<div class="pager"><button class="btn btn-sm" data-page="students" data-dir="-1"' +
    (page <= 1 ? " disabled" : "") + ">Anterior</button><span>página " + page + " de " + totalPages +
    '</span><button class="btn btn-sm" data-page="students" data-dir="1"' +
    (page >= totalPages ? " disabled" : "") + ">Siguiente</button></div>"
  );
}

function studentForm(row) {
  row = row || {};
  const communities = state.communities.map((c) =>
    '<option value="' + c.id + '"' + (row.communityId === c.id ? " selected" : "") + ">" + esc(c.name) + "</option>"
  ).join("");
  const langs = state.languages.filter((l) => l.code !== "spa_Latn").map((l) =>
    '<option value="' + l.code + '"' + (row.langCode === l.code ? " selected" : "") + ">" + esc(l.name) + "</option>"
  ).join("");
  return (
    '<label class="field">Nombre<input type="text" id="f-name" value="' + esc(row.name || "") + '"></label>' +
    '<div class="form-grid">' +
    '<label class="field">Comunidad<select id="f-community">' + communities + "</select></label>" +
    '<label class="field">Lengua<select id="f-lang">' + langs + "</select></label>" +
    '<label class="field">Cohorte<input type="text" id="f-cohort" value="' + esc(row.cohort || "A") + '"></label>' +
    '<label class="field">Pre<input type="number" id="f-pre" value="' + esc(row.pre || 0) + '"></label>' +
    '<label class="field">Post<input type="number" id="f-post" value="' + esc(row.post || 0) + '"></label>' +
    '<label class="field">Asistencia (%)<input type="number" id="f-attendance" value="' + esc(row.attendance || 0) + '"></label>' +
    "</div>"
  );
}

function studentModal(row) {
  const editing = !!row;
  modalSubmit = async () => {
    const payload = {
      name: $("#f-name").value.trim(),
      communityId: Number($("#f-community").value || 1),
      langCode: $("#f-lang").value,
      cohort: $("#f-cohort").value.trim(),
      pre: Number($("#f-pre").value || 0),
      post: Number($("#f-post").value || 0),
      attendance: Number($("#f-attendance").value || 0),
    };
    if (!payload.name) { toast("El nombre es obligatorio", "warn"); return; }
    try {
      if (editing) { await api("/api/students/" + row.id, { method: "PUT", body: payload }); }
      else { await api("/api/students", { method: "POST", body: payload }); }
      closeModal();
      await refresh("students");
      toast(editing ? "Medición actualizada" : "Estudiante creado", "ok");
    } catch (err) { toast(err.message, "bad"); }
  };
  openModal(
    editing ? "Editar medición" : t("Nuevo estudiante"),
    studentForm(row),
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Guardar</button>'
  );
}

/* =============================== MÓDULO 5 ================================ */

async function viewLibrary() {
  const studentsWithLanguage = state.students.filter((student) => student.langCode);
  if (!studentsWithLanguage.some((student) => String(student.id) === String(state.libraryStudentId))) {
    state.libraryStudentId = studentsWithLanguage.length ? studentsWithLanguage[0].id : null;
  }
  const studentOptions = studentsWithLanguage.map((student) =>
    '<option value="' + esc(student.id) + '"' + (String(student.id) === String(state.libraryStudentId) ? " selected" : "") + '>' +
    esc(student.name) + " · " + esc(languageName(student.langCode)) + "</option>"
  ).join("");
  const grid = state.materials.map((row) =>
    '<div class="card"><div class="card-head"><h3>' + esc(row.title) + "</h3>" +
    '<span class="tag">' + esc(row.kind) + "</span></div>" +
    '<p class="muted" style="min-height:44px">' + esc(row.snippet) + "</p>" +
    '<div class="row"><span class="tag tag-accent">' + esc(languageName(row.langCode)) + "</span>" +
    '<span class="tag">' + esc(row.level) + "</span><span class=\"tag\">" + esc(row.size) + "</span></div>" +
    '<div class="row" style="margin-top:12px">' +
    '<button class="btn btn-sm btn-primary" data-adapt-material="' + row.id + '">Adaptar fragmento →</button>' +
    '<button class="btn btn-sm" data-edit-material="' + row.id + '">Editar</button>' +
    '<button class="btn btn-sm btn-danger" data-del-material="' + row.id + '">Borrar</button>' +
    "</div></div>"
  ).join("");
  return (
    '<div class="page-head"><div><h2>Biblioteca</h2><p>Materiales base reutilizables. El botón «Adaptar fragmento» ' +
    "envía el texto directamente al Adaptador cultural.</p></div>" +
    '<div class="page-actions"><button class="btn btn-primary" data-new-material>Nuevo material</button>' +
    '<button class="btn" data-export="materials">Exportar CSV</button></div></div>' +
    '<div class="card" style="margin-bottom:16px"><label class="field">Adaptar para este estudiante' +
    '<select id="library-student"' + (studentsWithLanguage.length ? "" : " disabled") + '>' +
    (studentOptions || '<option value="">No hay estudiantes con idioma asignado</option>') +
    '</select><span class="muted">La lengua de su perfil queda seleccionada como destino. Puedes cambiarla antes de evaluar.</span></label></div>' +
    '<div class="grid grid-3">' + (grid || '<div class="empty">Biblioteca vacía.</div>') + "</div>"
  );
}

function materialForm(row) {
  row = row || {};
  const kinds = ["lectura", "ficha", "glosario", "video", "audio"].map((k) =>
    '<option value="' + k + '"' + (row.kind === k ? " selected" : "") + ">" + k + "</option>"
  ).join("");
  const langs = state.languages.map((l) =>
    '<option value="' + l.code + '"' + (row.langCode === l.code ? " selected" : "") + ">" + esc(l.name) + "</option>"
  ).join("");
  const levels = ["básico", "intermedio", "avanzado", "todos"].map((k) =>
    '<option value="' + k + '"' + (row.level === k ? " selected" : "") + ">" + k + "</option>"
  ).join("");
  return (
    '<label class="field">Título<input type="text" id="f-title" value="' + esc(row.title || "") + '"></label>' +
    '<div class="form-grid">' +
    '<label class="field">Tipo<select id="f-kind">' + kinds + "</select></label>" +
    '<label class="field">Lengua<select id="f-lang">' + langs + "</select></label>" +
    '<label class="field">Nivel<select id="f-level">' + levels + "</select></label>" +
    '<label class="field">Tamaño<input type="text" id="f-size" value="' + esc(row.size || "") + '"></label>' +
    "</div>" +
    '<label class="field">Fragmento<textarea id="f-snippet" style="min-height:110px">' + esc(row.snippet || "") + "</textarea></label>"
  );
}

function materialModal(row) {
  const editing = !!row;
  modalSubmit = async () => {
    const payload = {
      title: $("#f-title").value.trim(),
      kind: $("#f-kind").value,
      langCode: $("#f-lang").value,
      level: $("#f-level").value,
      size: $("#f-size").value.trim(),
      snippet: $("#f-snippet").value.trim(),
    };
    if (!payload.title) { toast("El título es obligatorio", "warn"); return; }
    try {
      if (editing) { await api("/api/materials/" + row.id, { method: "PUT", body: payload }); }
      else { await api("/api/materials", { method: "POST", body: payload }); }
      closeModal();
      await refresh("library");
      toast(editing ? "Material actualizado" : "Material creado", "ok");
    } catch (err) { toast(err.message, "bad"); }
  };
  openModal(
    editing ? "Editar material" : t("Nuevo material"),
    materialForm(row),
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Guardar</button>'
  );
}

/* =============================== MÓDULO 6 ================================ */

async function viewAnalytics() {
  const data = await api("/api/analytics");
  const donut = chartDonut(
    data.coverage.map((row) => ({ label: row.name, value: row.students })), 150, 20
  );
  const daily = chartBars(data.daily.map((d) => ({ label: d.day.slice(5), value: d.adaptations })));
  const leader = data.leaderboard.map((row, index) =>
    "<tr><td class=\"mono\">" + (index + 1) + "</td><td>" + esc(row.snippet) + "</td>" +
    "<td>" + esc(languageName(row.langCode)) + '</td><td><span class="' + scoreBand(row.chrF2) + '">' +
    fmt(row.chrF2, 2) + "</span></td><td>" + esc(row.actor) + "</td></tr>"
  ).join("");
  const alerts = data.alerts.map((row) =>
    '<div class="alert alert-' + esc(row.level) + '"><strong>' + esc(row.level.toUpperCase()) +
    "</strong><span>" + esc(row.text) + "</span></div>"
  ).join("");
  return (
    '<div class="page-head"><div><h2>Analítica</h2><p>Vista para el jurado técnico: cobertura, series de ' +
    "actividad, términos más adaptados, mejores resultados y alertas operacionales.</p></div>" +
    '<div class="page-actions"><span class="tag tag-accent">chrF2 medio ' + fmt(data.avgChrF2, 2) + "</span></div></div>" +
    '<div class="grid grid-2">' +
      '<div class="card"><h3>Cobertura por lengua</h3>' + donut + "</div>" +
      '<div class="card"><h3>Adaptaciones por día</h3>' + daily +
      '<div style="margin-top:10px"><small class="muted">' + esc(data.note) + "</small></div></div>" +
      '<div class="card"><h3>Términos más adaptados</h3>' + chartCloud(data.cloud) + "</div>" +
      '<div class="card"><h3>Alertas operacionales</h3>' + alerts + "</div>" +
    "</div>" +
    '<h3 style="margin:20px 0 10px">Top 10 por chrF2</h3>' +
    '<div class="table-wrap"><table><thead><tr><th>#</th><th>Fragmento</th><th>Lengua</th>' +
    "<th>chrF2</th><th>Autor</th></tr></thead><tbody>" +
    (leader || '<tr><td colspan="5"><div class="empty">Sin adaptaciones registradas.</div></td></tr>') +
    "</tbody></table></div>"
  );
}

/* =============================== MÓDULO 7 ================================ */

async function viewGlossary() {
  const query = state.q.glossary || "";
  const perPage = 8;
  const page = state.page.glossary || 1;
  const filtered = state.glossary.filter((row) => {
    if (!query) return true;
    const haystack = [row.term, row.domain].concat(Object.values(row.langs || {})).join(" ").toLowerCase();
    return haystack.indexOf(query.toLowerCase()) !== -1;
  });
  const slice = filtered.slice((page - 1) * perPage, page * perPage);
  const rows = slice.map((row) =>
    "<tr><td><b>" + esc(row.term) + "</b></td>" +
    "<td>" + esc((row.langs || {}).quy_Latn || "—") + "</td>" +
    "<td>" + esc((row.langs || {}).ayr_Latn || "—") + "</td>" +
    "<td>" + esc((row.langs || {}).grn_Latn || "—") + "</td>" +
    '<td><span class="tag">' + esc(row.domain) + "</span></td>" +
    '<td><span class="tag ' + (row.validated ? "tag-ok" : "tag-warn") + '">' +
    (row.validated ? "validado" : "por validar") + "</span></td>" +
    '<td><div class="actions"><button class="btn btn-sm" data-edit-term="' + row.id + '">Editar</button>' +
    '<button class="btn btn-sm btn-danger" data-del-term="' + row.id + '">Borrar</button></div></td></tr>'
  ).join("");
  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  return (
    '<div class="page-head"><div><h2>Glosario</h2><p>Vocabulario validado por hablantes: es la palanca real ' +
    "de mejora del LLM. Incluye búsqueda tolerante a typos e importación CSV masiva.</p></div>" +
    '<div class="page-actions"><button class="btn btn-primary" data-new-term>Nuevo término</button>' +
    '<button class="btn" data-import-glossary>Importar CSV</button>' +
    '<button class="btn" data-export="glossary">Exportar CSV</button></div></div>' +
    '<div class="card" style="margin-bottom:14px"><div class="row">' +
    '<label class="field" style="flex:1;margin:0">Búsqueda tolerante a typos' +
    '<input type="search" id="gloss-q" value="' + esc(query) + '" placeholder="ej. fraccion, semilla, kawsay…"></label>' +
    '<button class="btn" id="gloss-suggest">Sugerir</button>' +
    '<span class="tag">' + filtered.length + " de " + state.glossary.length + " términos</span></div>" +
    '<div id="suggest-out"></div></div>' +
    '<div class="table-wrap"><table><thead><tr><th>Castellano</th><th>Quechua</th><th>Aimara</th>' +
    "<th>Guaraní</th><th>Dominio</th><th>Estado</th><th></th></tr></thead><tbody>" +
    (rows || '<tr><td colspan="7"><div class="empty">Sin resultados para esa búsqueda.</div></td></tr>') +
    "</tbody></table></div>" +
    '<div class="pager"><button class="btn btn-sm" data-page="glossary" data-dir="-1"' +
    (page <= 1 ? " disabled" : "") + ">Anterior</button><span>página " + page + " de " + totalPages +
    '</span><button class="btn btn-sm" data-page="glossary" data-dir="1"' +
    (page >= totalPages ? " disabled" : "") + ">Siguiente</button></div>"
  );
}

function termForm(row) {
  row = row || { langs: {} };
  const langs = row.langs || {};
  return (
    '<label class="field">Término (castellano)<input type="text" id="f-term" value="' + esc(row.term || "") + '"></label>' +
    '<div class="form-grid">' +
    '<label class="field">Quechua<input type="text" id="f-quy" value="' + esc(langs.quy_Latn || "") + '"></label>' +
    '<label class="field">Aimara<input type="text" id="f-ayr" value="' + esc(langs.ayr_Latn || "") + '"></label>' +
    '<label class="field">Guaraní<input type="text" id="f-grn" value="' + esc(langs.grn_Latn || "") + '"></label>' +
    '<label class="field">Dominio<input type="text" id="f-domain" value="' + esc(row.domain || "general") + '"></label>' +
    "</div>" +
    '<label class="field" style="flex-direction:row;align-items:center;gap:8px">' +
    '<input type="checkbox" id="f-validated" style="width:auto"' + (row.validated ? " checked" : "") +
    "> Validado por hablante nativo</label>"
  );
}

function termModal(row) {
  const editing = !!row;
  modalSubmit = async () => {
    const payload = {
      term: $("#f-term").value.trim(),
      langs: {
        spa_Latn: $("#f-term").value.trim(),
        quy_Latn: $("#f-quy").value.trim(),
        ayr_Latn: $("#f-ayr").value.trim(),
        grn_Latn: $("#f-grn").value.trim(),
      },
      domain: $("#f-domain").value.trim() || "general",
      validated: $("#f-validated").checked,
      updatedBy: "panel",
    };
    if (!payload.term) { toast("El término es obligatorio", "warn"); return; }
    try {
      if (editing) { await api("/api/glossary/" + row.id, { method: "PUT", body: payload }); }
      else { await api("/api/glossary", { method: "POST", body: payload }); }
      closeModal();
      await refresh("glossary");
      toast(editing ? "Término actualizado" : "Término creado", "ok");
    } catch (err) { toast(err.message, "bad"); }
  };
  openModal(
    editing ? "Editar término" : t("Nuevo término"),
    termForm(row),
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Guardar</button>'
  );
}

function importModal() {
  modalSubmit = async () => {
    const csv = $("#f-csv").value.trim();
    if (!csv) { toast("Pega al menos una línea", "warn"); return; }
    try {
      const result = await api("/api/glossary/import", { method: "POST", body: { csv: csv } });
      closeModal();
      await refresh("glossary");
      toast("Importadas " + result.created + " filas", result.created ? "ok" : "warn");
    } catch (err) { toast(err.message, "bad"); }
  };
  openModal(
    t("Importar glosario por CSV"),
    '<label class="field">Una línea por término: <span class="mono">castellano;quechua;aimara;guaraní;dominio</span>' +
    '<textarea id="f-csv" style="min-height:150px">luz;kancha;nakhaya;tesape;física\nraíz;saphi;saphi;rapo;biología</textarea></label>' +
    '<div class="hint">La cabecera es opcional. Las líneas mal formadas se reportan sin interrumpir la importación.</div>',
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Importar</button>'
  );
}

/* =============================== MÓDULO 8 ================================ */

async function viewAdmin() {
  const [feedback, health, activity] = await Promise.all([
    api("/api/feedback").then((r) => r.feedback || []).catch(() => []),
    api("/healthz").catch(() => null),
    api("/api/activity?limit=12").then((r) => r.activity || []).catch(() => []),
  ]);
  const feedbackRows = feedback.map((row) =>
    '<div class="alert alert-accent"><strong>' + esc("★".repeat(row.rating)) + "</strong>" +
    '<span style="flex:1">' + esc(row.note || "(sin nota)") + "</span>" +
    '<span class="tag">' + esc(row.reviewer) + "</span>" +
    '<span class="muted mono">' + esc(String(row.createdAt || "").slice(0, 16)) + "</span></div>"
  ).join("") || '<div class="empty">Todavía no hay feedback de hablantes nativos.</div>';
  const activityRows = activity.map((row) =>
    '<div class="alert"><span class="tag">' + esc(row.type) + "</span><span style=\"flex:1\">" +
    esc(String(row.snippet || "").slice(0, 80)) + "</span>" +
    '<span class="muted mono">' + esc(String(row.ts || "").slice(0, 16)) + "</span></div>"
  ).join("") || '<div class="empty">Sin actividad registrada.</div>';
  const healthJson = health ? JSON.stringify(health, null, 2) : "sin respuesta";
  return (
    '<div class="page-head"><div><h2>Admin / Audit</h2><p>QA del jurado: feedback de hablantes nativos con ' +
    "puntaje y revisor, ping en vivo a /healthz y trazabilidad de todas las escrituras.</p></div>" +
    '<div class="page-actions"><button class="btn btn-primary" data-new-feedback>Registrar feedback</button>' +
    '<button class="btn" id="admin-ping">Ping /healthz</button>' +
    '<button class="btn" data-export="feedback">Exportar CSV</button></div></div>' +
    '<div class="grid grid-2">' +
      '<div class="card"><h3>Feedback de hablantes nativos</h3>' + feedbackRows + "</div>" +
      '<div class="card"><h3>Estado de /healthz</h3><div class="prompt-box" id="health-box">' +
      esc(healthJson) + "</div></div>" +
    "</div>" +
    '<h3 style="margin:20px 0 10px">Trazabilidad reciente</h3>' +
    '<div class="card">' + activityRows + "</div>"
  );
}

function feedbackModal() {
  openModal(
    t("Feedback de hablante nativo"),
    '<label class="field">Estudiante<select id="f-student">' +
    state.students.map((s) => '<option value="' + s.id + '">' + esc(s.name) + "</option>").join("") +
    "</select></label>" +
    '<label class="field">Puntaje (1-5)<div class="stars" id="stars">' +
    [1, 2, 3, 4, 5].map((n) => '<button class="star" data-star="' + n + '">★</button>').join("") +
    '</div><input type="hidden" id="f-rating" value="5"></label>' +
    '<label class="field">Nota<textarea id="f-note" style="min-height:90px" ' +
    'placeholder="¿Se entendió la adaptación? ¿Faltó algún término?"></textarea></label>' +
    '<label class="field">Revisor<input type="text" id="f-reviewer" value="Hab. nativo"></label>',
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Enviar</button>'
  );
  $$("#stars .star").forEach((button) => {
    button.addEventListener("click", () => {
      const value = Number(button.dataset.star);
      $("#f-rating").value = value;
      $$("#stars .star").forEach((other) => {
        other.classList.toggle("on", Number(other.dataset.star) <= value);
      });
    });
  });
  $$("#stars .star").forEach((b) => b.classList.add("on"));
  modalSubmit = async () => {
    const payload = {
      studentId: Number($("#f-student").value || 0),
      rating: Number($("#f-rating").value || 5),
      note: $("#f-note").value.trim(),
      reviewer: $("#f-reviewer").value.trim() || "anónimo",
    };
    try {
      await api("/api/feedback", { method: "POST", body: payload });
      closeModal();
      await render();
      toast(t("Feedback registrado"), "ok");
    } catch (err) { toast(err.message, "bad"); }
  };
}

/* ========================= MÓDULO 9 · ESCÁNER DE DOCUMENTOS ================= */

const SCAN_FALLBACK = {
  extensions: [".pdf", ".txt"],
  maxBytes: 8 * 1024 * 1024,
  maxLabel: "8 MB",
  rejected: ".doc, .docx, .xlsx, .zip, .png, .jpg, .csv, .json",
};

async function loadScanLimits() {
  if (state.scanLimits) return state.scanLimits;
  try {
    state.scanLimits = await api("/api/scan/limits");
  } catch (err) {
    state.scanLimits = SCAN_FALLBACK;
  }
  return state.scanLimits || SCAN_FALLBACK;
}

/* Selector de lenguas del escáner: agrupado por familia y con selección
   múltiple, para entregar el mismo documento en varias lenguas a la vez. */
function scanLangPicker() {
  const langs = state.languages;
  if (!langs.length) return '<div class="empty">Cargando lenguas...</div>';
  const selected = state.scanTargets[0] || "";
  return '<select id="scan-langs">' + langs.map((lang) =>
    '<option value="' + esc(lang.code) + '"' + (lang.code === selected ? ' selected' : '') + '>' +
    esc(lang.name) + ' (' + esc(lang.code) + ')</option>'
  ).join('') + '</select>';
}

/* A quién se entrega el documento: el docente elige estudiante; el estudiante
   elige entre los varios profesores disponibles. */
async function scanRecipients() {
  if (!(state.demoUsers || []).length) {
    try {
      const data = await api("/api/aula/users");
      state.demoUsers = data.users || [];
    } catch (err) { /* sin directorio: el selector queda vacío */ }
  }
  const users = state.demoUsers || [];
  const me = state.session;
  const wanted = me && me.role === "docente" ? "estudiante" : "docente";
  return users.filter((u) => u.role === wanted);
}

async function viewScan() {
  const limits = await loadScanLimits();
  const recipients = await scanRecipients();
  let selectedRecipient = recipients.find((user) => String(user.userId) === String(state.scanRecipientId));
  if (!selectedRecipient) selectedRecipient = recipients[0] || null;
  state.scanRecipientId = selectedRecipient ? selectedRecipient.userId : null;
  if (selectedRecipient && !state.scanTargets.length) state.scanTargets = [selectedRecipient.langCode];
  const history = state.docs.map((doc, index) =>
    '<div class="alert alert-accent"><span class="tag">' + esc(doc.ext) + "</span>" +
    '<span style="flex:1">' + esc(doc.name) + " · " + esc(doc.sizeLabel) + " · " +
    esc(doc.words) + " palabras</span>" +
    '<button class="btn btn-sm" data-doc-reload="' + index + '">Abrir</button></div>'
  ).join("") || '<div class="empty">Todavía no has escaneado ningún documento en esta sesión.</div>';
  const chips = state.scanTargets.length
    ? '<span class="chip-lang">' + esc(languageName(state.scanTargets[0])) + '</span>'
    : '<span class="muted">Selecciona un destinatario.</span>';
  const people = recipients
    .map(
      (user) =>
        '<option value="' + user.userId + '"' + (String(user.userId) === String(state.scanRecipientId) ? ' selected' : '') + '>' + esc(user.name) + " · " +
        esc(user.role === "docente" ? "docente" : "estudiante") + " · " +
        esc(user.langName || user.langCode) + "</option>"
    )
    .join("");
  return (
    '<div class="page-head"><div><h2>Enviar un documento</h2><p>Sube un archivo .pdf o .txt. Selecciona al destinatario; su idioma de perfil aparece elegido. Al subirlo, se adjunta en su conversacion de Mensajeria. Los PDF que solo contienen imagenes necesitan OCR.</p></div>' +
    '<div class="page-actions"><span class="tag tag-accent">máx. ' + esc(limits.maxLabel) + "</span>" +
    '<span class="tag">' + esc((limits.extensions || []).join(" · ")) + "</span></div></div>" +
    '<div class="grid grid-2">' +
      '<div class="card"><h3>Zona de arrastre</h3>' +
      '<div id="dropzone" class="dropzone">' +
        '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M12 16V4M7 9l5-5 5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>' +
        '<strong>Arrastra aquí tu documento</strong>' +
        '<span class="muted">o</span>' +
        '<button class="btn btn-primary" id="pick-doc">Elegir archivo</button>' +
        '<small class="muted">Sólo .pdf y .txt · hasta ' + esc(limits.maxLabel) + ' por archivo</small>' +
        '<input type="file" id="scan-input" accept=".pdf,.txt,application/pdf,text/plain" hidden>' +
      "</div>" +
      '<div style="margin-top:12px"><small class="muted">Formatos rechazados, entre otros: ' +
      esc(limits.rejected || "—") + ".</small></div>" +
      '<div class="chips" style="margin-top:14px">' +
      '<button class="btn btn-sm" id="scan-demo">Probar con un TXT de ejemplo</button></div>' +
      "</div>" +
      '<div class="card"><h3>Enviar documento por Mensajer\u00eda</h3>' +
      '<div class="form-grid">' +
      '<label class="field">' + (isDocente() ? "Entregar al alumno" : "Entregar al profesor") + '<select id="scan-to">' +
      (people || '<option value="">Sin destinatarios disponibles</option>') + "</select></label>" +
      '<label class="field">Idioma de entrega (se ajusta al perfil; puedes cambiarlo)' +
      scanLangPicker() + '</label>' +
      '<label class="field">Nivel<select id="scan-level"><option>b\u00e1sico</option>' +
      "<option>intermedio</option><option>avanzado</option></select></label>" +
      '</div><div class="chips" id="scan-targets">' + chips + '</div>' +
      (state.scanPendingFile ? '<p class="hint">Archivo listo: ' + esc(state.scanPendingFile.name) + '</p>' : '<p class="hint">Primero elige el archivo. Luego confirma con el bot\u00f3n para enviarlo por Mensajer\u00eda.</p>') +
      '<button class="btn btn-primary" id="scan-send"' + (state.scanPendingFile ? '' : ' disabled') + '>Subir y enviar</button></div>' +
      '<div class="card"><h3>Resultado</h3><div id="scan-out">' +
      '<div class="empty">Aún no hay documento escaneado.</div></div></div>' +
    "</div>" +
    '<h3 style="margin:20px 0 10px">Documentos de esta sesión</h3>' +
    '<div class="card">' + history + "</div>"
  );
}

/* Tabla de entregas cuando el escáner envía el documento en varias lenguas. */
function renderScanDoc(doc) {
  const notes = (doc.notes || []).length
    ? doc.notes.map((note) =>
        '<div class="alert ' + (doc.textless ? "alert-bad" : "alert-warn") +
        '"><strong>Aviso</strong><span>' + esc(note) + "</span></div>"
      ).join("")
    : '<div class="alert alert-ok"><strong>Sin avisos</strong><span>El texto se extrajo completo.</span></div>';
  const cell = (label, value) =>
    '<div class="score-cell"><span>' + esc(label) + "</span><b>" + esc(value) + "</b></div>";
  return (
    '<div class="chips">' +
      '<span class="tag tag-accent">' + esc(doc.name) + "</span>" +
      '<span class="tag">' + esc(doc.ext) + "</span>" +
      '<span class="tag">' + esc(doc.sizeLabel) + "</span>" +
      '<span class="tag">' + esc(doc.pages) + (doc.pages === 1 ? " página" : " páginas") + "</span>" +
      (doc.textless
        ? '<span class="tag tag-bad">sin texto</span>'
        : '<span class="tag tag-ok">texto extraído</span>') +
      (doc.truncated ? '<span class="tag tag-warn">truncado</span>' : "") +
    "</div>" +
    '<div class="score-strip">' +
      cell(t("Caracteres"), Number(doc.chars).toLocaleString("es")) +
      cell(t("Palabras"), Number(doc.words).toLocaleString("es")) +
      cell(t("Frases"), doc.sentences) +
      cell(t("Párrafos"), doc.paragraphs) +
      cell(t("Lectura"), doc.readingMinutes + " min") +
      cell(t("Legibilidad"), doc.flesch === null ? "—" : fmt(doc.flesch, 1)) +
      cell(t("Idioma (pista)"), doc.langHint) +
      cell(t("Huella"), doc.sha256) +
    "</div>" +
    notes +
    docViewer(doc) +
    '<div class="row" style="margin-top:12px">' +
      '<button class="btn btn-primary" data-doc-adapt="last"' + (doc.textless ? " disabled" : "") +
      ">Enviar al adaptador</button>" +
      '<button class="btn" data-doc-save="last"' + (doc.textless ? " disabled" : "") +
      ">Guardar en biblioteca</button>" +
      '<button class="btn" data-doc-copy="last">Copiar texto</button>' +
      '<button class="btn" data-doc-download="last">Descargar .txt</button>' +
    "</div>"
  );
}

function readScanTargets() {
  const box = $("#scan-langs");
  if (!box) return [];
  if (!box.multiple) return box.value ? [box.value] : [];
  return Array.from(box.selectedOptions || []).map((option) => option.value).filter(Boolean);
}

/* Guarda el archivo recién soltado para poder mostrar el original completo. */
function rememberFile(file) {
  if (state.fileSrc && state.fileSrc.url) {
    try { URL.revokeObjectURL(state.fileSrc.url); } catch (err) { /* ignorado */ }
  }
  const isPdf = String(file.name || "").toLowerCase().endsWith(".pdf");
  state.fileSrc = {
    name: file.name,
    ext: isPdf ? ".pdf" : ".txt",
    size: file.size,
    url: isPdf ? URL.createObjectURL(file) : "",
  };
}

/* URL del original sólo si corresponde a este documento. */
function docFileSrc(doc) {
  const src = state.fileSrc;
  if (!src || !src.url) return "";
  if (doc && src.name && doc.name && String(src.name) !== String(doc.name)) return "";
  return src.url;
}

function openDocPreview(doc) {
  if (!doc) return;
  const isPdf = String(doc.ext || "").toLowerCase() === ".pdf";
  const src = docFileSrc(doc);
  const body = isPdf && src
    ? '<iframe class="doc-frame doc-frame-full" src="' + esc(src) + '#view=FitH" title="Documento original"></iframe>'
    : '<pre class="doc-full doc-full-screen">' + (esc(doc.text) || t("(sin texto extraído)")) + "</pre>";
  openModal("Texto completo · " + String(doc.name || "documento"), body,
    '<button class="btn btn-ghost" data-modal-cancel>Cerrar</button>');
}

/* Pestañas del visor: vista rápida, texto completo y PDF original. */
function docViewer(doc) {
  const isPdf = String(doc.ext || "").toLowerCase() === ".pdf";
  const src = docFileSrc(doc);
  const canOriginal = isPdf && !!src;
  return (
    '<div class="doc-tabs" role="tablist">' +
      '<button type="button" class="doc-tab is-on" data-doc-tab="pistas">Vista rápida</button>' +
      '<button type="button" class="doc-tab" data-doc-tab="texto">Texto completo</button>' +
      (canOriginal ? '<button type="button" class="doc-tab" data-doc-tab="original">Documento original</button>' : "") +
      '<button type="button" class="btn btn-sm" id="doc-fullscreen">Ver en pantalla completa</button>' +
    "</div>" +
    '<div class="doc-panes">' +
      '<div class="doc-pane" data-doc-pane="pistas">' +
        '<div class="doc-preview">' + (esc(doc.preview) || t("(sin texto extraído)")) + "</div>" +
        '<p class="hint">Vista rápida. Usa «Texto completo» para leer todo el archivo' +
        (canOriginal ? " o «Documento original» para ver las páginas del PDF." : ".") + "</p>" +
      "</div>" +
      '<div class="doc-pane" data-doc-pane="texto" hidden>' +
        '<pre class="doc-full">' + (esc(doc.text) || t("(sin texto extraído)")) + "</pre>" +
      "</div>" +
      (canOriginal
        ? '<div class="doc-pane" data-doc-pane="original" hidden>' +
            '<iframe class="doc-frame" data-doc-src="' + esc(src) + '" title="Documento original"></iframe>' +
            '<p class="hint">Se muestra tu PDF tal como lo subiste: desplázate dentro del marco para ver todas las páginas.</p>' +
          "</div>"
        : (isPdf
            ? '<div class="doc-pane" data-doc-pane="original" hidden>' +
                '<div class="alert alert-warn"><strong>Vista del PDF original</strong><span>Vuelve a arrastrar el PDF para ver todas las páginas; el archivo no se conserva entre recargas.</span></div>' +
              "</div>"
            : "")) +
    "</div>"
  );
}

function showDocTab(which) {
  $$("[data-doc-tab]").forEach((btn) => btn.classList.toggle("is-on", btn.dataset.docTab === which));
  $$("[data-doc-pane]").forEach((pane) => { pane.hidden = pane.dataset.docPane !== which; });
  if (which === "original") {
    const frame = $(".doc-frame[data-doc-src]");
    if (frame && !frame.getAttribute("src")) frame.setAttribute("src", frame.dataset.docSrc);
  }
}

function paintScanTargetChip() {
  const host = document.getElementById("scan-targets");
  const code = state.scanTargets[0];
  if (host) host.innerHTML = code
    ? '<span class="chip-lang">' + esc(languageName(code)) + '</span>'
    : '<span class="muted">Selecciona un destinatario.</span>';
}

function selectedScanRecipientName(userId) {
  const user = (state.demoUsers || []).find((row) => String(row.userId) === String(userId));
  return user ? user.name : "el destinatario seleccionado";
}

async function sendScanToMessaging(file, recipientId, targetCode, level) {
  const session = state.session;
  const data = await api("/api/messaging/threads?userId=" + encodeURIComponent(session.userId));
  let thread = (data.threads || []).find((row) =>
    row.type === "direct" && (row.participants || []).length === 2 &&
    (row.participants || []).some((id) => String(id) === String(session.userId)) &&
    (row.participants || []).some((id) => String(id) === String(recipientId))
  );
  if (!thread) {
    thread = await api("/api/messaging/threads", {
      method: "POST",
      body: { fromUserId: session.userId, toUserIds: [Number(recipientId)], title: "Documento del aula" },
    });
  }
  const form = new FormData();
  form.append("file", file);
  form.append("fromUserId", String(session.userId));
  form.append("src", session.langCode || "spa_Latn");
  form.append("targets", targetCode);
  form.append("level", level || "b\u00e1sico");
  form.append("title", String(file.name || "Documento").replace(/\.[^.]+$/, ""));
  const response = await fetch("/api/messaging/threads/" + thread.id + "/documents", {
    method: "POST",
    headers: session.token ? { Authorization: "Bearer " + session.token } : {},
    body: form,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "No se pudo enviar el documento por Mensajer\u00eda.");
  return thread;
}

function stageScanFile(file) {
  if (!file) return;
  rememberFile(file);
  state.scanPendingFile = file;
  const button = document.getElementById("scan-send");
  if (button) button.disabled = false;
  const out = document.getElementById("scan-out");
  if (out) out.innerHTML = '<div class="empty">Analizando «' + esc(file.name) + '»…</div>';
  // Analiza y muestra el resultado primero. El envío al chat queda separado
  // para que el docente pueda revisar el documento antes de entregarlo.
  void scanFile(file, { previewOnly: true });
}

async function scanFile(file, options) {
  if (!file) return;
  rememberFile(file);
  const limits = await loadScanLimits();
  const name = String(file.name || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  const out = $("#scan-out");
  if ((limits.extensions || SCAN_FALLBACK.extensions).indexOf(ext) === -1) {
    if (out) {
      out.innerHTML = '<div class="alert alert-bad"><strong>Formato no permitido</strong><span>Sólo se aceptan ' +
        'documentos .pdf o .txt. Recibido: «' + esc(ext || "sin extensión") + "».</span></div>";
    }
    toast("Sólo se aceptan .pdf y .txt", "bad");
    return;
  }
  if (file.size > limits.maxBytes) {
    if (out) {
      out.innerHTML = '<div class="alert alert-bad"><strong>Archivo demasiado grande</strong><span>Pesa ' +
        esc((file.size / 1048576).toFixed(2)) + " MB y el límite es " + esc(limits.maxLabel) + ".</span></div>";
    }
    toast("El archivo supera el límite de " + limits.maxLabel, "bad");
    return;
  }
  state.scanTargets = readScanTargets();
  const zone = $("#dropzone");
  if (zone) zone.classList.add("busy");
  if (out) out.innerHTML = '<div class="empty">Extrayendo texto de «' + esc(file.name) + '»…</div>';
  try {
    const form = new FormData();
    form.append("file", file);
    let endpoint = "/api/scan";
    if (state.scanTargets.length && !(options && options.previewOnly)) {
      const to = $("#scan-to");
      if (!to || !to.value) throw new Error("Selecciona el destinatario del documento.");
      const level = $("#scan-level");
      const thread = await sendScanToMessaging(file, to.value, state.scanTargets[0], level ? level.value : "b\u00e1sico");
      state.msgThreadId = thread.id;
      state.msgMessages = [];
      state.msgDirLoaded = false;
      await loadMsgThreads();
      state.scanPendingFile = null;
      const sendButton = document.getElementById("scan-send");
      if (sendButton) sendButton.disabled = true;
      if (out) out.innerHTML = '<div class="alert alert-ok"><strong>Documento enviado</strong><span>' +
        esc(selectedScanRecipientName(to.value)) + ' lo recibir\u00e1 en ' + esc(languageName(state.scanTargets[0])) +
        '. <button class="btn btn-sm btn-primary" id="scan-open-chat">Abrir conversaci\u00f3n</button></span></div>' +
        (state.lastDoc ? renderScanDoc(state.lastDoc) : '');
      toast("Documento enviado por Mensajer\u00eda.", "ok", 5200);
      return;
    }
    const headers = {};
    if (state.session && state.session.token) {
      headers.Authorization = "Bearer " + state.session.token;
    }
    const response = await fetch(endpoint, { method: "POST", headers, body: form });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error((data && data.error) || ("HTTP " + response.status));
    }
    state.lastDoc = data;
    state.docs.unshift(data);
    state.docs = state.docs.slice(0, 8);
    paintNav();
    await render();
    const fresh = $("#scan-out");
    if (fresh) fresh.innerHTML = renderScanDoc(data);
    toast(
      data.textless
        ? "No se extrajo texto: el PDF parece escaneado (requiere OCR)"
        : "Texto extraído: " + data.words + t(" palabras"),
      data.textless ? "warn" : "ok",
      4200
    );
  } catch (err) {
    if (out) {
      out.innerHTML = '<div class="alert alert-bad"><strong>Error</strong><span>' + esc(err.message) + "</span></div>";
    }
    toast(err.message, "bad");
  } finally {
    const zone2 = $("#dropzone");
    if (zone2) zone2.classList.remove("busy");
    const sendButton = document.getElementById("scan-send");
    if (sendButton && state.scanPendingFile) sendButton.disabled = false;
  }
}

async function scanDemoTxt() {
  const text =
    "El ciclo del agua\n\nEl agua del río sube al cielo cuando el sol la calienta y vuelve como lluvia. " +
    "La semilla germina en la tierra húmeda y la comunidad comparte la cosecha en el ayllu.\n\n" +
    "Una fracción es una parte de un todo: si repartimos ocho papas entre cuatro personas, cada una recibe dos.";
  await scanFile(new File([text], "demostracion_ayllu.txt", { type: "text/plain" }), { previewOnly: true });
}

function resolveDoc(value) {
  if (value === "last") return state.lastDoc;
  const index = Number(value);
  return isFinite(index) ? state.docs[index] : null;
}

/* ============================= MÓDULO 10 · v3 ============================ */

/* Aula bilingüe y entrega docente. El texto que escribe cada persona NUNCA se
   modifica: se guarda el original y se entrega la traducción al otro lado. */

async function renderAula() {
  const session = state.session;
  if (!session) return '<div class="empty">Inicia sesión para ver el aula.</div>';
  const data = await api("/api/aula/messages?userId=" + encodeURIComponent(session.userId));
  const rows = (data.messages || []).filter(
    (m) => m.fromUserId === session.userId || m.toUserId === session.userId
  );
  const peers = (state.demoUsers || []).filter((user) => user.role !== session.role);
  // Por omisión se propone el interlocutor de la misma comunidad (así el aula de
  // Puno no entrega por error al profesor de Santa Cruz); el selector permite
  // cambiarlo: un estudiante puede elegir entre varios profesores.
  const partner =
    peers.find((user) => String(user.communityId) === String(session.communityId)) ||
    peers[0] ||
    null;
  const local = state.aulaLocal || {};
  const here = esc(session.langName || session.langCode);
  const there = esc(partner ? partner.langName || partner.langCode : "—");
  let out = "";

  out +=
    '<div class="page-head"><div><h2>' +
    (isDocente() ? "Aula bilingüe · actividades" : t("Aula bilingüe · mis actividades")) +
    "</h2><p>" + esc(session.name) + " · " + esc(session.jobTitle || "") +
    ". Aquí consultas actividades del curso y envías respuestas en " + here +
    (partner
      ? "; tu interlocutor es " + esc(partner.name) + " (" + esc(partner.role) + " · " + there + ")."
      : ".") +
    " Ayllu conserva el original y muestra la traducción disponible. Para conversar, usa Mensajería · chat.</p></div></div>";

  out +=
    '<div class="aula-flow"><span class="chip-lang">' + here +
    '</span><span class="flow-arrow">→</span><span class="chip-lang">Ayllu traduce y adapta</span>' +
    '<span class="flow-arrow">→</span><span class="chip-lang">' + there + "</span></div>";

  out +=
    '<div class="card"><h3>' +
    (isDocente() ? "Enviar una actividad o material" : "Responder o enviar una entrega") +
    '</h3><label class="field">Tu texto (' + here +
    ')<textarea id="aula-text" placeholder="' +
    (isDocente()
      ? "Actividad: observa una planta de tu comunidad y escribe qué necesita para crecer."
      : "Mi respuesta: la planta necesita agua, luz del sol y tierra.") +
    '"></textarea></label>' +
    '<div class="form-grid">' +
    '<label class="field">Idioma de este texto<select id="aula-src">' +
    msgLangOptions(session.langCode || "quy_Latn") + "</select><span class=\"muted\">Empieza con tu idioma de perfil; cámbialo si escribes en otro.</span></label>" +
    '<label class="field">Asunto o título<input id="aula-title" placeholder="' +
      (isDocente() ? "Actividad: observamos las plantas" : "Respuesta: observamos las plantas") + '"></label>' +
    '<label class="field">Enviar como<select id="aula-kind">' +
    '<option value="mensaje">Respuesta escrita</option><option value="material">Material</option></select></label>' +
    (peers.length
      ? '<label class="field">' + (isDocente() ? "Entregar al estudiante" : "Enviar al profesor") +
        '<select id="aula-to">' +
        peers
          .map(
            (user) =>
              '<option value="' + user.userId + '"' +
              (partner && partner.userId === user.userId ? " selected" : "") + ">" + esc(user.name) + " · " +
              esc(user.role) + " · " + esc(user.langName || user.langCode) +
              (user.communityId ? " · " + esc(communityName(user.communityId)) : "") + "</option>"
          )
          .join("") +
        "</select></label>"
      : "") +
    "</div>" +
    '<div class="row"><button class="btn btn-primary" id="aula-send">Traducir y enviar</button>' +
    '<button class="btn" id="aula-demo">Usar ejemplo</button>' +
    (partner ? '<span class="chip-lang">Se envía a ' + esc(partner.name) + " · " + there + "</span>" : "") +
    "</div>" +
    '<p class="hint">Tu texto original nunca se modifica: Ayllu conserva una copia y entrega la traducción.</p></div>';

  out += '<h3 style="margin:18px 0 10px">Actividades y respuestas</h3><div class="aula-thread">';
  if (!rows.length) {
    out += '<div class="empty">Todavía no hay actividades ni respuestas.</div>';
  }
  rows.forEach((message) => {
    const mine = message.fromUserId === session.userId;
    const extra = local[message.id] || {};
    const srcText = extra.srcText || message.srcText || "";
    const raw = extra.outText || message.outText || "";
    const degraded = extra.degraded !== undefined ? Boolean(extra.degraded) : Boolean(message.degraded);
    const glossary = extra.glossary || message.glossary || [];
    let rendered = degraded
      ? '<div class="translation-unavailable" role="status">No hay una traducción confiable disponible. Se ocultó la glosa automática porque puede cambiar el sentido. Pulsa “Reintentar traducción”.</div>'
      : esc(raw);
    glossary.forEach((hit) => {
      const target = (hit.target || "").trim();
      if (target.length >= 2) {
        rendered = rendered.split(esc(target)).join("<mark>" + esc(target) + "</mark>");
      }
    });
    out +=
      '<article class="aula-msg ' + (mine ? "out" : "in") + '">' +
      '<div class="aula-meta">' +
      '<span class="role-chip role-' + esc(message.fromRole) + '">' + esc(message.fromRole) + "</span>" +
      "<b>" + esc(message.fromName) + "</b>" +
      '<span class="muted">→ ' + esc(message.toName) + "</span>" +
      (message.kind === "material"
      ? '<span class="tag tag-accent">material' + (message.title ? ": " + esc(message.title) : "") + "</span>"
        : "") +
      (message.kind === "actividad" ? '<span class="tag tag-accent">actividad</span>' : "") +
      '<span class="tag">' + esc(message.src) + " → " + esc(message.tgt) + "</span>" +
      "<time>" + esc(String(message.createdAt || "").slice(0, 16).replace("T", " ")) + "</time>" +
      "</div>" +
      (message.title ? '<div class="msg-title">' + esc(message.title) + "</div>" : "") +
      '<div class="aula-pair">' +
      '<div class="pane"><h4>' +
      (mine ? "Lo que escribiste" : "Original de " + esc(message.fromName)) + " · " + esc(message.src) +
      '</h4><div class="body">' + esc(srcText) + "</div></div>" +
      '<div class="pane pane-out"><h4>Lo que lee ' +
      esc(mine ? message.toName : session.name) + " · " + esc(message.tgt) +
      '</h4><div class="body">' + rendered + "</div></div></div>" +
      (degraded
        ? '<div class="row" style="margin-top:8px"><button class="btn btn-sm" data-aula-translate="' + esc(message.id) + '" data-aula-target="' + esc(message.tgt) + '">Reintentar traducción</button></div>'
        : "") +
      '<div class="row" style="margin-top:8px">' +
      ((glossary || [])
        .map(
          (hit) =>
            '<span class="tag tag-accent" title="' + esc(hit.domain) + '">' + esc(hit.term) +
            (hit.target ? " → " + esc(hit.target) : "") + "</span>"
        )
        .join(" ") || '<span class="muted">Sin términos del glosario en este mensaje.</span>') +
      "</div>" +
      (message.kind === "actividad" && !mine
        ? '<div class="row" style="margin-top:8px"><button class="btn btn-sm btn-primary" data-activity-reply="' +
          esc(message.title || "Actividad") + '" data-activity-teacher="' + esc(message.fromUserId) + '">Responder esta actividad</button></div>'
        : "") +
      '<div class="aula-foot">' + esc((message.notes || []).join(" ")) + "</div>" +
      "</article>";
  });
  out += "</div>";
  return out;
}

async function sendAula() {
  const box = $("#aula-text");
  const text = box ? box.value.trim() : "";
  if (!text) { toast("Escribe un mensaje antes de enviarlo", "warn"); return; }
  const to = $("#aula-to");
  const payload = {
    fromUserId: state.session.userId,
    toUserId: to ? Number(to.value) : undefined,
    src: (($('#aula-src') || {}).value || state.session.langCode),
    kind: ($("#aula-kind") || {}).value || "mensaje",
    title: ($("#aula-title") || {}).value || "",
    text: text,
  };
  const button = $("#aula-send");
  if (button) { button.disabled = true; button.textContent = t("Traduciendo…"); }
  try {
    const row = await api("/api/aula/messages", { method: "POST", body: payload });
    state.aulaLocal = state.aulaLocal || {};
    state.aulaLocal[row.id] = { srcText: row.srcText, outText: row.outText, glossary: row.glossary, degraded: row.degraded };
    toast(
      "Enviado · " + row.src + " → " + row.tgt + " · cobertura " + fmt(row.coverage, 1) +
      "% de vocabulario",
      row.degraded ? "warn" : "ok",
      5200
    );
    await render();
  } catch (err) {
    toast(err.message, "bad");
  } finally {
    if (button) { button.disabled = false; button.textContent = t("Traducir y enviar"); }
  }
}

async function retryAulaTranslation(messageId) {
  const button = document.querySelector('[data-aula-translate="' + String(messageId) + '"]');
  if (button) { button.disabled = true; button.textContent = "Reintentando…"; }
  try {
    const result = await api("/api/messaging/messages/" + encodeURIComponent(messageId) + "/translate", {
      method: "POST",
      body: {
        userId: state.session.userId,
        tgt: button ? button.dataset.aulaTarget : "spa_Latn",
        level: "básico",
      },
    });
    state.aulaLocal = state.aulaLocal || {};
    state.aulaLocal[messageId] = {
      outText: result.text || "",
      glossary: result.glossary || [],
      degraded: Boolean(result.degraded),
    };
    toast(
      result.degraded ? "El motor no logró traducir; la glosa se mantiene oculta." : "Traducción lista con " + result.provider,
      result.degraded ? "warn" : "ok",
      4200
    );
    await render();
  } catch (err) {
    toast(err.message, "bad");
    if (button) { button.disabled = false; button.textContent = "Reintentar traducción"; }
  }
}

async function sendAulaActivity() {
  const title = String(($("#aula-activity-title") || {}).value || "").trim();
  const text = String(($("#aula-activity-text") || {}).value || "").trim();
  const toUserId = Number(($("#aula-activity-to") || {}).value || 0);
  if (!title || !text || !toUserId) {
    toast("Elige un estudiante y completa el título y las instrucciones.", "warn");
    return;
  }
  const button = $("#aula-activity-send");
  if (button) { button.disabled = true; button.textContent = "Traduciendo actividad…"; }
  try {
    const row = await api("/api/aula/messages", {
      method: "POST",
      body: {
        fromUserId: state.session.userId,
        toUserId,
        src: (($('#aula-activity-src') || {}).value || state.session.langCode),
        kind: "actividad",
        title,
        text,
      },
    });
    toast(
      row.degraded
        ? "Actividad enviada; la traducción quedó como glosa y requiere revisión."
        : "Actividad traducida y enviada al aula.",
      row.degraded ? "warn" : "ok",
      5200
    );
    await render();
  } catch (err) {
    toast(err.message, "bad", 5200);
  } finally {
    if (button) { button.disabled = false; button.textContent = "Traducir y enviar actividad"; }
  }
}

async function renderEntrega() {
  const [insight, inbox, usersData, sentData] = await Promise.all([
    api("/api/aula/insights"),
    api("/api/aula/messages?role=estudiante"),
    api("/api/aula/users"),
    api("/api/aula/messages?role=docente"),
  ]);
  const rows = (inbox.messages || []).filter((m) => m.fromRole === "estudiante").slice(0, 8);
  const students = (usersData.users || []).filter((user) => user.role === "estudiante");
  const activities = (sentData.messages || []).filter(
    (message) => message.fromRole === "docente" && message.kind === "actividad"
  ).slice(0, 8);
  let coverage = [];
  try { coverage = (await api("/api/dashboard")).coverage || []; } catch (err) { coverage = []; }

  let out =
    '<div class="page-head"><div><h2>Aula docente · actividades y entregas</h2>' +
    "<p>Envía actividades, revisa las respuestas del alumnado y consulta la cobertura de traducción. " +
    "Las conversaciones directas están en Mensajería · chat.</p></div>" +
    '<div class="page-actions"><button class="btn" data-route="aula_docente">Actualizar</button>' +
    '<button class="btn" data-export="messages">Exportar bandeja (CSV)</button>' +
    '<button class="btn" data-export="students">Exportar mediciones (CSV)</button></div></div>';

  out +=
    '<div class="grid grid-kpi">' +
    kpi("Registros del aula", insight.messages, "actividades y respuestas") +
    kpi("Adaptaciones", insight.adaptations, "materiales procesados") +
    kpi(t("Cobertura media"), fmt(insight.coverage, 1) + "%", "vocabulario del glosario") +
    kpi("Lenguas activas", insight.languages, "MVP FLORES-200") +
    "</div>";

  out +=
    '<div class="card" style="margin-top:14px"><h3>Enviar una actividad</h3>' +
    '<p class="muted">La actividad llegará al Aula bilingüe del estudiante. Su respuesta aparecerá en este panel.</p>' +
    (students.length
      ? '<div class="form-grid"><label class="field">Estudiante<select id="aula-activity-to">' +
        students.map((student) => '<option value="' + esc(student.userId) + '">' + esc(student.name) +
          ' · ' + esc(student.langName || student.langCode) + '</option>').join("") +
        '</select></label><label class="field">Idioma de las instrucciones<select id="aula-activity-src">' +
        msgLangOptions(state.session.langCode || "spa_Latn") + '</select></label>' +
        '<label class="field">Título<input id="aula-activity-title" maxlength="120" placeholder="Ej.: Observamos las plantas"></label></div>' +
        '<label class="field">Instrucciones<textarea id="aula-activity-text" placeholder="Describe qué debe hacer el estudiante."></textarea></label>' +
        '<button class="btn btn-primary" id="aula-activity-send">Traducir y enviar actividad</button>'
      : '<div class="empty">No hay estudiantes disponibles para asignar actividades.</div>') +
    '</div>';

  out +=
    '<div class="card" style="margin-top:14px"><h3>Actividades enviadas</h3>' +
    (activities.length
      ? '<div class="table-wrap"><table><thead><tr><th>Actividad</th><th>Estudiante</th><th>Estado</th></tr></thead><tbody>' +
        activities.map((activity) => {
          const replied = rows.some((reply) =>
            String(reply.fromUserId) === String(activity.toUserId) &&
            String(reply.title || "") === "Respuesta: " + String(activity.title || "")
          );
          return '<tr><td>' + esc(activity.title || "Actividad") + '</td><td>' + esc(activity.toName || "Estudiante") +
            '</td><td><span class="tag ' + (replied ? 'tag-ok">respondida' : 'tag-warn">pendiente') + '</span></td></tr>';
        }).join("") +
        '</tbody></table></div>'
      : '<div class="empty">Aún no has enviado actividades.</div>') +
    '</div>';

  out +=
    '<div class="grid grid-2" style="margin-top:14px">' +
    '<div class="card"><h3>Pares de lenguas en uso</h3>' +
    '<div class="chips">' +
    ((insight.pairs || [])
      .map(
        (pair) =>
          '<span class="chip-lang">' + esc(pair.pair) + " · " + pair.count + " mensajes</span>"
      )
      .join(" ") || '<span class="muted">Sin mensajes registrados.</span>') +
    "</div><h3 style=\"margin-top:14px\">Cobertura por lengua</h3>" +
    chartDonut((coverage || []).map((row) => ({ label: row.name || row.code, value: row.adaptations || 0 }))) +
    "</div></div>";

  out +=
    '<div class="card" style="margin-top:14px"><h3>Respuestas recibidas</h3>' +
    '<div class="table-wrap"><table><thead><tr><th>Estudiante</th><th>Asunto</th><th>Lengua</th>' +
    "<th>Respuesta original</th><th>Traducción al castellano</th><th>Cobertura</th></tr></thead><tbody>" +
    (rows
      .map(
        (row) =>
          "<tr><td>" + esc(row.fromName) + "</td><td>" + esc(row.title || "Sin asunto") + "</td><td>" + esc(row.src) + "</td><td>" +
          esc(row.srcText) + "</td><td>" + esc(row.outText) + "</td><td>" +
          fmt(row.coverage, 1) + "%</td></tr>"
      )
      .join("") || '<tr><td colspan="6" class="muted">Aún no hay respuestas de estudiantes.</td></tr>') +
    "</tbody></table></div>" +
    '<h3 style="margin:16px 0 8px">Documentos entregados por el escáner</h3>' +
    '<div class="table-wrap"><table><thead><tr><th>Documento</th><th>Para</th><th>Lengua</th>' +
    "<th>Cobertura</th><th>Estado</th></tr></thead><tbody>" +
    ((inbox.messages || [])
      .filter((m) => m.kind === "material")
      .slice(0, 8)
      .map(
        (row) =>
          "<tr><td>" + esc(row.title || t("Documento")) + "</td><td>" + esc(row.toName) +
          "</td><td>" + esc(languageName(row.tgt)) + "</td><td>" + fmt(row.coverage, 1) + "%</td><td>" +
          (row.degraded ? '<span class="tag tag-warn">glosa</span>' : '<span class="tag tag-ok">motor</span>') +
          "</td></tr>"
      )
      .join("") || '<tr><td colspan="5" class="muted">Sin documentos entregados.</td></tr>') +
    "</tbody></table></div>" +
    '<div class="alert alert-warn" style="margin-top:12px"><strong>Glosa, no traducción validada</strong>' +
    "<span>Las salidas en lenguas originarias provienen del léxico embebido y requieren revisión de " +
    "hablantes nativos antes de usarse en aula.</span></div></div>";
  return out;
}

async function viewRouter(id) {
  if (!state.session) return '<div class="empty">Inicia sesión para continuar.</div>';
  return id === "aula_docente" ? renderEntrega() : renderAula();
}

/* ------------------------------ render / router --------------------------- */

/* ==========================================================================
   v5 · MENSAJERÍA · docente ↔ estudiante (texto, documentos y traducción)
   Los DOS roles ven el mismo apartado: cambia quién escribe y a quién, no el
   módulo. Cada mensaje trae su texto original intacto y su traducción; el botón
   «Traducir» pide CUALQUIER lengua del catálogo para cualquiera de los dos.
   ========================================================================== */

/* Opciones de lengua: el catálogo completo (21 simikuna) del backend. */
function msgLangOptions(selected) {
  const rows = state.languages || [];
  if (!rows.length) return '<option value="spa_Latn">Castellano</option>';
  const groups = [["originaria", "Lenguas originarias"], ["internacional", "Otras lenguas"], ["puente", "Puente"]];
  return groups
    .map(([key, label]) => {
      const items = rows.filter((l) => (l.group || "originaria") === key);
      if (!items.length) return "";
      return (
        '<optgroup label="' + esc(label) + '">' +
        items
          .map(
            (l) =>
              '<option value="' + esc(l.code) + '"' +
              (l.code === selected ? " selected" : "") + ">" + esc(l.name) +
              " (" + esc(l.code) + ")</option>"
          )
          .join("") +
        "</optgroup>"
      );
    })
    .join("");
}

function msgThreadById(id) {
  return (state.msgThreads || []).find((row) => String(row.id) === String(id)) || null;
}

/* El interlocutor del hilo distinto de mí (para saber la lengua por omisión). */
function msgPartner(thread) {
  if (!thread || !state.session) return null;
  return ((thread.members || []).find((m) => String(m.userId) !== String(state.session.userId))) || null;
}

function msgTranslationTarget(row) {
  if (!state.session) return "quy_Latn";
  const thread = state.msgThreadId ? msgThreadById(state.msgThreadId) : null;
  const partner = msgPartner(thread);
  const myLang = String(state.session.langCode || "spa_Latn");
  const partnerLang = partner && partner.langCode ? String(partner.langCode) : null;
  if (thread && thread.type === "group") return myLang;
  if (!row) return partnerLang || myLang;
  const mine = String(row.fromUserId) === String(state.session.userId);
  if (mine) return partnerLang || myLang;
  return myLang || partnerLang || row.tgt || row.src || "quy_Latn";
}

async function loadMsgDirectory() {
  if (state.msgDirLoaded && (state.demoUsers || []).length) return state.demoUsers;
  try {
    const data = await api("/api/messaging/directory");
    state.demoUsers = data.users || state.demoUsers || [];
    state.msgDirLoaded = true;
  } catch (err) { /* el directorio queda como estaba */ }
  return state.demoUsers || [];
}

/* --- hilo abierto -------------------------------------------------------- */

function translationForRow(row) {
  if (!row || !row.translations) return null;
  const candidates = [];
  if (row.tgt && row.translations[row.tgt]) {
    candidates.push([row.tgt, row.translations[row.tgt]]);
  }
  Object.entries(row.translations).forEach(([code, item]) => {
    if (code !== row.tgt) candidates.push([code, item]);
  });
  for (const [code, item] of candidates) {
    if (item && typeof item === "object" && String(item.text || "").trim()) {
      return Object.assign({ tgt: code }, item);
    }
  }
  return null;
}

async function openMsgThread(threadId, options) {
  state.msgThreadId = Number(threadId) || null;
  state.msgMessages = [];
  state.msgMore = {};
  if (!state.msgThreadId) return;
  try {
    const data = await api(
      "/api/messaging/threads/" + state.msgThreadId + "/messages?userId=" +
      encodeURIComponent(state.session.userId)
    );
    state.msgMessages = data.messages || [];
    state.msgMessages.forEach((row) => {
      const saved = translationForRow(row);
      if (saved) state.msgMore[row.id] = saved;
    });
  } catch (err) {
    toast(err.message, "bad");
    state.msgMessages = [];
    return;
  }
  if (!options || !options.silent) {
    try {
      await api("/api/messaging/threads/" + state.msgThreadId + "/read", {
        method: "PUT", body: { userId: state.session.userId },
      });
      await loadMsgThreads();
    } catch (err) { /* el contador se refresca en el siguiente cambio de vista */ }
  }
}

function msgBubble(row) {
  const mine = String(row.fromUserId) === String(state.session.userId);
  const attachment = row.attachment || null;
  const activeThread = state.msgThreadId ? msgThreadById(state.msgThreadId) : null;
  const isGroupThread = !!activeThread && activeThread.type === "group";
  const displayTgt = isGroupThread ? msgTranslationTarget(row) : String(row.tgt || "");
  // Un reintento actualiza translations, mientras outText puede seguir con la
  // primera salida guardada. Renderiza la versión más reciente del destino.
  const delivery = displayTgt && row.translations ? row.translations[displayTgt] : null;
  const deliveryText = delivery && delivery.text ? delivery.text : (isGroupThread ? "" : (row.outText || ""));
  const deliveryDegraded = delivery ? Boolean(delivery.degraded) : (isGroupThread || Boolean(row.degraded));
  const savedTranslation = state.msgMore[row.id] || translationForRow(row) || null;
  // La entrega inicial ya aparece en el panel «Lo que lee». Mostrarla otra vez
  // debajo parecía una segunda traducción, aunque fuera exactamente la misma.
  const extra = !isGroupThread && savedTranslation && String(savedTranslation.tgt || "") !== String(row.tgt || "")
    ? savedTranslation
    : null;
  const glossary = (row.glossary || []).slice(0, 12);
  let rendered;
  if (deliveryDegraded) {
    rendered = '<div class="translation-unavailable" role="status">No hay una traducción confiable disponible. Se ocultó la glosa automática porque puede cambiar el sentido. Pulsa “Traducir” para volver a intentarlo; el original sigue visible a la izquierda.</div>';
  } else if (String(deliveryText || "").trim()) {
    rendered = esc(deliveryText);
    glossary.forEach((hit) => {
      const target = String(hit.target || "").trim();
      if (target.length >= 2) rendered = rendered.split(esc(target)).join("<mark>" + esc(target) + "</mark>");
    });
  } else {
    rendered = '<div class="translation-unavailable" role="status">Todavía no hay una traducción para mostrar. Pulsa “Traducir” para intentarlo; el original sigue disponible a la izquierda.</div>';
  }
  const defaultTgt = msgTranslationTarget(row);

  let out =
    '<article class="msg-bubble ' + (mine ? "mine" : "theirs") + '">' +
    '<div class="msg-head">' +
    '<span class="role-chip role-' + esc(row.fromRole) + '">' + esc(row.fromRole) + "</span>" +
    "<b>" + esc(row.fromName) + "</b>" +
    '<span class="muted">→ ' + esc(row.toName || "el aula") + "</span>" +
    (row.kind === "documento" ? '<span class="tag tag-accent">documento</span>' : "") +
    (row.kind === "material" ? '<span class="tag tag-accent">material</span>' : "") +
    '<span class="tag">' + esc(row.src) + " → " + esc(displayTgt || row.tgt) + "</span>" +
    (deliveryDegraded ? '<span class="tag tag-warn">sin traducción confiable</span>' : '<span class="tag tag-ok">traducido</span>') +
    "<time>" + esc(String(row.createdAt || "").slice(0, 16).replace("T", " ")) + "</time>" +
    "</div>";

  if (row.title) out += '<div class="msg-title">' + esc(row.title) + "</div>";

  out +=
    '<div class="aula-pair">' +
    '<div class="pane"><h4>Original de ' + esc(row.fromName) + " · " + esc(row.src) +
    '</h4><div class="body">' + esc(row.srcText || "") + "</div></div>" +
    '<div class="pane pane-out"><h4>' + (deliveryDegraded ? "Traducción no disponible · " : "Lo que lees ") + languageName(displayTgt || row.tgt) + " · " + esc(displayTgt || row.tgt) +
    '</h4><div class="body">' + rendered + "</div></div></div>";

  if (attachment) {
    out +=
      '<div class="att-chip">' +
      '<span class="tag">' + esc(attachment.ext || "archivo") + "</span>" +
      '<span style="flex:1">' + esc(attachment.name) + " · " + esc(attachment.sizeLabel || "") +
      (attachment.pages ? " · " + esc(attachment.pages) + " pág." : "") +
      (attachment.words ? " · " + esc(attachment.words) + " palabras" : "") + "</span>" +
      '<button class="btn btn-sm" data-msg-download="' + esc(row.id) +
      '">Descargar</button>' +
      '<button class="btn btn-sm" data-msg-tr="' + esc(row.id) + '">Traducir documento</button></div>';
  }

  if (glossary.length) {
    out +=
      '<div class="row" style="margin-top:8px">' +
      glossary
        .map(
          (hit) =>
            '<span class="tag tag-accent" title="' + esc(hit.domain) + '">' + esc(hit.term) +
            (hit.target ? " → " + esc(hit.target) : "") + "</span>"
        )
        .join(" ") +
      "</div>";
  }

  if (extra) {
    out +=
      '<div class="msg-more"><div class="pane pane-out"><h4>Traducción a ' +
      esc(languageName(extra.tgt)) + " · " + esc(extra.tgt) +
      (extra.cached ? ' <span class="tag">caché</span>' : "") +
      (extra.degraded ? ' <span class="tag tag-warn">glosa</span>' : ' <span class="tag tag-ok">motor</span>') +
      '</h4><div class="body">' + esc(extra.text || "") + "</div></div></div>";
  }

  out +=
    '<div class="msg-tools">' +
    '<select class="msg-lang" data-msg-lang="' + esc(row.id) + '">' + msgLangOptions(defaultTgt) + "</select>" +
    '<button class="btn btn-sm btn-primary" data-msg-tr="' + esc(row.id) + '">Traducir</button>';
  Object.entries(row.translations || {}).forEach(([code, translation]) => {
    // Una salida del léxico puede conservar gran parte del original. No la
    // presentemos como una traducción completa: el botón permite reintentarla.
    if (translation && translation.degraded) {
      out += '<span class="tag tag-warn" title="Respaldo automático; puede conservar partes del original. Pulsa Traducir para reintentar.">respaldo parcial a ' + esc(languageName(code)) + "</span>";
    } else {
      out += '<span class="tag">traducción guardada a ' + esc(languageName(code)) + "</span>";
    }
  });
  out += '<span class="muted">Cualquiera de los dos roles puede pedir otra lengua.</span></div>';
  out += '<div class="aula-foot">' + esc((row.notes || []).join(" ")) + "</div></article>";
  return out;
}

async function viewMensajeria() {
  const session = state.session;
  if (!session) return '<div class="empty">Inicia sesión para usar la mensajería.</div>';

  await loadMsgDirectory();
  await loadMsgThreads();
  if (!state.msgThreads.length) {
    // Sin conversaciones todavía: un estudiante escribe primero a su profesor.
    let out0 =
      '<div class="page-head"><div><h2>Mensajería</h2><p>' + esc(session.name) +
      ". Aquí el docente y el estudiante se escriben, se envían documentos y cada uno los traduce " +
      "a la lengua que necesita.</p></div>" +
      '<div class="page-actions"><button class="btn btn-primary" id="msg-new">Nueva conversación</button></div></div>';
    out0 += '<div class="card"><div class="empty">Todavía no tienes conversaciones. ' +
      (isDocente()
        ? "Abre una con «Nueva conversación» y elige a tus estudiantes."
        : "Tu profesor abrirá el canal contigo; también puedes iniciarlo tú.") +
      "</div></div>";
    return out0;
  }
  if (!state.msgThreadId || !msgThreadById(state.msgThreadId)) {
    state.msgThreadId = state.msgThreads[0].id;
    await openMsgThread(state.msgThreadId, { silent: true });
    await api("/api/messaging/threads/" + state.msgThreadId + "/read", {
      method: "PUT", body: { userId: session.userId },
    }).then(() => loadMsgThreads()).catch(() => {});
  } else if (!state.msgMessages.length) {
    await openMsgThread(state.msgThreadId, { silent: true });
  }

  const thread = msgThreadById(state.msgThreadId) || {};
  const partner = msgPartner(thread);
  const here = esc(session.langName || session.langCode);

  // --- columna de conversaciones ---
  const list = state.msgThreads
    .map((row) => {
      const on = String(row.id) === String(state.msgThreadId);
      return (
        '<button class="thread-item' + (on ? " is-on" : "") + '" data-msg-open="' + esc(row.id) + '">' +
        '<span class="thread-title">' +
        (row.type === "group" ? '<span class="tag">grupo</span> ' : "") + esc(row.title) + "</span>" +
        '<span class="thread-preview">' +
        (row.lastFrom ? esc(row.lastFrom) + ": " : "") + esc(row.lastPreview || "Sin mensajes todavía") + "</span>" +
        '<span class="thread-meta">' +
        (row.unread ? '<span class="badge-unread">' + row.unread + " sin leer</span>" : "") +
        '<span class="muted">' + esc(row.messageCount || 0) + " mensajes</span>" +
        (row.lastKind === "documento" ? '<span class="tag">documento</span>' : "") +
        "</span></button>"
      );
    })
    .join("");

  let out =
    '<div class="page-head"><div><h2>Mensajería</h2><p>' + esc(session.name) + " · " +
    esc(session.jobTitle || "") + ". Escribes en " + here +
    (partner ? "; tu interlocutor es " + esc(partner.name) + " (" + esc(partner.langName || partner.langCode) + ")" : " (grupo del aula)") +
    '. El original de cada mensaje se conserva y su traducción se entrega al otro lado.</p></div>' +
    '<div class="page-actions"><button class="btn btn-primary" id="msg-new">Nueva conversación</button>' +
    '<button class="btn" id="msg-refresh">Actualizar</button></div></div>' +
    '<div class="aula-flow"><span class="chip-lang">' + here +
    '</span><span class="flow-arrow">→</span><span class="chip-lang">Ayllu traduce y adapta</span>' +
    '<span class="flow-arrow">→</span><span class="chip-lang">' +
    esc(partner ? partner.langName || partner.langCode : "varias lenguas del aula") + "</span></div>";

  out +=
    '<div class="msg-layout"><div class="msg-side"><div class="card"><h3>Tus conversaciones</h3>' +
    '<div class="thread-list">' + list + "</div></div></div><div>";

  out +=
    '<div class="card"><div class="card-head"><h3>' + esc(thread.title || "Conversación") + "</h3>" +
    '<span class="tag tag-accent">' + esc(state.msgMessages.length) + " mensajes</span></div>" +
    '<div class="msg-stream">' +
    (state.msgMessages.length
      ? state.msgMessages.map((row) => msgBubble(row)).join("")
      : '<div class="empty">Esta conversación aún no tiene mensajes. Escribe el primero abajo.</div>') +
    "</div></div>";

  // --- redactar ---
  out +=
    '<div class="card msg-compose"><h3>' +
    (isDocente() ? "Escribe al aula o adjunta un documento" : "Escribe a tu profesor") + "</h3>" +
    '<label class="field">Mensaje (elige el idioma del texto abajo)' +
    '<textarea id="msg-text" placeholder="' +
    (isDocente()
      ? "Hola, hoy veremos el agua del río y la semilla de la tierra."
      : "Profesora, mi casa está cerca del río y el camino de la escuela.") +
    '"></textarea></label>' +
    '<div class="form-grid">' +
    '<label class="field">Idioma en que escribes<select id="msg-src">' +
    msgLangOptions(session.langCode || "quy_Latn") + "</select></label>" +
    '<label class="field">Lengua de la entrega (a quién le llega traducido)' +
    '<select class="msg-lang" id="msg-tgt">' +
    (thread.type === "group" ? '<option value="auto" selected>Idioma de cada participante</option>' : "") +
    msgLangOptions(thread.type === "group" ? "auto" : ((partner && partner.langCode) || "quy_Latn")) + "</select></label>" +
    '<label class="field">Nivel<select id="msg-level"><option>básico</option>' +
    "<option>intermedio</option><option>avanzado</option></select></label>" +
    '<label class="field">Título / asunto<input id="msg-title" placeholder="' +
    (isDocente() ? "Ficha de fracciones" : "Mi tarea de hoy") + '"></label>' +
    "</div>" +
    '<div class="row"><button class="btn btn-primary" id="msg-send">Traducir y enviar</button>' +
    '<button class="btn" id="msg-pick">Adjuntar .pdf / .txt</button>' +
    (partner ? '<span class="chip-lang">Se entrega a ' + esc(partner.name) + " · " +
      esc(partner.langName || partner.langCode) + "</span>" : "") +
    '<input type="file" id="msg-file" accept=".pdf,.txt,application/pdf,text/plain" hidden>' +
    "</div>" +
    '<p class="hint">El documento se valida igual que en el escáner (extensión, bytes mágicos y ' +
    "tamaño máximo): un .docx renombrado no pasa. Tu texto original nunca se modifica y el adjunto " +
    "se descarga desde el propio mensaje.</p></div></div></div>";
  return out;
}

/* --- acciones ------------------------------------------------------------ */

async function sendMsg() {
  const session = state.session;
  const box = $("#msg-text");
  const text = box ? box.value.trim() : "";
  if (!text) { toast("Escribe un mensaje antes de enviarlo", "warn"); return; }
  const button = $("#msg-send");
  if (button) { button.disabled = true; button.textContent = "Traduciendo…"; }
  try {
    const row = await api("/api/messaging/threads/" + state.msgThreadId + "/messages", {
      method: "POST",
      body: {
        fromUserId: session.userId,
        text: text,
        src: (($('#msg-src') || {}).value || session.langCode),
        tgt: ($("#msg-tgt") || {}).value || session.langCode,
        level: ($("#msg-level") || {}).value || "básico",
        title: ($("#msg-title") || {}).value || "",
      },
    });
    toast(
      $("#msg-tgt").value === "auto"
        ? "Enviado. Cada participante lo ver\u00e1 en su idioma."
        : "Enviado: " + row.src + " -> " + row.tgt +
          (row.coverage === null || row.coverage === undefined ? "" : " - cobertura " + fmt(row.coverage, 1) + "%"),
      row.degraded ? "warn" : "ok",
      5200
    );
    await openMsgThread(state.msgThreadId, { silent: true });
    await loadMsgThreads();
    await render();
  } catch (err) {
    toast(err.message, "bad");
  } finally {
    if (button) { button.disabled = false; button.textContent = "Traducir y enviar"; }
  }
}

async function attachMsg(file) {
  const session = state.session;
  if (!file) return;
  const button = $("#msg-pick");
  if (button) { button.disabled = true; button.textContent = "Enviando documento…"; }
  const form = new FormData();
  form.append("file", file);
  form.append("fromUserId", String(session.userId));
  form.append("src", ($("#msg-src") || {}).value || session.langCode);
  form.append("targets", ($("#msg-tgt") || {}).value || session.langCode);
  form.append("level", ($("#msg-level") || {}).value || "básico");
  form.append("title", ($("#msg-title") || {}).value || file.name);
  try {
    const response = await fetch("/api/messaging/threads/" + state.msgThreadId + "/documents", {
      method: "POST",
      headers: session.token ? { Authorization: "Bearer " + session.token } : {},
      body: form,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "No se pudo adjuntar el documento");
    toast(
      $("#msg-tgt").value === "auto"
        ? "Documento entregado en el idioma de cada participante."
        : "Documento adjuntado y traducido a " + languageName(data.tgt),
      "ok", 5200
    );
    await openMsgThread(state.msgThreadId, { silent: true });
    await loadMsgThreads();
    await render();
  } catch (err) {
    toast(err.message, "bad", 5600);
  } finally {
    if (button) { button.disabled = false; button.textContent = "Adjuntar .pdf / .txt"; }
  }
}

async function translateMsg(messageId) {
  const selected = $('[data-msg-lang="' + messageId + '"]');
  const row = (state.msgMessages || []).find((item) => String(item.id) === String(messageId));
  const tgt = selected ? selected.value : msgTranslationTarget(row);
  try {
    const result = await api("/api/messaging/messages/" + messageId + "/translate", {
      method: "POST",
      body: { userId: state.session.userId, tgt: tgt, level: ($("#msg-level") || {}).value || "básico" },
    });
    state.msgMore[messageId] = result;
    if (row) row.translations = Object.assign({}, row.translations || {}, { [result.tgt]: result });
    toast(
      "Traducido a " + languageName(result.tgt) + (result.cached ? " (desde la caché del mensaje)" : "") +
      (result.degraded ? " · glosa" : ""),
      result.degraded ? "warn" : "ok",
      4200
    );
    await render();
  } catch (err) {
    toast(err.message, "bad");
  }
}

async function downloadMsgAttachment(messageId) {
  try {
    const headers = {};
    if (state.session && state.session.token) {
      headers.Authorization = "Bearer " + state.session.token;
    }
    const response = await fetch("/api/messaging/messages/" + messageId + "/attachment", { headers });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || ("HTTP " + response.status));
    }
    const row = (state.msgMessages || []).find((item) => String(item.id) === String(messageId));
    const link = document.createElement("a");
    const objectUrl = URL.createObjectURL(await response.blob());
    link.href = objectUrl;
    link.download = (row && row.attachment && row.attachment.name) || "documento";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (err) {
    toast(err.message, "bad");
  }
}

async function newThreadModal() {
  const users = await loadMsgDirectory();
  const session = state.session;
  const others = users.filter((u) => String(u.userId) !== String(session.userId));
  const wanted = isDocente() ? "estudiante" : "docente";
  const candidates = others.filter((u) => u.role === wanted);
  const body =
    '<div class="field"><span>Destinatarios · ' +
    esc(isDocente() ? "estudiantes" : "profesores") + "</span>" +
    (isDocente() ? '<label class="pick"><input type="checkbox" id="msg-group"> Conversación grupal (varios a la vez)</label>' : "") +
    '<div class="pick-list" id="msg-picks">' +
    (candidates.length
      ? candidates
          .map(
            (u) =>
              '<label class="pick"><input type="checkbox" value="' + esc(u.userId) +
              '" data-msg-pick> <b>' + esc(u.name) + '</b> <span class="muted">· ' + esc(u.role) +
              " · " + esc(u.langName || u.langCode) +
              (u.communityId ? " · " + esc(communityName(u.communityId)) : "") + "</span></label>"
          )
          .join("")
      : '<div class="empty">No hay cuentas de ese rol en el directorio.</div>') +
    "</div></div>" +
    '<label class="field">Título de la conversación<input id="msg-new-title" placeholder="Aula · quechua ayacuchano"></label>' +
    '<p class="hint">El docente puede abrir con varios estudiantes a la vez; el estudiante abre el canal con su profesor.</p>';
  openModal(
    "Nueva conversación",
    body,
    '<button class="btn btn-ghost" data-modal-cancel>Cancelar</button>' +
      '<button class="btn btn-primary" data-modal-confirm>Crear conversación</button>'
  );
  modalSubmit = async () => {
    const chosen = Array.prototype.slice
      .call(document.querySelectorAll("[data-msg-pick]"))
      .filter((box) => box.checked)
      .map((box) => Number(box.value));
    if (!chosen.length) { toast("Elige al menos un destinatario", "warn"); return; }
    if (isDocente() && !($("#msg-group") || {}).checked && chosen.length > 1) {
      toast("Marca «Conversación grupal» para escribir a varios a la vez", "warn");
      return;
    }
    try {
      const row = await api("/api/messaging/threads", {
        method: "POST",
        body: {
          fromUserId: session.userId,
          toUserIds: chosen,
          group: isDocente() && !!($("#msg-group") || {}).checked,
          title: ($("#msg-new-title") || {}).value || "",
        },
      });
      closeModal();
      await loadMsgThreads();
      await openMsgThread(row.id, { silent: true });
      await render();
      toast("Conversación creada", "ok");
    } catch (err) {
      toast(err.message, "bad");
    }
  };
}

document.addEventListener("click", async (event) => {
  const open = event.target.closest("[data-msg-open]");
  if (open) {
    await openMsgThread(open.dataset.msgOpen);
    await render();
    return;
  }
  if (event.target.closest("#msg-send")) { await sendMsg(); return; }
  if (event.target.closest("#msg-new")) { await newThreadModal(); return; }
  if (event.target.closest("#msg-pick")) {
    const input = document.getElementById("msg-file");
    if (input) input.click();
    return;
  }
  if (event.target.closest("#msg-refresh")) {
    await openMsgThread(state.msgThreadId, { silent: true });
    await loadMsgThreads();
    await render();
    return;
  }
  const tr = event.target.closest("[data-msg-tr]");
  if (tr) { await translateMsg(tr.dataset.msgTr); return; }
  const download = event.target.closest("[data-msg-download]");
  if (download) { await downloadMsgAttachment(download.dataset.msgDownload); return; }
});

document.addEventListener("change", async (event) => {
  if (event.target.id === "msg-file" && event.target.files && event.target.files.length) {
    const file = event.target.files[0];
    event.target.value = "";
    await attachMsg(file);
  }
});

const VIEWS = {
  dashboard: viewDashboard,
  adapt: viewAdapt,
  scan: viewScan,
  communities: viewCommunities,
  students: viewStudents,
  library: viewLibrary,
  analytics: viewAnalytics,
  glossary: viewGlossary,
  admin: viewAdmin,
  aula: () => viewRouter("aula"),
  aula_docente: () => viewRouter("aula_docente"),
  mensajeria: viewMensajeria,
};

async function refresh(what) {
  await loadCommon();
  if (what === "glossary" || what === "communities") { /* refresco simple */ }
  await render();
}

async function render() {
  paintNav();
  const id = route();
  const host = $("#view");
  host.innerHTML = '<div class="empty">Cargando…</div>';
  try {
    host.innerHTML = await VIEWS[id]();
  } catch (err) {
    host.innerHTML = '<div class="alert alert-bad"><strong>Error al cargar el módulo</strong><span>' +
      esc(err.message) + "</span></div>";
  }
  applyI18n();
}

/* --------------------------------- eventos -------------------------------- */

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-route],[data-modal-cancel],[data-modal-confirm]," +
    "[data-new-community],[data-edit-community],[data-del-community],[data-new-student],[data-edit-student]," +
    "[data-del-student],[data-new-material],[data-edit-material],[data-del-material],[data-adapt-material]," +
    "[data-new-term],[data-edit-term],[data-del-term],[data-import-glossary],[data-new-feedback]," +
    "[data-page],[data-export],[data-fill-demo],[id=admin-ping]," +
    "[id=adapt-run],[id=adapt-prompt],[id=adapt-feedback]");
  if (!target) {
    if (event.target.id === "modal") closeModal();
    return;
  }
  const dataset = target.dataset;

  if (dataset.route) { navigate(dataset.route); return; }
  if (target.hasAttribute("data-modal-cancel")) { closeModal(); return; }
  if (target.hasAttribute("data-modal-confirm")) { if (modalSubmit) await modalSubmit(); return; }

  if (target.hasAttribute("data-new-community")) { communityModal(null); return; }
  if (dataset.editCommunity) {
    const row = state.communities.find((c) => String(c.id) === String(dataset.editCommunity));
    communityModal(row); return;
  }
  if (dataset.delCommunity) {
    const row = state.communities.find((c) => String(c.id) === String(dataset.delCommunity));
    confirmModal(t("Borrar comunidad"), "Se eliminará «" + (row ? row.name : "") + "». Esta acción no se puede deshacer.", async () => {
      try { await api("/api/communities/" + dataset.delCommunity, { method: "DELETE" }); closeModal(); await refresh(); toast("Comunidad borrada", "ok"); }
      catch (err) { toast(err.message, "bad"); }
    });
    return;
  }
  if (target.hasAttribute("data-new-student")) { studentModal(null); return; }
  if (dataset.editStudent) {
    const row = state.students.find((s) => String(s.id) === String(dataset.editStudent));
    studentModal(row); return;
  }
  if (dataset.delStudent) {
    confirmModal(t("Borrar estudiante"), "Se eliminará la medición pre/post de este estudiante.", async () => {
      try { await api("/api/students/" + dataset.delStudent, { method: "DELETE" }); closeModal(); await refresh(); toast("Estudiante borrado", "ok"); }
      catch (err) { toast(err.message, "bad"); }
    });
    return;
  }
  if (target.hasAttribute("data-new-material")) { materialModal(null); return; }
  if (dataset.editMaterial) {
    const row = state.materials.find((m) => String(m.id) === String(dataset.editMaterial));
    materialModal(row); return;
  }
  if (dataset.delMaterial) {
    confirmModal(t("Borrar material"), "Se eliminará el material de la biblioteca.", async () => {
      try { await api("/api/materials/" + dataset.delMaterial, { method: "DELETE" }); closeModal(); await refresh(); toast("Material borrado", "ok"); }
      catch (err) { toast(err.message, "bad"); }
    });
    return;
  }
  if (dataset.adaptMaterial) {
    const row = state.materials.find((m) => String(m.id) === String(dataset.adaptMaterial));
    if (row) {
      const selectedStudent = state.students.find((student) => String(student.id) === String(state.libraryStudentId));
      lastAdapt = { _src: row.snippet, tgt: (selectedStudent && selectedStudent.langCode) || undefined };
      navigate("adapt");
      setTimeout(() => {
        const box = $("#adapt-text");
        if (box) { box.value = row.snippet; toast(t("Fragmento cargado en el adaptador"), "ok"); }
      }, 120);
    }
    return;
  }
  if (target.hasAttribute("data-new-term")) { termModal(null); return; }
  if (dataset.editTerm) {
    const row = state.glossary.find((g) => String(g.id) === String(dataset.editTerm));
    termModal(row); return;
  }
  if (dataset.delTerm) {
    confirmModal(t("Borrar término"), "Se eliminará el término y sus traducciones del glosario.", async () => {
      try { await api("/api/glossary/" + dataset.delTerm, { method: "DELETE" }); closeModal(); await refresh("glossary"); toast("Término borrado", "ok"); }
      catch (err) { toast(err.message, "bad"); }
    });
    return;
  }
  if (target.hasAttribute("data-import-glossary")) { importModal(); return; }
  if (target.hasAttribute("data-new-feedback")) { feedbackModal(); return; }
  if (target.id === "adapt-run") { await runAdapt(); return; }
  if (target.id === "adapt-prompt") { promptModal(); return; }
  if (target.id === "adapt-feedback") { feedbackModal(); return; }
  if (dataset.page) {
    const key = dataset.page;
    state.page[key] = Math.max(1, (state.page[key] || 1) + Number(dataset.dir || 0));
    await render(); return;
  }
  if (dataset.export) {
    window.location.href = "/api/export/" + dataset.export + ".csv";
    toast("Descargando CSV de " + dataset.export, "ok");
    return;
  }
  if (target.hasAttribute("data-fill-demo")) {
    const box = $("#adapt-text");
    if (box) {
      box.value = "Una fracción es una parte de un todo. La semilla germina en la tierra húmeda y el agua sube al cielo cuando el sol la calienta.";
      toast(t("Ejemplo cargado"), "ok");
    }
    return;
  }
  if (target.id === "admin-ping") {
    try {
      const health = await api("/healthz");
      const box = $("#health-box");
      if (box) box.textContent = JSON.stringify(health, null, 2);
      paintHealth(health);
      toast("healthz OK · modo " + health.mode, "ok");
    } catch (err) { toast("healthz sin respuesta: " + err.message, "bad"); }
    return;
  }
});

document.addEventListener("change", (event) => {
  if (event.target.id === "library-student") {
    state.libraryStudentId = event.target.value || null;
    const student = state.students.find((row) => String(row.id) === String(state.libraryStudentId));
    if (student) toast("Destino: " + languageName(student.langCode) + " ? " + student.name, "ok");
  }
  if (event.target.id === "f-color") { /* reservado */ }
  if (event.target.id === "f-validated") { /* reservado */ }
});

/* búsqueda global */
let searchTimer = null;
document.addEventListener("input", (event) => {
  if (event.target.id === "gloss-q") {
    state.q.glossary = event.target.value;
    state.page.glossary = 1;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => render(), 260);
    return;
  }
  if (event.target.id === "global-search") {
    const value = event.target.value.trim();
    clearTimeout(searchTimer);
    if (!value) { $("#search-panel").hidden = true; return; }
    searchTimer = setTimeout(async () => {
      try {
        const data = await api("/api/search?q=" + encodeURIComponent(value));
        const panel = $("#search-panel");
        panel.innerHTML = (data.results || []).map((row) =>
          '<div class="search-row" data-jump="' + esc(row.type) + '"><span class="tag tag-accent">' +
          esc(row.type) + "</span><span style=\"flex:1\">" + esc(row.title) + '</span><span class="muted">' +
          esc(row.detail) + "</span></div>"
        ).join("") || '<div class="search-row"><span class="muted">Sin coincidencias</span></div>';
        panel.hidden = false;
      } catch (err) { /* silencio: la búsqueda no debe romper la vista */ }
    }, 240);
  }
});

document.addEventListener("click", (event) => {
  const row = event.target.closest("[data-jump]");
  if (row) {
    $("#search-panel").hidden = true;
    $("#global-search").value = "";
    const map = { comunidad: "communities", estudiante: "students", glosario: "glossary", material: "library" };
    navigate(map[row.dataset.jump] || "dashboard");
  } else if (!event.target.closest(".search")) {
    $("#search-panel").hidden = true;
  }
});

/* --------------------------- aula: dos roles ------------------------------ */

document.addEventListener("click", async (event) => {
  const pick = event.target.closest("[data-login-email]");
  if (pick) {
    await doLogin(pick.dataset.loginEmail, pick.dataset.loginPass || "");
    return;
  }
  if (event.target.closest("[data-aula-logout]")) { logout(); return; }
  if (event.target.closest("#aula-send")) { await sendAula(); return; }
  if (event.target.closest("#aula-activity-send")) { await sendAulaActivity(); return; }
  const retryAula = event.target.closest("[data-aula-translate]");
  if (retryAula) { await retryAulaTranslation(retryAula.dataset.aulaTranslate); return; }
  const activityReply = event.target.closest("[data-activity-reply]");
  if (activityReply) {
    const title = $("#aula-title");
    const text = $("#aula-text");
    const recipient = $("#aula-to");
    const kind = $("#aula-kind");
    if (title) title.value = "Respuesta: " + activityReply.dataset.activityReply;
    if (text) {
      text.value = "";
      text.focus();
    }
    if (recipient && activityReply.dataset.activityTeacher) {
      recipient.value = activityReply.dataset.activityTeacher;
    }
    if (kind) kind.value = "mensaje";
    window.scrollTo({ top: 0, behavior: "smooth" });
    toast("Escribe tu respuesta a esta actividad.", "ok", 2200);
    return;
  }
  const demo = event.target.closest("#aula-demo");
  if (demo) {
    const box = $("#aula-text");
    if (box) {
      box.value = isDocente()
        ? "Hola Ana, hoy veremos el agua del río y la semilla de la tierra."
        : "Profesora, mi casa está cerca del río y el camino de la escuela.";
      toast(t("Ejemplo cargado"), "ok", 1500);
    }
    return;
  }
});

document.addEventListener("submit", async (event) => {
  if (event.target.id !== "login-form") return;
  event.preventDefault();
  const email = ($("#login-email") || {}).value || "";
  const password = ($("#login-password") || {}).value || "";
  await doLogin(email.trim(), password);
});

/* ------------------------------- arranque --------------------------------- */

function paintHealth(health) {
  const dot = $("#health-dot");
  const side = $("#side-dot");
  const mode = $("#side-mode");
  const healthy = health && health.status === "ok";
  const degraded = health && health.degraded;
  const klass = healthy ? (degraded ? "dot-warn" : "dot-ok") : "dot-bad";
  [dot, side].forEach((node) => { if (node) node.className = "dot " + klass; });
  if (mode) mode.textContent = health ? health.mode + (degraded ? " · degradado" : "") : "sin datos";
}

function paintClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  $("#clock").textContent =
    pad(now.getUTCHours()) + ":" + pad(now.getUTCMinutes()) + ":" + pad(now.getUTCSeconds()) + " UTC";
}

async function pollHealth() {
  try { paintHealth(await api("/healthz")); }
  catch (err) { paintHealth(null); }
}

async function boot() {
  document.documentElement.dataset.theme = state.theme;
  await loadLang();
  $("#collapse").addEventListener("click", () => $("#sidebar").classList.toggle("collapsed"));
  $("#modal-close").addEventListener("click", closeModal);
  $("#theme").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = state.theme;
    toast("Tema " + (state.theme === "dark" ? "oscuro" : "claro"), "ok", 1400);
  });
  window.addEventListener("hashchange", async () => { await render(); });

  // --- escáner de documentos: arrastrar y soltar (delegado sobre document) ---
  const highlightZone = (event) => {
    const zone = document.getElementById("dropzone");
    if (!zone) return;
    const types = (event.dataTransfer && event.dataTransfer.types) || [];
    if (Array.prototype.indexOf.call(types, "Files") !== -1) {
      event.preventDefault();
      zone.classList.add("over");
    }
  };
  document.addEventListener("dragover", highlightZone);
  document.addEventListener("dragenter", highlightZone);
  document.addEventListener("dragleave", (event) => {
    const zone = document.getElementById("dropzone");
    if (zone && !zone.contains(event.relatedTarget)) zone.classList.remove("over");
  });
  document.addEventListener("drop", async (event) => {
    const zone = document.getElementById("dropzone");
    if (!zone || !zone.contains(event.target)) return;
    if (!event.dataTransfer || !event.dataTransfer.files || !event.dataTransfer.files.length) return;
    event.preventDefault();
    zone.classList.remove("over");
    if (event.dataTransfer.files.length > 1) toast("Sólo se escaneará el primer archivo", "warn");
    stageScanFile(event.dataTransfer.files[0]);
  });
  document.addEventListener("change", async (event) => {
    if (event.target.id === "scan-input" && event.target.files && event.target.files.length) {
      const file = event.target.files[0];
      event.target.value = "";
      stageScanFile(file);
    }
    if (event.target.matches && event.target.matches("[data-lang-select]")) {
      await changeLang(event.target.value);
      return;
    }
    if (event.target.id === "scan-langs") {
      state.scanTargets = readScanTargets();
      paintScanTargetChip();
    }
    if (event.target.id === "scan-to") {
      state.scanRecipientId = event.target.value;
      const recipient = (state.demoUsers || []).find((user) => String(user.userId) === String(event.target.value));
      state.scanTargets = recipient && recipient.langCode ? [recipient.langCode] : [];
      const languageSelect = document.getElementById("scan-langs");
      if (languageSelect && state.scanTargets[0]) languageSelect.value = state.scanTargets[0];
      paintScanTargetChip();
    }
  });

  document.addEventListener("click", async (event) => {
    const zone = event.target.closest("#dropzone");
    const demo = event.target.closest("#scan-demo");
    const reload = event.target.closest("[data-doc-reload]");
    const adapt = event.target.closest("[data-doc-adapt]");
    const save = event.target.closest("[data-doc-save]");
    const copy = event.target.closest("[data-doc-copy]");
    const download = event.target.closest("[data-doc-download]");
    const tab = event.target.closest("[data-doc-tab]");
    const fullscreen = event.target.closest("#doc-fullscreen");

    if (zone) {
      const input = document.getElementById("scan-input");
      if (input) input.click();
      return;
    }
    if (demo) { await scanDemoTxt(); return; }
    const sendScan = event.target.closest("#scan-send");
    if (sendScan) {
      if (!state.scanPendingFile) { toast("Primero elige un archivo.", "warn"); return; }
      sendScan.disabled = true;
      await scanFile(state.scanPendingFile);
      return;
    }
    const openScanChat = event.target.closest("#scan-open-chat");
    if (openScanChat) {
      navigate("mensajeria");
      await render();
      return;
    }
    if (reload) {
      const doc = resolveDoc(reload.dataset.docReload);
      if (doc) {
        state.lastDoc = doc;
        const out = document.getElementById("scan-out");
        if (out) out.innerHTML = renderScanDoc(doc);
      }
      return;
    }
    if (adapt) {
      const doc = resolveDoc(adapt.dataset.docAdapt);
      if (!doc) return;
      if (doc.textless) { toast(t("Este PDF no tiene texto extraíble (necesita OCR)"), "warn"); return; }
      const snippet = String(doc.text || "").slice(0, 4000);
      lastAdapt = { _src: snippet };
      navigate("adapt");
      setTimeout(() => {
        const box = document.getElementById("adapt-text");
        if (box) { box.value = snippet; toast(t("Texto cargado en el adaptador"), "ok"); }
      }, 150);
      return;
    }
    if (tab) { showDocTab(tab.dataset.docTab); return; }
    if (fullscreen) {
      openDocPreview(state.lastDoc || state.docs[0]);
      return;
    }
    if (save) {
      const doc = resolveDoc(save.dataset.docSave);
      if (!doc) return;
      try {
        await api("/api/materials", {
          method: "POST",
          body: {
            title: String(doc.name).replace(/\.[^.]+$/, ""),
            kind: doc.ext === ".pdf" ? "lectura" : "ficha",
            langCode: "spa_Latn",
            level: "todos",
            size: doc.pages + " pág. · " + doc.sizeLabel,
            snippet: String(doc.text || "").slice(0, 600),
          },
        });
        await refresh("library");
        toast(t("Guardado en la biblioteca"), "ok");
      } catch (err) { toast(err.message, "bad"); }
      return;
    }
    if (copy) {
      const doc = resolveDoc(copy.dataset.docCopy);
      if (!doc) return;
      try {
        await navigator.clipboard.writeText(String(doc.text || ""));
        toast(t("Texto copiado al portapapeles"), "ok");
      } catch (err) { toast(t("El navegador bloqueó el portapapeles"), "warn"); }
      return;
    }
    if (download) {
      const doc = resolveDoc(download.dataset.docDownload);
      if (!doc) return;
      const blob = new Blob([String(doc.text || "")], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = String(doc.name).replace(/\.[^.]+$/, "") + ".txt";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast(t("Descargando texto extraído"), "ok");
      return;
    }
  });

  await loadScanLimits();
  paintClock();
  setInterval(paintClock, 1000);
  setInterval(pollHealth, 30000);
  await pollHealth();
  await loadSession();
  try { await loadCommon(); } catch (err) { /* la vista mostrará el error */ }
  if (!location.hash) {
    location.hash = state.session && !isDocente() ? "#/aula" : "#/dashboard";
  }
  await render();
  applyI18n();
  if (lastAdapt === null) { /* primera visita */ }
}

document.addEventListener("DOMContentLoaded", boot);
