"""Canvas UI v3.2 — Timus Premium Hochglanz-Interface.

Visuelles Design:
  • Tiefes Raumblau-Schwarz (#04070b) mit phosphoreszierendem Teal-Akzent
  • Glassmorphismus-Panels: backdrop-filter blur + saturate
  • Animierter Dot-Grid Hintergrund + radiale Nebel-Gradienten
  • Gradient-Borders, Inset-Glows, Box-Shadow-Tiefe
  • JetBrains Mono (Google Fonts CDN)
  • Gradient-Shimmer auf Fortschrittsbalken
  • Pulsende Ringe für denkende Agenten
  • Gradient-Text für Timus-Titel (animierter Shimmer)
  • Premium Cytoscape-Nodes mit Glow + Border-Gradient
  • Rich chat bubbles mit Markdown + Syntax-Highlighting
"""

from __future__ import annotations


def build_canvas_ui_html(poll_ms: int = 2000) -> str:
    effective_poll_ms = max(500, int(poll_ms))
    return _TEMPLATE.replace("__POLL_MS__", str(effective_poll_ms))


_TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Timus Canvas</title>

  <!-- Premium Monospace Font -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet" />

  <!-- marked.js -->
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <!-- highlight.js -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11/styles/atom-one-dark.min.css" />
  <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/highlight.min.js"></script>
  <!-- Cytoscape.js -->
  <script src="https://cdn.jsdelivr.net/npm/cytoscape@3/dist/cytoscape.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js"></script>

  <style>
    /* ═══════════════════════════════════════════════════
       DESIGN TOKENS — 30-bit-ähnliche Farbtiefe
    ═══════════════════════════════════════════════════ */
    :root {
      /* Hintergrund-Schichten */
      --bg-base:    #03060a;
      --bg:         #06090e;
      --surface:    #0b1520;
      --surface2:   #0f1c2c;
      --surface3:   #152436;
      --surface4:   #1b2e42;

      /* Grenzen */
      --border:     rgba(0, 210, 130, 0.10);
      --border2:    rgba(0, 210, 130, 0.18);
      --border3:    rgba(0, 210, 130, 0.32);
      --border-dim: rgba(255,255,255,0.04);

      /* Primär — Phosphoreszierendes Teal */
      --brand:      #00e09a;
      --brand2:     #00c485;
      --brand3:     #00a870;
      --brand-glow: rgba(0, 224, 154, 0.18);
      --brand-dim:  rgba(0, 224, 154, 0.06);

      /* Sekundär — Elektrisches Cyan */
      --cyan:       #00d4f0;
      --cyan-glow:  rgba(0, 212, 240, 0.15);

      /* Denk-Zustand — KI-Lila */
      --think:      #a78bfa;
      --think-glow: rgba(167, 139, 250, 0.20);

      /* Status */
      --ok:         #00e09a;
      --ok-glow:    rgba(0, 224, 154, 0.25);
      --warn:       #fbbf24;
      --warn-glow:  rgba(251,191,36,0.20);
      --err:        #f43f5e;
      --err-glow:   rgba(244,63,94,0.20);

      /* Typografie */
      --text:       #cce8db;
      --text2:      #7db599;
      --text3:      #4a7a60;
      --font:       'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;

      /* Chat */
      --user-bg:    rgba(0,80,50,0.35);
      --bot-bg:     rgba(11,21,32,0.90);
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    /* ── BODY + HINTERGRUND ─────────────────────────────────────── */
    html, body { height: 100%; }

    body {
      background: var(--bg-base);
      color: var(--text);
      font-family: var(--font);
      font-size: 12.5px;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      position: relative;
    }

    /* Nebel-Gradient-Overlays (Tiefe) */
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background:
        radial-gradient(ellipse 70% 60% at 15% 5%,  rgba(0,160,100,0.07) 0%, transparent 65%),
        radial-gradient(ellipse 50% 40% at 85% 90%, rgba(0,80,180,0.05)  0%, transparent 60%),
        radial-gradient(ellipse 40% 30% at 50% 50%, rgba(0,0,0,0.4)      0%, transparent 80%);
      pointer-events: none;
      z-index: 0;
    }

    /* Dot-Grid (sehr fein, 28px Raster) */
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      background-image: radial-gradient(circle, rgba(0,210,130,0.032) 1px, transparent 1px);
      background-size: 28px 28px;
      pointer-events: none;
      z-index: 0;
    }

    /* Alles über dem Hintergrund */
    .topbar, .shell { position: relative; z-index: 1; }

    /* ── SCROLLBARS ─────────────────────────────────────────────── */
    ::-webkit-scrollbar              { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track        { background: transparent; }
    ::-webkit-scrollbar-thumb        { background: rgba(0,210,130,0.18); border-radius: 99px; }
    ::-webkit-scrollbar-thumb:hover  { background: rgba(0,210,130,0.35); }
    * { scrollbar-width: thin; scrollbar-color: rgba(0,210,130,0.18) transparent; }

    /* ── TOP BAR ────────────────────────────────────────────────── */
    .topbar {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 0 20px;
      height: 46px;
      background: linear-gradient(180deg,
        rgba(10, 20, 32, 0.98) 0%,
        rgba(6, 12, 20, 0.96)  100%);
      border-bottom: 1px solid var(--border);
      box-shadow:
        0 1px 0 rgba(0,210,130,0.05),
        0 4px 20px rgba(0,0,0,0.6);
      flex-shrink: 0;
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      user-select: none;
    }

    /* Timus-Titel mit Shimmer-Gradient */
    .topbar h1 {
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 4px;
      text-transform: uppercase;
      background: linear-gradient(90deg,
        #00e09a 0%, #00d4f0 35%, #a78bfa 55%, #00d4f0 70%, #00e09a 100%);
      background-size: 300% 100%;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      animation: title-shimmer 6s linear infinite;
    }
    @keyframes title-shimmer {
      0%   { background-position: 0%   50%; }
      100% { background-position: 300% 50%; }
    }

    .topbar .spacer { flex: 1; }
    .topbar .poll-info {
      font-size: 10px;
      color: var(--text3);
      letter-spacing: 0.5px;
    }
    .topbar .poll-info span { color: var(--text2); }

    /* Thinking-LED (Topbar) */
    .thinking-led {
      width: 11px; height: 11px;
      border-radius: 50%;
      background: var(--surface3);
      border: 1px solid var(--border);
      flex-shrink: 0;
      transition: all 0.3s;
      position: relative;
    }
    .thinking-led.active {
      background: var(--think);
      border-color: var(--think);
      box-shadow: 0 0 12px var(--think-glow), 0 0 24px rgba(167,139,250,0.1);
      animation: think-pulse 0.9s ease-in-out infinite;
    }
    @keyframes think-pulse {
      0%, 100% { opacity: 1;    box-shadow: 0 0 8px  var(--think-glow); }
      50%       { opacity: 0.3; box-shadow: 0 0 20px var(--think-glow); }
    }
    #thinkingLabel {
      font-size: 10px;
      color: var(--think);
      letter-spacing: 0.8px;
      min-width: 70px;
    }

    /* ── 3-SPALTEN SHELL ─────────────────────────────────────────── */
    .shell {
      display: grid;
      grid-template-columns: 262px 1fr 5px 382px;
      flex: 1;
      overflow: hidden;
      min-height: 0;
    }

    /* ── RESIZE-HANDLE ───────────────────────────────────────────── */
    .resize-handle {
      background: var(--border);
      cursor: col-resize;
      position: relative;
      transition: background 0.2s;
      user-select: none;
      z-index: 10;
    }
    .resize-handle:hover,
    .resize-handle.dragging {
      background: var(--border3);
      box-shadow: 0 0 8px var(--brand-glow);
    }
    .resize-handle::after {
      content: "";
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 1px;
      height: 40px;
      background: linear-gradient(180deg, transparent, var(--brand), transparent);
      border-radius: 999px;
      opacity: 0.5;
    }

    /* ── SIDEBAR ─────────────────────────────────────────────────── */
    .sidebar {
      background: linear-gradient(180deg,
        rgba(11, 21, 33, 0.97) 0%,
        rgba(6,  11, 18, 0.99) 100%);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-right: 1px solid var(--border);
      box-shadow: inset -1px 0 0 var(--brand-dim);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      position: relative;
    }

    /* Leuchtende linke Kante */
    .sidebar::before {
      content: "";
      position: absolute;
      left: 0; top: 0; bottom: 0;
      width: 2px;
      background: linear-gradient(180deg,
        transparent 0%, var(--brand) 30%, var(--cyan) 70%, transparent 100%);
      opacity: 0.35;
      pointer-events: none;
    }

    .sidebar-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 14px 12px;
    }

    /* Abschnitts-Label */
    .section-label {
      font-size: 9.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: var(--text3);
      margin: 18px 0 8px;
      padding: 0 2px 5px;
      border-bottom: 1px solid;
      border-image: linear-gradient(90deg, var(--border2) 0%, transparent 100%) 1;
    }
    .section-label:first-child { margin-top: 2px; }

    /* ── AGENT-REIHEN ─────────────────────────────────────────────── */
    .agent-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 5px 6px;
      border-radius: 7px;
      transition: background 0.2s, box-shadow 0.2s;
      cursor: default;
      position: relative;
    }
    .agent-row:hover {
      background: var(--surface3);
      box-shadow: inset 0 0 0 1px var(--border);
    }

    /* LED */
    .led {
      width: 9px; height: 9px;
      border-radius: 50%;
      flex-shrink: 0;
      position: relative;
      transition: all 0.3s;
    }
    /* Puls-Ring */
    .led::after {
      content: "";
      position: absolute;
      inset: -3px;
      border-radius: 50%;
      border: 1px solid transparent;
      opacity: 0;
    }
    .led.idle      { background: var(--surface4); box-shadow: none; }
    .led.completed {
      background: var(--ok);
      box-shadow: 0 0 6px var(--ok-glow);
    }
    .led.error {
      background: var(--err);
      box-shadow: 0 0 6px var(--err-glow);
    }
    .led.thinking {
      background: var(--think);
      box-shadow: 0 0 8px var(--think-glow), 0 0 16px rgba(167,139,250,0.12);
      animation: led-think 0.8s ease-in-out infinite;
    }
    .led.thinking::after {
      border-color: var(--think);
      animation: led-ring 1.2s cubic-bezier(0,0.5,0.8,1) infinite;
    }
    @keyframes led-think {
      0%,100% { opacity: 1; }
      50%      { opacity: 0.25; }
    }
    @keyframes led-ring {
      0%   { inset: -2px;  opacity: 0.7; }
      100% { inset: -11px; opacity: 0;   }
    }

    .agent-name  { flex: 1; font-size: 11.5px; font-weight: 400; color: var(--text); }
    .agent-model {
      font-size: 8.5px; color: var(--text3);
      max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .agent-st { font-size: 9px; color: var(--text3); min-width: 38px; text-align: right; }

    /* ── TOOL ACTIVITY ───────────────────────────────────────────── */
    .tool-row { display: flex; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 5px; }
    .tool-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--surface4); }
    .tool-dot.running {
      background: var(--warn);
      box-shadow: 0 0 6px var(--warn-glow);
      animation: led-think 0.7s ease-in-out infinite;
    }
    .tool-dot.done { background: var(--ok); box-shadow: 0 0 5px var(--ok-glow); }
    .tool-name-active { color: var(--warn); font-size: 11px; font-weight: 600; }
    .tool-name-done   { color: var(--text3); font-size: 10px; }

    /* ── AUTONOMY SCORE RING (SIDEBAR) ───────────────────────────── */
    .score-ring-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 6px;
      background: linear-gradient(135deg, var(--surface2) 0%, var(--surface) 100%);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow:
        0 4px 16px rgba(0,0,0,0.4),
        inset 0 1px 0 var(--border-dim);
      margin-bottom: 2px;
    }
    .score-ring-svg { flex-shrink: 0; filter: drop-shadow(0 0 6px rgba(0,224,154,0.3)); }
    .score-ring-info { flex: 1; }
    .score-val   { font-size: 22px; font-weight: 700; color: var(--brand); line-height: 1; }
    .score-label { font-size: 8px; color: var(--text3); letter-spacing: 1.5px; text-transform: uppercase; margin-top: 2px; }
    .score-level-txt { font-size: 9px; color: var(--text2); margin-top: 1px; text-transform: uppercase; letter-spacing: 1px; }

    /* ── CANVAS KARTEN (SIDEBAR) ─────────────────────────────────── */
    .canvas-card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 7px 10px;
      background: var(--surface2);
      cursor: pointer;
      margin-bottom: 5px;
      transition: all 0.2s;
    }
    .canvas-card:hover  {
      border-color: var(--border2);
      background: var(--surface3);
      box-shadow: 0 2px 12px rgba(0,0,0,0.3);
    }
    .canvas-card.active {
      border-color: var(--border3);
      background: linear-gradient(135deg, rgba(0,80,50,0.3) 0%, rgba(0,40,30,0.4) 100%);
      box-shadow: 0 0 0 1px var(--brand-dim), 0 4px 16px rgba(0,0,0,0.3);
    }
    .canvas-card .ctitle { font-weight: 600; font-size: 11.5px; color: var(--text); }
    .canvas-card .cmeta  { color: var(--text3); font-size: 9.5px; margin-top: 2px; }

    /* ── BUTTONS & INPUTS ────────────────────────────────────────── */
    button {
      border: 1px solid var(--border2);
      border-radius: 7px;
      font: 600 11.5px var(--font);
      padding: 6px 12px;
      background: linear-gradient(135deg, var(--brand) 0%, var(--brand2) 100%);
      color: #011a0f;
      cursor: pointer;
      transition: all 0.2s;
      white-space: nowrap;
      letter-spacing: 0.3px;
    }
    button:hover {
      box-shadow: 0 0 16px var(--brand-glow), 0 4px 12px rgba(0,0,0,0.3);
      transform: translateY(-1px);
    }
    button:active  { transform: translateY(0); box-shadow: none; }
    button:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }
    button.sec {
      background: linear-gradient(135deg, var(--surface3) 0%, var(--surface2) 100%);
      color: var(--text2);
      border-color: var(--border);
      font-weight: 500;
    }
    button.sec:hover {
      border-color: var(--border2);
      color: var(--text);
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    input {
      border: 1px solid var(--border);
      border-radius: 7px;
      font: 400 11.5px var(--font);
      padding: 6px 9px;
      background: rgba(6,9,14,0.8);
      color: var(--text);
      width: 100%;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    input:focus {
      outline: none;
      border-color: var(--border3);
      box-shadow: 0 0 0 3px var(--brand-dim), 0 0 16px var(--brand-dim);
    }
    input::placeholder { color: var(--text3); }

    .btn-row     { display: flex; gap: 6px; margin-bottom: 7px; }
    .attach-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 6px; }

    /* ── HAUPT-BEREICH (TABS) ────────────────────────────────────── */
    .main-area {
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
      border-right: 1px solid var(--border);
      background: var(--bg-base);
    }

    /* Tab-Leiste */
    .tab-bar {
      display: flex;
      background: linear-gradient(180deg, rgba(11,21,33,0.98) 0%, rgba(8,15,24,0.96) 100%);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
      padding: 0 12px;
      gap: 0;
    }
    .tab-btn {
      padding: 0 20px;
      height: 42px;
      font: 500 10.5px var(--font);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      background: transparent;
      color: var(--text3);
      border: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      cursor: pointer;
      transition: all 0.2s;
      position: relative;
    }
    .tab-btn:hover { color: var(--text2); background: transparent; opacity: 1; transform: none; box-shadow: none; }
    .tab-btn.active {
      color: var(--brand);
      border-bottom-color: var(--brand);
      background: transparent;
      opacity: 1;
      text-shadow: 0 0 12px var(--brand-glow);
    }
    .tab-btn.active::after {
      content: "";
      position: absolute;
      bottom: -1px; left: 20%; right: 20%;
      height: 2px;
      background: linear-gradient(90deg, transparent, var(--brand), transparent);
      filter: blur(2px);
    }

    /* Tab-Inhalte */
    .tab-content { flex: 1; overflow: hidden; display: none; flex-direction: column; min-height: 0; }
    .tab-content.active { display: flex; }

    /* ── CANVAS TAB (Cytoscape) ──────────────────────────────────── */
    #cy-wrap {
      flex: 1;
      min-height: 0;
      position: relative;
      overflow: hidden;
    }
    #cy { position: absolute; inset: 0; background: transparent; }
    #cy-beam-overlay {
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 5;
    }

    .cy-toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 14px;
      background: linear-gradient(180deg, rgba(11,21,33,0.95) 0%, rgba(6,12,20,0.9) 100%);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }
    .cy-toolbar select {
      font: 400 11px var(--font);
      padding: 4px 8px;
      background: var(--surface2);
      color: var(--text2);
      border: 1px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
    }
    .cy-toolbar select:focus { outline: none; border-color: var(--border2); }

    /* Node-Detail-Panel */
    .node-detail {
      position: absolute;
      bottom: 14px; right: 14px;
      background: linear-gradient(135deg, rgba(11,21,35,0.97) 0%, rgba(6,12,22,0.99) 100%);
      backdrop-filter: blur(20px);
      border: 1px solid var(--border3);
      border-radius: 12px;
      padding: 14px 16px;
      font-size: 11px;
      min-width: 220px;
      max-width: 300px;
      z-index: 100;
      display: none;
      box-shadow:
        0 0 0 1px var(--brand-dim),
        0 8px 32px rgba(0,0,0,0.6),
        0 0 40px var(--brand-dim);
    }
    .node-detail.visible { display: block; }
    .node-detail h4 { font-size: 13px; font-weight: 600; color: var(--brand); margin-bottom: 10px; }
    .nd-row { display: flex; justify-content: space-between; gap: 8px; padding: 3px 0; border-bottom: 1px solid var(--border-dim); font-size: 10.5px; }
    .nd-row:last-of-type { border-bottom: none; }
    .nd-key { color: var(--text3); }
    .nd-val { color: var(--text); font-weight: 500; }
    .nd-close { position: absolute; top: 10px; right: 12px; cursor: pointer; color: var(--text3); font-size: 12px; line-height: 1; }
    .nd-close:hover { color: var(--err); }

    /* ── AUTONOMY TAB ────────────────────────────────────────────── */
    .autonomy-view {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
    }
    .auto-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

    /* Glassmorphismus-Karte */
    .auto-card {
      background: linear-gradient(135deg,
        rgba(11,21,33,0.92) 0%,
        rgba(7,14,23,0.96)  100%);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px;
      box-shadow:
        0 0 0 1px var(--brand-dim),
        0 8px 32px rgba(0,0,0,0.5),
        inset 0 1px 0 rgba(255,255,255,0.03);
      transition: border-color 0.3s, box-shadow 0.3s;
    }
    .auto-card:hover {
      border-color: var(--border2);
      box-shadow:
        0 0 0 1px var(--brand-glow),
        0 8px 40px rgba(0,0,0,0.5),
        0 0 30px var(--brand-dim),
        inset 0 1px 0 rgba(0,210,130,0.06);
    }
    .auto-card.full { grid-column: 1 / -1; }
    .auto-card h3 {
      font-size: 9.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: var(--text3);
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }

    /* ── RESEARCH SETTINGS TOGGLES ───────────────────────────────── */
    .toggle-switch { position:relative; display:inline-block; width:40px; height:22px; flex-shrink:0; }
    .toggle-switch input { opacity:0; width:0; height:0; }
    .toggle-slider { position:absolute; cursor:pointer; inset:0; background:#333; border-radius:22px; transition:.25s; }
    .toggle-slider:before { content:""; position:absolute; height:16px; width:16px; left:3px; bottom:3px; background:#888; border-radius:50%; transition:.25s; }
    input:checked + .toggle-slider { background:#ff9d00; }
    input:checked + .toggle-slider:before { background:white; transform:translateX(18px); }
    .setting-row { display:flex; align-items:center; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.04); }
    .setting-row:last-child { border-bottom:none; }
    .setting-info { flex:1; margin-right:12px; }
    .setting-name { font-weight:600; font-size:10pt; color:var(--text1); }
    .setting-desc { font-size:8pt; color:#666; display:block; margin-top:2px; }
    /* Toast */
    .toast { position:fixed; top:16px; right:16px; padding:8px 14px; border-radius:6px;
             font-size:9pt; z-index:9999; animation:toastIn .2s; }
    .toast.ok { background:#1b4332; color:#4ade80; border:1px solid #166534; }
    .toast.error { background:#450a0a; color:#f87171; border:1px solid #7f1d1d; }
    @keyframes toastIn { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:none} }

    /* Scorecard-Header */
    .scorecard-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
    .score-big-wrap { }
    .score-big {
      font-size: 48px;
      font-weight: 700;
      line-height: 1;
      background: linear-gradient(135deg, var(--brand) 0%, var(--cyan) 60%, var(--brand) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      filter: drop-shadow(0 0 20px rgba(0,224,154,0.4));
    }
    .score-denom { font-size: 18px; color: var(--text3); font-weight: 300; }
    .score-ts { font-size: 9px; color: var(--text3); margin-top: 4px; letter-spacing: 0.5px; }

    /* Level-Badge */
    .level-badge {
      padding: 5px 14px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      border: 1px solid;
    }
    .level-badge.low        { color: var(--err);   border-color: var(--err);   background: rgba(244,63,94,0.10); }
    .level-badge.developing { color: var(--warn);  border-color: var(--warn);  background: rgba(251,191,36,0.10); }
    .level-badge.medium     { color: var(--warn);  border-color: var(--warn);  background: rgba(251,191,36,0.10); }
    .level-badge.high       { color: var(--brand); border-color: var(--brand); background: var(--brand-dim); box-shadow: 0 0 12px var(--brand-glow); }
    .level-badge.very_high  { color: var(--cyan);  border-color: var(--cyan);  background: var(--cyan-glow);   box-shadow: 0 0 12px var(--cyan-glow);  }

    /* Pillar-Bars */
    .pillar-bar { margin-bottom: 10px; }
    .pillar-bar-label {
      display: flex;
      justify-content: space-between;
      font-size: 10.5px;
      margin-bottom: 5px;
    }
    .pillar-bar-name  { color: var(--text2); font-weight: 500; }
    .pillar-bar-score { color: var(--text); font-weight: 600; }
    .pillar-bar-track {
      height: 7px;
      background: rgba(0,0,0,0.4);
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--border);
      position: relative;
    }
    .pillar-bar-fill {
      height: 100%;
      border-radius: 999px;
      transition: width 0.8s cubic-bezier(0.34,1.56,0.64,1);
      background: linear-gradient(90deg, var(--brand) 0%, var(--cyan) 50%, var(--brand) 100%);
      background-size: 200% 100%;
      animation: shimmer-bar 2.5s linear infinite;
      position: relative;
    }
    .pillar-bar-fill::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 50%, transparent 100%);
      background-size: 60% 100%;
      animation: shimmer-sweep 2s linear infinite;
    }
    .pillar-bar-fill.warn-fill { background: linear-gradient(90deg, var(--warn) 0%, #fde68a 50%, var(--warn) 100%); }
    .pillar-bar-fill.err-fill  { background: linear-gradient(90deg, var(--err)  0%, #fb7185 50%, var(--err)  100%); }
    @keyframes shimmer-bar   { 0% { background-position: 0%   0; } 100% { background-position: 200% 0; } }
    @keyframes shimmer-sweep { 0% { background-position: -100% 0; } 100% { background-position: 200% 0; } }

    /* Goals */
    .goal-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 0;
      border-bottom: 1px solid var(--border-dim);
      font-size: 11px;
    }
    .goal-row:last-child { border-bottom: none; }
    .goal-prio {
      flex-shrink: 0;
      min-width: 32px;
      text-align: center;
      padding: 2px 5px;
      border-radius: 5px;
      font-size: 9.5px;
      font-weight: 700;
      background: var(--surface3);
      color: var(--text3);
      border: 1px solid var(--border);
    }
    .goal-prio.high-prio { background: rgba(244,63,94,0.12); color: var(--err);   border-color: rgba(244,63,94,0.25); }
    .goal-prio.med-prio  { background: rgba(251,191,36,0.12); color: var(--warn);  border-color: rgba(251,191,36,0.25); }
    .goal-prio.low-prio  { background: var(--brand-dim);       color: var(--brand); border-color: var(--border2); }
    .goal-title   { flex: 1; color: var(--text2); word-break: break-word; line-height: 1.4; }
    .goal-source  {
      flex-shrink: 0;
      font-size: 8.5px;
      color: var(--text3);
      padding: 2px 6px;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--surface);
    }

    /* Healing */
    .degrade-badge {
      display: inline-block; padding: 4px 12px;
      border-radius: 999px; font-size: 10.5px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px; border: 1px solid;
    }
    .degrade-badge.normal     { color: var(--brand); border-color: var(--brand);     background: var(--brand-dim); box-shadow: 0 0 10px var(--brand-glow); }
    .degrade-badge.cautious   { color: var(--warn);  border-color: var(--warn);      background: rgba(251,191,36,0.10); }
    .degrade-badge.restricted { color: #fb923c;      border-color: #fb923c;          background: rgba(251,146,60,0.10); }
    .degrade-badge.emergency  { color: var(--err);   border-color: var(--err);       background: rgba(244,63,94,0.10); box-shadow: 0 0 10px var(--err-glow); }

    .heal-stat { display: flex; justify-content: space-between; font-size: 11px; padding: 5px 0; border-bottom: 1px solid var(--border-dim); }
    .heal-stat:last-child { border-bottom: none; }
    .heal-key { color: var(--text3); }
    .heal-val { font-weight: 600; color: var(--text); }

    /* Allgemein */
    .empty { color: var(--text3); font-style: italic; font-size: 10.5px; padding: 8px 0; }

    /* ── CHAT PANEL ──────────────────────────────────────────────── */
    .chat-panel {
      background: linear-gradient(180deg,
        rgba(8,14,22,0.98) 0%,
        rgba(5,9,14,0.99)  100%);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
      backdrop-filter: blur(20px);
    }

    .chat-header {
      padding: 0 14px;
      height: 42px;
      display: flex;
      align-items: center;
      border-bottom: 1px solid var(--border);
      font-size: 9.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: var(--text3);
      flex-shrink: 0;
      background: linear-gradient(180deg, rgba(11,21,33,0.97) 0%, rgba(7,14,22,0.94) 100%);
    }
    .chat-header span {
      margin-left: auto;
      width: 6px; height: 6px;
      border-radius: 50%;
      background: var(--brand);
      box-shadow: 0 0 8px var(--brand-glow);
      animation: led-think 2s ease-in-out infinite;
    }

    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 14px 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-height: 0;
    }

    /* Chat-Nachrichten-Bubbles */
    .msg {
      max-width: 100%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 12px;
      line-height: 1.65;
      word-break: break-word;
      position: relative;
    }
    .msg.user {
      align-self: flex-end;
      background: linear-gradient(135deg, rgba(0,70,44,0.6) 0%, rgba(0,50,32,0.7) 100%);
      border: 1px solid rgba(0,224,154,0.18);
      box-shadow: 0 2px 12px rgba(0,0,0,0.3), inset 0 1px 0 rgba(0,224,154,0.06);
      white-space: pre-wrap;
    }
    .msg.assistant {
      align-self: flex-start;
      background: linear-gradient(135deg, rgba(11,21,33,0.95) 0%, rgba(7,14,22,0.98) 100%);
      border: 1px solid var(--border);
      box-shadow: 0 2px 12px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.02);
    }
    .msg .msg-who {
      font-size: 9px;
      color: var(--text3);
      margin-bottom: 6px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .msg.user .msg-who   { color: var(--brand2); }
    .msg.assistant .msg-who { color: var(--cyan); }

    /* Markdown-Inhalte */
    .msg-body p      { margin-bottom: 7px; }
    .msg-body p:last-child { margin-bottom: 0; }
    .msg-body ul, .msg-body ol { padding-left: 18px; margin-bottom: 7px; }
    .msg-body li     { margin-bottom: 3px; color: var(--text); }
    .msg-body strong { color: var(--brand); }
    .msg-body em     { color: var(--warn); font-style: italic; }
    .msg-body code {
      background: rgba(0,0,0,0.5);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 1px 6px;
      font-family: var(--font);
      font-size: 10.5px;
      color: var(--cyan);
    }
    .msg-body pre {
      background: rgba(4,7,11,0.95);
      border: 1px solid var(--border2);
      border-radius: 9px;
      padding: 12px;
      overflow-x: auto;
      margin: 8px 0;
      position: relative;
      box-shadow: inset 0 2px 8px rgba(0,0,0,0.4);
    }
    .msg-body pre code { background: none; border: none; padding: 0; font-size: 11px; color: inherit; }
    .msg-body table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 10.5px; }
    .msg-body th, .msg-body td { border: 1px solid var(--border); padding: 5px 10px; }
    .msg-body th { background: var(--surface3); color: var(--text2); font-weight: 600; }
    .msg-body a  { color: var(--brand); text-decoration: underline; text-underline-offset: 2px; }
    .msg-body h1, .msg-body h2, .msg-body h3 {
      color: var(--brand);
      margin: 10px 0 5px;
      font-weight: 600;
    }
    .msg-body blockquote {
      border-left: 2px solid var(--border2);
      padding-left: 10px;
      color: var(--text3);
      margin: 6px 0;
    }

    .msg-thinking {
      align-self: flex-start;
      color: var(--think);
      font-size: 11px;
      padding: 3px 0;
      animation: led-think 1s ease-in-out infinite;
    }

    /* Chat-Input */
    .chat-input-bar {
      display: flex;
      gap: 7px;
      padding: 10px 12px;
      border-top: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(8,15,24,0.97) 0%, rgba(5,9,14,0.99) 100%);
      flex-shrink: 0;
      align-items: flex-end;
    }
    #chatInput {
      flex: 1;
      resize: none;
      min-height: 38px;
      max-height: 120px;
      overflow-y: auto;
      font: 400 12.5px var(--font);
      line-height: 1.5;
      padding: 7px 10px;
      background: rgba(4,7,11,0.9);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    #chatInput:focus {
      outline: none;
      border-color: var(--border3);
      box-shadow: 0 0 0 3px var(--brand-dim);
    }
    #fileInput { display: none; }
    .upload-label {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px; height: 36px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface2);
      color: var(--text3);
      cursor: pointer;
      font-size: 15px;
      flex-shrink: 0;
      transition: all 0.2s;
      user-select: none;
    }
    .upload-label:hover {
      border-color: var(--border3);
      color: var(--brand);
      box-shadow: 0 0 12px var(--brand-dim);
    }

    /* ── MIKROFON-BUTTON ─────────────────────────────────────────── */
    .mic-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px; height: 36px;
      border-radius: 50%;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text3);
      cursor: pointer;
      font-size: 16px;
      flex-shrink: 0;
      transition: all 0.2s;
      user-select: none;
      position: relative;
      padding: 0;
      font-weight: 400;
    }
    .mic-btn:hover {
      border-color: var(--border2);
      color: var(--text);
      transform: none;
      box-shadow: none;
    }
    .mic-btn:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }
    /* Aktiv = hört zu */
    .mic-btn.listening {
      border-color: var(--err);
      color: var(--err);
      background: rgba(244,63,94,0.12);
      box-shadow: 0 0 0 0 rgba(244,63,94,0.5);
      animation: mic-ring 1.4s ease-out infinite;
    }
    /* Äußerer Pulsring */
    .mic-btn.listening::before {
      content: "";
      position: absolute;
      inset: -5px;
      border-radius: 50%;
      border: 1px solid rgba(244,63,94,0.45);
      animation: mic-ring-outer 1.4s ease-out infinite;
    }
    @keyframes mic-ring {
      0%   { box-shadow: 0 0 0 0   rgba(244,63,94,0.55); }
      70%  { box-shadow: 0 0 0 8px rgba(244,63,94,0);    }
      100% { box-shadow: 0 0 0 0   rgba(244,63,94,0);    }
    }
    @keyframes mic-ring-outer {
      0%   { inset: -3px;  opacity: 0.7; }
      100% { inset: -14px; opacity: 0;   }
    }
    /* Transcript-Vorschau über dem Input */
    .mic-transcript {
      position: absolute;
      bottom: calc(100% + 6px);
      left: 0; right: 0;
      padding: 6px 10px;
      background: rgba(6,9,14,0.96);
      border: 1px solid var(--border2);
      border-radius: 8px;
      font-size: 11px;
      color: var(--text2);
      font-style: italic;
      pointer-events: none;
      backdrop-filter: blur(10px);
      display: none;
    }
    .mic-transcript.visible { display: block; }

    /* ── KAMERA TAB ──────────────────────────────────────────────── */
    #tab-kamera { padding: 0; background: #000; }
    .cam-wrap {
      flex: 1; display: flex; flex-direction: column; align-items: center;
      justify-content: center; overflow: hidden; position: relative; gap: 0;
    }
    #camFeed {
      max-width: 100%; max-height: 100%; object-fit: contain;
      border-radius: 0; display: block;
    }
    .cam-offline {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; gap: 12px; color: var(--text3); font-size: 13px;
    }
    .cam-offline svg { opacity: 0.3; }
    .cam-bar {
      flex-shrink: 0; display: flex; align-items: center; gap: 10px;
      padding: 6px 14px; background: rgba(0,0,0,0.7);
      border-top: 1px solid var(--border); font-size: 10px; color: var(--text3);
    }
    .cam-bar .cam-dot { width: 7px; height: 7px; border-radius: 50%; background: #555; }
    .cam-bar .cam-dot.live { background: #22c55e; box-shadow: 0 0 6px #22c55e; animation: pulse-dot 1.5s infinite; }
    @keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.4} }
    .cam-bar button { font-size: 10px; padding: 2px 10px; }

    /* ── VOICE PULSE CANVAS ──────────────────────────────────────── */
    #voiceCanvas {
      position: absolute;
      top: 50%;
      left: 9%;
      transform: translate(-50%, -50%);
      pointer-events: none;
      z-index: 5;
    }

    /* ── RESPONSIVE ──────────────────────────────────────────────── */
    @media (max-width: 1280px) { .shell { grid-template-columns: 225px 1fr 5px 330px; } }
    @media (max-width: 960px)  {
      .shell { grid-template-columns: 1fr; grid-template-rows: auto 1fr 280px; }
      .main-area { border-right: none; }
      .resize-handle { display: none; }
      .chat-panel { border-top: 1px solid var(--border); }
    }
  </style>
