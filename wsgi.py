"""
Ponto de entrada WSGI para Gunicorn (produção).
Uso: gunicorn "wsgi:app"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.web.app import create_app

app = create_app()
