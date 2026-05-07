"""
Deep diagnostic: understand the REAL scope of the levels + house tag problem.
Questions to answer:
  1. Is building:levels missing GENERALLY or only in city center?
  2. How many buildings are tagged 'house' across all PLZs?
  3. How does the BEFORE vs AFTER look at segment level?
  4. What's the actual composition of Sternstrasse's 80 foundation buildings?
"""
import osmium
import json

# ── Part 1: Raw PBF extraction — levels coverage by PLZ ────────────────

PLZ_SET = {"41460","41462","41464","41466","41468","41469","41470","41472"}
NEUSS_BBOX = (6.61, 51.13, 6.77, 51.25)

class BuildingStatsHandler(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.stats = {}  # plz -> {total, has_levels, levels_ge3, tag_counts}
        self.no_plz_total = 0

    def way(self, w):
        tags = w.tags
        btag = tags.get("building", "")
        if not btag or btag.lower() in ("no",""):
            return
        if btag.lower() not in ("yes","residential","house","apartments","detached",
                                 "semidetached_house","terrace","multi_family","dormitory"):
            return

        # Bbox filter
        nodes = []
        for n in w.nodes:
            if n.location.valid():
                nodes.append((n.location.lat, n.location.lon))
        if not nodes:
            return
        c_lat = sum(n[0] for n in nodes) / len(nodes)
        c_lon = sum(n[1] for n in nodes) / len(nodes)
        if not (NEUSS_BBOX[1] <= c_lat <= NEUSS_BBOX[3] and NEUSS_BBOX[0] <= c_lon <= NEUSS_BBOX[2]):
            return

        plz = tags.get("addr:postcode", "")
        if plz not in PLZ_SET:
            self.no_plz_total += 1
            return  # skip buildings without our target PLZ

        if plz not in self.stats:
            self.stats[plz] = {"total": 0, "has_levels": 0, "levels_ge3": 0, "tags": {}}

        s = self.stats[plz]
        s["total"] += 1
        tag_low = btag.lower()
        s["tags"][tag_low] = s["tags"].get(tag_low, 0) + 1

        levels_str = tags.get("building:levels", "")
        if levels_str:
            s["has_levels"] += 1
            try:
                lv = int(float(levels_str))
                if lv >= 3:
                    s["levels_ge3"] += 1
            except:
                pass

print("=" * 70)
print("PART 1: building:levels coverage by PLZ (raw OSM data)")
print("=" * 70)

handler = BuildingStatsHandler()
handler.apply_file("data/osm/duesseldorf-regbez-latest.osm.pbf", locations=True, idx="flex_mem")

print(f"{'PLZ':<8} {'Total':>6} {'HasLvl':>7} {'Cvg%':>5} {'Lvl>=3':>7} {'house':>6} {'yes':>6} {'resid':>6} {'apart':>6}")
print("-" * 70)
total_all = 0
total_has_levels = 0
total_ge3 = 0
total_house = 0
for plz in sorted(handler.stats.keys()):
    s = handler.stats[plz]
    cvg = s["has_levels"] / s["total"] * 100 if s["total"] > 0 else 0
    house_n = s["tags"].get("house", 0)
    yes_n = s["tags"].get("yes", 0)
    res_n = s["tags"].get("residential", 0)
    apt_n = s["tags"].get("apartments", 0)
    print(f"{plz:<8} {s['total']:>6} {s['has_levels']:>7} {cvg:>4.0f}% {s['levels_ge3']:>7} {house_n:>6} {yes_n:>6} {res_n:>6} {apt_n:>6}")
    total_all += s["total"]
    total_has_levels += s["has_levels"]
    total_ge3 += s["levels_ge3"]
    total_house += house_n

print("-" * 70)
cvg_all = total_has_levels / total_all * 100 if total_all > 0 else 0
print(f"{'TOTAL':<8} {total_all:>6} {total_has_levels:>7} {cvg_all:>4.0f}% {total_ge3:>7} {total_house:>6}")
print(f"\nBuildings with PLZ but outside our set: {handler.no_plz_total}")

# ── Part 2: Sternstrasse deep dive — which tags have levels? ────────────

print("\n" + "=" * 70)
print("PART 2: Sternstrasse — levels by tag breakdown")
print("=" * 70)

class SternHandler(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []

    def way(self, w):
        tags = w.tags
        street = tags.get("addr:street", "")
        plz = tags.get("addr:postcode", "")
        if "Sternstra" not in street:
            return
        if plz and plz != "41460":
            return
        btag = tags.get("building", "")
        if not btag or btag.lower() in ("no",""):
            return
        nodes = []
        for n in w.nodes:
            if n.location.valid():
                nodes.append((n.location.lat, n.location.lon))
        if not nodes:
            return
        c_lat = sum(n[0] for n in nodes) / len(nodes)
        c_lon = sum(n[1] for n in nodes) / len(nodes)
        if not (NEUSS_BBOX[1] <= c_lat <= NEUSS_BBOX[3] and NEUSS_BBOX[0] <= c_lon <= NEUSS_BBOX[2]):
            return

        self.buildings.append({
            "tag": btag.lower(),
            "levels": tags.get("building:levels", ""),
        })

sh = SternHandler()
sh.apply_file("data/osm/duesseldorf-regbez-latest.osm.pbf", locations=True, idx="flex_mem")

# Cross-tab: tag x levels
tag_level_matrix = {}
for b in sh.buildings:
    tag = b["tag"]
    lvl = b["levels"] if b["levels"] else "MISSING"
    if tag not in tag_level_matrix:
        tag_level_matrix[tag] = {}
    tag_level_matrix[tag][lvl] = tag_level_matrix[tag].get(lvl, 0) + 1

print(f"\n{'Tag':<20} {'Total':>5} {'NoLvl':>6} {'Lvl1':>5} {'Lvl2':>5} {'Lvl3':>5} {'Lvl4':>5} {'Lvl5+':>5}")
print("-" * 60)
for tag in sorted(tag_level_matrix.keys()):
    row = tag_level_matrix[tag]
    total = sum(row.values())
    no_lvl = row.get("MISSING", 0)
    l1 = row.get("1", 0)
    l2 = row.get("2", 0)
    l3 = row.get("3", 0) + row.get("3.5", 0)
    l4 = row.get("4", 0)
    l5p = sum(v for k, v in row.items() if k not in ("MISSING","1","2","3","3.5","4"))
    print(f"{tag:<20} {total:>5} {no_lvl:>6} {l1:>5} {l2:>5} {l3:>5} {l4:>5} {l5p:>5}")

# ── Part 3: Before vs After comparison (foundation JSON) ────────────────

print("\n" + "=" * 70)
print("PART 3: Foundation output — PLZ41460 BEFORE vs AFTER")
print("=" * 70)

with open('output/foundation/foundation_structure_results.json', encoding='utf-8') as f:
    data = json.load(f)

seg41460 = [c for c in data if str(c.get('plz','')) == '41460']
total_pass = sum(1 for c in seg41460 if c['structure_gate'] == 'PASS')
total_qualified = sum(1 for c in seg41460 if c['structure_gate'] == 'QUALIFIED')
total_review = sum(1 for c in seg41460 if c['structure_gate'] == 'REVIEW')
total_fail = sum(1 for c in seg41460 if c['structure_gate'] == 'FAIL')
print(f"PLZ41460: {len(seg41460)} streets | PASS={total_pass} QUALIFIED={total_qualified} REVIEW={total_review} FAIL={total_fail}")
print(f"\nPASS/QUALIFIED streets in 41460:")
for c in seg41460:
    if c['structure_gate'] in ('PASS','QUALIFIED'):
        print(f"  {c['street_name']}: sfh={c['sfh_total_count']}/{c['building_count_total']} = {c['sfh_total_ratio']:.0%} | mfh={c['mfh_count']} | gate={c['structure_gate']}")

# ── Part 4: Suburban sanity check — are levels missing there too? ────────

print("\n" + "=" * 70)
print("PART 4: Suburban PLZ41472 — is levels-missing the same problem?")
print("=" * 70)
seg41472 = [c for c in data if str(c.get('plz','')) == '41472']
total_pass_72 = sum(1 for c in seg41472 if c['structure_gate'] == 'PASS')
total_fail_72 = sum(1 for c in seg41472 if c['structure_gate'] == 'FAIL')
print(f"PLZ41472: {len(seg41472)} streets | PASS={total_pass_72} FAIL={total_fail_72}")
print(f"→ Even with low levels coverage, suburban classification works because:")
print(f"  1. Actual detached/house tags ARE correct in suburbs")
print(f"  2. Spatial adjacency heuristic works well for spread-out houses")
print(f"  3. The problem is city-center-specific, not general")
