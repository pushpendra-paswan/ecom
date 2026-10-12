from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# The engine manages the connections to Postgres
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# Each request gets its own session from this factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    # All models will inherit from this class (starting in M1)
    pass


def get_db():
    # Open a session for one request and always close it afterwards
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
