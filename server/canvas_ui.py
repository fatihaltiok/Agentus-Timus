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
    #cy { flex: 1; background: transparent; }

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

    /* ── VOICE PULSE CANVAS ──────────────────────────────────────── */
    #voiceCanvas {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      pointer-events: none;
      z-index: 5;
      /* Größe wird per JS gesetzt */
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
      </div>

      <!-- Canvas Tab (position:relative für Voice-Canvas-Overlay) -->
      <div class="tab-content active" id="tab-canvas" style="position:relative;">
        <!-- Voice Pulse Canvas (zentriert, pointer-events:none) -->
        <canvas id="voiceCanvas" width="420" height="420"></canvas>
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
        <div id="cy"></div>
        <div class="node-detail" id="nodeDetail">
          <span class="nd-close" onclick="closeNodeDetail()">✕</span>
          <h4 id="ndTitle">–</h4>
          <div class="nd-row"><span class="nd-key">ID</span>    <span class="nd-val" id="ndId">–</span></div>
          <div class="nd-row"><span class="nd-key">Typ</span>   <span class="nd-val" id="ndType">–</span></div>
          <div class="nd-row"><span class="nd-key">Status</span><span class="nd-val" id="ndStatus">–</span></div>
        </div>
      </div>

      <!-- Autonomy Tab -->
      <div class="tab-content" id="tab-autonomy">
        <div class="autonomy-view">

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

// ── Autonomy Dashboard ────────────────────────────────────────────────────────
async function loadAutonomyData() {
  await Promise.allSettled([ loadScorecard(), loadGoals(), loadPlans() ]);
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
  cy.nodes().forEach(node => {
    if (node.data("label") === agent || node.data("agentName") === agent) {
      node.data("bgColor",     bg);
      node.data("borderColor", brd);
      node.data("status",      status);
    }
  });
}

async function reloadGraph() {
  if (!selectedCanvasId || !cy) return;
  try {
    const { canvas } = await api(`/canvas/${encodeURIComponent(selectedCanvasId)}`);
    if (!canvas) return;

    const agentSet   = new Set(AGENTS);
    const cyElements = [];

    for (const n of Object.values(canvas.nodes || {})) {
      const label      = n.title || n.id || "?";
      const liveStatus = agentSet.has(label) ? _agentStatusFromLed(label) : (n.status || "idle");
      cyElements.push({
        group: "nodes",
        data: {
          id:          "node-" + n.id,
          label,
          status:      liveStatus,
          bgColor:     STATUS_COLOR[liveStatus]  || STATUS_COLOR.idle,
          borderColor: STATUS_BORDER[liveStatus] || STATUS_BORDER.idle,
          type:        n.node_type || "generic",
          agentName:   agentSet.has(label) ? label : "",
        },
      });
    }
    for (const e of (canvas.edges || [])) {
      cyElements.push({
        group: "edges",
        data: { id:"edge-"+e.id, source:"node-"+e.source, target:"node-"+e.target, label:e.kind||"" },
      });
    }

    cy.elements().remove();
    cy.add(cyElements);
    cy.layout({ name: document.getElementById("cyLayout").value || "cose", padding: 40, animate: false }).run();
    cy.fit(40);
  } catch {}
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
