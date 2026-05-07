"""
explain_tannenweg.py
====================
Shows exactly which buildings OSM has for Tannenweg,
and WHY cluster_building_count = 15 instead of 45.
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")

import osmium

PBF = r"D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\osm\duesseldorf-regbez-latest.osm.pbf"
TARGET_STREET = "Tannenweg"

NEUSS_BBOX = (6.61, 51.13, 6.77, 51.25)  # lon_min, lat_min, lon_max, lat_max

class TannenwegExtractor(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []

    def way(self, w):
        tags = w.tags
        if tags.get("addr:street", "") != TARGET_STREET:
            return
        building_tag = tags.get("building", "")
        if not building_tag or building_tag.lower() == "no":
            return

        # Neuss bbox filter (centroid-based)
        nodes = [(n.location.lon, n.location.lat) for n in w.nodes if n.location.valid()]
        if not nodes:
            return
        c_lon = sum(x for x, _ in nodes) / len(nodes)
        c_lat = sum(y for _, y in nodes) / len(nodes)
        lon_min, lat_min, lon_max, lat_max = NEUSS_BBOX
        if not (lat_min <= c_lat <= lat_max and lon_min <= c_lon <= lon_max):
            return  # Not in Neuss — skip

        self.buildings.append({
            "id": w.id,
            "building": building_tag,
            "housenumber": tags.get("addr:housenumber", ""),
            "postcode": tags.get("addr:postcode", ""),
        })

print(f"Reading PBF for Tannenweg in NEUSS (bbox filtered)...")
h = TannenwegExtractor()
h.apply_file(PBF, locations=True)  # locations=True needed for bbox centroid check

buildings = sorted(h.buildings, key=lambda x: x["housenumber"])
print(f"\nTotal buildings found with addr:street=Tannenweg: {len(buildings)}")
print()

import re
def parse_num(s):
    m = re.match(r"^(\d+)", str(s).strip())
    return int(m.group(1)) if m else None

# Show all buildings with their housenumbers
print(f"{'Nr':<12} {'Building tag':<20} {'PLZ':<8} {'In range 1b-7?'}")
print("-" * 58)

in_range = []
out_of_range = []
no_number = []

for b in buildings:
    hn = b["housenumber"]
    num = parse_num(hn)
    if not hn:
        tag = "(no housenumber)"
        status = "NO NR"
        no_number.append(b)
    elif num is not None and 1 <= num <= 7:
        tag = "IN RANGE"
        status = "YES"
        in_range.append(b)
    else:
        tag = "out of range"
        status = "NO"
        out_of_range.append(b)

    print(f"  {hn:<10} {b['building']:<20} {b['postcode']:<8} {status}")

print()
print("=" * 58)
print(f"  IN RANGE (housenumber 1-7)  : {len(in_range):>3}")
print(f"  OUT OF RANGE (housenumber >7): {len(out_of_range):>3}")
print(f"  NO HOUSENUMBER              : {len(no_number):>3}")
print(f"  TOTAL                       : {len(buildings):>3}")
print()
print("CONCLUSION:")
print(f"  cluster_building_count = {len(in_range)} (only buildings with housenumber 1-7)")
print(f"  building_count_total   = {len(buildings)} (ALL buildings on Tannenweg, any housenumber)")
print()
if out_of_range:
    print(f"  The {len(out_of_range)} 'out of range' buildings are on the SAME STREET (Tannenweg)")
    print(f"  but have higher house numbers (>7), meaning they belong to a different")
    print(f"  SECTION of the street that was separately clustered.")
    nrs = sorted(set(b["housenumber"] for b in out_of_range))
    print(f"  Their house numbers: {nrs[:20]}{'...' if len(nrs)>20 else ''}")
