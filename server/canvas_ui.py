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
  <!-- Timus Canvas Live View | Nodes | Edges | Event Timeline | selectedStillExists -->

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
    .live-connection-chip {
      min-height: 26px;
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid rgba(0,212,240,0.16);
      background: rgba(0,212,240,0.06);
      color: var(--text2);
      font-size: 10px;
      letter-spacing: 0.9px;
      text-transform: uppercase;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      flex-shrink: 0;
    }
    .live-connection-chip::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--cyan);
      box-shadow: 0 0 10px rgba(0,212,240,0.22);
    }
    .live-connection-chip.ok {
      border-color: rgba(0,224,154,0.18);
      background: rgba(0,224,154,0.06);
      color: var(--brand);
    }
    .live-connection-chip.ok::before {
      background: var(--brand);
      box-shadow: 0 0 10px rgba(0,224,154,0.24);
    }
    .live-connection-chip.warn {
      border-color: rgba(251,191,36,0.22);
      background: rgba(251,191,36,0.07);
      color: var(--warn);
    }
    .live-connection-chip.warn::before {
      background: var(--warn);
      box-shadow: 0 0 10px rgba(251,191,36,0.24);
    }
    .live-connection-chip.error {
      border-color: rgba(244,63,94,0.24);
      background: rgba(244,63,94,0.08);
      color: var(--err);
    }
    .live-connection-chip.error::before {
      background: var(--err);
      box-shadow: 0 0 10px rgba(244,63,94,0.22);
    }

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

    /* Flow-Architecture-Panel */
    .flow-toolbar {
      position: absolute;
      top: 10px;
      left: 10px;
      right: 10px;
      z-index: 12;
      display: flex;
      align-items: center;
      gap: 10px;
      pointer-events: none;
    }
    .flow-legend, .flow-actions, .flow-hud, .flow-detail {
      pointer-events: auto;
    }
    .flow-legend {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: linear-gradient(135deg, rgba(8,14,24,0.93) 0%, rgba(4,8,14,0.97) 100%);
      box-shadow: 0 8px 28px rgba(0,0,0,0.38);
      backdrop-filter: blur(18px);
    }
    .flow-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 9.5px;
      color: var(--text2);
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.02);
    }
    .flow-chip-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      box-shadow: 0 0 12px currentColor;
    }
    .flow-actions {
      margin-left: auto;
      display: flex;
      gap: 6px;
    }
    .flow-groups {
      display: flex;
      gap: 6px;
      margin-left: 4px;
    }
    .flow-actions button {
      font-size: 10px;
      padding: 4px 10px;
    }
    .flow-group-btn.active {
      border-color: rgba(0,224,154,0.24);
      color: var(--brand);
      box-shadow: 0 0 18px rgba(0,224,154,0.08);
    }
    .flow-group-btn.collapsed {
      border-color: rgba(0,212,240,0.22);
      color: var(--cyan);
      background: rgba(0,212,240,0.07);
    }
    .flow-hud {
      position: absolute;
      top: 56px;
      left: 10px;
      z-index: 12;
      min-width: 270px;
      max-width: 340px;
      padding: 11px 12px;
      border-radius: 12px;
      border: 1px solid rgba(0,212,240,0.14);
      background: linear-gradient(140deg, rgba(7,13,22,0.92) 0%, rgba(5,10,18,0.97) 100%);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.03),
        0 10px 30px rgba(0,0,0,0.42);
      backdrop-filter: blur(16px);
    }
    .flow-hud-title {
      font-size: 10px;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--cyan);
      margin-bottom: 7px;
    }
    .flow-hud-line {
      font-size: 10.5px;
      color: var(--text2);
      line-height: 1.5;
    }
    .flow-hud-line strong { color: var(--text); font-weight: 600; }
    .flow-detail {
      position: absolute;
      right: 14px;
      bottom: 118px;
      z-index: 12;
      display: none;
      min-width: 260px;
      max-width: 340px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--border3);
      background: linear-gradient(135deg, rgba(10,18,29,0.95) 0%, rgba(4,8,15,0.985) 100%);
      box-shadow:
        0 0 0 1px rgba(0,224,154,0.06),
        0 16px 40px rgba(0,0,0,0.6),
        0 0 36px rgba(0,212,240,0.07);
      backdrop-filter: blur(20px);
    }
    .flow-detail.visible { display: block; }
    .flow-detail h4 {
      font-size: 13px;
      color: var(--brand);
      margin-bottom: 10px;
      padding-right: 20px;
      white-space: pre-wrap;
    }
    .fd-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 4px 0;
      border-bottom: 1px solid var(--border-dim);
      font-size: 10.5px;
    }
    .fd-row:last-of-type {
      border-bottom: none;
      padding-bottom: 0;
    }
    .fd-key { color: var(--text3); }
    .fd-val {
      color: var(--text);
      font-weight: 500;
      text-align: right;
      max-width: 180px;
      word-break: break-word;
    }
    .fd-log {
      margin-top: 11px;
      padding: 9px 10px;
      border-radius: 10px;
      border: 1px solid var(--border-dim);
      background: rgba(0,0,0,0.24);
      font-size: 10px;
      line-height: 1.55;
      color: var(--text2);
      max-height: 140px;
      overflow-y: auto;
      white-space: pre-wrap;
    }
    .flow-empty {
      color: var(--text3);
      font-style: italic;
    }
    .flow-group-note {
      margin-top: 8px;
      font-size: 9.5px;
      color: var(--text3);
    }

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

    /* ── MOBILE CONSOLE LAYER ───────────────────────────────────── */
    .mobile-home-hero,
    .mobile-bottom-nav {
      display: none;
    }

    .mobile-home-hero {
      margin: 12px 12px 0;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(0, 224, 154, 0.14);
      background:
        radial-gradient(circle at top left, rgba(0, 224, 154, 0.14), transparent 38%),
        linear-gradient(145deg, rgba(10, 20, 32, 0.96) 0%, rgba(5, 10, 18, 0.98) 100%);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.03),
        0 18px 48px rgba(0,0,0,0.42),
        0 0 24px rgba(0,224,154,0.08);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      flex-shrink: 0;
    }
    .mobile-home-hero .hero-kicker {
      font-size: 9px;
      letter-spacing: 2.2px;
      text-transform: uppercase;
      color: var(--text3);
      margin-bottom: 8px;
    }
    .mobile-hero-top {
      display: flex;
      align-items: center;
      gap: 12px;
      justify-content: space-between;
      margin-bottom: 14px;
    }
    .mobile-session-head {
      min-width: 0;
      flex: 1;
    }
    .mobile-session-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.25;
      margin-bottom: 4px;
    }
    .mobile-session-meta {
      font-size: 11px;
      color: var(--text2);
      line-height: 1.45;
    }
    .mobile-score-orb-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .mobile-score-stack {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .mobile-score-value {
      font-size: 30px;
      line-height: 1;
      font-weight: 700;
      color: var(--brand);
      text-shadow: 0 0 18px rgba(0,224,154,0.24);
    }
    .mobile-score-caption {
      font-size: 10px;
      letter-spacing: 1.6px;
      text-transform: uppercase;
      color: var(--text3);
    }
    .mobile-score-level {
      align-self: flex-start;
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid rgba(0, 224, 154, 0.18);
      background: rgba(0, 224, 154, 0.08);
      font-size: 10px;
      color: var(--text2);
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .mobile-voice-orb {
      width: 62px;
      height: 62px;
      flex-shrink: 0;
      border: 1px solid rgba(0,224,154,0.22);
      border-radius: 50%;
      background:
        radial-gradient(circle at 35% 35%, rgba(210,255,240,0.45) 0%, rgba(0,224,154,0.24) 34%, rgba(0,90,64,0.42) 100%);
      box-shadow:
        0 0 0 1px rgba(0,224,154,0.06),
        0 0 22px rgba(0,224,154,0.22),
        inset 0 0 18px rgba(0,224,154,0.10);
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      cursor: pointer;
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    .mobile-voice-orb:hover {
      transform: translateY(-1px);
      border-color: rgba(0,224,154,0.35);
      box-shadow:
        0 0 0 1px rgba(0,224,154,0.10),
        0 0 28px rgba(0,224,154,0.28),
        inset 0 0 18px rgba(0,224,154,0.14);
    }
    .mobile-voice-orb::before {
      content: "";
      position: absolute;
      inset: -8px;
      border-radius: 50%;
      border: 1px solid rgba(0,224,154,0.18);
      opacity: 0;
      transform: scale(0.88);
    }
    .mobile-voice-orb.listening,
    .mobile-voice-orb.speaking,
    .mobile-voice-orb.thinking {
      animation: mobile-orb-glow 1.5s ease-in-out infinite;
    }
    .mobile-voice-orb.listening::before,
    .mobile-voice-orb.speaking::before,
    .mobile-voice-orb.thinking::before {
      opacity: 1;
      animation: mobile-orb-ring 1.5s ease-out infinite;
    }
    .mobile-voice-orb.listening {
      border-color: rgba(0,224,154,0.55);
      box-shadow: 0 0 30px rgba(0,224,154,0.32), inset 0 0 20px rgba(0,224,154,0.16);
    }
    .mobile-voice-orb.speaking {
      border-color: rgba(0,212,240,0.55);
      box-shadow: 0 0 30px rgba(0,212,240,0.30), inset 0 0 20px rgba(0,212,240,0.14);
    }
    .mobile-voice-orb.thinking {
      border-color: rgba(167,139,250,0.5);
      box-shadow: 0 0 30px rgba(167,139,250,0.24), inset 0 0 20px rgba(167,139,250,0.12);
    }
    .mobile-voice-orb.error {
      border-color: rgba(244,63,94,0.55);
      box-shadow: 0 0 30px rgba(244,63,94,0.24), inset 0 0 20px rgba(244,63,94,0.12);
    }
    @keyframes mobile-orb-glow {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.035); }
    }
    @keyframes mobile-orb-ring {
      0%   { transform: scale(0.88); opacity: 0.62; }
      100% { transform: scale(1.18); opacity: 0; }
    }
    .mobile-quick-pills {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .mobile-hero-actions {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .mobile-hero-action {
      min-height: 38px;
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.02);
      color: var(--text2);
      font-size: 11px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      box-shadow: none;
      transform: none;
    }
    .mobile-hero-action.active {
      border-color: rgba(0,224,154,0.18);
      background: rgba(0,224,154,0.08);
      color: var(--brand);
    }
    .mobile-pill {
      min-height: 48px;
      padding: 9px 10px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: rgba(6, 11, 18, 0.78);
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 3px;
    }
    .mobile-pill-label {
      font-size: 9px;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--text3);
    }
    .mobile-pill-value {
      font-size: 12px;
      color: var(--text);
      font-weight: 600;
      line-height: 1.35;
    }
    .mobile-pill.ok    { border-color: rgba(0,224,154,0.22); box-shadow: inset 0 0 0 1px rgba(0,224,154,0.05); }
    .mobile-pill.warn  { border-color: rgba(251,191,36,0.26); box-shadow: inset 0 0 0 1px rgba(251,191,36,0.06); }
    .mobile-pill.error { border-color: rgba(244,63,94,0.26); box-shadow: inset 0 0 0 1px rgba(244,63,94,0.06); }
    .mobile-pill.info  { border-color: rgba(0,212,240,0.24); box-shadow: inset 0 0 0 1px rgba(0,212,240,0.05); }
    .mobile-status-shell {
      display: none;
    }
    .mobile-files-shell {
      display: none;
      padding: 12px 12px 0;
    }
    .mobile-files-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .mobile-file-action {
      min-height: 46px;
      padding: 9px 10px;
      border-radius: 14px;
      border: 1px solid rgba(0,224,154,0.12);
      background: rgba(255,255,255,0.02);
      color: var(--text);
      text-align: left;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 3px;
    }
    .mobile-file-action .k {
      font-size: 9px;
      color: var(--text3);
      text-transform: uppercase;
      letter-spacing: 1.2px;
    }
    .mobile-file-action .v {
      font-size: 12px;
      font-weight: 600;
      line-height: 1.35;
    }
    .mobile-files-list {
      display: grid;
      gap: 10px;
    }
    .mobile-file-card {
      padding: 12px;
      border-radius: 16px;
      border: 1px solid rgba(0,224,154,0.10);
      background: linear-gradient(145deg, rgba(9,17,28,0.95) 0%, rgba(5,10,18,0.985) 100%);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.02),
        0 14px 26px rgba(0,0,0,0.28);
    }
    .mobile-file-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    .mobile-file-name {
      font-size: 12px;
      color: var(--text);
      font-weight: 600;
      line-height: 1.4;
      word-break: break-word;
    }
    .mobile-file-badge {
      flex-shrink: 0;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text2);
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.03);
    }
    .mobile-file-badge.upload { color: var(--cyan); border-color: rgba(0,212,240,0.18); background: rgba(0,212,240,0.07); }
    .mobile-file-badge.result { color: var(--brand); border-color: rgba(0,224,154,0.18); background: rgba(0,224,154,0.07); }
    .mobile-file-meta {
      font-size: 10px;
      color: var(--text3);
      line-height: 1.5;
      margin-bottom: 10px;
    }
    .mobile-file-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .mobile-file-actions a,
    .mobile-file-actions button {
      min-height: 36px;
      padding: 7px 11px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.02);
      color: var(--text2);
      font-size: 11px;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-shadow: none;
      transform: none;
    }
    .mobile-file-actions a:hover,
    .mobile-file-actions button:hover {
      color: var(--brand);
      border-color: rgba(0,224,154,0.18);
      box-shadow: none;
      transform: none;
    }
    .mobile-status-shell .status-stack {
      display: grid;
      gap: 12px;
      padding: 0 12px 12px;
    }
    .mobile-status-card {
      border-radius: 16px;
      border: 1px solid rgba(0,224,154,0.12);
      background: linear-gradient(145deg, rgba(9,17,28,0.95) 0%, rgba(5,10,18,0.985) 100%);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.02),
        0 14px 30px rgba(0,0,0,0.34);
      padding: 13px 14px;
    }
    .mobile-status-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    .mobile-status-kicker {
      font-size: 9px;
      letter-spacing: 1.7px;
      text-transform: uppercase;
      color: var(--text3);
    }
    .mobile-status-title {
      font-size: 15px;
      color: var(--text);
      font-weight: 600;
      line-height: 1.2;
      margin-top: 3px;
    }
    .mobile-status-badge {
      align-self: flex-start;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 1px;
      border: 1px solid var(--border);
      color: var(--text2);
      background: rgba(255,255,255,0.03);
    }
    .mobile-status-badge.ok { color: var(--brand); border-color: rgba(0,224,154,0.22); background: rgba(0,224,154,0.08); }
    .mobile-status-badge.warn { color: var(--warn); border-color: rgba(251,191,36,0.24); background: rgba(251,191,36,0.08); }
    .mobile-status-badge.error { color: var(--err); border-color: rgba(244,63,94,0.26); background: rgba(244,63,94,0.08); }
    .mobile-status-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .mobile-status-metric {
      padding: 10px 11px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.04);
      background: rgba(255,255,255,0.02);
    }
    .mobile-status-metric .k {
      display: block;
      font-size: 9px;
      color: var(--text3);
      letter-spacing: 1.1px;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .mobile-status-metric .v {
      display: block;
      font-size: 12px;
      color: var(--text);
      line-height: 1.35;
      font-weight: 600;
    }
    .mobile-status-list {
      display: grid;
      gap: 8px;
    }
    .mobile-status-row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      padding: 9px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .mobile-status-row:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }
    .mobile-status-row .name {
      font-size: 12px;
      color: var(--text);
      font-weight: 600;
      line-height: 1.35;
    }
    .mobile-status-row .meta {
      margin-top: 3px;
      font-size: 10px;
      color: var(--text3);
      line-height: 1.45;
    }
    .mobile-status-row .state {
      flex-shrink: 0;
      font-size: 10px;
      color: var(--text2);
      text-transform: uppercase;
      letter-spacing: 0.8px;
      padding: 4px 8px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.03);
    }
    .mobile-status-row .state.ok { color: var(--brand); border-color: rgba(0,224,154,0.18); background: rgba(0,224,154,0.08); }
    .mobile-status-row .state.warn { color: var(--warn); border-color: rgba(251,191,36,0.18); background: rgba(251,191,36,0.08); }
    .mobile-status-row .state.error { color: var(--err); border-color: rgba(244,63,94,0.18); background: rgba(244,63,94,0.08); }
    .mobile-chat-summary {
      display: none;
      padding: 10px 12px;
      gap: 8px;
      background: linear-gradient(180deg, rgba(11,21,33,0.92) 0%, rgba(7,14,22,0.88) 100%);
      border-bottom: 1px solid rgba(0,224,154,0.08);
    }
    .mobile-chat-summary-card {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      width: 100%;
    }
    .mobile-chat-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      width: 100%;
      margin-top: 8px;
    }
    .mobile-chat-chip {
      padding: 9px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.05);
      background: rgba(255,255,255,0.02);
    }
    .mobile-chat-chip .k {
      display: block;
      font-size: 9px;
      color: var(--text3);
      letter-spacing: 1.2px;
      text-transform: uppercase;
      margin-bottom: 3px;
    }
    .mobile-chat-chip .v {
      display: block;
      font-size: 12px;
      color: var(--text);
      line-height: 1.35;
      font-weight: 600;
    }
    .mobile-chat-action {
      min-height: 36px;
      padding: 8px 12px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.02);
      color: var(--text2);
      font-size: 11px;
      letter-spacing: 0.4px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      box-shadow: none;
      transform: none;
    }
    .mobile-chat-action.active {
      color: var(--brand);
      border-color: rgba(0,224,154,0.20);
      background: rgba(0,224,154,0.08);
    }

    .mobile-bottom-nav {
      position: fixed;
      left: 14px;
      right: 14px;
      bottom: calc(12px + env(safe-area-inset-bottom));
      height: 74px;
      padding: 8px 10px;
      border-radius: 24px;
      border: 1px solid rgba(0,224,154,0.14);
      background: linear-gradient(180deg, rgba(8,14,24,0.97) 0%, rgba(5,10,18,0.985) 100%);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.03),
        0 18px 40px rgba(0,0,0,0.5),
        0 0 30px rgba(0,224,154,0.08);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      z-index: 50;
      display: none;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      align-items: center;
    }
    .mobile-nav-btn {
      min-width: 0;
      height: 58px;
      padding: 8px 6px;
      border-radius: 18px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--text3);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      font-size: 10px;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      box-shadow: none;
      transform: none;
    }
    .mobile-nav-btn:hover {
      transform: none;
      box-shadow: none;
      color: var(--text2);
    }
    .mobile-nav-btn .mobile-nav-icon {
      font-size: 18px;
      line-height: 1;
    }
    .mobile-nav-btn.active {
      color: var(--brand);
      border-color: rgba(0,224,154,0.16);
      background: rgba(0,224,154,0.08);
      text-shadow: 0 0 14px rgba(0,224,154,0.18);
    }
    .mobile-nav-btn.voice-nav {
      background: radial-gradient(circle at top, rgba(0,224,154,0.18), rgba(0,120,90,0.08) 70%);
      border-color: rgba(0,224,154,0.18);
      color: var(--text);
    }
    .mobile-nav-btn.voice-nav.active {
      color: var(--brand);
      background: radial-gradient(circle at top, rgba(0,224,154,0.24), rgba(0,120,90,0.1) 72%);
    }
    .mobile-nav-orb {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, rgba(220,255,245,0.95) 0%, rgba(0,224,154,0.8) 45%, rgba(0,140,95,0.9) 100%);
      box-shadow: 0 0 16px rgba(0,224,154,0.30);
    }

    /* ── RESPONSIVE ──────────────────────────────────────────────── */
    @media (max-width: 1280px) { .shell { grid-template-columns: 225px 1fr 5px 330px; } }
    @media (max-width: 960px)  {
      body {
        overflow: hidden;
      }
      .topbar {
        height: 54px;
        padding: 0 14px;
      }
      .topbar h1 {
        font-size: 12px;
        letter-spacing: 3px;
      }
      .topbar .poll-info,
      #togglePollingBtn {
        display: none;
      }
      .shell {
        display: block;
        position: relative;
        flex: 1;
        min-height: 0;
      }
      .sidebar,
      .main-area,
      .chat-panel {
        display: none;
        height: 100%;
        min-height: 0;
      }
      .resize-handle { display: none; }
      body[data-mobile-section="files"] .sidebar { display: block; }
      body[data-mobile-section="home"] .main-area,
      body[data-mobile-section="status"] .main-area { display: flex; }
      body[data-mobile-section="chat"] .chat-panel { display: flex; }
      .sidebar {
        border-right: none;
        background: linear-gradient(180deg, rgba(6,12,20,0.98) 0%, rgba(4,8,14,0.99) 100%);
      }
      .sidebar-scroll {
        padding-bottom: 112px;
      }
      body[data-mobile-section="files"] .mobile-files-shell {
        display: block;
      }
      body[data-mobile-section="files"] .sidebar-scroll > :not(.mobile-files-shell) {
        display: none;
      }
      .main-area {
        border-right: none;
        background: var(--bg-base);
      }
      body[data-mobile-section="status"] .tab-bar {
        display: flex;
      }
      body[data-mobile-section="status"] #tab-canvas-btn,
      body[data-mobile-section="status"] #tab-kamera-btn,
      body[data-mobile-section="status"] #tab-flow-btn {
        display: none;
      }
      body[data-mobile-section="home"] .tab-bar {
        display: none;
      }
      .mobile-home-hero {
        display: block;
      }
      body:not([data-mobile-section="home"]) .mobile-home-hero {
        display: none;
      }
      .tab-bar {
        padding: 0 12px;
        overflow-x: auto;
        overflow-y: hidden;
        gap: 4px;
        scrollbar-width: none;
      }
      .tab-bar::-webkit-scrollbar { display: none; }
      .tab-btn {
        flex: 0 0 auto;
        padding: 0 14px;
        height: 44px;
        font-size: 10px;
      }
      .cy-toolbar {
        padding: 8px 12px;
        gap: 6px;
        overflow-x: auto;
      }
      .cy-toolbar select,
      .cy-toolbar button {
        flex: 0 0 auto;
      }
      #voiceCanvas {
        width: 300px;
        height: 300px;
        left: 50%;
        top: 48%;
        transform: translate(-50%, -50%);
        opacity: 0.85;
      }
      .chat-panel {
        border-top: none;
        background: linear-gradient(180deg, rgba(8,14,22,0.98) 0%, rgba(4,8,14,0.995) 100%);
      }
      .mobile-chat-summary {
        display: flex;
      }
      .chat-header {
        height: 52px;
        padding: 0 16px;
        font-size: 10px;
      }
      .chat-messages {
        padding: 14px 14px 12px;
      }
      .chat-input-bar {
        position: sticky;
        bottom: 0;
        gap: 8px;
        padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
      }
      #chatInput {
        min-height: 42px;
        font-size: 14px;
        padding: 9px 12px;
      }
      .upload-label,
      .mic-btn {
        width: 42px;
        height: 42px;
      }
      .mobile-bottom-nav {
        display: grid;
      }
      .sidebar-scroll,
      .tab-content,
      .chat-messages,
      .autonomy-view {
        padding-bottom: max(100px, calc(88px + env(safe-area-inset-bottom)));
      }
      body[data-mobile-section="status"] .mobile-status-shell {
        display: block;
      }
      body[data-mobile-section="status"] .auto-grid,
      body[data-mobile-section="status"] #triggersPanel,
      body[data-mobile-section="status"] #goalTreePanel,
      body[data-mobile-section="status"] #improvementPanel,
      body[data-mobile-section="status"] #plansPanel,
      body[data-mobile-section="status"] #goalsList,
      body[data-mobile-section="status"] #healingPanel,
      body[data-mobile-section="status"] #apiCostPanel,
      body[data-mobile-section="status"] .scorecard-header,
      body[data-mobile-section="status"] #pillarBars,
      body[data-mobile-section="status"] .setting-row {
        display: none;
      }
      body[data-mobile-section="status"] .auto-card {
        display: none;
      }
      body[data-mobile-section="status"] .autonomy-view {
        padding: 12px 0 0;
      }
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
    <span class="live-connection-chip ok" id="liveConnectionChip">live</span>
    <span class="poll-info">
      Poll: <span id="pollState">on</span> · <span id="pollMs">__POLL_MS__</span> ms
    </span>
    <button class="sec" id="togglePollingBtn" style="padding:4px 10px; font-size:10px;">Pause</button>
  </div>

  <div class="shell">

    <!-- ── SIDEBAR ─────────────────────────────────── -->
    <aside class="sidebar">
      <div class="sidebar-scroll">
        <div class="mobile-files-shell">
          <div class="mobile-status-card" style="margin-bottom:12px;">
            <div class="mobile-status-head">
              <div>
                <div class="mobile-status-kicker">Dateien</div>
                <div class="mobile-status-title">Uploads & Dokumente</div>
              </div>
              <span class="mobile-status-badge" id="mobileFilesBadge">lade…</span>
            </div>
            <div class="mobile-files-actions">
              <button class="mobile-file-action" onclick="triggerMobileUpload()">
                <span class="k">Upload</span>
                <span class="v">Datei hochladen</span>
              </button>
              <button class="mobile-file-action" onclick="setMobileSection('chat')">
                <span class="k">Chat</span>
                <span class="v">Mit Datei arbeiten</span>
              </button>
            </div>
            <div class="mobile-files-list" id="mobileFilesList">
              <div class="empty">Lade…</div>
            </div>
          </div>
        </div>

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
        <div class="mobile-home-hero" id="mobileHomeHero">
          <div class="hero-kicker">Timus Mobile Console</div>
          <div class="mobile-hero-top">
            <div class="mobile-session-head">
              <div class="mobile-session-title" id="mobileSessionTitle">Timus Session Canvas</div>
              <div class="mobile-session-meta" id="mobileSessionMeta">Lade aktuellen Status…</div>
            </div>
          </div>
          <div class="mobile-score-orb-wrap">
            <div class="mobile-score-stack">
              <div class="mobile-score-value" id="mobileAutonomyScore">–</div>
              <div class="mobile-score-caption">Autonomy Score</div>
              <div class="mobile-score-level" id="mobileAutonomyLevel">lade…</div>
            </div>
            <button class="mobile-voice-orb" id="mobileVoiceOrbBtn" title="Voice starten oder stoppen">
              <span class="mobile-nav-orb"></span>
            </button>
          </div>
          <div class="mobile-quick-pills">
            <div class="mobile-pill info" id="mobilePillMcp">
              <span class="mobile-pill-label">MCP</span>
              <span class="mobile-pill-value">lade…</span>
            </div>
            <div class="mobile-pill info" id="mobilePillDispatcher">
              <span class="mobile-pill-label">Dispatcher</span>
              <span class="mobile-pill-value">lade…</span>
            </div>
            <div class="mobile-pill info" id="mobilePillOps">
              <span class="mobile-pill-label">Ops Gate</span>
              <span class="mobile-pill-value">lade…</span>
            </div>
            <div class="mobile-pill info" id="mobilePillBudget">
              <span class="mobile-pill-label">Budget</span>
              <span class="mobile-pill-value">lade…</span>
            </div>
          </div>
          <div class="mobile-hero-actions">
            <button class="mobile-hero-action active" id="mobileHeroRefreshBtn" onclick="refreshMobileOperationalData()">
              Refresh
            </button>
            <button class="mobile-hero-action" id="mobileHeroAlertsBtn" onclick="setMobileSection('status')">
              Alerts
            </button>
            <button class="mobile-hero-action" id="mobileHeroFilesBtn" onclick="setMobileSection('files')">
              Dateien
            </button>
          </div>
        </div>
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
        <div class="flow-toolbar">
          <div class="flow-legend">
            <span class="flow-chip"><span class="flow-chip-dot" style="background:#1d3753;color:#1d3753;"></span>Entry / Dispatch</span>
            <span class="flow-chip"><span class="flow-chip-dot" style="background:#00d4f0;color:#00d4f0;"></span>Running</span>
            <span class="flow-chip"><span class="flow-chip-dot" style="background:#00e09a;color:#00e09a;"></span>Healthy</span>
            <span class="flow-chip"><span class="flow-chip-dot" style="background:#fbbf24;color:#fbbf24;"></span>Warning</span>
            <span class="flow-chip"><span class="flow-chip-dot" style="background:#f43f5e;color:#f43f5e;"></span>Error Hotspot</span>
          </div>
          <div class="flow-actions">
            <button class="sec" onclick="focusFlowErrors()">Focus Errors</button>
            <button class="sec" onclick="reloadFlowRuntime()">↺ Runtime</button>
            <button class="sec" onclick="flowCy&&flowCy.fit(60)">⊞ Fit</button>
          </div>
          <div class="flow-groups">
            <button class="sec flow-group-btn active" id="flowGroupBtn-voice" onclick="toggleFlowGroup('voice')">Voice</button>
            <button class="sec flow-group-btn active" id="flowGroupBtn-memory" onclick="toggleFlowGroup('memory')">Memory</button>
            <button class="sec flow-group-btn active" id="flowGroupBtn-autonomy" onclick="toggleFlowGroup('autonomy')">Autonomy</button>
          </div>
        </div>
        <div class="flow-hud" id="flowHud">
          <div class="flow-hud-title">Architecture Runtime</div>
          <div class="flow-hud-line" id="flowHudCounts">Knoten: – · Aktiv: – · Fehler: –</div>
          <div class="flow-hud-line" id="flowHudLast">Noch keine Laufzeitdaten.</div>
          <div class="flow-group-note" id="flowHudGroups">Gruppen: Voice offen · Memory offen · Autonomy offen</div>
        </div>
        <div id="flow-cy" style="width:100%;height:100%;"></div>
        <canvas id="flow-beam-overlay" style="position:absolute;top:0;left:0;pointer-events:none;"></canvas>
        <div id="flow-minimap" style="position:absolute;bottom:8px;right:8px;width:150px;height:100px;
             border:1px solid #334;background:#0d1117;border-radius:4px;z-index:10;"></div>
        <div class="flow-detail" id="flowDetail">
          <span class="nd-close" onclick="closeFlowDetail()">✕</span>
          <h4 id="fdTitle">–</h4>
          <div class="fd-row"><span class="fd-key">ID</span><span class="fd-val" id="fdId">–</span></div>
          <div class="fd-row"><span class="fd-key">Layer</span><span class="fd-val" id="fdLayer">–</span></div>
          <div class="fd-row"><span class="fd-key">Status</span><span class="fd-val" id="fdStatus">–</span></div>
          <div class="fd-row"><span class="fd-key">Quelle</span><span class="fd-val" id="fdSource">–</span></div>
          <div class="fd-row"><span class="fd-key">Update</span><span class="fd-val" id="fdUpdated">–</span></div>
          <div class="fd-log" id="fdMessage"><span class="flow-empty">Kein Laufzeitereignis.</span></div>
        </div>
      </div>

      <!-- Autonomy Tab -->
      <div class="tab-content" id="tab-autonomy">
        <div class="autonomy-view">
          <div class="mobile-status-shell">
            <div class="status-stack">
              <section class="mobile-status-card">
                <div class="mobile-status-head">
                  <div>
                    <div class="mobile-status-kicker">Operations</div>
                    <div class="mobile-status-title">Systemstatus</div>
                  </div>
                  <span class="mobile-status-badge" id="mobileStatusBadge">lade…</span>
                </div>
                <div class="mobile-status-grid">
                  <div class="mobile-status-metric">
                    <span class="k">MCP</span>
                    <span class="v" id="mobileStatusMcp">lade…</span>
                  </div>
                  <div class="mobile-status-metric">
                    <span class="k">Dispatcher</span>
                    <span class="v" id="mobileStatusDispatcher">lade…</span>
                  </div>
                  <div class="mobile-status-metric">
                    <span class="k">Ops Gate</span>
                    <span class="v" id="mobileStatusOpsGate">lade…</span>
                  </div>
                  <div class="mobile-status-metric">
                    <span class="k">Stability</span>
                    <span class="v" id="mobileStatusStability">lade…</span>
                  </div>
                </div>
              </section>

              <section class="mobile-status-card">
                <div class="mobile-status-head">
                  <div>
                    <div class="mobile-status-kicker">Incidents</div>
                    <div class="mobile-status-title">Self-Healing</div>
                  </div>
                  <span class="mobile-status-badge" id="mobileHealingBadge">lade…</span>
                </div>
                <div class="mobile-status-list" id="mobileIncidentList">
                  <div class="empty">Lade…</div>
                </div>
              </section>

              <section class="mobile-status-card">
                <div class="mobile-status-head">
                  <div>
                    <div class="mobile-status-kicker">Modelle</div>
                    <div class="mobile-status-title">Agenten</div>
                  </div>
                  <span class="mobile-status-badge" id="mobileAgentsBadge">13 Rollen</span>
                </div>
                <div class="mobile-status-list" id="mobileAgentList">
                  <div class="empty">Lade…</div>
                </div>
              </section>
            </div>
          </div>

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

          <div class="auto-card full" style="margin-bottom:14px;">
            <h3>API &amp; Kostenkontrolle</h3>
            <div id="apiCostPanel"><div class="empty">Lade…</div></div>
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
      <div class="mobile-chat-summary">
        <div class="mobile-chat-summary-card">
          <div class="mobile-chat-chip">
            <span class="k">Session</span>
            <span class="v" id="mobileChatSession">lade…</span>
          </div>
          <div class="mobile-chat-chip">
            <span class="k">Voice</span>
            <span class="v" id="mobileChatVoice">bereit</span>
          </div>
        </div>
        <div class="mobile-chat-summary-card">
          <div class="mobile-chat-chip">
            <span class="k">Stimme</span>
            <span class="v" id="mobileVoiceName">lade…</span>
          </div>
          <div class="mobile-chat-chip">
            <span class="k">Playback</span>
            <span class="v" id="mobileVoicePlayback">browser</span>
          </div>
        </div>
        <div class="mobile-chat-actions">
          <button class="mobile-chat-action active" id="mobileVoiceAutoBtn" onclick="toggleVoiceAutoReply()">
            Auto-Vorlesen
          </button>
          <button class="mobile-chat-action" id="mobileVoiceReplayBtn" onclick="replayLastVoiceReply()">
            Letzte Antwort
          </button>
        </div>
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
      <audio id="voicePlayer" preload="none"></audio>
    </div>

  </div><!-- .shell -->

  <nav class="mobile-bottom-nav" aria-label="Timus Mobile Navigation">
    <button class="mobile-nav-btn active" id="mobileNav-home" onclick="setMobileSection('home')">
      <span class="mobile-nav-icon">⌂</span>
      <span>Home</span>
    </button>
    <button class="mobile-nav-btn" id="mobileNav-status" onclick="setMobileSection('status')">
      <span class="mobile-nav-icon">◎</span>
      <span>Status</span>
    </button>
    <button class="mobile-nav-btn voice-nav" id="mobileNav-voice" onclick="toggleMobileVoice()">
      <span class="mobile-nav-orb"></span>
      <span>Voice</span>
    </button>
    <button class="mobile-nav-btn" id="mobileNav-chat" onclick="setMobileSection('chat')">
      <span class="mobile-nav-icon">◫</span>
      <span>Chat</span>
    </button>
    <button class="mobile-nav-btn" id="mobileNav-files" onclick="setMobileSection('files')">
      <span class="mobile-nav-icon">⌘</span>
      <span>Dateien</span>
    </button>
  </nav>

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
let mobileSection    = "home";
let lastStatusSnapshot = null;
let lastCanvasItems    = [];
let mobileVoiceState   = "idle";
let lastRecentFiles    = [];
let voiceAutoReply     = true;
let lastVoiceReplyText = "";
let lastVoiceAudioUrl  = "";
let sseConnected       = false;
let sseReconnectTimer  = null;

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

