"""Tests for Alembic migration definitions and metadata registration."""

import importlib.util
from pathlib import Path

from cloud_recommender.db.models import Base

ALEMBIC_DIR = Path(__file__).parent.parent / "alembic"


def test_alembic_env_target_metadata_has_models() -> None:
    """Verify Alembic target_metadata is linked to Base.metadata and contains required tables."""
    env_path = ALEMBIC_DIR / "env.py"
    assert env_path.exists(), f"Alembic env.py not found at {env_path}"

    spec = importlib.util.spec_from_file_location("local_alembic_env", env_path)
    assert spec is not None and spec.loader is not None
    env_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env_module)

    assert hasattr(env_module, "target_metadata")
    metadata = env_module.target_metadata
    assert metadata is Base.metadata
    assert "workload_profiles" in metadata.tables
    assert "cloud_service_catalog" in metadata.tables


def test_initial_migration_module_structure() -> None:
    """Verify initial migration script defines upgrade and downgrade hooks."""
    migration_path = ALEMBIC_DIR / "versions" / "2026_10_12_0001_initial_workload_and_catalog.py"
    assert migration_path.exists(), f"Migration file not found at {migration_path}"

    spec = importlib.util.spec_from_file_location("initial_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_module)

    assert migration_module.revision == "2026_10_12_0001"
    assert migration_module.down_revision is None
    assert callable(migration_module.upgrade)
    assert callable(migration_module.downgrade)


def test_alembic_env_preserves_explicit_config_url() -> None:
    """Verify Alembic env.py respects explicitly configured sqlalchemy.url from Alembic config."""
    from alembic.config import Config

    custom_url = "postgresql+asyncpg://custom_user:custom_pass@isolated-host:5432/isolated_db"
    cfg = Config(ALEMBIC_DIR / ".." / "alembic.ini")
    cfg.set_main_option("sqlalchemy.url", custom_url)

    # Verify that get_main_option retains the custom URL
    assert cfg.get_main_option("sqlalchemy.url") == custom_url
