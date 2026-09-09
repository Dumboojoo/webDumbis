"use strict";

const DAYS = ["Mo", "Di", "Mi", "Do", "Fr"];
const DAY_LABELS = { Mo: "Montag", Di: "Dienstag", Mi: "Mittwoch", Do: "Donnerstag", Fr: "Freitag" };
const MAX_RESULTS = 30;
const TOP_VIEWS = ["suche", "schueler", "kurse", "gemeinsam", "lehrer"];

const view = document.getElementById("view");
const navEl = document.getElementById("nav");
const switchEl = document.getElementById("cohortSwitch");
const sideFoot = document.getElementById("sideFoot");
const pageFoot = document.getElementById("pageFoot");

/* --------------------------------------------------------------------- icons */
const I = (p) =>
  `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
  `stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const ICONS = {
  search: I(`<circle cx="11" cy="11" r="7"/><line x1="20.5" y1="20.5" x2="16.5" y2="16.5"/>`),
  users: I(`<path d="M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19"/>` +
    `<circle cx="10" cy="8" r="3.4"/><path d="M20 19v-1.5a3.5 3.5 0 0 0-2.7-3.4"/>` +
    `<path d="M15.5 4.7a3.4 3.4 0 0 1 0 6.6"/>`),
  book: I(`<path d="M12 7C12 5.6 10.6 4.5 8 4.5H4V17h4.7c1.9 0 3.3 1 3.3 2.5"/>` +
    `<path d="M12 7c0-1.4 1.4-2.5 4-2.5h4V17h-4.7c-1.9 0-3.3 1-3.3 2.5"/><path d="M12 7v12.5"/>`),
  venn: I(`<circle cx="9.5" cy="12" r="5.7"/><circle cx="14.5" cy="12" r="5.7"/>`),
  cap: I(`<path d="M12 4.5 2.5 9 12 13.5 21.5 9 12 4.5Z"/>` +
    `<path d="M6.5 11.3V16c0 1.6 2.5 3 5.5 3s5.5-1.4 5.5-3v-4.7"/><line x1="21.5" y1="9" x2="21.5" y2="13.5"/>`),
};
const NAV = [
  { id: "suche", label: "Suche", short: "Suche", icon: "search" },
  { id: "schueler", label: "Schüler/innen", short: "Schüler", icon: "users" },
  { id: "kurse", label: "Kurse", short: "Kurse", icon: "book" },
  { id: "gemeinsam", label: "Gemeinsame Kurse", short: "Gemeinsam", icon: "venn" },
  { id: "lehrer", label: "Lehrkräfte", short: "Lehrer", icon: "cap" },
];

/* --------------------------------------------------------------------- state */
let meta = null;
let cohortId = null;
const store = {};   // id -> built cohort data
let cur = null;     // active cohort data

/* -------------------------------------------------------------------- helpers */
function norm(s) {
  return (s || "").toLowerCase().replace(/ß/g, "ss").normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").replace(/oe/g, "o").replace(/ae/g, "a").replace(/ue/g, "u");
}
function esc(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function parseLabel(label, code) {
  const m = /^(\S+)\s*\((.+)\)\s*$/.exec(label || "");
  if (m) return { code: m[1], desc: m[2] };
  return { code: code || label || "", desc: "" };
}
const deCmp = (a, b) => a.localeCompare(b, "de");
const byName = (a, b) => deCmp(a.name, b.name);
const teacherKey = (t) => (t || "").replace(/^(Herr|Frau)\s+/, "");
const kindLabel = (k) => (k === "LK" ? "Leistungskurs" : "Basiskurs");
const matchMobile = () => window.matchMedia("(max-width: 860px)").matches;

function courseSort(a, b) {
  if (a.kind !== b.kind) return a.kind === "LK" ? -1 : 1;
  return (parseInt(a.index || "0", 10) - parseInt(b.index || "0", 10)) ||
    a.code.localeCompare(b.code);
}
function groupLabel(g) {
  if (!g) return "";
  return /^\d/.test(g) ? "Klasse " + g : "Tutor/in " + g;
}

/* Link builder – jeder interne Link traegt die aktive Stufe. */
const L = (...seg) => "#/" + [cohortId, ...seg.filter((x) => x != null)].join("/");
const cohortInfo = (id) => meta.cohorts.find((c) => c.id === id);

/* 🎀 Pinky-Modus – kleine Spielerei, umschaltbar unten auf der Startseite. */
function pinkyOn() {
  try { return localStorage.getItem("pinky") === "1"; } catch (e) { return false; }
}
function applyPinky(on) {
  document.documentElement.toggleAttribute("data-pinky", on);
  const tc = document.querySelector('meta[name="theme-color"]');
  if (tc) tc.setAttribute("content", on ? "#ff1493" : "#1f3a68");
}

/* ------------------------------------------------------------ Datum / Wochen */
const MONTHS_SHORT = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.",
  "Sept.", "Okt.", "Nov.", "Dez."];
