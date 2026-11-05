"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
let sources = [], categories = [], history = [], busy = false;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  let data = {};
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) { const e = new Error(data.error || r.statusText); e.manual = data.manual; throw e; }
  return data;
}
const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* ---- tabs */
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "kb") loadDocs();
  if (b.dataset.tab === "log") loadLog();
}));

/* ---- settings (key kept in memory; optional sessionStorage) */
const PRESETS = {
  hkust: { model: "gpt-5.6-luna", base_url: "https://hkust.azure-api.net/hkust-genai-auth/v1" },
  openai: { model: "gpt-4o-mini", base_url: "https://api.openai.com/v1" },
  custom: {},
};
function applyPreset(name, overwrite) {
  const p = PRESETS[name] || PRESETS.custom;
  if (overwrite && p.base_url) { $("#s-model").value = p.model; $("#s-base").value = p.base_url; }
  $("#preset-note").textContent = t("set.note." + (PRESETS[name] ? name : "custom"));
}
$("#s-preset").addEventListener("change", () => { applyPreset($("#s-preset").value, true); saveCfg(); });
const cfg = () => ({ api_key: $("#s-key").value.trim(), model: $("#s-model").value.trim() || "gpt-4o-mini", base_url: $("#s-base").value.trim() });
function loadCfg() {
  const s = JSON.parse(sessionStorage.getItem("cfg") || "{}");
  $("#s-preset").value = s.preset || "hkust";
  applyPreset($("#s-preset").value, !s.model);
  if (s.model) $("#s-model").value = s.model;
  if (s.base_url) $("#s-base").value = s.base_url;
  if (s.api_key) { $("#s-key").value = s.api_key; $("#s-remember").checked = true; }
  updateStatus();
}
function saveCfg() {
  const c = cfg();
  const keep = { model: c.model, base_url: c.base_url, preset: $("#s-preset").value };
  if ($("#s-remember").checked) keep.api_key = c.api_key;
  sessionStorage.setItem("cfg", JSON.stringify(keep));
  updateStatus();
}
["#s-key", "#s-model", "#s-base", "#s-remember"].forEach((s) => $(s).addEventListener("input", saveCfg));
$("#s-clear").onclick = () => { $("#s-key").value = ""; $("#s-remember").checked = false; saveCfg(); $("#s-result").textContent = t("set.cleared"); };
$("#s-test").onclick = async () => {
  const r = $("#s-result"); r.textContent = t("set.testing");
  try { const d = await post("/api/test_connection", cfg()); r.innerHTML = `<span class="ok">${esc(t("set.ok", { reply: d.reply }))}</span>`; }
  catch (e) { r.innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
};
let lastExtra = "";
function updateStatus(extra) {
  if (extra !== undefined) lastExtra = extra;
  const c = cfg();
  const build = window._build === "OLD" ? t("status.oldbuild") : window._build ? t("status.build", { build: window._build }) : "";
  const model = document.body.classList.contains("public") ? t("status.model", { model: window._publicModel || "server" })
    : c.api_key ? t("status.model", { model: c.model }) : t("status.nokey");
  $("#status").textContent = [model, lastExtra, build].filter(Boolean).join(" · ");
}

/* ---- chat */
// Minimal markdown: input is escaped first, so nothing from the model/sources can inject HTML.
function renderMd(src) {
  const lines = esc(src).split("\n");
  const inline = (t) => t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    const lab = /^\s*\*\*(中文|English)\*\*\s*$/.exec(ln);  // bilingual answer section headers
    if (lab) { out.push(`<div class="lang-label ${lab[1] === "English" ? "en" : "zh"}">${lab[1]}</div>`); i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(ln) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
      let html = "<table class='md'><thead><tr>" + cells(ln).map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { html += "<tr>" + cells(lines[i]).map((c) => `<td>${c}</td>`).join("") + "</tr>"; i++; }
      out.push(html + "</tbody></table>");
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(ln)) {
      const ordered = /^\s*\d+[.)]/.test(ln), tag = ordered ? "ol" : "ul";
      let html = `<${tag}>`;
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) { html += "<li>" + inline(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, "")) + "</li>"; i++; }
      out.push(html + `</${tag}>`);
      continue;
    }
    out.push(ln.trim() ? `<p>${inline(ln)}</p>` : "");
    i++;
  }
  return out.join("");
}
function addMsg(role, text, extra) {
  const m = document.createElement("div");
  m.className = "msg " + role;
  if (role.startsWith("bot")) { const av = document.createElement("div"); av.className = "avatar"; av.textContent = "H"; av.setAttribute("aria-hidden", "true"); m.appendChild(av); }
  const b = document.createElement("div");
  b.className = "bubble";
  if (role.startsWith("bot") && !role.includes("err")) { b.classList.add("md"); b.innerHTML = renderMd(text); }
  else b.textContent = text;
  if (extra) b.appendChild(extra);
  m.appendChild(b);
  $("#messages").appendChild(m);
  $("#messages").scrollTop = 1e9;
  return m;
}
const catLabel = (c) => { const k = "cat." + c; const v = t(k); return v === k ? c : v; };
function renderTrace(t_) {
  if (!t_) return null;
  const d = document.createElement("div");
  d.className = "trace";
  if (t_.note) { d.textContent = t("trace.nokey"); return d; }
  const fold = document.createElement("details");  // reasoning is available but out of the way
  fold.className = "trace";
  const sum = document.createElement("summary");
  sum.textContent = t("trace.title");
  const steps = document.createElement("div");
  steps.className = "steps";
  fold.append(sum, steps);
  const intentLabel = t("intent." + t_.intent);
  const parts = [t("trace.intent", { v: intentLabel === "intent." + t_.intent ? t_.intent : intentLabel })];
  if (t_.categories && t_.categories.length) parts.push(t("trace.categories", { v: t_.categories.map(catLabel).join("/") }));
  if (t_.queries && t_.queries.length) parts.push(t("trace.queries", { v: t_.queries.join("; ") }));
  if (t_.standalone) parts.push(t("trace.standalone", { v: t_.standalone }));
  if (t_.sub_questions && t_.sub_questions.length > 1) parts.push(t("trace.split", { v: t_.sub_questions.join(" | ") }));
  if (t_.retried) parts.push(t("trace.retried"));
  if (t_.retry_queries && t_.retry_queries.length) parts.push(t("trace.retryQueries", { v: t_.retry_queries.join("; ") }));
  if (t_.retry_reason) parts.push(t("trace.retryReason", { v: t_.retry_reason }));
  if (typeof t_.hits === "number") parts.push(t("trace.hits", { n: t_.hits }));
  if (t_.retrieval_quality && t_.retrieval_quality !== "good") parts.push(t("trace.quality." + t_.retrieval_quality));
  if (t_.missing_aspects && t_.missing_aspects.length) parts.push(t("trace.missing", { v: t_.missing_aspects.join("; ") }));
  if (t_.assumption) parts.push(t("trace.assumption", { v: t_.assumption }));
  if (t_.plan_error) parts.push(t("trace.planError", { v: t_.plan_error }));
  steps.textContent = parts.join(" · ");
  return fold;
}
function renderSources(res) {
  const wrap = document.createElement("div");
  wrap.className = "sources";
  const tr = renderTrace(res.trace);
  if (tr) wrap.appendChild(tr);
  if (res.flags && res.flags.length) {
    const f = document.createElement("div");
    f.innerHTML = res.flags.map((x) => `<span class="badge flag">${esc(t("flag." + x) === "flag." + x ? x : t("flag." + x))}</span>`).join("");
    wrap.appendChild(f);
  }
  if (res.invalid_citations && res.invalid_citations.length) {
    const w = document.createElement("div");
    w.innerHTML = `<span class="badge flag">${esc(t("src.badInvalid", { v: res.invalid_citations.join(",") }))}</span>`;
    wrap.appendChild(w);
  }
  (res.sources || []).forEach((s) => {
    const d = document.createElement("div");
    const url = safeUrl(s.url);
    const link = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>` : esc(s.title);
    d.innerHTML = `[${s.n}] ${link}<span class="badge ${s.source_type === "student" ? "student" : ""}">${esc(t(s.source_type === "student" ? "src.student" : "src.official"))}</span>` +
      (s.date ? `<span class="badge">${esc(t("src.effective", { d: s.date }))}</span>` : "") +
      (s.fetched ? `<span class="badge">${esc(t("src.fetched", { d: s.fetched }))}</span>` : "") +
      (res.mode === "retrieval_only" ? `<div class="snip">${esc(s.snippet)}…</div>` : "");
    wrap.appendChild(d);
  });
  return wrap.children.length ? wrap : null;
}
async function ask(q) {
  if (busy || !q.trim()) return;
  busy = true; $("#send").disabled = true;
  $("#welcome").classList.add("hidden");
  addMsg("user", q);
  const pending = addMsg("bot", t("chat.loading"));
  pending.querySelector(".bubble").classList.add("loading");
  try {
    const res = await post("/api/chat", { question: q, category: $("#cat-filter").value, history, agent: $("#s-agent").checked, ui_lang: LANG, ...cfg() });
    pending.remove();
    addMsg("bot", res.answer, renderSources(res));
    history.push({ role: "user", content: q }, { role: "assistant", content: res.answer });
    history = history.slice(-8);
    updateStatus(`${res.ms} ms`);
  } catch (e) {
    pending.remove();
    addMsg("bot err", t("chat.error", { msg: e.message }));
  }
  busy = false; $("#send").disabled = false;
}
$("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#question").value; $("#question").value = ""; ask(q); });
function renderExamples() {
  $("#examples").innerHTML = t("examples").map((e) => `<button type="button">${esc(e)}</button>`).join("");
}
$("#examples").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") ask(e.target.textContent); });

/* ---- knowledge base */
async function loadDocs() {
  const d = await api("/api/docs");
  $("#kb-stats").textContent = t("kb.stats", { d: d.stats.documents, c: d.stats.chunks, n: d.stats.chars.toLocaleString() });
  $("#empty-warn").classList.toggle("hidden", d.stats.documents > 0);
  const tb = $("#doc-table tbody");
  tb.innerHTML = "";
  d.docs.forEach((x) => {
    const tr = document.createElement("tr");
    const url = safeUrl(x.source_url);
    tr.innerHTML = `<td>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a>` : esc(x.title)}</td><td>${esc(catLabel(x.category))}</td><td>${esc(t(x.source_type === "student" ? "src.student" : "src.official"))}</td><td>${x.n_chunks}</td><td>${esc(x.effective_date || x.retrieved_at)}</td><td><button class="ghost" data-id="${x.id}">${esc(t("kb.delete"))}</button></td>`;
    tb.appendChild(tr);
  });
}
$("#doc-table").addEventListener("click", async (e) => {
  const id = e.target.dataset && e.target.dataset.id;
  if (id && confirm(t("kb.confirmDelete"))) { await api("/api/docs/" + id, { method: "DELETE" }); loadDocs(); }
});
function metaFromForm() {
  return { category: $("#up-cat").value, source_type: $("#up-type").value, source_url: $("#up-url").value.trim(), publisher: $("#up-pub").value.trim(), effective_date: $("#up-date").value.trim() };
}
$("#up-file").addEventListener("change", async (e) => {
  const out = $("#up-result"); out.textContent = "";
  const m = metaFromForm();
  for (const f of e.target.files) {
    try {
      const q = new URLSearchParams(Object.fromEntries(Object.entries(m).filter(([, v]) => v)));
      const d = await api("/api/upload?" + q, { method: "POST", headers: { "X-Filename": encodeURIComponent(f.name) }, body: f });
      out.innerHTML += `<div class="${d.duplicate ? "" : "ok"}">${esc(f.name)}: ${esc(d.duplicate ? t("kb.dup") : t("kb.chunksAdded", { n: d.chunks }))}</div>`;
    } catch (err) { out.innerHTML += `<div class="bad">${esc(f.name)}: ${esc(err.message)}</div>`; }
  }
  e.target.value = ""; loadDocs();
});
async function importUrl(url, meta, out) {
  out.textContent = t("kb.fetching");
  try {
    const d = await post("/api/url", { url, ...meta });
    out.innerHTML = `<span class="${d.duplicate ? "" : "ok"}">${esc(d.duplicate ? t("kb.dup") : t("kb.fetchOk", { chars: d.chars, n: d.chunks }))}</span>`;
    return true;
  } catch (e) { out.innerHTML = `<span class="bad">${e.manual ? esc(t("kb.manual")) : ""}${esc(e.message)}</span>`; return false; }
}
$("#url-btn").onclick = async () => { await importUrl($("#url-in").value.trim(), metaFromForm(), $("#url-result")); loadDocs(); };
$("#tx-btn").onclick = async () => {
  const out = $("#tx-result");
  try {
    const d = await post("/api/text", { title: $("#tx-title").value.trim(), text: $("#tx-body").value, ...metaFromForm() });
    out.innerHTML = `<span class="ok">${esc(d.duplicate ? t("kb.dup") : t("kb.chunksAdded", { n: d.chunks }))}</span>`;
    $("#tx-body").value = ""; loadDocs();
  } catch (e) { out.innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
};

/* ---- source list */
const fetchState = {}; // index -> { ok, text } so the status survives re-render / language switch
function renderSources_() {
  const tb = $("#src-table tbody"); tb.innerHTML = "";
  sources.forEach((s, i) => {
    const tr = document.createElement("tr");
    const st = fetchState[i];
    tr.innerHTML = `<td>${esc(catLabel(s.category))}</td><td><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.label || s.url)}</a></td><td id="st-${i}" class="${st ? (st.ok ? "ok" : "bad") : ""}">${esc(st ? st.text : t("kb.pending"))}</td><td><button class="ghost" data-i="${i}">${esc(t("kb.fetchBtn"))}</button></td>`;
    tb.appendChild(tr);
  });
}
async function fetchSource(i) {
  const s = sources[i], cell = $("#st-" + i);
  cell.className = ""; cell.textContent = t("kb.fetching");
  const tmp = document.createElement("div");
  const ok = await importUrl(s.url, { title: s.label, category: s.category, publisher: s.publisher, source_type: s.source_type }, tmp);
  fetchState[i] = { ok, text: tmp.textContent };
  cell.className = ok ? "ok" : "bad"; cell.textContent = tmp.textContent;
}
$("#src-table").addEventListener("click", (e) => { if (e.target.dataset && e.target.dataset.i) fetchSource(+e.target.dataset.i).then(loadDocs); });
$("#fetch-all").onclick = async () => { for (let i = 0; i < sources.length; i++) await fetchSource(i); loadDocs(); };
$("#links-parse").onclick = async () => {
  const d = await post("/api/links", { text: $("#links-text").value });
  d.urls.forEach((u) => { if (!sources.some((s) => s.url === u)) sources.push({ category: $("#up-cat").value, label: u, url: u, publisher: "", source_type: "official" }); });
  renderSources_();
};

/* ---- log */
async function loadLog() {
  const d = await api("/api/log");
  const tb = $("#log-table tbody"); tb.innerHTML = "";
  window._log = d.log;
  d.log.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(new Date(r.ts * 1000).toLocaleString())}</td><td>${esc(r.question)}</td><td>${esc(r.mode)}</td><td>${esc(r.flags)}</td><td>${r.ms} ms</td><td>${esc((JSON.parse(r.sources || "[]")).join(" , "))}</td>`;
    tb.appendChild(tr);
  });
}
$("#log-export").onclick = () => {
  const q = (v) => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const rows = [["time", "question", "mode", "flags", "answer", "sources", "model", "ms"]].concat((window._log || []).map((r) => [new Date(r.ts * 1000).toISOString(), r.question, r.mode, r.flags, r.answer, r.sources, r.model, r.ms]));
  const blob = new Blob(["\ufeff" + rows.map((r) => r.map(q).join(",")).join("\n")], { type: "text/csv" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "qa_log.csv"; a.click();
};

/* ---- init + language */
function fillCategorySelects() {
  const keep = { up: $("#up-cat").value, f: $("#cat-filter").value };
  $("#up-cat").innerHTML = categories.map((c) => `<option value="${esc(c)}">${esc(catLabel(c))}</option>`).join("");
  $("#cat-filter").innerHTML = `<option value="">${esc(t("chat.catAll"))}</option>` + categories.map((c) => `<option value="${esc(c)}">${esc(catLabel(c))}</option>`).join("");
  if (keep.up) $("#up-cat").value = keep.up;
  if (keep.f) $("#cat-filter").value = keep.f;
}
function refreshLanguage() {
  applyStaticI18n();
  $("#lang-btn").textContent = t("lang.switch");
  $("#opt-official").textContent = t("src.official");
  $("#opt-student").textContent = t("src.student");
  fillCategorySelects();
  renderExamples();
  renderSources_();
  applyPreset($("#s-preset").value, false);
  updateStatus();
  loadDocs().catch(() => {});
  if ($("#tab-log").classList.contains("active")) loadLog();
}
$("#lang-btn").onclick = () => { LANG = LANG === "zh" ? "en" : "zh"; localStorage.setItem("lang", LANG); refreshLanguage(); };

(async function init() {
  const s = await api("/api/sources");
  sources = s.sources; categories = s.categories;
  // public demo: the server holds the key/model; hide everything that writes or configures
  try {
    const c = await api("/api/config");
    if (c.public) {
      document.body.classList.add("public");
      window._publicModel = c.model;
      $("#s-agent").checked = true;
    }
  } catch (_) {}
  loadCfg();
  refreshLanguage();
  api("/api/version").then((v) => { window._build = v.build; updateStatus(); }).catch(() => { window._build = "OLD"; updateStatus(); });
})();