</head>
<body>

  <!-- TOP BAR -->
  <div class="topbar">
    <div id="thinkingLed" class="thinking-led" title="Thinking-LED"></div>
    <h1>Timus Canvas</h1>
    <span id="thinkingLabel"></span>
    <div class="spacer"></div>
    <span class="poll-info">
      Poll: <span id="pollState">on</span> · <span id="pollMs">__POLL_MS__</span> ms
    </span>
    <button class="sec" id="togglePollingBtn" style="padding:4px 10px; font-size:10px;">Pause</button>
  </div>

  <div class="shell">

    <!-- ── SIDEBAR ─────────────────────────────────── -->
    <aside class="sidebar">
      <div class="sidebar-scroll">

        <div class="section-label">Agenten</div>
        <div id="agentLeds"></div>

        <div class="section-label">Tools</div>
        <div id="toolActive"></div>
        <div id="toolHistory"></div>

        <div class="section-label">Autonomy</div>
        <div class="score-ring-wrap">
          <svg class="score-ring-svg" width="56" height="56" viewBox="0 0 56 56">
            <!-- Hintergrund-Ring -->
            <circle cx="28" cy="28" r="23" fill="none"
                    stroke="rgba(0,210,130,0.06)" stroke-width="6"/>
            <!-- Dekorativer äußerer Ring -->
            <circle cx="28" cy="28" r="26" fill="none"
                    stroke="rgba(0,210,130,0.04)" stroke-width="1"
                    stroke-dasharray="4 4"/>
            <!-- Haupt-Fortschrittsring -->
            <defs>
              <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%"   stop-color="#00e09a"/>
                <stop offset="50%"  stop-color="#00d4f0"/>
                <stop offset="100%" stop-color="#00e09a"/>
              </linearGradient>
            </defs>
            <circle id="scoreRingFill" cx="28" cy="28" r="23" fill="none"
                    stroke="url(#ringGrad)" stroke-width="6"
                    stroke-dasharray="144.5" stroke-dashoffset="144.5"
                    stroke-linecap="round"
                    transform="rotate(-90 28 28)"
                    style="transition:stroke-dashoffset 0.8s cubic-bezier(0.34,1.56,0.64,1);filter:drop-shadow(0 0 4px rgba(0,224,154,0.5))"/>
          </svg>
          <div class="score-ring-info">
            <div class="score-val" id="sidebarScore">–</div>
            <div class="score-label">Score</div>
            <div class="score-level-txt" id="sidebarLevel">lade…</div>
          </div>
        </div>

        <div class="section-label">Canvas</div>
        <div class="btn-row">
          <button id="createBtn" style="flex:1; font-size:10.5px;">+ Neu</button>
          <button class="sec" id="refreshBtn" style="padding:5px 8px; font-size:11px;" title="Aktualisieren">↺</button>
        </div>
        <div class="attach-grid">
          <input id="attachCanvasId" placeholder="canvas_id" />
          <input id="attachSessionId" placeholder="session_id" />
        </div>
        <div class="btn-row">
          <button class="sec" id="attachBtn" style="flex:1; font-size:10.5px; font-weight:500;">Session verknüpfen</button>
        </div>
        <div id="canvasList"></div>

      </div>
    </aside>

    <!-- ── HAUPT-BEREICH ───────────────────────────── -->
    <div class="main-area">
      <div class="tab-bar">
        <button class="tab-btn active" id="tab-canvas-btn"   onclick="switchTab('canvas')">Canvas</button>
        <button class="tab-btn"        id="tab-autonomy-btn" onclick="switchTab('autonomy')">Autonomy</button>
        <button class="tab-btn"        id="tab-kamera-btn"   onclick="switchTab('kamera')">Kamera</button>
        <button class="tab-btn"        id="tab-flow-btn"     onclick="switchTab('flow')">Flow</button>
      </div>

      <!-- Canvas Tab (position:relative für Voice-Canvas-Overlay) -->
      <div class="tab-content active" id="tab-canvas" style="position:relative;">
        <!-- Voice Pulse Canvas (zentriert, pointer-events:none) -->
        <canvas id="voiceCanvas" width="504" height="504"></canvas>
        <div class="cy-toolbar">
          <span style="color:var(--text3);font-size:10px;letter-spacing:1px;text-transform:uppercase;">Layout</span>
          <select id="cyLayout" onchange="applyCyLayout()">
            <option value="cose">CoSE (auto)</option>
            <option value="circle">Kreis</option>
            <option value="grid">Raster</option>
            <option value="breadthfirst">Baum</option>
          </select>
          <span style="flex:1;"></span>
          <button class="sec" style="font-size:10px;padding:3px 10px;" onclick="fitGraph()">Fit</button>
          <button class="sec" style="font-size:10px;padding:3px 10px;" onclick="reloadGraph()">↺ Reload</button>
        </div>
        <div id="cy-wrap">
          <div id="cy"></div>
          <canvas id="cy-beam-overlay"></canvas>
        </div>
        <div class="node-detail" id="nodeDetail">
          <span class="nd-close" onclick="closeNodeDetail()">✕</span>
          <h4 id="ndTitle">–</h4>
          <div class="nd-row"><span class="nd-key">ID</span>    <span class="nd-val" id="ndId">–</span></div>
          <div class="nd-row"><span class="nd-key">Typ</span>   <span class="nd-val" id="ndType">–</span></div>
          <div class="nd-row"><span class="nd-key">Status</span><span class="nd-val" id="ndStatus">–</span></div>
        </div>
      </div>

      <!-- Kamera Tab -->
      <div class="tab-content" id="tab-kamera">
        <div class="cam-wrap" id="camWrap">
          <!-- Offline-Platzhalter (sichtbar bis Kamera bereit) -->
          <div class="cam-offline" id="camOffline">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
            <span id="camOfflineMsg">Kamera nicht verbunden</span>
            <button class="sec" onclick="camStart()" style="font-size:11px;padding:4px 16px;margin-top:4px;">
              Stream starten
            </button>
          </div>
          <!-- Live-Bild -->
          <img id="camFeed" src="" alt="RealSense Live" style="display:none;"
               onerror="camHandleError()" onload="camHandleLoad()">
        </div>
        <!-- Status-Leiste -->
        <div class="cam-bar">
          <span class="cam-dot" id="camDot"></span>
          <span id="camInfo">–</span>
          <span style="flex:1;"></span>
          <button class="sec" onclick="camStart()" id="camBtnStart">▶ Start</button>
          <button class="sec" onclick="camStop()"  id="camBtnStop" style="display:none;">⏹ Stop</button>
        </div>
      </div>

      <!-- Flow Tab -->
      <div class="tab-content" id="tab-flow" style="position:relative;">
        <div id="flow-cy" style="width:100%;height:100%;"></div>
        <canvas id="flow-beam-overlay" style="position:absolute;top:0;left:0;pointer-events:none;"></canvas>
        <!-- Zoom-Controls -->
        <div style="position:absolute;top:8px;right:8px;z-index:10;display:flex;gap:6px;">
          <button class="sec" style="font-size:12px;padding:3px 10px;" onclick="flowCy&&(flowCy.zoom(flowCy.zoom()*1.3),flowCy.center())">＋</button>
          <button class="sec" style="font-size:12px;padding:3px 10px;" onclick="flowCy&&(flowCy.zoom(flowCy.zoom()*0.77),flowCy.center())">－</button>
          <button class="sec" style="font-size:12px;padding:3px 10px;" onclick="flowCy&&flowCy.fit(40)">⊞ Fit</button>
        </div>
        <!-- Minimap -->
        <div id="flow-minimap" style="position:absolute;bottom:8px;right:8px;width:150px;height:100px;
             border:1px solid #334;background:#0d1117;border-radius:4px;z-index:10;"></div>
      </div>

      <!-- Autonomy Tab -->
      <div class="tab-content" id="tab-autonomy">
        <div class="autonomy-view">

          <!-- Research Settings -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3 style="margin-bottom:8px;">Research Settings</h3>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">ArXiv</span>
                <span class="setting-desc">Wissenschaftliche Paper &middot; kostenlos</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="arxivToggle" onchange="onResearchToggle(this,'DEEP_RESEARCH_ARXIV_ENABLED','ArXiv')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">GitHub</span>
                <span class="setting-desc">Open-Source-Projekte &middot; kostenlos (60 req/h anonym)</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="githubToggle" onchange="onResearchToggle(this,'DEEP_RESEARCH_GITHUB_ENABLED','GitHub')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">HuggingFace</span>
                <span class="setting-desc">KI-Modelle &amp; Daily Papers &middot; kostenlos</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="hfToggle" onchange="onResearchToggle(this,'DEEP_RESEARCH_HF_ENABLED','HuggingFace')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">Edison Scientific (PaperQA3)</span>
                <span class="setting-desc">Wissenschaftliche Literatur &middot; &#9888; 10 Credits/Monat</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="edisonToggle" onchange="onResearchToggle(this,'DEEP_RESEARCH_EDISON_ENABLED','Edison')">
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>

          <!-- Autonomie-Kern -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3 style="margin-bottom:8px;">Autonomie-Kern</h3>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M1 Zielhierarchie</span>
                <span class="setting-desc">Eigenständige Zielgenerierung aus Memory + Curiosity</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="goalsToggle" onchange="onResearchToggle(this,'AUTONOMY_GOALS_ENABLED','M1 Zielhierarchie')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M2 Langzeit-Planung</span>
                <span class="setting-desc">Mehrstufige Aufgabenplanung &uuml;ber mehrere Sessions</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="planningToggle" onchange="onResearchToggle(this,'AUTONOMY_PLANNING_ENABLED','M2 Langzeit-Planung')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M3 Self-Healing</span>
                <span class="setting-desc">Automatische Fehlererkennung und Selbstreparatur</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="healingToggle" onchange="onResearchToggle(this,'AUTONOMY_SELF_HEALING_ENABLED','M3 Self-Healing')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M5 Scorecard</span>
                <span class="setting-desc">Autonomie-Metriken: Aufgaben, Erfolgsrate, Uptime</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="scorecardToggle" onchange="onResearchToggle(this,'AUTONOMY_SCORECARD_ENABLED','M5 Scorecard')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">LLM-Diagnose</span>
                <span class="setting-desc">Ursachenanalyse bei Fehlern per LLM</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="llmDiagToggle" onchange="onResearchToggle(this,'AUTONOMY_LLM_DIAGNOSIS_ENABLED','LLM-Diagnose')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">Meta-Analyse</span>
                <span class="setting-desc">Systemweite Analyse alle 60 Min &mdash; Routing + Tool-Performance</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="metaAnalysisToggle" onchange="onResearchToggle(this,'AUTONOMY_META_ANALYSIS_ENABLED','Meta-Analyse')">
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>

          <!-- Autonomie-Erweiterungen -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3 style="margin-bottom:8px;">Autonomie-Erweiterungen</h3>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M8 Session-Reflexion</span>
                <span class="setting-desc">End-of-Session-Analyse &amp; Verbesserungsvorschl&auml;ge</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="reflectionToggle" onchange="onResearchToggle(this,'AUTONOMY_REFLECTION_ENABLED','M8 Session-Reflexion')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M9 Agent Blackboard</span>
                <span class="setting-desc">Gemeinsamer Kontext-Speicher zwischen Agenten (TTL)</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="blackboardToggle" onchange="onResearchToggle(this,'AUTONOMY_BLACKBOARD_ENABLED','M9 Agent Blackboard')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M10 Proaktive Trigger</span>
                <span class="setting-desc">Zeitgesteuerte Routinen (Morning 08:00 / Evening 20:00)</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="triggersToggle" onchange="onResearchToggle(this,'AUTONOMY_PROACTIVE_TRIGGERS_ENABLED','M10 Proaktive Trigger')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M11 Ziel-Queue</span>
                <span class="setting-desc">Persistente Ziel-Hierarchie mit Fortschritts-Rollup</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="goalQueueToggle" onchange="onResearchToggle(this,'AUTONOMY_GOAL_QUEUE_ENABLED','M11 Ziel-Queue')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M12 Selbstoptimierung</span>
                <span class="setting-desc">Tool-Erfolgsraten &amp; Routing-Konfidenz-Tracking</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="selfImproveToggle" onchange="onResearchToggle(this,'AUTONOMY_SELF_IMPROVEMENT_ENABLED','M12 Selbstoptimierung')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M13 Tool-Generierung</span>
                <span class="setting-desc">Eigene Tools schreiben &amp; per Telegram reviewen</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="m13Toggle" onchange="onResearchToggle(this,'AUTONOMY_M13_ENABLED','M13 Tool-Generierung')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M14 E-Mail-Autonomie</span>
                <span class="setting-desc">Eigenst&auml;ndige E-Mails (Whitelist + Telegram-Freigabe)</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="m14Toggle" onchange="onResearchToggle(this,'AUTONOMY_M14_ENABLED','M14 E-Mail-Autonomie')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M15 Ambient Context</span>
                <span class="setting-desc">Eigeninitiative aus E-Mail / Dateien / Zielen (alle 15 Min)</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="ambientToggle" onchange="onResearchToggle(this,'AUTONOMY_AMBIENT_CONTEXT_ENABLED','M15 Ambient Context')">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-name">M16 Feedback-Lernen</span>
                <span class="setting-desc">&#128077;/&#128078; aus Telegram gewichtet Soul-Hooks um</span>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="m16Toggle" onchange="onResearchToggle(this,'AUTONOMY_M16_ENABLED','M16 Feedback-Lernen')">
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>

          <!-- M8: Session-Reflexion -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3>Session-Reflexion · M8</h3>
            <div id="reflectionPanel"><div class="empty">Lade…</div></div>
          </div>

          <!-- M9: Agent Blackboard -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3>Agent Blackboard · M9</h3>
            <div id="blackboardPanel"><div class="empty">Lade…</div></div>
          </div>

          <!-- M10: Proaktive Trigger -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3>Proaktive Trigger · M10</h3>
            <div id="triggersPanel"><div class="empty">Lade…</div></div>
          </div>

          <!-- M11: Ziel-Hierarchie -->
          <div class="auto-card full" style="margin-bottom:10px;">
            <h3>Ziel-Hierarchie · M11</h3>
            <div id="goalTreePanel" style="min-height:80px;"><div class="empty">Lade…</div></div>
          </div>

          <div class="auto-card full" style="margin-bottom:14px;">
            <h3>Autonomy Scorecard</h3>
            <div class="scorecard-header">
              <div class="score-big-wrap">
                <div>
                  <span class="score-big" id="autoScore">–</span>
                  <span class="score-denom"> / 100</span>
                </div>
                <div class="score-ts" id="autoScoreTS">Lade…</div>
              </div>
              <span class="level-badge" id="autoLevel">–</span>
            </div>
            <div id="pillarBars"></div>
          </div>

          <div class="auto-grid">
            <div class="auto-card">
              <h3>Aktive Ziele · M1</h3>
              <div id="goalsList"><div class="empty">Lade…</div></div>
            </div>
            <div class="auto-card">
              <h3>Self-Healing · M3</h3>
              <div id="healingPanel"><div class="empty">Lade…</div></div>
            </div>
            <div class="auto-card full">
              <h3>Planung · M2</h3>
              <div id="plansPanel"><div class="empty">Lade…</div></div>
            </div>
            <!-- M12: Self-Improvement -->
            <div class="auto-card full">
              <h3>Self-Improvement · M12</h3>
              <div id="improvementPanel"><div class="empty">Lade…</div></div>
            </div>
          </div>

        </div>
      </div>
    </div>

    <!-- ── RESIZE-HANDLE ─────────────────────────── -->
    <div class="resize-handle" id="chatResizeHandle"></div>

    <!-- ── CHAT PANEL ──────────────────────────────── -->
    <div class="chat-panel">
      <div class="chat-header">
        Chat mit Timus
        <span title="Verbunden"></span>
      </div>
      <div id="chatMessages" class="chat-messages">
        <div class="empty">Stelle Timus eine Frage…</div>
      </div>
      <div class="chat-input-bar" style="position:relative;">
        <!-- Transcript-Vorschau (erscheint beim Sprechen) -->
        <div class="mic-transcript" id="micTranscript"></div>
        <textarea id="chatInput" rows="1"
          placeholder="Nachricht… (Enter = Senden, Shift+Enter = Neue Zeile)"></textarea>
        <label class="upload-label" title="Datei hochladen">
          📎
          <input type="file" id="fileInput" />
        </label>
        <!-- Mikrofon-Button -->
        <button class="mic-btn" id="micBtn" title="Mikrofon ein/aus (Deutsch)" disabled>🎤</button>
        <button id="sendBtn">Senden</button>
      </div>
    </div>

  </div><!-- .shell -->

