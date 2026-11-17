from __future__ import annotations

import json
from pathlib import Path

import streamlit.components.v1 as components

STATIONS = {
    "IISC00IND": {"lat": 13.021, "lon": 77.570, "label": "IISC · Bengaluru"},
    "LCK400IND": {"lat": 26.846, "lon": 80.946, "label": "LCK4 · Lucknow"},
    "JDPR00IND": {"lat": 26.238, "lon": 73.024, "label": "JDPR · Jodhpur"},
}
ROOT = Path(__file__).resolve().parents[1]
GEOJSON_PATH = ROOT / "data" / "geography" / "railway_corridor.geojson"
COLORS = {"Genuine": "#22c55e", "Multipath": "#f59e0b", "Spoofing": "#ef4444"}


def _load_geojson():
    if not GEOJSON_PATH.exists():
        return None, 0
    try:
        obj = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or obj.get("type") not in {
            "FeatureCollection", "Feature", "LineString", "MultiLineString",
            "Polygon", "MultiPolygon", "GeometryCollection", "Point", "MultiPoint"
        }:
            return None, 0
        if obj.get("type") == "FeatureCollection":
            count = len(obj.get("features", []))
        else:
            count = 1
        return obj, count
    except Exception:
        return None, 0


def render_railway_gis(
    station: str,
    sv: str,
    threat: str,
    confidence: float,
    forecast: float,
    show_all: bool = True,
    scenario: str = "Observed data (no injection)",
):
    geojson, feature_count = _load_geojson()
    stations = STATIONS if show_all else {station: STATIONS.get(station, STATIONS["IISC00IND"])}
    payload = json.dumps({
        "station": station,
        "sv": sv,
        "threat": threat,
        "scenario": scenario,
        "confidence": float(confidence),
        "forecast": float(forecast),
        "stations": stations,
        "geojson": geojson,
        "geojsonPath": str(GEOJSON_PATH),
        "featureCount": feature_count,
        "colors": COLORS,
    }, ensure_ascii=False).replace("</", "<\\/")

    html = r"""
    <div id="railgis-shell">
      <div class="railgis-heading">
        <span>India · Railway network · GNSS reference stations</span>
        <span class="railgis-note">Select a layer using the control at the top-right of the map</span>
      </div>
      <div id="railgis-map"></div>
      <div id="railgis-status">Loading interactive railway map…</div>
    </div>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    <style>
      #railgis-shell{font-family:Arial,sans-serif;color:#e5e7eb}
      .railgis-heading{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;
        font-size:13px;color:#cbd5e1;margin:2px 0 9px}
      .railgis-note{color:#94a3b8}
      #railgis-map{height:650px;width:100%;border:1px solid #475569;border-radius:12px;overflow:hidden;background:#dbeafe}
      #railgis-status{margin-top:8px;padding:9px 11px;border:1px solid #334155;border-radius:8px;
        background:#111827;color:#cbd5e1;font-size:12px;line-height:1.5}
      .leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#111827;color:#f8fafc}
      .leaflet-control-layers{border-radius:8px!important}
      .railgis-station-label{background:rgba(15,23,42,.88);border:1px solid #64748b;color:#fff;
        border-radius:5px;padding:3px 6px;font-weight:600;box-shadow:none}
      .railgis-station-label:before{display:none}
    </style>
    <script>
    (() => {
      const d = PAYLOAD;
      const status = document.getElementById('railgis-status');
      if (!window.L) {
        status.textContent = 'Leaflet could not load. Check access to unpkg.com and reload the app.';
        return;
      }
      const map = L.map('railgis-map', {preferCanvas:true, zoomControl:true}).setView([22.5, 79.0], 5);

      const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom:19, attribution:'© OpenStreetMap contributors'
      }).addTo(map);

      const imagery = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {maxZoom:19, attribution:'Tiles © Esri'}
      );
      const labels = L.tileLayer(
        'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
        {maxZoom:19, attribution:'Labels © Esri'}
      );
      const hybrid = L.layerGroup([imagery, labels]);

      const threatColor = d.colors[d.threat] || '#22c55e';
      const stationBounds = [];
      Object.entries(d.stations || {}).forEach(([code, s]) => {
        const selected = code === d.station;
        const color = selected ? threatColor : '#22c55e';
        const marker = L.circleMarker([s.lat, s.lon], {
          radius:selected ? 10 : 7, color:'#ffffff', weight:2,
          fillColor:color, fillOpacity:1
        }).addTo(map);
        marker.bindPopup(
          `<b>${s.label}</b><br>Station code: ${code}<br>` +
          (selected ? `Selected satellite: ${d.sv}<br>Threat: ${d.threat} (${(d.confidence*100).toFixed(1)}%)<br>σφ proxy forecast: ${Number(d.forecast).toFixed(3)}` :
          'GNSS observation reference station<br>Not a verified railway receiver installation.')
        );
        marker.bindTooltip(s.label, {permanent:true,direction:'top',offset:[0,-8],className:'railgis-station-label'});
        stationBounds.push([s.lat,s.lon]);
      });

      let geoLayer = null;
      if (d.geojson) {
        geoLayer = L.geoJSON(d.geojson, {
          style: feature => {
            const p = (feature && feature.properties) || {};
            const name = String(p.name || p.railway || p.ref || '').toLowerCase();
            const isRail = name.includes('rail') || p.railway || p.usage === 'main';
            return {color:isRail ? '#facc15' : '#38bdf8', weight:isRail ? 4 : 2,
              opacity:.95, dashArray:null};
          },
          pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
            radius:6,color:'#fff',weight:1,fillColor:'#38bdf8',fillOpacity:.95
          }),
          onEachFeature: (feature, layer) => {
            const props = (feature && feature.properties) || {};
            const title = props.name || props.ref || props.railway || 'GeoJSON feature';
            layer.bindPopup(`<b>${String(title)}</b><br>Loaded from railway_corridor.geojson`);
          }
        }).addTo(map);
        try {
          const b = geoLayer.getBounds();
          if (b.isValid()) map.fitBounds(b.pad(0.08), {maxZoom:9});
        } catch(e) {}
      } else if (stationBounds.length) {
        map.fitBounds(stationBounds, {padding:[45,45]});
      }

      const overlays = {};
      if (geoLayer) overlays['Railway corridor / GeoJSON'] = geoLayer;
      overlays['Satellite labels'] = labels;
      L.control.layers(
        {'OpenStreetMap · street / rail context':osm, 'Esri · satellite imagery':imagery,
         'Esri · hybrid satellite + labels':hybrid},
        overlays, {collapsed:false}
      ).addTo(map);

      const selected = d.stations[d.station];
      if (selected) {
        L.circle([selected.lat,selected.lon], {radius:25000,color:threatColor,
          weight:1,dashArray:'5 7',fill:false,opacity:.7}).addTo(map);
      }
      status.textContent = d.geojson
        ? `Map ready · ${d.geojsonPath} · ${d.featureCount || 'GeoJSON'} feature(s) · Selected: ${d.station} / ${d.sv} · Scenario test: ${d.scenario} · LightGBM output: ${d.threat} (${(d.confidence*100).toFixed(1)}%)`
        : `Map ready · OpenStreetMap and Esri layers available · No corridor GeoJSON found at ${d.geojsonPath} · Selected: ${d.station} / ${d.sv} · Scenario test: ${d.scenario} · LightGBM output: ${d.threat} (${(d.confidence*100).toFixed(1)}%)`;
      setTimeout(() => map.invalidateSize(), 250);
      window.addEventListener('resize', () => map.invalidateSize());
    })();
    </script>
    """.replace("PAYLOAD", payload)

    components.html(html, height=735, scrolling=False)
    return {"geojson_loaded": geojson is not None, "feature_count": feature_count,
            "geojson_path": str(GEOJSON_PATH)}
