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
        "selectedStation": STATIONS.get(station, STATIONS["IISC00IND"]),
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
      <div id="railgis-map">
        <div id="railgis-twin-overlay">
          <div class="twin-title">Digital twin overlays</div>
          <div id="railgis-train-state">Train: preparing route…</div>
          <div id="railgis-integrity-state">Integrity: evaluating…</div>
          <div id="railgis-satellite-state">NavIC: preparing selected satellite…</div>
          <div class="twin-note">Train and satellite geometry are simulated in this 2D fallback.</div>
        </div>
      </div>
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
      #railgis-twin-overlay{position:absolute;z-index:650;left:12px;top:12px;background:rgba(15,23,42,.94);border:1px solid #475569;border-radius:9px;padding:9px 12px;min-width:220px;max-width:290px;color:#f8fafc;box-shadow:0 4px 16px rgba(0,0,0,.35);pointer-events:none;font-size:12px;line-height:1.55}
      .twin-title{font-weight:700;font-size:13px;margin-bottom:4px;color:#e2e8f0}
      .twin-note{font-size:10px;color:#94a3b8;margin-top:4px}
      .railgis-train-icon{background:transparent;border:0}
      .railgis-train-glyph{font-size:25px;line-height:28px;text-shadow:0 1px 4px #111827;filter:drop-shadow(0 0 3px #fb923c)}
      .railgis-satellite-icon{background:rgba(15,23,42,.9);border:1px solid #67e8f9;border-radius:5px;color:#67e8f9;padding:2px 5px;font-size:11px;font-weight:700;white-space:nowrap}
      .railgis-satellite-selected{color:#fde047;border-color:#fde047;box-shadow:0 0 8px rgba(250,204,21,.8)}
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

      // ---------------- 2D digital-twin fallback overlays ----------------
      const trainState = document.getElementById('railgis-train-state');
      const satelliteState = document.getElementById('railgis-satellite-state');

      function collectLines(node, output) {
        if (!node) return;
        if (node.type === 'FeatureCollection') {
          (node.features || []).forEach(f => collectLines(f, output));
        } else if (node.type === 'Feature') {
          collectLines(node.geometry, output);
        } else if (node.type === 'GeometryCollection') {
          (node.geometries || []).forEach(g => collectLines(g, output));
        } else if (node.type === 'LineString') {
          const line = (node.coordinates || [])
            .filter(p => Array.isArray(p) && p.length >= 2)
            .map(p => [Number(p[1]), Number(p[0])]);
          if (line.length >= 2) output.push(line);
        } else if (node.type === 'MultiLineString') {
          (node.coordinates || []).forEach(segment => {
            const line = (segment || [])
              .filter(p => Array.isArray(p) && p.length >= 2)
              .map(p => [Number(p[1]), Number(p[0])]);
            if (line.length >= 2) output.push(line);
          });
        }
      }

      const routeSegments = [];
      collectLines(d.geojson, routeSegments);
      routeSegments.sort((a,b) => b.length - a.length);
      const trainRoute = routeSegments[0] || [];
      const trainLayer = L.layerGroup().addTo(map);
      const integrityState = document.getElementById('railgis-integrity-state');
      let trainMarker = null;

      const threatName = String(d.threat || 'Genuine');
      const threatConfidence = Number(d.confidence || 0);
      const isThreat = (threatName === 'Multipath' || threatName === 'Spoofing') &&
                       threatConfidence >= 0.70;
      const alertColor = threatName === 'Spoofing' ? '#ef4444' : '#f59e0b';
      const alertRadiusMetres = 10000; // illustrative 10 km section around nearest route point

      if (trainRoute.length >= 2) {
        const cumulative = [0];
        for (let i=1; i<trainRoute.length; i++) {
          cumulative.push(cumulative[i-1] + map.distance(trainRoute[i-1], trainRoute[i]));
        }
        const totalLength = cumulative[cumulative.length-1];

        // Associate the selected receiver's model output with the nearest point
        // on this displayed railway route. This is a visualization proxy only.
        let nearestIndex = 0;
        let nearestDistance = Infinity;
        const selectedLatLng = L.latLng(
          Number(d.selectedStation.lat), Number(d.selectedStation.lon)
        );
        trainRoute.forEach((point, index) => {
          const distance = map.distance(selectedLatLng, L.latLng(point[0], point[1]));
          if (distance < nearestDistance) {
            nearestDistance = distance;
            nearestIndex = index;
          }
        });

        const alertCentreDistance = cumulative[nearestIndex];
        const alertStartDistance = Math.max(0, alertCentreDistance-alertRadiusMetres);
        const alertEndDistance = Math.min(totalLength, alertCentreDistance+alertRadiusMetres);

        function positionAtDistance(distanceAlong) {
          let seg = 0;
          while (seg < cumulative.length-2 && cumulative[seg+1] < distanceAlong) seg++;
          const segmentLength = Math.max(0.001, cumulative[seg+1]-cumulative[seg]);
          const fraction = Math.max(0, Math.min(1, (distanceAlong-cumulative[seg])/segmentLength));
          const a = trainRoute[seg], b = trainRoute[seg+1];
          return [
            a[0] + (b[0]-a[0])*fraction,
            a[1] + (b[1]-a[1])*fraction
          ];
        }

        // Highlight the section associated with the selected station's O2 output.
        if (isThreat && alertEndDistance > alertStartDistance) {
          const alertPoints = [positionAtDistance(alertStartDistance)];
          for (let i=0; i<cumulative.length; i++) {
            if (cumulative[i] > alertStartDistance && cumulative[i] < alertEndDistance) {
              alertPoints.push(trainRoute[i]);
            }
          }
          alertPoints.push(positionAtDistance(alertEndDistance));
          L.polyline(alertPoints, {
            color:alertColor, weight:9, opacity:0.9,
            dashArray:threatName === 'Spoofing' ? '2 7' : '10 6',
            lineCap:'round'
          }).addTo(trainLayer).bindPopup(
            `<b>${threatName} integrity alert section</b><br>` +
            `Model confidence: ${(threatConfidence*100).toFixed(1)}%<br>` +
            `Associated with selected GNSS station: ${d.station}<br>` +
            `Illustrative section: ±10 km around nearest route point.`
          );
        }

        trainMarker = L.marker(trainRoute[0], {
          icon:L.divIcon({
            className:'railgis-train-icon',
            html:'<div class="railgis-train-glyph">🚆</div>',
            iconSize:[30,30], iconAnchor:[15,15]
          }),
          zIndexOffset:1200,
          title:'Simulated train — not live tracking'
        }).addTo(trainLayer);

        const durationMs = 180000;
        let startTime = null;

        function animateTrain(timestamp) {
          if (startTime === null) startTime = timestamp;
          const progress = ((timestamp-startTime) % durationMs)/durationMs;
          const distanceAlong = progress*totalLength;
          const currentPosition = positionAtDistance(distanceAlong);
          const insideAlert = isThreat &&
            distanceAlong >= alertStartDistance &&
            distanceAlong <= alertEndDistance;

          trainMarker.setLatLng(currentPosition);
          trainMarker.setIcon(L.divIcon({
            className:'railgis-train-icon',
            html:`<div class="railgis-train-glyph" style="filter:drop-shadow(0 0 6px ${insideAlert ? alertColor : '#fb923c'})">${insideAlert ? '🚨' : '🚆'}</div>`,
            iconSize:[30,30], iconAnchor:[15,15]
          }));

          if (insideAlert) {
            integrityState.innerHTML =
              `<span style="color:${alertColor};font-weight:800">⚠ TRAIN IN ${threatName.toUpperCase()} SECTION</span><br>` +
              `O2 confidence: ${(threatConfidence*100).toFixed(1)}% · Station: ${d.station}`;
          } else if (isThreat) {
            integrityState.innerHTML =
              `<span style="color:${alertColor};font-weight:700">● ${threatName.toUpperCase()} SECTION IDENTIFIED</span><br>` +
              `Train outside highlighted section · O2: ${(threatConfidence*100).toFixed(1)}%`;
          } else {
            integrityState.innerHTML =
              '<span style="color:#22c55e;font-weight:700">● NO HIGH-CONFIDENCE O2 THREAT</span><br>' +
              `Current classification: ${threatName} · ${(threatConfidence*100).toFixed(1)}%`;
          }

          trainState.innerHTML =
            '<span style="color:#fb923c;font-weight:700">● Train moving</span><br>' +
            'Route: longest GeoJSON line<br>Loop: 3 minutes · ' +
            (totalLength/1000).toFixed(1) + ' km';

          window.requestAnimationFrame(animateTrain);
        }
        window.requestAnimationFrame(animateTrain);

        if (isThreat) {
          integrityState.innerHTML =
            `<span style="color:${alertColor};font-weight:800">⚠ ${threatName.toUpperCase()} SECTION HIGHLIGHTED</span><br>` +
            `O2 confidence: ${(threatConfidence*100).toFixed(1)}% · Nearest route point to ${d.station}`;
        } else {
          integrityState.innerHTML =
            '<span style="color:#22c55e;font-weight:700">● NO HIGH-CONFIDENCE O2 THREAT</span><br>' +
            `Current classification: ${threatName} · ${(threatConfidence*100).toFixed(1)}%`;
        }
      } else {
        trainState.textContent = 'Train: no valid railway LineString found in GeoJSON.';
        integrityState.textContent = 'Integrity overlay unavailable: no railway route geometry.';
      }

      // Schematic 2D satellite marker and signal link; not ephemeris-derived.
      const selectedStation = d.selectedStation;
      const selectedSv = String(d.sv || 'I01').toUpperCase();
      const satelliteIds = ['I01','I02','I03','I04','I05','I06','I07'];
      if (!satelliteIds.includes(selectedSv)) satelliteIds.push(selectedSv);
      const satelliteLayer = L.layerGroup().addTo(map);
      const satLat = Math.min(82, Number(selectedStation.lat) + 5.0);
      const satLon = Number(selectedStation.lon) + 5.5;

      L.marker([satLat,satLon], {
        icon:L.divIcon({
          className:'railgis-satellite-icon railgis-satellite-selected',
          html:selectedSv, iconSize:null, iconAnchor:[0,0]
        }),
        zIndexOffset:1100,
        title:selectedSv + ' — schematic selected satellite'
      }).addTo(satelliteLayer);

      L.polyline(
        [[satLat,satLon],[Number(selectedStation.lat),Number(selectedStation.lon)]],
        {color:'#facc15',weight:2,dashArray:'5 7',opacity:.9}
      ).addTo(satelliteLayer);

      const satChips = satelliteIds.map(id =>
        id === selectedSv
          ? '<span style="color:#fde047;font-weight:800">[' + id + ']</span>'
          : '<span style="color:#67e8f9">' + id + '</span>'
      ).join('  ');
      satelliteState.innerHTML =
        '<span style="color:#fde047;font-weight:700">Selected: ' + selectedSv + '</span><br>' +
        'NavIC IDs: ' + satChips + '<br>Signal link: schematic to ' + d.station;

      const overlays = {};
      if (geoLayer) overlays['Railway corridor / GeoJSON'] = geoLayer;
      overlays['Simulated train'] = trainLayer;
      overlays['NavIC satellite + signal (schematic)'] = satelliteLayer;
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
        ? `Map ready · ${d.geojsonPath} · ${d.featureCount || 'GeoJSON'} feature(s) · Selected: ${d.station} / ${d.sv} · Scenario test: ${d.scenario} · LightGBM output: ${d.threat} (${(d.confidence*100).toFixed(1)}%) · Simulated train + integrity section overlay`
        : `Map ready · OpenStreetMap and Esri layers available · No corridor GeoJSON found at ${d.geojsonPath} · Selected: ${d.station} / ${d.sv} · Scenario test: ${d.scenario} · LightGBM output: ${d.threat} (${(d.confidence*100).toFixed(1)}%)`;
      setTimeout(() => map.invalidateSize(), 250);
      window.addEventListener('resize', () => map.invalidateSize());
    })();
    </script>
    """.replace("PAYLOAD", payload)

    components.html(html, height=735, scrolling=False)
    return {"geojson_loaded": geojson is not None, "feature_count": feature_count,
            "geojson_path": str(GEOJSON_PATH)}
