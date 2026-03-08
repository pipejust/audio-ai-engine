# MoshWasi AI Audio Project (Agent-Orchestrated)

Este proyecto implementa un backend de Inteligencia Artificial basado en una arquitectura Multi-Agente. Permite ingesta de múltiples fuentes de datos, búsqueda semántica (RAG), y un motor de audio Full Duplex mediante WebSockets.

## 🚀 Cómo iniciar el servidor

### 1. Preparar el entorno
Asegúrate de tener Python 3.10+ instalado.
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Variables de Entorno
Crea un archivo `.env` en la carpeta backend con tus llaves y el motor de voz deseado:
```bash
GROQ_API_KEY="tu_llave_de_groq_aqui"
ELEVENLABS_API_KEY="tu_llave_de_elevenlabs"
OPENAI_API_KEY="tu_llave_openai_realtime"

# Elige el motor de voz interactivo: GROQ_PIPELINE o OPENAI_REALTIME
VOICE_ENGINE_MODE=OPENAI_REALTIME
```

### 3. Iniciar el Backend
Arranca el servidor FastAPI (Agentes + WebSockets):
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload
```
- El API de texto estará en `http://localhost:8765/chat`
- El API de audio estará en `ws://localhost:8765/voice/stream`

---

## 🎙️ Cómo probar la interfaz de Voz
Hemos provisto un cliente Mock en HTML puro en la raíz del proyecto.
1. Abre el archivo `index.html` en tu navegador (Chrome o Safari).
2. Otorga permisos de micrófono.
3. Haz clic en **Conectar & Hablar**.
4. Habla al micrófono. El audio se enviará interactivamente por WebSockets, el agente de IA decidirá qué responder usando el VectorStore, y mandará el audio de respuesta generado por el TTS simulado de vuelta.