const MONTHS_LONG = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
  "August", "September", "Oktober", "November", "Dezember"];

function parseISO(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
  return m ? new Date(+m[1], +m[2] - 1, +m[3], 12) : null;
}
function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-` +
    `${String(d.getDate()).padStart(2, "0")}`;
}
function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
function mondayOf(d) {
  return addDays(d, -((d.getDay() + 6) % 7));
}
function sameISO(a, b) { return isoDate(a) === isoDate(b); }
const pad2 = (n) => String(n).padStart(2, "0");

function isoWeekNum(d) {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  t.setDate(t.getDate() + 4 - (t.getDay() || 7));
  const yearStart = new Date(t.getFullYear(), 0, 1);
  return Math.ceil(((t - yearStart) / 86400000 + 1) / 7);
}
function fmtD(d) { return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.`; }

function fmtWeekLabel(mon) {
  const fri = addDays(mon, 4);
  const range = mon.getMonth() === fri.getMonth()
    ? `${mon.getDate()}.–${fri.getDate()}. ${MONTHS_SHORT[fri.getMonth()]}`
    : `${mon.getDate()}. ${MONTHS_SHORT[mon.getMonth()]} – ${fri.getDate()}. ${MONTHS_SHORT[fri.getMonth()]}`;
  return `${range} ${fri.getFullYear()} · KW ${isoWeekNum(mon)}`;
}

/* Ferien / Feiertage (data/calendar.json) */
let calendar = { free: [] };

function freeOn(d) {
  const iso = isoDate(d);
  for (const e of calendar.free || []) {
    const from = e.from || e.date;
    const to = e.to || e.date;
    if (from && to && iso >= from && iso <= to) return { label: e.label || "unterrichtsfrei" };
  }
  return null;
}
function weekFullyFree(mon) {
  const labels = [];
  for (let i = 0; i < 5; i++) {
    const f = freeOn(addDays(mon, i));
    if (!f) return null;
    labels.push(f.label);
  }
  // häufigstes Label zurückgeben
  const count = {};
  let best = labels[0];
  for (const l of labels) { count[l] = (count[l] || 0) + 1; if (count[l] > (count[best] || 0)) best = l; }
  return best;
}
function schoolBounds() {
  const lo = parseISO(calendar.schoolYearStart) || new Date(2000, 0, 1, 12);
  const hi = parseISO(calendar.schoolYearEnd) || new Date(2100, 0, 1, 12);
  return [mondayOf(lo), mondayOf(hi)];
}
function clampMonday(mon) {
  const [lo, hi] = schoolBounds();
  if (mon < lo) return lo;
  if (mon > hi) return hi;
  return mon;
}

/* ----------------------------------------------------------------------- init */
async function init() {
  try {
    const [m, cal] = await Promise.all([
      fetch("data/meta.json").then((r) => r.json()),
      fetch("data/calendar.json").then((r) => r.json()).catch(() => ({ free: [] })),
    ]);
    meta = m;
    calendar = cal && Array.isArray(cal.free) ? cal : { free: [] };
  } catch (e) {
    view.innerHTML = "<p class='empty'>Daten konnten nicht geladen werden.</p>";
    return;
  }
  if (!meta.cohorts || !meta.cohorts.length) {
    view.innerHTML = "<p class='empty'>Keine Stufendaten vorhanden.</p>";
    return;
  }

  applyPinky(pinkyOn());

  const ids = meta.cohorts.map((c) => c.id);
  let saved = null;
  try { saved = localStorage.getItem("cohort"); } catch (e) { /* ignore */ }
  cohortId = ids.includes(saved) ? saved : ids[0];

  navEl.innerHTML = NAV.map((n) =>
    `<a data-nav="${n.id}">${ICONS[n.icon]}` +
    `<span class="nav-label">${esc(n.label)}</span>` +
    `<span class="nav-label-m">${esc(n.short)}</span></a>`).join("");

  window.addEventListener("hashchange", route);
  route();
}

