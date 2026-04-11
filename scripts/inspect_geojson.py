import json

with open('config/boundaries/neuss_admin_boundary.geojson') as f:
    d = json.load(f)
c = d['features'][0]['geometry']['coordinates']
print('GeoJSON type:', d['features'][0]['geometry']['type'])
print(f'Number of polygons in MultiPolygon: {len(c)}')
if d['features'][0]['geometry']['type'] == 'Polygon':
    rings = c
    ring = rings[0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    print(f'Polygon Outer Ring: {len(ring)} points. Lon range {min(lons):.4f} to {max(lons):.4f}')
else:
    for i, poly in enumerate(c):
        ring = poly[0]
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        print(f'MultiPoly {i} Outer Ring: {len(ring)} points. Lon range {min(lons):.4f} to {max(lons):.4f}')
