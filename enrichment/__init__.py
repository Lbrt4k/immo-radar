"""ImmoRadar - Enrichment modules"""
from .dvf import enrich_with_dvf
from .dpe import enrich_with_dpe

__all__ = ["enrich_with_dvf", "enrich_with_dpe"]
