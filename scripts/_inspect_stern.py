import osmium

class WayHandler(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.stern_buildings = []

    def way(self, w):
        tags = w.tags
        street = tags.get("addr:street", "")
        if "Sternstra" in street:
            self.stern_buildings.append({
                "id": w.id,
                "building": tags.get("building", ""),
                "levels": tags.get("building:levels", ""),
                "nodes": len(w.nodes)
            })

handler = WayHandler()
handler.apply_file("data/osm/duesseldorf-regbez-latest.osm.pbf")
print(f"Total Sternstrasse buildings: {len(handler.stern_buildings)}")

tags = {}
levels = {}
for b in handler.stern_buildings:
    tag = b['building']
    tags[tag] = tags.get(tag, 0) + 1
    lvl = b['levels']
    if lvl:
        levels[lvl] = levels.get(lvl, 0) + 1
    else:
        levels["MISSING"] = levels.get("MISSING", 0) + 1

print(f"Tags: {tags}")
print(f"Levels: {levels}")
