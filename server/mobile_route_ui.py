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
      display: flex;
      flex-direction: column;
      height: 100%;
      gap: 8px;
      padding: 10px;
    }
    .card {
      border-radius: 18px;
      border: 1px solid var(--border);
      background: rgba(12, 28, 45, 0.94);
      box-shadow: 0 10px 30px rgba(0,0,0,0.28);
    }
    .map-stage {
      position: relative;
      flex: 1 1 auto;
      min-height: 320px;
      overflow: hidden;
    }
    .map-hud {
      position: absolute;
      top: 10px;
      left: 10px;
      right: auto;
      width: min(300px, calc(100% - 20px));
      z-index: 6;
      display: grid;
      gap: 6px;
      pointer-events: none;
    }
    .map-hud-card {
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(12, 28, 45, 0.88);
      box-shadow: 0 10px 24px rgba(0,0,0,0.22);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      pointer-events: auto;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 10px 6px;
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
      font-size: 11px;
    }
    .title span {
      color: var(--muted);
      font-size: 11px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 10px 8px;
    }
    .chip,
    .btn {
      min-height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(6, 17, 27, 0.72);
      color: var(--text);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      font-size: 11px;
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
      padding: 0 10px 8px;
      display: grid;
      gap: 2px;
      color: var(--muted);
      font-size: 10px;
      line-height: 1.35;
    }
    .map-wrap {
      position: relative;
      min-height: 0;
      height: 100%;
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
      display: none;
      padding: 6px 12px 10px;
      color: var(--muted);
      font-size: 11px;
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="card map-wrap map-stage">
      <div class="map-hud">
        <div class="map-hud-card">
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
        </div>
      </div>
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
    let directionsService = null;
    let directionsCache = { key: "", path: [], promise: null };
    let map = null;
    let routePolyline = null;
    let stepPolyline = null;
    let startMarker = null;
    let endMarker = null;
    let liveMarker = null;
    let lastRoute = null;
    let lastLocation = null;
    let followEnabled = true;
    let staticImageObjectUrl = null;
    const query = new URLSearchParams(window.location.search);
    const forceStaticSurface = query.get("client") === "android" || query.get("surface") === "static";

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

    async function showStaticMap(route) {
      const image = document.getElementById("mapImage");
      const mapEl = document.getElementById("map");
      if (!image || !mapEl) return;
      mapEl.classList.remove("visible");
      image.classList.add("visible");
      const stamp = encodeURIComponent(String((route || {}).saved_at || Date.now()));
      const target = "/location/route/map?ts=" + stamp;
      try {
        const response = await fetch(target, { cache: "no-store" });
        if (!response.ok) {
          throw new Error("map_http_" + response.status);
        }
        const blob = await response.blob();
        if (staticImageObjectUrl) {
          URL.revokeObjectURL(staticImageObjectUrl);
          staticImageObjectUrl = null;
        }
        staticImageObjectUrl = URL.createObjectURL(blob);
        image.src = staticImageObjectUrl;
      } catch (error) {
        image.removeAttribute("src");
        setOverlay("Kartenvorschau konnte nicht geladen werden: " + (error?.message || error));
      }
    }

    function showInteractiveSurface() {
      const image = document.getElementById("mapImage");
      const mapEl = document.getElementById("map");
      if (image) image.classList.remove("visible");
      if (mapEl) mapEl.classList.add("visible");
    }

    function routePathCoordinates(route) {
      const rawPoints = Array.isArray((route || {}).path_coordinates) ? route.path_coordinates : [];
      const points = [];
      rawPoints.forEach((value) => {
        const point = coords(value);
        if (!point) return;
        const previous = points[points.length - 1];
        if (
          previous &&
          Math.abs(previous.lat - point.lat) < 0.0000001 &&
          Math.abs(previous.lng - point.lng) < 0.0000001
        ) {
          return;
        }
        points.push(point);
      });
      return points;
    }

    function routeHasInteractiveGeometry(route) {
      const origin = coords((route || {}).start_coordinates || (route || {}).origin || {});
      const destination = coords((route || {}).end_coordinates || {});
      const destinationLabel = String(
        (route || {}).destination_label ||
        (route || {}).end_address ||
        (route || {}).destination_query ||
        ""
      ).trim();
      return Boolean(
        String((route || {}).overview_polyline || "").trim() ||
        routePathCoordinates(route).length > 1 ||
        (origin && (destination || destinationLabel))
      );
    }

    function directionsCacheKey(route) {
      if (!route || !route.has_route) return "";
      return JSON.stringify({
        savedAt: String(route.saved_at || ""),
        reroutedAt: String(route.last_reroute_at || ""),
        travelMode: String(route.travel_mode || "driving"),
        destinationLabel: String(route.destination_label || route.end_address || route.destination_query || ""),
        origin: coords(route.start_coordinates || route.origin || {}),
        destination: coords(route.end_coordinates || {}),
      });
    }

    function travelModeForRoute(maps, route) {
      const normalized = String((route || {}).travel_mode || "driving").trim().toLowerCase();
      const travelMode = maps?.TravelMode || {};
      if (normalized === "walking") return travelMode.WALKING || "WALKING";
      if (normalized === "bicycling") return travelMode.BICYCLING || "BICYCLING";
      if (normalized === "transit") return travelMode.TRANSIT || "TRANSIT";
      return travelMode.DRIVING || "DRIVING";
    }

    function normalizeLatLng(value) {
      if (!value) return null;
      if (typeof value.lat === "function" && typeof value.lng === "function") {
        return { lat: value.lat(), lng: value.lng() };
      }
      return coords(value);
    }

    async function computeBrowserRoutePath(maps, route) {
      const cacheKey = directionsCacheKey(route);
      if (!cacheKey || !maps?.DirectionsService) return [];
      if (directionsCache.key === cacheKey) {
        if (Array.isArray(directionsCache.path) && directionsCache.path.length) return directionsCache.path;
        if (directionsCache.promise) {
          try {
            return await directionsCache.promise;
          } catch {
            return [];
          }
        }
      }

      const origin = coords(route.start_coordinates || route.origin || {});
      const destination = coords(route.end_coordinates || {});
      const destinationLabel = String(
        route.destination_label || route.end_address || route.destination_query || ""
      ).trim();
      if (!origin || (!destination && !destinationLabel)) return [];

      directionsService = directionsService || new maps.DirectionsService();
      const request = {
        origin,
        destination: destination || destinationLabel,
        travelMode: travelModeForRoute(maps, route),
        provideRouteAlternatives: false,
      };
      if (maps.UnitSystem?.METRIC) request.unitSystem = maps.UnitSystem.METRIC;
      if (String(route.language_code || "").trim()) request.region = String(route.language_code).trim();

      const promise = new Promise((resolve) => {
        directionsService.route(request, (response, status) => {
          const okStatus = status === "OK" || status === maps.DirectionsStatus?.OK;
          if (!okStatus) {
            resolve([]);
            return;
          }
          const overviewPath = Array.isArray((response?.routes || [])[0]?.overview_path)
            ? response.routes[0].overview_path
            : [];
          resolve(
            overviewPath
              .map(normalizeLatLng)
              .filter(Boolean),
          );
        });
      });
      directionsCache = { key: cacheKey, path: [], promise };
      const path = await promise;
      directionsCache = { key: cacheKey, path, promise: null };
      return path;
    }

    async function decodeRoutePath(maps, route) {
      const polyline = String((route || {}).overview_polyline || "").trim();
      if (polyline && maps?.geometry?.encoding) {
        try {
          const decoded = maps.geometry.encoding.decodePath(polyline) || [];
          if (decoded.length) return decoded;
        } catch {}
      }
      const browserPath = await computeBrowserRoutePath(maps, route);
      if (browserPath.length) return browserPath;
      return routePathCoordinates(route);
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

    function settleMapViewport(maps, bounds) {
      if (!map) return;
      const applyViewport = () => {
        if (!map) return;
        if (followEnabled) {
          const live = activeLiveLocation();
          if (live) {
            map.panTo(live);
            const zoom = Number(map.getZoom() || 0);
            if (zoom < 15) map.setZoom(15);
            return;
          }
        }
        if (bounds && !bounds.isEmpty()) {
          map.fitBounds(bounds, 36);
        }
      };
      if (maps.event?.trigger) {
        maps.event.trigger(map, "resize");
      }
      applyViewport();
      window.setTimeout(() => {
        if (maps.event?.trigger) {
          maps.event.trigger(map, "resize");
        }
        applyViewport();
      }, 140);
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
        if (forceStaticSurface || !config.interactive_available || !routeHasInteractiveGeometry(route)) {
          await showStaticMap(route);
          hideOverlay();
          const footer = document.getElementById("footerNote");
          if (footer) {
            footer.textContent = forceStaticSurface
              ? "Android static live view aktiv."
              : "Static fallback aktiv · interaktive Route nicht verfuegbar.";
          }
          return;
        }

        const maps = await ensureGoogleLoaded().catch(() => null);
        if (!maps) {
          await showStaticMap(route);
          hideOverlay();
          const footer = document.getElementById("footerNote");
          if (footer) footer.textContent = "Static fallback aktiv · Google Maps JS derzeit nicht verfuegbar.";
          return;
        }

        const decodedPath = await decodeRoutePath(maps, route);
        if (!decodedPath.length) {
          await showStaticMap(route);
          hideOverlay();
          const footer = document.getElementById("footerNote");
          if (footer) footer.textContent = "Static fallback aktiv · Routengeometrie fehlt.";
          return;
        }

      showInteractiveSurface();

      if (!map) {
        map = new maps.Map(document.getElementById("map"), {
          center: decodedPath[0],
          zoom: 13,
          zoomControl: true,
          mapTypeControl: true,
          streetViewControl: false,
          fullscreenControl: true,
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
      showInteractiveSurface();
      settleMapViewport(maps, bounds);
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
