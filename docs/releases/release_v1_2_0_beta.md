# D-ESS Engine Release v1.2.0 (Beta)
**Date**: 2026-03-01  
**Release Type**: Internal Validation / Beta  
**Scope**: Module 2 (Logic) + Module 3 (E2E Integration) Qualified  

## 1. Release Quality
This build has passed the **Global Regression Meta Suite: PASS**.
- **Module 2 (Logic)**: PASS (All baseline cases)
- **Module 3 (Integration)**: 13/13 checks PASS

## 2. Artifact Hashes (Build Anchor)
Refer to the official Qualified Report for full traceability:
[Module 3 E2E Integration Qualified Report](../reports/module3_e2e_integration_qualified_v1.md)

| Artifact | SHA256 Hash |
| :--- | :--- |
| `core/dess_main.py` | (See Qualified Report) |
| `core/dess_state_machine.py` | (See Qualified Report) |
| `evidence_store/evidence_index.json` | (See Qualified Report) |
| `tests/packs/module3_e2e_pack_v1.json` | (See Qualified Report) |

## 3. Reproducibility & Determinism
- **Status**: `VERIFIED (CI)`
- **Verification Method**: 
  1. **Dual-Environment Parity**: CI job installs `requirements.lock` into two isolated virtual environments; `pip freeze` outputs must be identical (Diff=Empty).
  2. **Report Determinism Gate**: A dedicated test (`test_report_determinism.py`) runs the engine twice with identical input (E2E-01 Golden). Normalized report hashes must match perfectly.
- **Protection**: These checks are now mandatory CI gates. Any dependency drift or non-deterministic logic change will fail the build.

## 4. Known Limitations
- **UI Interaction**: This release is CLI/Adapter focused. GUI compatibility has not been end-to-end verified in this milestone.

## 5. How to Run
```bash
# Global Regression
pytest -q d-ess-engine/tests/test_regression_all.py -x

# Determinism Gate (Phase 5)
pytest -q d-ess-engine/tests/test_report_determinism.py -x
```
