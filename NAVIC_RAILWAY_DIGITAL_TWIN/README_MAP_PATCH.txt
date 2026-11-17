# NavIC Railway Digital Twin — Map Patch

## Files to replace/add
1. Replace your project-root `app.py` with this `app.py`.
2. Replace `components/cesium_view.py` with `components/cesium_view.py` from this patch.
3. Add `components/railway_map.py`.
4. Add `components/__init__.py` if your components folder does not already have one.
5. Replace `requirements.txt` (the Python dependency list is unchanged; Leaflet and CesiumJS are loaded in the browser).

Do not replace `config.py`, `src/`, trained model folders, Parquet data, or GeoJSON data.

## Required folders / data
Keep your existing:
- `data/processed/all_raw_cleaned.parquet`
- `data/geography/railway_corridor.geojson` (optional, but required to draw your project-specific corridor)
- `models/o1_deepar/predictor/` including its GluonTS files
- `models/o1_deepar/metadata.json`
- `models/o2_lightgbm/` trained LightGBM files

## Run
From the project root in your activated virtual environment:
```powershell
pip install -r requirements.txt
streamlit run app.py
```

## What changed
- CesiumJS now adds an OpenStreetMap imagery layer immediately, so the 3D globe is not left as a black starfield when ion imagery fails.
- CesiumJS has Street map, Esri satellite + labels, and optional Cesium ion imagery controls.
- A separate `Railway GIS Map` tab uses Leaflet with OpenStreetMap and Esri imagery/hybrid layers.
- Both maps display the same selected reference station, O2 threat classification, DeepAR forecast and local GeoJSON overlay.
- If Cesium ion fails because of asset compatibility or token permissions, the public basemap and the independent Leaflet map remain available.

## Important limitations
- Reference station coordinates are GNSS observation-site locations, not confirmed railway receiver installations.
- The satellite and signal path in CesiumJS remain schematic until live NavIC ephemerides are integrated.
- The project-specific railway line is displayed only when a valid GeoJSON is placed at `data/geography/railway_corridor.geojson`.
- Public tile providers require internet access and may impose usage policies/rate limits.
