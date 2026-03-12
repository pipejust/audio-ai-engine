from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.session import Base

class TrainingSource(Base):
    __tablename__ = "training_sources"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(String, index=True)
    source_type = Column(String)
    source_name = Column(String)
    status = Column(String, default="indexed")
    file_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