async function loadCohort(id) {
  if (store[id]) return store[id];
  const [sData, cData] = await Promise.all([
    fetch(`data/${id}/students.json`).then((r) => r.json()),
    fetch(`data/${id}/courses.json`).then((r) => r.json()),
  ]);
  const students = sData.students || [];
  const courses = cData.courses || [];
  const byNr = new Map(students.map((s) => [s.nr, s]));
  const byCode = new Map(courses.map((c) => [c.code, c]));
  const studentCodes = new Map();
  for (const s of students) {
    const set = new Set();
    for (const d of DAYS) for (const cell of s.timetable[d] || []) if (cell) set.add(cell.code);
    studentCodes.set(s.nr, set);
  }
  const coursesByTeacher = new Map();
  const bySubject = new Map();
  for (const c of courses) {
    (coursesByTeacher.get(c.teacher) || coursesByTeacher.set(c.teacher, []).get(c.teacher)).push(c);
    const sub = c.subject || "Sonstige";
    (bySubject.get(sub) || bySubject.set(sub, []).get(sub)).push(c);
  }
  for (const arr of coursesByTeacher.values()) arr.sort(courseSort);
  const subjectsOrdered = [...bySubject.entries()].sort((a, b) => deCmp(a[0], b[0]));
  for (const [, arr] of subjectsOrdered) arr.sort(courseSort);

  store[id] = {
    id, students, courses, byNr, byCode, studentCodes, coursesByTeacher, subjectsOrdered,
    info: cohortInfo(id),
  };
  return store[id];
}

/* --------------------------------------------------------------------- chrome */
function renderChrome(activeNav) {
  switchEl.innerHTML = meta.cohorts.map((c) =>
    `<a href="#/${c.id}/suche" class="cs-btn${c.id === cohortId ? " active" : ""}" ` +
    `aria-current="${c.id === cohortId ? "true" : "false"}">${esc(c.label)}` +
    `<span class="cs-abi">Abi ${esc(c.abi)}</span></a>`).join("");

  navEl.querySelectorAll("a").forEach((a) => {
    a.setAttribute("href", L(a.dataset.nav));
    a.classList.toggle("active", a.dataset.nav === activeNav);
  });

  const info = cohortInfo(cohortId);
  const bits = [];
  if (info) {
    bits.push(`${esc(info.label)} · Abi ${esc(info.abi)}`);
    if (info.validFrom) bits.push("Plan gültig ab " + esc(info.validFrom));
    bits.push(`${info.studentCount} Schüler/innen · ${info.courseCount} Kurse`);
  }
  if (meta.generatedAt) bits.push("Datenstand " + esc(meta.generatedAt));
  sideFoot.innerHTML = bits.join("<br>");
  pageFoot.innerHTML =
    `<span>Privates Projekt, nicht von der Schule. Ohne Gewähr.</span>` +
    (info && info.validFrom
      ? `<span>${esc(info.label)} · Plan gültig ab ${esc(info.validFrom)}` +
        (meta.generatedAt ? ` · Stand ${esc(meta.generatedAt)}` : "") + `</span>`
      : "");
}

/* --------------------------------------------------------------------- router */
async function route() {
  const raw = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  const parts = raw.split("/").filter((x, i) => x !== "" || i === 0);
  const ids = meta.cohorts.map((c) => c.id);

  if (parts[0] === "" || parts[0] === "start") {
    renderChrome(null);
    renderHome();
    window.scrollTo(0, 0);
    return;
  }
  if (!ids.includes(parts[0])) {
    location.replace("#/" + cohortId + "/" + parts.join("/"));  // Altlink -> Stufe voranstellen
    return;
  }

  cohortId = parts[0];
  try { localStorage.setItem("cohort", cohortId); } catch (e) { /* ignore */ }
  const v = parts[1] || "suche";
  const a = parts[2];
  const b = parts[3];
  const week = parts[3] === "w" && parseISO(parts[4]) ? parts[4] : null;

  try {
    cur = await loadCohort(cohortId);
  } catch (e) {
    renderChrome(null);
    view.innerHTML = "<p class='empty'>Stufendaten konnten nicht geladen werden.</p>";
    return;
  }

  let activeNav = TOP_VIEWS.includes(v) ? v : null;
  switch (v) {
    case "suche": renderSearch(); break;
    case "schueler": renderStudentList(); break;
    case "kurse": renderCourseList(); break;
    case "gemeinsam": renderShared(a, b); break;
    case "lehrer": renderTeacherList(); break;
    case "s": renderStudent(a, week); activeNav = "schueler"; break;
    case "k": renderCourse(a); activeNav = "kurse"; break;
    case "l": renderTeacher(a); activeNav = "lehrer"; break;
    default: renderSearch(); activeNav = "suche";
  }
  renderChrome(activeNav);
  window.scrollTo(0, 0);
}

