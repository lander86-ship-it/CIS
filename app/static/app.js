"use strict";

const $ = (sel) => document.querySelector(sel);
const consoleEl = $("#console");

let CATALOG = [];        // all benchmarks
let selectedId = null;   // currently marked benchmark id

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

// tolerant field getters (cis-bench JSON schema may vary)
const pick = (o, keys) => { for (const k of keys) { if (o[k] != null && o[k] !== "") return o[k]; } return ""; };
const benchId = (b) => String(pick(b, ["id", "benchmark_id", "workbench_id", "number", "ID"]));
const benchTitle = (b) => String(pick(b, ["title", "name", "benchmark", "Title"]));
const benchPlatform = (b) => String(pick(b, ["platform", "platform_type", "os", "technology"]));
const benchVersion = (b) => String(pick(b, ["version", "ver", "Version"]));

// --- session / auth --------------------------------------------------------

async function refreshSession() {
  try {
    const s = await api("/api/session");
    if (s.user) { $("#userBadge").textContent = s.user; }
  } catch { /* redirected */ }
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
  if (wb) {
    wb.textContent = active ? "session active" : "no session — upload cookies";
    wb.className = "badge " + (active ? "badge--ok" : "badge--err");
  }
  const card = $("#wbCard");
  if (card) card.classList.toggle("card--attention", !active);
}

async function refreshAuth() {
  try {
    const res = await api("/api/auth/status");
    setAuthUI(!!res.ok);
    return res;
  } catch { setAuthUI(false); }
  return { ok: false };
}

// --- catalog ---------------------------------------------------------------

let pollTimer = null, pollCount = 0;

async function loadCatalog() {
  // The catalog needs an active WorkBench session; prompt if missing.
  const a = await refreshAuth();
  if (!a.ok) {
    clearTimeout(pollTimer);
    $("#catalogStatus").textContent = "no session";
    $("#catalog").innerHTML = `<p class="hint">Upload your <code>cookies.txt</code> in the <strong>CIS WorkBench session</strong> panel above to load the catalog.</p>`;
    return;
  }
  $("#catalogStatus").textContent = "loading…";
  try {
    const res = await api("/api/catalog");
    if (res.status === "ready") {
      clearTimeout(pollTimer); pollCount = 0;
      CATALOG = res.benchmarks || [];
      $("#catalogStatus").textContent = `${CATALOG.length} benchmarks`;
      renderCatalog();
      if (!CATALOG.length) $("#catalogHint").textContent = "Catalog is empty. Check authentication, then Reload.";
    } else if (res.status === "error") {
      clearTimeout(pollTimer);
      $("#catalogStatus").textContent = "error";
      $("#catalog").innerHTML = `<p class="hint">Could not load the catalog: ${escapeHtml(res.error || "unknown error")}. Verify CIS WorkBench authentication (Session panel) and press Reload.</p>`;
    } else {
      // refreshing — poll
      $("#catalogStatus").textContent = "building catalog… (first load can take a few minutes)";
      $("#catalogHint").textContent = "Loading the benchmark catalog from CIS WorkBench…";
      if (pollCount++ < 90) pollTimer = setTimeout(loadCatalog, 5000);
      else $("#catalogStatus").textContent = "still building… press Reload";
    }
  } catch { /* redirected */ }
}

function renderCatalog() {
  const q = $("#catalogFilter").value.trim().toLowerCase();
  const rows = CATALOG.filter((b) => {
    if (!q) return true;
    return (benchTitle(b) + " " + benchPlatform(b) + " " + benchId(b)).toLowerCase().includes(q);
  });
  const box = $("#catalog");
  if (!CATALOG.length) { box.innerHTML = `<p class="hint" id="catalogHint">Loading catalog…</p>`; return; }
  if (!rows.length) { box.innerHTML = `<p class="hint">No benchmarks match "${escapeHtml(q)}".</p>`; return; }
  const body = rows.slice(0, 500).map((b) => {
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
    </tr></thead><tbody>${body}</tbody></table></div>
    ${rows.length > 500 ? `<p class="subtle">Showing first 500 of ${rows.length}. Refine the filter.</p>` : ""}`;

  box.querySelectorAll("tr.brow").forEach((tr) => {
    const id = tr.getAttribute("data-id");
    const title = tr.getAttribute("data-title");
    tr.addEventListener("click", (e) => {
      if (e.target.classList.contains("genbtn")) return; // button handles itself
      selectRow(id);
    });
    tr.querySelector(".genbtn").addEventListener("click", () => {
      selectRow(id);
      generatePolicy(id || title, title);
    });
  });
}

function selectRow(id) {
  selectedId = id;
  document.querySelectorAll("tr.brow").forEach((tr) =>
    tr.classList.toggle("row--selected", tr.getAttribute("data-id") === id));
}

$("#catalogFilter").addEventListener("input", renderCatalog);
$("#reloadBtn").addEventListener("click", () => { pollCount = 0; loadCatalog(); });

// --- generate policy -------------------------------------------------------

async function generatePolicy(identifier, label) {
  const fd = new FormData();
  fd.append("identifier", identifier);
  if ($("#polTitle").value.trim()) fd.append("title", $("#polTitle").value.trim());
  if ($("#polAuthor").value.trim()) fd.append("author", $("#polAuthor").value.trim());
  if ($("#polVersion").value.trim()) fd.append("version", $("#polVersion").value.trim());
  fd.append("src_format", $("#polFormat").value);
  log(`Generating Word policy for "${label || identifier}" (SABIC template)… this can take a while.`);
  const btns = document.querySelectorAll(".genbtn");
  btns.forEach((b) => (b.disabled = true));
  try {
    const res = await api("/api/policy", { method: "POST", body: fd });
    if (res.ok) {
      const b = res.benchmark || {};
      log(`Policy generated: ${res.file} — ${b.controls} controls in ${b.sections} sections.`, "ok");
      await loadFiles();
      const a = document.querySelector(`#fileList a[href$="${encodeURIComponent(res.file)}"]`);
      if (a) a.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      log(res.stderr || res.detail || "Could not generate the policy.", "err");
    }
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

// --- session cookies (re-auth on expiry) -----------------------------------

$("#cookiesForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const file = $("#cookiesFile").files[0];
  if (!file) { log("Choose a cookies.txt file first.", "err"); return; }
  const fd = new FormData();
  fd.append("cookies", file);
  busy(btn, true);
  log("Updating CIS WorkBench cookies…");
  try {
    const res = await api("/api/auth/login", { method: "POST", body: fd });
    showResult(res);
    await refreshAuth();
    if (res.ok) { pollCount = 0; loadCatalog(); }
  } finally { busy(btn, false); }
});
$("#authStatusBtn").addEventListener("click", async (e) => {
  busy(e.target, true);
  const res = await refreshAuth();
  if (res) showResult(res);
  busy(e.target, false);
});

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

refreshSession();
loadCatalog();   // refreshes auth first and gates on it
loadFiles();
