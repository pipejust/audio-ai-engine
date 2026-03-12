import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# If the database URL starts with postgres:// (old format), we replace it with postgresql:// for SQLAlchemy
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# We are strictly using Postgres (Supabase) now
engine = create_engine(
    SQLALCHEMY_DATABASE_URL
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