/* ---------------------------------------------------------------------- home */
function renderHome() {
  cur = null;
  const chooser = meta.cohorts.map((c) =>
    `<a class="stufe" href="#/${c.id}/suche"><span class="stufe-k">${esc(c.label)}</span>` +
    `<span class="stufe-meta">Abiturjahrgang ${esc(c.abi)}<br>` +
    `${c.studentCount} Schüler/innen · ${c.courseCount} Kurse` +
    (c.validFrom ? `<br>Plan gültig ab ${esc(c.validFrom)}` : "") +
    `</span></a>`).join("");

  view.innerHTML =
    `<section class="home">` +
    `<h1 class="home-title"><span class="wm-web">web</span><span class="wm-main">Dumbis</span></h1>` +
    `<p class="lead">Die Schule gibt die Stundenpläne nur als PDF raus. Jedes Mal den ` +
    `eigenen Plan da rauszusuchen nervt, also habe ich das hier gebaut.</p>` +
    `<p class="home-text">Namen oder Schülernummer eintippen, dann kommt der Stundenplan. ` +
    `Man kann auch durch alle Kurse und Lehrkräfte gehen oder zwei Leute vergleichen und sehen, ` +
    `welche Kurse sie zusammen haben. K1 und K2 laufen getrennt – oben umstellen.</p>` +
    `<h2 class="group-title">Stufe wählen</h2>` +
    `<div class="stufen">${chooser}</div>` +
    `<p class="disclaimer">Privates Projekt, nicht von der Schule und ohne Gewähr. Wenn hier was ` +
    `anderes steht als am Aushang, dann stimmt der Aushang.</p>` +
    `<button type="button" class="pinky-toggle" id="pinkyBtn"></button>` +
    `</section>`;

  const pb = document.getElementById("pinkyBtn");
  const setLabel = () => {
    pb.textContent = pinkyOn() ? "🎀 Pinky-Modus aus" : "🎀 Pinky-Modus an";
    pb.setAttribute("aria-pressed", pinkyOn() ? "true" : "false");
  };
  setLabel();
  pb.addEventListener("click", () => {
    const now = !pinkyOn();
    try { localStorage.setItem("pinky", now ? "1" : "0"); } catch (e) { /* ignore */ }
    applyPinky(now);
    setLabel();
  });
}

/* -------------------------------------------------------------------- search */
function searchStudents(term) {
  const nq = norm(term);
  const digits = term.replace(/\D/g, "").replace(/^0+/, "");
  const scored = [];
  for (const s of cur.students) {
    const name = norm(s.name);
    let score = -1;
    if (digits && s.nr.replace(/^0+/, "").startsWith(digits)) score = 0;
    else if (name.startsWith(nq)) score = 1;
    else if (name.includes(nq)) score = 2;
    if (score >= 0) scored.push([score, s]);
  }
  scored.sort((a, b) => a[0] - b[0] || byName(a[1], b[1]));
  return scored.slice(0, MAX_RESULTS).map((x) => x[1]);
}

function renderSearch() {
  view.innerHTML =
    `<h1>Schüler suchen</h1>` +
    `<p class="sub">${esc(cur.info.label)} · Abi ${esc(cur.info.abi)}</p>` +
    `<div class="search"><input type="search" id="q" autocomplete="off" ` +
    `placeholder="Name oder Schülernummer …" aria-label="Schüler suchen"></div>` +
    `<ul class="list" id="results" hidden></ul>` +
    `<p class="empty" id="hint">Tippe einen Namen oder eine Nummer ein.</p>`;

  const q = document.getElementById("q");
  const results = document.getElementById("results");
  const hint = document.getElementById("hint");
  if (!matchMobile()) q.focus();

  q.addEventListener("input", () => {
    const term = q.value.trim();
    if (!term) {
      results.hidden = true; results.innerHTML = "";
      hint.hidden = false; hint.textContent = "Tippe einen Namen oder eine Nummer ein.";
      return;
    }
    const hits = searchStudents(term);
    results.innerHTML = hits.map(studentRow).join("");
    results.hidden = hits.length === 0;
    hint.hidden = hits.length > 0;
    if (hits.length === 0) hint.textContent = "Keine Treffer für „" + term + "“.";
  });
  q.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const first = results.querySelector("a");
      if (first) location.hash = first.getAttribute("href");
    }
  });
}

