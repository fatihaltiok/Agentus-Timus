"""Canvas UI – erweitertes Web-Interface für Timus.

Neu (v2):
  • Interaktiver Chat mit Timus (SSE-basiert)
  • Datei-Upload (📎) mit automatischem Pfad im Chat-Input
  • Agent-Health-LEDs (idle/thinking/completed/error) per SSE
  • Blinkende Thinking-LED wenn ein KI-Modell arbeitet
  • Klassische Canvas-Ansicht (Nodes, Edges, Sessions, Events) bleibt erhalten
"""

from __future__ import annotations


def build_canvas_ui_html(poll_ms: int = 2000) -> str:
    effective_poll_ms = max(500, int(poll_ms))
    html = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Timus Canvas</title>
  <style>
    :root {
      --bg:        #1b1f22;
      --surface:   #252a2e;
      --surface2:  #2a3035;
      --line:      #3b4349;
      --text:      #7dff99;
      --muted:     #56c86f;
      --ok:        #4df27a;
      --warn:      #d6f57a;
      --err:       #ff6d7a;
      --brand:     #4df27a;
      --user-bg:   #1a3a25;
      --bot-bg:    #232a2f;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: "IBM Plex Mono", "Fira Code", "Cascadia Code", monospace;
      font-size: 13px;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* ── TOP BAR ──────────────────────────────────────────────── */
    .topbar {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 9px 16px;
      background: var(--surface);
      border-bottom: 2px solid var(--line);
      flex-shrink: 0;
      user-select: none;
    }
    .topbar h1 {
      font-size: 15px;
      letter-spacing: 2px;
      color: var(--brand);
      text-transform: uppercase;
    }
    .topbar .spacer { flex: 1; }
    .topbar .poll-info { font-size: 11px; color: var(--muted); }

    /* Thinking LED (groß, prominent) */
    .thinking-led {
      width: 13px; height: 13px;
      border-radius: 50%;
      background: #3a4040;
      flex-shrink: 0;
      transition: background 0.3s;
    }
    .thinking-led.active {
      background: var(--warn);
      animation: blink 0.7s ease-in-out infinite;
    }
    #thinkingLabel {
      font-size: 11px;
      color: var(--warn);
      min-width: 80px;
      letter-spacing: 0.5px;
    }

    @keyframes blink {
      0%, 100% { opacity: 1; box-shadow: 0 0 8px var(--warn); }
      50%       { opacity: 0.12; box-shadow: none; }
    }

    /* ── SHELL: sidebar + right ───────────────────────────────── */
    .shell {
      display: grid;
      grid-template-columns: 260px 1fr;
      flex: 1;
      overflow: hidden;
      min-height: 0;
    }

    /* ── SIDEBAR ──────────────────────────────────────────────── */
    .sidebar {
      background: var(--surface);
      border-right: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .sidebar-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      scrollbar-width: thin;
      scrollbar-color: var(--line) transparent;
    }

    .section-label {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      color: var(--muted);
      margin: 14px 0 7px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--line);
    }
    .section-label:first-child { margin-top: 0; }

    /* Agent LEDs */
    .agent-row {
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 5px 4px;
      border-radius: 6px;
      transition: background 0.15s;
      cursor: default;
    }
    .agent-row:hover { background: var(--surface2); }
    .led {
      width: 9px; height: 9px;
      border-radius: 50%;
      flex-shrink: 0;
      transition: background 0.3s;
    }
    .led.idle      { background: #3a4040; }
    .led.thinking  { background: var(--warn); animation: blink 0.7s ease-in-out infinite; }
    .led.completed { background: var(--ok); }
    .led.error     { background: var(--err); }
    .agent-name    { flex: 1; font-size: 12px; }
    .agent-st      { font-size: 10px; color: var(--muted); }

    /* Canvas list */
    .canvas-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 7px 9px;
      background: var(--surface2);
      cursor: pointer;
      margin-bottom: 5px;
      transition: border-color 0.15s;
    }
    .canvas-card:hover { border-color: var(--muted); }
    .canvas-card.active { border-color: var(--brand); background: #1f3a29; }
    .canvas-card .ctitle { font-weight: 600; font-size: 12px; }
    .canvas-card .cmeta  { color: var(--muted); font-size: 10px; margin-top: 2px; }

    /* Buttons & inputs */
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
      font-size: 12px;
      padding: 6px 10px;
      background: var(--brand);
      color: #0d2b18;
      cursor: pointer;
      font-weight: 700;
      transition: opacity 0.15s;
      white-space: nowrap;
    }
    button:hover    { opacity: 0.82; }
    button:disabled { opacity: 0.4; cursor: not-allowed; }
    button.sec {
      background: var(--surface2);
      color: var(--text);
      border-color: var(--line);
      font-weight: 500;
    }

    input {
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
      font-size: 12px;
      padding: 6px 8px;
      background: #1e2428;
      color: var(--text);
      width: 100%;
    }
    input:focus         { outline: none; border-color: var(--brand); }
    input::placeholder  { color: #3a6040; }

    .btn-row {
      display: flex;
      gap: 6px;
      margin-bottom: 7px;
    }
    .attach-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 5px;
      margin-bottom: 6px;
    }

    /* ── RIGHT PANEL ──────────────────────────────────────────── */
    .right-panel {
      display: grid;
      grid-template-rows: 1fr 330px;
      overflow: hidden;
      min-height: 0;
    }

    /* Canvas view (top 60%) */
    .canvas-view {
      overflow-y: auto;
      padding: 14px 16px;
      scrollbar-width: thin;
      scrollbar-color: var(--line) transparent;
    }

    .view-title { font-size: 15px; margin-bottom: 3px; }
    .view-meta  { font-size: 10px; color: var(--muted); margin-bottom: 10px; }

    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 8px;
      align-items: center;
    }
    .filters input        { width: 130px; }
    .filter-limit         { width: 65px !important; }
    .checkbox-inline {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }
    .checkbox-inline input { width: auto; }

    .filter-line { font-size: 10px; color: var(--muted); margin-bottom: 10px; }

    .panel-grid {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 9px;
      background: var(--surface);
      padding: 10px;
      min-height: 140px;
    }
    .panel.full { grid-column: 1 / -1; }
    .panel h2 {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--muted);
      margin-bottom: 7px;
    }

    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      padding: 5px 0;
      border-bottom: 1px solid var(--line);
      font-size: 12px;
    }
    .row:last-child { border-bottom: none; }

    .badge {
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      flex-shrink: 0;
    }
    .badge.ok   { background: #1d4027; color: var(--ok); }
    .badge.warn { background: #424a1a; color: var(--warn); }
    .badge.err  { background: #3d1a20; color: var(--err); }

    .timeline {
      display: grid;
      gap: 6px;
      max-height: 300px;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--line) transparent;
    }
    .event {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #1e2428;
      padding: 7px 9px;
      font-size: 11px;
    }
    .event .ehead {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      margin-bottom: 3px;
    }
    .event .etitle { font-weight: 600; }
    .event .emeta  { font-size: 10px; color: var(--muted); }
    .empty { color: var(--muted); font-style: italic; font-size: 11px; padding: 8px 0; }

    /* ── CHAT PANEL (bottom 40%) ──────────────────────────────── */
    .chat-panel {
      border-top: 2px solid var(--line);
      background: var(--surface);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
    }
    .chat-header {
      padding: 7px 12px;
      border-bottom: 1px solid var(--line);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--muted);
      flex-shrink: 0;
    }
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      scrollbar-width: thin;
      scrollbar-color: var(--line) transparent;
      min-height: 0;
    }
    .msg {
      max-width: 88%;
      padding: 8px 12px;
      border-radius: 10px;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .msg.user {
      align-self: flex-end;
      background: var(--user-bg);
      border: 1px solid #2a6040;
    }
    .msg.assistant {
      align-self: flex-start;
      background: var(--bot-bg);
      border: 1px solid var(--line);
    }
    .msg .msg-who { font-size: 10px; color: var(--muted); margin-bottom: 3px; }
    .msg-thinking {
      align-self: flex-start;
      color: var(--warn);
      font-size: 11px;
      padding: 3px 0;
      animation: blink 1s ease-in-out infinite;
    }

    .chat-input-bar {
      display: flex;
      gap: 6px;
      padding: 8px 12px;
      border-top: 1px solid var(--line);
      background: var(--surface2);
      flex-shrink: 0;
      align-items: center;
    }
    #chatInput { flex: 1; }
    #fileInput  { display: none; }

    .upload-label {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 33px; height: 33px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface2);
      color: var(--muted);
      cursor: pointer;
      font-size: 15px;
      flex-shrink: 0;
      transition: border-color 0.15s, color 0.15s;
      user-select: none;
    }
    .upload-label:hover { border-color: var(--brand); color: var(--brand); }

    /* ── TOOL ACTIVITY ────────────────────────────────────────── */
    .tool-row {
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 3px 4px;
      border-radius: 5px;
      font-size: 11px;
    }
    .tool-dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      flex-shrink: 0;
      background: #3a4040;
    }
    .tool-dot.running {
      background: var(--warn);
      animation: blink 0.7s ease-in-out infinite;
    }
    .tool-dot.done { background: var(--ok); }
    .tool-name-active {
      color: var(--warn);
      font-size: 11px;
      font-weight: 600;
    }
    .tool-name-done {
      color: var(--muted);
      font-size: 10px;
    }

    @media (max-width: 1100px) {
      .shell { grid-template-columns: 1fr; }
      .right-panel { grid-template-rows: 1fr 280px; }
      .panel-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- TOP BAR -->
  <div class="topbar">
    <div id="thinkingLed" class="thinking-led" title="Thinking-LED: leuchtet wenn Timus denkt"></div>
    <h1>Timus Canvas</h1>
    <span id="thinkingLabel"></span>
    <div class="spacer"></div>
    <span class="poll-info">Poll: <span id="pollState">on</span> · <span id="pollMs">__POLL_MS__</span> ms</span>
    <button class="sec" id="togglePollingBtn" style="padding:4px 9px; font-size:11px;">Pause</button>
  </div>

  <div class="shell">

    <!-- SIDEBAR -->
    <aside class="sidebar">
      <div class="sidebar-scroll">

        <!-- AGENT LEDs -->
        <div class="section-label">Agenten</div>
        <div id="agentLeds"></div>

        <!-- TOOL ACTIVITY -->
        <div class="section-label">Tools</div>
        <div id="toolActive"></div>
        <div id="toolHistory"></div>

        <!-- CANVAS VERWALTUNG -->
        <div class="section-label">Canvas</div>
        <div class="btn-row">
          <button id="createBtn" style="flex:1; font-size:11px;">+ Neu</button>
          <button class="sec" id="refreshBtn" style="padding:6px 8px; font-size:11px;" title="Aktualisieren">↺</button>
        </div>
        <div class="attach-grid">
          <input id="attachCanvasId" placeholder="canvas_id" />
          <input id="attachSessionId" placeholder="session_id" />
        </div>
        <div class="btn-row">
          <button class="sec" id="attachBtn" style="flex:1; font-size:11px; font-weight:500;">Session verknüpfen</button>
        </div>

        <div id="canvasList"></div>

      </div>
    </aside><!-- .sidebar -->

    <!-- RIGHT: Canvas-Ansicht oben + Chat unten -->
    <div class="right-panel">

      <!-- CANVAS-ANSICHT -->
      <div class="canvas-view">
        <div class="view-title" id="viewTitle">Kein Canvas ausgewählt</div>
        <div class="view-meta" id="viewMeta">Erstelle ein Canvas oder wähle eines aus der Sidebar.</div>

        <div class="filters">
          <input id="filterSession" placeholder="Session-ID…" />
          <input id="filterAgent"   placeholder="Agent…" />
          <input id="filterStatus"  placeholder="Status…" />
          <label class="checkbox-inline">
            <input id="filterErrors" type="checkbox" /> nur Fehler
          </label>
          <input id="filterLimit" class="filter-limit" type="number" min="1" max="500" value="100" />
          <button id="applyFilter"  style="font-size:11px; padding:5px 9px;">Filter</button>
          <button class="sec" id="resetFilter" style="font-size:11px; padding:5px 7px;">Reset</button>
        </div>
        <div class="filter-line" id="filterLine">Filter: keine</div>

        <div class="panel-grid">
          <div class="panel"><h2>Nodes</h2><div id="nodes"></div></div>
          <div class="panel"><h2>Edges</h2><div id="edges"></div></div>
          <div class="panel"><h2>Sessions</h2><div id="sessions"></div></div>
          <div class="panel full">
            <h2>Event Timeline</h2>
            <div id="events" class="timeline"></div>
          </div>
        </div>
      </div><!-- .canvas-view -->

      <!-- CHAT-PANEL -->
      <div class="chat-panel">
        <div class="chat-header">Chat mit Timus</div>
        <div id="chatMessages" class="chat-messages">
          <div class="empty">Stelle Timus eine Frage…</div>
        </div>
        <div class="chat-input-bar">
          <input id="chatInput" placeholder="Nachricht eingeben… (Enter = Senden)" />
          <label class="upload-label" title="Datei hochladen">
            📎
            <input type="file" id="fileInput" />
          </label>
          <button id="sendBtn">Senden</button>
        </div>
      </div><!-- .chat-panel -->

    </div><!-- .right-panel -->

  </div><!-- .shell -->

<script>
"use strict";

const POLL_MS = __POLL_MS__;
let selectedCanvasId = "";
let pollingEnabled   = true;
let pollTimer        = null;
let currentFilters   = { session_id: "", agent: "", status: "", only_errors: false, event_limit: 100 };
let chatSessionId    = "canvas_" + Math.random().toString(36).slice(2, 10);
let isSending        = false;
let activeTool       = null;   // { tool, id }
let toolHistory      = [];     // letzten 5 abgeschlossenen Tools

// ── UTILITIES ────────────────────────────────────────────────────
function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
function statusCls(s) {
  s = String(s || "").toLowerCase();
  if (s.includes("error") || s.includes("fehler")) return "err";
  if (s.includes("cancel") || s.includes("warn"))   return "warn";
  if (s.includes("completed") || s.includes("success") || s.includes("running") || s.includes("ok")) return "ok";
  return "warn";
}
async function api(url, opts) {
  const r = await fetch(url, opts || {});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || d.message || r.statusText);
  return d;
}

