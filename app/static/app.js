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
  if (!res.stdout && !res.stderr) log(res.ok ? "OK" : `Failed (code ${res.returncode})`, res.ok ? "ok" : "err");
}

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (r.status === 401) { window.location.href = "/login"; throw new Error("unauthenticated"); }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return { ok: r.ok, stdout: await r.text(), stderr: "", returncode: r.ok ? 0 : 1 };
}

function busy(btn, on) {
  if (!btn) return;
  btn.disabled = on;
}

// --- Session / health / auth badges ---------------------------------------

async function refreshSession() {
  try {
    const s = await api("/api/session");
    if (s.user) {
      $("#userBadge").textContent = s.user;
      $("#userBadge").className = "badge badge--muted";
    }
  } catch { /* redirected to /login */ }
}

$("#logoutBtn").addEventListener("click", async () => {
  await fetch("/api/session/logout", { method: "POST" });
  window.location.href = "/login";
});

async function refreshHealth() {
  try {
    const h = await api("/api/health");
    const badge = $("#cliBadge");
    if (h.cli_available) {
      badge.textContent = `CLI ${h.cli_version || "ok"}`;
      badge.className = "badge badge--ok";
    } else {
      badge.textContent = "CLI not found";
      badge.className = "badge badge--err";
    }
  } catch {
    $("#cliBadge").textContent = "server unreachable";
    $("#cliBadge").className = "badge badge--err";
  }
}

async function refreshAuth() {
  const badge = $("#authBadge");
  try {
    const res = await api("/api/auth/status");
    badge.textContent = res.ok ? "auth: active" : "auth: no";
    badge.className = "badge " + (res.ok ? "badge--ok" : "badge--err");
    return res;
  } catch {
    badge.textContent = "auth: ?";
    badge.className = "badge badge--muted";
  }
}

// --- Handlers --------------------------------------------------------------

$("#btnBrowser").addEventListener("click", async (e) => {
  const btn = e.target;
  const browser = $("#browser").value;
  const fd = new FormData();
  fd.append("browser", browser);
  busy(btn, true);
  log(`Extracting cookies from ${browser}…`);
  try {
    const res = await api("/api/auth/login-browser", { method: "POST", body: fd });
    showResult(res);
    if (!res.ok) {
      log("If this fails: make sure you're in native mode (./run-local.sh), that " +
          "you're signed in to WorkBench in that browser, and try closing it. " +
          "Otherwise use Option B (cookies.txt).", "err");
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
  log("Uploading cookies and signing in…");
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
  log("Refreshing catalog (this can take a while)…");
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
  log(`Searching "${$("#query").value.trim()}"…`);
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
    box.innerHTML = `<p class="hint">No results.</p>`;
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
  log(`Exporting "${$("#identifier").value.trim()}" to ${$("#fmt").value}…`);
  try {
    const res = await api("/api/export", { method: "POST", body: fd });
    showResult(res);
    if (res.download_url) {
      log(`File generated: ${res.file}`, "ok");
      await loadFiles();
    }
  } finally {
    busy(btn, false);
  }
});

$("#btnPolicy").addEventListener("click", async (e) => {
  const btn = e.target;
  const id = $("#polId").value.trim();
  if (!id) { log("Enter the CIS benchmark ID or name for the policy.", "err"); return; }
  const fd = new FormData();
  fd.append("identifier", id);
  if ($("#polTitle").value.trim()) fd.append("title", $("#polTitle").value.trim());
  if ($("#polAuthor").value.trim()) fd.append("author", $("#polAuthor").value.trim());
  if ($("#polVersion").value.trim()) fd.append("version", $("#polVersion").value.trim());
  fd.append("src_format", $("#polFormat").value);
  busy(btn, true);
  log(`Generating Word policy from "${id}" (SABIC template)… this can take a while.`);
  try {
    const res = await api("/api/policy", { method: "POST", body: fd });
    if (res.ok) {
      const b = res.benchmark || {};
      log(`Policy generated: ${res.file} — ${b.controls} controls in ${b.sections} sections (${b.title}).`, "ok");
      await loadFiles();
    } else {
      log(res.stderr || res.detail || "Could not generate the policy.", "err");
    }
  } finally {
    busy(btn, false);
  }
});

$("#filesBtn").addEventListener("click", loadFiles);
$("#clearBtn").addEventListener("click", () => { consoleEl.textContent = "Ready."; });

async function loadFiles() {
  const { files } = await api("/api/files");
  const list = $("#fileList");
  if (!files || !files.length) {
    list.innerHTML = `<li class="empty">No files yet.</li>`;
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

refreshSession();
refreshHealth();
refreshAuth();
loadFiles();