function studentRow(s) {
  return `<li><a href="${L("s", s.nr)}">` +
    `<span class="nr">${esc(s.nr)}</span><span class="grow">${esc(s.name)}</span>` +
    `<span class="tag">${esc(s.klasse)}</span></a></li>`;
}

/* ------------------------------------------------------------- student list */
function renderStudentList() {
  const sorted = [...cur.students].sort(byName);
  view.innerHTML =
    `<h1>Schüler/innen</h1><p class="sub">${sorted.length} Personen · ${esc(cur.info.label)}</p>` +
    `<ul class="list">${sorted.map(studentRow).join("")}</ul>`;
}

/* ------------------------------------------------------------- course list */
function courseRow(c, { teacher = true } = {}) {
  const p = parseLabel(c.label, c.code);
  return `<li class="crow">` +
    `<a class="crow-main" href="${L("k", c.code)}">` +
    `<span class="badge badge-${c.kind === "LK" ? "lk" : "bk"}">${esc(c.code)}</span>` +
    `<span class="crow-title">${esc(p.desc || c.code)}</span></a>` +
    (teacher ? `<a class="crow-teacher" href="${L("l", c.teacher)}">${esc(c.teacher)}</a>` : "") +
    `<span class="tag" title="Teilnehmer/innen">${c.students.length}</span></li>`;
}

function courseGroupsHtml(term) {
  const nq = norm(term || "");
  let html = "";
  for (const [subject, arr] of cur.subjectsOrdered) {
    const matches = nq
      ? arr.filter((c) => norm(subject).includes(nq) || norm(c.code).includes(nq) ||
          norm(c.teacher).includes(nq))
      : arr;
    if (!matches.length) continue;
    html += `<h2 class="group-title">${esc(subject)}</h2>` +
      `<ul class="list">${matches.map((c) => courseRow(c)).join("")}</ul>`;
  }
  return html || `<p class="empty">Keine Kurse gefunden.</p>`;
}

function renderCourseList() {
  view.innerHTML =
    `<h1>Kurse</h1>` +
    `<p class="sub">${cur.courses.length} Kurse · ${esc(cur.info.label)} · ` +
    `<span class="badge badge-lk">ABC</span> Leistungskurs · ` +
    `<span class="badge badge-bk">abc</span> Basiskurs</p>` +
    `<div class="search"><input type="search" id="cf" autocomplete="off" ` +
    `placeholder="Nach Fach, Kürzel oder Lehrkraft filtern …" aria-label="Kurse filtern"></div>` +
    `<div id="course-groups"></div>`;
  const cf = document.getElementById("cf");
  const box = document.getElementById("course-groups");
  const paint = () => { box.innerHTML = courseGroupsHtml(cf.value.trim()); };
  cf.addEventListener("input", paint);
  paint();
}

/* --------------------------------------------------------------- teachers */
function renderTeacherList() {
  const names = [...cur.coursesByTeacher.keys()].sort((a, b) => deCmp(teacherKey(a), teacherKey(b)));
  const rows = names.map((t) => {
    const n = cur.coursesByTeacher.get(t).length;
    return `<li><a href="${L("l", t)}"><span class="grow">${esc(t)}</span>` +
      `<span class="tag">${n} Kurs${n === 1 ? "" : "e"}</span></a></li>`;
  }).join("");
  view.innerHTML =
    `<h1>Lehrkräfte</h1><p class="sub">${names.length} Lehrkräfte · ${esc(cur.info.label)}</p>` +
    `<ul class="list">${rows}</ul>`;
}

function renderTeacher(name) {
  const list = cur.coursesByTeacher.get(name);
  if (!list) return notFound("lehrer", "Lehrkräfte", "Unbekannte Lehrkraft.");
  const total = list.reduce((n, c) => n + c.students.length, 0);
  view.innerHTML =
    backlink("lehrer", "Lehrkräfte") +
    `<h1>${esc(name)}</h1>` +
    `<p class="sub">${list.length} Kurs${list.length === 1 ? "" : "e"} · ` +
    `${total} Kursbelegungen · ${esc(cur.info.label)}</p>` +
    `<ul class="list">${list.map((c) => courseRow(c, { teacher: false })).join("")}</ul>`;
}

