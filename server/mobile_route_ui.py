from __future__ import annotations


def build_mobile_route_ui_html(poll_ms: int = 10000) -> str:
    effective_poll_ms = max(5000, int(poll_ms))
    return _TEMPLATE.replace("__POLL_MS__", str(effective_poll_ms))


_TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
  <title>Timus Mobile Route</title>
  <style>
    :root {
      --bg: #06111b;
      --panel: #0c1c2d;
      --panel-strong: #10263a;
      --border: rgba(42,245,201,0.18);
      --text: #e9f7ff;
      --muted: #8fb0c7;
      --brand: #2af5c9;
      --accent: #1fd8ff;
      --warn: #ffc85c;
      --error: #ff5d67;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; }
    body {
      background: linear-gradient(180deg, #041019 0%, var(--bg) 100%);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }
    .shell {
      display: grid;
      grid-template-rows: auto auto 1fr;
      height: 100%;
      gap: 10px;
      padding: 12px;
    }
    .card {
      border-radius: 18px;
      border: 1px solid var(--border);
      background: rgba(12, 28, 45, 0.94);
      box-shadow: 0 10px 30px rgba(0,0,0,0.28);
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 14px;
    }
    .title {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .title strong {
      color: var(--brand);
      letter-spacing: 0.06em;
      text-transform: uppercase;
      font-size: 12px;
    }
    .title span {
      color: var(--muted);
      font-size: 12px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 0 14px 12px;
    }
    .chip,
    .btn {
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(6, 17, 27, 0.72);
      color: var(--text);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      font-size: 12px;
    }
    .btn {
      cursor: pointer;
      user-select: none;
    }
    .btn.active {
      border-color: rgba(42,245,201,0.42);
      background: rgba(42,245,201,0.10);
      color: var(--brand);
    }
    .btn.secondary.active {
      border-color: rgba(31,216,255,0.42);
      background: rgba(31,216,255,0.10);
      color: var(--accent);
    }
    .status {
      color: var(--muted);
      font-size: 12px;
    }
    .summary {
      padding: 0 14px 12px;
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .map-wrap {
      position: relative;
      min-height: 280px;
      overflow: hidden;
      border-radius: 20px;
      border: 1px solid rgba(255,255,255,0.05);
      background: linear-gradient(180deg, rgba(16,38,58,0.92) 0%, rgba(8,18,29,0.98) 100%);
    }
    #map {
      position: absolute;
      inset: 0;
      display: none;
    }
    #map.visible {
      display: block;
    }
    #mapImage {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: none;
    }
    #mapImage.visible {
      display: block;
    }
    #overlay {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 18px;
      color: var(--muted);
      background: rgba(5, 12, 19, 0.26);
    }
    .footer {
      padding: 10px 14px 14px;
      color: var(--muted);
      font-size: 11px;
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="card">
      <div class="topbar">
        <div class="title">
          <strong>Timus Navigation</strong>
          <span id="headline">Warte auf aktive Route…</span>
        </div>
        <div class="chip" id="presenceChip">Standort unbekannt</div>
      </div>
      <div class="toolbar">
        <button class="btn active" id="followBtn" type="button">Follow an</button>
        <button class="btn secondary" id="refreshBtn" type="button">Neu laden</button>
        <a class="btn" id="openMapsLink" href="#" target="_blank" rel="noopener noreferrer">Google Maps</a>
      </div>
      <div class="summary" id="summary">
        <div>Status wird geladen…</div>
      </div>
    </section>

    <section class="card map-wrap">
      <div id="map" aria-label="Interaktive Route"></div>
      <img id="mapImage" alt="Statische Route" loading="eager" />
      <div id="overlay">Route wird geladen…</div>
    </section>

    <div class="footer" id="footerNote">Mobile Route View · Timus pollt Route und Live-Standort automatisch.</div>
  </div>

  <script>
    const POLL_MS = __POLL_MS__;
    let mapConfig = null;
    let googlePromise = null;
    let map = null;
    let routePolyline = null;
    let stepPolyline = null;
    let startMarker = null;
    let endMarker = null;
    let liveMarker = null;
    let lastRoute = null;
    let lastLocation = null;
    let followEnabled = true;

    function api(path) {
      return fetch(path).then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || payload.message || response.statusText);
        return payload;
      });
    }

    function esc(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function coords(value) {
      if (!value || typeof value !== "object") return null;
      const lat = Number(value.latitude ?? value.lat);
      const lng = Number(value.longitude ?? value.lng ?? value.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
      return { lat, lng };
    }

    function activeLiveLocation() {
      const location = ((lastLocation || {}).location) || {};
      const presence = String(location.presence_status || "unknown").toLowerCase();
      if (!["live", "recent"].includes(presence)) return null;
      if (location.usable_for_context !== true) return null;
      const position = coords(location);
      if (!position) return null;
      return { ...position, presence, display_name: location.display_name || location.locality || "Aktueller Standort" };
    }

    function setOverlay(text) {
      const overlay = document.getElementById("overlay");
      if (!overlay) return;
      overlay.textContent = text || "";
      overlay.style.display = "flex";
    }

    function hideOverlay() {
      const overlay = document.getElementById("overlay");
      if (overlay) overlay.style.display = "none";
    }

    function showStaticMap(route) {
      const image = document.getElementById("mapImage");
      const mapEl = document.getElementById("map");
      if (!image || !mapEl) return;
      mapEl.classList.remove("visible");
      image.classList.add("visible");
      const stamp = encodeURIComponent(String((route || {}).saved_at || Date.now()));
      image.src = "/location/route/map?ts=" + stamp;
    }

    async function loadMapConfig() {
      if (mapConfig) return mapConfig;
      const payload = await api("/location/route/map_config");
      mapConfig = payload.config || {};
      return mapConfig;
    }

    async function ensureGoogleLoaded() {
      if (window.google && window.google.maps && window.google.maps.geometry) return window.google.maps;
      if (googlePromise) return googlePromise;
      const config = await loadMapConfig();
      if (!config.interactive_available || !config.browser_api_key) return null;
      googlePromise = new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-role="timus-mobile-route-google"]');
        if (existing) {
          existing.addEventListener("load", () => resolve(window.google?.maps || null), { once: true });
          existing.addEventListener("error", () => reject(new Error("google_script_failed")), { once: true });
          return;
        }
        const script = document.createElement("script");
        const params = new URLSearchParams({
          key: config.browser_api_key,
          v: "weekly",
          libraries: Array.isArray(config.js_libraries) && config.js_libraries.length ? config.js_libraries.join(",") : "geometry",
          language: config.language_code || "de",
        });
        script.src = "https://maps.googleapis.com/maps/api/js?" + params.toString();
        script.async = true;
        script.defer = true;
        script.dataset.role = "timus-mobile-route-google";
        script.onload = () => resolve(window.google?.maps || null);
        script.onerror = () => reject(new Error("google_script_failed"));
        document.head.appendChild(script);
      });
      return googlePromise;
    }

    function clearMapArtifacts() {
      [routePolyline, stepPolyline, startMarker, endMarker, liveMarker].forEach((entry) => {
        if (entry && entry.setMap) entry.setMap(null);
      });
      routePolyline = null;
      stepPolyline = null;
      startMarker = null;
      endMarker = null;
      liveMarker = null;
    }

    function renderSummary() {
      const summary = document.getElementById("summary");
      const headline = document.getElementById("headline");
      const chip = document.getElementById("presenceChip");
      const openMapsLink = document.getElementById("openMapsLink");
      const route = lastRoute || {};
      const location = ((lastLocation || {}).location) || {};
      const presence = String(location.presence_status || "unknown").toLowerCase();
      if (chip) chip.textContent = location.display_name ? `${location.display_name} · ${presence}` : `Standort ${presence}`;
      if (!route.has_route) {
        if (headline) headline.textContent = "Noch keine aktive Route";
        if (summary) summary.innerHTML = "<div>Lege zuerst in Timus eine Route an. Danach erscheint sie hier automatisch.</div>";
        if (openMapsLink) {
          openMapsLink.removeAttribute("href");
          openMapsLink.style.pointerEvents = "none";
          openMapsLink.style.opacity = "0.55";
        }
        return;
      }
      if (headline) headline.textContent = route.destination_label || route.end_address || route.destination_query || "Aktive Route";
      if (summary) {
        summary.innerHTML = [
          `<div><strong>Von</strong> ${esc(route.start_address || ((route.origin || {}).display_name) || "Start")}</div>`,
          `<div><strong>Nach</strong> ${esc(route.end_address || route.destination_query || "Ziel")}</div>`,
          `<div><strong>ETA</strong> ${esc(route.duration_text || "–")} · <strong>Distanz</strong> ${esc(route.distance_text || "–")} · <strong>Modus</strong> ${esc(route.travel_mode || "driving")}</div>`,
        ].join("");
      }
      if (openMapsLink) {
        openMapsLink.href = route.maps_url || route.route_url || "#";
        openMapsLink.style.pointerEvents = "";
        openMapsLink.style.opacity = "1";
      }
    }

    function renderLiveMarker(maps) {
      if (!map) return;
      const live = activeLiveLocation();
      if (!live) {
        if (liveMarker) {
          liveMarker.setMap(null);
          liveMarker = null;
        }
        return;
      }
      if (!liveMarker) {
        liveMarker = new maps.Marker({
          position: live,
          map,
          zIndex: 1200,
          title: `${live.display_name} (${live.presence})`,
          icon: {
            path: maps.SymbolPath.CIRCLE,
            scale: 7,
            fillColor: "#1fd8ff",
            fillOpacity: 0.96,
            strokeColor: "#041019",
            strokeWeight: 2,
          },
        });
      } else {
        liveMarker.setPosition(live);
        liveMarker.setTitle(`${live.display_name} (${live.presence})`);
      }
      if (followEnabled) {
        map.panTo(live);
        const zoom = Number(map.getZoom() || 0);
        if (zoom < 15) map.setZoom(15);
      }
    }

    async function renderRoute() {
      renderSummary();
      const route = lastRoute || {};
      const image = document.getElementById("mapImage");
      const mapEl = document.getElementById("map");
      if (!route.has_route) {
        clearMapArtifacts();
        if (image) image.classList.remove("visible");
        if (mapEl) mapEl.classList.remove("visible");
        setOverlay("Noch keine aktive Route. Erzeuge zuerst eine Route in Timus.");
        return;
      }

      const config = await loadMapConfig().catch(() => ({ interactive_available: false }));
        if (!config.interactive_available || !route.overview_polyline) {
          showStaticMap(route);
          hideOverlay();
          const footer = document.getElementById("footerNote");
          if (footer) footer.textContent = "Static fallback aktiv · interaktive Route nicht verfuegbar.";
          return;
        }

        const maps = await ensureGoogleLoaded().catch(() => null);
        if (!maps || !maps.geometry || !maps.geometry.encoding) {
          showStaticMap(route);
          hideOverlay();
          const footer = document.getElementById("footerNote");
          if (footer) footer.textContent = "Static fallback aktiv · Google Maps JS derzeit nicht verfuegbar.";
          return;
        }

        const decodedPath = maps.geometry.encoding.decodePath(route.overview_polyline || "");
        if (!decodedPath.length) {
          showStaticMap(route);
          hideOverlay();
          const footer = document.getElementById("footerNote");
          if (footer) footer.textContent = "Static fallback aktiv · Routengeometrie fehlt.";
          return;
        }

      if (!map) {
        map = new maps.Map(document.getElementById("map"), {
          center: decodedPath[0],
          zoom: 13,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
          clickableIcons: false,
          gestureHandling: "greedy",
          backgroundColor: "#07111a",
        });
      }

      clearMapArtifacts();
      routePolyline = new maps.Polyline({
        path: decodedPath,
        strokeColor: "#2af5c9",
        strokeOpacity: 0.88,
        strokeWeight: 6,
        map,
      });
      const start = coords(route.start_coordinates || route.origin || {});
      const end = coords(route.end_coordinates || {});
      if (start) {
        startMarker = new maps.Marker({ position: start, map, label: "S", title: route.start_address || "Start" });
      }
      if (end) {
        endMarker = new maps.Marker({ position: end, map, label: "Z", title: route.destination_label || route.end_address || "Ziel" });
      }
      const bounds = new maps.LatLngBounds();
      decodedPath.forEach((point) => bounds.extend(point));
      if (!bounds.isEmpty() && !followEnabled) {
        map.fitBounds(bounds, 52);
      }
      renderLiveMarker(maps);
      if (image) image.classList.remove("visible");
      if (mapEl) mapEl.classList.add("visible");
      hideOverlay();
      const footer = document.getElementById("footerNote");
      if (footer) {
        footer.textContent = `${route.source_provider || "provider"} · ${route.engine || "route"} · ${route.step_count || 0} Schritte · Follow ${followEnabled ? "an" : "aus"}`;
      }
    }

    async function refreshAll() {
      try {
        const [routePayload, locationPayload] = await Promise.all([
          api("/location/route/status"),
          api("/location/status"),
        ]);
        lastRoute = routePayload.route || {};
        lastLocation = locationPayload || {};
        await renderRoute();
      } catch (error) {
        setOverlay("Route konnte nicht geladen werden: " + error.message);
      }
    }

    function bindUi() {
      const followBtn = document.getElementById("followBtn");
      if (followBtn) {
        followBtn.addEventListener("click", () => {
          followEnabled = !followEnabled;
          followBtn.classList.toggle("active", followEnabled);
          followBtn.textContent = followEnabled ? "Follow an" : "Follow aus";
          renderRoute().catch(() => {});
        });
      }
      const refreshBtn = document.getElementById("refreshBtn");
      if (refreshBtn) {
        refreshBtn.addEventListener("click", () => refreshAll().catch(() => {}));
      }
    }

    bindUi();
    refreshAll().catch(() => {});
    setInterval(() => refreshAll().catch(() => {}), POLL_MS);
  </script>
</body>
</html>
"""
