"""Regression test for Phase 1-5 fixes."""
import sys, os, json
sys.path.insert(0, 'D:/Stock Analysis/D-Energy Berater/d-ess-engine')
sys.stdout.reconfigure(encoding='utf-8')
os.chdir('D:/Stock Analysis/D-Energy Berater/d-ess-engine')

print("=== REGRESSION TEST: Phase 1-5 Fixes ===")
FAIL_COUNT = 0

def ok(msg): print(f"  PASS | {msg}")
def fail(msg):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  FAIL | {msg}")

# T1: calculate_roi_dual
print("\n[T1] calculate_roi_dual ...")
from core.roi_mvp import calculate_roi_dual
with open("policies/roi_hp_mvp_neuss_2026.json", encoding="utf-8") as f:
    policy = json.load(f)
base = {"case_id": "REG", "attributes": {"has_pv": False, "household_size": "3", "kwp_override": 10}}
r = calculate_roi_dual(base, policy)
if r["household"]["verdict"] == "ROI_OK": ok("household verdict OK")
else: fail("household verdict not ROI_OK")
if r["high_load"]["verdict"] == "ROI_OK": ok("high_load verdict OK")
else: fail("high_load verdict not ROI_OK")
hh_hp = r["household"]["household_snapshot"]["e_hp_kwh"]
hl_hp = r["high_load"]["household_snapshot"]["e_hp_kwh"]
if hh_hp == 0: ok(f"HOUSEHOLD e_hp=0 (correct)")
else: fail(f"HOUSEHOLD e_hp={hh_hp} (should be 0)")
if hl_hp > 0: ok(f"HIGH_LOAD e_hp={hl_hp} (correct)")
else: fail(f"HIGH_LOAD e_hp={hl_hp} (should be >0)")
delta = r["delta_annual_eur"]
uplift = r["hp_uplift_class"]
if delta > 0: ok(f"delta={delta} EUR | class={uplift}")
else: fail(f"delta={delta} (should be >0)")

# T2: copy_de
print("\n[T2] copy_de LABELS + COPY ...")
from ui.copy_de import LABELS, COPY
if "prio_sofort" in LABELS and "roi_assumptions" in COPY and "uwg_footnote_high_load" in COPY:
    ok(f"LABELS={len(LABELS)} keys, COPY={len(COPY)} keys")
else:
    fail("Missing required keys")
if "garantiert" not in str(COPY).lower():
    ok("No forbidden word 'garantiert' in COPY")
else:
    fail("Forbidden word 'garantiert' found")

# T3: ui_shared.py exists
print("\n[T3] ui_shared.py ...")
if os.path.exists("ui/components/ui_shared.py"):
    ok("ui/components/ui_shared.py exists")
else:
    fail("ui/components/ui_shared.py missing")

# T4: campaign_tools.py exists
print("\n[T4] campaign_tools.py ...")
if os.path.exists("ui/components/campaign_tools.py"):
    ok("ui/components/campaign_tools.py exists")
else:
    fail("ui/components/campaign_tools.py missing")

# T5: de_copy_guard check
print("\n[T5] de_copy_guard violations in street_roi_generator.py ...")
with open("ui/components/street_roi_generator.py", encoding="utf-8") as f:
    src = f.read()
bad_words = ["EFH Detached", "DHH Semi-Det", "RH Rowhouse", "HP+PV", "PV only (kein HP)", "ROI Error:", "VAT 0%"]
found = [b for b in bad_words if b in src]
if not found:
    ok("No de_copy_guard violations found")
else:
    fail(f"Violations still present: {found}")

# T6: render_vollbericht_expander
print("\n[T6] render_vollbericht_expander ...")
if "def render_vollbericht_expander" in src:
    ok("Function defined")
else:
    fail("Function missing")
if "calculate_roi_dual" in src:
    ok("calculate_roi_dual called")
else:
    fail("calculate_roi_dual not referenced")
if "Gespr" in src:
    ok("Gesprächsleitfaden present")
else:
    fail("Gesprächsleitfaden missing")
if "generate_vollbericht_pdf" in src and "generate_flyer_pdf" in src:
    ok("PDF download buttons present")
else:
    fail("PDF functions missing")

# T7: campaign_tools syntax check
print("\n[T7] campaign_tools syntax ...")
import ast
with open("ui/components/campaign_tools.py", encoding="utf-8") as f:
    ct_src = f.read()
try:
    ast.parse(ct_src)
    ok("campaign_tools.py parses OK")
except SyntaxError as e:
    fail(f"SyntaxError: {e}")

print(f"\n{'='*40}")
if FAIL_COUNT == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{FAIL_COUNT} TEST(S) FAILED")