// ── TOOL ACTIVITY ────────────────────────────────────────────────
function renderToolActivity() {
  const activeEl  = document.getElementById("toolActive");
  const historyEl = document.getElementById("toolHistory");

  if (activeTool) {
    activeEl.innerHTML =
      `<div class="tool-row">` +
      `<div class="tool-dot running"></div>` +
      `<span class="tool-name-active">${esc(activeTool.tool)}</span>` +
      `</div>`;
  } else {
    activeEl.innerHTML = `<div class="empty" style="font-size:10px;">Kein Tool aktiv</div>`;
  }

  if (toolHistory.length) {
    historyEl.innerHTML = toolHistory.map(t =>
      `<div class="tool-row">` +
      `<div class="tool-dot done"></div>` +
      `<span class="tool-name-done">${esc(t)}</span>` +
      `</div>`
    ).join("");
  } else {
    historyEl.innerHTML = "";
  }
}

// ── AGENT LEDs ───────────────────────────────────────────────────
const AGENTS = ["executor","research","reasoning","creative","development","meta","visual","data","document","communication","system"];
const agentState = Object.fromEntries(AGENTS.map(a => [a, "idle"]));

function renderAgentLeds(agents) {
  const wrap = document.getElementById("agentLeds");
  wrap.innerHTML = "";
  for (const name of AGENTS) {
    const info   = (agents && agents[name]) || { status: "idle", last_query: "" };
    const status = info.status || "idle";
    agentState[name] = status;
    const row = document.createElement("div");
    row.className = "agent-row";
    row.id        = "agent-row-" + name;
    row.innerHTML =
      `<div class="led ${esc(status)}" id="led-${esc(name)}"></div>` +
      `<span class="agent-name">${esc(name)}</span>` +
      `<span class="agent-st"  id="ledst-${esc(name)}">${esc(status)}</span>`;
    if (info.last_query) row.title = info.last_query;
    wrap.appendChild(row);
  }
}