function isMobileLayout() {
  return window.matchMedia("(max-width: 960px)").matches;
}

function setMobilePill(id, label, value, state) {
  const el = document.getElementById(id);
  if (!el) return;
  const normalized = ["ok", "warn", "error", "info"].includes(state) ? state : "info";
  el.className = "mobile-pill " + normalized;
  el.innerHTML =
    `<span class="mobile-pill-label">${esc(label)}</span>` +
    `<span class="mobile-pill-value">${esc(value)}</span>`;
}

function _mobileStateClass(state) {
  const normalized = String(state || "unknown").toLowerCase();
  if (["pass", "healthy", "active", "ok", "normal"].includes(normalized)) return "ok";
  if (["warn", "soft_limit", "degraded", "recovering"].includes(normalized)) return "warn";
  if (["blocked", "fail", "error", "inactive", "missing", "down"].includes(normalized)) return "error";
  return "";
}

function setMobileBadge(id, text, state) {
  const el = document.getElementById(id);
  if (!el) return;
  const cls = _mobileStateClass(state);
  el.className = "mobile-status-badge" + (cls ? " " + cls : "");
  el.textContent = text || "unknown";
}

function updateMobileScore(score, level) {
  const scoreEl = document.getElementById("mobileAutonomyScore");
  const levelEl = document.getElementById("mobileAutonomyLevel");
  if (scoreEl) scoreEl.textContent = (parseFloat(score) || 0).toFixed(1);
  if (levelEl) levelEl.textContent = (level || "–").replace(/_/g, " ");
}

