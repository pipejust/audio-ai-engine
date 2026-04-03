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

class SmtpSettings(Base):
    __tablename__ = "smtp_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(String, unique=True, index=True, nullable=False)
    smtp_host = Column(String, nullable=False, default="smtp.resend.com")
    smtp_port = Column(Integer, nullable=False, default=465)
    smtp_user = Column(String, nullable=False, default="resend")
    smtp_pass = Column(String, nullable=False)
    from_email = Column(String, nullable=False)
    bcc_email = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, default="Plantilla Cotización")
    project_id = Column(String, unique=True, index=True, nullable=False)
    
    # JSON String para guardar la familia tipográfica y los tres colores (textColor, headingColor, etc.)
    style_config = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class VoiceSettings(Base):
    __tablename__ = "voice_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(String, unique=True, index=True, nullable=False)
    voice_id = Column(String, nullable=False, default="alloy")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(String, index=True, nullable=False, default="buscofacil")
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(String, index=True, nullable=False, default="buscofacil")
    lead_id = Column(Integer, index=True, nullable=False) # Relates to Lead.id
    property_id = Column(String, index=True, nullable=False)
    agent_id_user = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    agent_email = Column(String, index=True, nullable=True)
    agent_phone = Column(String, nullable=True)
    appointment_date = Column(String, nullable=True) # E.g., ISO date string
    status = Column(String, default="pending") 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
