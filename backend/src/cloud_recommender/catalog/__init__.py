"""Cloud service catalog and fixture management."""

from cloud_recommender.catalog.seeds import load_curated_catalog, seed_catalog

__all__ = ["load_curated_catalog", "seed_catalog"]
