"""SQLAlchemy declarative base shared by every ORM table in `app.persistence.db`.

One `MetaData` instance, one naming convention, for the whole database
schema -- this is what makes Alembic's autogenerate produce deterministic,
reviewable constraint/index names (`ck_...`, `fk_...`, `uq_...`, `ix_...`)
instead of the driver-assigned defaults, which differ run to run and are
useless in a migration diff.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Recommended by SQLAlchemy's own documentation for exactly this reason:
# https://docs.sqlalchemy.org/en/20/core/constraints.html#configuring-a-naming-convention-for-a-metadata-collection
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every table in `app.persistence.db.tables`.

    `Base.metadata` is the single source of truth Alembic's `env.py`
    targets for autogenerate -- see `migrations/env.py`.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
