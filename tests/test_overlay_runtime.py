import json
import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core")))

import main


CASES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cases"))
POLICIES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "policies"))


def test_overlay_matches_policy_id_alias_by_year(tmp_path):
    policy_path = tmp_path / "policy.json"
    policy = {
        "policy_id": "DUS_BALCONY_PV_2025",
        "status": "Active",
        "citations": {
            "source_url": "https://example.org/policy.pdf",
            "doc_version": "2025",
            "last_policy_sync_timestamp": "2026-01-01T00:00:00Z",
        },
    }
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    intelligence_dir = tmp_path / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    overlay = {
        "updates": {
            "DUS_BALCONY_PV_2026": {
                "policy_id": "DUS_BALCONY_PV_2026",
                "last_checked_utc": "2026-02-21T17:51:21.187680",
                "status": "PAUSED",
                "health": "OK",
                "status_reason_de": "Program under revision.",
                "signals": {
                    "landing_claim_open": False,
                    "portal_operational": True,
                    "portal_allows_new_application": "unknown",
                },
                "doc_integrity": {
                    "remote_hash": "sha256:test-remote-hash",
                    "local_hash_match": True,
                    "last_modified": None,
                    "etag": None,
                },
                "evidence": {
                    "snapshot_id": "file://test_snapshot.html",
                    "timestamp": "2026-02-21T17:51:21.187755",
                },
            }
        }
    }
    (intelligence_dir / "status_updates.json").write_text(json.dumps(overlay), encoding="utf-8")

    merged = main.load_policy_with_overlay(str(policy_path), str(tmp_path))

    assert merged["status"] == "PAUSED"
    assert merged["citations"]["last_policy_sync_timestamp"].endswith("Z")
    assert merged["citations"]["doc_hash"] == "sha256:test-remote-hash"
    assert merged["_runtime_status"]["source"] == "OVERLAY"


def test_run_engine_returns_blocked_report_when_policy_closed(monkeypatch, tmp_path):
    policy_path = os.path.join(POLICIES_DIR, "dus_balcony_pv.json")
    case_path = os.path.join(CASES_DIR, "golden_001_input.json")

    original_loader = main.load_policy_with_overlay

    def _force_closed(path, base_dir):
        policy = original_loader(path, base_dir)
        policy["status"] = "CLOSED"
        policy["_runtime_status"] = {
            "source": "OVERLAY",
            "status": "CLOSED",
            "status_reason_de": "Test-injected closed status.",
            "health": "OK",
            "last_checked_utc": "2026-02-26T00:00:00Z",
            "snapshot_id": "file://test_closed_snapshot.html",
            "doc_hash": None,
        }
        policy.setdefault("citations", {})
        policy["citations"]["last_policy_sync_timestamp"] = "2026-02-26T00:00:00Z"
        return policy

    monkeypatch.setattr(main, "load_policy_with_overlay", _force_closed)

    report = main.run_engine(policy_path, case_path, str(tmp_path))

    assert report is not None
    assert report["status"] == "BLOCKED"
    assert report["subsidy_total_cents"] == 0
    assert any(v["code"] == "REJECTED_POLICY_CLOSED" for v in report["violations"])
    assert report["policy_runtime_status"]["status"] == "CLOSED"


def test_run_engine_allows_needs_input_status_contract(monkeypatch, tmp_path):
    policy_path = os.path.join(POLICIES_DIR, "dus_balcony_pv.json")
    case_path = tmp_path / "needs_input_case.json"
    case_data = {
        "case_id": "TC_NEEDS_INPUT_001",
        "attributes": {},
        "costs": {"currency": "EUR", "buckets": {}},
        "timeline_events": [],
    }
    case_path.write_text(json.dumps(case_data), encoding="utf-8")

    original_loader = main.load_policy_with_overlay

    def _force_open(path, base_dir):
        policy = original_loader(path, base_dir)
        policy["status"] = "OPEN"
        policy["_runtime_status"] = {
            "source": "STATIC",
            "status": "OPEN",
            "status_reason_de": "Test-injected open status.",
            "health": "N/A",
            "last_checked_utc": None,
            "snapshot_id": None,
            "doc_hash": None,
        }
        return policy

    monkeypatch.setattr(main, "load_policy_with_overlay", _force_open)

    report = main.run_engine(policy_path, str(case_path), str(tmp_path))

    assert report["status"] == "NEEDS_INPUT"
    assert report["policy_runtime_status"]["status"] == "OPEN"
    assert report["violations"]
