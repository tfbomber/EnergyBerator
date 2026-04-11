"""
foundation_explainer/__init__.py

Public API for the Layer 1.5 Explanation / Sales Translation Layer.

Exports ONLY what generate_foundation_layer.py needs:
  - generate_explanation()

THIS MODULE IS METADATA-ONLY.
Do not use any output field from this module in:
  gate logic, ranking, scoring, filtering, or sorting.
"""

from .explainer_rules import generate_explanation  # noqa: F401

__all__ = ["generate_explanation"]