<script>
"use strict";

const POLL_MS = __POLL_MS__;

// ── Markdown-Renderer ─────────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return "";
  try {
    marked.setOptions({
      highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
          try { return hljs.highlight(code, { language: lang }).value; } catch {}
        }
        try { return hljs.highlightAuto(code).value; } catch {}
        return code;
      },
      breaks: true, gfm: true,
    });
    return marked.parse(text);
  } catch { return "<pre>" + esc(text) + "</pre>"; }
}

// ── State ─────────────────────────────────────────────────────────────────────
let selectedCanvasId = "";
let pollingEnabled   = true;
let pollTimer        = null;
let chatSessionId    = "canvas_" + Math.random().toString(36).slice(2, 10);
let isSending        = false;
let activeTool       = null;
let toolHistory      = [];
let agentModels      = {};
let activeTab        = "canvas";
let cy               = null;

// ── Utilities ─────────────────────────────────────────────────────────────────
function esc(v) {
  return String(v ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
async function api(url, opts) {
  const r = await fetch(url, opts || {});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || d.message || r.statusText);
  return d;
}

// ── Tab-Switch ────────────────────────────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById("tab-" + tab).classList.add("active");
  document.getElementById("tab-" + tab + "-btn").classList.add("active");
  if (tab === "autonomy") loadAutonomyData();
  else if (tab === "canvas" && cy) setTimeout(() => cy.fit(), 60);
  else if (tab === "kamera") camCheckStatus();
  else if (tab === "flow") initFlowGraph();
}

