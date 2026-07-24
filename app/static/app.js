"use strict";

const $ = (sel) => document.querySelector(sel);
const consoleEl = $("#console");

let RESULTS = [];        // current search results
let selectedId = null;   // marked benchmark id

// --- utilities -------------------------------------------------------------

function log(text, kind = "") {
  const stamp = new Date().toLocaleTimeString();
  const cls = kind ? ` class="out-${kind}"` : "";
  consoleEl.innerHTML += `\n<span${cls}>[${stamp}] ${escapeHtml(text)}</span>`;
  consoleEl.scrollTop = consoleEl.scrollHeight;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function showResult(res) {
  if (res.command) log(`$ cis-bench ${String(res.command).replace(/^cis-bench\s*/, "")}`);
  if (res.stdout && res.stdout.trim()) log(res.stdout.trim(), res.ok ? "ok" : "");
  if (res.stderr && res.stderr.trim()) log(res.stderr.trim(), res.ok ? "" : "err");
  if (!res.stdout && !res.stderr) log(res.ok ? "OK" : `Failed (code ${res.returncode})`, res.ok ? "ok" : "err");
}
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (r.status === 401) { window.location.href = "/login"; throw new Error("unauthenticated"); }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return { ok: r.ok, stdout: await r.text(), stderr: "", returncode: r.ok ? 0 : 1 };
}
function busy(btn, on) { if (btn) btn.disabled = on; }

const pick = (o, keys) => { for (const k of keys) { if (o[k] != null && o[k] !== "") return o[k]; } return ""; };
const benchId = (b) => String(pick(b, ["id", "benchmark_id", "workbench_id", "number", "ID"]));
const benchTitle = (b) => String(pick(b, ["title", "name", "benchmark", "Title"]));
const benchPlatform = (b) => String(pick(b, ["platform", "platform_type", "os", "technology"]));
const benchVersion = (b) => String(pick(b, ["version", "ver", "Version"]));

// --- session / auth --------------------------------------------------------

async function refreshSession() {
  try { const s = await api("/api/session"); if (s.user) $("#userBadge").textContent = s.user; }
  catch { /* redirected */ }
}
$("#logoutBtn").addEventListener("click", async () => {
  await fetch("/api/session/logout", { method: "POST" });
  window.location.href = "/login";
});

function setAuthUI(active) {
  const badge = $("#authBadge");
  badge.textContent = active ? "auth: active" : "auth: no session";
  badge.className = "badge " + (active ? "badge--ok" : "badge--err");
  const wb = $("#wbStatus");
  wb.textContent = active ? "session active" : "no session";
  wb.className = "badge " + (active ? "badge--ok" : "badge--err");
  $("#wbCard").classList.toggle("card--attention", !active);
}
async function refreshAuth() {
  try { const res = await api("/api/auth/status"); setAuthUI(!!res.ok); return res; }
  catch { setAuthUI(false); }
  return { ok: false };
}

// Option A — username/password
$("#credForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const fd = new FormData();
  fd.append("username", $("#wbUser").value.trim());
  fd.append("password", $("#wbPass").value);
  if (!$("#wbUser").value.trim() || !$("#wbPass").value) { log("Enter username and password.", "err"); return; }
  busy(btn, true);
  log(`Signing in to CIS WorkBench as ${$("#wbUser").value.trim()}…`);
  try {
    const res = await api("/api/auth/login-credentials", { method: "POST", body: fd });
    showResult(res);
    const a = await refreshAuth();
    if (a.ok) { $("#wbPass").value = ""; catalogStatus(); }
  } finally { busy(btn, false); }
});

// Option B — cookies upload
$("#cookiesForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const file = $("#cookiesFile").files[0];
  if (!file) { log("Choose a cookies.txt file first.", "err"); return; }
  const fd = new FormData();
  fd.append("cookies", file);
  busy(btn, true);
  log("Uploading cookies and signing in…");
  try {
    const res = await api("/api/auth/login", { method: "POST", body: fd });
    showResult(res);
    const a = await refreshAuth();
    if (a.ok) catalogStatus();
  } finally { busy(btn, false); }
});
$("#authStatusBtn").addEventListener("click", async (e) => {
  busy(e.target, true);
  const res = await refreshAuth();
  if (res) showResult(res);
  busy(e.target, false);
});

// --- catalog status (needed for search to return results) ------------------

let statusTimer = null;
async function catalogStatus() {
  try {
    const s = await api("/api/catalog/status");
    const el = $("#catalogStatus");
    if (s.status === "ready") {
      el.textContent = s.count ? `catalog ready (${s.count})` : "catalog ready";
      clearTimeout(statusTimer);
    } else if (s.status === "refreshing") {
      el.textContent = "preparing catalog… (first time only)";
      statusTimer = setTimeout(catalogStatus, 5000);
    } else if (s.status === "error") {
      el.textContent = "catalog needs a session";
    } else {
      el.textContent = "";
    }
  } catch { /* redirected */ }
}

// --- prepare catalog / diagnostics -----------------------------------------

$("#prepBtn").addEventListener("click", async (e) => {
  busy(e.target, true);
  log("Preparing the local catalog (cis-bench catalog refresh)… first time can take minutes.");
  try {
    const s = await api("/api/catalog/status");
    log(`Catalog status: ${s.status}${s.count ? ` (${s.count})` : ""}${s.error ? " — " + s.error : ""}`, s.status === "ready" ? "ok" : (s.status === "error" ? "err" : ""));
    catalogStatus();
  } finally { busy(e.target, false); }
});

