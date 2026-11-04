"""Database initialisation for SpecGuard 2.0.

Run from the ``backend`` directory:

    python -m app.database.init_db

"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect

import app.models  # noqa: F401  (registers every model with Base.metadata)
from app.core.config import get_settings
from app.database.base import Base
from app.database.session import engine as default_engine

logger = logging.getLogger("specguard.database")

def init_db(bind: Engine | None = None) -> list[str]:
    """Create all registered tables (idempotent) and return the table names."""
    target = bind if bind is not None else default_engine
    Base.metadata.create_all(bind=target)
    tables = sorted(inspect(target).get_table_names())
    logger.info("Database initialised with %d table(s)", len(tables))
    return tables

def main() -> None:
    """Command-line entry point that initialises the configured database."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    tables = init_db()
    print(f"Database initialised at {get_settings().resolved_database_url}")
    print(f"Tables ({len(tables)}): {', '.join(tables)}")

if __name__ == "__main__":
    main()
