# 📋 Requerimientos y Ajustes para el equipo de Frontend (MVP Busco Fácil)

Este documento centraliza todas las tareas, ajustes de UI/UX y necesidades de integración que debe aplicar el equipo de Frontend, basadas en la *"Revisión MVP Marzo 31"* y los recientes cambios implementados en el Backend.

---

## 🎨 1. Ajustes de UI y Experiencia de Usuario (UX)

### 1.1 Corrección de Responsive Mobile (Prioridad Alta)
- **Problema:** Hay textos desbordados en las pantallas móviles y los bloques no se adaptan de forma fluida.
- **Acción requerida:** 
  - Ajustar el padding, margins y tamaños de fuente (`font-size`) en las vistas principales.
  - Validar los quiebres de pantalla (breakpoints) para asegurar que la interfaz se percibe profesional en cualquier dispositivo.

### 1.2 Mejorar impacto del primer pantallazo (Home)
- **Problema:** El *Home* actual funciona pero falta que genere un mayor impacto emocional en el cliente.
- **Acción requerida:** 
  - Modificar el "Copy" o texto de bienvenida. 
  - **Texto sugerido:** *"Busco Fácil busca, valida y agenda por ti... y puedes recibir dinero al comprar"*.
  - Añadir diseño que acompañe este mensaje para denotar un servicio premium y diferenciador.

### 1.3 Eliminar superposición de la IA vs Formularios
- **Problema:** La esfera o chat de IA tapa parcialmente los formularios que el usuario debe leer/llenar.
- **Acción requerida:** 
  - Ocultar, desplazar o minimizar la IA automáticamente en cuanto se abra la capa de formularios.
  - Opcional: Modificar el `z-index` para asegurar que las modales queden siempre por encima y bloqueen la interacción con la esfera si es necesario (sin cortar la llamada de audio base).

---

## ⚙️ 2. Flujo de Registro y Retención

### 2.1 Formulario de Registro Optimizado
- **Problema:** Se requiere un enfoque claro y con mínima fricción para que el usuario sienta valor y seguridad, no repulsión.
- **Acción requerida:**
  - El formulario de registro solo debe exigir tres campos estrictos: **Nombre**, **Email**, y **Celular**.
  - *(Opcional/A futuro: Preparar un espacio para "Cédula" para validaciones posteriores, pero por el momento mantenerlo oculto o inactivo)*.

### 2.2 Advertencia explicita "Antes de pre-agendar"
- **Problema:** Hoy el usuario avanza por el embudo hasta intentar pre-agendar sin que sepa de antemano que para guardar esa cita requiere registrarse.
- **Acción requerida:** 
  - Mostrar un aviso claro e ineludible un paso "antes" del paso definitivo o cuando envíen el formulario/petición de citas.
  - **Texto sugerido:** *"Para agendar esta visita necesitas registrarte en menos de 30 segundos"*.

### 2.3 Persistencia de Búsqueda tras el registro
- **Problema:** Al registrarse o iniciar sesión, la página recarga o rompe el flujo, haciendo que el usuario pierda toda la información de búsqueda que traía con la IA.
- **Acción requerida:** 
  - Implementar el guardado del estado actual de los inmuebles vistos o parámetros de búsqueda usando `localStorage` o `sessionStorage`.
  - Cuando se complete el registro, la interfaz debe regresar o re-renderizar la vista exactamente donde el cliente se quedó, para continuar hacia la confirmación de las citas en 1 clic.

### 2.4 Claridad de Promesa ("Mensaje final de pre-agendamiento")
- **Problema:** Falsas expectativas en usuarios que creen que la cita es absoluta.
- **Acción requerida:** 
  - Hacer mucho más visible y claro el mensaje final.
  - **Texto sugerido:** *"Tu cita debe ser confirmada por el responsable del inmueble"*.

---

## 🔌 3. Integración con el nuevo Backend

El backend ya está listo para capturar a los usuarios (`Leads`), guardar sus inmuebles seleccionados (`Appointments`) y disparar el Workflow automatizado de Notificaciones por Email tanto al usuario como al agente interno de Busco Fácil.

Para que esto funcione el Frontend debe:

1. **Pasar la Metadata del Cliente en todo momento**.
   - Si se usa WebSocket (`/voice/stream`): Asegurarse de adjuntar los *Query Params* con la información de sesión actual cada vez que inicie:
     `ws://.../voice/stream?project_id=buscofacil&clientName=Juan&clientEmail=juan@mail.com&clientPhone=300123`
   - Si se usa HTTP Text (Endpoint `/chat`): Mandar los campos `client_name`, `client_email` y `client_phone` junto con el `query`.

2. **Detección de evento "action: open_login"**.
   - Si la IA de voz detecta que el usuario no ha dado su email o no está autenticado vía frontend (si detecta email vacío), la IA disparará un JSON indicando `'action': 'open_login'`. 
   - El Front debe escuchar (parser) este evento en el socket y, en lugar de imprimir un texto, abrir visualmente el componente `Modal de Login/Registro` del punto 2.1 e impedir que el flujo continúe hasta que pasen el email.

---
*Documento generado a partir de la revisión de requerimientos de PM. Las subidas a GitHub o a Vercel/Render deben pausarse hasta que la integración Backend y Frontend esté unificada localmente.*
