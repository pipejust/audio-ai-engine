# Ruta completa, paso a paso, para implementar Moshi full duplex + búsqueda semántica en Wasi (texto y voz)

Voy a describirte todo en etapas, con tareas súper claras, sin código. La idea es que tu equipo escriba el código con Claude, pero que tú tengas la receta completa de qué hacer y en qué orden.

**Fuentes clave (para que abras y confirmes instalación y capacidades):**
- Moshi (repo oficial)
- Moshi fine-tune (LoRA) repo oficial
- Documentación Moshi en Transformers (explica el modelo “dos streams” y cómo se usa)
- Wasi API: getting started (tokens) y propiedades/campos

---

## Etapa 0. Qué vas a construir exactamente (para no perderte)

Vas a construir 3 piezas:

**Pieza A. Backend “Data Layer” (solo lectura)**
- Conecta Wasi y otras APIs de inmuebles
- Normaliza los datos a un esquema interno
- Expone endpoints internos en tu backend (por ejemplo, `/properties/search`, `/properties/{id}`)

**Pieza B. Motor semántico (texto)**
- Recibe texto del usuario (NLP)
- Entiende intención y filtros (habitaciones, baños, zona, precio, etc.)
- Llama a la Data Layer para traer resultados
- Responde con grounding (basado en datos reales, cero inventos)
- Calcula afinidad (qué tan bien cumple cada inmueble)

**Pieza C. Motor de voz full duplex (Moshi)**
- Escucha audio y habla al mismo tiempo (full duplex)
- Mientras el usuario habla, el sistema puede interrumpir, confirmar, y seguir conversando
- Cuando detecta intención de búsqueda, llama a la Pieza B (semántica) y responde con voz

**Importante sobre “entrenar el modelo con los datos de Wasi”**
No se recomienda “re-entrenar un LLM” cada vez que cambia una casa o un precio. Lo correcto es actualizar el índice/datos y consultar en tiempo real.
Lo que sí puedes entrenar periódicamente (y tiene sentido) es:
1. el modelo que convierte lenguaje natural a filtros estructurados (slot filling)
2. un reranker para mejorar el orden de resultados
3. ajustes LoRA del comportamiento del agente (tono, estilo, consistencia de extracción)
Esto te da robustez sin “romper” el sistema cada vez que cambia el inventario.

---

## Etapa 1. Infraestructura local (o nube) lista para voz full duplex

**Objetivo:** Tener un servidor donde Moshi pueda correr estable con baja latencia, y un backend Python con WebSockets para streaming.

**1.1 Decide dónde corre Moshi**
- **Opción 1: Máquina local con GPU (recomendado para duplex)**. Ventaja: latencia baja, costo controlado. Requisito: GPU NVIDIA moderna, drivers y CUDA listos.
- **Opción 2: Nube con GPU (si necesitas escalabilidad o no tienes GPU)**. Ventaja: escalas por demanda. Requisito: instancia con GPU y buen audio streaming hacia clientes (latencia y jitter controlados).

**1.2 Requisitos mínimos prácticos**
- Linux Ubuntu 22.04 o similar (recomendado para GPU)
- Python moderno
- PyTorch con soporte GPU (si vas con NVIDIA)
- Red estable (para duplex la red importa mucho)

**1.3 Repositorios y credenciales**
- Acceso a Wasi requiere token e `id_company` (Wasi indica cómo obtenerlos).
- Define un “secrets manager” sencillo (env vars en dev, vault/parameter store en prod).

**Entregable de esta etapa:** Un servidor con Docker instalado, Python instalado, GPU usable (si aplica), Puertos definidos para API HTTP y WebSocket.

---

## Etapa 2. Preparar Wasi “solo lectura” y normalización (tu base de datos viva)

**Objetivo:** Poder leer “todo el inventario” y consultarlo por filtros sin que el motor de IA toque JSON crudo.

**2.1 Confirmar credenciales y primer llamado**
- Sigue “Getting started” de Wasi para tokens y ejemplo de llamadas.

**2.2 Identificar endpoints mínimos**
- Listado de propiedades (con paginación)
- Detalle de propiedad
- Ubicaciones (ciudades, barrios, etc.)
- Tipos de propiedad
- Campos completos de propiedad (features, galerías si aplica)

**2.3 Construir un esquema interno (muy importante)**
Define tu “Property” interno con campos limpios:
`id`, `title`, `address`, `city`, `neighborhood`, `for_sale / for_rent`, `price`, `area_m2`, `rooms`, `baths`, `floors`, `parking`, `features`, `description`, `images`, `updated_at`.

**2.4 Conector Wasi y normalizadores**
- **Conector:** maneja retries, backoff, timeouts, paginación, rate limits.
- **Normalizador:** convierte el JSON de Wasi al esquema interno. Guardas los registros normalizados en una DB tuya (Postgres recomendado).

**2.5 Sincronización incremental**
Proceso “SYNC”: cada X minutos trae cambios, hace upsert en DB y registra “qué cambió”.

**Entregable de esta etapa:** Un servicio interno “Inventory Service” que expone: buscar propiedades por filtros estructurados, traer detalle por id, y devolver “conteos” y stats básicos.

---

## Etapa 3. Motor semántico de texto (la versión escrita)

**Objetivo:** Que el usuario escriba “casa 4 habitaciones, 3 baños, grande, Laureles, hasta 450M” y tú respondas con opciones reales, afinidad y explicaciones.

**3.1 Definir “intenciones” (lista cerrada)**
- search_property, get_property_details, compare_properties, refine_search, ask_constraints.

