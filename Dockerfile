FROM python:3.11-slim

# Instalar dependencias del sistema necesarias para compilar paquetes ML (Chroma, etc) y procesar audio
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    sqlite3 \
    libsqlite3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar una versión ligera y CPU-only de PyTorch antes del resto de dependencias
# Esto evita que ChromaDB y SentenceTransformers descarguen la version GPU de +2GB
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Copiar requerimientos e instalar el resto
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
ENV PORT=10000
# Bandera para saber que estamos en Render y no Vercel (ya no usaremos /tmp restringido por defecto)
ENV RENDER=1

# Configurar el PYTHONPATH para que Python y Uvicorn encuentren el módulo 'app' absoluto
ENV PYTHONPATH=/app/backend

# Comando de inicio
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"
