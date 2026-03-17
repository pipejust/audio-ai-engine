# Guía de Integración Frontend para el Backend de Voz (MoshWasi)

Este documento define todos los pasos necesarios y requerimientos técnicos para integrar un frontend de terceros o aplicación móvil con el motor central de procesamiento de Voz alojado en Render (`moshwasi-audio-api.onrender.com`).

La arquitectura agnóstica de render permite construir constructores visuales (como la Esfera Activa) en cualquier entorno tecnológico (React, Vue, Vanilla JS, UIKit nativo) que envíen audio y reaccionen a los eventos de la Inteligencia Artificial simulando una voz natural Full Duplex (bi-direccional).

---

## 1. Handshake y Conexión (WebSockets)

Toda la comunicación ocurre a través de un único canal de WebSocket persistente (No REST), logrando latencia cercana a cero.

*   **URL Base de Producción:** `wss://moshwasi-audio-api.onrender.com/voice/stream`
*   **Parámetros GET obligatorios:**
    *   `project_id`: Identificador del proyecto al que se asocian las reglas y base de conocimiento (`xkape`, `buscofacil`, o dinámico).

**Ejemplo de conexión Inicial (Vanilla JS):**
```javascript
const ws = new WebSocket('wss://moshwasi-audio-api.onrender.com/voice/stream?project_id=xkape');

ws.onopen = () => {
    console.log("Conectado al motor de voz IA");
    // Aviso Visual Opcional. La IA saludará y enviará su evento instantes después del ONOPEN.
};
```

---

## 2. Envío del Audio del Usuario (Flujo de Entrada / Micrófono)

El Frontend debe capturar el micrófono, empaquetarlo en archivos `.webm` (WebM) y mandarlo por el canal de WebSocket como Blob.

*   **Cuándo enviar el Blob (VAD - *Voice Activity Detection*):** 
    No se envía un stream crudo por microsegundos. El cliente debe aplicar un algoritmo en cliente que mida silencios (ej. un `AnalyserNode` de la WebAudio API mapeando los decibelios).
    Te quedas grabando mientras el usuario hable. Si hay más de **1.2 segundos** continuos de silencio (con db por debajo de 40), detienes el micro (`mediaRecorder.stop()`), recuperas el binario final generado y envías ese compendio binario íntegro a través del socket: `ws.send(blob)`.
*   **Aviso Lógico:** Al enviar este archivo, la UI debe cambiar a **"Pensando"** (`.thinking`).

---

## 3. Recepción de Respuesta IA (Flujo de Salida / Audio de la Máquina)

La IA envía su respuesta en voz no como un archivo entero, sino en ráfagas de audio (milisegundos) generadas en el transcurso ("Streaming").

*   **Tipología de Payload:** Entrará por el WebSocket como datos Binarios/Buffer (`event.data instanceof Blob` en JS).
*   **Formato de Descompresión:** El Backend emite audio PCM Crudo (Pulse-code modulation), **16-bit a 24000 Hz, un solo canal (Mono)** (Little Endian).
*   **Lógica de Reproducción (`Web Audio API`):**
    1. Interceptar el binario y transcodificar los Integers a Floats (`valor / 32768`).
    2. Crear un buffer estricto con `sampleRate = 24000`.
    3. Construir `AudioBufferSourceNode` en el API.
    4. Cear un "Chain de Reproducción" (Variable `nextPlayTime`): La IA los manda tan rápido que no puedes solaparlos. Debes decirle al source que arranque en el timestamp que termine el anterior, por ejemplo:
    `source.start(nextPlayTime); nextPlayTime += buffer.duration;`

---

## 4. Estructura de Eventos Control (JSON Protocol)

Cuando el WebSocket recibe **texto nativo** y no un binario, está intercambiando eventos JSON ("Status") generados desde el backend para comandar los cambios de colores, transcripciones, y las directivas lógicas (como finalizar o cancelar el hilo).

### Señales del Servidor -> Cliente (Frontend reacciona):

1.  `{ "status": "reasoning" }`: 
    *   La IA comenzó a analizar el request y se despertó el LLM interno. La interfaz salta a color Naranja (Carga).
    *   **CASO DE CORTE (BARGE-IN REAL):** Si el navegador seguía reproduciendo los últimos buffers de PCM de la respuesta pasada y recibes un "reasoning", indica que *el usuario recién interrumpió la llamada con su voz*. En fracción de segundo **debes silenciar localmente y destruir todos los Buffers sobrantes** del frontend, simulando interrupción nativa humana.
