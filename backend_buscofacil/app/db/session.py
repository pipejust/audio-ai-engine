import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# If the database URL starts with postgres:// (old format), we replace it with postgresql:// for SQLAlchemy
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 300}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    # SQLite no requiere pool_recycle de Postgres
    engine_kwargs.pop("pool_recycle", None)
    engine_kwargs.pop("pool_pre_ping", None)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    **engine_kwargs
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
