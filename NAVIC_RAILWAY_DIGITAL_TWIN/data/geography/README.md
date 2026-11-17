# Geography data

The dashboard no longer has a GeoJSON upload control.

To display a verified, project-specific railway corridor, place its GeoJSON file here with this exact name:

`railway_corridor.geojson`

Supported geometries: `LineString`, `MultiLineString`, `Feature`, `FeatureCollection`, and `GeometryCollection`. Coordinates must be GeoJSON `[longitude, latitude]` in WGS84.

No route is bundled because the user has not yet selected a specific railway corridor. The Cesium street basemap already displays OpenStreetMap railway-network context. The locally configured corridor file, when supplied, is automatically loaded at application startup.

The reference-station coordinates are GNSS observation-site coordinates, not verified railway receiver installations.