2.  `{ "transcription": "Hola me interesa una casa" }`:
    *   Reflejo directo del Speech-to-Text de Whisper. Para añadir esta burbuja en la ventana tipo WhatsApp (Texto Usuario).
3.  `{ "status": "listening_delta", "delta": "Claro qu..." }`:
    *   Se recibe cada 10ms mientras se genera el texto y el audio al mismo tiempo. Debe "tipearse" dinámicamente en la caja de transcripciones del usuario (Texto IA).
4.  `{ "response": "Claro que sí, me encantaría buscar tu casita." }`:
    *   Respuesta de la IA finalizada.
5.  `{ "status": "listening" }`:
    *   El motor finalizó de emitir los binarios y el backend está listo. Frontend lo atrapa, prende la UI con la luz Azul y texto indicador en pantalla: `"Te escucho..."`.
6.  `{ "status": "end_call" }`:
    *   El Toolchain decidió cortar debido a una despedida cordial o petición del usuario.
    *   Ejecuta las rutinas destructivas de UI de este evento: `ws.close()`, `audioContext.close()`, y resetear a desconectado.

### Señales del Cliente -> Servidor (Comandar el Backend):

1.  `{ "type": "interruption" }`: 
    *   Si tu VAD (detector de volumen) del frontend identifica voz altísima repitiéndose en tu micrófono... y **JUSTAMENTE** de fondo la luz es verde (y la IA estaba hablando), quiere decir que el Humano está intentando interrumpir.
    *   Lanza de ti para servidor un json exacto: `ws.send(JSON.stringify({ type: "interruption" }))`. 
    *   El servidor Render atajará la trama y de inmediato cancelará la generación futura de respuestas hacia OpenAI.

---

## 5. Kit de Componentes Frontend UI (Clases y Estructuras)

Para reproducir la exactitud, paleta de colores corporativa y transiciones visuales de la aplicación matriz. Aplica las siguientes capas en el `class=` al orbe o render reactivo durante el onMessage del JSON WebSocket:

### Marcado HTML Básico Ideal
```html
<div class="orb-container" id="orb-btn">
    <!-- El Id Orb es el motor de colores reactivos -->
    <div class="orb listening" id="orb">
        <svg id="mic-icon" ... > <!-- Micrófono Blanco --> </svg>
    </div>
</div>

<!-- Ventana Consola (Transcripción) -->
<div class="transcription-box" id="t-box">
    <div id="transcript-content">
        <div class="text-user">Usuario: xxxx </div>
        <div class="text-ai">IA: yyyyy </div>
    </div>
</div>
```

### Animaciones de la Esfera (CSS Base 1:1)
```css
/* Base de la Burbuja (Desconectado/Apagado) */
.orb {
    width: 120px; height: 120px; border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, #475569, #1e293b);
    transition: all 0.5s ease;
}

/* 1. Actividad Mínima (Azul) - El mic está libre para que el usuario hable */
.orb.listening {
    background: radial-gradient(circle at 30% 30%, #60a5fa, #2563eb);
    box-shadow: 0 0 30px rgba(59,130,246,0.6);
    animation: pulse-listen 1.5s infinite alternate;
}

/* 2. Análisis del Modelo (Naranja) - Calculando respuesta lógica LLM */
.orb.thinking {
    background: radial-gradient(circle at 30% 30%, #fbbf24, #d97706);
    box-shadow: 0 0 30px rgba(245,158,11,0.6);
    animation: spin 2s linear infinite;
}

/* 3. Audio de Retorno Emitiendo (Verde Esmeralda) - Se ejecuta mientras los buffers son consumidos */
.orb.speaking {
    background: radial-gradient(circle at 30% 30%, #34d399, #059669);
    box-shadow: 0 0 40px rgba(16,185,129,0.8);
    animation: pulse-speak 0.8s infinite alternate;
}

/* Animaciones del Box-Shadow */
@keyframes pulse-listen {
    from { transform: scale(1); box-shadow: 0 0 20px rgba(59,130,246,0.4); }
    to { transform: scale(1.05); box-shadow: 0 0 40px rgba(59,130,246,0.8); }
}

@keyframes spin {
    /* Simulador de engranajes pensando, usar rotaciones en SVGs internos o gradientes */
    100% { transform: rotate(360deg); }
}
```
