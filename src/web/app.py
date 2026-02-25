from flask import Flask, render_template, jsonify, request
from datetime import date, datetime, timedelta
from pathlib import Path
import yaml
from ..database.repository import Repository
from ..alerts.alert_manager import AlertManager
from ..analysis.statistics import StatisticsCalculator
from ..utils.logger import logger


def create_app():
    """Cria e configura a aplicação Flask."""
    app = Flask(__name__)

    # Carregar configurações
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    app.config['DEBUG'] = config['web']['debug']

    # Registrar rotas
    from .routes import register_routes
    register_routes(app)

    # Forçar no-cache em todas as respostas HTML para evitar cache de browser
    @app.after_request
    def add_no_cache_headers(response):
        if 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    return app


def get_repository():
    """Helper para obter repositório."""
    return Repository()


def get_alert_manager():
    """Helper para obter gerenciador de alertas."""
    return AlertManager()


def get_statistics_calculator():
    """Helper para obter calculador de estatísticas."""
    return StatisticsCalculator()
