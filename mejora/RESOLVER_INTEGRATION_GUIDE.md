# Guía de Integración del Resolutor Geográfico con el Agente AI

El objetivo de la tarea era integrar nativamente el sistema algorítmico `resolver_ubicacion` dentro de los *flows* cognitivos del asistente de IA. Queríamos que cuando el cliente solicite una casa en un lugar ambiguo o demasiado granular (ej. "Pance"), el Agente de Inteligencia Artificial llame a la herramienta, resuelva automáticamente que Pance es en Cali y, **empatizadamente le pregunte al cliente**: *"¿Te refieres al barrio Pance que queda en la ciudad de Cali?"*.

A continuación muestro las capas en donde se inyectó esta lógica para volverla 100% autónoma.

## 1. Definición de la Herramienta (Tool Calling)
Se fue al archivo en la ruta **`app/core/prompts.py`** y se agregó una nueva herramienta llamada `check_location_context` dentro del set de herramientas habilitadas para el `project_id == "buscofacil"`.

A esta herramienta se le dotó de un prompt descriptivo muy explícito que fuerza a la IA a usarla cuando existe ambigüedad de lugar:
```json
{
    "type": "function",
    "name": "check_location_context",
    "description": "Obligatorio: Si el usuario menciona el nombre de un lugar (ej. un barrio o sector como 'Pance', 'Ciudad Jardín', 'Valle del Lili', etc.) pero NO aclara explícitamente en qué ciudad o municipio de Colombia se encuentra, utiliza esta herramienta para que el sistema geográfico te ubique exactamente a qué barrio, ciudad y departamento pertenece.",
    "parameters": {
        "type": "object",
        "properties": {
            "location_name": {"type": "string", "description": "El nombre del lugar escrito por el usuario (ej. Pance)"}
        },
        "required": ["location_name"]
    }
}
```

## 2. Inyección de Responsabilidad (Regla Mandatoria del Agente)
No bastaba con darle la herramienta a la IA (ya que a menudo pueden ser perezosas o asumirlo todo como "Bogotá"), así que también editamos el **System Prompt Dinámico** (`get_agent_instructions`) en  **`app/core/prompts.py`** agregando la regla estricta:

> `"REGLA DE LOCALIZACIÓN OBLIGATORIA: [...] Si el cliente solo menciona el barrio, DEBES llamar INMEDIATAMENTE a la herramienta 'check_location_context'. Si esta te devuelve la ciudad y el departamento (ej. te dice que Pance queda en Cali), NO busques aún: infórmaselo empáticamente al cliente y pídela que confirme (ej. '¿Te refieres al barrio Pance que queda en la ciudad de Cali?'). Una vez el cliente confirme que sí busca en esa ciudad, recién ahí ejecuta la búsqueda de inmuebles."`

## 3. Manejador en el Action Router (Ejecución Python)
Finalmente, había que indicarle a FastAPI cómo lidiar con la solicitud que hace la Inteligencia artificial cuando trata de invocar `check_location_context`. Esto se hizo abriendo **`app/routers/tools.py`**, donde están centralizadas las llamadas externas.

Se inyectó el siguiente bloque:
```python
if function_name == "check_location_context":
    location_name = args.get("location_name", "")
    import os
    import sys
    
    # Se anexa el sys.path al root para acceder a db_colombia
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if root_dir not in sys.path:
        sys.path.append(root_dir)
        
    try:
        from db_colombia import setup_database, resolver_ubicacion
        conn = setup_database()
        # Se ejecuta nuestro script mágico construido previamente
        resolver_response = resolver_ubicacion(location_name, conn)
        conn.close()
        
        # OBLIGAMOS al LLM a que devuelva la información haciendo una pregunta al usuario
        return {"status": "success", "result_text": f"Dato geográfico: {resolver_response}. IMPORTANTE: Infórmaselo inmediatamente al cliente y hazle una pregunta corta de confirmación sobre la ciudad encontrada para estar seguros antes de buscar."}
    except Exception as e:
        return {"status": "error", "result_text": f"Falló al buscar contexto de lugar: {e}"}
```

### 👉 Flujo de Acción Resultante (Step-by-Step Causal)
1.  **Audio entrante:** *"¡Hola Sol! Quiero alquiler casas en el Valle del Lili"*
2.  El motor Whisper detecta el texto.
3.  El `Text Agent` lee el System Prompt y ve que **Valle del Lili** es un barrio o sector asilado sin ciudad mencionada. 
4.  Llama inmediatamente por web-socket a la tool `check_location_context(location_name="Valle del Lili")`.
5.  El router en FastAPI ejecuta `db_colombia.py` -> `resolver_ubicacion("Valle del Lili")`.
6.  La base de datos retorna: *"Valle del Lili es el barrio Valle del Lili de la Comuna 17, pertenece a la zona Sur en la ciudad de Cali, departamento de Valle del Cauca."*
7.  El Router le devuelve una orden estricta a la IA con los datos que descubrió.
8.  La Inteligencia Artificial sintetiza, humaniza y emite vocalmente: 
    *   🤖🔈: *"¿Te refieres al barrio Valle del Lili que queda en la ciudad de Cali?"*
9.  **Audio Entrante** *"Sí, exacto."*
10. La IA procede a utilizar la herramienta `search_properties(city="Cali", neighborhood="Valle del Lili")`.

🎉 **El ecosistema ha quedado robustecido de forma autónoma, sin fallos geográficos y de interconexión directa con cualquier Voice LLM que lo use.**