// ── Kamera ────────────────────────────────────────────────────────────────────
let camLive = false;

function camCheckStatus() {
  fetch("/camera/status").then(r => r.json()).then(d => {
    if (d.running) {
      camActivate();
    } else {
      camSetOffline(d.last_error || "Kamera nicht verbunden");
    }
  }).catch(() => camSetOffline("Server nicht erreichbar"));
}

function camActivate() {
  camLive = true;
  const feed = document.getElementById("camFeed");
  const offline = document.getElementById("camOffline");
  feed.src = "/camera/stream?" + Date.now();  // Cache-Buster
  feed.style.display = "block";
  offline.style.display = "none";
  document.getElementById("camDot").classList.add("live");
  document.getElementById("camBtnStart").style.display = "none";
  document.getElementById("camBtnStop").style.display  = "";
  camPollStatus();
}

function camSetOffline(msg) {
  camLive = false;
  const feed = document.getElementById("camFeed");
  feed.src = "";
  feed.style.display = "none";
  document.getElementById("camOffline").style.display = "flex";
  document.getElementById("camOfflineMsg").textContent = msg || "Kamera nicht verbunden";
  document.getElementById("camDot").classList.remove("live");
  document.getElementById("camInfo").textContent = "–";
  document.getElementById("camBtnStart").style.display = "";
  document.getElementById("camBtnStop").style.display  = "none";
}

function camHandleLoad() {
  document.getElementById("camInfo").textContent = "Live";
}

function camHandleError() {
  if (camLive) camSetOffline("Stream unterbrochen");
}

function camStart() {
  document.getElementById("camOfflineMsg").textContent = "Verbinde…";
  fetch("/camera/start", {method:"POST"}).then(r => r.json()).then(d => {
    if (d.status === "started" || d.status === "already_running") {
      setTimeout(camActivate, 500);
    } else {
      camSetOffline(d.error || "Start fehlgeschlagen");
    }
  }).catch(e => camSetOffline("Fehler: " + e));
}

function camStop() {
  fetch("/camera/stop", {method:"POST"}).then(() => camSetOffline("Stream gestoppt"));
}

function camPollStatus() {
  if (!camLive || activeTab !== "kamera") return;
  fetch("/camera/status").then(r => r.json()).then(d => {
    if (d.running) {
      const age = d.latest_frame_age_sec != null ? d.latest_frame_age_sec.toFixed(1) + "s" : "–";
      const res = (d.width && d.height) ? d.width + "×" + d.height : "";
      const fps = d.fps ? d.fps + " fps" : "";
      document.getElementById("camInfo").textContent =
        [res, fps, "Frame-Alter: " + age].filter(Boolean).join(" · ");
    } else {
      camSetOffline("Stream nicht mehr aktiv");
      return;
    }
    setTimeout(camPollStatus, 3000);
  }).catch(() => setTimeout(camPollStatus, 5000));
}

// ── Agent LEDs ────────────────────────────────────────────────────────────────
const AGENTS = ["executor","research","reasoning","creative","development","meta","visual",
                "data","document","communication","system","shell","image"];
const PROVIDER_BADGE = {nvidia:"🟢",anthropic:"🔵",openai:"⚪",deepseek:"🟠",inception:"🟣",openrouter:"🔴"};

function renderAgentLeds(agents) {
  const wrap = document.getElementById("agentLeds");
  wrap.innerHTML = "";
  for (const name of AGENTS) {
    const info   = (agents && agents[name]) || { status:"idle", last_query:"" };
    const status = info.status || "idle";
    const minfo  = agentModels[name] || {};
    const badge  = PROVIDER_BADGE[minfo.provider] || "";
    const mshort = minfo.model ? minfo.model.split("/").pop() : "";
    const row    = document.createElement("div");
    row.className = "agent-row";
    row.id        = "agent-row-" + name;
    row.innerHTML =
      `<div class="led ${esc(status)}" id="led-${esc(name)}"></div>` +
      `<span class="agent-name">${esc(name)}</span>` +
      `<span class="agent-model" title="${esc(minfo.model||'')}">${badge} ${esc(mshort)}</span>` +
      `<span class="agent-st" id="ledst-${esc(name)}">${esc(status)}</span>`;
    if (info.last_query) row.title = info.last_query;
    wrap.appendChild(row);
  }
}

function updateAgentLed(agent, status) {
  const led = document.getElementById("led-" + agent);
  if (led) led.className = "led " + status;
  const st = document.getElementById("ledst-" + agent);
  if (st) st.textContent = status;
  updateGraphNodeColor(agent, status);
}

// ── Thinking LED ──────────────────────────────────────────────────────────────
function setThinking(active) {
  const led   = document.getElementById("thinkingLed");
  const label = document.getElementById("thinkingLabel");
  if (active) { led.classList.add("active");    label.textContent = "Denkt…"; }
  else         { led.classList.remove("active"); label.textContent = "";       }
}

// ── Tool Activity ─────────────────────────────────────────────────────────────
function renderToolActivity() {
  const activeEl  = document.getElementById("toolActive");
  const historyEl = document.getElementById("toolHistory");
  activeEl.innerHTML = activeTool
    ? `<div class="tool-row"><div class="tool-dot running"></div><span class="tool-name-active">${esc(activeTool.tool)}</span></div>`
    : `<div class="empty" style="font-size:10px;">Kein Tool aktiv</div>`;
  historyEl.innerHTML = toolHistory.map(t =>
    `<div class="tool-row"><div class="tool-dot done"></div><span class="tool-name-done">${esc(t)}</span></div>`
  ).join("");
}

// ── SSE ───────────────────────────────────────────────────────────────────────
let sseSource = null;
function connectSSE() {
  if (sseSource) return;
  sseSource = new EventSource("/events/stream");
  // window.handleSSE erlaubt nachträgliches Patching durch voicePulse
  sseSource.onmessage = e => { try { (window.handleSSE || handleSSE)(JSON.parse(e.data)); } catch {} };
  sseSource.onerror   = () => { sseSource.close(); sseSource = null; setTimeout(connectSSE, 5000); };
}

function handleSSE(d) {
  if (d.type === "ping") return;
  if (d.type === "init")         { renderAgentLeds(d.agents || {}); setThinking(!!d.thinking); return; }
  if (d.type === "thinking")     { setThinking(!!d.active); return; }
  if (d.type === "agent_status") { updateAgentLed(d.agent, d.status); return; }
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
      `📎 Datei gespeichert: ${d.filename} (${(d.size/1024).toFixed(1)} KB)\nPfad: ${d.path}`);
    return;
  }
  if (d.type === "tool_start") { activeTool = { tool: d.tool, id: d.id }; renderToolActivity(); return; }
  if (d.type === "tool_done") {
    activeTool = null;
    if (d.tool) { toolHistory.unshift(d.tool); if (toolHistory.length > 5) toolHistory.length = 5; }
    renderToolActivity();
    return;
  }
  if (d.type === "autonomy_score") { updateSidebarScore(d.score, d.level); return; }
  if (d.type === "delegation") {
    animateDelegationBeam(d.from, d.to, d.status || "running");
    if (typeof flowCy !== "undefined" && flowCy) animateFlowBeam(d.from, d.to, d.status || "running");
    return;
  }
}

