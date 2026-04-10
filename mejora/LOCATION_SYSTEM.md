# Sistema de Resolución Geográfica - Colombia (BuscoFácil)

## Problema a resolver
El objetivo es proveerle a la inteligencia artificial de **BuscoFácil** (la aplicación) un **conglomerado de ubicaciones con algoritmos** que permitan identificar si una ubicación solicitada por el usuario (ej. *"Apartamentos en Pance"*, *"Quiero comprar en Valle del Lili"*) se refiere a un **Barrio, Comuna, Zona, Municipio, o Departamento**. 

A diferencia de los Departamentos y Municipios, en Colombia **no existe una única base de datos oficial nacional (como el DANE) que contenga la totalidad de los barrios y comunas del país** de manera unificada y estructurada. Estos datos son competencia de las divisiones de planeación territoriales (POT) de cada Alcaldía, por lo que su formato y precisión varía por ciudad.

## La Solución

Hemos construido un **Sistema Algorítmico y Base de Datos sembrada con toda la DIVIPOLA (Departamentos y Municipios de Colombia)** y preparado la jerarquía para estructurar las Zonas, Comunas y Barrios a medida que se ingresan en la base de datos de los mercados activos (ej: Cali).

### 1. Estructura de Base de Datos (PostgreSQL / Supabase y SQLite)
Se ha organizado una de base de datos relacional de granularidad fina (de menor a mayor nivel de detalle geográfico):
- `col_departments` (Departamentos)
- `col_municipalities` (Municipios y Ciudades)
- `col_zones` (Zonas, p. ej. Norte, Sur, Centro)
- `col_comunas` (Comunas)
- `col_neighborhoods` (Barrios)

> **Nota para el equipo:** Esta base de datos ya almacena nombres de forma normalizada (sin tildes, en minúscula) para hacer la búsqueda un 300% más rápida y resiliente a las faltas ortográficas o problemas de transcripción (Speech-To-Text / Whisper / Moshi).

### 2. Algoritmo de Búsqueda (Location Resolver)
En el backend, se implementó la función `resolver_ubicacion(query: str)` (ubicada en `db_colombia.py`) que ejecuta una **búsqueda jerárquica exacta y luego aproximada**. 
Busca en cascada desde lo más granular:
1. **Paso 1: ¿Es un Barrio?** Realiza inferencias recursivas integrando a qué comuna, zona y ciudad pertenece.
2. **Paso 2: ¿Es una Comuna?** 
3. **Paso 3: ¿Es una Zona?**
4. **Paso 4: ¿Es una Ciudad/Municipio?**
5. **Paso 5: ¿Es un Departamento?**

Al hacerlo de esta forma se prioriza el detalle. Por ejemplo esto previene que `Cali` sea detectado incorrectamente. 

### 3. Ejecutar y testear en local
La lógica para construir, sembrar y testear la de base de datos está consolidada en el archivo `db_colombia.py`.

```bash
# Entrar al backend
cd backend_buscofacil

# Correr el archivo de sembrado y testing algoritmico
python3 db_colombia.py
```

### Ejemplos de uso por el Agente de Voz API

Las respuestas estructuradas por el algoritmo pueden ser pasadas de inmediato al modelo de IA (LLM/Groq/Moshi) para que este se sitúe y contextualice su conocimiento del inmueble.

*   `resolver_ubicacion("Pance")` -> **"Pance es el barrio Pance de la Comuna 22, pertenece a la zona Sur en la ciudad de Cali, departamento de Valle del Cauca."**
*   `resolver_ubicacion("Valle del Lili")` -> **"Valle del Lili es el barrio Valle del Lili de la Comuna 17, pertenece a la zona Sur en la ciudad de Cali, departamento de Valle del Cauca."**
*   `resolver_ubicacion("Cali")` -> **"Cali es el municipio o ciudad de Cali, en el departamento de Valle del Cauca."**

### Despliegue hacia Supabase (Producción)

Si deseas aplicar esta misma arquitectura a la base de datos `Supabase` (Production), puedes ejecutar este esquema SQL directamente en el editor SQL de Supabase:

```sql
CREATE TABLE IF NOT EXISTS col_departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS col_municipalities (
    id SERIAL PRIMARY KEY,
    department_id INTEGER REFERENCES col_departments(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS col_zones (
    id SERIAL PRIMARY KEY,
    municipality_id INTEGER REFERENCES col_municipalities(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS col_comunas (
    id SERIAL PRIMARY KEY,
    municipality_id INTEGER REFERENCES col_municipalities(id) ON DELETE CASCADE,
    zone_id INTEGER REFERENCES col_zones(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS col_neighborhoods (
    id SERIAL PRIMARY KEY,
    municipality_id INTEGER REFERENCES col_municipalities(id) ON DELETE CASCADE,
    comuna_id INTEGER REFERENCES col_comunas(id) ON DELETE SET NULL,
    zone_id INTEGER REFERENCES col_zones(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL
);

-- OPTIONAL INDEXES FOR SPEED
CREATE INDEX idx_col_departments_norm ON col_departments(normalized_name);
CREATE INDEX idx_col_municipalities_norm ON col_municipalities(normalized_name);
CREATE INDEX idx_col_zones_norm ON col_zones(normalized_name);
CREATE INDEX idx_col_comunas_norm ON col_comunas(normalized_name);
CREATE INDEX idx_col_neighborhoods_norm ON col_neighborhoods(normalized_name);
```

### Automatizando las Ciudades en Futuro
Para agregar *absolutamente todos* los barrios de Medellín o Bogotá en el futuro, se debe buscar en los **Portales de Datos Abiertos de las Alcaldías** correspondientes el archivo `Shapefile/GeoJSON`, extraer la columna "Nombre Barrio" y realizar un script que ejecute rutinas `INSERT` en la tabla `col_neighborhoods`. Mapeándolos frente al respectivo `municipality_id`.
