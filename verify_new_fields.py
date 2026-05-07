import sys, json
sys.stdout.reconfigure(encoding="utf-8")

with open(r"output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    data = json.load(f)

keywords = ["Tannenweg", "Marienburger", "Schluchenhau", "Gladbacher"]
shown = set()
for c in data:
    street = c["street_name"]
    if any(k in street for k in keywords) and street not in shown:
        shown.add(street)
        rng = c.get("address_range", "?")
        tot = c.get("building_count_total", "?")
        clust = c.get("cluster_building_count", "N/A")
        unadr = c.get("unaddressed_building_count", "N/A")
        cov   = c.get("address_filter_coverage", "N/A")
        print(f"=== {street} (range: {rng}) ===")
        print(f"  building_count_total       = {tot}   <- street-level (unchanged, used for scoring)")
        print(f"  cluster_building_count     = {clust}  <- range-filtered NEW field")
        print(f"  unaddressed_building_count = {unadr}  <- no housenumber in OSM")
        print(f"  address_filter_coverage    = {cov}   <- fraction with housenumber")
        print()