// ── Chat ──────────────────────────────────────────────────────────────────────
function appendChatMsg(role, sender, text) {
  const wrap = document.getElementById("chatMessages");
  const ph   = wrap.querySelector(".empty");
  if (ph) ph.remove();

  const div  = document.createElement("div");
  div.className = "msg " + role;

  const who = document.createElement("div");
  who.className = "msg-who";
  who.textContent = (role === "user" ? "Du" : (sender || "Timus")) + "  ·  " + new Date().toLocaleTimeString();
  div.appendChild(who);

  if (role === "assistant") {
    const body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = renderMarkdown(text);
    div.appendChild(body);
    div.querySelectorAll("pre code").forEach(el => { try { hljs.highlightElement(el); } catch {} });
  } else {
    const body = document.createElement("div");
    body.textContent = text;
    div.appendChild(body);
  }

  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function addChatThinking() {
  const wrap = document.getElementById("chatMessages");
  const div  = document.createElement("div");
  div.className = "msg-thinking"; div.id = "chat-thinking";
  div.textContent = "● Timus denkt…";
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}
function removeChatThinking() { const el = document.getElementById("chat-thinking"); if (el) el.remove(); }

async function sendChat() {
  if (isSending) return;
  const input = document.getElementById("chatInput");
  const query = input.value.trim();
  if (!query) return;
  isSending = true;
  document.getElementById("sendBtn").disabled = true;
  input.value = "";
  input.style.height = "auto";
  appendChatMsg("user", "", query);
  addChatThinking();
  try {
    await fetch("/chat", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, session_id: chatSessionId }),
    });
  } catch (err) {
    removeChatThinking();
    appendChatMsg("assistant", "⚠ Fehler", "Verbindungsfehler: " + err.message);
    isSending = false;
    document.getElementById("sendBtn").disabled = false;
  }
}

async function handleFileUpload(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await api("/upload", { method: "POST", body: fd });
    if (data.status === "success") {
      document.getElementById("chatInput").value = `Analysiere die hochgeladene Datei: ${data.abs_path || data.path}`;
      document.getElementById("chatInput").focus();
    }
  } catch (err) { appendChatMsg("assistant", "⚠ Upload", "Upload fehlgeschlagen: " + err.message); }
}

// ── Score-Ring ────────────────────────────────────────────────────────────────
const RING_CIRC = 2 * Math.PI * 23; // ~144.5

function updateSidebarScore(score, level) {
  const s      = parseFloat(score) || 0;
  const fill   = document.getElementById("scoreRingFill");
  const scoreE = document.getElementById("sidebarScore");
  const levelE = document.getElementById("sidebarLevel");
  if (!fill) return;
  scoreE.textContent = s.toFixed(1);
  levelE.textContent = (level || "–").replace(/_/g, " ");
  fill.setAttribute("stroke-dashoffset", (RING_CIRC - (s/100)*RING_CIRC).toFixed(1));
  const c = s >= 75 ? "#00e09a" : s >= 45 ? "#fbbf24" : "#f43f5e";
  fill.setAttribute("stroke", c);
}

// ── Research Settings + Autonomie-Flags ───────────────────────────────────────
async function loadSettings() {
  try {
    const s = await api("/settings");
    // Deep Research
    document.getElementById("arxivToggle").checked  = s["DEEP_RESEARCH_ARXIV_ENABLED"]  !== "false";
    document.getElementById("githubToggle").checked = s["DEEP_RESEARCH_GITHUB_ENABLED"] !== "false";
    document.getElementById("hfToggle").checked     = s["DEEP_RESEARCH_HF_ENABLED"]     !== "false";
    document.getElementById("edisonToggle").checked = s["DEEP_RESEARCH_EDISON_ENABLED"] === "true";
    // Autonomie-Kern
    document.getElementById("goalsToggle").checked        = s["AUTONOMY_GOALS_ENABLED"]          === "true";
    document.getElementById("planningToggle").checked     = s["AUTONOMY_PLANNING_ENABLED"]        === "true";
    document.getElementById("healingToggle").checked      = s["AUTONOMY_SELF_HEALING_ENABLED"]    === "true";
    document.getElementById("scorecardToggle").checked    = s["AUTONOMY_SCORECARD_ENABLED"]       === "true";
    document.getElementById("llmDiagToggle").checked      = s["AUTONOMY_LLM_DIAGNOSIS_ENABLED"]   === "true";
    document.getElementById("metaAnalysisToggle").checked = s["AUTONOMY_META_ANALYSIS_ENABLED"]   === "true";
    // Autonomie-Erweiterungen
    document.getElementById("reflectionToggle").checked   = s["AUTONOMY_REFLECTION_ENABLED"]         === "true";
    document.getElementById("blackboardToggle").checked   = s["AUTONOMY_BLACKBOARD_ENABLED"]          !== "false";
    document.getElementById("triggersToggle").checked     = s["AUTONOMY_PROACTIVE_TRIGGERS_ENABLED"]  === "true";
    document.getElementById("goalQueueToggle").checked    = s["AUTONOMY_GOAL_QUEUE_ENABLED"]          !== "false";
    document.getElementById("selfImproveToggle").checked  = s["AUTONOMY_SELF_IMPROVEMENT_ENABLED"]    === "true";
    document.getElementById("m13Toggle").checked          = s["AUTONOMY_M13_ENABLED"]                 === "true";
    document.getElementById("m14Toggle").checked          = s["AUTONOMY_M14_ENABLED"]                 === "true";
    document.getElementById("ambientToggle").checked      = s["AUTONOMY_AMBIENT_CONTEXT_ENABLED"]     !== "false";
    document.getElementById("m16Toggle").checked          = s["AUTONOMY_M16_ENABLED"]                 === "true";
  } catch(e) { console.warn("Settings laden fehlgeschlagen:", e); }
}

async function onResearchToggle(el, key, label) {
  const val = el.checked ? "true" : "false";
  try {
    await api("/settings", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ key, value: val }),
    });
    showToast(label + (el.checked ? " aktiviert ✓" : " deaktiviert"));
  } catch(e) {
    el.checked = !el.checked;
    showToast("Fehler: " + e.message, "error");
  }
}

