import urllib.request
import json
import os
from supabase import create_client

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not url or not key:
    print("Error: Se requieren SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en el entorno.")
    exit(1)

supabase = create_client(url, key)

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS colombia_departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS colombia_cities (
    id SERIAL PRIMARY KEY,
    department_id INTEGER REFERENCES colombia_departments(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    UNIQUE(department_id, name)
);

CREATE TABLE IF NOT EXISTS colombia_neighborhoods (
    id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES colombia_cities(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    UNIQUE(city_id, name)
);
"""

# Ejecutar esquema (se requeriría direct postgres connection, pero enviaremos por API si es posible, o dejaremos el SQL para el usuario)

def seed():
    # Descargar JSON oficial de Divipola (Colombia) - GitHub Publico
    json_url = "https://raw.githubusercontent.com/marcovega/colombia-json/master/colombia.json"
    print("Descargando taxonomía de Colombia...")
    response = urllib.request.urlopen(json_url)
    data = json.loads(response.read())
    
    for dep in data:
        dep_name = dep["departamento"].capitalize()
        # Insertar Depto
        res = supabase.table("colombia_departments").insert({"name": dep_name}).execute()
        dep_id = res.data[0]["id"]
        
        ciudades = dep.get("ciudades", [])
        city_payloads = [{"department_id": dep_id, "name": c.capitalize()} for c in ciudades]
        if city_payloads:
            supabase.table("colombia_cities").insert(city_payloads).execute()
            
    print("Base de datos geográfica sembrada con éxito.")

if __name__ == "__main__":
    file_path = "colombia_geography_schema.sql"
    with open(file_path, "w") as f:
        f.write(SQL_SCHEMA)
    print(f"Esquema SQL generado en {file_path}. Ejecútalo en el SQL Editor de Supabase.")
    # seed() # Descomentar para poblar la DB despues de correr el flag SQL
