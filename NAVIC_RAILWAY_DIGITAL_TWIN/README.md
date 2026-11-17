# NavIC Railway Corridor — Comprehensive AI Digital Twin Dashboard

This update expands the Streamlit + CesiumJS dashboard while preserving the saved O1 DeepAR and O2 LightGBM model artifacts. It does **not** retrain either model.

## Dashboard modules

1. **Overview** — combined O1/O2 status, threat probabilities, integrated prototype decision and 20-step forecast.
2. **3D Digital Twin** — CesiumJS India view with the selected GNSS reference station, optional other reference stations, threat-coloured status and an explicitly illustrative satellite marker. An actual railway alignment can be overlaid by uploading a GeoJSON `LineString` or `MultiLineString` in `[longitude, latitude]` order.
3. **Signal Analytics** — recent `sigma_phi_proxy` history, DeepAR forecast, raw C5A/L5A/S5A observable traces and recent records.
4. **Threat Intelligence** — LightGBM class probabilities, session assessment history and a scenario laboratory for controlled synthetic multipath/spoofing perturbations.
5. **Railway Integrity** — transparent decision-support output and a list of inputs still required for real HPL/VPL computation.
6. **Data & Model Info** — dataset coverage and saved model metadata/validation information.

## Run

Use the existing project virtual environment and model artifacts:

```powershell
# Activate the existing environment
.venv\Scripts\Activate.ps1

# Install any newly required dashboard dependency
pip install -r requirements.txt

# Launch
streamlit run app.py
```

The expected trained artifacts remain:

- `models/o1_deepar/predictor/`
- `models/o2_lightgbm/lightgbm_classifier.joblib`
- `models/o2_lightgbm/feature_list.joblib`
- `models/o2_lightgbm/train_medians.joblib`

The dataset is downloaded from Google Drive on first use and saved as `data.parquet` in the project root. Later runs reuse the local file.

## Scenario laboratory

Selecting `Multipath` or `Spoofing` applies a temporary, controlled perturbation to a copy of the selected station/satellite observations before O2 inference. It never writes changes to the source Parquet file. These are demonstration scenarios, not real attack observations.

## Important research and safety qualifications

- O1 forecasts `sigma_phi_proxy`; it is not a direct conventional S4 measurement. Its absolute magnitude needs calibration and interpretation against the source dataset and modelling pipeline.
- O2 uses synthetically injected multipath/spoofing examples. Its reported validation performance is not field-validated attack-detection performance.
- D5A was not present in the checked files. The Doppler-related O2 input is a carrier-phase-derived proxy.
- The Cesium satellite location and signal path are illustrative. Live NavIC ephemeris, satellite visibility and receiver-satellite geometry are not connected.
- The displayed IGS sites are GNSS reference observation sites, not verified railway receiver installations.
- The current integrity decision is a transparent demonstration heuristic. It is **not** a certified HPL/VPL, ARAIM implementation, HAL/VAL compliance calculation or Kavach safety decision.
- An actual railway corridor requires its route geometry, chainage, receiver locations and validated operating constraints. The dashboard accepts a GeoJSON corridor overlay but does not invent one.

## Validation status

The Python files are syntax-checked. The dashboard has not been executed end-to-end on the user's Windows machine with their local dataset, saved model artifacts, browser and network access. CesiumJS imagery requires internet access.


## Geography / CesiumJS update (V2)

- Removed the Streamlit frontend GeoJSON uploader.
- CesiumJS now opens on an India-wide geographical extent.
- Default basemap is OpenStreetMap street/railway context; a button switches to Esri World Imagery satellite basemap.
- Configured IGS reference stations are shown with selected-station threat colouring.
- A project-specific corridor is loaded automatically from `data/geography/railway_corridor.geojson`.
- The corridor file is currently an empty valid GeoJSON placeholder because no specific railway corridor was selected. The basemap still shows mapped railway-network context; no custom corridor has been invented.
- Satellite position and signal path remain schematic. Actual NavIC ephemeris/orbit propagation is not implemented.
- The map uses public tile services and therefore requires internet access in the browser.

### Add the verified corridor once (not in the frontend)

Replace `data/geography/railway_corridor.geojson` with the verified corridor GeoJSON. Supported geometries are LineString and MultiLineString (also wrapped in Feature/FeatureCollection). Use WGS84 longitude/latitude coordinates.


## Map imagery reliability update (V3)

The CesiumJS map now starts with Esri World Street Map (rail/road labels), then supports Esri World Imagery and provider fallback candidates (CARTO Voyager and OpenStreetMap). Imagery provider tile errors are monitored and a visible diagnostic message is shown when external tile services are unavailable. The project route loader preserves each GeoJSON LineString separately to avoid connecting unrelated railway ways with artificial straight segments.

The map still requires browser internet access to the external imagery tile services. No client can guarantee map imagery where a network, proxy, firewall, content blocker or provider outage blocks all tile endpoints.


## Cesium ion hybrid imagery setup (V4)

The 3D view now uses Cesium ion's **Google Maps 2D Satellite with Labels** imagery asset (asset ID `3830183`) as its primary hybrid basemap. This is a hosted hybrid layer: satellite imagery with map labels. The implementation uses the official `Cesium.IonImageryProvider.fromAssetId()` API.

### Configure the access token

1. Create/sign in to a Cesium ion account: https://ion.cesium.com/
2. Create an access token: https://ion.cesium.com/tokens/
3. Ensure the token can access imagery asset `3830183`. If your ion account does not have access to that asset, use an imagery asset available in your account and update `ION_HYBRID_IMAGERY_ASSET_ID` in `components/cesium_view.py`.
4. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
5. Put your token in `.streamlit/secrets.toml`:
   `CESIUM_ION_TOKEN = "your_token_here"`
6. Restart Streamlit.

You can alternatively set the `CESIUM_ION_TOKEN` environment variable. Do not commit or share `.streamlit/secrets.toml`.

**Browser-token note:** CesiumJS requests imagery from the browser, so the token is necessarily delivered to the client component. In Cesium ion, create a least-privilege token, restrict its allowed URLs/domains to your actual local/deployed dashboard origin where supported, and grant only the required asset access. Never use an unrestricted account/master token.

### What is and is not included

- The hybrid imagery is provided by Cesium ion asset `3830183`; it is not downloaded into the ZIP.
- The 3D view reports token/provider errors visibly instead of silently displaying a black globe.
- Existing Streamlit, DeepAR, LightGBM and local GeoJSON loading are preserved.
- The route GeoJSON remains local at `data/geography/railway_corridor.geojson`.
- The NavIC satellite marker and signal path remain schematic; live ephemeris is not included.
- A successful token/provider initialisation does not prove imagery tiles are delivered. Confirm the actual tiles render in the browser.
