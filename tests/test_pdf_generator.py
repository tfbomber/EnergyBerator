import pytest
from ui.components.s2_pdf_generator import generate_sales_pdf_bytes

def test_pdf_returns_bytes_and_has_content():
    # Minimal report structure that the generator expects
    report = {
        "case_id": "TEST-123",
        "roi_result": {
            "kWp_rec": 10,
            "e_load_kwh": 5000,
            "household_snapshot": {
                "household_size": "3",
                "e_base_kwh": 3000,
                "e_hp_kwh": 2000,
                "e_load_total_kwh": 5000
            },
            "scenarios": [
                {
                    "name": "BASELINE",
                    "e_self_kwh": 2500,
                    "payback_dynamic_years": 8,
                    "annual_benefit_cents": 150000,
                    "profit20_cents": 2500000
                }
            ],
            "breakdown_base": {
                "self_saving_cents": 100000,
                "opex_cents": 20000
            },
            "export_analysis": {
                "eeg_income_eur": 50
            },
            "financing_report": {
                "enabled": True,
                "loan_monthly_payment_eur": 120,
                "monthly_savings_eur": 145,
                "monthly_cashflow_margin_eur": 25
            },
            "carbon_impact": {
                "annual_co2_reduction_tons": 2.5,
                "co2_20y_total_tons": 48
            }
        }
    }
    
    pdf_bytes = generate_sales_pdf_bytes(report)
    
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 5000  # Basic size check
    # We verify it starts with PDF magic number
    assert pdf_bytes.startswith(b"%PDF")

def test_pdf_no_financing_path():
    report = {
        "roi_result": {
            "financing_report": {"enabled": False},
            "scenarios": [{"name": "BASE", "e_self_kwh": 1000}]
        }
    }
    pdf_bytes = generate_sales_pdf_bytes(report)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 1000

def test_pdf_empty_report_graceful_failure():
    # Should not crash even with empty dicts or missing keys
    pdf_bytes = generate_sales_pdf_bytes({})
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF")