function showToast(msg, type) {
  const t = document.createElement("div");
  t.className = "toast " + (type || "ok");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// ── Autonomy Dashboard ────────────────────────────────────────────────────────
async function loadAutonomyData() {
  await Promise.allSettled([
    loadSettings(), loadScorecard(), loadGoals(), loadPlans(),
    loadReflections(), loadBlackboard(), loadTriggers(), loadGoalTree(), loadImprovement()
  ]);
}

// ── M8: Session-Reflexion ─────────────────────────────────────────────────────
async function loadReflections() {
  const el = document.getElementById("reflectionPanel");
  if (!el) return;
  try {
    const data = await api("/autonomy/reflections?limit=3");
    const refs = data.reflections || [];
    if (!refs.length) { el.innerHTML = '<div class="empty">Noch keine Reflexionen</div>'; return; }
    const latest = refs[0];
    const rate = Math.round((latest.success_rate||0)*100);
    const worked = (latest.what_worked||[]).slice(0,2).join(" · ") || "–";
    const suggestions_data = await api("/autonomy/suggestions");
    const sug = (suggestions_data.suggestions||[]).filter(s=>!s.applied);
    el.innerHTML = `
      <div style="display:flex;gap:16px;flex-wrap:wrap;">
        <div><strong>Letzte Reflexion:</strong> ${(latest.reflected_at||"").substring(0,16).replace("T"," ")}</div>
        <div><strong>Erfolgsrate:</strong> ${rate}%</div>
        <div><strong>Tasks:</strong> ${latest.tasks_count||0}</div>
      </div>
      <div style="margin-top:6px;font-size:12px;opacity:.8">✅ ${worked}</div>
      ${sug.length ? `<div style="margin-top:6px;font-size:12px;color:#f9c;opacity:.9">💡 ${sug[0].suggestion.substring(0,120)}</div>` : ""}
      <div style="margin-top:4px;font-size:11px;opacity:.5">${refs.length} Reflexion(en) gespeichert · ${sug.length} offene Vorschläge</div>
    `;
  } catch(e) { el.innerHTML = `<div class="empty">Fehler: ${e.message}</div>`; }
}

// ── M9: Agent Blackboard ──────────────────────────────────────────────────────
async function loadBlackboard() {
  const el = document.getElementById("blackboardPanel");
  if (!el) return;
  try {
    const data = await api("/blackboard");
    const total = data.total_active || 0;
    const byAgent = data.by_agent || {};
    const last = data.last_entry;
    const agentList = Object.entries(byAgent).slice(0,5).map(([a,n])=>`<span style="margin-right:8px">${a}: <strong>${n}</strong></span>`).join("");
    el.innerHTML = `
      <div style="display:flex;gap:16px;flex-wrap:wrap;">
        <div><strong>Aktive Einträge:</strong> ${total}</div>
        ${last ? `<div><strong>Letzter:</strong> [${last.agent}:${last.topic}] ${last.key}</div>` : ""}
      </div>
      ${agentList ? `<div style="margin-top:6px;font-size:12px;opacity:.8">${agentList}</div>` : ""}
    `;
  } catch(e) { el.innerHTML = `<div class="empty">Fehler: ${e.message}</div>`; }
}

// ── M10: Proaktive Trigger ────────────────────────────────────────────────────
async function loadTriggers() {
  const el = document.getElementById("triggersPanel");
  if (!el) return;
  try {
    const data = await api("/triggers");
    const triggers = data.triggers || [];
    if (!triggers.length) { el.innerHTML = '<div class="empty">Keine Trigger konfiguriert</div>'; return; }
    const rows = triggers.map(t => {
      const lastFired = t.last_fired_at ? t.last_fired_at.substring(0,16).replace("T"," ") : "–";
      const statusColor = t.enabled ? "#4ade80" : "#888";
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05);">
        <div>
          <span style="color:${statusColor};margin-right:8px;">●</span>
          <strong>${t.name}</strong>
          <span style="margin-left:8px;opacity:.6;">${t.time_of_day} · ${t.target_agent}</span>
        </div>
        <div style="font-size:11px;opacity:.5">Letzter: ${lastFired}</div>
      </div>`;
    }).join("");
    el.innerHTML = rows;
  } catch(e) { el.innerHTML = `<div class="empty">Fehler: ${e.message}</div>`; }
}

// ── M11: Ziel-Hierarchie ──────────────────────────────────────────────────────
async function loadGoalTree() {
  const el = document.getElementById("goalTreePanel");
  if (!el) return;
  try {
    const data = await api("/goals/tree");
    const tree = data.tree || [];
    const nodes = tree.filter(e => !e.data?.source);
    if (!nodes.length) { el.innerHTML = '<div class="empty">Keine Ziele definiert</div>'; return; }
    const rows = nodes.slice(0,6).map(n => {
      const d = n.data || {};
      const pct = Math.round((d.progress||0)*100);
      const ms = (d.milestones||[]).length;
      const done = (d.completed_milestones||[]).length;
      return `<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.05);">
        <div style="display:flex;justify-content:space-between;">
          <strong>${d.label||"–"}</strong>
          <span style="font-size:12px;opacity:.7">${pct}%${ms > 0 ? ` · ${done}/${ms} MS` : ""}</span>
        </div>
        <div style="background:rgba(255,255,255,.1);border-radius:3px;height:4px;margin-top:4px;">
          <div style="background:#22d3ee;height:4px;border-radius:3px;width:${pct}%;transition:width .4s;"></div>
        </div>
      </div>`;
    }).join("");
    const edgeCount = tree.filter(e=>e.data?.source).length;
    el.innerHTML = rows + `<div style="margin-top:6px;font-size:11px;opacity:.4">${nodes.length} Ziele · ${edgeCount} Verknüpfungen</div>`;
  } catch(e) { el.innerHTML = `<div class="empty">Fehler: ${e.message}</div>`; }
}

// ── M12: Self-Improvement ─────────────────────────────────────────────────────
async function loadImprovement() {
  const el = document.getElementById("improvementPanel");
  if (!el) return;
  try {
    const data = await api("/autonomy/improvement");
    const sug = data.top_suggestions || [];
    const critical = data.critical_suggestions || 0;
    const statusColor = critical > 0 ? "#f87171" : "#4ade80";
    const rows = sug.slice(0,3).map(s => {
      const emoji = s.severity === "high" ? "🔴" : s.severity === "medium" ? "🟡" : "🟢";
      return `<div style="padding:3px 0;font-size:12px;">${emoji} <strong>${s.target}</strong>: ${(s.finding||"").substring(0,100)}</div>`;
    }).join("");
    el.innerHTML = `
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:6px;">
        <div><strong>Tool-Stats:</strong> ${data.tool_stats_count||0} Einträge</div>
        <div><strong>Routing:</strong> ${data.routing_decisions||0} Entscheidungen</div>
        <div><strong style="color:${statusColor}">Kritisch:</strong> ${critical}</div>
      </div>
      ${rows || '<div style="opacity:.5;font-size:12px;">Noch keine Befunde</div>'}
    `;
  } catch(e) { el.innerHTML = `<div class="empty">Fehler: ${e.message}</div>`; }
}

async function loadScorecard() {
  try {
    const { scorecard: card } = await api("/autonomy/scorecard?window_hours=24");
    if (!card) return;
    const overall = parseFloat(card.overall_score) || 0;
    const level   = card.autonomy_level || "low";

    document.getElementById("autoScore").textContent   = overall.toFixed(1);
    document.getElementById("autoScoreTS").textContent = "Stand: " + (card.timestamp||"–").substring(0,19).replace("T"," ");
    const lv = document.getElementById("autoLevel");
    lv.textContent = level.replace(/_/g," ");
    lv.className   = "level-badge " + level;
    updateSidebarScore(overall, level);

    const pillars  = card.pillars || {};
    const pillarDefs = [
      { key:"goals",        label:"Goals"        },
      { key:"planning",     label:"Planning"     },
      { key:"self_healing", label:"Self-Healing" },
      { key:"policy",       label:"Policy"       },
    ];
    document.getElementById("pillarBars").innerHTML = pillarDefs.map(({ key, label }) => {
      const p   = pillars[key] || {};
      const sc  = parseFloat(p.score) || 0;
      const cls = sc >= 60 ? "" : sc >= 40 ? " warn-fill" : " err-fill";
      return `<div class="pillar-bar">
        <div class="pillar-bar-label">
          <span class="pillar-bar-name">${esc(label)}</span>
          <span class="pillar-bar-score">${sc.toFixed(0)}</span>
        </div>
        <div class="pillar-bar-track">
          <div class="pillar-bar-fill${cls}" style="width:${sc}%"></div>
        </div>
      </div>`;
    }).join("");

    renderHealingPanel(pillars.self_healing || {});
  } catch (e) {
    document.getElementById("pillarBars").innerHTML = `<div class="empty">Nicht verfügbar: ${esc(e.message)}</div>`;
  }
}

async function loadGoals() {
  try {
    const { goals = [] } = await api("/autonomy/goals?status=active&limit=20");
    const el = document.getElementById("goalsList");
    if (!goals.length) { el.innerHTML = '<div class="empty">Keine aktiven Ziele.</div>'; return; }
    el.innerHTML = goals.map(g => {
      const prio = parseFloat(g.priority_score) || 0;
      const cls  = prio >= 70 ? "high-prio" : prio >= 40 ? "med-prio" : "low-prio";
      return `<div class="goal-row">
        <span class="goal-prio ${cls}">${Math.round(prio)}</span>
        <span class="goal-title">${esc(g.title || g.id)}</span>
        <span class="goal-source">${esc(g.source || "–")}</span>
      </div>`;
    }).join("");
  } catch (e) {
    document.getElementById("goalsList").innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`;
  }
}

async function loadPlans() {
  try {
    const { plans = {} } = await api("/autonomy/plans");
    const el = document.getElementById("plansPanel");
    el.innerHTML = [
      ["Aktive Pläne",       plans.active_plans      ?? "–"],
      ["Commitments gesamt", plans.commitments_total  ?? "–"],
      ["Überfällig",         plans.overdue_commitments?? "–"],
      ["Abweichungs-Score",  typeof plans.plan_deviation_score === "number" ? plans.plan_deviation_score.toFixed(2) : "–"],
    ].map(([k,v]) =>
      `<div class="heal-stat"><span class="heal-key">${esc(k)}</span><span class="heal-val">${esc(String(v))}</span></div>`
    ).join("");
  } catch (e) {
    document.getElementById("plansPanel").innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`;
  }
}

function renderHealingPanel(h) {
  const mode = h.degrade_mode || "normal";
  document.getElementById("healingPanel").innerHTML =
    `<div style="margin-bottom:10px;"><span class="degrade-badge ${esc(mode)}">${esc(mode)}</span></div>` +
    [
      ["Incidents offen",  h.open_incidents              ?? "–"],
      ["Escalated",        h.open_escalated_incidents    ?? "–"],
      ["Circuit Breakers", h.circuit_breakers_open       ?? "–"],
      ["Recovery 24h",     typeof h.recovery_rate_24h === "number" ? h.recovery_rate_24h.toFixed(1)+"%" : "–"],
    ].map(([k,v]) =>
      `<div class="heal-stat"><span class="heal-key">${esc(k)}</span><span class="heal-val">${esc(String(v))}</span></div>`
    ).join("");
}

// ── Cytoscape ─────────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  idle:      "#1b2e42",
  thinking:  "#a78bfa",
  completed: "#00e09a",
  error:     "#f43f5e",
  running:   "#00e09a",
};
const STATUS_BORDER = {
  idle:      "#243748",
  thinking:  "#a78bfa",
  completed: "#00e09a",
  error:     "#f43f5e",
  running:   "#00e09a",
};

// Strahlfarben nach Delegations-Status
const BEAM_COLORS = {
  running:   { outer: [255,180,0],   core: [255,215,0],   white: [255,255,200] },
  completed: { outer: [0,200,80],    core: [0,230,100],   white: [200,255,220] },
  error:     { outer: [220,30,30],   core: [255,60,60],   white: [255,200,200] },
};

function initCytoscape() {
  cy = cytoscape({
    container: document.getElementById("cy"),
    style: [
      {
        selector: "node",
        style: {
          "background-color":  "data(bgColor)",
          "border-color":      "data(borderColor)",
          "border-width":      2,
          "label":             "data(label)",
          "color":             "#cce8db",
          "font-family":       "JetBrains Mono, monospace",
          "font-size":         "9.5px",
          "font-weight":       "500",
          "text-valign":       "bottom",
          "text-halign":       "center",
          "text-margin-y":     5,
          "width":             44,
          "height":            44,
          "shadow-blur":       12,
          "shadow-color":      "data(borderColor)",
          "shadow-opacity":    0.45,
          "shadow-offset-x":   0,
          "shadow-offset-y":   0,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#ffffff",
          "border-width": 3,
          "shadow-opacity": 0.7,
        },
      },
      {
        selector: "edge",
        style: {
          "line-color":          "#1b2e42",
          "target-arrow-color":  "#00e09a",
          "target-arrow-shape":  "triangle",
          "curve-style":         "bezier",
          "width":               1.5,
          "opacity":             0.7,
          "label":               "data(label)",
          "font-size":           "8.5px",
          "color":               "#4a7a60",
          "text-rotation":       "autorotate",
          "font-family":         "JetBrains Mono, monospace",
        },
      },
    ],
    layout: { name: "cose", padding: 40, randomize: false, animate: false },
    minZoom: 0.15, maxZoom: 5,
  });

  cy.on("tap", "node", evt => {
    const d = evt.target.data();
    document.getElementById("ndTitle").textContent  = d.label  || d.id  || "–";
    document.getElementById("ndId").textContent     = d.id     || "–";
    document.getElementById("ndType").textContent   = d.type   || "–";
    document.getElementById("ndStatus").textContent = d.status || "–";
    document.getElementById("nodeDetail").classList.add("visible");
  });
  cy.on("tap", evt => { if (evt.target === cy) closeNodeDetail(); });
}

function closeNodeDetail() { document.getElementById("nodeDetail").classList.remove("visible"); }
function applyCyLayout()   {
  if (!cy) return;
  cy.layout({ name: document.getElementById("cyLayout").value, padding: 40, animate: true, animationDuration: 500 }).run();
}
function fitGraph() { if (cy) cy.fit(40); }

function _agentStatusFromLed(name) {
  const led = document.getElementById("led-" + name);
  if (!led) return "idle";
  for (const c of ["thinking","completed","error","running"]) if (led.classList.contains(c)) return c;
  return "idle";
}

function updateGraphNodeColor(agent, status) {
  if (!cy) return;
  const bg  = STATUS_COLOR[status]  || STATUS_COLOR.idle;
  const brd = STATUS_BORDER[status] || STATUS_BORDER.idle;
  // Direkte ID-Suche (Knoten-ID = Agent-Name)
  const idMap = { development: "development", developer: "development" };
  const nodeId = idMap[agent] || agent;
  const node = cy.getElementById(nodeId);
  if (node && node.length) {
    node.data("bgColor",     bg);
    node.data("borderColor", brd);
    node.data("status",      status);
  }
}

// ── 13-Agenten-Kreis ──────────────────────────────────────────────────────────
// Statische Whitelist — nur diese Agenten werden im Canvas-Graph gezeigt.
const REAL_AGENTS_RING = [
  "executor","research","reasoning","creative","development",
  "visual","data","document","communication","system","shell","image",
];

function initAgentCircle() {
  if (!cy) return;
  cy.elements().remove();

  const R = 220; // Radius des Außenrings
  const elements = [];

  // Meta im Mittelpunkt
  elements.push({
    group: "nodes",
    data: {
      id: "meta", label: "meta", agentName: "meta",
      bgColor: "#1a1500", borderColor: "#ffd700",
      type: "agent", status: "idle",
    },
    position: { x: 0, y: 0 },
  });

  // 12 Agenten gleichmäßig auf dem Kreis
  REAL_AGENTS_RING.forEach((name, i) => {
    const angle = (2 * Math.PI * i) / REAL_AGENTS_RING.length - Math.PI / 2;
    elements.push({
      group: "nodes",
      data: {
        id: name, label: name, agentName: name,
        bgColor: "#1b2e42", borderColor: "#243748",
        type: "agent", status: "idle",
      },
      position: { x: Math.cos(angle) * R, y: Math.sin(angle) * R },
    });
  });

  cy.add(elements);
  cy.layout({ name: "preset", padding: 50, animate: false }).run();
  cy.fit(50);
  syncBeamOverlay();
}

function syncBeamOverlay() {
  const overlay = document.getElementById("cy-beam-overlay");
  const wrap    = document.getElementById("cy-wrap");
  if (overlay && wrap) {
    overlay.width  = wrap.clientWidth;
    overlay.height = wrap.clientHeight;
  }
}

// ── Delegation-Lichtstrahl-Animation ──────────────────────────────────────────
let _beamRAF = null;

function animateDelegationBeam(fromId, toId, status) {
  status = status || "running";
  if (!cy) return;

  // Aliases auflösen (z.B. "developer" → "development")
  const idMap = { developer: "development" };
  const src = idMap[fromId] || fromId;
  const tgt = idMap[toId]   || toId;

  const fromNode = cy.getElementById(src);
  const toNode   = cy.getElementById(tgt);
  if (!fromNode.length || !toNode.length) return;

  syncBeamOverlay();
  const overlay = document.getElementById("cy-beam-overlay");
  if (!overlay) return;
  const ctx = overlay.getContext("2d");

  const fromPos = fromNode.renderedPosition();
  const toPos   = toNode.renderedPosition();

  const startTime = performance.now();
  const duration  = 700; // ms

  if (_beamRAF) cancelAnimationFrame(_beamRAF);

  const colors = BEAM_COLORS[status] || BEAM_COLORS.running;
  const [or, og, ob] = colors.outer;
  const [cr, cg, cb] = colors.core;
  const [wr, wg, wb] = colors.white;

  function draw(now) {
    const t  = Math.min((now - startTime) / duration, 1.0);
    const px = fromPos.x + (toPos.x - fromPos.x) * t;
    const py = fromPos.y + (toPos.y - fromPos.y) * t;
    const dx = toPos.x - fromPos.x;
    const dy = toPos.y - fromPos.y;
    const angle = Math.atan2(dy, dx);
    const dist  = Math.hypot(dx, dy);
    const bLen  = Math.max(28, Math.min(60, dist * 0.22));
    const bW    = 5.5;

    ctx.clearRect(0, 0, overlay.width, overlay.height);

    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(angle);

    // Äußere Glut
    const glowGrad = ctx.createLinearGradient(-bLen * 1.4, 0, bLen * 1.4, 0);
    glowGrad.addColorStop(0,   `rgba(${or},${og},${ob},0)`);
    glowGrad.addColorStop(0.4, `rgba(${cr},${cg},${cb},0.35)`);
    glowGrad.addColorStop(0.5, `rgba(${cr},${cg},${cb},0.55)`);
    glowGrad.addColorStop(0.6, `rgba(${cr},${cg},${cb},0.35)`);
    glowGrad.addColorStop(1,   `rgba(${or},${og},${ob},0)`);
    ctx.beginPath();
    ctx.ellipse(0, 0, bLen * 1.4, bW * 2.2, 0, 0, Math.PI * 2);
    ctx.fillStyle = glowGrad;
    ctx.fill();

    // Strahl-Körper
    const beamGrad = ctx.createLinearGradient(-bLen, 0, bLen, 0);
    beamGrad.addColorStop(0,   `rgba(${or},${og},${ob},0)`);
    beamGrad.addColorStop(0.3, `rgba(${cr},${cg},${cb},0.85)`);
    beamGrad.addColorStop(0.5, `rgba(${wr},${wg},${wb},1)`);
    beamGrad.addColorStop(0.7, `rgba(${cr},${cg},${cb},0.85)`);
    beamGrad.addColorStop(1,   `rgba(${or},${og},${ob},0)`);
    ctx.beginPath();
    ctx.ellipse(0, 0, bLen, bW, 0, 0, Math.PI * 2);
    ctx.fillStyle = beamGrad;
    ctx.fill();

    // Heller Kern
    const coreGrad = ctx.createLinearGradient(-bLen * 0.45, 0, bLen * 0.45, 0);
    coreGrad.addColorStop(0,   "rgba(255,255,255,0)");
    coreGrad.addColorStop(0.5, "rgba(255,255,255,0.92)");
    coreGrad.addColorStop(1,   "rgba(255,255,255,0)");
    ctx.beginPath();
    ctx.ellipse(0, 0, bLen * 0.45, bW * 0.32, 0, 0, Math.PI * 2);
    ctx.fillStyle = coreGrad;
    ctx.fill();

    ctx.restore();

    if (t < 1.0) {
      _beamRAF = requestAnimationFrame(draw);
    } else {
      ctx.clearRect(0, 0, overlay.width, overlay.height);
      _beamRAF = null;
      flashNode(tgt, status);
    }
  }

  _beamRAF = requestAnimationFrame(draw);
}

function flashNode(agentId, status) {
  if (!cy) return;
  const node = cy.getElementById(agentId);
  if (!node.length) return;

  const flashColorMap = { running: "#ffd700", completed: "#00e676", error: "#ff1744" };
  const bgColorMap    = { running: "#2a2000",  completed: "#00200d",  error: "#200000"  };
  const col = flashColorMap[status] || flashColorMap.running;
  const bg  = bgColorMap[status]   || bgColorMap.running;

  node.style({
    "border-color":     col,
    "border-width":     5,
    "shadow-color":     col,
    "shadow-opacity":   0.95,
    "shadow-blur":      28,
    "background-color": bg,
  });

  setTimeout(() => {
    const curStatus = node.data("status") || "idle";
    node.style({
      "border-color":     STATUS_BORDER[curStatus] || "#243748",
      "border-width":     2,
      "shadow-color":     STATUS_BORDER[curStatus] || "#243748",
      "shadow-opacity":   0.45,
      "shadow-blur":      12,
      "background-color": STATUS_COLOR[curStatus]  || "#1b2e42",
    });
  }, 600);
}

async function reloadGraph() {
  if (!cy) return;
  // Nur Farben der 13 festen Agenten aktualisieren
  for (const name of ["meta", ...REAL_AGENTS_RING]) {
    const status = _agentStatusFromLed(name);
    updateGraphNodeColor(name, status);
  }
}

// ── Flow-Graph ────────────────────────────────────────────────────────────────
let flowCy = null;
let _flowBeamRAF = null;
let _flowGraphInited = false;

function initFlowGraph() {
  const container = document.getElementById("flow-cy");
  if (!container) return;
  if (_flowGraphInited && flowCy) { flowCy.fit(40); return; }
  _flowGraphInited = true;

  const nodes = [
    // Eingabe-Schicht
    { data: { id: "telegram",  label: "Telegram",        bgColor: "#1b2e42", borderColor: "#243748" } },
    { data: { id: "terminal",  label: "Terminal",         bgColor: "#1b2e42", borderColor: "#243748" } },
    // Dispatcher
    { data: { id: "dispatcher", label: "Dispatcher",      bgColor: "#1b314a", borderColor: "#2a4a6a" } },
    // Meta
    { data: { id: "meta",      label: "MetaAgent",        bgColor: "#1e2a40", borderColor: "#3a5080" } },
    // Executor-Agenten
    { data: { id: "executor",      label: "Executor",     bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "research",      label: "Research",     bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "reasoning",     label: "Reasoning",    bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "creative",      label: "Creative",     bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "development",   label: "Developer",    bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "visual",        label: "Visual",       bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "data",          label: "Data",         bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "communication", label: "Comms",        bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "system",        label: "System",       bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "shell",         label: "Shell",        bgColor: "#152030", borderColor: "#243748" } },
    { data: { id: "image",         label: "Image",        bgColor: "#152030", borderColor: "#243748" } },
    // Autonomie-Runner
    { data: { id: "runner",    label: "AutonomousRunner",  bgColor: "#1a1a35", borderColor: "#3a3a80" } },
    // Autonomie-Motoren
    { data: { id: "m1",        label: "M1 GoalGen",        bgColor: "#0d1a28", borderColor: "#1a3a50" } },
    { data: { id: "m3",        label: "M3 Healing",        bgColor: "#0d1a28", borderColor: "#1a3a50" } },
    { data: { id: "m8",        label: "M8 Reflect",        bgColor: "#0d1a28", borderColor: "#1a3a50" } },
    { data: { id: "m13",       label: "M13 ToolGen",       bgColor: "#0d1a28", borderColor: "#1a3a50" } },
    { data: { id: "m14",       label: "M14 Email",         bgColor: "#0d1a28", borderColor: "#1a3a50" } },
    { data: { id: "m15",       label: "M15 Ambient",       bgColor: "#0d1a28", borderColor: "#1a3a50" } },
    { data: { id: "m16",       label: "M16 Feedback",      bgColor: "#0d1a28", borderColor: "#1a3a50" } },
  ];

  const edges = [
    { data: { id: "e-tg-d",  source: "telegram",  target: "dispatcher" } },
    { data: { id: "e-tr-d",  source: "terminal",  target: "dispatcher" } },
    { data: { id: "e-d-m",   source: "dispatcher", target: "meta" } },
    { data: { id: "e-m-ex",  source: "meta", target: "executor" } },
    { data: { id: "e-m-re",  source: "meta", target: "research" } },
    { data: { id: "e-m-rz",  source: "meta", target: "reasoning" } },
    { data: { id: "e-m-cr",  source: "meta", target: "creative" } },
    { data: { id: "e-m-dv",  source: "meta", target: "development" } },
    { data: { id: "e-m-vi",  source: "meta", target: "visual" } },
    { data: { id: "e-m-da",  source: "meta", target: "data" } },
    { data: { id: "e-m-co",  source: "meta", target: "communication" } },
    { data: { id: "e-m-sy",  source: "meta", target: "system" } },
    { data: { id: "e-m-sh",  source: "meta", target: "shell" } },
    { data: { id: "e-m-im",  source: "meta", target: "image" } },
    { data: { id: "e-r-m1",  source: "runner", target: "m1" } },
    { data: { id: "e-r-m3",  source: "runner", target: "m3" } },
    { data: { id: "e-r-m8",  source: "runner", target: "m8" } },
    { data: { id: "e-r-m13", source: "runner", target: "m13" } },
    { data: { id: "e-r-m14", source: "runner", target: "m14" } },
    { data: { id: "e-r-m15", source: "runner", target: "m15" } },
    { data: { id: "e-r-m16", source: "runner", target: "m16" } },
    { data: { id: "e-m15-d", source: "m15", target: "dispatcher" } },
  ];

  flowCy = cytoscape({
    container,
    userZoomingEnabled: true,
    userPanningEnabled: true,
    elements: { nodes, edges },
    style: [
      {
        selector: "node",
        style: {
          "background-color":  "data(bgColor)",
          "border-color":      "data(borderColor)",
          "border-width":      2,
          "label":             "data(label)",
          "color":             "#cce8db",
          "font-family":       "JetBrains Mono, monospace",
          "font-size":         "9px",
          "font-weight":       "500",
          "text-valign":       "center",
          "text-halign":       "center",
          "width":             65,
          "height":            65,
          "shape":             "roundrectangle",
          "text-wrap":         "wrap",
          "text-max-width":    58,
          "shadow-blur":       10,
          "shadow-color":      "data(borderColor)",
          "shadow-opacity":    0.4,
          "shadow-offset-x":   0,
          "shadow-offset-y":   0,
        },
      },
      {
        selector: "edge",
        style: {
          "line-color":         "#1e3a50",
          "target-arrow-color": "#1e3a50",
          "target-arrow-shape": "triangle",
          "curve-style":        "bezier",
          "width":              1.5,
          "opacity":            0.6,
          "arrow-scale":        0.9,
        },
      },
    ],
    layout: {
      name:     "dagre",
      rankDir:  "LR",
      nodeSep:  35,
      rankSep:  80,
      padding:  30,
    },
  });

  flowCy.fit(40);

  // Minimap initialisieren (falls cytoscape-navigator geladen)
  try {
    if (flowCy.navigator) {
      flowCy.navigator({ container: "#flow-minimap", viewLiveFramerate: 0, thumbnailEventFramerate: 30 });
    }
  } catch (_) {}

  // Sync Flow-Beam-Overlay
  syncFlowBeamOverlay();
  const ro = new ResizeObserver(syncFlowBeamOverlay);
  ro.observe(container);
}

function syncFlowBeamOverlay() {
  const container = document.getElementById("flow-cy");
  const overlay   = document.getElementById("flow-beam-overlay");
  if (!container || !overlay) return;
  const r = container.getBoundingClientRect();
  overlay.width  = r.width;
  overlay.height = r.height;
}

function animateFlowBeam(fromId, toId, status) {
  if (!flowCy) return;
  status = status || "running";

  const idMap = { developer: "development" };
  const src = idMap[fromId] || fromId;
  const tgt = idMap[toId]   || toId;

  const fromNode = flowCy.getElementById(src);
  const toNode   = flowCy.getElementById(tgt);
  if (!fromNode.length || !toNode.length) return;

  syncFlowBeamOverlay();
  const overlay = document.getElementById("flow-beam-overlay");
  if (!overlay) return;
  const ctx = overlay.getContext("2d");

  const fromPos = fromNode.renderedPosition();
  const toPos   = toNode.renderedPosition();

  const startTime = performance.now();
  const duration  = 700;

  if (_flowBeamRAF) cancelAnimationFrame(_flowBeamRAF);

  const colors = BEAM_COLORS[status] || BEAM_COLORS.running;
  const [or, og, ob] = colors.outer;
  const [cr, cg, cb] = colors.core;
  const [wr, wg, wb] = colors.white;

  function draw(now) {
    const t  = Math.min((now - startTime) / duration, 1.0);
    const px = fromPos.x + (toPos.x - fromPos.x) * t;
    const py = fromPos.y + (toPos.y - fromPos.y) * t;
    const dx = toPos.x - fromPos.x;
    const dy = toPos.y - fromPos.y;
    const angle = Math.atan2(dy, dx);
    const dist  = Math.hypot(dx, dy);
    const bLen  = Math.max(22, Math.min(55, dist * 0.22));
    const bW    = 4.5;

    ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(angle);

    const glowGrad = ctx.createLinearGradient(-bLen * 1.4, 0, bLen * 1.4, 0);
    glowGrad.addColorStop(0,   `rgba(${or},${og},${ob},0)`);
    glowGrad.addColorStop(0.4, `rgba(${cr},${cg},${cb},0.35)`);
    glowGrad.addColorStop(0.5, `rgba(${cr},${cg},${cb},0.55)`);
    glowGrad.addColorStop(0.6, `rgba(${cr},${cg},${cb},0.35)`);
    glowGrad.addColorStop(1,   `rgba(${or},${og},${ob},0)`);
    ctx.beginPath();
    ctx.ellipse(0, 0, bLen * 1.4, bW * 2.2, 0, 0, Math.PI * 2);
    ctx.fillStyle = glowGrad;
    ctx.fill();

    const beamGrad = ctx.createLinearGradient(-bLen, 0, bLen, 0);
    beamGrad.addColorStop(0,   `rgba(${or},${og},${ob},0)`);
    beamGrad.addColorStop(0.3, `rgba(${cr},${cg},${cb},0.85)`);
    beamGrad.addColorStop(0.5, `rgba(${wr},${wg},${wb},1)`);
    beamGrad.addColorStop(0.7, `rgba(${cr},${cg},${cb},0.85)`);
    beamGrad.addColorStop(1,   `rgba(${or},${og},${ob},0)`);
    ctx.beginPath();
    ctx.ellipse(0, 0, bLen, bW, 0, 0, Math.PI * 2);
    ctx.fillStyle = beamGrad;
    ctx.fill();

    const coreGrad = ctx.createLinearGradient(-bLen * 0.45, 0, bLen * 0.45, 0);
    coreGrad.addColorStop(0,   "rgba(255,255,255,0)");
    coreGrad.addColorStop(0.5, "rgba(255,255,255,0.92)");
    coreGrad.addColorStop(1,   "rgba(255,255,255,0)");
    ctx.beginPath();
    ctx.ellipse(0, 0, bLen * 0.45, bW * 0.32, 0, 0, Math.PI * 2);
    ctx.fillStyle = coreGrad;
    ctx.fill();

    ctx.restore();

    if (t < 1.0) {
      _flowBeamRAF = requestAnimationFrame(draw);
    } else {
      ctx.clearRect(0, 0, overlay.width, overlay.height);
      _flowBeamRAF = null;
      // Flash-Zielknoten im Flow-Graph
      const node = flowCy.getElementById(tgt);
      if (node.length) {
        const flashColorMap = { running: "#ffd700", completed: "#00e676", error: "#ff1744" };
        const col = flashColorMap[status] || flashColorMap.running;
        node.style({ "border-color": col, "border-width": 4, "shadow-color": col, "shadow-opacity": 0.9, "shadow-blur": 20 });
        setTimeout(() => node.style({ "border-color": node.data("borderColor") || "#243748", "border-width": 2, "shadow-opacity": 0.4, "shadow-blur": 10 }), 600);
      }
    }
  }

  _flowBeamRAF = requestAnimationFrame(draw);
}

// ── Canvas List ───────────────────────────────────────────────────────────────
async function loadCanvasList() {
  const { items = [] } = await api("/canvas?limit=200").catch(() => ({ items: [] }));
  const list = document.getElementById("canvasList");
  list.innerHTML = "";
  if (!items.length) { list.innerHTML = '<div class="empty">Noch kein Canvas.</div>'; selectedCanvasId = ""; return; }
  if (!selectedCanvasId || !items.some(c => c.id === selectedCanvasId)) {
    selectedCanvasId = items[0].id;
    document.getElementById("attachCanvasId").value = selectedCanvasId;
  }
  for (const c of items) {
    const card = document.createElement("div");
    card.className = "canvas-card" + (c.id === selectedCanvasId ? " active" : "");
    card.innerHTML =
      `<div class="ctitle">${esc(c.title)}</div>` +
      `<div class="cmeta">${(c.events||[]).length} Events · ${(c.session_ids||[]).length} Sessions</div>`;
    card.addEventListener("click", () => {
      selectedCanvasId = c.id;
      document.getElementById("attachCanvasId").value = c.id;
      loadCanvasList();
      reloadGraph();
    });
    list.appendChild(card);
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────
let _pollTick = 0;
function setPolling(on) {
  pollingEnabled = Boolean(on);
  document.getElementById("pollState").textContent      = pollingEnabled ? "on" : "pause";
  document.getElementById("togglePollingBtn").textContent = pollingEnabled ? "Pause" : "Resume";
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (pollingEnabled) {
    pollTimer = setInterval(() => {
      _pollTick++;
      loadCanvasList();
      if (activeTab === "canvas") reloadGraph();
      if (_pollTick % Math.ceil(30000/POLL_MS) === 0) loadScorecard().catch(() => {});
    }, POLL_MS);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  document.getElementById("pollMs").textContent = String(POLL_MS);
  renderAgentLeds({});
  renderToolActivity();
  initCytoscape();
  initAgentCircle();

  try { const s = await api("/agent_status"); renderAgentLeds(s.agents||{}); setThinking(!!s.thinking); } catch {}
  try { const m = await api("/agent_models"); if (m.models) { agentModels = m.models; renderAgentLeds({}); } } catch {}
  try {
    const h = await api("/chat/history");
    if ((h.history||[]).length) {
      document.getElementById("chatMessages").innerHTML = "";
      for (const m of h.history) appendChatMsg(m.role||"assistant", m.agent||"Timus", m.text||"");
    }
  } catch {}
  try { await loadScorecard(); } catch {}

  connectSSE();
  await loadCanvasList();
  await reloadGraph();

  // Event-Listener
  document.getElementById("sendBtn").addEventListener("click", sendChat);
  const ci = document.getElementById("chatInput");
  ci.addEventListener("keydown", e => { if (e.key==="Enter"&&!e.shiftKey) { e.preventDefault(); sendChat(); } });
  ci.addEventListener("input",   () => { ci.style.height="auto"; ci.style.height=Math.min(ci.scrollHeight,120)+"px"; });
  document.getElementById("fileInput").addEventListener("change", e => { handleFileUpload(e.target.files[0]); e.target.value=""; });
  document.getElementById("togglePollingBtn").addEventListener("click", () => setPolling(!pollingEnabled));

  document.getElementById("createBtn").addEventListener("click", async () => {
    const title = prompt("Canvas-Titel", "Timus Session");
    if (!title) return;
    try {
      const out = await api("/canvas/create", {
        method:"POST", headers:{"content-type":"application/json"},
        body: JSON.stringify({ title, description:"" }),
      });
      selectedCanvasId = out.canvas.id;
      document.getElementById("attachCanvasId").value = out.canvas.id;
      await loadCanvasList(); await reloadGraph();
    } catch (err) { alert("Fehler: " + err.message); }
  });

  document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadCanvasList(); await reloadGraph();
  });

  document.getElementById("attachBtn").addEventListener("click", async () => {
    const cid = document.getElementById("attachCanvasId").value.trim();
    const sid = document.getElementById("attachSessionId").value.trim();
    if (!cid || !sid) { alert("canvas_id und session_id erforderlich"); return; }
    try {
      await api(`/canvas/${encodeURIComponent(cid)}/attach_session`, {
        method:"POST", headers:{"content-type":"application/json"},
        body: JSON.stringify({ session_id: sid }),
      });
      selectedCanvasId = cid;
      await loadCanvasList(); await reloadGraph();
    } catch (err) { alert("Fehler: " + err.message); }
  });

  setPolling(true);

  // Overlay-Canvas mit cy-wrap synchron halten
  const _cyWrap = document.getElementById("cy-wrap");
  if (_cyWrap && window.ResizeObserver) {
    new ResizeObserver(syncBeamOverlay).observe(_cyWrap);
  }
}

init().catch(err => console.error("Canvas-Init-Fehler:", err));

// ══════════════════════════════════════════════════════════════════
// VOICE PULSE — Stimm-reaktiver Licht-Impuls (Canvas API)
// ══════════════════════════════════════════════════════════════════
(function() {
  const canvas = document.getElementById("voiceCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  // Zustand
  let activity   = 0.08;   // 0 = still, 1 = volle Aktivität
  let speaking   = false;  // Timus spricht gerade
  let thinking   = false;  // Timus denkt gerade
  let rings      = [];     // aktive Ausbreitungsringe
  let frame      = 0;      // Animations-Frame-Zähler
  let noisePhase = 0;      // für organische Wellenform

  // Öffentliche API (wird von SSE-Handler aufgerufen)
  window.voicePulse = {
    startSpeaking(text) {
      speaking  = true;
      // Aktivität proportional zur Textlänge (simuliert Sprechdauer)
      activity  = Math.min(1.0, 0.5 + (text || "").length / 600);
      spawnBurst(4);
      // Automatisch stoppen (grob: 50ms pro Zeichen)
      const dur = Math.max(800, Math.min(8000, (text || "").length * 45));
      clearTimeout(window._voiceSpeakTimer);
      window._voiceSpeakTimer = setTimeout(() => { speaking = false; }, dur);
    },
    startThinking() { thinking = true;  activity = Math.max(activity, 0.35); },
    stopThinking()  { thinking = false; },
    pulse(amount)   { activity = Math.min(1.0, activity + (amount || 0.3)); spawnRing(0.9); },
    // Mikrofon-Eingangspegel (0–1) → Orb reagiert auf Nutzerstimme
    setMicLevel(level) {
      activity = Math.max(activity, level * 0.82);
      if (level > 0.12 && frame % Math.max(1, Math.round(12 / (level + 0.1))) === 0) {
        spawnRing(level * 0.75);
      }
    },
  };

  function spawnRing(opacity) {
    rings.push({
      r:       0,
      opacity: opacity ?? (0.4 + activity * 0.5),
      speed:   1.2 + activity * 3.5 + Math.random() * 1.5,
    });
  }
  function spawnBurst(n) { for (let i = 0; i < n; i++) spawnRing(0.5 + Math.random() * 0.4); }

  // Organische Perlin-ähnliche Noise (einfach, ohne Bibliothek)
  function noise(t, i) {
    return Math.sin(t * 1.7 + i * 2.3) * 0.5 +
           Math.sin(t * 3.1 + i * 1.1) * 0.3 +
           Math.sin(t * 0.9 + i * 4.7) * 0.2;
  }

  function draw() {
    requestAnimationFrame(draw);
    frame++;
    noisePhase += 0.018 + activity * 0.03;

    const W  = canvas.width;
    const H  = canvas.height;
    const cx = W / 2;
    const cy = H / 2;

    ctx.clearRect(0, 0, W, H);

    // ── Aktivität abklingen ───────────────────────────────────────
    if (speaking) {
      activity = Math.max(activity, 0.4 + Math.abs(noise(noisePhase, 0)) * 0.3);
    } else if (thinking) {
      activity = 0.25 + Math.abs(noise(noisePhase * 0.5, 1)) * 0.25;
    } else {
      activity *= 0.988;
      activity  = Math.max(activity, 0.06);
    }

    // ── Heartbeat: Ring alle N Frames ────────────────────────────
    const beatInterval = speaking ? 18 : thinking ? 30 : 80;
    if (frame % beatInterval === 0) spawnRing();

    // ── Ausbreitungs-Ringe ───────────────────────────────────────
    rings = rings.filter(r => r.opacity > 0.008);
    for (const r of rings) {
      r.r      += r.speed * (0.8 + activity * 0.6);
      r.opacity *= 0.965;
      if (r.r > W * 0.85) r.opacity *= 0.90;   // schneller fade am Rand

      const grd = ctx.createRadialGradient(cx, cy, r.r * 0.7, cx, cy, r.r);
      grd.addColorStop(0, `rgba(0,224,154,${r.opacity * 0.55})`);
      grd.addColorStop(0.6, `rgba(0,212,240,${r.opacity * 0.20})`);
      grd.addColorStop(1,   `rgba(0,180,120,0)`);

      ctx.beginPath();
      ctx.arc(cx, cy, r.r, 0, Math.PI * 2);
      ctx.fillStyle = grd;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(cx, cy, r.r, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(0,224,154,${r.opacity * 0.7})`;
      ctx.lineWidth   = 0.8;
      ctx.stroke();
    }

    // ── Organische Wellenform (radiale Strahlen) ─────────────────
    const segments  = 96;
    const baseR     = 28 + activity * 12;
    const waveAmp   = activity * 22;

    ctx.beginPath();
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      const n     = noise(noisePhase + angle * 0.8, i % 16) * waveAmp;
      const r     = baseR + n + Math.sin(noisePhase * 2 + angle * 3) * (waveAmp * 0.3);
      const x     = cx + Math.cos(angle) * r;
      const y     = cy + Math.sin(angle) * r;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = `rgba(0,230,160,${0.25 + activity * 0.55})`;
    ctx.lineWidth   = 1.2;
    ctx.shadowBlur  = 8;
    ctx.shadowColor = "rgba(0,224,154,0.6)";
    ctx.stroke();
    ctx.shadowBlur  = 0;

    // ── Innerer Glow-Halo ────────────────────────────────────────
    const haloR   = baseR * 2.2 + activity * 18;
    const halo    = ctx.createRadialGradient(cx, cy, baseR * 0.5, cx, cy, haloR);
    halo.addColorStop(0,   `rgba(0,255,180,${0.12 + activity * 0.18})`);
    halo.addColorStop(0.5, `rgba(0,224,154,${0.06 + activity * 0.10})`);
    halo.addColorStop(1,   "rgba(0,180,120,0)");
    ctx.beginPath();
    ctx.arc(cx, cy, haloR, 0, Math.PI * 2);
    ctx.fillStyle = halo;
    ctx.fill();

    // ── Zentraler Orb ────────────────────────────────────────────
    const orbR      = baseR + Math.sin(noisePhase * 2.1) * (2 + activity * 4);
    const orbInner  = ctx.createRadialGradient(cx, cy, 0, cx, cy, orbR);
    orbInner.addColorStop(0,   "rgba(210,255,240,0.98)");
    orbInner.addColorStop(0.25, `rgba(0,255,180,${0.90 + activity * 0.10})`);
    orbInner.addColorStop(0.65, `rgba(0,200,140,${0.70 + activity * 0.25})`);
    orbInner.addColorStop(1,   `rgba(0,160,100,${0.50 + activity * 0.40})`);

    ctx.save();
    // Glow-Shadow vor dem Orb
    ctx.shadowBlur  = 18 + activity * 28;
    ctx.shadowColor = `rgba(0,224,154,${0.5 + activity * 0.4})`;
    ctx.beginPath();
    ctx.arc(cx, cy, orbR, 0, Math.PI * 2);
    ctx.fillStyle = orbInner;
    ctx.fill();
    ctx.restore();

    // Glanz-Fleck oben links (Specular)
    const specR   = orbR * 0.35;
    const specGrd = ctx.createRadialGradient(cx - orbR * 0.28, cy - orbR * 0.28, 0,
                                             cx - orbR * 0.28, cy - orbR * 0.28, specR);
    specGrd.addColorStop(0, "rgba(255,255,255,0.55)");
    specGrd.addColorStop(1, "rgba(255,255,255,0)");
    ctx.beginPath();
    ctx.arc(cx - orbR * 0.28, cy - orbR * 0.28, specR, 0, Math.PI * 2);
    ctx.fillStyle = specGrd;
    ctx.fill();
  }

  draw();
})();

