import json
import sqlite3
import urllib.request
import re
import unicodedata

DB_NAME = "test.db"

def normalize_text(text):
    if not text:
        return ""
    text = str(text).lower().strip()
    text = ''.join((c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn'))
    # text = re.sub(r'[^a-z0-9\s]', '', text)
    return text

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS col_departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS col_municipalities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        FOREIGN KEY(department_id) REFERENCES col_departments(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS col_zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        municipality_id INTEGER,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        FOREIGN KEY(municipality_id) REFERENCES col_municipalities(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS col_comunas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        municipality_id INTEGER,
        zone_id INTEGER,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        FOREIGN KEY(municipality_id) REFERENCES col_municipalities(id),
        FOREIGN KEY(zone_id) REFERENCES col_zones(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS col_neighborhoods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        municipality_id INTEGER,
        comuna_id INTEGER,
        zone_id INTEGER,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        FOREIGN KEY(municipality_id) REFERENCES col_municipalities(id),
        FOREIGN KEY(comuna_id) REFERENCES col_comunas(id),
        FOREIGN KEY(zone_id) REFERENCES col_zones(id)
    )
    ''')
    
    conn.commit()
    return conn

def seed_data(conn):
    cursor = conn.cursor()
    
    # Check if already seeded
    cursor.execute('SELECT COUNT(*) FROM col_departments')
    if cursor.fetchone()[0] > 0:
        print("Base de datos ya sembrada.")
        return
        
    print("Descargando Departamentos y Municipios...")
    json_url = "https://raw.githubusercontent.com/marcovega/colombia-json/master/colombia.json"
    response = urllib.request.urlopen(json_url)
    data = json.loads(response.read())
    
    for dep in data:
        dep_name = dep["departamento"].strip()
        norm_dep = normalize_text(dep_name)
        
        cursor.execute("INSERT INTO col_departments (name, normalized_name) VALUES (?, ?)", (dep_name, norm_dep))
        dep_id = cursor.lastrowid
        
        ciudades = dep.get("ciudades", [])
        for c in ciudades:
            c_name = c.strip()
            norm_c = normalize_text(c_name)
            cursor.execute("INSERT INTO col_municipalities (department_id, name, normalized_name) VALUES (?, ?, ?)", (dep_id, c_name, norm_c))
    
    # Seed specific data for Cali
    cursor.execute("SELECT id FROM col_municipalities WHERE normalized_name = 'cali'")
    cali_row = cursor.fetchone()
    if cali_row:
        cali_id = cali_row[0]
        
        # Zonas
        zonas = ["Norte", "Sur", "Oriente", "Occidente", "Centro"]
        zona_ids = {}
        for z in zonas:
            cursor.execute("INSERT INTO col_zones (municipality_id, name, normalized_name) VALUES (?, ?, ?)", (cali_id, z, normalize_text(z)))
            zona_ids[z] = cursor.lastrowid
            
        # Comunas
        # Pance es Comuna 22.
        comunas = [
            ("Comuna 22", "Sur"),
            ("Comuna 2", "Norte"),
            ("Comuna 17", "Sur")
        ]
        comuna_ids = {}
        for c, z in comunas:
            cursor.execute("INSERT INTO col_comunas (municipality_id, zone_id, name, normalized_name) VALUES (?, ?, ?, ?)", (cali_id, zona_ids[z], c, normalize_text(c)))
            comuna_ids[c] = cursor.lastrowid
            
        # Barrios
        barrios = [
            ("Pance", "Comuna 22", "Sur"),
            ("Ciudad Jardín", "Comuna 22", "Sur"),
            ("Valle del Lili", "Comuna 17", "Sur"),
            ("La Flora", "Comuna 2", "Norte"),
            ("El Peñón", None, "Occidente")
        ]
        for b, c, z in barrios:
            c_id = comuna_ids[c] if c else None
            z_id = zona_ids[z] if z else None
            cursor.execute("INSERT INTO col_neighborhoods (municipality_id, comuna_id, zone_id, name, normalized_name) VALUES (?, ?, ?, ?, ?)", (cali_id, c_id, z_id, b, normalize_text(b)))

    conn.commit()
    print("Datos sembrados.")

def resolver_ubicacion(query: str, conn):
    """
    Recibe una consulta como 'Pance' o 'Valle del Cauca' y devuelve el conglomerado estructurado.
    """
    cursor = conn.cursor()
    norm_query = normalize_text(query)
    
    def search_table(table, joins, selects, table_alias, where_col="name", exact=True):
        match_str = norm_query if exact else f"%{norm_query}%"
        op = "=" if exact else "LIKE"
        sql = f"SELECT {selects} FROM {table} {table_alias} {joins} WHERE {table_alias}.normalized_{where_col} {op} ?"
        cursor.execute(sql, (match_str,))
        return cursor.fetchall()
        
    for exact in [True, False]:
        # 1. Barrios
        barrios = search_table("col_neighborhoods", 
                               "LEFT JOIN col_comunas c ON b.comuna_id = c.id LEFT JOIN col_zones z ON b.zone_id = z.id JOIN col_municipalities m ON b.municipality_id = m.id JOIN col_departments d ON m.department_id = d.id",
                               "b.name as barrio, c.name as comuna, z.name as zona, m.name as municipio, d.name as departamento",
                               "b", exact=exact)
        if barrios:
            res = barrios[0]
            zona_text = f" pertenece a la zona {res[2]}" if res[2] else ""
            comuna_text = f" de la {res[1]}" if res[1] else ""
            return f"'{query}' es el barrio {res[0]}{comuna_text},{zona_text} en la ciudad de {res[3]}, departamento de {res[4]}."
            
        # 2. Comunas
        comunas = search_table("col_comunas",
                               "LEFT JOIN col_zones z ON c.zone_id = z.id JOIN col_municipalities m ON c.municipality_id = m.id JOIN col_departments d ON m.department_id = d.id",
                               "c.name as comuna, z.name as zona, m.name as municipio, d.name as departamento",
                               "c", exact=exact)
        if comunas:
            res = comunas[0]
            zona_text = f" en la zona {res[1]}" if res[1] else ""
            return f"'{query}' es la {res[0]}{zona_text} de la ciudad de {res[2]}, departamento de {res[3]}."
            
        # 3. Zonas
        zonas = search_table("col_zones",
                             "JOIN col_municipalities m ON z.municipality_id = m.id JOIN col_departments d ON m.department_id = d.id",
                             "z.name as zona, m.name as municipio, d.name as departamento",
                             "z", exact=exact)
        if zonas:
            res = zonas[0]
            return f"'{query}' se refiere a la zona {res[0]} de la ciudad de {res[1]}, departamento de {res[2]}."
            
        # 4. Municipios
        municipios = search_table("col_municipalities",
                                  "JOIN col_departments d ON m.department_id = d.id",
                                  "m.name as municipio, d.name as departamento",
                                  "m", exact=exact)
        if municipios:
            res = municipios[0]
            return f"'{query}' es el municipio o ciudad de {res[0]}, en el departamento de {res[1]}."
            
        # 5. Departamentos
        departamentos = search_table("col_departments",
                                     "",
                                     "d.name as departamento",
                                     "d", exact=exact)
        if departamentos:
            res = departamentos[0]
            return f"'{query}' es el departamento de {res[0]}."
            
    return f"No se encontró información geográfica estructural para '{query}'."

if __name__ == "__main__":
    conn = setup_database()
    seed_data(conn)
    
    queries = ["Pance", "Flora", "Valle del Lili", "Cali", "Medellin", "Comuna 22", "Valle del Cauca"]
    for q in queries:
        print(f"Buscando '{q}':")
        print(" ->", resolver_ubicacion(q, conn))
        print()
    
    conn.close()
