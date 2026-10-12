from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# A single SQL statement may run for 15 seconds at most (this includes waiting for a row lock),
# so a stuck query can never hold a connection forever
STATEMENT_TIMEOUT_MS = 15000

# The engine manages the connections to Postgres. pool_pre_ping checks that a pooled connection
# still works before it is used. hide_parameters keeps the values of a failed statement (which can hold a
# password hash or an email) out of error messages and logs.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    hide_parameters=True,
    connect_args={"options": "-c statement_timeout=" + str(STATEMENT_TIMEOUT_MS)},
)

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
