# Guía de Inicio: MoshWasi AI Audio Project

¡Hola Agente (Cline, Claude Code, Cursor)! 
Estás en la raíz del proyecto **MoshWasi AI**. Este proyecto combina un modelo de Inteligencia Artificial Full Duplex de Audio (Moshi) y un buscador semántico con la API Inmobiliaria Wasi.

## Tu objetivo:
Actuar como Tech Lead y ejecutar las Etapas de la `Ruta completa` paso a paso.

## Contexto Inicial:
Para comenzar, lee la visión general y el roadmap arquitectónico del proyecto para que tengas todo el panorama:
1. `roadmap_basico.md` -> Aquí están detalladas las piezas y etapas. **Léelo antes de empezar a programar.**
2. `roadmap_interactivo.html` -> Versión visual UI/UX interactiva (puedes ignorarla si trabajas en consola).

## Prioridad Inmediata (Tu primer paso):
**Ejecutar las Etapas 1 y 2 del Roadmap:**
- Etapa 1: Preparar la infraestructura base del backend en Python. (Crea archivos `requirements.txt`, configura tu entorno virtual `venv` local en la carpeta `backend/`).
- Etapa 2: Crear el "Inventory Service" o la "Data Layer" que se debe conectar con la API de Wasi. Para esto necesitarás requerirle al usuario (Felipe) que te proporcione sus credenciales de Wasi (Token de Wasi y Company ID).
- Crea un `README.md` detallado de cómo levantar el servidor luego de hacer el setup de Python.
- Prepara los scripts para normalizar propiedades en una Base de Datos SQLite (para empezar).

## Reglas importantes:
- **No generes todo el código de golpe.** Ve paso a paso.
- Usa `sqlite3` u otra base simple al inicio para la base de datos de "Data Layer".
- Siempre que te falten llaves/APIKeys o tengas dudas de negocio, pausa y pídeselas explícitamente al usuario.
- Aprovecha los servidores MCP que ya están instalados globalmente en la máquina del usuario si necesitas consultar a Vercel, Supabase, Test Sprite, GitHub o realizar busquedas (`npx mcp-handler`, `npx @modelcontextprotocol/server-github`, etc.).

¡Inicia leyendo el `roadmap_basico.md`!
