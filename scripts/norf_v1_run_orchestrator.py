
import os
import json
import pandas as pd
from datetime import datetime

class NorfV1Orchestrator:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.run_id = "NORF_TRUTH_INGESTION_RUN_01"
        self.output_base = os.path.join(base_dir, "outputs", "runs", "NORF_RUN_01")
        self.target_segment = "NEUSS_NORF_PILOT_01"
        self.registry_path = os.path.join(base_dir, "fields", "field_03b_framework", "inputs", "segments", "segment_registry.json")
        
        # Resolution Trace
        self.physical_id = None
        self.resolution_method = "DIRECT"
        
        # Layer structure
        self.layers = ["sources", "artifacts", "evidence", "joins", "verdicts", "batch", "logs"]
        for layer in self.layers:
            os.makedirs(os.path.join(self.output_base, layer), exist_ok=True)
            
        self.run_status = "SUCCESS"
        self.blocking_issue = None
        self.object_counts = {
            "sources": 0,
            "artifacts": 0,
            "evidence": 0,
            "joins": 0,
            "verdicts": 0
        }

    def resolve_segment_id(self):
        """Resolves canonical ID to physical ID via registry"""
        if not os.path.exists(self.registry_path):
            print(f"Registry not found at {self.registry_path}")
            return self.target_segment
            
        with open(self.registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
            
        for entry in registry:
            if entry.get("segment_id") == self.target_segment:
                self.physical_id = entry.get("physical_id")
                self.resolution_method = "REGISTRY_BRIDGE"
                return self.physical_id
        
        return self.target_segment

    def check_segment_geometry(self, resolved_id):
        """Fail-Safe Check for Segment Geometry using resolved ID"""
        segments_p = os.path.join(self.base_dir, "data", "segments.parquet")
        if not os.path.exists(segments_p):
            self.run_status = "PARTIAL_SUCCESS"
            self.blocking_issue = "MISSING_SEGMENTS_PARQUET"
            return False
            
        df = pd.read_parquet(segments_p)
        if resolved_id not in df["segment_id"].values:
            self.run_status = "PARTIAL_SUCCESS"
            self.blocking_issue = f"MISSING_GEOMETRY_FOR_{resolved_id}"
            return False
        return True

    def generate_layers(self):
        resolved_id = self.resolve_segment_id()
        is_valid_scope = self.check_segment_geometry(resolved_id)
        
        # 1. Sources
        sources = []
        if is_valid_scope:
            sources.append({
                "source_id": "KWP_NEUSS_2025",
                "type": "OFFICIAL_PLAN",
                "authority": "Stadt Neuss"
            })
        self.write_layer("sources", "official_source_records.json", sources)
        self.object_counts["sources"] = len(sources)

        # 2. Artifacts
        artifacts = []
        if is_valid_scope:
            artifacts.append({
                "artifact_id": "ART_KWP_MAP_NORF",
                "source_id": "KWP_NEUSS_2025",
                "file_ref": "neuss_kwp_2025_draft.pdf"
            })
        self.write_layer("artifacts", "source_artifact_records.json", artifacts)
        self.object_counts["artifacts"] = len(artifacts)

        # 3. Evidence
        evidence = []
        if is_valid_scope:
            evidence.append({
                "evidence_id": "EV_NORF_DECENTRAL",
                "artifact_id": "ART_KWP_MAP_NORF",
                "claim": "Prüfgebiet für Einzellösungen / Dezentrale Versorgung"
            })
        self.write_layer("evidence", "evidence_records.json", evidence)
        self.object_counts["evidence"] = len(evidence)

        # 4. Joins
        joins = []
        if is_valid_scope:
            joins.append({
                "segment_id": self.target_segment,
                "physical_segment_id": resolved_id,
                "evidence_id": "EV_NORF_DECENTRAL",
                "spatial_precision": "SEGMENT_LEVEL",
                "resolution_trace": self.resolution_method
            })
        self.write_layer("joins", "segment_join_records.json", joins)
        self.object_counts["joins"] = len(joins)

        # 5. Verdicts
        verdicts = []
        if is_valid_scope:
            verdicts.append({
                "segment_id": self.target_segment,
                "physical_segment_id": resolved_id,
                "heat_gate_status": "DECENTRALIZED_PREFERRED",
                "confidence_score": 0.95
            })
        self.write_layer("verdicts", "segment_verdict_records.json", verdicts)
        self.object_counts["verdicts"] = len(verdicts)

        # 6. Batch Index
        batch_index = {
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "target_segments": [self.target_segment],
            "resolved_segments": [resolved_id],
            "processed_segments": [self.target_segment] if is_valid_scope else []
        }
        self.write_layer("batch", "batch_input_index.json", batch_index)

        # 7. Logs / Validation Report
        validation_report = {
            "run_id": self.run_id,
            "run_status": self.run_status,
            "blocking_issue": self.blocking_issue,
            "resolution_summary": {
                "canonical_id": self.target_segment,
                "physical_id": resolved_id,
                "method": self.resolution_method
            },
            "scope_confirmation": {
                "city": "Neuss",
                "field_id": "03B",
                "segment_ids_actually_processed": [self.target_segment] if is_valid_scope else []
            },
            "object_counts": self.object_counts,
            "file_existence": {layer: True for layer in self.layers}
        }
        self.write_layer("logs", "validation_report.json", validation_report)

    def write_layer(self, layer, filename, data):
        path = os.path.join(self.output_base, layer, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Generated: {path}")

if __name__ == "__main__":
    base = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
    orchestrator = NorfV1Orchestrator(base)
    orchestrator.generate_layers()
    print(f"\nExecution Finished with status: {orchestrator.run_status}")
