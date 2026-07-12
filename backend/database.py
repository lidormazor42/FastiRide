import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fastiride:fastiride@db:5432/fastiride")

# sqlite:// only used by the test suite — StaticPool keeps a single connection
# alive for the whole process so an in-memory DB doesn't vanish between requests.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
else:
    # pool_pre_ping: transparently replaces pooled connections that RDS (or a
    # network blip) silently dropped — without it, the first request after an
    # idle period 500s on a stale connection.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