/* --------------------------------------------------------- student profile */
function renderStudent(nr, weekParam) {
  const s = cur.byNr.get(nr);
  if (!s) return notFound("schueler", "Schüler/innen", "Unbekannte Schülernummer.");
  const maxP = lastUsedPeriod(s.timetable);
  const grp = groupLabel(s.klasse);
  const curMon = mondayOf(new Date());
  const start = weekParam && parseISO(weekParam) ? mondayOf(parseISO(weekParam)) : curMon;
  let week = clampMonday(start);

  view.innerHTML =
    backlink("schueler", "Schüler/innen") +
    `<h1>${esc(s.name)}</h1>` +
    `<p class="sub">${esc(cur.info.label)} · Nr. ${esc(s.nr)}` +
    (grp ? ` · ${esc(grp)}` : "") +
    ` · <a href="${L("gemeinsam", s.nr)}">gemeinsame Kurse suchen</a></p>` +
    `<div id="ttWeek"></div>`;

  const box = document.getElementById("ttWeek");
  const [lo, hi] = schoolBounds();

  const paint = () => {
    const isCurrent = sameISO(week, curMon);
    const dates = [0, 1, 2, 3, 4].map((i) => addDays(week, i));
    const todayIdx = isCurrent
      ? [0, 1, 2, 3, 4].find((i) => sameISO(dates[i], new Date()))
      : undefined;

    const nav =
      `<div class="week-nav">` +
      `<button type="button" class="week-btn" data-go="-1"${week <= lo ? " disabled" : ""} ` +
      `aria-label="vorige Woche">‹</button>` +
      `<span class="week-label">${esc(fmtWeekLabel(week))}</span>` +
      `<button type="button" class="week-btn" data-go="1"${week >= hi ? " disabled" : ""} ` +
      `aria-label="nächste Woche">›</button>` +
      (isCurrent ? "" : `<button type="button" class="week-btn week-today" data-go="0">Diese Woche</button>`) +
      `</div>`;

    const fullFree = weekFullyFree(week);
    let bodyHtml;
    if (fullFree) {
      bodyHtml = `<div class="ferien-banner">🌴 <b>${esc(fullFree)}</b>` +
        `<span>In dieser Woche ist unterrichtsfrei.</span></div>`;
    } else {
      const frees = dates.map(freeOn);
      const notes = dates.map((dt, i) => frees[i]
        ? `<li>${DAYS[i]} ${fmtD(dt)} — ${esc(frees[i].label)} (unterrichtsfrei)</li>` : "")
        .filter(Boolean).join("");
      bodyHtml =
        `<div class="grid-wrap">${timetableTable(s, maxP, dates, frees, todayIdx)}</div>` +
        (notes ? `<ul class="tt-footnote">${notes}</ul>` : "") +
        `<div class="tt-mobile"><div class="tt-tabs" role="tablist">` +
        DAYS.map((d, i) =>
          `<button type="button" class="tt-tab${i === todayIdx ? " today" : ""}` +
          `${frees[i] ? " free" : ""}" data-day="${i}" role="tab" aria-selected="false">` +
          `<span>${d}</span><span class="tt-tabdate">${fmtD(dates[i])}</span></button>`).join("") +
        `</div><div class="tt-day-view" id="ttDayView"></div></div>`;
    }

    box.innerHTML = nav + bodyHtml;

    box.querySelectorAll(".week-btn").forEach((b) => b.addEventListener("click", () => {
      const go = +b.dataset.go;
      week = go === 0 ? curMon : clampMonday(addDays(week, go * 7));
      history.replaceState(null, "",
        sameISO(week, curMon) ? L("s", nr) : L("s", nr, "w", isoDate(week)));
      paint();
      box.scrollIntoView({ block: "nearest" });
    }));

    if (fullFree) return;

    const tabs = [...box.querySelectorAll(".tt-tab")];
    const dv = document.getElementById("ttDayView");
    const showDay = (i) => {
      tabs.forEach((t, j) => {
        t.classList.toggle("active", j === i);
        t.setAttribute("aria-selected", j === i ? "true" : "false");
      });
      dv.innerHTML = dayViewHtml(s, i, maxP, dates, todayIdx);
    };
    tabs.forEach((t, i) => t.addEventListener("click", () => showDay(i)));
    showDay(todayIdx != null ? todayIdx : 0);
  };

  paint();
}