$("#diagBtn").addEventListener("click", async (e) => {
  busy(e.target, true);
  const q = $("#query").value.trim() || "ubuntu";
  log(`Running diagnostics (query "${q}")…`);
  try {
    const d = await api(`/api/diagnostics?q=${encodeURIComponent(q)}`);
    log("— cli_available: " + d.cli_available);
    log("— catalog_state: " + JSON.stringify(d.catalog_state));
    const dump = (name, r) => { if (!r) return; log(`— ${name}: rc=${r.returncode}`); if (r.stdout && r.stdout.trim()) log(r.stdout.trim().slice(0, 1200)); if (r.stderr && r.stderr.trim()) log(r.stderr.trim().slice(0, 800), "err"); };
    dump("auth status", d.auth_status);
    dump("list --output-format json", d.list_json);
    dump("search json", d.search_json);
    dump("search plain", d.search_plain);
    log("Diagnostics done. If this looks off, copy the Output and send it over.", "ok");
  } finally { busy(e.target, false); }
});

// --- search ----------------------------------------------------------------

$("#searchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const q = $("#query").value.trim();
  if (!q) { log("Type a keyword to search.", "err"); return; }
  busy(btn, true);
  $("#results").innerHTML = `<p class="hint">Searching…</p>`;
  log(`Searching benchmarks for "${q}"…`);
  try {
    const res = await api(`/api/search?q=${encodeURIComponent(q)}`);
    showResult(res); // always surface the raw cis-bench output
    RESULTS = Array.isArray(res.json) ? res.json : (res.json && Array.isArray(res.json.results) ? res.json.results : []);
    if (RESULTS.length) {
      renderRows(RESULTS);
      log(`${RESULTS.length} result(s).`, "ok");
    } else if (res.stdout && res.stdout.trim()) {
      // Non-JSON (plain text) results — show them raw so nothing is hidden.
      $("#results").innerHTML = `<pre class="console">${escapeHtml(res.stdout.trim())}</pre>`;
    } else {
      $("#results").innerHTML = `<p class="hint">No benchmarks matched "${escapeHtml(q)}". If you just signed in, the catalog may still be preparing — press <strong>Prepare catalog</strong> and retry. Use <strong>Diagnose</strong> to see what cis-bench reports.</p>`;
      catalogStatus();
    }
  } finally { busy(btn, false); }
});

function renderRows(list) {
  const box = $("#results");
  const body = list.slice(0, 300).map((b) => {
    const id = benchId(b), title = benchTitle(b) || id, plat = benchPlatform(b), ver = benchVersion(b);
    const marked = (id && id === selectedId) ? " row--selected" : "";
    return `<tr class="brow${marked}" data-id="${escapeHtml(id)}" data-title="${escapeHtml(title)}">
      <td class="sel"><span class="dotmark"></span></td>
      <td><span class="id">${escapeHtml(id || "—")}</span></td>
      <td>${escapeHtml(title)}</td>
      <td>${plat ? `<span class="chip">${escapeHtml(plat)}</span>` : ""}</td>
      <td class="ver">${escapeHtml(ver)}</td>
      <td class="rowbtn"><button class="btn sm genbtn">Generate policy</button></td>
    </tr>`;
  }).join("");
  box.innerHTML = `<div class="scroll"><table class="catalog"><thead><tr>
      <th></th><th>ID</th><th>Benchmark</th><th>Platform</th><th>Version</th><th></th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
  box.querySelectorAll("tr.brow").forEach((tr) => {
    const id = tr.getAttribute("data-id"), title = tr.getAttribute("data-title");
    tr.addEventListener("click", (e) => { if (!e.target.classList.contains("genbtn")) selectRow(id); });
    tr.querySelector(".genbtn").addEventListener("click", () => { selectRow(id); generatePolicy(id || title, title); });
  });
}
function selectRow(id) {
  selectedId = id;
  document.querySelectorAll("tr.brow").forEach((tr) =>
    tr.classList.toggle("row--selected", tr.getAttribute("data-id") === id));
}

// --- generate policy -------------------------------------------------------

async function generatePolicy(identifier, label) {
  const fd = new FormData();
  fd.append("identifier", identifier);
  fd.append("src_format", "xccdf");
  log(`Generating Word policy for "${label || identifier}" (SABIC template)… this can take a while.`);
  const btns = document.querySelectorAll(".genbtn");
  btns.forEach((b) => (b.disabled = true));
  try {
    const res = await api("/api/policy", { method: "POST", body: fd });
    if (res.ok) {
      const b = res.benchmark || {};
      log(`Policy generated: ${res.file} — ${b.controls} controls in ${b.sections} sections.`, "ok");
      await loadFiles();
    } else {
      log(res.stderr || res.detail || "Could not generate the policy.", "err");
    }
  } finally { btns.forEach((b) => (b.disabled = false)); }
}

// --- files -----------------------------------------------------------------

async function loadFiles() {
  const { files } = await api("/api/files");
  const list = $("#fileList");
  if (!files || !files.length) { list.innerHTML = `<li class="empty">No files yet.</li>`; return; }
  list.innerHTML = files.map((f) =>
    `<li><a href="/api/files/${encodeURIComponent(f.name)}" download>${escapeHtml(f.name)}</a>` +
    `<span class="size">${fmtSize(f.size)}</span></li>`).join("");
}
function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}
$("#filesBtn").addEventListener("click", loadFiles);
$("#clearBtn").addEventListener("click", () => { consoleEl.textContent = "Ready."; });

// --- init ------------------------------------------------------------------

(async function init() {
  refreshSession();
  const a = await refreshAuth();
  if (a.ok) catalogStatus();
  loadFiles();
})();
