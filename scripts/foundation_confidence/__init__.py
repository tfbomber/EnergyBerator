"""
foundation_confidence/__init__.py

Public API for the Street Confidence Layer (Enhancement C).

Exports ONLY what generate_foundation_layer.py needs:
  - compute_street_confidence()

Do NOT import anything from this module into gate logic,
ranking pipelines, or scoring computations.
"""

from .confidence_rules import compute_street_confidence  # noqa: F401

__all__ = ["compute_street_confidence"]