// Voice Pulse + Timus Voice System: SSE-Events weiterleiten
const _origHandleSSE = handleSSE;
window.handleSSE = function(d) {
  _origHandleSSE(d);
  // Voice Pulse Orb
  if (window.voicePulse) {
    if (d.type === "thinking")          { d.active ? voicePulse.startThinking() : voicePulse.stopThinking(); }
    if (d.type === "agent_status")      { if (d.status === "thinking") voicePulse.startThinking(); else voicePulse.stopThinking(); }
    if (d.type === "chat_reply")        { voicePulse.startSpeaking(d.text || ""); }
    if (d.type === "tool_start")        { voicePulse.pulse(0.25); }
    if (d.type === "tool_done")         { voicePulse.pulse(0.15); }
    if (d.type === "voice_speaking_start") { voicePulse.startSpeaking(d.text || ""); }
    if (d.type === "voice_speaking_end")   { voicePulse.stopThinking(); }
  }
  // Timus Voice System: Voice-Events an Mic IIFE weiterleiten
  if (window.onVoiceSSE) window.onVoiceSSE(d);
  // Auto-Speak: Wenn Sprach-Modus aktiv, Antwort automatisch vorlesen
  if (d.type === "chat_reply" && window.voiceActive && d.text) {
    fetch("/voice/speak", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: d.text})
    }).catch(() => {});
  }
};