function updateAgentLed(agent, status) {
  agentState[agent] = status;
  const led = document.getElementById("led-" + agent);
  if (led) led.className = "led " + status;
  const st  = document.getElementById("ledst-" + agent);
  if (st)  st.textContent = status;
}

// ── THINKING LED ─────────────────────────────────────────────────
function setThinking(active) {
  const led   = document.getElementById("thinkingLed");
  const label = document.getElementById("thinkingLabel");
  if (active) {
    led.classList.add("active");
    label.textContent = "Denkt…";
  } else {
    led.classList.remove("active");
    label.textContent = "";
  }
}

// ── SSE ──────────────────────────────────────────────────────────
let sseSource = null;
function connectSSE() {
  if (sseSource) return;
  sseSource = new EventSource("/events/stream");
  sseSource.onmessage = (e) => {
    try { handleSSE(JSON.parse(e.data)); } catch {}
  };
  sseSource.onerror = () => {
    sseSource.close();
    sseSource = null;
    setTimeout(connectSSE, 5000);
  };
}

function handleSSE(d) {
  if (d.type === "ping") return;

  if (d.type === "init") {
    renderAgentLeds(d.agents || {});
    setThinking(!!d.thinking);
    return;
  }
  if (d.type === "thinking") {
    setThinking(!!d.active);
    return;
  }
  if (d.type === "agent_status") {
    updateAgentLed(d.agent, d.status);
    return;
  }
  if (d.type === "chat_reply") {
    removeChatThinking();
    appendChatMsg("assistant", d.agent || "Timus", d.text || "");
    isSending = false;
    document.getElementById("sendBtn").disabled = false;
    return;
  }
  if (d.type === "chat_error") {
    removeChatThinking();
    appendChatMsg("assistant", "⚠ Fehler", d.error || "Unbekannter Fehler");
    isSending = false;
    document.getElementById("sendBtn").disabled = false;
    return;
  }
  if (d.type === "upload") {
    appendChatMsg("assistant", "System",
      `📎 Datei gespeichert: ${d.filename} (${(d.size / 1024).toFixed(1)} KB)\nPfad: ${d.path}`);
    return;
  }
  if (d.type === "tool_start") {
    activeTool = { tool: d.tool, id: d.id };
    renderToolActivity();
    return;
  }
  if (d.type === "tool_done") {
    activeTool = null;
    if (d.tool) {
      toolHistory.unshift(d.tool);
      if (toolHistory.length > 5) toolHistory.length = 5;
    }
    renderToolActivity();
    return;
  }
}

