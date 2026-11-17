from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

STATIONS = {
    "IISC00IND": {"lat": 13.021, "lon": 77.570, "label": "IISC · Bengaluru"},
    "LCK400IND": {"lat": 26.846, "lon": 80.946, "label": "LCK4 · Lucknow"},
    "JDPR00IND": {"lat": 26.238, "lon": 73.024, "label": "JDPR · Jodhpur"},
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORRIDOR_FILE = PROJECT_ROOT / "data" / "geography" / "railway_corridor.geojson"
ION_HYBRID_IMAGERY_ASSET_ID = 3830183


def _read_geojson_route(path: Path) -> list[list[list[float]]]:
    """Read valid LineString segments without joining unrelated railway features."""
    if not path.exists():
        return []
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        lines: list[list[list[float]]] = []

        def visit(node: Any):
            if not isinstance(node, dict):
                return
            typ = node.get("type")
            if typ == "FeatureCollection":
                for feature in node.get("features", []):
                    visit(feature)
            elif typ == "Feature":
                visit(node.get("geometry"))
            elif typ == "GeometryCollection":
                for geom in node.get("geometries", []):
                    visit(geom)
            elif typ == "LineString":
                coords = node.get("coordinates", [])
                line = [[float(p[0]), float(p[1])] for p in coords
                        if isinstance(p, (list, tuple)) and len(p) >= 2]
                if len(line) >= 2:
                    lines.append(line)
            elif typ == "MultiLineString":
                for segment in node.get("coordinates", []):
                    line = [[float(p[0]), float(p[1])] for p in segment
                            if isinstance(p, (list, tuple)) and len(p) >= 2]
                    if len(line) >= 2:
                        lines.append(line)

        visit(obj)
        cleaned = []
        for line in lines:
            valid = [[lon, lat] for lon, lat in line
                     if -180 <= lon <= 180 and -90 <= lat <= 90]
            if len(valid) >= 2:
                cleaned.append(valid)
        return cleaned
    except Exception:
        return []


def render_india_view(
    station: str,
    sv: str,
    threat: str,
    confidence: float,
    forecast: float,
    show_all: bool = True,
    route_coordinates: list[list[float]] | None = None,
    ion_token: str | None = None,
    scenario: str = "Observed data (no injection)",
):
    selected = STATIONS.get(
        station, {"lat": 20.5937, "lon": 78.9629, "label": station}
    )
    stations_to_show = STATIONS if show_all else {station: selected}
    route_lines = _read_geojson_route(DEFAULT_CORRIDOR_FILE)
    if route_coordinates:
        route_lines = [route_coordinates]

    payload = json.dumps({
        "station": station,
        "sv": sv,
        "threat": threat,
        "scenario": scenario,
        "confidence": float(confidence),
        "forecast": float(forecast),
        "selected": selected,
        "stations": stations_to_show,
        "routeLines": route_lines,
        "ionToken": ion_token or "",
        "hybridAssetId": ION_HYBRID_IMAGERY_ASSET_ID,
    }, ensure_ascii=False).replace("</", "<\\/")

    html = r"""
    <div id="navic-shell">
      <div class="navic-toolbar">
        <div class="navic-title">India · Railway geography · GNSS reference stations</div>
        <div class="navic-buttons">
          <button id="navic-street" class="navic-btn">Street map</button>
          <button id="navic-satellite" class="navic-btn active">Satellite + labels</button>
          <button id="navic-ion" class="navic-btn">Cesium ion imagery</button>
          <button id="navic-home" class="navic-btn">India view</button>
        </div>
      </div>
      <style>
        #navic-shell{width:100%;font-family:Arial,sans-serif;color:#e5e7eb}
        .navic-toolbar{display:flex;gap:9px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:0 0 9px}
        .navic-title{font-size:13px;color:#cbd5e1}
        .navic-buttons{display:flex;gap:7px;flex-wrap:wrap}
        .navic-btn{border:1px solid #64748b;background:#172033;color:#fff;padding:8px 12px;border-radius:7px;cursor:pointer}
        .navic-btn.active{background:#31547c;border-color:#93c5fd}
        #navic-cesium{width:100%;height:650px;border-radius:12px;overflow:hidden;border:1px solid #475569;background:#142536}
        #navic-status{font-size:12px;line-height:1.5;color:#cbd5e1;margin-top:8px;padding:8px 10px;background:#111827;border:1px solid #334155;border-radius:7px}
        #navic-error{display:none;margin-top:8px;padding:9px 10px;background:#451a1a;color:#fecaca;border:1px solid #991b1b;border-radius:7px;font-size:12px;white-space:pre-wrap}
        #navic-cesium .cesium-viewer-bottom{left:8px}
      </style>
      <div id="navic-cesium"></div>
      <div id="navic-status">Initialising CesiumJS map…</div>
      <div id="navic-error"></div>
    </div>
    <link href="https://cesium.com/downloads/cesiumjs/releases/1.124/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
    <script src="https://cesium.com/downloads/cesiumjs/releases/1.124/Build/Cesium/Cesium.js"></script>
    <script>
    (() => {
      const d = __NAVIC_PAYLOAD__;
      const status = document.getElementById("navic-status");
      const errorBox = document.getElementById("navic-error");
      const btnStreet = document.getElementById("navic-street");
      const btnSatellite = document.getElementById("navic-satellite");
      const btnIon = document.getElementById("navic-ion");
      const btnHome = document.getElementById("navic-home");

      const setStatus = (s) => status.textContent = s;
      const showError = (s) => { errorBox.style.display = "block"; errorBox.textContent = s; };
      const clearError = () => { errorBox.style.display = "none"; errorBox.textContent = ""; };
      const activate = (btn) => {
        [btnStreet, btnSatellite, btnIon].forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      };

      if (!window.Cesium) {
        setStatus("CesiumJS could not be loaded.");
        showError("The CesiumJS script was blocked or unavailable. Allow access to cesium.com and reload.");
        return;
      }
      if (d.ionToken) Cesium.Ion.defaultAccessToken = d.ionToken;

      let viewer;
      try {
        viewer = new Cesium.Viewer("navic-cesium", {
          animation:false, timeline:false, baseLayerPicker:false, geocoder:false,
          homeButton:false, sceneModePicker:true, navigationHelpButton:false,
          infoBox:true, selectionIndicator:true, fullscreenButton:true,
          baseLayer:false, terrainProvider:new Cesium.EllipsoidTerrainProvider(),
          shouldAnimate:false, requestRenderMode:false
        });
      } catch (e) {
        setStatus("Cesium viewer initialisation failed.");
        showError(String(e && e.message ? e.message : e));
        return;
      }

      viewer.scene.globe.show = true;
      viewer.scene.globe.enableLighting = true;
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#263746");
      viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#07111f");
      viewer.scene.screenSpaceCameraController.minimumZoomDistance = 1500;
      viewer.scene.screenSpaceCameraController.maximumZoomDistance = 50000000;

      let streetLayer = null, satelliteLayer = null, labelLayer = null, ionLayer = null;
      const esriSatelliteUrl = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
      const esriLabelsUrl = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
      const osmUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

      function setBase(which) {
        if (streetLayer) streetLayer.show = which === "street";
        if (satelliteLayer) satelliteLayer.show = which === "satellite";
        if (labelLayer) labelLayer.show = which === "satellite";
        if (ionLayer) ionLayer.show = which === "ion";
        viewer.scene.requestRender();
      }

      async function showStreet() {
        clearError();
        try {
          if (!streetLayer) {
            streetLayer = viewer.imageryLayers.addImageryProvider(
              new Cesium.UrlTemplateImageryProvider({
                url: osmUrl, maximumLevel:19,
                credit:"© OpenStreetMap contributors"
              })
            );
          }
          setBase("street");
          activate(btnStreet);
          setStatus("OpenStreetMap street and railway context is active.");
        } catch (e) {
          setStatus("Street map failed to initialise.");
          showError(String(e && e.message ? e.message : e));
        }
      }

      async function showSatellite() {
        clearError();
        setStatus("Loading Esri World Imagery and geographic labels…");
        try {
          if (!satelliteLayer) {
            satelliteLayer = viewer.imageryLayers.addImageryProvider(
              new Cesium.UrlTemplateImageryProvider({
                url: esriSatelliteUrl, maximumLevel:19,
                credit:"Imagery © Esri"
              })
            );
            labelLayer = viewer.imageryLayers.addImageryProvider(
              new Cesium.UrlTemplateImageryProvider({
                url: esriLabelsUrl, maximumLevel:19,
                credit:"Labels © Esri"
              })
            );
          }
          setBase("satellite");
          activate(btnSatellite);
          setStatus("Esri satellite imagery with geographic labels is active.");
        } catch (e) {
          console.error("[NavIC] Esri imagery failed", e);
          await showStreet();
          showError("Esri imagery could not be initialised; OpenStreetMap fallback is active. " +
                    (e && e.message ? e.message : String(e)));
        }
      }

      async function showIon() {
        clearError();
        if (!d.ionToken) {
          await showSatellite();
          showError("Cesium ion token is not configured. Esri satellite imagery remains active. Add CESIUM_ION_TOKEN in .streamlit/secrets.toml to try ion-hosted imagery.");
          return;
        }
        setStatus("Requesting Cesium ion imagery asset…");
        try {
          if (!Cesium.IonImageryProvider || typeof Cesium.IonImageryProvider.fromAssetId !== "function") {
            throw new Error("This CesiumJS build does not expose IonImageryProvider.fromAssetId.");
          }
          if (!ionLayer) {
            const provider = await Cesium.IonImageryProvider.fromAssetId(d.hybridAssetId);
            ionLayer = viewer.imageryLayers.addImageryProvider(provider);
          }
          setBase("ion");
          activate(btnIon);
          setStatus("Cesium ion imagery asset loaded.");
        } catch (e) {
          console.error("[NavIC] Cesium ion imagery failed", e);
          await showSatellite();
          showError("The configured ion asset is not compatible or cannot be accessed. Switched to Esri satellite imagery. " +
                    (e && e.message ? e.message : String(e)));
        }
      }

      const threatColor = d.threat === "Spoofing" ? Cesium.Color.fromCssColorString("#ef4444") :
        (d.threat === "Multipath" ? Cesium.Color.fromCssColorString("#f59e0b") :
        Cesium.Color.fromCssColorString("#22c55e"));

      Object.entries(d.stations || {}).forEach(([code, s]) => {
        const selected = code === d.station;
        viewer.entities.add({
          id:"station-" + code,
          position:Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 150),
          point:{pixelSize:selected ? 17 : 12,
            color:selected ? threatColor : Cesium.Color.fromCssColorString("#22c55e"),
            outlineColor:Cesium.Color.WHITE, outlineWidth:2},
          label:{text:s.label, font:selected ? "bold 15px sans-serif" : "13px sans-serif",
            fillColor:Cesium.Color.WHITE, outlineColor:Cesium.Color.BLACK, outlineWidth:3,
            style:Cesium.LabelStyle.FILL_AND_OUTLINE,
            pixelOffset:new Cesium.Cartesian2(0,-24), showBackground:true,
            backgroundColor:Cesium.Color.BLACK.withAlpha(.72)},
          description:"GNSS observation reference station " + code +
            "; this is not a confirmed railway receiver installation."
        });
      });

      (d.routeLines || []).forEach((line, idx) => {
        if (!Array.isArray(line) || line.length < 2) return;
        const positions = line.map(p => Cesium.Cartesian3.fromDegrees(p[0],p[1],120));
        viewer.entities.add({
          id:"railway-corridor-" + idx,
          polyline:{positions:positions,width:4,
            material:new Cesium.PolylineGlowMaterialProperty({
              glowPower:0.16,color:Cesium.Color.fromCssColorString("#facc15")
            })},
          description:"Railway geometry loaded from the locally configured GeoJSON."
        });
      });

      // Schematic marker only; live NavIC ephemeris is not connected.
      const s = d.selected;
      const satLon = s.lon + 18.0;
      const satLat = Math.min(45.0, s.lat + 10.0);
      const satHeight = 35786000.0;
      viewer.entities.add({
        id:"schematic-navic-satellite",
        position:Cesium.Cartesian3.fromDegrees(satLon,satLat,satHeight),
        point:{pixelSize:13,color:Cesium.Color.CYAN,outlineColor:Cesium.Color.WHITE,outlineWidth:1},
        label:{text:"Schematic " + d.sv,font:"13px sans-serif",
          fillColor:Cesium.Color.CYAN,outlineColor:Cesium.Color.BLACK,outlineWidth:3,
          style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-20),
          showBackground:true,backgroundColor:Cesium.Color.BLACK.withAlpha(.65)},
        description:"Illustrative satellite marker, not derived from live NavIC ephemeris."
      });
      viewer.entities.add({
        id:"schematic-signal-link",
        polyline:{positions:[
          Cesium.Cartesian3.fromDegrees(s.lon,s.lat,150),
          Cesium.Cartesian3.fromDegrees(satLon,satLat,satHeight)
        ],width:2.5,material:new Cesium.PolylineDashMaterialProperty({color:threatColor,dashLength:14})},
        description:"Illustrative signal path, not computed from live satellite geometry."
      });
      viewer.entities.add({
        id:"selected-integrity-status",
        position:Cesium.Cartesian3.fromDegrees(s.lon,s.lat,18000),
        label:{text:d.threat + " · " + (d.confidence*100).toFixed(1) +
          "% · " + d.scenario + " · σφ proxy " + d.forecast.toFixed(2),
          font:"bold 13px sans-serif",fillColor:threatColor,outlineColor:Cesium.Color.BLACK,
          outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset:new Cesium.Cartesian2(0,28),showBackground:true,
          backgroundColor:Cesium.Color.BLACK.withAlpha(.75)}
      });

      const indiaRectangle = Cesium.Rectangle.fromDegrees(67.0,5.0,98.0,37.5);
      viewer.camera.flyTo({destination:indiaRectangle,duration:0.8});

      btnStreet.addEventListener("click",showStreet);
      btnSatellite.addEventListener("click",showSatellite);
      btnIon.addEventListener("click",showIon);
      btnHome.addEventListener("click",() =>
        viewer.camera.flyTo({destination:indiaRectangle,duration:0.8})
      );

      // Load a known public imagery source by default; ion is an optional layer.
      showSatellite();
      window.addEventListener("resize",() => viewer.resize());
      setTimeout(() => viewer.resize(),350);

      const segments = (d.routeLines || []).length;
      const vertices = (d.routeLines || []).reduce((n,line) => n + line.length,0);
      if (segments) console.info("[NavIC] GeoJSON corridor:",segments,"segments /",vertices,"vertices");
    })();
    </script>
    """.replace("__NAVIC_PAYLOAD__", payload)

    components.html(html, height=735, scrolling=False)
    return {
        "route_loaded": bool(route_lines),
        "route_vertices": sum(len(line) for line in route_lines),
        "route_segments": len(route_lines),
        "route_path": str(DEFAULT_CORRIDOR_FILE),
        "token_configured": bool(ion_token),
        "default_imagery": "Esri World Imagery + geographic labels",
        "ion_asset_id": ION_HYBRID_IMAGERY_ASSET_ID,
    }
