from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,       # base persistent connections (was: 5 default)
    max_overflow=20,    # burst connections on top of pool_size (was: 10 default)
    pool_timeout=30,    # seconds to wait for a connection before raising
    pool_recycle=1800,  # recycle connections after 30 min to avoid stale handles
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    from app.models import job, summary, transaction  # noqa: F401

    Base.metadata.create_all(bind=engine)
