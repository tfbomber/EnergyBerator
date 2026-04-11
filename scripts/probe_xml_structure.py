"""
Quick diagnostic: read the first record element from EinheitenSolar_1.xml
and print all tag names + any coordinate-like fields.
"""

import io
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCE = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine\data\sources\mastr\2026-03-12_einheitensolar\EinheitenSolar_1.xml")

COORD_HINTS = {"breitengrad", "laengengrad", "laengen", "koordinate", "lat", "lon", "breite"}

records_found = 0
all_tags = set()

with io.open(SOURCE, mode="rt", encoding="utf-16le") as f:
    context = ET.iterparse(f, events=("end",))
    for event, elem in context:
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        # Collect every unique tag we see
        all_tags.add(local)

        # Look for any record element (containing child elements)
        if len(list(elem)) > 0 and local not in ("EinheitenSolar", "root", "data", "Export"):
            children = {
                (c.tag.split("}")[-1] if "}" in c.tag else c.tag): c.text
                for c in elem
            }

            # Only print records that look like unit entries (have a MastrNummer-style field)
            has_id = any("mastr" in k.lower() or "nummer" in k.lower() for k in children)
            if has_id and records_found < 2:
                records_found += 1
                print(f"\n=== RECORD #{records_found} - Element: <{local}> ===")
                for k, v in children.items():
                    marker = " <<< COORD" if any(h in k.lower() for h in COORD_HINTS) else ""
                    print(f"  {k}: {v!r}{marker}")

            # Free memory
            elem.clear()

        if records_found >= 2:
            break

print("\n=== ALL TAGS SEEN SO FAR ===")
for t in sorted(all_tags):
    print(f"  {t}")