function dayViewHtml(s, di, maxP, dates, todayIdx) {
  const d = DAYS[di];
  const dt = dates[di];
  const head = `<h3 class="tt-dayname">${DAY_LABELS[d]}, ${dt.getDate()}. ${MONTHS_LONG[dt.getMonth()]}` +
    (di === todayIdx ? ` <span class="tt-heute">heute</span>` : "") + `</h3>`;
  const free = freeOn(dt);
  if (free) return head + `<p class="tt-none">${esc(free.label)} — unterrichtsfrei</p>`;

  const blocks = dayBlocks(s.timetable[d] || [], maxP);
  if (!blocks.length) return head + `<p class="tt-none">unterrichtsfrei</p>`;

  const items = blocks.map((b) => {
    const when = b.from === b.to ? `${b.from}.` : `${b.from}.–${b.to}.`;
    if (!b.cell) {
      return `<li class="tt-row tt-row-free"><span class="tt-when">${when}</span>` +
        `<span class="tt-what">frei</span></li>`;
    }
    const info = parseLabel(b.cell.label, b.cell.code);
    const code = cur.byCode.has(b.cell.code)
      ? `<a class="code" href="${L("k", b.cell.code)}">${esc(info.code)}</a>`
      : `<span class="code">${esc(info.code)}</span>`;
    return `<li class="tt-row"><span class="tt-when">${when}</span><span class="tt-what">` +
      `${code}${info.desc ? ` <span class="tt-desc">${esc(info.desc)}</span>` : ""}` +
      `${b.cell.teacher ? ` <span class="tt-teacher">· ${esc(b.cell.teacher)}</span>` : ""}` +
      `</span></li>`;
  }).join("");
  return head + `<ul class="tt-rows">${items}</ul>`;
}

