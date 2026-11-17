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



def _read_geojson_document(path: Path) -> tuple[dict[str, Any] | None, int]:
    """Load the complete railway GIS GeoJSON, preserving all supported geometry types."""
    if not path.exists():
        return None, 0
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        allowed = {
            "FeatureCollection", "Feature", "LineString", "MultiLineString",
            "Polygon", "MultiPolygon", "GeometryCollection", "Point", "MultiPoint"
        }
        if not isinstance(obj, dict) or obj.get("type") not in allowed:
            return None, 0
        count = len(obj.get("features", [])) if obj.get("type") == "FeatureCollection" else 1
        return obj, count
    except Exception:
        return None, 0


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
    railway_geojson, railway_feature_count = _read_geojson_document(DEFAULT_CORRIDOR_FILE)
    if route_coordinates:
        route_lines = [route_coordinates]
        # Preserve the app-provided corridor override, while keeping it in GeoJSON form
        # so Cesium can render it as part of the GIS overlay.
        railway_geojson = {
            "type": "Feature",
            "properties": {"name": "Railway corridor (provided route)"},
            "geometry": {"type": "LineString", "coordinates": route_coordinates},
        }
        railway_feature_count = 1

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
        "railwayGeoJSON": railway_geojson,
        "railwayFeatureCount": railway_feature_count,
        "ionToken": ion_token or "",
        "hybridAssetId": 3830183,
    }, ensure_ascii=False).replace("</", "<\\/")

    html = r"""
    <div id="navic-shell">
      <div class="navic-toolbar">
        <div class="navic-title">India · Railway geography · GNSS reference stations</div>
        <div class="navic-buttons">
          <button id="navic-street" class="navic-btn">Street map</button>
          <button id="navic-satellite" class="navic-btn active">Satellite + labels</button>
          <button id="navic-ion" class="navic-btn">Cesium ion imagery</button>
          <button id="navic-globe" class="navic-btn">3D Globe + satellites</button>
          <button id="navic-rail-toggle" class="navic-btn active">Railway GIS: on</button>
          <button id="navic-station-toggle" class="navic-btn active">Stations: on</button>
          <button id="navic-train-toggle" class="navic-btn active">Train: on</button>
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
    <link href="https://cesium.com/downloads/cesiumjs/releases/1.144/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
    <script src="https://cesium.com/downloads/cesiumjs/releases/1.144/Build/Cesium/Cesium.js"></script>
    <script>
    (() => {
      const d = __NAVIC_PAYLOAD__;
      const status = document.getElementById("navic-status");
      const errorBox = document.getElementById("navic-error");
      const btnStreet = document.getElementById("navic-street");
      const btnSatellite = document.getElementById("navic-satellite");
      const btnIon = document.getElementById("navic-ion");
      const btnHome = document.getElementById("navic-home");
      const btnGlobe = document.getElementById("navic-globe");
      const btnRailToggle = document.getElementById("navic-rail-toggle");
      const btnStationToggle = document.getElementById("navic-station-toggle");
      const btnTrainToggle = document.getElementById("navic-train-toggle");

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
        // Follow Cesium's official Viewer setup:
        // - ion asset 3830183 is the Google satellite + labels base imagery.
        // - World Terrain is streamed from Cesium ion when a token is configured.
        // Without a token, use the ellipsoid and the Esri imagery fallback below.
        const viewerOptions = {
          animation:false, timeline:false, baseLayerPicker:false, geocoder:false,
          homeButton:false, sceneModePicker:true, navigationHelpButton:false,
          infoBox:true, selectionIndicator:true, fullscreenButton:true,
          baseLayer:false,
          terrainProvider:new Cesium.EllipsoidTerrainProvider(),
          shouldAnimate:false, requestRenderMode:false
        };
        viewer = new Cesium.Viewer("navic-cesium", viewerOptions);
      } catch (e) {
        setStatus("Cesium viewer initialisation failed.");
        showError(String(e && e.message ? e.message : e));
        return;
      }

      viewer.scene.globe.show = true;
      viewer.scene.globe.enableLighting = true;
      viewer.scene.skyBox.show = true;
      viewer.scene.skyAtmosphere.show = true;
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
            const imageryProvider = await Cesium.IonImageryProvider.fromAssetId(3830183);
            ionLayer = viewer.imageryLayers.addImageryProvider(imageryProvider);
          }
          ionLayer.show = true;
          setBase("ion");
          activate(btnIon);
          setStatus("Cesium ion imagery loaded; zooming to imagery layer…");

          // Match the official Cesium imagery tutorial's camera step.
          const zoomSucceeded = await viewer.zoomTo(ionLayer);
          viewer.scene.globe.show = true;

          if (!zoomSucceeded) {
            throw new Error(
              "viewer.zoomTo(imageryLayer) returned false; Cesium did not complete the imagery-layer camera zoom."
            );
          }

          viewer.scene.requestRender();
          setStatus("Cesium ion imagery asset 3830183 loaded and camera zoomed to the imagery layer.");
        } catch (e) {
          console.error("[NavIC] Cesium ion imagery failed:", e);
          const ionErrorText = (e && e.message) ? e.message : String(e);

          // Switch to Esri, but do not leave the camera pointing into the sky.
          await showSatellite();
          viewer.scene.globe.show = true;
          viewer.scene.mode = Cesium.SceneMode.SCENE3D;
          flyToGlobe();
          viewer.scene.requestRender();

          showError(
            "Cesium ion imagery asset 3830183 failed. Esri fallback is active. " +
            "Ion error: " + ionErrorText
          );
          setStatus(
            "Ion imagery failed; switched to Esri fallback and reset camera to Earth. " +
            "Check the error panel / browser Console for the ion error."
          );
        }
      }

      const s = d.selected;

      const threatColor = d.threat === "Spoofing" ? Cesium.Color.fromCssColorString("#ef4444") :
        (d.threat === "Multipath" ? Cesium.Color.fromCssColorString("#f59e0b") :
        Cesium.Color.fromCssColorString("#22c55e"));

      const stationEntities = [];
      Object.entries(d.stations || {}).forEach(([code, s]) => {
        const selected = code === d.station;
        const stationEntity = viewer.entities.add({
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
        stationEntities.push(stationEntity);

        // Match the selected-station proximity ring used in the 2D Railway GIS map.
        if (selected) {
          const stationRange = viewer.entities.add({
            id:"station-range-" + code,
            position:Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 0),
            ellipse:{
              semiMajorAxis:25000,
              semiMinorAxis:25000,
              height:0,
              material:threatColor.withAlpha(0.06),
              outline:true,
              outlineColor:threatColor.withAlpha(0.75),
              outlineWidth:2
            },
            description:"Illustrative 25 km radius around the selected GNSS reference station; not a railway safety boundary."
          });
          stationEntities.push(stationRange);
        }
      });

      // Full railway GIS overlay: supports LineString, MultiLineString, polygons,
      // points, multipolygons and geometry collections from the same GeoJSON
      // used by the separate Leaflet railway GIS tab.
      let railwayDataSource = null;
      async function loadRailwayGIS() {
        if (!d.railwayGeoJSON) {
          setStatus("No railway GeoJSON found at data/geography/railway_corridor.geojson; basemap and stations remain available.");
          return;
        }
        try {
          railwayDataSource = await Cesium.GeoJsonDataSource.load(d.railwayGeoJSON, {
            clampToGround:true,
            stroke:Cesium.Color.fromCssColorString("#facc15"),
            strokeWidth:4,
            fill:Cesium.Color.fromCssColorString("#38bdf8").withAlpha(0.20),
            markerColor:Cesium.Color.fromCssColorString("#38bdf8"),
            markerSize:10
          });
          railwayDataSource.name = "Railway GIS · GeoJSON";
          railwayDataSource.entities.values.forEach((entity) => {
            const props = entity.properties;
            let featureName = "Railway GIS feature";
            if (props) {
              const candidates = ["name", "railway", "ref", "usage", "type"];
              for (const key of candidates) {
                const value = props[key] && props[key].getValue ? props[key].getValue() : null;
                if (value !== undefined && value !== null && String(value).trim()) {
                  featureName = String(value); break;
                }
              }
            }
            entity.name = featureName;
            entity.description = "Loaded from data/geography/railway_corridor.geojson";
            if (entity.polyline) {
              const railText = featureName.toLowerCase();
              const isRail = railText.includes("rail") || railText.includes("track") || railText.includes("line");
              entity.polyline.material = isRail ? Cesium.Color.fromCssColorString("#facc15") : Cesium.Color.fromCssColorString("#38bdf8");
              entity.polyline.width = isRail ? 4 : 2;
              entity.polyline.clampToGround = true;
            }
            if (entity.polygon) {
              entity.polygon.material = Cesium.Color.fromCssColorString("#38bdf8").withAlpha(0.20);
              entity.polygon.outline = true;
              entity.polygon.outlineColor = Cesium.Color.fromCssColorString("#38bdf8");
            }
            if (entity.point) {
              entity.point.color = Cesium.Color.fromCssColorString("#38bdf8");
              entity.point.outlineColor = Cesium.Color.WHITE;
              entity.point.outlineWidth = 1.5;
              entity.point.pixelSize = 9;
            }
          });
          viewer.dataSources.add(railwayDataSource);
          railwayDataSource.show = true;
          setStatus("Railway GIS overlay loaded · " + (d.railwayFeatureCount || railwayDataSource.entities.values.length) + " GeoJSON feature(s). Use Railway GIS on/off to toggle it.");
          viewer.scene.requestRender();
        } catch (e) {
          console.error("[NavIC] Railway GeoJSON overlay failed", e);
          showError("Railway GIS GeoJSON could not be rendered: " + (e && e.message ? e.message : String(e)));
        }
      }

      // SIMULATED TRAIN MOVEMENT:
      // The train follows the longest LineString segment extracted from the configured
      // railway GeoJSON. This is a visual demo, not a live train feed or timetable.
      let trainEntity = null;
      let trainAnimationStart = Date.now();
      let trainVisible = true;
      const trainRoute = (d.routeLines || [])
        .filter(line => Array.isArray(line) && line.length >= 2)
        .sort((a,b) => b.length - a.length)[0] || [];

      if (trainRoute.length >= 2) {
        const trainPositions = trainRoute.map(p =>
          Cesium.Cartesian3.fromDegrees(Number(p[0]), Number(p[1]), 35)
        );
        const cumulativeMetres = [0];
        for (let i = 1; i < trainPositions.length; i++) {
          cumulativeMetres.push(
            cumulativeMetres[i-1] +
            Cesium.Cartesian3.distance(trainPositions[i-1], trainPositions[i])
          );
        }
        const totalTrainDistance = cumulativeMetres[cumulativeMetres.length - 1];

        if (totalTrainDistance > 1) {
          // One full pass takes three minutes, independent of the Cesium clock multiplier.
          const trainLoopDurationMs = 180000;

          function getTrainPosition() {
            const elapsed = (Date.now() - trainAnimationStart) % trainLoopDurationMs;
            const progress = elapsed / trainLoopDurationMs;
            const distanceAlongRoute = progress * totalTrainDistance;

            let segment = 0;
            while (
              segment < cumulativeMetres.length - 2 &&
              cumulativeMetres[segment + 1] < distanceAlongRoute
            ) {
              segment++;
            }

            const segmentStart = cumulativeMetres[segment];
            const segmentLength = Math.max(
              0.001, cumulativeMetres[segment + 1] - segmentStart
            );
            const fraction = Math.max(
              0, Math.min(1, (distanceAlongRoute - segmentStart) / segmentLength)
            );

            return Cesium.Cartesian3.lerp(
              trainPositions[segment],
              trainPositions[segment + 1],
              fraction,
              new Cesium.Cartesian3()
            );
          }

          trainEntity = viewer.entities.add({
            id:"simulated-railway-train",
            position:new Cesium.CallbackProperty(() => getTrainPosition(), false),
            point:{
              pixelSize:17,
              color:Cesium.Color.fromCssColorString("#fb923c"),
              outlineColor:Cesium.Color.WHITE,
              outlineWidth:3,
              disableDepthTestDistance:Number.POSITIVE_INFINITY
            },
            label:{
              text:"TRAIN · SIMULATED",
              font:"bold 13px sans-serif",
              fillColor:Cesium.Color.fromCssColorString("#fed7aa"),
              outlineColor:Cesium.Color.BLACK,
              outlineWidth:4,
              style:Cesium.LabelStyle.FILL_AND_OUTLINE,
              pixelOffset:new Cesium.Cartesian2(0,-25),
              showBackground:true,
              backgroundColor:Cesium.Color.fromCssColorString("#7c2d12").withAlpha(0.88),
              disableDepthTestDistance:Number.POSITIVE_INFINITY
            },
            description:
              "Simulated train marker moving along the longest railway LineString in the configured GeoJSON. " +
              "This is a visualization only; it is not a live train location, timetable, or operational railway feed."
          });

          setStatus(
            "Railway GIS loaded · simulated train animation follows the longest route segment (" +
            (totalTrainDistance / 1000).toFixed(1) +
            " km per loop). This is not live train tracking."
          );
        } else {
          setStatus("Railway GIS loaded, but the selected route segment is too short for train animation.");
        }
      } else {
        setStatus(
          "Railway GIS loaded, but no LineString with at least two coordinates was found; " +
          "train animation is unavailable. Check railway_corridor.geojson."
        );
      }

      // VISUAL DEMONSTRATION ONLY:
      // These animated markers follow simplified circular/inclined paths.
      // They are NOT calculated from NavIC broadcast ephemeris or live tracking data.
      const orbitStart = Cesium.JulianDate.clone(viewer.clock.currentTime);
      viewer.clock.shouldAnimate = true;
      viewer.clock.multiplier = 120; // Accelerated visual animation; not real-time orbit propagation.

      const selectedSv = String(d.sv || "").trim().toUpperCase();
      const navicSatelliteIds = [
        "I01", "I02", "I03", "I04", "I05", "I06", "I07"
      ];
      // Ensure a selected ID outside this illustrative list is still represented.
      if (selectedSv && !navicSatelliteIds.includes(selectedSv)) {
        navicSatelliteIds.push(selectedSv);
      }
      const demoSatellites = navicSatelliteIds.map((id, index) => ({
        id:id,
        angle:(index * 360 / navicSatelliteIds.length),
        inclination:index < 3 ? 0 : 25,
        selected:id === selectedSv
      }));
      const orbitHeight = 35786000.0;
      const orbitPeriodSeconds = 86164.0;

      function orbitPosition(angleDeg, inclinationDeg) {
        const a = angleDeg * Math.PI / 180;
        const inc = inclinationDeg * Math.PI / 180;
        const lon = ((angleDeg + 180) % 360) - 180;
        const lat = Math.asin(Math.sin(inc) * Math.sin(a)) * 180 / Math.PI;
        return Cesium.Cartesian3.fromDegrees(lon, lat, orbitHeight);
      }

      // Draw simplified orbital tracks.
      [0, 25, -25].forEach((inclination, idx) => {
        const orbitPoints = [];
        for (let deg = 0; deg <= 360; deg += 3) {
          const lat = Math.asin(
            Math.sin(inclination * Math.PI / 180) *
            Math.sin(deg * Math.PI / 180)
          ) * 180 / Math.PI;
          const lon = ((deg + 180) % 360) - 180;
          orbitPoints.push(Cesium.Cartesian3.fromDegrees(lon, lat, orbitHeight));
        }
        viewer.entities.add({
          id:"schematic-orbit-" + idx,
          polyline:{
            positions:orbitPoints,
            width:1.5,
            material:new Cesium.PolylineDashMaterialProperty({
              color:idx === 0 ? Cesium.Color.CYAN.withAlpha(0.65) :
                Cesium.Color.MEDIUMSLATEBLUE.withAlpha(0.55),
              dashLength:18
            })
          },
          description:"Illustrative orbital path only; not a NavIC ephemeris-derived orbit."
        });
      });

      const satelliteEntities = [];
      demoSatellites.forEach((sat, index) => {
        const initialAngle = sat.angle;
        const position = new Cesium.CallbackProperty((time) => {
          const elapsed = Cesium.JulianDate.secondsDifference(time, orbitStart);
          const angle = initialAngle + (elapsed / orbitPeriodSeconds) * 360;
          const a = angle * Math.PI / 180;
          const inc = sat.inclination * Math.PI / 180;
          const lon = ((angle + 180) % 360) - 180;
          const lat = Math.asin(Math.sin(inc) * Math.sin(a)) * 180 / Math.PI;
          return Cesium.Cartesian3.fromDegrees(lon, lat, orbitHeight);
        }, false);

        const entity = viewer.entities.add({
          id:"schematic-navic-" + sat.id,
          position:position,
          point:{
            pixelSize:sat.selected ? 19 : 11,
            color:sat.selected ? Cesium.Color.fromCssColorString("#ff3b30") :
              Cesium.Color.fromCssColorString("#67e8f9"),
            outlineColor:sat.selected ? Cesium.Color.YELLOW : Cesium.Color.WHITE,
            outlineWidth:sat.selected ? 3 : 1.5,
            disableDepthTestDistance:Number.POSITIVE_INFINITY
          },
          label:{
            text:sat.id,
            font:sat.selected ? "bold 15px sans-serif" : "bold 12px sans-serif",
            fillColor:sat.selected ? Cesium.Color.YELLOW :
              Cesium.Color.fromCssColorString("#67e8f9"),
            outlineColor:Cesium.Color.BLACK,
            outlineWidth:3,
            style:Cesium.LabelStyle.FILL_AND_OUTLINE,
            pixelOffset:new Cesium.Cartesian2(0,-20),
            showBackground:true,
            backgroundColor:Cesium.Color.BLACK.withAlpha(.55),
            disableDepthTestDistance:Number.POSITIVE_INFINITY
          },
          description:(sat.selected ? "Currently selected dashboard satellite. " : "") +
            "Animated illustrative marker for " + sat.id +
            "; position is schematic and is not based on live NavIC ephemeris."
        });
        satelliteEntities.push(entity);
      });

      // Illustrative link follows the dashboard-selected satellite.
      const selectedSatelliteEntity =
        satelliteEntities.find(entity => entity.id === "schematic-navic-" + selectedSv) ||
        satelliteEntities[0];

      viewer.entities.add({
        id:"schematic-signal-link",
        polyline:{
          positions:new Cesium.CallbackProperty((time) => {
            const satPosition = selectedSatelliteEntity.position.getValue(time);
            return [
              Cesium.Cartesian3.fromDegrees(s.lon,s.lat,150),
              satPosition
            ];
          }, false),
          width:2.5,
          material:new Cesium.PolylineDashMaterialProperty({
            color:threatColor,
            dashLength:14
          })
        },
        description:"Illustrative connection to selected satellite " + selectedSv + "; not a computed line-of-sight or live signal link."
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
      function flyToGlobe() {
        viewer.scene.mode = Cesium.SceneMode.SCENE3D;
        viewer.scene.globe.show = true;
        viewer.scene.skyBox.show = true;
        viewer.scene.skyAtmosphere.show = true;
        viewer.camera.cancelFlight();
        viewer.camera.flyTo({
          destination:Cesium.Cartesian3.fromDegrees(78.0, 20.0, 17500000),
          orientation:{
            heading:Cesium.Math.toRadians(0.0),
            pitch:Cesium.Math.toRadians(-90.0),
            roll:0.0
          },
          duration:1.5,
          complete:() => viewer.scene.requestRender()
        });
        setStatus("3D Earth globe view · selected satellite " + selectedSv + " highlighted; imagery/terrain source depends on Cesium ion token.");
      }
      function flyToIndia() {
        viewer.camera.flyTo({destination:indiaRectangle,duration:0.9});
      }
      flyToGlobe();

      btnStreet.addEventListener("click",showStreet);
      btnSatellite.addEventListener("click",showSatellite);
      btnIon.addEventListener("click",showIon);
      btnHome.addEventListener("click",flyToIndia);
      btnGlobe.addEventListener("click",flyToGlobe);
      btnRailToggle.addEventListener("click",() => {
        if (!railwayDataSource) {
          loadRailwayGIS();
          return;
        }
        railwayDataSource.show = !railwayDataSource.show;
        btnRailToggle.classList.toggle("active", railwayDataSource.show);
        btnRailToggle.textContent = railwayDataSource.show ? "Railway GIS: on" : "Railway GIS: off";
        viewer.scene.requestRender();
      });
      btnStationToggle.addEventListener("click",() => {
        const show = !stationEntities.some(entity => entity.show !== false);
        stationEntities.forEach(entity => entity.show = show);
        btnStationToggle.classList.toggle("active", show);
        btnStationToggle.textContent = show ? "Stations: on" : "Stations: off";
        viewer.scene.requestRender();
      });
      btnTrainToggle.addEventListener("click",() => {
        if (!trainEntity) {
          showError("Train animation is unavailable because no valid railway LineString was found in the configured GeoJSON.");
          return;
        }
        trainVisible = !trainVisible;
        trainEntity.show = trainVisible;
        btnTrainToggle.classList.toggle("active", trainVisible);
        btnTrainToggle.textContent = trainVisible ? "Train: on" : "Train: off";
        viewer.scene.requestRender();
      });

      // Load railway GIS and initialize the imagery using the official tutorial sequence.
      // Do not call flyToGlobe() after showIon(): that would override viewer.zoomTo().
      loadRailwayGIS();
      if (d.ionToken) {
        setStatus("Cesium ion token received by the component; requesting imagery asset 3830183…");
        showIon();
      } else {
        showSatellite().then(() => {
          flyToGlobe();
          viewer.scene.requestRender();
        });
      }
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
        "railway_geojson_loaded": railway_geojson is not None,
        "railway_geojson_features": railway_feature_count,
        "route_vertices": sum(len(line) for line in route_lines),
        "route_segments": len(route_lines),
        "route_path": str(DEFAULT_CORRIDOR_FILE),
        "token_configured": bool(ion_token),
        "default_imagery": "Cesium ion Google Satellite + Labels (asset 3830183) when token is configured; Esri fallback otherwise",
        "satellite_visualization": "Animated schematic constellation; not live NavIC ephemeris",
        "train_visualization": "Simulated train moves along the longest GeoJSON LineString; not live train tracking",
        "ion_asset_id": ION_HYBRID_IMAGERY_ASSET_ID,
    }