// ══════════════════════════════════════════════════════════════════
// MIKROFON — Timus Voice System (Whisper STT + ElevenLabs TTS)
// ══════════════════════════════════════════════════════════════════
(function() {
  const micBtn     = document.getElementById("micBtn");
  const transcript = document.getElementById("micTranscript");
  const chatInput  = document.getElementById("chatInput");
  if (!micBtn) return;

  micBtn.disabled = false;
  micBtn.title = "Mikrofon ein/aus (Shift+M)";

  // Globaler Sprach-Modus Flag (für SSE-Patch: auto-speak nach chat_reply)
  window.voiceActive = false;

  let listening    = false;
  let micStream    = null;
  let audioCtx     = null;
  let analyser     = null;
  let micAnimFrame = null;

  // ── Pegel-Loop: Web Audio API nur für visuelle Animation ─────────
  function startLevelLoop(stream) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 128;
    analyser.smoothingTimeConstant = 0.75;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    function loop() {
      micAnimFrame = requestAnimationFrame(loop);
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      const level = Math.min(1.0, Math.sqrt(sum / data.length) / 128 * 2.5);
      if (window.voicePulse && level > 0.02) voicePulse.setMicLevel(level);
    }
    loop();
  }

  function stopLevelLoop() {
    if (micAnimFrame) { cancelAnimationFrame(micAnimFrame); micAnimFrame = null; }
    if (analyser)     { try { analyser.disconnect(); } catch {} analyser = null; }
    if (audioCtx)     { audioCtx.close().catch(() => {}); audioCtx = null; }
    if (micStream)    { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (window.voicePulse) voicePulse.setMicLevel(0);
  }

  // ── SSE-Callback für Voice-Events ────────────────────────────────
  window.onVoiceSSE = function(d) {
    if (d.type === "voice_status") {
      transcript.textContent = "⏳ " + (d.message || "…");
      transcript.classList.add("visible");
    }
    if (d.type === "voice_listening_start") {
      transcript.textContent = "● Höre zu…";
      transcript.classList.add("visible");
    }
    if (d.type === "voice_listening_stop") {
      transcript.classList.remove("visible");
    }
    if (d.type === "voice_transcript") {
      stopLevelLoop();
      listening = false;
      micBtn.classList.remove("listening");
      micBtn.title = "Mikrofon ein/aus (Shift+M)";
      if (d.text && d.text.trim()) {
        chatInput.value = d.text.trim();
        chatInput.style.height = "auto";
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
        transcript.textContent = "Erkannt: " + d.text;
        transcript.classList.add("visible");
        // Auto-Submit
        setTimeout(() => {
          const sendBtn = document.getElementById("sendBtn");
          if (sendBtn) sendBtn.click();
          transcript.classList.remove("visible");
        }, 350);
      } else {
        transcript.textContent = "Keine Sprache erkannt.";
        transcript.classList.add("visible");
        setTimeout(() => transcript.classList.remove("visible"), 3000);
      }
    }
    if (d.type === "voice_error") {
      transcript.textContent = "Fehler: " + (d.error || "unbekannt");
      transcript.classList.add("visible");
      setTimeout(() => transcript.classList.remove("visible"), 4000);
      stopLevelLoop();
      listening = false;
      micBtn.classList.remove("listening");
      micBtn.title = "Mikrofon ein/aus (Shift+M)";
    }
    // Nach dem Sprechen: im Sprach-Modus automatisch wieder lauschen
    if (d.type === "voice_speaking_end" && window.voiceActive && !listening) {
      setTimeout(startMic, 900);
    }
  };

  // ── Timus Voice System starten (Whisper STT über Server) ─────────
  async function startMic() {
    if (listening) return;
    listening = true;
    window.voiceActive = true;
    micBtn.classList.add("listening");
    micBtn.title = "Mikrofon aktiv — klicken zum Stoppen";
    transcript.textContent = "● Verbinde…";
    transcript.classList.add("visible");

    // Server-seitig Whisper STT ZUERST starten (Priorität vor Browser-Mikro)
    try {
      const r = await fetch("/voice/listen", { method: "POST" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error((body.error || "HTTP " + r.status));
      }
      // Erfolg: Endpoint hat sofort geantwortet, Ergebnis kommt per SSE
    } catch (err) {
      transcript.textContent = "Mikrofon-Fehler: " + err.message;
      transcript.classList.add("visible");
      setTimeout(() => transcript.classList.remove("visible"), 5000);
      stopLevelLoop();
      listening = false;
      window.voiceActive = false;
      micBtn.classList.remove("listening");
      micBtn.title = "Mikrofon ein/aus (Shift+M)";
      return;
    }

    // Browser-Mikro für visuelle Pegelanzeige (nach Server-Start, nicht exklusiv)
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      startLevelLoop(micStream);
    } catch { /* Pegel-Animation optional — kein showstopper */ }
  }

  function stopMic() {
    if (!listening && !window.voiceActive) return;
    listening = false;
    window.voiceActive = false;
    micBtn.classList.remove("listening");
    micBtn.title = "Mikrofon ein/aus (Shift+M)";
    transcript.classList.remove("visible");
    stopLevelLoop();
    fetch("/voice/stop", { method: "POST" }).catch(() => {});
  }

  micBtn.addEventListener("click", () => {
    if (listening || window.voiceActive) stopMic();
    else startMic();
  });

  // Shift+M Shortcut
  document.addEventListener("keydown", e => {
    if (e.key === "m" && e.shiftKey && document.activeElement !== chatInput) {
      e.preventDefault();
      if (listening || window.voiceActive) stopMic(); else startMic();
    }
  });
})();

// ══════════════════════════════════════════════════════════════════
// RESIZE HANDLE — Chat-Panel horizontal skalierbar
// ══════════════════════════════════════════════════════════════════
(function() {
  const handle    = document.getElementById("chatResizeHandle");
  const shell     = document.querySelector(".shell");
  const chatPanel = document.querySelector(".chat-panel");
  if (!handle || !shell || !chatPanel) return;

  let dragging  = false;
  let startX    = 0;
  let startW    = 0;

  handle.addEventListener("mousedown", e => {
    dragging = true;
    startX   = e.clientX;
    startW   = chatPanel.offsetWidth;
    handle.classList.add("dragging");
    document.body.style.cursor    = "col-resize";
    document.body.style.userSelect = "none";
    e.preventDefault();
  });

  document.addEventListener("mousemove", e => {
    if (!dragging) return;
    const dx      = startX - e.clientX;               // nach links = Chat breiter
    const newW    = Math.max(260, Math.min(700, startW + dx));
    const cols    = getComputedStyle(shell).gridTemplateColumns.split(" ");
    cols[3]       = newW + "px";                       // 4. Spalte (0-indexiert)
    shell.style.gridTemplateColumns = cols.join(" ");
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove("dragging");
    document.body.style.cursor     = "";
    document.body.style.userSelect = "";
  });
})();
</script>
</body>
</html>
"""
