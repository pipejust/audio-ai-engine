from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.core import security

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Mock database de usuarios por tenant
# En produccion esto iría a la tabla Users de SQL/Postgres.
FAKE_USERS_DB = {
    "admin_buscofacil": {
        "username": "admin_buscofacil",
        "full_name": "Agente Venta Wasi",
        "email": "wasi@buscofacil.com",
        # Contraseña en texto plano para testing rapido de login (pass: secreto123)
        "hashed_password": security.get_password_hash("secreto123"), 
        "project_id": "buscofacil"
    },
    "admin_xkape": {
        "username": "admin_xkape",
        "full_name": "Agente Cotizador",
        "email": "cotiza@xkape.com",
        "hashed_password": security.get_password_hash("secreto123"),
        "project_id": "xkape"
    }
}

@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user_dict = FAKE_USERS_DB.get(form_data.username)
    if not user_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not security.verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    access_token = security.create_access_token(
        data={
            "sub": user_dict["username"],
            "project_id": user_dict["project_id"]
        },
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "project_id": user_dict["project_id"],
        "user": user_dict["full_name"]
    }