function updateMobileVoiceState(state) {
  mobileVoiceState = state || "idle";
  const ids = ["mobileVoiceOrbBtn", "mobileNav-voice"];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("listening", "speaking", "thinking", "error", "active");
    if (mobileVoiceState !== "idle") {
      el.classList.add(mobileVoiceState);
      el.classList.add("active");
    }
  });
  const chatVoiceEl = document.getElementById("mobileChatVoice");
  if (chatVoiceEl) {
    const voiceText = mobileVoiceState === "listening"
      ? "hört zu"
      : mobileVoiceState === "speaking"
      ? "spricht"
      : mobileVoiceState === "thinking"
      ? "verarbeitet"
      : mobileVoiceState === "error"
      ? "fehler"
      : "bereit";
    chatVoiceEl.textContent = voiceText;
  }
}

function updateVoiceControlState() {
  const autoBtn = document.getElementById("mobileVoiceAutoBtn");
  if (autoBtn) {
    autoBtn.classList.toggle("active", voiceAutoReply);
    autoBtn.textContent = voiceAutoReply ? "Auto-Vorlesen" : "Auto-Vorlesen aus";
  }
  const replayBtn = document.getElementById("mobileVoiceReplayBtn");
  if (replayBtn) {
    const hasReply = Boolean(lastVoiceReplyText);
    replayBtn.disabled = !hasReply;
    replayBtn.classList.toggle("active", hasReply && mobileVoiceState === "speaking");
  }
}

function updateLiveConnectionState(state, label) {
  const chip = document.getElementById("liveConnectionChip");
  if (!chip) return;
  chip.classList.remove("ok", "warn", "error");
  const normalized = state === "ok" || state === "warn" || state === "error" ? state : "warn";
  chip.classList.add(normalized);
  chip.textContent = label || (normalized === "ok" ? "live" : normalized === "warn" ? "reconnect" : "offline");
}

async function refreshMobileOperationalData() {
  const btn = document.getElementById("mobileHeroRefreshBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Lädt…";
  }
  try {
    await Promise.all([
      loadMobileSnapshot(),
      loadRecentFiles(),
      loadVoiceStatus(),
      loadCanvasList(),
    ]);
    updateLiveConnectionState(navigator.onLine ? "ok" : "warn", navigator.onLine ? "live" : "offline");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Refresh";
    }
  }
}

async function loadVoiceStatus() {
  try {
    const data = await api("/voice/status");
    const voice = data.voice || {};
    const voiceNameEl = document.getElementById("mobileVoiceName");
    if (voiceNameEl) {
      voiceNameEl.textContent = voice.current_voice || "–";
    }
    const playbackEl = document.getElementById("mobileVoicePlayback");
    if (playbackEl) {
      const playback = voice.speaking ? "spricht" : voice.listening ? "hört zu" : "browser";
      playbackEl.textContent = playback;
    }
  } catch (e) {
    const voiceNameEl = document.getElementById("mobileVoiceName");
    if (voiceNameEl) voiceNameEl.textContent = "nicht bereit";
  }
  updateVoiceControlState();
}

function toggleVoiceAutoReply() {
  voiceAutoReply = !voiceAutoReply;
  updateVoiceControlState();
}

function _resetVoiceAudioUrl() {
  if (lastVoiceAudioUrl) {
    try { URL.revokeObjectURL(lastVoiceAudioUrl); } catch {}
    lastVoiceAudioUrl = "";
  }
}

async function browserSpeakText(text) {
  const clean = String(text || "").trim();
  if (!clean) return false;
  const player = document.getElementById("voicePlayer");
  if (!player) return false;

  lastVoiceReplyText = clean;
  updateVoiceControlState();
  updateMobileVoiceState("speaking");

  try {
    const response = await fetch("/voice/synthesize", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text: clean }),
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.error || body.message || detail;
      } catch {}
      throw new Error(detail);
    }

    const audioBlob = await response.blob();
    _resetVoiceAudioUrl();
    lastVoiceAudioUrl = URL.createObjectURL(audioBlob);

    player.pause();
    player.src = lastVoiceAudioUrl;
    player.currentTime = 0;
    await player.play();
    return true;
  } catch (err) {
    updateMobileVoiceState("error");
    const transcript = document.getElementById("micTranscript");
    if (transcript) {
      transcript.textContent = "Voice-Playback Fehler: " + err.message;
      transcript.classList.add("visible");
      setTimeout(() => transcript.classList.remove("visible"), 3500);
    }
    updateVoiceControlState();
    return false;
  }
}

function replayLastVoiceReply() {
  if (!lastVoiceReplyText) return;
  browserSpeakText(lastVoiceReplyText).catch(() => {});
}

function applyMobileCanvasSummary(items) {
  lastCanvasItems = Array.isArray(items) ? items : [];
  const titleEl = document.getElementById("mobileSessionTitle");
  const metaEl = document.getElementById("mobileSessionMeta");
  if (!titleEl || !metaEl) return;
  const selected = lastCanvasItems.find(c => c.id === selectedCanvasId) || lastCanvasItems[0] || null;
  titleEl.textContent = selected?.title || "Timus Session Canvas";
  const sessionCount = (selected?.session_ids || []).length;
  const eventCount = (selected?.events || []).length;
  metaEl.textContent =
    selected
      ? `${sessionCount} Sessions · ${eventCount} Events · ${chatSessionId}`
      : `Keine aktive Session · ${chatSessionId}`;
}

function applyMobileSnapshot(snapshot) {
  lastStatusSnapshot = snapshot || {};
  const services = lastStatusSnapshot.services || {};
  const opsGate = lastStatusSnapshot.ops_gate || {};
  const budget = lastStatusSnapshot.budget || {};
  const selfHealing = lastStatusSnapshot.self_healing || {};
  const stabilityGate = lastStatusSnapshot.stability_gate || {};
  const agents = lastStatusSnapshot.agents || [];

  const mcpOk = Boolean((services.mcp || {}).ok);
  const dispatcherOk = Boolean((services.dispatcher || {}).ok);
  const opsState = String(opsGate.state || "unknown").toLowerCase();
  const budgetState = String(budget.state || "unknown").toLowerCase();

  setMobilePill(
    "mobilePillMcp",
    "MCP",
    `${(services.mcp || {}).active || "unknown"} · ${selfHealing.open_incidents || 0} Incidents`,
    mcpOk ? "ok" : "error",
  );
  setMobilePill(
    "mobilePillDispatcher",
    "Dispatcher",
    `${(services.dispatcher || {}).active || "unknown"} · PID ${(services.dispatcher || {}).main_pid || 0}`,
    dispatcherOk ? "ok" : "error",
  );
  setMobilePill(
    "mobilePillOps",
    "Ops Gate",
    `${opsGate.state || "unknown"} · Canary ${opsGate.recommended_canary_percent || 0}%`,
    opsState === "pass" ? "ok" : opsState === "warn" ? "warn" : "error",
  );
  setMobilePill(
    "mobilePillBudget",
    "Budget",
    `${budget.state || "unknown"} · ${budget.message || `${budget.window_days || 1}d window`}`,
    budgetState === "ok" || budgetState === "normal" ? "ok" : budgetState === "warn" || budgetState === "soft_limit" ? "warn" : "error",
  );

  const openIncidents = Number(selfHealing.open_incidents || 0);
  const mcpHealth = (lastStatusSnapshot.local || {}).mcp_health || {};
  const mcpPayload = mcpHealth.data || {};
  const statusBadgeState = openIncidents > 0 ? selfHealing.degrade_mode || "warn" : opsGate.state || "ok";

  setMobileBadge("mobileStatusBadge", `${selfHealing.degrade_mode || "normal"}`, statusBadgeState);
  setMobileBadge("mobileHealingBadge", `${openIncidents} offen`, openIncidents > 0 ? selfHealing.degrade_mode || "warn" : "ok");
  setMobileBadge("mobileAgentsBadge", `${agents.length || 0} Rollen`, agents.some(a => ["error", "warn"].includes(String(a.provider_state || "").toLowerCase())) ? "warn" : "ok");

  const mcpStatusEl = document.getElementById("mobileStatusMcp");
  const dispatcherStatusEl = document.getElementById("mobileStatusDispatcher");
  const opsStatusEl = document.getElementById("mobileStatusOpsGate");
  const stabilityEl = document.getElementById("mobileStatusStability");
  if (mcpStatusEl) {
    mcpStatusEl.textContent = `${(services.mcp || {}).active || "unknown"} · ${mcpPayload.status || "down"} · ${(mcpHealth.latency_ms ?? "–")} ms`;
  }
  if (dispatcherStatusEl) {
    dispatcherStatusEl.textContent = `${(services.dispatcher || {}).active || "unknown"} · PID ${(services.dispatcher || {}).main_pid || 0}`;
  }
  if (opsStatusEl) {
    opsStatusEl.textContent = `${opsGate.state || "unknown"} · Canary ${(opsGate.recommended_canary_percent || 0)}%`;
  }
  if (stabilityEl) {
    stabilityEl.textContent = `${stabilityGate.state || "unknown"} · Breaker ${stabilityGate.circuit_breakers_open || 0}`;
  }

  const incidentList = document.getElementById("mobileIncidentList");
  if (incidentList) {
    const incidents = (selfHealing.incidents || []).slice(0, 3);
    incidentList.innerHTML = incidents.length
      ? incidents.map(incident => {
          const state = incident.recovery_phase || incident.quarantine_state || incident.notification_state || "unknown";
          return `
            <div class="mobile-status-row">
              <div>
                <div class="name">${esc(incident.component || "unknown")} · ${esc(incident.signal || "signal")}</div>
                <div class="meta">
                  ${esc(incident.recovery_stage || "observe")} · ${esc(incident.memory_state || "new")}
                  ${incident.cooldown_until ? ` · cooldown ${esc(incident.cooldown_until)}` : ""}
                </div>
              </div>
              <span class="state ${_mobileStateClass(state)}">${esc(state)}</span>
            </div>
          `;
        }).join("")
      : '<div class="empty">Keine offenen Incidents.</div>';
  }

  const agentList = document.getElementById("mobileAgentList");
  if (agentList) {
    const rows = agents.slice(0, 5);
    agentList.innerHTML = rows.length
      ? rows.map(agent => {
          const state = agent.runtime_status || agent.provider_state || "idle";
          return `
            <div class="mobile-status-row">
              <div>
                <div class="name">${esc(agent.agent || "agent")}</div>
                <div class="meta">${esc(agent.provider || "provider")} · ${esc((agent.model || "").split("/").pop() || "–")}</div>
              </div>
              <span class="state ${_mobileStateClass(state)}">${esc(state)}</span>
            </div>
          `;
        }).join("")
      : '<div class="empty">Keine Agentendaten.</div>';
  }

  const chatSessionEl = document.getElementById("mobileChatSession");
  if (chatSessionEl) chatSessionEl.textContent = chatSessionId;
}

