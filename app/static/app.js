"use strict";

const $ = (sel) => document.querySelector(sel);
const consoleEl = $("#console");

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

// Render a cis-bench command Result into the console.
function showResult(res) {
  if (res.command) log(`$ cis-bench ${res.command.replace(/^cis-bench\s*/, "")}`);
  if (res.stdout && res.stdout.trim()) log(res.stdout.trim(), res.ok ? "ok" : "");
  if (res.stderr && res.stderr.trim()) log(res.stderr.trim(), res.ok ? "" : "err");
  if (!res.stdout && !res.stderr) log(res.ok ? "OK" : `Fallo (código ${res.returncode})`, res.ok ? "ok" : "err");
}

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return { ok: r.ok, stdout: await r.text(), stderr: "", returncode: r.ok ? 0 : 1 };
}

function busy(btn, on) {
  if (!btn) return;
  btn.disabled = on;
}

// --- Health + auth badges --------------------------------------------------

async function refreshHealth() {
  try {
    const h = await api("/api/health");
    const badge = $("#cliBadge");
    if (h.cli_available) {
      badge.textContent = `CLI ${h.cli_version || "ok"}`;
      badge.className = "badge badge--ok";
    } else {
      badge.textContent = "CLI no encontrada";
      badge.className = "badge badge--err";
    }
  } catch {
    $("#cliBadge").textContent = "servidor sin respuesta";
    $("#cliBadge").className = "badge badge--err";
  }
}

async function refreshAuth() {
  const badge = $("#authBadge");
  try {
    const res = await api("/api/auth/status");
    badge.textContent = res.ok ? "auth: activa" : "auth: no";
    badge.className = "badge " + (res.ok ? "badge--ok" : "badge--err");
    return res;
  } catch {
    badge.textContent = "auth: ?";
    badge.className = "badge badge--muted";
  }
}

// --- Handlers --------------------------------------------------------------

$("#browserForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const browser = $("#browser").value;
  const fd = new FormData();
  fd.append("browser", browser);
  busy(btn, true);
  log(`Extrayendo cookies de ${browser}…`);
  try {
    const res = await api("/api/auth/login-browser", { method: "POST", body: fd });
    showResult(res);
    if (!res.ok) {
      log("Si falla: asegúrate de estar en modo nativo (./run-local.sh), " +
          "de haber iniciado sesión en WorkBench en ese navegador, y prueba a " +
          "cerrarlo. Si sigue fallando, usa la Opción B (cookies.txt).", "err");
    }
    await refreshAuth();
  } finally {
    busy(btn, false);
  }
});

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const file = $("#cookiesFile").files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("cookies", file);
  busy(btn, true);
  log("Subiendo cookies e iniciando sesión…");
  try {
    const res = await api("/api/auth/login", { method: "POST", body: fd });
    showResult(res);
    await refreshAuth();
  } finally {
    busy(btn, false);
  }
});

$("#authStatusBtn").addEventListener("click", async (e) => {
  busy(e.target, true);
  const res = await refreshAuth();
  if (res) showResult(res);
  busy(e.target, false);
});

$("#refreshBtn").addEventListener("click", async (e) => {
  busy(e.target, true);
  log("Refrescando catálogo (puede tardar)…");
  try {
    showResult(await api("/api/catalog/refresh", { method: "POST" }));
  } finally {
    busy(e.target, false);
  }
});

$("#searchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const q = encodeURIComponent($("#query").value.trim());
  const pt = $("#platformType").value.trim();
  let url = `/api/search?q=${q}`;
  if (pt) url += `&platform_type=${encodeURIComponent(pt)}`;
  busy(btn, true);
  log(`Buscando "${$("#query").value.trim()}"…`);
  try {
    const res = await api(url);
    renderSearch(res);
    showResult(res);
  } finally {
    busy(btn, false);
  }
});

function renderSearch(res) {
  const box = $("#searchResults");
  const data = res.json;
  if (Array.isArray(data) && data.length) {
    const cols = [...new Set(data.flatMap((r) => Object.keys(r)))].slice(0, 6);
    const head = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
    const rows = data.slice(0, 100).map((r) =>
      `<tr>${cols.map((c) => `<td>${escapeHtml(r[c] ?? "")}</td>`).join("")}</tr>`).join("");
    box.innerHTML = `<div class="scroll"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  } else if (res.stdout && res.stdout.trim()) {
    box.innerHTML = "";
  } else {
    box.innerHTML = `<p class="hint">Sin resultados.</p>`;
  }
}

// Show/hide the XCCDF style selector based on the chosen format.
$("#fmt").addEventListener("change", () => {
  $("#styleWrap").style.display = $("#fmt").value === "xccdf" ? "" : "none";
});

$("#exportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  const fd = new FormData();
  fd.append("identifier", $("#identifier").value.trim());
  fd.append("fmt", $("#fmt").value);
  if ($("#fmt").value === "xccdf") fd.append("style", $("#style").value);
  if ($("#filename").value.trim()) fd.append("filename", $("#filename").value.trim());
  busy(btn, true);
  log(`Exportando "${$("#identifier").value.trim()}" a ${$("#fmt").value}…`);
  try {
    const res = await api("/api/export", { method: "POST", body: fd });
    showResult(res);
    if (res.download_url) {
      log(`Archivo generado: ${res.file}`, "ok");
      await loadFiles();
    }
  } finally {
    busy(btn, false);
  }
});

$("#filesBtn").addEventListener("click", loadFiles);
$("#clearBtn").addEventListener("click", () => { consoleEl.textContent = "Listo."; });

async function loadFiles() {
  const { files } = await api("/api/files");
  const list = $("#fileList");
  if (!files || !files.length) {
    list.innerHTML = `<li class="empty">Sin archivos todavía.</li>`;
    return;
  }
  list.innerHTML = files.map((f) =>
    `<li><a href="/api/files/${encodeURIComponent(f.name)}" download>${escapeHtml(f.name)}</a>` +
    `<span class="size">${fmtSize(f.size)}</span></li>`).join("");
}

function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

// --- Init ------------------------------------------------------------------

refreshHealth();
refreshAuth();
loadFiles();
