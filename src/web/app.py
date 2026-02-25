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
