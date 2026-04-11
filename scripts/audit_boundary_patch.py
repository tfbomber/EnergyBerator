import requests
import json
import os

print("--- Boundary Patch Validation Audit ---")

# We will measure the impact of the 6.715 cut.
# We fetch a bounding box of data and classify it
query = """
[out:json][timeout:50];
(
  way["building"~"residential|house|apartments"](51.13, 6.715, 51.23, 6.80);
);
out center tags;
"""
print("Fetching buildings right of the 6.715 cut line...")
resp = requests.post("http://overpass-api.de/api/interpreter", data={"data": query})
elements = resp.json().get("elements", [])

dus_count = 0
neuss_count = 0
neuss_samples = []
dus_samples = set()

for el in elements:
    if "center" not in el: continue
    tags = el.get("tags", {})
    plz = tags.get("addr:postcode", "")
    street = tags.get("addr:street", "")
    lat = el["center"]["lat"]
    lon = el["center"]["lon"]
    
    if plz.startswith("414") or tags.get("addr:city", "").lower() == "neuss":
        neuss_count += 1
        if street and len(neuss_samples) < 5 and street not in [s[0] for s in neuss_samples]:
            neuss_samples.append((street, plz, lat, lon))
    elif plz.startswith("40") or tags.get("addr:city", "").lower() == "düsseldorf":
        dus_count += 1
        if street:
            dus_samples.add(street)

print(f"\nBuildings explicitly in the cut zone (lon > 6.715): {len(elements)}")
print(f"Düsseldorf buildings successfully excluded: {dus_count}")
print(f"Neuss buildings falsely excluded (False Negatives!): {neuss_count}")

print("\nSample of Neuss streets wrongly excluded:")
for s in neuss_samples:
    print(f" - {s[0]} ({s[1]}), lat: {s[2]}, lon: {s[3]}")

print("\nDid we successfully exclude the DUS leaks?")
leaks = ["Gladbacher Straße", "Volmerswerther Deich", "Merkurstraße"]
for leak in leaks:
    if leak in dus_samples:
        print(f" [PASS] {leak} was in the cut zone and is now excluded.")
    else:
        print(f" [?] {leak} not found in this slice (might be caught by another filter).")

if neuss_count > 50:
    print("\nVERDICT: TOO_AGGRESSIVE")
    print("The 6.715 hard trim causes material Neuss data loss (e.g., Uedesheim, Grimlinghausen).")
else:
    print("\nVERDICT: ACCEPTABLE_MVP_PATCH")
