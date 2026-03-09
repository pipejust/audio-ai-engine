FROM python:3.11-slim

# Instalar dependencias del sistema necesarias para compilar paquetes ML (Chroma, etc)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    sqlite3 \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requerimientos e instalar (esto incluirá dependencias pesadas ML)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY backend/app /app/backend/app
COPY backend/knowledge_registry.db /app/backend/knowledge_registry.db
# Para montar temporales si es necesario
RUN mkdir -p /app/backend/uploads

# Exponer el puerto
EXPOSE 8000

# Variable de entorno de puerto de Render u otro
ENV PORT=8000
# Bandera para saber que estamos en Render y no Vercel (ya no usaremos /tmp restringido por defecto)
ENV RENDER=1

# Comando de inicio
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