function timetableTable(s, maxP, dates, frees, todayIdx) {
  const head = DAYS.map((d, i) =>
    `<th scope="col"${i === todayIdx ? ' class="today"' : ""}>${DAY_LABELS[d]}` +
    `<span class="th-date">${fmtD(dates[i])}</span></th>`).join("");
  let rows = "";
  for (let p = 1; p <= maxP; p++) {
    let cells = "";
    for (let i = 0; i < DAYS.length; i++) {
      cells += frees[i] ? `<td class="free"></td>` : cellHtml((s.timetable[DAYS[i]] || [])[p - 1]);
    }
    rows += `<tr><th scope="row">${p}.</th>${cells}</tr>`;
  }
  return `<table class="tt"><thead><tr><th><span class="vh">Stunde</span></th>${head}</tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

function cellHtml(c) {
  if (!c) return `<td class="free"></td>`;
  const info = parseLabel(c.label, c.code);
  const link = cur.byCode.has(c.code)
    ? `<a class="code" href="${L("k", c.code)}">${esc(info.code)}</a>`
    : `<span class="code">${esc(info.code)}</span>`;
  return `<td>${link}` +
    (c.teacher ? ` <span class="teacher">${esc(c.teacher)}</span>` : "") +
    (info.desc ? `<span class="desc">${esc(info.desc)}</span>` : "") + `</td>`;
}

function dayBlocks(arr, maxP) {
  const blocks = [];
  for (let p = 1; p <= maxP; p++) {
    const c = arr[p - 1] || null;
    const prev = blocks[blocks.length - 1];
    if (prev && prev.to === p - 1 &&
        ((prev.cell && c && prev.cell.code === c.code && prev.cell.teacher === c.teacher) ||
         (!prev.cell && !c))) {
      prev.to = p;
    } else {
      blocks.push({ from: p, to: p, cell: c });
    }
  }
  while (blocks.length && !blocks[0].cell) blocks.shift();
  while (blocks.length && !blocks[blocks.length - 1].cell) blocks.pop();
  return blocks;
}

function lastUsedPeriod(tt) {
  let max = 6;
  for (const d of DAYS) {
    const arr = tt[d] || [];
    for (let i = arr.length - 1; i >= 0; i--) if (arr[i]) { max = Math.max(max, i + 1); break; }
  }
  return max;
}

/* ---------------------------------------------------------- course profile */
function renderCourse(code) {
  const c = cur.byCode.get(code);
  if (!c) return notFound("kurse", "Kurse", "Unbekannter Kurs.");
  const p = parseLabel(c.label, c.code);
  const members = c.students.map((nr) => cur.byNr.get(nr)).filter(Boolean).sort(byName);
  view.innerHTML =
    backlink("kurse", "Kurse") +
    `<h1>${esc(p.desc || c.code)}</h1>` +
    `<p class="sub"><span class="badge badge-${c.kind === "LK" ? "lk" : "bk"}">${esc(c.code)}</span> ` +
    `${kindLabel(c.kind)} · ${esc(cur.info.label)}</p>` +
    `<dl class="factbox">` +
    (c.subject ? `<dt>Fach</dt><dd>${esc(c.subject)}</dd>` : "") +
    `<dt>Lehrkraft</dt><dd><a href="${L("l", c.teacher)}">${esc(c.teacher)}</a></dd>` +
    (c.courseNr ? `<dt>Kurs-Nr.</dt><dd>${esc(c.courseNr)}</dd>` : "") +
    `<dt>Teilnehmer/innen</dt><dd>${members.length}</dd>` +
    `</dl>` +
    `<h2 class="group-title">Teilnehmer/innen</h2>` +
    `<ul class="list">${members.map(studentRow).join("")}</ul>`;
}

/* --------------------------------------------------------- shared courses */
function renderShared(a, b) {
  const sorted = [...cur.students].sort(byName);
  const opts = (sel) => `<option value="">— Person wählen —</option>` +
    sorted.map((s) => `<option value="${esc(s.nr)}"${s.nr === sel ? " selected" : ""}>` +
      `${esc(s.name)}${s.klasse ? ` (${esc(s.klasse)})` : ""}</option>`).join("");

  view.innerHTML =
    `<h1>Gemeinsame Kurse</h1>` +
    `<p class="sub">${esc(cur.info.label)} · zwei Personen wählen – angezeigt werden die Kurse, ` +
    `die beide besuchen.</p>` +
    `<div class="pickers">` +
    `<select id="pa" aria-label="Erste Person">${opts(a)}</select>` +
    `<span class="pickers-amp">&amp;</span>` +
    `<select id="pb" aria-label="Zweite Person">${opts(b)}</select>` +
    `</div><div id="shared-out"></div>`;

  const pa = document.getElementById("pa");
  const pb = document.getElementById("pb");
  const out = document.getElementById("shared-out");
  const upd = () => {
    const na = pa.value, nb = pb.value;
    const hash = na && nb ? L("gemeinsam", na, nb) : na ? L("gemeinsam", na) : L("gemeinsam");
    history.replaceState(null, "", hash);
    out.innerHTML = sharedHtml(na, nb);
  };
  pa.addEventListener("change", upd);
  pb.addEventListener("change", upd);
  upd();
}

function sharedHtml(na, nb) {
  if (!na || !nb) return `<p class="empty">Bitte beide Personen auswählen.</p>`;
  if (na === nb) return `<p class="empty">Bitte zwei verschiedene Personen wählen.</p>`;
  const sa = cur.byNr.get(na), sb = cur.byNr.get(nb);
  if (!sa || !sb) return `<p class="empty">Unbekannte Schülernummer.</p>`;
  const ca = cur.studentCodes.get(na) || new Set();
  const cb = cur.studentCodes.get(nb) || new Set();
  const shared = [...ca].filter((code) => cb.has(code))
    .map((code) => cur.byCode.get(code)).filter(Boolean).sort(courseSort);

  const summary = `<p class="sub"><a href="${L("s", na)}">${esc(sa.name)}</a> (${ca.size} Kurse) &amp; ` +
    `<a href="${L("s", nb)}">${esc(sb.name)}</a> (${cb.size} Kurse)</p>`;
  if (!shared.length) return summary + `<p class="empty">Keine gemeinsamen Kurse.</p>`;
  return summary +
    `<h2 class="group-title">${shared.length} gemeinsame${shared.length === 1 ? "r Kurs" : " Kurse"}</h2>` +
    `<ul class="list">${shared.map((c) => courseRow(c)).join("")}</ul>`;
}

/* ------------------------------------------------------------------ shared UI */
function backlink(vseg, label) {
  return `<a class="backlink" href="${L(vseg)}"><span aria-hidden="true">←</span> ${esc(label)}</a>`;
}
function notFound(vseg, label, msg) {
  view.innerHTML = backlink(vseg, label) + `<p class="empty">${esc(msg)}</p>`;
}

init();