// ── CHAT ─────────────────────────────────────────────────────────
function appendChatMsg(role, sender, text) {
  const wrap = document.getElementById("chatMessages");
  const placeholder = wrap.querySelector(".empty");
  if (placeholder) placeholder.remove();

  const div = document.createElement("div");
  div.className = "msg " + role;
  div.innerHTML =
    `<div class="msg-who">${esc(role === "user" ? "Du" : sender)} · ${new Date().toLocaleTimeString()}</div>` +
    esc(text);
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function addChatThinking() {
  const wrap = document.getElementById("chatMessages");
  const div  = document.createElement("div");
  div.className = "msg-thinking";
  div.id        = "chat-thinking";
  div.textContent = "● Timus denkt…";
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function removeChatThinking() {
  const el = document.getElementById("chat-thinking");
  if (el) el.remove();
}

async function sendChat() {
  if (isSending) return;
  const input = document.getElementById("chatInput");
  const query = input.value.trim();
  if (!query) return;

  isSending = true;
  document.getElementById("sendBtn").disabled = true;
  input.value = "";

  appendChatMsg("user", "", query);
  addChatThinking();

  try {
    await fetch("/chat", {
      method:  "POST",
      headers: { "content-type": "application/json" },
      body:    JSON.stringify({ query, session_id: chatSessionId }),
    });
    // Antwort kommt asynchron via SSE (chat_reply / chat_error)
  } catch (err) {
    removeChatThinking();
    appendChatMsg("assistant", "⚠ Fehler", "Verbindungsfehler: " + err.message);
    isSending = false;
    document.getElementById("sendBtn").disabled = false;
  }
}

// ── FILE UPLOAD ──────────────────────────────────────────────────
async function handleFileUpload(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await api("/upload", { method: "POST", body: fd });
    if (data.status === "success") {
      document.getElementById("chatInput").value =
        `Analysiere die hochgeladene Datei: ${data.path}`;
      document.getElementById("chatInput").focus();
    }
  } catch (err) {
    appendChatMsg("assistant", "⚠ Upload", "Upload fehlgeschlagen: " + err.message);
  }
}

// ── CANVAS VIEW ──────────────────────────────────────────────────
function renderRows(id, rows, emptyText) {
  const el = document.getElementById(id);
  el.innerHTML = rows.length
    ? rows.join("")
    : `<div class="empty">${esc(emptyText)}</div>`;
}

function renderCanvas(canvas) {
  if (!canvas) return;

  document.getElementById("viewTitle").textContent = canvas.title || canvas.id;
  const vc = canvas.view_counts || {};
  document.getElementById("viewMeta").textContent =
    `${canvas.id} · geändert: ${canvas.updated_at || "–"} · ` +
    `nodes=${vc.nodes ?? 0}  edges=${vc.edges ?? 0}  events=${vc.events ?? 0}`;

  const vf = canvas.view_filters || {};
  const parts = [];
  if (vf.session_id) parts.push("session=" + vf.session_id);
  if (vf.agent)      parts.push("agent=" + vf.agent);
  if (vf.status)     parts.push("status=" + vf.status);
  if (vf.only_errors) parts.push("nur-Fehler");
  parts.push("limit=" + (vf.event_limit || 100));
  document.getElementById("filterLine").textContent = "Filter: " + parts.join(", ");

  // Nodes
  const nodes = Object.values(canvas.nodes || {})
    .sort((a, b) => String(a.title || "").localeCompare(String(b.title || "")));
  renderRows("nodes", nodes.map(n => `
    <div class="row">
      <div>
        <div style="font-weight:600;">${esc(n.title || n.id)}</div>
        <div style="font-size:10px;color:var(--muted);">${esc(n.id)}</div>
      </div>
      <span class="badge ${statusCls(n.status)}">${esc(n.status || "idle")}</span>
    </div>`), "Keine Nodes");

  // Edges
  const edges = (canvas.edges || []).slice()
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  renderRows("edges", edges.map(e => `
    <div class="row">
      <div><strong>${esc(e.source)}</strong> → <strong>${esc(e.target)}</strong></div>
      <span style="font-size:10px;color:var(--muted);">${esc(e.kind || "flow")}</span>
    </div>`), "Keine Edges");

  // Sessions
  const sessions = (canvas.session_ids || []).slice().sort();
  renderRows("sessions",
    sessions.map(sid => `<div class="row">${esc(sid)}</div>`),
    "Keine Sessions");

  // Events
  const events = (canvas.events || []).slice()
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  renderRows("events", events.map(ev => `
    <article class="event">
      <div class="ehead">
        <div class="etitle">
          ${esc(ev.type || "event")}
          <span style="font-weight:normal;color:var(--muted);">
            | ${esc(ev.agent || "–")} | ${esc(ev.node_id || "–")}
          </span>
        </div>
        <span class="badge ${statusCls(ev.status)}">${esc(ev.status || "–")}</span>
      </div>
      <div class="emeta">${esc(ev.created_at || "–")} · session: ${esc(ev.session_id || "–")}</div>
      <div style="margin-top:4px;">${esc(ev.message || "")}</div>
    </article>`), "Keine Events");
}

// ── CANVAS LIST ──────────────────────────────────────────────────
async function loadCanvasList() {
  const data  = await api("/canvas?limit=200").catch(() => ({ items: [] }));
  const items = data.items || [];
  const list  = document.getElementById("canvasList");
  list.innerHTML = "";

  if (!items.length) {
    list.innerHTML = '<div class="empty">Noch kein Canvas erstellt.</div>';
    selectedCanvasId = "";
    return;
  }

  if (!selectedCanvasId || !items.some(c => c.id === selectedCanvasId)) {
    selectedCanvasId = items[0].id;
    document.getElementById("attachCanvasId").value = selectedCanvasId;
  }

  for (const c of items) {
    const card = document.createElement("div");
    card.className = "canvas-card" + (c.id === selectedCanvasId ? " active" : "");
    card.innerHTML =
      `<div class="ctitle">${esc(c.title)}</div>` +
      `<div class="cmeta">${(c.events || []).length} Events · ${(c.session_ids || []).length} Sessions</div>`;
    card.addEventListener("click", () => {
      selectedCanvasId = c.id;
      document.getElementById("attachCanvasId").value = c.id;
      renderCanvas(c);
      loadCanvasList();
    });
    list.appendChild(card);
  }
}

function buildQuery() {
  const p = new URLSearchParams();
  if (currentFilters.session_id) p.set("session_id", currentFilters.session_id);
  if (currentFilters.agent)      p.set("agent", currentFilters.agent);
  if (currentFilters.status)     p.set("status", currentFilters.status);
  if (currentFilters.only_errors) p.set("only_errors", "true");
  p.set("event_limit", String(currentFilters.event_limit));
  const qs = p.toString();
  return qs ? "?" + qs : "";
}

async function refreshCanvas() {
  if (!selectedCanvasId) return;
  try {
    const data = await api(`/canvas/${encodeURIComponent(selectedCanvasId)}${buildQuery()}`);
    renderCanvas(data.canvas);
  } catch {}
}

function setPolling(on) {
  pollingEnabled = Boolean(on);
  document.getElementById("pollState").textContent = pollingEnabled ? "on" : "pause";
  document.getElementById("togglePollingBtn").textContent = pollingEnabled ? "Pause" : "Resume";
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (pollingEnabled) {
    pollTimer = setInterval(() => { refreshCanvas(); loadCanvasList(); }, POLL_MS);
  }
}

// ── INIT ─────────────────────────────────────────────────────────
async function init() {
  document.getElementById("pollMs").textContent = String(POLL_MS);

  // Leere LED-Zeilen sofort rendern
  renderAgentLeds({});
  renderToolActivity();

  // Agent-Status vom Server holen
  try {
    const s = await api("/agent_status");
    renderAgentLeds(s.agents || {});
    setThinking(!!s.thinking);
  } catch {}

  // Chat-Verlauf laden
  try {
    const h = await api("/chat/history");
    const msgs = (h.history || []);
    if (msgs.length) {
      document.getElementById("chatMessages").innerHTML = "";
      for (const m of msgs) {
        appendChatMsg(m.role || "assistant", m.agent || "Timus", m.text || "");
      }
    }
  } catch {}

  // SSE verbinden
  connectSSE();

  // Event-Listener
  document.getElementById("sendBtn").addEventListener("click", sendChat);
  document.getElementById("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
  document.getElementById("fileInput").addEventListener("change", (e) => {
    handleFileUpload(e.target.files[0]);
    e.target.value = "";
  });
  document.getElementById("togglePollingBtn").addEventListener("click", () => setPolling(!pollingEnabled));

  document.getElementById("createBtn").addEventListener("click", async () => {
    const title = prompt("Canvas-Titel", "Timus Session");
    if (!title) return;
    try {
      const out = await api("/canvas/create", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body:    JSON.stringify({ title, description: "" }),
      });
      selectedCanvasId = out.canvas.id;
      document.getElementById("attachCanvasId").value = out.canvas.id;
      renderCanvas(out.canvas);
      await loadCanvasList();
    } catch (err) { alert("Fehler: " + err.message); }
  });

  document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadCanvasList();
    await refreshCanvas();
  });

  document.getElementById("attachBtn").addEventListener("click", async () => {
    const cid = document.getElementById("attachCanvasId").value.trim();
    const sid = document.getElementById("attachSessionId").value.trim();
    if (!cid || !sid) { alert("canvas_id und session_id sind erforderlich"); return; }
    try {
      await api(`/canvas/${encodeURIComponent(cid)}/attach_session`, {
        method:  "POST",
        headers: { "content-type": "application/json" },
        body:    JSON.stringify({ session_id: sid }),
      });
      selectedCanvasId = cid;
      await refreshCanvas();
      await loadCanvasList();
    } catch (err) { alert("Fehler: " + err.message); }
  });

  document.getElementById("applyFilter").addEventListener("click", () => {
    const limitRaw = Number(document.getElementById("filterLimit").value) || 100;
    currentFilters = {
      session_id:  document.getElementById("filterSession").value.trim(),
      agent:       document.getElementById("filterAgent").value.trim(),
      status:      document.getElementById("filterStatus").value.trim(),
      only_errors: document.getElementById("filterErrors").checked,
      event_limit: Math.max(1, Math.min(500, limitRaw)),
    };
    document.getElementById("filterLimit").value = String(currentFilters.event_limit);
    refreshCanvas();
  });

  document.getElementById("resetFilter").addEventListener("click", () => {
    document.getElementById("filterSession").value = "";
    document.getElementById("filterAgent").value   = "";
    document.getElementById("filterStatus").value  = "";
    document.getElementById("filterErrors").checked = false;
    document.getElementById("filterLimit").value   = "100";
    currentFilters = { session_id: "", agent: "", status: "", only_errors: false, event_limit: 100 };
    refreshCanvas();
  });

  await loadCanvasList();
  await refreshCanvas();
  setPolling(true);
}

init().catch((err) => console.error("Canvas-Init-Fehler:", err));
</script>
</body>
</html>
"""
    return html.replace("__POLL_MS__", str(effective_poll_ms))
