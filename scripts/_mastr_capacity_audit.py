"""
Root-cause diagnostic: Extract Nettonennleistung (capacity) distribution
from MaStR XML for Neuss PLZs to understand residential vs commercial mix.
"""
import re
from pathlib import Path

XML_DIR = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine\data\sources\mastr\2026-03-12_einheitensolar")
TARGET_PLZS = {"41460","41462","41464","41466","41468","41469","41470","41472"}

# Regex: capture PLZ and capacity within the same XML unit
# MaStR XML structure: each unit is wrapped in <EinheitSolar>...</EinheitSolar>
# We'll scan for units and extract both fields

plz_pattern = re.compile(r"<Postleitzahl>(\d{5})</Postleitzahl>")
cap_pattern = re.compile(r"<Nettonennleistung>([\d.]+)</Nettonennleistung>")
nutzung_pattern = re.compile(r"<Nutzungsbereich>(\d+)</Nutzungsbereich>")
unit_pattern = re.compile(r"<EinheitSolar>(.+?)</EinheitSolar>", re.DOTALL)

# Per-PLZ capacity buckets
results = {plz: {"total": 0, "le10": 0, "le30": 0, "le100": 0, "gt100": 0, "nutzung": {}} for plz in TARGET_PLZS}

chunk_size = 8 * 1024 * 1024  # 8 MB
overlap = 10000  # generous overlap for unit boundaries

xml_files = sorted(XML_DIR.glob("EinheitenSolar_*.xml"))
print(f"Scanning {len(xml_files)} XML files...")

for xml_file in xml_files:
    try:
        with open(xml_file, "rb") as f:
            bom = f.read(2)
            encoding = "utf-16-le" if bom == b"\xff\xfe" else "utf-16-be" if bom == b"\xfe\xff" else "utf-16"
            carry = ""
            while True:
                raw = f.read(chunk_size)
                if not raw:
                    # Process final carry
                    text = carry
                    carry = ""
                else:
                    text = carry + raw.decode(encoding, errors="ignore")
                    carry = text[-overlap:] if len(text) > overlap else text
                    text = text[:-overlap] if len(text) > overlap else text

                for m in unit_pattern.finditer(text):
                    unit_xml = m.group(1)
                    plz_m = plz_pattern.search(unit_xml)
                    if not plz_m or plz_m.group(1) not in TARGET_PLZS:
                        continue

                    plz = plz_m.group(1)
                    results[plz]["total"] += 1

                    cap_m = cap_pattern.search(unit_xml)
                    if cap_m:
                        cap = float(cap_m.group(1))
                        if cap <= 10:
                            results[plz]["le10"] += 1
                        elif cap <= 30:
                            results[plz]["le30"] += 1
                        elif cap <= 100:
                            results[plz]["le100"] += 1
                        else:
                            results[plz]["gt100"] += 1

                    nutz_m = nutzung_pattern.search(unit_xml)
                    if nutz_m:
                        n = nutz_m.group(1)
                        results[plz]["nutzung"][n] = results[plz]["nutzung"].get(n, 0) + 1

                if not raw:
                    break

    except Exception as e:
        print(f"Error: {xml_file.name}: {e}")

print("\n" + "=" * 80)
print("MaStR CAPACITY DISTRIBUTION BY PLZ")
print("=" * 80)
print(f"{'PLZ':<8} {'Total':>6} {'<=10kW':>7} {'10-30':>6} {'30-100':>7} {'>100kW':>7} {'Resid':>7} {'Nutzung':>20}")
print("-" * 80)

for plz in sorted(results.keys()):
    r = results[plz]
    resid = r["le10"] + r["le30"]  # residential = <= 30 kWp
    nutz_str = str(r["nutzung"]) if r["nutzung"] else "-"
    print(f"{plz:<8} {r['total']:>6} {r['le10']:>7} {r['le30']:>6} {r['le100']:>7} {r['gt100']:>7} {resid:>7} {nutz_str:>20}")

print()
print("KEY INSIGHT:")
total_all = sum(r['total'] for r in results.values())
total_resid = sum(r['le10'] + r['le30'] for r in results.values())
print(f"  Total PV units in Neuss: {total_all}")
print(f"  Residential (<=30kWp):   {total_resid} ({total_resid/total_all*100:.0f}%)")
print(f"  Commercial (>30kWp):     {total_all - total_resid} ({(total_all-total_resid)/total_all*100:.0f}%)")