async function loadMobileSnapshot() {
  try {
    const data = await api("/status/snapshot");
    applyMobileSnapshot(data.snapshot || {});
  } catch (e) {
    setMobilePill("mobilePillMcp", "MCP", `Fehler: ${e.message}`, "error");
  }
}

function setMobileSection(section) {
  mobileSection = section;
  if (!isMobileLayout()) return;
  document.body.setAttribute("data-mobile-section", section);
  document.querySelectorAll(".mobile-nav-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById("mobileNav-" + section);
  if (activeBtn) activeBtn.classList.add("active");

  if (section === "home") {
    if (activeTab !== "canvas") switchTab("canvas");
  } else if (section === "status") {
    if (activeTab !== "autonomy") switchTab("autonomy");
    loadAutonomyData().catch(() => {});
  } else if (section === "chat") {
    setTimeout(() => {
      const input = document.getElementById("chatInput");
      if (input) input.focus();
    }, 60);
  } else if (section === "files") {
    loadRecentFiles().catch(() => {});
  }
}

function syncMobileLayout() {
  if (isMobileLayout()) {
    document.body.setAttribute("data-mobile-section", mobileSection);
  } else {
    document.body.removeAttribute("data-mobile-section");
  }
}

function toggleMobileVoice() {
  const micBtn = document.getElementById("micBtn");
  if (micBtn) micBtn.click();
}

function formatBytes(num) {
  const size = Number(num || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function triggerMobileUpload() {
  document.getElementById("fileInput")?.click();
}

function useFileInChat(path) {
  const input = document.getElementById("chatInput");
  if (!input) return;
  input.value = `Analysiere die Datei ${path} und fasse die wichtigsten Punkte zusammen.`;
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 120) + "px";
  setMobileSection("chat");
  setTimeout(() => input.focus(), 60);
}

function renderRecentFiles(files) {
  lastRecentFiles = Array.isArray(files) ? files : [];
  const badge = document.getElementById("mobileFilesBadge");
  if (badge) {
    badge.className = "mobile-status-badge ok";
    badge.textContent = `${lastRecentFiles.length} Dateien`;
  }
  const list = document.getElementById("mobileFilesList");
  if (!list) return;
  if (!lastRecentFiles.length) {
    list.innerHTML = '<div class="empty">Noch keine Uploads oder Ergebnisse.</div>';
    return;
  }
  list.innerHTML = lastRecentFiles.map(file => {
    const origin = String(file.origin || "result");
    const badgeCls = origin === "upload" ? "upload" : "result";
    const filePath = String(file.path || "");
    const downloadHref = `/files/download?path=${encodeURIComponent(filePath)}`;
    const modified = String(file.modified_at || "").replace("T", " ").slice(0, 16) || "–";
    const jsPath = JSON.stringify(filePath);
    return `
      <div class="mobile-file-card">
        <div class="mobile-file-top">
          <div class="mobile-file-name">${esc(file.filename || file.path || "Datei")}</div>
          <span class="mobile-file-badge ${badgeCls}">${esc(origin)}</span>
        </div>
        <div class="mobile-file-meta">
          ${esc(file.type || "file")} · ${formatBytes(file.size_bytes)} · ${esc(modified)}
        </div>
        <div class="mobile-file-actions">
          <a href="${downloadHref}" target="_blank" rel="noopener">Öffnen</a>
          <a href="${downloadHref}" download>Download</a>
          <button type="button" onclick='useFileInChat(${jsPath})'>Im Chat nutzen</button>
        </div>
      </div>
    `;
  }).join("");
}

async function loadRecentFiles() {
  try {
    const data = await api("/files/recent");
    renderRecentFiles(data.files || []);
  } catch (e) {
    const list = document.getElementById("mobileFilesList");
    if (list) list.innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`;
  }
}

// ── Tab-Switch ────────────────────────────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
  if (isMobileLayout()) {
    mobileSection = tab === "canvas" ? "home" : "status";
    document.body.setAttribute("data-mobile-section", mobileSection);
    document.querySelectorAll(".mobile-nav-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById("mobileNav-" + mobileSection);
    if (activeBtn) activeBtn.classList.add("active");
  }
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById("tab-" + tab).classList.add("active");
  document.getElementById("tab-" + tab + "-btn").classList.add("active");
  if (tab === "autonomy") loadAutonomyData();
  else if (tab === "canvas" && cy) setTimeout(() => cy.fit(), 60);
  else if (tab === "kamera") camCheckStatus();
  else if (tab === "flow") { initFlowGraph(); setTimeout(() => reloadFlowRuntime(), 80); }
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
  updateLiveConnectionState(navigator.onLine ? "warn" : "error", navigator.onLine ? "verbinde" : "offline");
  sseSource = new EventSource("/events/stream");
  sseSource.onopen = () => {
    sseConnected = true;
    updateLiveConnectionState("ok", "live");
    if (sseReconnectTimer) {
      clearTimeout(sseReconnectTimer);
      sseReconnectTimer = null;
    }
  };
  // window.handleSSE erlaubt nachträgliches Patching durch voicePulse
  sseSource.onmessage = e => { try { (window.handleSSE || handleSSE)(JSON.parse(e.data)); } catch {} };
  sseSource.onerror   = () => {
    sseConnected = false;
    updateLiveConnectionState(navigator.onLine ? "warn" : "error", navigator.onLine ? "reconnect" : "offline");
    sseSource.close();
    sseSource = null;
    if (sseReconnectTimer) clearTimeout(sseReconnectTimer);
    sseReconnectTimer = setTimeout(connectSSE, 5000);
  };
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
    loadRecentFiles().catch(() => {});
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
    if (typeof flowCy !== "undefined" && flowCy) animateFlowBeam(flowAliasToNodeId(d.from) || d.from, flowAliasToNodeId(d.to) || d.to, d.status || "running");
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

  if (role === "assistant" && text && String(text).trim()) {
    lastVoiceReplyText = String(text).trim();
    updateVoiceControlState();
  }

  const sessionEl = document.getElementById("mobileChatSession");
  if (sessionEl) sessionEl.textContent = chatSessionId;
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
      loadRecentFiles().catch(() => {});
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
  updateMobileScore(s, level);
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
    loadReflections(), loadBlackboard(), loadTriggers(), loadGoalTree(), loadImprovement(), loadApiCostControl()
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

async function loadApiCostControl() {
  const el = document.getElementById("apiCostPanel");
  if (!el) return;
  try {
    const data = await api("/status/snapshot");
    const snapshot = data.snapshot || {};
    applyMobileSnapshot(snapshot);
    const apiControl = snapshot.api_control || {};
    const budget = snapshot.budget || {};
    const opsGate = snapshot.ops_gate || {};
    const providers = apiControl.providers || [];

    const header = `
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;">
        <div><strong>Provider aktiv:</strong> ${apiControl.active_provider_count || 0}</div>
        <div><strong>Requests 24h:</strong> ${apiControl.total_requests || 0}</div>
        <div><strong>Gesamtkosten 24h:</strong> $${Number(apiControl.total_cost_usd || 0).toFixed(6)}</div>
        <div><strong>Budget:</strong> ${(budget.state || "unknown")}</div>
        <div><strong>Ops Gate:</strong> ${(opsGate.state || "unknown")}</div>
      </div>
    `;

    const providerRows = providers.length
      ? providers.map(item => {
          const state = item.state || "unknown";
          const icon = state === "ok" ? "🟢" : state === "missing" ? "⚪" : state === "auth_error" ? "🟠" : "🔴";
          const configured = item.api_configured ? "aktiv" : "fehlt";
          const latency = item.latency_ms != null ? `${item.latency_ms} ms` : "–";
          return `
            <div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,.05);">
              <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                <div><strong>${icon} ${esc(item.provider || "unknown")}</strong> · ${esc(item.api_env || "n/a")} · ${configured}</div>
                <div>Cost $${Number(item.total_cost_usd || 0).toFixed(6)} · Req ${item.total_requests || 0} · ${latency}</div>
              </div>
              <div style="font-size:11px;opacity:.72;margin-top:2px;">
                ${esc(item.base_url || "")}${item.status_code ? ` · HTTP ${esc(String(item.status_code))}` : ""}${item.detail ? ` · ${esc(item.detail)}` : ""}
              </div>
            </div>
          `;
        }).join("")
      : '<div class="empty">Keine Provider-Daten verfügbar</div>';

    const budgetRows = (budget.scopes || []).slice(0, 3).map(scope => `
      <div style="font-size:12px;opacity:.82;">
        ${esc(scope.scope || "?")}: $${Number(scope.current_cost_usd || 0).toFixed(6)} / warn $${Number(scope.warn_usd || 0).toFixed(6)} / soft $${Number(scope.soft_limit_usd || 0).toFixed(6)} / hard $${Number(scope.hard_limit_usd || 0).toFixed(6)}
      </div>
    `).join("");

    el.innerHTML = header + providerRows + (
      budgetRows
        ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,.05);">${budgetRows}</div>`
        : ""
    );
  } catch(e) {
    el.innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`;
  }
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
let _flowNavigatorInited = false;
let _flowResizeObserver = null;
let _flowActiveDetailNodeId = "";
let _flowLastRuntimeSummary = { active: 0, errors: 0, latest: "" };
let _flowCollapsedGroups = { voice: false, memory: false, autonomy: false };
let _flowEdgeAnimationRAF = null;
let _flowEdgeDashOffset = 0;

const FLOW_STATUS_ORDER = { idle: 0, completed: 1, running: 2, warning: 3, error: 4 };
const FLOW_RUNTIME_STALE_MS = {
  running: 5 * 60 * 1000,
  completed: 15 * 60 * 1000,
  warning: 20 * 60 * 1000,
  error: 20 * 60 * 1000,
};
const FLOW_GROUPS = {
  voice: {
    label: "Voice",
    parent: "GROUP_VOICE",
    summaryNode: "VOICE_SUM",
    summaryEdges: ["e-M-VOICE_SUM"],
    children: ["VC", "VW", "VT", "CV"],
  },
  memory: {
    label: "Memory",
    parent: "GROUP_MEMORY",
    summaryNode: "MEMORY_SUM",
    summaryEdges: ["e-M-MEMORY_SUM", "e-MEMORY_SUM-ARP"],
    children: ["MM", "WAL", "MAG", "IE", "UR", "CHR", "CUR", "AUS", "RFT", "SE", "SEA", "SED", "SET", "SEP", "CE", "CEL", "CET", "CEQ", "CES", "CEG", "CED", "CEP"],
  },
  autonomy: {
    label: "Autonomy",
    parent: "GROUP_AUTONOMY",
    summaryNode: "AUTONOMY_SUM",
    summaryEdges: ["e-D-AUTONOMY_SUM", "e-AUTONOMY_SUM-B", "e-AUTONOMY_SUM-MEMORY_SUM"],
    children: ["RUN", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13"],
  },
};
const FLOW_NODE_POSITIONS = {
  U: { x: 120, y: 220 },
  D: { x: 360, y: 220 },
  DS: { x: 600, y: 90 },
  DI: { x: 600, y: 150 },
  DP: { x: 600, y: 210 },
  DL: { x: 600, y: 270 },
  A: { x: 840, y: 250 },
  AR: { x: 1080, y: 180 },
  ARD: { x: 1310, y: 120 },
  ARDR: { x: 1530, y: 70 },
  ARDP: { x: 1530, y: 130 },
  ARDL: { x: 1530, y: 190 },
  ARP: { x: 1310, y: 280 },
  ARPM: { x: 1530, y: 260 },
  ARPA: { x: 1530, y: 320 },
  B: { x: 1080, y: 430 },
  BW: { x: 1310, y: 390 },
  BR: { x: 1310, y: 460 },
  BL: { x: 1310, y: 530 },
  M: { x: 1580, y: 430 },
  FH: { x: 1900, y: 80 },
  VC: { x: 1900, y: 210 },
  VW: { x: 2140, y: 145 },
  VT: { x: 2140, y: 225 },
  CV: { x: 2140, y: 305 },
  VOICE_SUM: { x: 2020, y: 225 },
  RS: { x: 1900, y: 430 },
  RSS: { x: 2140, y: 385 },
  RSC: { x: 2140, y: 445 },
  RSL: { x: 2140, y: 505 },
  RSM: { x: 2140, y: 565 },
  RSD: { x: 2380, y: 445 },
  RSLD: { x: 2380, y: 515 },
  SYS: { x: 1900, y: 660 },
  SH: { x: 1900, y: 760 },
  DR: { x: 1900, y: 920 },
  DRY: { x: 2140, y: 860 },
  DRI: { x: 2140, y: 930 },
  DRP: { x: 2140, y: 1000 },
  E: { x: 1900, y: 1110 },
  MM: { x: 1600, y: 1370 },
  WAL: { x: 1830, y: 1220 },
  MAG: { x: 1830, y: 1290 },
  IE: { x: 1830, y: 1360 },
  UR: { x: 1830, y: 1430 },
  CHR: { x: 1830, y: 1500 },
  CUR: { x: 1830, y: 1570 },
  AUS: { x: 1830, y: 1640 },
  RFT: { x: 1830, y: 1710 },
  SE: { x: 2110, y: 1350 },
  SEA: { x: 2350, y: 1220 },
  SED: { x: 2350, y: 1300 },
  SET: { x: 2350, y: 1380 },
  SEP: { x: 2350, y: 1460 },
  CE: { x: 2110, y: 1590 },
  CEL: { x: 2350, y: 1540 },
  CET: { x: 2350, y: 1610 },
  CEQ: { x: 2350, y: 1680 },
  CES: { x: 2350, y: 1750 },
  CEG: { x: 2350, y: 1820 },
  CED: { x: 2350, y: 1890 },
  CEP: { x: 2350, y: 1960 },
  MEMORY_SUM: { x: 2070, y: 1530 },
  RUN: { x: 420, y: 1080 },
  G1: { x: 700, y: 930 },
  G2: { x: 700, y: 1000 },
  G3: { x: 700, y: 1070 },
  G4: { x: 700, y: 1140 },
  G5: { x: 980, y: 930 },
  G6: { x: 980, y: 1020 },
  G7: { x: 980, y: 1120 },
  G8: { x: 1260, y: 930 },
  G9: { x: 1260, y: 1020 },
  G10: { x: 1260, y: 1120 },
  G11: { x: 1540, y: 930 },
  G12: { x: 1540, y: 1020 },
  G13: { x: 1540, y: 1120 },
  AUTONOMY_SUM: { x: 980, y: 1040 },
};
const FLOW_PRIMARY_BEAM_MAP = {
  user: "U",
  telegram: "U",
  terminal: "U",
  canvas: "U",
  dispatcher: "D",
  main_dispatcher: "D",
  meta: "ARPA",
  executor: "B",
  research: "DR",
  reasoning: "DI",
  creative: "DRI",
  development: "M",
  developer: "M",
  visual: "FH",
  data: "MM",
  document: "DRP",
  communication: "VC",
  system: "SYS",
  shell: "SH",
  image: "DRI",
};
const FLOW_ALIAS_NODE_IDS = {
  u: "U",
  user: "U",
  cli: "U",
  telegram: "U",
  canvas: "U",
  terminal: "U",
  d: "D",
  dispatcher: "D",
  main_dispatcher: "D",
  "query sanitizing": "DS",
  sanitize: "DS",
  sanitizing: "DS",
  "intent analyse llm": "DI",
  intent: "DI",
  "policy gate": "DP",
  policy: "DP",
  lane: "DL",
  session: "DL",
  agent_class_map: "A",
  agent_classmap: "A",
  "13 agenten": "A",
  agentregistry: "AR",
  agent_registry: "AR",
  delegate: "ARD",
  delegation: "ARD",
  retry: "ARDR",
  partial: "ARDP",
  "loop prevention": "ARDL",
  loop: "ARDL",
  delegate_parallel: "ARP",
  fanout: "ARP",
  "fan out": "ARP",
  "memoryaccessguard": "ARPM",
  "resultaggregator": "ARPA",
  result_aggregator: "ARPA",
  base_agent: "B",
  dynamictoolmixin: "B",
  dynamic_tool_mixin: "B",
  "working memory": "BW",
  recall: "BR",
  fastpath: "BR",
  buglogger: "BL",
  "mcp server": "M",
  mcp: "M",
  jsonrpc: "M",
  "json-rpc": "M",
  tools: "M",
  visualnemotron: "FH",
  florence: "FH",
  paddleocr: "FH",
  voice: "VC",
  whisper: "VW",
  stt: "VW",
  tts: "VT",
  inworld: "VT",
  realsense: "RS",
  start_realsense_stream: "RSS",
  capture_realsense_snapshot: "RSC",
  snapshot: "RSC",
  capture_realsense_live_frame: "RSL",
  live_frame: "RSL",
  realsense_stream: "RSM",
  "realsense captures": "RSD",
  "realsense stream": "RSLD",
  systemagent: "SYS",
  "system agent": "SYS",
  shellagent: "SH",
  "shell agent": "SH",
  "deep research": "DR",
  deep_research: "DR",
  youtuberesearcher: "DRY",
  imagecollector: "DRI",
  researchpdfbuilder: "DRP",
  memory: "MM",
  memory_system: "MM",
  sqlite: "WAL",
  wal: "WAL",
  interaction_events: "IE",
  unified_recall: "UR",
  chromadb: "CHR",
  curator: "CUR",
  summarize: "AUS",
  reflection: "RFT",
  soulengine: "SE",
  soul_engine: "SE",
  axes: "SEA",
  apply_drift: "SED",
  tone: "SET",
  system_prompt_prefix: "SEP",
  curiosity: "CE",
  curiosityengine: "CE",
  "fuzzy sleep": "CEL",
  topic: "CET",
  query: "CEQ",
  dataforseo: "CES",
  gatekeeper: "CEG",
  duplicate: "CED",
  push: "CEP",
  autonomous_runner: "RUN",
  goalgenerator: "G1",
  longtermplanner: "G2",
  replanningengine: "G3",
  selfhealingengine: "G4",
  autonomyscorecard: "G5",
  sessionreflection: "G6",
  agentblackboard: "G7",
  blackboard: "G7",
  proactivetriggers: "G8",
  goalqueuemanager: "G9",
  selfimprovementengine: "G10",
  feedbackengine: "G11",
  emailautonomyengine: "G12",
  toolgeneratorengine: "G13",
  executor: "A",
  research: "DR",
  reasoning: "A",
  creative: "DRI",
  development: "A",
  developer: "A",
  visual: "FH",
  data: "MM",
  document: "DRP",
  communication: "VC",
  system: "SYS",
  shell: "SH",
  image: "DRI",
  meta: "ARPA",
};
const FLOW_KEYWORD_GROUPS = [
  { nodeIds: ["DS"], terms: ["sanitize", "sanitizing", "query sanitize"] },
  { nodeIds: ["DI"], terms: ["intent", "routing llm", "classifier"] },
  { nodeIds: ["DP"], terms: ["policy", "guardrail"] },
  { nodeIds: ["DL"], terms: ["lane", "session", "context"] },
  { nodeIds: ["AR", "ARD"], terms: ["delegate", "delegation"] },
  { nodeIds: ["ARDR"], terms: ["retry", "backoff"] },
  { nodeIds: ["ARDP"], terms: ["partial"] },
  { nodeIds: ["ARDL"], terms: ["loop", "max_depth"] },
  { nodeIds: ["ARP", "ARPA"], terms: ["parallel", "fan-out", "fan out", "fan-in", "fan in", "gather", "aggregator"] },
  { nodeIds: ["ARPM", "MAG"], terms: ["memoryaccessguard", "contextvar", "thread-safe", "thread safe"] },
  { nodeIds: ["B", "BW"], terms: ["working memory", "prompt prefix", "soul-prefix", "soul prefix"] },
  { nodeIds: ["BR"], terms: ["recall", "fast-path", "fast path"] },
  { nodeIds: ["BL"], terms: ["buglogger", "traceback"] },
  { nodeIds: ["M"], terms: ["mcp", "json-rpc", "jsonrpc", "tool", "fastapi"] },
  { nodeIds: ["FH"], terms: ["visualnemotron", "florence", "paddleocr", "vision"] },
  { nodeIds: ["VC", "VW", "VT", "CV"], terms: ["voice", "listen", "speak", "whisper", "tts", "stt", "playback"] },
  { nodeIds: ["RS", "RSS", "RSC", "RSL", "RSM", "RSD", "RSLD"], terms: ["realsense", "snapshot", "live_frame", "live frame", "capture_realsense", "camera/status"] },
  { nodeIds: ["SYS"], terms: ["systemagent", "system agent", "monitoring"] },
  { nodeIds: ["SH"], terms: ["shellagent", "shell agent", "bash", "terminal"] },
  { nodeIds: ["DR", "DRY", "DRI", "DRP"], terms: ["deep research", "researchpdfbuilder", "imagecollector", "youtube"] },
  { nodeIds: ["MM", "WAL", "IE", "UR", "CHR", "CUR", "AUS", "RFT"], terms: ["memory", "sqlite", "wal", "interaction_events", "unified_recall", "chromadb", "curator", "summarize", "reflection"] },
  { nodeIds: ["SE", "SEA", "SED", "SET", "SEP"], terms: ["soul", "tone", "apply_drift", "risk_appetite", "system prompt prefix"] },
  { nodeIds: ["CE", "CEL", "CET", "CEQ", "CES", "CEG", "CED", "CEP"], terms: ["curiosity", "fuzzy sleep", "topic", "dataforseo", "telegram push", "duplicate"] },
  { nodeIds: ["RUN", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13"], terms: ["autonomous_runner", "goalgenerator", "planner", "selfhealing", "scorecard", "sessionreflection", "blackboard", "trigger", "goal queue", "self improvement", "feedback", "email autonomy", "tool generator"] },
];

function flowTonePalette(tone) {
  const palette = {
    entry:      { bg: "#102236", border: "#2d5273", glow: "rgba(45,82,115,0.35)" },
    dispatch:   { bg: "#12273c", border: "#3270a1", glow: "rgba(50,112,161,0.34)" },
    agent:      { bg: "#142437", border: "#2d5f83", glow: "rgba(45,95,131,0.30)" },
    runtime:    { bg: "#101f30", border: "#296181", glow: "rgba(41,97,129,0.28)" },
    voice:      { bg: "#102634", border: "#2b7f91", glow: "rgba(43,127,145,0.30)" },
    sensor:     { bg: "#1d1f39", border: "#4b4ba3", glow: "rgba(75,75,163,0.28)" },
    memory:     { bg: "#17212f", border: "#4a5e8a", glow: "rgba(74,94,138,0.28)" },
    soul:       { bg: "#1a2037", border: "#6d61b5", glow: "rgba(109,97,181,0.26)" },
    curiosity:  { bg: "#142a24", border: "#2b8a6d", glow: "rgba(43,138,109,0.28)" },
    autonomy:   { bg: "#1d2432", border: "#788aa8", glow: "rgba(120,138,168,0.26)" },
    storage:    { bg: "#1d2330", border: "#4f5d76", glow: "rgba(79,93,118,0.25)" },
    external:   { bg: "#2a2316", border: "#9a7a39", glow: "rgba(154,122,57,0.28)" },
    system:     { bg: "#2a1821", border: "#92506d", glow: "rgba(146,80,109,0.27)" },
  };
  return palette[tone] || palette.runtime;
}

function flowRuntimePalette(status, baseBg, baseBorder, baseGlow) {
  const presets = {
    idle:      { bg: baseBg, border: baseBorder, glow: baseGlow, blur: 18, opacity: 0.45 },
    completed: { bg: "#0f2d24", border: "#00e09a", glow: "rgba(0,224,154,0.45)", blur: 28, opacity: 0.82 },
    running:   { bg: "#0f2933", border: "#00d4f0", glow: "rgba(0,212,240,0.50)", blur: 30, opacity: 0.88 },
    warning:   { bg: "#332710", border: "#fbbf24", glow: "rgba(251,191,36,0.48)", blur: 32, opacity: 0.92 },
    error:     { bg: "#381320", border: "#f43f5e", glow: "rgba(244,63,94,0.60)", blur: 40, opacity: 0.96 },
  };
  return presets[status] || presets.idle;
}

function flowNodeSpec(id, label, tone, meta) {
  meta = meta || {};
  const lines = String(label).split("\n");
  const longest = lines.reduce((m, line) => Math.max(m, line.length), 0);
  const position = meta.position || FLOW_NODE_POSITIONS[id] || null;
  const dims = {
    w: meta.w || Math.min(230, Math.max(96, 28 + longest * 6.2)),
    h: meta.h || (lines.length >= 3 ? 72 : lines.length === 2 ? 60 : 46),
  };
  const palette = flowTonePalette(tone);
  const data = {
    id,
    label,
    tone,
    lane: meta.lane || "",
    description: meta.description || "",
    groupKey: meta.groupKey || "",
    isGroup: meta.isGroup ? 1 : 0,
    isSummary: meta.isSummary ? 1 : 0,
    zoneMinW: meta.zoneMinW || 220,
    zoneMinH: meta.zoneMinH || 160,
    baseBg: palette.bg,
    baseBorder: palette.border,
    baseGlow: palette.glow,
    renderBg: palette.bg,
    renderBorder: palette.border,
    renderGlow: palette.glow,
    renderBlur: 18,
    renderOpacity: 0.45,
    runtimeStatus: "idle",
    runtimeSource: "",
    runtimeMessage: "",
    runtimeUpdatedAt: "",
    runtimeSeverity: 0,
    w: dims.w,
    h: dims.h,
    renderDashOffset: 0,
  };
  if (meta.parent) data.parent = meta.parent;
  return {
    data,
    position: position || undefined,
  };
}

function flowEdgeSpec(source, target, meta) {
  meta = meta || {};
  return {
    data: {
      id: meta.id || `e-${source}-${target}`,
      source,
      target,
      label: meta.label || "",
      dashed: !!meta.dashed,
      baseColor: meta.color || "#274058",
      renderColor: meta.color || "#274058",
      renderOpacity: meta.opacity != null ? meta.opacity : (meta.dashed ? 0.42 : 0.62),
      renderWidth: meta.width || (meta.dashed ? 1.15 : 1.4),
    },
    classes: meta.dashed ? "flow-edge-dashed" : "",
  };
}

function buildArchitectureFlowElements() {
  const nodes = [
    flowNodeSpec("GROUP_VOICE", "Voice", "voice", { lane: "Group", isGroup: true, groupKey: "voice", zoneMinW: 520, zoneMinH: 230 }),
    flowNodeSpec("GROUP_MEMORY", "Memory", "memory", { lane: "Group", isGroup: true, groupKey: "memory", zoneMinW: 1120, zoneMinH: 900 }),
    flowNodeSpec("GROUP_AUTONOMY", "Autonomy", "autonomy", { lane: "Group", isGroup: true, groupKey: "autonomy", zoneMinW: 1320, zoneMinH: 360 }),
    flowNodeSpec("U", "User Input\nCLI / Telegram / Canvas / Terminal", "entry", { lane: "Input", description: "Alle primären Einstiegspunkte." }),
    flowNodeSpec("D", "main_dispatcher.py", "dispatch", { lane: "Dispatch", description: "Zentraler Router für Queries." }),
    flowNodeSpec("DS", "Query Sanitizing", "dispatch", { lane: "Dispatch" }),
    flowNodeSpec("DI", "Intent Analyse LLM", "dispatch", { lane: "Dispatch" }),
    flowNodeSpec("DP", "Policy Gate", "dispatch", { lane: "Dispatch" }),
    flowNodeSpec("DL", "Lane + Session", "dispatch", { lane: "Dispatch" }),
    flowNodeSpec("A", "AGENT_CLASS_MAP\n13 Agenten", "agent", { lane: "Agents", description: "Gemeinsamer Einstieg in die Agentenklasse." }),
    flowNodeSpec("AR", "AgentRegistry", "agent", { lane: "Delegation" }),
    flowNodeSpec("ARD", "delegate - sequenziell\nasyncio.wait_for 120s", "agent", { lane: "Delegation" }),
    flowNodeSpec("ARDR", "Retry expon. Backoff", "agent", { lane: "Delegation" }),
    flowNodeSpec("ARDP", "Partial-Erkennung", "agent", { lane: "Delegation" }),
    flowNodeSpec("ARDL", "Loop-Prevention MAX_DEPTH 3", "agent", { lane: "Delegation" }),
    flowNodeSpec("ARP", "delegate_parallel - Fan-Out v2.5\nasyncio.gather + Semaphore max 10", "agent", { lane: "Delegation", h: 72 }),
    flowNodeSpec("ARPM", "MemoryAccessGuard\nContextVar - thread-safe", "agent", { lane: "Delegation" }),
    flowNodeSpec("ARPA", "ResultAggregator\nFan-In Markdown", "agent", { lane: "Delegation" }),
    flowNodeSpec("B", "agent/base_agent.py\nDynamicToolMixin", "runtime", { lane: "Runtime" }),
    flowNodeSpec("BW", "Working Memory inject\nSoul-Prefix NEU v2.8", "runtime", { lane: "Runtime" }),
    flowNodeSpec("BR", "Recall Fast-Path", "runtime", { lane: "Runtime" }),
    flowNodeSpec("BL", "BugLogger", "runtime", { lane: "Runtime" }),
    flowNodeSpec("M", "MCP Server :5000\nFastAPI + JSON-RPC\n80+ Tools", "runtime", { lane: "Tools", h: 72 }),
    flowNodeSpec("FH", "VisualNemotron v4\nFlorence-2 + PaddleOCR\nPlan-then-Execute", "runtime", { lane: "Tools", h: 72 }),
    flowNodeSpec("VC", "Voice REST API\n/voice/status|listen|stop|speak", "voice", { lane: "Voice", h: 72, parent: "GROUP_VOICE" }),
    flowNodeSpec("VW", "Faster-Whisper STT\ninit via Background-Task", "voice", { lane: "Voice", parent: "GROUP_VOICE" }),
    flowNodeSpec("VT", "Inworld.AI TTS\nBase64-MP3 + Playback", "voice", { lane: "Voice", parent: "GROUP_VOICE" }),
    flowNodeSpec("CV", "Canvas UI v3.3+\nSSE Voice-Loop", "voice", { lane: "Voice", parent: "GROUP_VOICE" }),
    flowNodeSpec("VOICE_SUM", "Voice Cluster\n4 Subsysteme", "voice", { lane: "Voice", isSummary: true, groupKey: "voice", w: 180, h: 74, description: "Zusammenfassung des Voice-Subsystems." }),
    flowNodeSpec("RS", "RealSense Toolchain\nrealsense_camera_tool", "sensor", { lane: "Sensor" }),
    flowNodeSpec("RSS", "start_realsense_stream\nOpenCV Background Thread", "sensor", { lane: "Sensor" }),
    flowNodeSpec("RSC", "capture_realsense_snapshot\nrs-save-to-disk", "sensor", { lane: "Sensor" }),
    flowNodeSpec("RSL", "capture_realsense_live_frame\nexport latest frame", "sensor", { lane: "Sensor" }),
    flowNodeSpec("RSM", "utils/realsense_stream.py\nlatest frame + stream status", "sensor", { lane: "Sensor" }),
    flowNodeSpec("RSD", "data/realsense_captures\nSnapshot-Persistenz", "storage", { lane: "Storage" }),
    flowNodeSpec("RSLD", "data/realsense_stream\nLive-Frame Export", "storage", { lane: "Storage" }),
    flowNodeSpec("SYS", "SystemAgent\nread-only Monitoring", "system", { lane: "Agents" }),
    flowNodeSpec("SH", "ShellAgent v2\n5-Schicht-Policy\nSystem-Kontext-Injektion", "system", { lane: "Agents", h: 72 }),
    flowNodeSpec("DR", "Timus Deep Research v8.0\nEvidence Engine\nYouTube + Bilder + PDF", "runtime", { lane: "Tools", h: 84, w: 224 }),
    flowNodeSpec("DRY", "YouTubeResearcher\nDataForSEO + qwen3-235b\nNVIDIA Vision", "runtime", { lane: "Tools", h: 72 }),
    flowNodeSpec("DRI", "ImageCollector\nWeb-Bild + DALL-E", "runtime", { lane: "Tools" }),
    flowNodeSpec("DRP", "ResearchPDFBuilder\nWeasyPrint A4-PDF\nJinja2 Template", "runtime", { lane: "Tools", h: 72 }),
    flowNodeSpec("E", "Externe Systeme\nPyAutoGUI / Playwright / APIs", "external", { lane: "External" }),
    flowNodeSpec("MM", "memory/memory_system.py\nMemory v2.2 + WAL", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("WAL", "SQLite WAL\ncuriosity_sent NEU v2.8", "storage", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("MAG", "MemoryAccessGuard\nContextVar", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("IE", "interaction_events\ndeterministisches Logging", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("UR", "unified_recall\n200-Scan", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CHR", "ChromaDB Direktverbindung", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CUR", "Nemotron-Kurator\n4 Kriterien", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("AUS", "Auto-Summarize\nalle 20 Nachrichten", "memory", { lane: "Memory", parent: "GROUP_MEMORY" }),
    flowNodeSpec("RFT", "Reflection 30s Timeout\n-> soul_engine.apply_drift NEU v2.8", "memory", { lane: "Memory", h: 72, parent: "GROUP_MEMORY" }),
    flowNodeSpec("SE", "SoulEngine NEU v2.8\nmemory/soul_engine.py", "soul", { lane: "Soul", parent: "GROUP_MEMORY" }),
    flowNodeSpec("SEA", "5 Achsen\nconfidence formality humor\nverbosity risk_appetite", "soul", { lane: "Soul", h: 72, parent: "GROUP_MEMORY" }),
    flowNodeSpec("SED", "apply_drift\n7 Signale - x0.1 Dampfung\nClamp 5-95", "soul", { lane: "Soul", h: 72, parent: "GROUP_MEMORY" }),
    flowNodeSpec("SET", "get_tone_config\nvorsichtig neutral direkt", "soul", { lane: "Soul", parent: "GROUP_MEMORY" }),
    flowNodeSpec("SEP", "get_system_prompt_prefix\ndynamisches Prompt-Fragment", "soul", { lane: "Soul", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CE", "CuriosityEngine NEU v2.8\norchestration/curiosity_engine.py", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CEL", "Fuzzy Sleep\n3-14h zufallig", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CET", "Topic-Extraktion\nSession + SQLite 72h", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CEQ", "LLM Query-Gen\nEdge-Suchanfrage 2026", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CES", "DataForSEO\nTop-3 Ergebnisse", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CEG", "Gatekeeper-LLM\nScore 0-10 - >=7 = senden", "curiosity", { lane: "Curiosity", h: 72, parent: "GROUP_MEMORY" }),
    flowNodeSpec("CED", "Duplikat-Check\n14 Tage - 2/Tag Limit", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("CEP", "Telegram Push\nSoul-Ton als Einstieg", "curiosity", { lane: "Curiosity", parent: "GROUP_MEMORY" }),
    flowNodeSpec("MEMORY_SUM", "Memory Cluster\n22 Module", "memory", { lane: "Memory", isSummary: true, groupKey: "memory", w: 190, h: 78, description: "Zusammenfassung von Memory, Soul und Curiosity." }),
    flowNodeSpec("RUN", "autonomous_runner.py\nAutonomie-Loop v4.0", "autonomy", { lane: "Autonomy", parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G1", "GoalGenerator M1\nMemory+Curiosity+Events", "autonomy", { lane: "Autonomy", parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G2", "LongTermPlanner M2\n3-Horizont-Planung", "autonomy", { lane: "Autonomy", parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G3", "ReplanningEngine M2\nCommitment-Uberwachung", "autonomy", { lane: "Autonomy", parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G4", "SelfHealingEngine M3\nCircuit-Breaker+Incidents", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G5", "AutonomyScorecard M5\nScore 0-100-Control-Loop", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G6", "SessionReflection M8\nIdle-Erkennung + LLM-Reflexion\nPattern-Akkumulation", "autonomy", { lane: "Autonomy", h: 78, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G7", "AgentBlackboard M9\nTTL Shared Memory\nwrite/read/search", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G8", "ProactiveTriggers M10\n+-14-Min-Fenster\nMorgen + Abend-Routinen", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G9", "GoalQueueManager M11\nHierarchische Ziele\nMeilenstein-Rollup", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G10", "SelfImprovementEngine M12\nTool-/Routing-Analytics\nwochentliche Analyse", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G11", "FeedbackEngine M16\n+/-/? -> Soul-Hooks\nDecay taglich", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G12", "EmailAutonomyEngine M14\nWhitelist+Confidence\nSMTP-Backend", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("G13", "ToolGeneratorEngine M13\nAST-Check+Review\nimportlib-Aktivierung", "autonomy", { lane: "Autonomy", h: 72, parent: "GROUP_AUTONOMY" }),
    flowNodeSpec("AUTONOMY_SUM", "Autonomy Cluster\n14 Module", "autonomy", { lane: "Autonomy", isSummary: true, groupKey: "autonomy", w: 190, h: 78, description: "Zusammenfassung des Autonomy-Subsystems." }),
  ];

  const edges = [
    flowEdgeSpec("U", "D"),
    flowEdgeSpec("D", "DS"),
    flowEdgeSpec("D", "DI"),
    flowEdgeSpec("D", "DP"),
    flowEdgeSpec("D", "DL"),
    flowEdgeSpec("DL", "A"),
    flowEdgeSpec("A", "AR"),
    flowEdgeSpec("AR", "ARD"),
    flowEdgeSpec("ARD", "ARDR"),
    flowEdgeSpec("ARD", "ARDP"),
    flowEdgeSpec("ARD", "ARDL"),
    flowEdgeSpec("AR", "ARP"),
    flowEdgeSpec("ARP", "ARPM"),
    flowEdgeSpec("ARP", "ARPA"),
    flowEdgeSpec("A", "B"),
    flowEdgeSpec("B", "BW"),
    flowEdgeSpec("B", "BR"),
    flowEdgeSpec("B", "BL"),
    flowEdgeSpec("B", "M"),
    flowEdgeSpec("M", "FH"),
    flowEdgeSpec("M", "VC"),
    flowEdgeSpec("VC", "VW"),
    flowEdgeSpec("VC", "VT"),
    flowEdgeSpec("VC", "CV"),
    flowEdgeSpec("M", "RS"),
    flowEdgeSpec("RS", "RSS"),
    flowEdgeSpec("RS", "RSC"),
    flowEdgeSpec("RS", "RSL"),
    flowEdgeSpec("RS", "RSM"),
    flowEdgeSpec("RSC", "RSD"),
    flowEdgeSpec("RSL", "RSLD"),
    flowEdgeSpec("M", "SYS"),
    flowEdgeSpec("M", "SH"),
    flowEdgeSpec("M", "DR"),
    flowEdgeSpec("DR", "DRY"),
    flowEdgeSpec("DR", "DRI"),
    flowEdgeSpec("DR", "DRP"),
    flowEdgeSpec("M", "E"),
    flowEdgeSpec("M", "MM"),
    flowEdgeSpec("MM", "WAL"),
    flowEdgeSpec("MM", "MAG"),
    flowEdgeSpec("MM", "IE"),
    flowEdgeSpec("MM", "UR"),
    flowEdgeSpec("MM", "CHR"),
    flowEdgeSpec("MM", "CUR"),
    flowEdgeSpec("MM", "AUS"),
    flowEdgeSpec("MM", "RFT"),
    flowEdgeSpec("MM", "SE"),
    flowEdgeSpec("SE", "SEA"),
    flowEdgeSpec("SE", "SED"),
    flowEdgeSpec("SE", "SET"),
    flowEdgeSpec("SE", "SEP"),
    flowEdgeSpec("MM", "CE"),
    flowEdgeSpec("CE", "CEL"),
    flowEdgeSpec("CE", "CET"),
    flowEdgeSpec("CE", "CEQ"),
    flowEdgeSpec("CE", "CES"),
    flowEdgeSpec("CE", "CEG"),
    flowEdgeSpec("CE", "CED"),
    flowEdgeSpec("CE", "CEP"),
    flowEdgeSpec("SET", "CEP", { dashed: true }),
    flowEdgeSpec("SEP", "BW", { dashed: true }),
    flowEdgeSpec("SED", "RFT", { dashed: true }),
    flowEdgeSpec("ARP", "MAG", { dashed: true }),
    flowEdgeSpec("WAL", "ARP", { dashed: true }),
    flowEdgeSpec("D", "RUN"),
    flowEdgeSpec("RUN", "G1"),
    flowEdgeSpec("RUN", "G2"),
    flowEdgeSpec("RUN", "G3"),
    flowEdgeSpec("RUN", "G4"),
    flowEdgeSpec("RUN", "G5"),
    flowEdgeSpec("RUN", "G6"),
    flowEdgeSpec("RUN", "G7"),
    flowEdgeSpec("RUN", "G8"),
    flowEdgeSpec("RUN", "G9"),
    flowEdgeSpec("RUN", "G10"),
    flowEdgeSpec("RUN", "G11"),
    flowEdgeSpec("RUN", "G12"),
    flowEdgeSpec("RUN", "G13"),
    flowEdgeSpec("G1", "WAL", { dashed: true }),
    flowEdgeSpec("G4", "WAL", { dashed: true }),
    flowEdgeSpec("G5", "WAL", { dashed: true }),
    flowEdgeSpec("G6", "WAL", { dashed: true }),
    flowEdgeSpec("G7", "B", { dashed: true }),
    flowEdgeSpec("G8", "WAL", { dashed: true }),
    flowEdgeSpec("G9", "WAL", { dashed: true }),
    flowEdgeSpec("G10", "WAL", { dashed: true }),
    flowEdgeSpec("M", "VOICE_SUM", { id: "e-M-VOICE_SUM", dashed: true, color: "#2b7f91", opacity: 0.55 }),
    flowEdgeSpec("M", "MEMORY_SUM", { id: "e-M-MEMORY_SUM", dashed: true, color: "#4a5e8a", opacity: 0.55 }),
    flowEdgeSpec("MEMORY_SUM", "ARP", { id: "e-MEMORY_SUM-ARP", dashed: true, color: "#4a5e8a", opacity: 0.55 }),
    flowEdgeSpec("D", "AUTONOMY_SUM", { id: "e-D-AUTONOMY_SUM", dashed: true, color: "#788aa8", opacity: 0.55 }),
    flowEdgeSpec("AUTONOMY_SUM", "B", { id: "e-AUTONOMY_SUM-B", dashed: true, color: "#788aa8", opacity: 0.55 }),
    flowEdgeSpec("AUTONOMY_SUM", "MEMORY_SUM", { id: "e-AUTONOMY_SUM-MEMORY_SUM", dashed: true, color: "#788aa8", opacity: 0.55 }),
  ];
  return { nodes, edges };
}

function isResearchTimeoutMessage(message = "") {
  const msg = String(message || "").toLowerCase();
  return (
    (msg.includes("research") && /\btimeout\b/.test(msg)) ||
    msg.includes("hat nicht innerhalb von 600.0s geantwortet") ||
    msg.includes("delegation meta -> research timeout") ||
    msg.includes("partial_research") ||
    msg.includes("\"timed_out\": true") ||
    msg.includes("recovery_hint")
  );
}

function normalizeFlowStatus(status, message) {
  const raw = String(status || "").toLowerCase();
  const msg = String(message || "").toLowerCase();
  if (isResearchTimeoutMessage(message)) return "warning";
  if (["error", "failed", "failure", "exception", "fatal"].includes(raw) || /\b(error|failed|exception|timeout|traceback)\b/.test(msg)) return "error";
  if (["warning", "warn", "partial", "degraded"].includes(raw) || /\b(partial|warning|fallback)\b/.test(msg)) return "warning";
  if (["running", "active", "thinking", "processing", "start", "started"].includes(raw)) return "running";
  if (["ok", "done", "success", "completed", "complete", "healthy", "idle"].includes(raw)) return raw === "idle" ? "idle" : "completed";
  return raw ? "running" : "idle";
}

function parseFlowTimestamp(value) {
  const ts = Date.parse(String(value || ""));
  return Number.isFinite(ts) ? ts : 0;
}

function flowStatusIsStale(status, updatedAt) {
  const ttl = FLOW_RUNTIME_STALE_MS[String(status || "").toLowerCase()] || 0;
  const ts = parseFlowTimestamp(updatedAt);
  return Boolean(ttl && ts && (Date.now() - ts) > ttl);
}

function flowAliasToNodeId(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (FLOW_PRIMARY_BEAM_MAP[raw]) return FLOW_PRIMARY_BEAM_MAP[raw];
  if (FLOW_ALIAS_NODE_IDS[raw.toLowerCase()]) return FLOW_ALIAS_NODE_IDS[raw.toLowerCase()];
  if (flowCy && flowCy.getElementById(raw).length) return raw;
  return "";
}

function flowNodeIdsForText(text) {
  const found = new Set();
  const normalized = String(text || "").toLowerCase();
  if (!normalized) return [];

  for (const token of Object.keys(FLOW_ALIAS_NODE_IDS)) {
    if (!token || token.length < 3) continue;
    if (normalized.includes(token)) found.add(FLOW_ALIAS_NODE_IDS[token]);
  }
  for (const group of FLOW_KEYWORD_GROUPS) {
    if (group.terms.some(term => normalized.includes(term))) {
      group.nodeIds.forEach(id => found.add(id));
    }
  }
  return Array.from(found);
}

function resolveFlowNodeIds(ctx) {
  const ids = new Set();
  const directFields = [
    ctx && ctx.nodeId,
    ctx && ctx.node_id,
    ctx && ctx.agent,
    ctx && ctx.from,
    ctx && ctx.to,
    ctx && ctx.tool,
    ctx && ctx.type,
  ];
  for (const value of directFields) {
    const mapped = flowAliasToNodeId(value);
    if (mapped) ids.add(mapped);
  }
  const text = [
    ctx && ctx.title,
    ctx && ctx.message,
    ctx && ctx.error,
    ctx && JSON.stringify(ctx && ctx.payload || {}),
  ].join(" ");
  flowNodeIdsForText(text).forEach(id => ids.add(id));
  if (ctx && ctx.type === "chat_error") {
    ids.add("D");
    ids.add("M");
  }
  if (ctx && ctx.type === "delegation") {
    ids.add("AR");
    ids.add("ARD");
    ids.add("A");
  }
  if (ctx && ctx.type === "tool_start") ids.add("M");
  if (ctx && ctx.type === "tool_done") ids.add("M");
  return Array.from(ids);
}

function setFlowNodeRuntime(nodeId, patch) {
  if (!flowCy) return;
  const node = flowCy.getElementById(nodeId);
  if (!node.length) return;
  const current = node.data();
  const nextStatus = normalizeFlowStatus(patch.status, patch.message);
  const nextSeverity = FLOW_STATUS_ORDER[nextStatus] || 0;
  const currentSeverity = Number(current.runtimeSeverity || 0);
  const shouldReplace =
    patch.force ||
    nextSeverity >= currentSeverity ||
    !current.runtimeUpdatedAt ||
    (patch.updatedAt && String(patch.updatedAt) >= String(current.runtimeUpdatedAt));
  if (!shouldReplace) return;

  const runtime = flowRuntimePalette(nextStatus, current.baseBg, current.baseBorder, current.baseGlow);
  node.data({
    runtimeStatus: nextStatus,
    runtimeSource: patch.source || current.runtimeSource || "",
    runtimeMessage: patch.message || current.runtimeMessage || "",
    runtimeUpdatedAt: patch.updatedAt || current.runtimeUpdatedAt || "",
    runtimeSeverity: nextSeverity,
    renderBg: runtime.bg,
    renderBorder: runtime.border,
    renderGlow: runtime.glow,
    renderBlur: runtime.blur,
    renderOpacity: runtime.opacity,
  });
}

function expireStaleFlowRuntime() {
  if (!flowCy) return;
  flowCy.nodes().forEach(node => {
    const status = node.data("runtimeStatus") || "idle";
    const updatedAt = node.data("runtimeUpdatedAt") || "";
    if (!flowStatusIsStale(status, updatedAt)) return;
    const runtime = flowRuntimePalette("idle", node.data("baseBg"), node.data("baseBorder"), node.data("baseGlow"));
    node.data({
      runtimeStatus: "idle",
      runtimeSource: "",
      runtimeMessage: "",
      runtimeSeverity: 0,
      renderBg: runtime.bg,
      renderBorder: runtime.border,
      renderGlow: runtime.glow,
      renderBlur: runtime.blur,
      renderOpacity: runtime.opacity,
    });
  });
}

function resetFlowRuntime() {
  if (!flowCy) return;
  flowCy.nodes().forEach(node => {
    node.data({
      runtimeStatus: "idle",
      runtimeSource: "",
      runtimeMessage: "",
      runtimeUpdatedAt: "",
      runtimeSeverity: 0,
      renderBg: node.data("baseBg"),
      renderBorder: node.data("baseBorder"),
      renderGlow: node.data("baseGlow"),
      renderBlur: 18,
      renderOpacity: 0.45,
    });
  });
  flowCy.edges().forEach(edge => {
    edge.data({
      renderColor: edge.data("baseColor"),
      renderOpacity: edge.hasClass("flow-edge-dashed") ? 0.42 : 0.62,
      renderWidth: edge.hasClass("flow-edge-dashed") ? 1.15 : 1.4,
      renderDashOffset: 0,
    });
    edge.removeClass("flow-edge-alert");
  });
  _flowLastRuntimeSummary = { active: 0, errors: 0, latest: "" };
  refreshFlowHud();
  refreshFlowGroupSummaries();
  refreshFlowEdgeStates();
}

function stopFlowEdgeAnimation() {
  if (_flowEdgeAnimationRAF) cancelAnimationFrame(_flowEdgeAnimationRAF);
  _flowEdgeAnimationRAF = null;
}

function animateFlowAlertEdges() {
  if (!flowCy) return;
  const activeEdges = flowCy.edges(".flow-edge-alert").filter(edge => edge.style("display") !== "none");
  if (!activeEdges.length) {
    stopFlowEdgeAnimation();
    return;
  }
  _flowEdgeDashOffset = (_flowEdgeDashOffset - 1.2) % 100;
  activeEdges.forEach(edge => edge.data("renderDashOffset", _flowEdgeDashOffset));
  _flowEdgeAnimationRAF = requestAnimationFrame(animateFlowAlertEdges);
}

function ensureFlowEdgeAnimation() {
  const hasAlerts = flowCy && flowCy.edges(".flow-edge-alert").filter(edge => edge.style("display") !== "none").length > 0;
  if (hasAlerts && !_flowEdgeAnimationRAF) {
    _flowEdgeAnimationRAF = requestAnimationFrame(animateFlowAlertEdges);
  } else if (!hasAlerts) {
    stopFlowEdgeAnimation();
  }
}

function refreshFlowEdgeStates() {
  if (!flowCy) return;
  flowCy.edges().forEach(edge => {
    if (edge.style("display") === "none") return;
    const sourceStatus = edge.source().data("runtimeStatus") || "idle";
    const targetStatus = edge.target().data("runtimeStatus") || "idle";
    const level = ["error", "warning", "running", "completed"].find(status => sourceStatus === status || targetStatus === status) || "idle";

    if (level === "error" || level === "warning") {
      edge.addClass("flow-edge-alert");
      edge.data({
        renderColor: level === "error" ? "#f43f5e" : "#fbbf24",
        renderOpacity: 0.98,
        renderWidth: 2.8,
      });
    } else if (level === "running") {
      edge.removeClass("flow-edge-alert");
      edge.data({
        renderColor: "#00d4f0",
        renderOpacity: 0.86,
        renderWidth: 2.1,
        renderDashOffset: 0,
      });
    } else if (level === "completed") {
      edge.removeClass("flow-edge-alert");
      edge.data({
        renderColor: "#00e09a",
        renderOpacity: 0.74,
        renderWidth: 1.8,
        renderDashOffset: 0,
      });
    } else {
      edge.removeClass("flow-edge-alert");
      edge.data({
        renderColor: edge.data("baseColor"),
        renderOpacity: edge.hasClass("flow-edge-dashed") ? 0.42 : 0.62,
        renderWidth: edge.hasClass("flow-edge-dashed") ? 1.15 : 1.4,
        renderDashOffset: 0,
      });
    }
  });
  ensureFlowEdgeAnimation();
}

function pulseFlowPath(nodeIds, status) {
  if (!flowCy || !nodeIds || !nodeIds.length) return;
  const colorByStatus = {
    running: "#00d4f0",
    completed: "#00e09a",
    warning: "#fbbf24",
    error: "#f43f5e",
  };
  const color = colorByStatus[normalizeFlowStatus(status)] || "#00d4f0";
  const active = new Set(nodeIds);
  flowCy.edges().forEach(edge => {
    const touches = active.has(edge.source().id()) || active.has(edge.target().id());
    if (!touches) return;
    edge.data({ renderColor: color, renderOpacity: 0.92, renderWidth: 2.7 });
    setTimeout(() => {
      if (!edge.removed()) {
        edge.data({
          renderColor: edge.data("baseColor"),
          renderOpacity: edge.hasClass("flow-edge-dashed") ? 0.42 : 0.62,
          renderWidth: edge.hasClass("flow-edge-dashed") ? 1.15 : 1.4,
        });
      }
    }, 1200);
  });
}

function refreshFlowHud(events) {
  const countEl = document.getElementById("flowHudCounts");
  const lastEl = document.getElementById("flowHudLast");
  if (!countEl || !lastEl) return;
  const total = flowCy ? flowCy.nodes().length : 0;
  const active = flowCy ? flowCy.nodes().filter(node => node.data("runtimeStatus") === "running").length : 0;
  const errors = flowCy ? flowCy.nodes().filter(node => node.data("runtimeStatus") === "error" || node.data("runtimeStatus") === "warning").length : 0;
  const latest = _flowLastRuntimeSummary.latest || ((events && events[0] && (events[0].message || events[0].type)) || "Noch keine Laufzeitdaten.");
  countEl.innerHTML = `Knoten: <strong>${total}</strong> · Aktiv: <strong>${active}</strong> · Hotspots: <strong>${errors}</strong>`;
  lastEl.textContent = latest;
}

function openFlowDetail(nodeId) {
  if (!flowCy) return;
  const node = flowCy.getElementById(nodeId);
  if (!node.length) return;
  _flowActiveDetailNodeId = nodeId;
  flowCy.nodes().unselect();
  node.select();
  document.getElementById("fdTitle").textContent = String(node.data("label") || "–");
  document.getElementById("fdId").textContent = node.id();
  document.getElementById("fdLayer").textContent = node.data("lane") || "–";
  document.getElementById("fdStatus").textContent = node.data("runtimeStatus") || "idle";
  document.getElementById("fdSource").textContent = node.data("runtimeSource") || "–";
  document.getElementById("fdUpdated").textContent = node.data("runtimeUpdatedAt") || "–";
  const msg = node.data("runtimeMessage") || node.data("description") || "";
  document.getElementById("fdMessage").innerHTML = msg ? esc(msg).replace(/\n/g, "<br>") : '<span class="flow-empty">Kein Laufzeitereignis.</span>';
  document.getElementById("flowDetail").classList.add("visible");
}

function closeFlowDetail() {
  _flowActiveDetailNodeId = "";
  if (flowCy) flowCy.nodes().unselect();
  document.getElementById("flowDetail").classList.remove("visible");
}

function focusFlowErrors() {
  if (!flowCy) return;
  const hot = flowCy.nodes().filter(node => {
    const status = node.data("runtimeStatus");
    return status === "error" || status === "warning";
  });
  if (hot.length) {
    flowCy.fit(hot, 90);
    hot.forEach(node => openFlowDetail(node.id()));
  } else {
    flowCy.fit(60);
  }
}

function flowGroupOfNode(nodeId) {
  for (const [groupKey, cfg] of Object.entries(FLOW_GROUPS)) {
    if (cfg.children.includes(nodeId) || cfg.summaryNode === nodeId || cfg.parent === nodeId) return groupKey;
  }
  return "";
}

function isFlowNoiseMessage(message = "", source = "") {
  const hay = `${message || ""}\n${source || ""}`.toLowerCase();
  return hay.includes("posthog") ||
    hay.includes("telemetry event") ||
    hay.includes("capture() takes 1 positional argument");
}

function effectiveFlowStatus(node) {
  if (!node || !node.length) return "idle";
  const raw = node.data("runtimeStatus") || "idle";
  const updatedAt = node.data("runtimeUpdatedAt") || "";
  if (flowStatusIsStale(raw, updatedAt)) return "idle";
  const source = node.data("runtimeSource") || "";
  const message = node.data("runtimeMessage") || "";
  if (raw === "error" && isFlowNoiseMessage(message, source)) return "warning";
  return raw;
}

function highestFlowStatus(nodes) {
  let winner = null;
  for (const node of nodes) {
    if (!node || !node.length) continue;
    if (!winner || (FLOW_STATUS_ORDER[effectiveFlowStatus(node)] || 0) > (FLOW_STATUS_ORDER[effectiveFlowStatus(winner)] || 0)) {
      winner = node;
    }
  }
  return winner;
}

function refreshFlowGroupToggleButtons() {
  const hud = document.getElementById("flowHudGroups");
  const parts = [];
  for (const [groupKey, cfg] of Object.entries(FLOW_GROUPS)) {
    const btn = document.getElementById(`flowGroupBtn-${groupKey}`);
    if (btn) {
      btn.classList.toggle("collapsed", !!_flowCollapsedGroups[groupKey]);
      btn.classList.toggle("active", !_flowCollapsedGroups[groupKey]);
      btn.textContent = `${cfg.label} ${_flowCollapsedGroups[groupKey] ? "▸" : "▾"}`;
    }
    parts.push(`${cfg.label} ${_flowCollapsedGroups[groupKey] ? "zu" : "offen"}`);
  }
  if (hud) hud.textContent = `Gruppen: ${parts.join(" · ")}`;
}

function refreshFlowGroupSummaries() {
  if (!flowCy) return;
  for (const [groupKey, cfg] of Object.entries(FLOW_GROUPS)) {
    const summaryNode = flowCy.getElementById(cfg.summaryNode);
    if (!summaryNode.length) continue;
    const memberNodes = cfg.children.map(id => flowCy.getElementById(id)).filter(node => node.length);
    const topNode = highestFlowStatus(memberNodes);
    const topStatus = topNode ? effectiveFlowStatus(topNode) : "idle";
    const activeCount = memberNodes.filter(node => {
      const status = effectiveFlowStatus(node);
      return status === "running" || status === "warning" || status === "error";
    }).length;
    const message = topNode
      ? `${cfg.label}: ${activeCount} aktive Hotspots.\nFokus: ${topNode.data("label")}\n${topNode.data("runtimeMessage") || ""}`.trim()
      : `${cfg.label}: keine Laufzeitdaten.`;
    setFlowNodeRuntime(cfg.summaryNode, {
      status: topStatus,
      message,
      source: `group:${cfg.label}`,
      updatedAt: topNode ? topNode.data("runtimeUpdatedAt") : "",
      force: true,
    });
  }
}

function applyFlowGroupState(groupKey) {
  if (!flowCy || !FLOW_GROUPS[groupKey]) return;
  const cfg = FLOW_GROUPS[groupKey];
  const collapsed = !!_flowCollapsedGroups[groupKey];
  const parentNode = flowCy.getElementById(cfg.parent);
  const summaryNode = flowCy.getElementById(cfg.summaryNode);
  const childSet = new Set(cfg.children);

  if (parentNode.length) parentNode.style("display", collapsed ? "none" : "element");
  if (summaryNode.length) summaryNode.style("display", collapsed ? "element" : "none");

  cfg.children.forEach(nodeId => {
    const node = flowCy.getElementById(nodeId);
    if (node.length) node.style("display", collapsed ? "none" : "element");
  });

  flowCy.edges().forEach(edge => {
    const edgeId = edge.id();
    const isSummaryEdge = cfg.summaryEdges.includes(edgeId);
    const touchesChild = childSet.has(edge.source().id()) || childSet.has(edge.target().id());
    const touchesParent = edge.source().id() === cfg.parent || edge.target().id() === cfg.parent;
    if (isSummaryEdge) {
      edge.style("display", collapsed ? "element" : "none");
    } else if (touchesChild || touchesParent) {
      edge.style("display", collapsed ? "none" : "element");
    }
  });

  if (collapsed && _flowActiveDetailNodeId && childSet.has(_flowActiveDetailNodeId)) {
    openFlowDetail(cfg.summaryNode);
  }
}

function applyAllFlowGroupStates() {
  refreshFlowGroupSummaries();
  Object.keys(FLOW_GROUPS).forEach(applyFlowGroupState);
  refreshFlowGroupToggleButtons();
}

function toggleFlowGroup(groupKey) {
  if (!FLOW_GROUPS[groupKey]) return;
  _flowCollapsedGroups[groupKey] = !_flowCollapsedGroups[groupKey];
  applyFlowGroupState(groupKey);
  refreshFlowGroupSummaries();
  refreshFlowEdgeStates();
  refreshFlowGroupToggleButtons();
  if (flowCy) flowCy.fit(80);
}

function initFlowGraph() {
  const container = document.getElementById("flow-cy");
  if (!container) return;
  if (_flowGraphInited && flowCy) {
    flowCy.resize();
    flowCy.fit(60);
    reloadFlowRuntime();
    return;
  }
  _flowGraphInited = true;
  const { nodes, edges } = buildArchitectureFlowElements();

  flowCy = cytoscape({
    container,
    userZoomingEnabled: true,
    userPanningEnabled: true,
    elements: { nodes, edges },
    style: [
      {
        selector: "node",
        style: {
          "background-color":  "data(renderBg)",
          "border-color":      "data(renderBorder)",
          "border-width":      2,
          "label":             "data(label)",
          "color":             "#e4f8ef",
          "font-family":       "JetBrains Mono, monospace",
          "font-size":         "9.5px",
          "font-weight":       "500",
          "text-valign":       "center",
          "text-halign":       "center",
          "width":             "data(w)",
          "height":            "data(h)",
          "shape":             "roundrectangle",
          "text-wrap":         "wrap",
          "text-max-width":    "data(w)",
          "padding":           "8px",
          "shadow-blur":       "data(renderBlur)",
          "shadow-color":      "data(renderGlow)",
          "shadow-opacity":    "data(renderOpacity)",
          "shadow-offset-x":   0,
          "shadow-offset-y":   0,
          "text-outline-width": 0,
        },
      },
      {
        selector: "node[isGroup = 1]",
        style: {
          "shape": "roundrectangle",
          "background-color": "data(baseBg)",
          "background-opacity": 0.16,
          "border-color": "data(baseBorder)",
          "border-width": 1.2,
          "border-style": "dashed",
          "label": "data(label)",
          "font-size": "11px",
          "font-weight": 700,
          "color": "#9bd0bf",
          "text-valign": "top",
          "text-halign": "left",
          "text-margin-x": 14,
          "text-margin-y": 12,
          "padding": 28,
          "min-width": "data(zoneMinW)",
          "min-height": "data(zoneMinH)",
          "shadow-opacity": 0,
        },
      },
      {
        selector: "node[isSummary = 1]",
        style: {
          "border-style": "dashed",
          "border-width": 2.4,
          "font-size": "10px",
          "font-weight": 700,
          "background-opacity": 0.92,
        },
      },
      {
        selector: "edge",
        style: {
          "line-color":         "data(renderColor)",
          "target-arrow-color": "data(renderColor)",
          "target-arrow-shape": "triangle",
          "curve-style":        "unbundled-bezier",
          "width":              "data(renderWidth)",
          "opacity":            "data(renderOpacity)",
          "arrow-scale":        0.9,
          "control-point-distances": [25, -25],
          "control-point-weights": [0.25, 0.75],
          "line-dash-offset":   "data(renderDashOffset)",
        },
      },
      {
        selector: "edge.flow-edge-dashed",
        style: {
          "line-style": "dashed",
          "target-arrow-shape": "triangle",
          "target-arrow-fill": "hollow",
        },
      },
      {
        selector: "edge.flow-edge-alert",
        style: {
          "line-style": "dashed",
          "line-dash-pattern": [10, 6],
          "shadow-color": "data(renderColor)",
          "shadow-opacity": 0.72,
          "shadow-blur": 18,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-width": 4,
          "overlay-opacity": 0,
          "shadow-opacity": 1,
          "shadow-blur": 34,
        },
      },
    ],
    layout: {
      name:     "preset",
      padding:  46,
      fit:      false,
    },
  });

  flowCy.on("tap", "node", evt => openFlowDetail(evt.target.id()));
  flowCy.on("tap", evt => {
    if (evt.target === flowCy) closeFlowDetail();
  });

  applyAllFlowGroupStates();
  flowCy.fit(80);

  // Minimap initialisieren (falls cytoscape-navigator geladen)
  try {
    if (!_flowNavigatorInited && flowCy.navigator) {
      flowCy.navigator({ container: "#flow-minimap", viewLiveFramerate: 0, thumbnailEventFramerate: 30 });
      _flowNavigatorInited = true;
    }
  } catch (_) {}

  // Sync Flow-Beam-Overlay
  syncFlowBeamOverlay();
  if (!_flowResizeObserver && window.ResizeObserver) {
    _flowResizeObserver = new ResizeObserver(() => {
      syncFlowBeamOverlay();
      if (flowCy) flowCy.resize();
    });
    _flowResizeObserver.observe(container);
  }
  resetFlowRuntime();
  reloadFlowRuntime();
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
  const src = flowAliasToNodeId(fromId) || fromId;
  const tgt = flowAliasToNodeId(toId) || toId;

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
        const flashColorMap = { running: "#00d4f0", completed: "#00e676", warning: "#fbbf24", error: "#ff1744" };
        const col = flashColorMap[status] || flashColorMap.running;
        node.style({ "border-color": col, "border-width": 4, "shadow-color": col, "shadow-opacity": 0.95, "shadow-blur": 26 });
        pulseFlowPath([src, tgt], status);
        setTimeout(() => {
          if (!node.removed()) {
            node.style({
              "border-color": node.data("renderBorder") || node.data("baseBorder") || "#243748",
              "border-width": node.selected() ? 4 : 2,
              "shadow-color": node.data("renderGlow") || node.data("baseGlow"),
              "shadow-opacity": node.data("renderOpacity") || 0.45,
              "shadow-blur": node.data("renderBlur") || 18,
            });
          }
        }, 700);
      }
    }
  }

  _flowBeamRAF = requestAnimationFrame(draw);
}

async function reloadFlowRuntime() {
  if (!flowCy) return;
  const canvasId = selectedCanvasId || document.getElementById("attachCanvasId").value.trim();
  resetFlowRuntime();
  if (!canvasId) return;
  const out = await api(`/canvas/${encodeURIComponent(canvasId)}?event_limit=180`).catch(() => null);
  if (!out || !out.canvas) return;

  const canvas = out.canvas;
  const nodes = Object.values(canvas.nodes || {});
  for (const item of nodes) {
    const mapped = resolveFlowNodeIds({
      nodeId: item.id,
      node_id: item.id,
      title: item.title,
      status: item.status,
      message: JSON.stringify(item.metadata || {}),
      payload: item.metadata || {},
    });
    mapped.forEach(nodeId => setFlowNodeRuntime(nodeId, {
      status: item.status,
      message: item.title || JSON.stringify(item.metadata || {}),
      source: `canvas.node:${item.id}`,
      updatedAt: item.updated_at || "",
    }));
  }

  const orderedEvents = (canvas.events || []).slice().reverse();
  for (const ev of orderedEvents) {
    const message = [ev.message || "", JSON.stringify(ev.payload || {})].filter(Boolean).join("\n");
    const mapped = resolveFlowNodeIds({
      type: ev.type,
      agent: ev.agent,
      nodeId: ev.node_id,
      node_id: ev.node_id,
      status: ev.status,
      message,
      payload: ev.payload || {},
    });
    mapped.forEach(nodeId => setFlowNodeRuntime(nodeId, {
      status: ev.status || ev.type,
      message: ev.message || ev.type || "",
      source: `canvas.event:${ev.type || "event"}`,
      updatedAt: ev.created_at || "",
    }));
  }

  expireStaleFlowRuntime();
  const latestEvent = canvas.events && canvas.events[0];
  _flowLastRuntimeSummary = {
    active: flowCy.nodes().filter(node => node.data("runtimeStatus") === "running").length,
    errors: flowCy.nodes().filter(node => ["warning", "error"].includes(node.data("runtimeStatus"))).length,
    latest: latestEvent ? `${latestEvent.type || "event"}: ${latestEvent.message || latestEvent.status || "Aktualisiert"}` : "",
  };
  refreshFlowGroupSummaries();
  applyAllFlowGroupStates();
  refreshFlowEdgeStates();
  refreshFlowHud(canvas.events || []);
  if (_flowActiveDetailNodeId) openFlowDetail(_flowActiveDetailNodeId);
}

function handleFlowRuntimeEvent(d) {
  if (!flowCy || !d || d.type === "ping" || d.type === "init") return;
  const status = d.status || (d.type === "chat_error" ? "error" : d.type === "tool_done" ? "completed" : "running");
  const message = d.error || d.message || d.text || d.tool || d.type || "";
  const mapped = resolveFlowNodeIds({
    type: d.type,
    agent: d.agent,
    from: d.from,
    to: d.to,
    nodeId: d.node_id,
    node_id: d.node_id,
    tool: d.tool,
    status,
    message,
    error: d.error,
    payload: d,
  });
  if (!mapped.length) return;

  mapped.forEach(nodeId => setFlowNodeRuntime(nodeId, {
    status,
    message,
    source: `sse:${d.type}`,
    updatedAt: new Date().toISOString(),
    force: status === "error" || status === "warning",
  }));

  if (d.type === "delegation") {
    const path = [
      "AR",
      flowAliasToNodeId(d.from) || "",
      flowAliasToNodeId(d.to) || "",
      "ARPA",
    ].filter(Boolean);
    pulseFlowPath(path, status);
  } else {
    pulseFlowPath(mapped, status);
  }

  _flowLastRuntimeSummary = {
    active: flowCy.nodes().filter(node => node.data("runtimeStatus") === "running").length,
    errors: flowCy.nodes().filter(node => ["warning", "error"].includes(node.data("runtimeStatus"))).length,
    latest: `${d.type}: ${message || status}`,
  };
  refreshFlowGroupSummaries();
  applyAllFlowGroupStates();
  refreshFlowEdgeStates();
  refreshFlowHud();
  if (_flowActiveDetailNodeId && mapped.includes(_flowActiveDetailNodeId)) openFlowDetail(_flowActiveDetailNodeId);
}

// ── Canvas List ───────────────────────────────────────────────────────────────
async function loadCanvasList() {
  const { items = [] } = await api("/canvas?limit=200").catch(() => ({ items: [] }));
  applyMobileCanvasSummary(items);
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
      if (activeTab === "flow") reloadFlowRuntime();
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
      if (activeTab === "flow") reloadFlowRuntime();
      if (_pollTick % Math.ceil(30000/POLL_MS) === 0) {
        loadScorecard().catch(() => {});
        loadMobileSnapshot().catch(() => {});
      }
    }, POLL_MS);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  document.getElementById("pollMs").textContent = String(POLL_MS);
  syncMobileLayout();
  updateLiveConnectionState(navigator.onLine ? "warn" : "error", navigator.onLine ? "bereit" : "offline");
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
  try { await loadMobileSnapshot(); } catch {}
  try { await loadRecentFiles(); } catch {}
  try { await loadVoiceStatus(); } catch {}

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
  window.addEventListener("resize", syncMobileLayout);
  window.addEventListener("online", () => {
    updateLiveConnectionState("warn", "reconnect");
    if (!sseConnected) connectSSE();
    refreshMobileOperationalData().catch(() => {});
  });
  window.addEventListener("offline", () => updateLiveConnectionState("error", "offline"));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      refreshMobileOperationalData().catch(() => {});
      if (!sseConnected) connectSSE();
    }
  });
  document.getElementById("mobileVoiceOrbBtn")?.addEventListener("click", toggleMobileVoice);
  const voicePlayer = document.getElementById("voicePlayer");
  if (voicePlayer) {
    voicePlayer.addEventListener("ended", () => {
      updateMobileVoiceState(window.voiceActive ? "listening" : "idle");
      updateVoiceControlState();
      if (window.voiceActive) setTimeout(startMic, 450);
    });
    voicePlayer.addEventListener("error", () => {
      updateMobileVoiceState("error");
      updateVoiceControlState();
    });
  }
  updateVoiceControlState();

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
      if (activeTab === "flow") await reloadFlowRuntime();
    } catch (err) { alert("Fehler: " + err.message); }
  });

  document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadCanvasList(); await reloadGraph();
    if (activeTab === "flow") await reloadFlowRuntime();
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
      if (activeTab === "flow") await reloadFlowRuntime();
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
  handleFlowRuntimeEvent(d);
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
  if (d.type === "thinking") {
    updateMobileVoiceState(d.active ? "thinking" : (window.voiceActive ? "listening" : "idle"));
  }
  if (d.type === "chat_reply" || d.type === "voice_speaking_start") {
    updateMobileVoiceState("speaking");
  }
  if (d.type === "voice_speaking_end" && d.mode !== "browser") {
    updateMobileVoiceState(window.voiceActive ? "listening" : "idle");
  }
  // Timus Voice System: Voice-Events an Mic IIFE weiterleiten
  if (window.onVoiceSSE) window.onVoiceSSE(d);
  // Auto-Speak: Wenn Sprach-Modus aktiv, Antwort automatisch vorlesen
  if (d.type === "chat_reply" && window.voiceActive && voiceAutoReply && d.text) {
    browserSpeakText(d.text).catch(() => {});
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
  let mediaRecorder = null;
  let recordedChunks = [];
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
      loadVoiceStatus().catch(() => {});
      updateMobileVoiceState("thinking");
      transcript.textContent = "⏳ " + (d.message || "…");
      transcript.classList.add("visible");
    }
    if (d.type === "voice_listening_start") {
      updateMobileVoiceState("listening");
      transcript.textContent = "● Höre zu…";
      transcript.classList.add("visible");
    }
    if (d.type === "voice_listening_stop") {
      updateMobileVoiceState(window.voiceActive ? "listening" : "idle");
      transcript.classList.remove("visible");
    }
    if (d.type === "voice_transcript" && d.source !== "browser_upload") {
      stopLevelLoop();
      listening = false;
      micBtn.classList.remove("listening");
      micBtn.title = "Mikrofon ein/aus (Shift+M)";
      updateMobileVoiceState("thinking");
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
      updateMobileVoiceState("error");
      transcript.textContent = "Fehler: " + (d.error || "unbekannt");
      transcript.classList.add("visible");
      setTimeout(() => {
        transcript.classList.remove("visible");
        updateMobileVoiceState(window.voiceActive ? "listening" : "idle");
      }, 4000);
      stopLevelLoop();
      listening = false;
      micBtn.classList.remove("listening");
      micBtn.title = "Mikrofon ein/aus (Shift+M)";
    }
    // Nach dem Sprechen: im Sprach-Modus automatisch wieder lauschen
    if (d.type === "voice_speaking_end" && d.mode !== "browser" && window.voiceActive && !listening) {
      setTimeout(startMic, 900);
    }
  };

  async function transcribeRecordedAudio(audioBlob) {
    const form = new FormData();
    const mime = audioBlob?.type || "audio/webm";
    const ext = mime.includes("ogg") ? "ogg" : mime.includes("mp4") || mime.includes("m4a") ? "m4a" : mime.includes("wav") ? "wav" : "webm";
    form.append("file", audioBlob, `voice-input.${ext}`);

    updateMobileVoiceState("thinking");
    transcript.textContent = "⏳ Transkribiere…";
    transcript.classList.add("visible");

    const r = await fetch("/voice/transcribe", { method: "POST", body: form });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      throw new Error(data.error || ("HTTP " + r.status));
    }

    const text = (data.text || "").trim();
    if (text) {
      chatInput.value = text;
      chatInput.style.height = "auto";
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
      transcript.textContent = "Erkannt: " + text;
      transcript.classList.add("visible");
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

  // ── Timus Voice System starten (Browser-Mikro → Whisper über Server) ─────
  async function startMic() {
    if (listening) return;
    listening = true;
    window.voiceActive = true;
    micBtn.classList.add("listening");
    micBtn.title = "Mikrofon aktiv — klicken zum Stoppen";
    updateMobileVoiceState("listening");
    transcript.textContent = "● Aufnahme läuft…";
    transcript.classList.add("visible");

    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      recordedChunks = [];
      mediaRecorder = new MediaRecorder(micStream);
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      };
      mediaRecorder.onstop = async () => {
        const chunkType = recordedChunks[0]?.type || mediaRecorder?.mimeType || "audio/webm";
        const audioBlob = new Blob(recordedChunks, { type: chunkType });
        recordedChunks = [];
        try {
          await transcribeRecordedAudio(audioBlob);
        } catch (err) {
          updateMobileVoiceState("error");
          transcript.textContent = "Mikrofon-Fehler: " + err.message;
          transcript.classList.add("visible");
          setTimeout(() => transcript.classList.remove("visible"), 5000);
        }
      };
      mediaRecorder.start();
      startLevelLoop(micStream);
    } catch (err) {
      transcript.textContent = "Mikrofon-Fehler: " + err.message;
      transcript.classList.add("visible");
      setTimeout(() => transcript.classList.remove("visible"), 5000);
      stopLevelLoop();
      listening = false;
      window.voiceActive = false;
      micBtn.classList.remove("listening");
      micBtn.title = "Mikrofon ein/aus (Shift+M)";
      updateMobileVoiceState("error");
    }
  }

  function stopMic() {
    if (!listening && !window.voiceActive) return;
    listening = false;
    micBtn.classList.remove("listening");
    micBtn.title = "Mikrofon ein/aus (Shift+M)";
    updateMobileVoiceState("thinking");
    transcript.textContent = "⏳ Aufnahme wird verarbeitet…";
    transcript.classList.add("visible");
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    stopLevelLoop();
    mediaRecorder = null;
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
