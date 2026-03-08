import sys
import os

# Agregamos la ruta del backend para que Vercel pueda ver los imports de app...
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, '..', 'backend')
sys.path.append(backend_dir)

from app.main import app
