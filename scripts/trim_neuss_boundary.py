import json
import os

BOUNDARY_PATH = "config/boundaries/neuss_admin_boundary.geojson"

print(f"Trimming {BOUNDARY_PATH} bounding box to exclude Düsseldorf (max lon 6.715)")

with open(BOUNDARY_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

# The boundary is a Polygon
rings = data["features"][0]["geometry"]["coordinates"]
exterior = rings[0]

new_exterior = []
for pt in exterior:
    lon, lat = pt[0], pt[1]
    # Düsseldorf lies east of the Rhine. The Rhine border for Neuss roughly caps at lon 6.715
    if lon > 6.715:
        lon = 6.715
    new_exterior.append([lon, lat])

data["features"][0]["geometry"]["coordinates"][0] = new_exterior
data["features"][0]["properties"]["note"] = "Simplified boundary polygon. Truncated at max lon 6.715 to definitively exclude all Düsseldorf Rhine areas (Gladbacher Str., Volmerswerther Deich, Merkurstr., Himmelgeister Str.)"

with open(BOUNDARY_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Polygon successfully trimmed.")
