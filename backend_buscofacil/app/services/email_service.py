import smtplib
from email.message import EmailMessage
from app.db.session import SessionLocal
from app.db.models import SmtpSettings
import logging

logger = logging.getLogger(__name__)

def send_appointment_emails(project_id: str, client_name: str, client_email: str, client_phone: str, appointments: list):
    """
    Función síncrona para enviar emails de notificación de citas.
    Debe ser ejecutada en un background task (thread).
    """
    db = SessionLocal()
    try:
        # Obtenemos configuración SMTP por tenant
        smtp_config = db.query(SmtpSettings).filter(SmtpSettings.project_id == project_id).first()
        
        # Si no hay configuración para BuscoFacil, usamos un fallback dummy
        if not smtp_config:
            logger.error(f"No SMTP settings found for project {project_id}.")
            return

        smtp_host = smtp_config.smtp_host
        smtp_port = smtp_config.smtp_port
        smtp_user = smtp_config.smtp_user
        smtp_pass = smtp_config.smtp_pass
        from_email = smtp_config.from_email
        internal_bcc = smtp_config.bcc_email or "admin@buscofacil.com"

        # Conectar con el servidor SMTP
        with smtplib.SMTP_SSL(smtp_host, smtp_port) if smtp_port == 465 else smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_port != 465:
                server.starttls()
            
            server.login(smtp_user, smtp_pass)

            # Notificación 1: Al Usuario / Cliente
            msg_user = EmailMessage()
            msg_user["Subject"] = "Tus Citas Pre-Agendadas - Busco Fácil"
            msg_user["From"] = from_email
            msg_user["To"] = client_email
            
            body_user = f"Hola {client_name},\n\nHemos registrado exitosamente tu solicitud de pre-agendamiento para las siguientes propiedades:\n\n"
            for appt in appointments:
                body_user += f"- Propiedad ID: {appt}\n"
            
            body_user += "\nRecuerda: Tu cita aún debe ser confirmada por el responsable del inmueble. Te contactaremos pronto.\n\nEl equipo de Busco Fácil"
            msg_user.set_content(body_user)
            
            # Notificación 2 e Inteerna: Al Contacto / Interno (Para simplificar, mandamos un solo email a internal_bcc)
            msg_internal = EmailMessage()
            msg_internal["Subject"] = f"Nueva Solicitud de Cita - {client_name}"
            msg_internal["From"] = from_email
            msg_internal["To"] = internal_bcc
            
            body_internal = f"El usuario {client_name} ({client_email} / Cel: {client_phone}) ha solicitado agendar citas para:\n\n"
            for appt in appointments:
                body_internal += f"- Propiedad ID: {appt}\n"
            
            body_internal += "\nPor favor revisa el panel de Busco Fácil para coordinar con los asesores correspondientes."
            msg_internal.set_content(body_internal)
            
            server.send_message(msg_user)
            server.send_message(msg_internal)
            
            logger.info(f"Correos de agendamiento enviados para el lead {client_email}")

    except Exception as e:
        logger.error(f"Error enviando correos de agendamiento: {e}")
    finally:
        db.close()
