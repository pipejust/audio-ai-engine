from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import SmtpSettings, Template

router = APIRouter(prefix="/settings", tags=["Settings"])

# Dependencia para obtener la DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class SmtpConfigRequest(BaseModel):
    project_id: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    from_email: str

class SmtpConfigResponse(BaseModel):
    project_id: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    from_email: str
    smtp_pass: str
    
    class Config:
        from_attributes = True

@router.get("/smtp", response_model=SmtpConfigResponse)
def get_smtp_settings(project_id: str, db: Session = Depends(get_db)):
    """Obtiene la configuración SMTP actual de un proyecto"""
    settings = db.query(SmtpSettings).filter(SmtpSettings.project_id == project_id).first()
    if not settings:
        # Devolver valores por defecto vacíos si no existe
        return SmtpConfigResponse(
            project_id=project_id,
            smtp_host="smtp.resend.com",
            smtp_port=465,
            smtp_user="resend",
            from_email="",
            smtp_pass=""
        )
    return settings

@router.post("/smtp", response_model=dict)
def save_smtp_settings(config: SmtpConfigRequest, db: Session = Depends(get_db)):
    """Crea o actualiza la configuración SMTP de un proyecto"""
    settings = db.query(SmtpSettings).filter(SmtpSettings.project_id == config.project_id).first()
    
    if settings:
        settings.smtp_host = config.smtp_host
        settings.smtp_port = config.smtp_port
        settings.smtp_user = config.smtp_user
        settings.smtp_pass = config.smtp_pass
        settings.from_email = config.from_email
    else:
        settings = SmtpSettings(
            project_id=config.project_id,
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_pass=config.smtp_pass,
            from_email=config.from_email
        )
        db.add(settings)
        
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando configuración: {e}")
        
    return {"status": "success", "message": "Configuración SMTP actualizada correctamente."}

class TemplateConfigRequest(BaseModel):
    project_id: str
    title: str = "Plantilla Cotización"
    style_config: str

class TemplateConfigResponse(BaseModel):
    id: int
    project_id: str
    title: str
    style_config: str | None
    
    class Config:
        from_attributes = True

@router.get("/template", response_model=TemplateConfigResponse)
def get_template_settings(project_id: str, db: Session = Depends(get_db)):
    """Obtiene la configuración visual de la plantilla de un proyecto"""
    template = db.query(Template).filter(Template.project_id == project_id).first()
    if not template:
        # Devolver valores por defecto vacíos si no existe
        # Ejemplo: '{"fontFamily": "helvetica", "fontSize": "12", "textColor": "#333333", "headingColor": "#0055ff"}'
        return TemplateConfigResponse(
            id=0,
            project_id=project_id,
            title="Plantilla Cotización",
            style_config="{}"
        )
    return template

@router.post("/template", response_model=dict)
def save_template_settings(config: TemplateConfigRequest, db: Session = Depends(get_db)):
    """Crea o actualiza la configuración visual de la plantilla de un proyecto"""
    template = db.query(Template).filter(Template.project_id == config.project_id).first()
    
    if template:
        template.title = config.title
        template.style_config = config.style_config
    else:
        template = Template(
            project_id=config.project_id,
            title=config.title,
            style_config=config.style_config
        )
        db.add(template)
        
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando plantilla: {e}")
        
    return {"status": "success", "message": "Plantilla visual actualizada correctamente."}