**3.2 Definir “slots” (los filtros)**
- tipo, operación, ciudad, barrio, zona, rango de precio, habitaciones, baños, pisos, mínima área, bosquejos como "grande" o "cerca de...".

**3.3 Construir el parser NL a JSON (sin entrenar al inicio)**
- Entrada: texto libre
- Salida: JSON con intent + filtros + “confidence”

**3.4 Búsqueda y ranking con afinidad**
- Para cada inmueble calculas un score. Si cumple todo 100%, parcialmente 20-60%. Explicas por qué.

**3.5 Respuesta conversacional**
Primero: “Listo, ya lo estoy buscando. Dame 3 segundos.”
Luego: devuelves 3 a 7 opciones y mantienes memoria de contexto.

**Entregable de esta etapa:** Un endpoint /nlq-text (HTTP) que recibe texto y devuelve resultados (lista), afinidad por resultado, explicación y preguntas de seguimiento.

---

## Etapa 4. Instalar y ejecutar Moshi full duplex (local)

**Objetivo:** Tener Moshi corriendo, primero en demo local, luego integrado a tu backend.

**4.1 Leer el repo oficial y confirmar requisitos**
- El repo oficial describe Moshi como speech-text y framework full duplex.

**4.2 Elegir “runtime” Moshi**
- **Ruta A:** ejecutar Moshi desde su repo (más control).
- **Ruta B:** usar Transformers con Moshi (más integración Python estándar - **RECOMENDADA**).

**4.3 Preparar entorno Python**
Crea venv, instala PyTorch para GPU, instala dependencias de Moshi. Verifica audio I/O.

**4.4 Descargar pesos del modelo**
Sigue las referencias de Hugging Face y valida que el modelo cargue sin OOM.

**4.5 Probar “loop duplex” mínimo**
Audio entra -> Moshi responde con audio -> mide latencia. Si no está estable, no avances.

**Entregable de esta etapa:** Moshi funcionando en local como servicio.

---

## Etapa 5. Backend de voz: streaming, turn-taking, interrupciones

**Objetivo:** Que mobile y web envíen audio en streaming a Moshi y reciban audio de respuesta, permitiendo interrumpir natural.

**5.1 Elegir protocolo de audio**
- WebSocket con audio en chunks (PCM 16-bit 16kHz o 24kHz).

**5.2 Construir “Voice Gateway” en Python**
Responsabilidades:
- Recibir audio del cliente, manejar buffering/timestamps, enviarlo a Moshi.
- Recibir audio de respuesta y reenviarlo.
- Implementar **barge-in**: si el usuario habla, cortar el audio de salida.

**5.3 Gestión de sesiones**
Cada usuario tiene `session_id`. Se mantiene el contexto de búsqueda y el historial.

**Entregable de esta etapa:** Endpoint WebSocket `/voice/stream` que hace duplex estable.

---

## Etapa 6. Conectar Moshi con herramientas (tools) para consultar Wasi

**Objetivo:** Que Moshi “pueda buscar” inmuebles en tus datos sin inventar nada.

**6.1 Definir el contrato “tool calling” interno**
- `tool.search_properties(filters)`
- `tool.get_property(id)`
- `tool.refine_search(filters)`

**6.2 Disparadores de tool-calling (Router Semántico Externo recomendado)**
Moshi produce texto interno. Tu backend decide si es una búsqueda, la convierte a JSON y llama al Wasi Inventory Service. Luego reinyecta los resultados como contexto.

**6.3 Respuesta mientras busca (experiencia humana)**
El backend debe responder rápido en voz: “Listo, ya estoy buscando casas con 4 habitaciones...”. Enviar eventos al frontend para renderizar tarjetas (Cards).

**Entregable:** Voice assistant que consulta Wasi y responde con opciones reales.

---

## Etapa 7. Actualización de datos y “re-entrenamiento” correcto

**Objetivo:** Mantener inventario actualizado y mejorar la extracción NLP sin quebrar el modelo de voz.

**7.1 Proceso recomendado**
A) Sync incremental de Wasi (cronjob).
B) Re-index semántico (RAG embeddings).
C) Entrenamiento periódico del parser NL a JSON o reranker.

*Ignorar el fine-tuning masivo de LLMs solo para memorizar inmuebles, eso es una mala práctica.*

---

## Etapa 8. Fine-tuning Moshi (LoRA) para dominio inmobiliario (Opcional)

**Objetivo:** Solo cuando el flujo principal base ya funcione, hacer que el asistente suene más natural en el dominio inmobiliario y sea más estricto con las intenciones.

- Crear dataset de llamadas de ejemplo.
- Seguir las instrucciones del repositorio de `moshi-finetune`.

---

## Etapa 9. Integración con app móvil y web

**Objetivo:** Un solo backend de voz sirviendo a dos clientes (Web Browser y React Native/Mobile).

- Captura de micrófono y streaming al websocket `/voice/stream`.
- Interfaz gráfica mostrando un "Transcript" en tiempo real y UI Cards con los detalles de los inmuebles recibidos.
- Manejo de fallback a texto (`/nlq-text`).

---

## Etapa 10. Producción (Integración con backend original)

**Objetivo:** Ligar el AI Voice Service con la aplicación central y asegurar APIs.

**10.1 Fronteras Claras**
Microservicio aislado `ai-voice-service` (Python/Moshi) para voz y NLP, con tu backend en NJ consumiendo los resultados (UI).

**10.2 Seguridad**
- Auth por JWT en el handshake del websocket.
- Rate limiting.

**10.3 Observabilidad**
- Logs, UUID tracks, métricas de latencia, requests fallidos desde Wasi.

---
*Para iniciar como Tech Lead, enfócate 100% en las Etapas 1 y 2.*
