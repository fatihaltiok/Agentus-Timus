"""HTML View fuer das Timus Canvas MVP."""

from __future__ import annotations


def build_canvas_ui_html(poll_ms: int = 2000) -> str:
    effective_poll_ms = max(500, int(poll_ms))
    html = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Timus Canvas Live View</title>
  <style>
    :root {
      --bg: #1f2326;
      --surface: #2a2f33;
      --line: #3b4349;
      --text: #7dff99;
      --muted: #56c86f;
      --ok: #9bffb1;
      --warn: #d6f57a;
      --err: #ff6d7a;
      --brand: #4df27a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(180deg, #1b1f22 0%, var(--bg) 100%);
      color: var(--text);
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }
    .shell {
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
    }
    .sidebar {
      border-right: 1px solid var(--line);
      background: var(--surface);
      padding: 14px;
      overflow: auto;
    }
    .main {
      padding: 14px;
      overflow: auto;
    }
    h1 {
      margin: 0 0 12px;
      font-size: 20px;
      letter-spacing: 0.2px;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 15px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .controls, .attach {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      margin-bottom: 10px;
    }
    .attach {
      grid-template-columns: 1fr 1fr auto;
    }
    .filters {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr auto auto auto auto;
      gap: 8px;
      margin: 10px 0 12px;
      align-items: center;
    }
    .checkbox-inline {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .checkbox-inline input {
      width: 14px;
      height: 14px;
      margin: 0;
      padding: 0;
    }
    button, input {
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
      padding: 8px 10px;
      background: #23292d;
      color: var(--text);
    }
    button {
      cursor: pointer;
      background: var(--brand);
      color: #12301b;
      border-color: var(--brand);
      font-weight: 600;
    }
    button.secondary {
      background: #23292d;
      color: var(--text);
      border-color: var(--line);
      font-weight: 500;
    }
    input::placeholder {
      color: #5bbf72;
      opacity: 0.9;
    }
    .list {
      display: grid;
      gap: 8px;
    }
    .canvas-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      background: #252b2f;
      cursor: pointer;
    }
    .canvas-card.active {
      border-color: var(--brand);
      background: #1f3a29;
    }
    .small {
      color: var(--muted);
      font-size: 12px;
    }
    .grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--surface);
      padding: 12px;
      min-height: 220px;
    }
    .panel.full {
      grid-column: 1 / -1;
    }
    .row {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
    }
    .row:last-child { border-bottom: none; }
    .badge {
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .badge.ok { background: #24412b; color: var(--ok); }
    .badge.warn { background: #454b1f; color: var(--warn); }
    .badge.err { background: #4a2329; color: var(--err); }
    .muted { color: var(--muted); }
    .empty {
      color: var(--muted);
      padding: 16px 0;
      font-style: italic;
    }
    .timeline {
      display: grid;
      gap: 8px;
      max-height: 460px;
      overflow: auto;
      padding-right: 2px;
    }
    .event {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #252b2f;
      padding: 10px;
    }
    .event .head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    @media (max-width: 1200px) {
      .shell {
        grid-template-columns: 1fr;
      }
      .filters {
        grid-template-columns: 1fr 1fr;
      }
      .grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <h1>Canvas</h1>
      <div class="controls">
        <button id="createCanvasBtn">Create</button>
        <button id="refreshListBtn" class="secondary">Refresh</button>
      </div>
      <div class="attach">
        <input id="attachCanvasId" placeholder="canvas_id" />
        <input id="attachSessionId" placeholder="session_id" />
        <button id="attachBtn">Attach</button>
      </div>
      <div id="canvasList" class="list"></div>
    </aside>
    <main class="main">
      <h1 id="title">No Canvas selected</h1>
      <div class="small" id="metaLine">Use "Create" or select an existing canvas.</div>
      <div class="small" style="margin: 8px 0 12px;">
        Live polling: <span id="pollState">on</span> every <span id="pollMs">__POLL_MS__</span> ms
        <button id="togglePollingBtn" class="secondary" style="margin-left:8px; padding:4px 8px;">Toggle</button>
      </div>
      <div class="filters">
        <input id="filterSession" placeholder="filter session_id" />
        <input id="filterAgent" placeholder="filter agent (e.g. research)" />
        <input id="filterStatus" placeholder="filter status (e.g. error)" />
        <label class="checkbox-inline"><input id="filterOnlyErrors" type="checkbox" /> only errors</label>
        <input id="filterLimit" type="number" min="1" max="1000" value="200" style="width:90px;" />
        <button id="applyFilterBtn">Apply</button>
        <button id="resetFilterBtn" class="secondary">Reset</button>
      </div>
      <div class="small" id="filterLine">Active filters: none</div>

      <section class="grid">
        <div class="panel">
          <h2>Nodes</h2>
          <div id="nodes"></div>
        </div>
        <div class="panel">
          <h2>Edges</h2>
          <div id="edges"></div>
        </div>
        <div class="panel">
          <h2>Sessions</h2>
          <div id="sessions"></div>
        </div>
        <div class="panel full">
          <h2>Event Timeline</h2>
          <div id="events" class="timeline"></div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const POLL_MS = __POLL_MS__;
    let selectedCanvasId = "";
    let pollingEnabled = true;
    let pollTimer = null;
    let currentFilters = {
      session_id: "",
      agent: "",
      status: "",
      only_errors: false,
      event_limit: 200
    };

    function statusClass(status) {
      const s = String(status || "").toLowerCase();
      if (s.includes("error")) return "err";
      if (s.includes("cancel") || s.includes("warn") || s.includes("limit")) return "warn";
      if (s.includes("completed") || s.includes("success") || s.includes("running")) return "ok";
      return "warn";
    }

    function escapeHtml(v) {
      return String(v || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    async function fetchJson(url, options) {
      const resp = await fetch(url, options || {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const detail = data.error || data.message || resp.statusText;
        throw new Error(detail);
      }
      return data;
    }

    async function loadCanvasList() {
      const out = await fetchJson("/canvas?limit=200");
      const list = document.getElementById("canvasList");
      list.innerHTML = "";
      const items = out.items || [];
      if (!items.length) {
        selectedCanvasId = "";
        document.getElementById("attachCanvasId").value = "";
        list.innerHTML = '<div class="empty">No canvases yet.</div>';
        return;
      }

      const selectedStillExists = items.some((c) => c.id === selectedCanvasId);
      if (!selectedStillExists) {
        selectedCanvasId = items[0].id;
        document.getElementById("attachCanvasId").value = selectedCanvasId;
      }

      for (const c of items) {
        const card = document.createElement("div");
        card.className = "canvas-card" + (c.id === selectedCanvasId ? " active" : "");
        card.innerHTML = `
          <div><strong>${escapeHtml(c.title)}</strong></div>
          <div class="small">${escapeHtml(c.id)}</div>
          <div class="small">${(c.session_ids || []).length} sessions, ${(c.events || []).length} events</div>
        `;
        card.addEventListener("click", () => {
          selectedCanvasId = c.id;
          document.getElementById("attachCanvasId").value = c.id;
          renderCanvas(c);
          void loadCanvasList();
        });
        list.appendChild(card);
      }

      if (!selectedStillExists) {
        await refreshSelectedCanvas();
      }
    }

    function renderListRows(targetId, rowsHtml, emptyText) {
      const el = document.getElementById(targetId);
      if (!rowsHtml.length) {
        el.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
      } else {
        el.innerHTML = rowsHtml.join("");
      }
    }

    function renderCanvas(canvas) {
      if (!canvas) return;
      const viewCounts = canvas.view_counts || {};
      const vc = `nodes=${viewCounts.nodes ?? Object.keys(canvas.nodes || {}).length}, `
        + `edges=${viewCounts.edges ?? (canvas.edges || []).length}, `
        + `events=${viewCounts.events ?? (canvas.events || []).length}`;
      document.getElementById("title").textContent = canvas.title || canvas.id;
      document.getElementById("metaLine").textContent =
        `${canvas.id} | updated: ${canvas.updated_at || "-"} | created: ${canvas.created_at || "-"} | ${vc}`;

      const vf = canvas.view_filters || {};
      const activeParts = [];
      if (vf.session_id) activeParts.push(`session=${vf.session_id}`);
      if (vf.agent) activeParts.push(`agent=${vf.agent}`);
      if (vf.status) activeParts.push(`status=${vf.status}`);
      if (vf.only_errors) activeParts.push(`only_errors=true`);
      activeParts.push(`limit=${vf.event_limit || currentFilters.event_limit}`);
      document.getElementById("filterLine").textContent =
        "Active filters: " + (activeParts.length ? activeParts.join(", ") : "none");

      const nodes = Object.values(canvas.nodes || {});
      nodes.sort((a, b) => String(a.title || "").localeCompare(String(b.title || "")));
      const nodeRows = nodes.map((n) => `
        <div class="row">
          <div>
            <div><strong>${escapeHtml(n.title || n.id)}</strong></div>
            <div class="small">${escapeHtml(n.id)}</div>
          </div>
          <div class="badge ${statusClass(n.status)}">${escapeHtml(n.status || "idle")}</div>
        </div>
      `);
      renderListRows("nodes", nodeRows, "No nodes");

      const edges = (canvas.edges || []).slice();
      edges.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      const edgeRows = edges.map((e) => `
        <div class="row">
          <div>
            <div><strong>${escapeHtml(e.source)}</strong> -> <strong>${escapeHtml(e.target)}</strong></div>
            <div class="small">${escapeHtml(e.kind || "flow")} ${e.label ? ("| " + escapeHtml(e.label)) : ""}</div>
          </div>
        </div>
      `);
      renderListRows("edges", edgeRows, "No edges");

      const sessions = (canvas.session_ids || []).slice().sort();
      const sessionRows = sessions.map((sid) => `
        <div class="row">
          <div>${escapeHtml(sid)}</div>
        </div>
      `);
      renderListRows("sessions", sessionRows, "No linked sessions");

      const events = (canvas.events || []).slice();
      events.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      const eventRows = events.map((e) => `
        <article class="event">
          <div class="head">
            <div>
              <strong>${escapeHtml(e.type || "event")}</strong>
              <span class="muted"> | ${escapeHtml(e.agent || "-")} | ${escapeHtml(e.node_id || "-")}</span>
            </div>
            <span class="badge ${statusClass(e.status)}">${escapeHtml(e.status || "-")}</span>
          </div>
          <div class="small">${escapeHtml(e.created_at || "-")} | session: ${escapeHtml(e.session_id || "-")}</div>
          <div style="margin-top:6px;">${escapeHtml(e.message || "")}</div>
        </article>
      `);
      renderListRows("events", eventRows, "No events");
    }

    function readFilterControls() {
      const limitRaw = Number(document.getElementById("filterLimit").value || 200);
      currentFilters = {
        session_id: document.getElementById("filterSession").value.trim(),
        agent: document.getElementById("filterAgent").value.trim(),
        status: document.getElementById("filterStatus").value.trim(),
        only_errors: document.getElementById("filterOnlyErrors").checked,
        event_limit: Number.isFinite(limitRaw) ? Math.max(1, Math.min(1000, limitRaw)) : 200
      };
      document.getElementById("filterLimit").value = String(currentFilters.event_limit);
    }

    function resetFilterControls() {
      document.getElementById("filterSession").value = "";
      document.getElementById("filterAgent").value = "";
      document.getElementById("filterStatus").value = "";
      document.getElementById("filterOnlyErrors").checked = false;
      document.getElementById("filterLimit").value = "200";
      readFilterControls();
    }

    function buildCanvasQuery() {
      const p = new URLSearchParams();
      if (currentFilters.session_id) p.set("session_id", currentFilters.session_id);
      if (currentFilters.agent) p.set("agent", currentFilters.agent);
      if (currentFilters.status) p.set("status", currentFilters.status);
      if (currentFilters.only_errors) p.set("only_errors", "true");
      p.set("event_limit", String(currentFilters.event_limit || 200));
      const qs = p.toString();
      return qs ? ("?" + qs) : "";
    }

    async function refreshSelectedCanvas() {
      if (!selectedCanvasId) return;
      try {
        const out = await fetchJson(`/canvas/${encodeURIComponent(selectedCanvasId)}${buildCanvasQuery()}`);
        renderCanvas(out.canvas);
      } catch (err) {
        console.error("refresh canvas failed:", err);
      }
    }

    function setPolling(enabled) {
      pollingEnabled = Boolean(enabled);
      const state = document.getElementById("pollState");
      state.textContent = pollingEnabled ? "on" : "off";
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (pollingEnabled) {
        pollTimer = setInterval(async () => {
          await refreshSelectedCanvas();
          await loadCanvasList();
        }, POLL_MS);
      }
    }

    async function createCanvasFlow() {
      const title = prompt("Canvas title", "Timus Session Canvas");
      if (title === null) return;
      const description = prompt("Description", "Live orchestration view");
      try {
        const out = await fetchJson("/canvas/create", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({title, description})
        });
        selectedCanvasId = out.canvas.id;
        document.getElementById("attachCanvasId").value = out.canvas.id;
        renderCanvas(out.canvas);
        await loadCanvasList();
      } catch (err) {
        alert("Create failed: " + err.message);
      }
    }

    async function attachSessionFlow() {
      const canvasId = document.getElementById("attachCanvasId").value.trim();
      const sessionId = document.getElementById("attachSessionId").value.trim();
      if (!canvasId || !sessionId) {
        alert("canvas_id and session_id are required");
        return;
      }
      try {
        await fetchJson(`/canvas/${encodeURIComponent(canvasId)}/attach_session`, {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({session_id: sessionId})
        });
        selectedCanvasId = canvasId;
        await refreshSelectedCanvas();
        await loadCanvasList();
      } catch (err) {
        alert("Attach failed: " + err.message);
      }
    }

    async function init() {
      document.getElementById("pollMs").textContent = String(POLL_MS);
      document.getElementById("createCanvasBtn").addEventListener("click", createCanvasFlow);
      document.getElementById("refreshListBtn").addEventListener("click", async () => {
        await loadCanvasList();
        await refreshSelectedCanvas();
      });
      document.getElementById("attachBtn").addEventListener("click", attachSessionFlow);
      document.getElementById("togglePollingBtn").addEventListener("click", () => {
        setPolling(!pollingEnabled);
      });
      document.getElementById("applyFilterBtn").addEventListener("click", async () => {
        readFilterControls();
        await refreshSelectedCanvas();
      });
      document.getElementById("resetFilterBtn").addEventListener("click", async () => {
        resetFilterControls();
        await refreshSelectedCanvas();
      });

      readFilterControls();
      await loadCanvasList();
      await refreshSelectedCanvas();
      setPolling(true);
    }

    init().catch((err) => {
      console.error(err);
      alert("Canvas UI init failed: " + err.message);
    });
  </script>
</body>
</html>
"""
    return html.replace("__POLL_MS__", str(effective_poll_ms))
