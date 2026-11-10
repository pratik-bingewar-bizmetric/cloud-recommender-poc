#!/usr/bin/env python3
"""Dedicated controlled database migration runner for Cloud Recommender.

This script executes Alembic migrations as a standalone operational step.
In compliance with production deployment policies, migrations are NEVER
executed automatically during application startup.
"""

import argparse
import sys
from pathlib import Path

# Add backend/src to sys.path so cloud_recommender can be imported
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from alembic.config import Config  # noqa: E402

from alembic import command  # noqa: E402
from cloud_recommender.core.config import get_settings  # noqa: E402


def get_alembic_config() -> Config:
    """Build Alembic configuration pointing to backend/alembic directory."""
    ini_path = backend_dir / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"Alembic configuration file not found at {ini_path}")

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

    settings = get_settings()
    safe_url = settings.database_url.replace("%", "%%")
    alembic_cfg.set_main_option("sqlalchemy.url", safe_url)
    return alembic_cfg


def check_database_accessible(database_url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Synchronous pre-flight socket probe for target database."""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(
        database_url.replace("postgresql+asyncpg://", "http://").replace("postgresql://", "http://")
    )
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        err = s.connect_ex((host, port))
        s.close()
        if err == 0:
            return True, f"Port {port} on {host} is responding."
        else:
            return False, f"Port {port} on {host} returned status code {err}."
    except Exception as exc:
        return False, str(exc)


def run_upgrade(revision: str = "head") -> int:
    """Apply migrations up to the target revision."""
    config = get_alembic_config()
    print(f"\nExecuting controlled migration to target revision: {revision}", flush=True)
    try:
        command.upgrade(config, revision)
        print("  Migration completed successfully (OK).", flush=True)
        return 0
    except Exception as exc:
        print(f"  Migration failed: {exc}", file=sys.stderr, flush=True)
        return 1


def check_current_revision() -> int:
    """Show the currently applied revision in the database."""
    config = get_alembic_config()
    print("\nQuerying current migration revision:", flush=True)
    try:
        command.current(config)
        return 0
    except Exception as exc:
        print(f"  Failed to query revision: {exc}", file=sys.stderr, flush=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Controlled PostgreSQL Migration Runner for Cloud Recommender"
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Target migration revision (default: head)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check database connectivity and current revision without upgrading",
    )
    args = parser.parse_args()

    settings = get_settings()
    target_display = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Pre-flight: Checking PostgreSQL connectivity for target: {target_display}...", flush=True)

    is_connected, detail = check_database_accessible(settings.database_url)
    if not is_connected:
        print(f"  Database Status : UNREACHABLE ({detail})", flush=True)
        print("  Guidance        : Ensure PostgreSQL is running and accessible from this environment.", flush=True)
        print("  Production Note : For Azure Databricks Apps, set DATABASE_URL to your Azure PostgreSQL Flexible Server.", flush=True)
        if args.check_only:
            print("  Check Verdict   : Pre-flight completed (Database is offline / unreachable).", flush=True)
            return 0
        return 2

    print(f"  Database Status : REACHABLE ({detail})", flush=True)

    if args.check_only:
        return check_current_revision()

    return run_upgrade(args.revision)


if __name__ == "__main__":
    sys.exit(main())
