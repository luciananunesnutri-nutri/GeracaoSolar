from flask import Flask, render_template, jsonify, request
from datetime import date, datetime, timedelta
from pathlib import Path
import os
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

    # Variáveis de ambiente sobrescrevem o config.yaml (para deploy em nuvem)
    if os.environ.get('SECRET_KEY'):
        config['auth']['secret_key'] = os.environ['SECRET_KEY']
    if os.environ.get('ANTHROPIC_API_KEY'):
        config.setdefault('claude', {})['api_key'] = os.environ['ANTHROPIC_API_KEY']
    if os.environ.get('PORT'):
        config['web']['port'] = int(os.environ['PORT'])

    app.config['DEBUG'] = config['web']['debug']
    app.secret_key = config['auth']['secret_key']

    # Autenticação via Flask-Login
    from .login_manager import login_manager
    login_manager.init_app(app)

    # Blueprint de autenticação (login/logout)
    from .auth import auth_bp
    app.register_blueprint(auth_bp)

    # Registrar rotas
    from .routes import register_routes
    register_routes(app)

    # Criar admin inicial se não existir
    _ensure_admin_user(config)

    # Garantir destinatário padrão de alertas/relatórios
    _ensure_default_recipients()

    # Iniciar scheduler de jobs (coleta, relatórios, estatísticas)
    _start_scheduler(config)

    # Injeta chat_enabled em todos os templates (leitura em tempo real do config)
    @app.context_processor
    def inject_chat_enabled():
        try:
            with open(config_path, 'r', encoding='utf-8') as _f:
                _cfg = yaml.safe_load(_f)
            return {'chat_enabled': _cfg.get('claude', {}).get('chat_enabled', True)}
        except Exception:
            return {'chat_enabled': True}

    # Forçar no-cache em todas as respostas HTML para evitar cache de browser
    @app.after_request
    def add_no_cache_headers(response):
        if 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    return app


def _ensure_admin_user(config):
    """Cria o usuário admin inicial se o banco não tiver nenhum usuário."""
    from werkzeug.security import generate_password_hash
    from ..database.models import db, User
    session = db.get_session()
    try:
        if session.query(User).count() > 0:
            return
        admin_cfg = config.get('auth', {}).get('initial_admin', {})
        email    = admin_cfg.get('email', 'admin@geracaosolar.local')
        password = admin_cfg.get('password', 'SenhaForte2026!')
        name     = admin_cfg.get('name', 'Administrador')
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            name=name,
            role='admin',
            active=True,
        )
        session.add(user)
        session.commit()
        logger.info(f"Admin inicial criado: {email}")
    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao criar admin inicial: {e}")
    finally:
        session.close()


def _ensure_default_recipients():
    """Garante que os destinatários padrão existam no banco (recria após reset do DB)."""
    from ..database.models import db, AlertRecipient
    session = db.get_session()
    try:
        defaults = [
            {'name': 'Luciana Nunes', 'email': 'luciananunesnutri@gmail.com'},
        ]
        for d in defaults:
            exists = session.query(AlertRecipient).filter_by(email=d['email']).first()
            if not exists:
                recipient = AlertRecipient(
                    name=d['name'],
                    email=d['email'],
                    active=True,
                    receive_alerts=True,
                    receive_reports=True,
                )
                session.add(recipient)
                logger.info(f"Destinatário padrão criado: {d['email']}")
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao criar destinatários padrão: {e}")
    finally:
        session.close()


def _parse_cron(cron_expr: str) -> dict:
    """Converte cron '15 20 * * *' em kwargs do APScheduler CronTrigger."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return {}
    return {
        'minute': parts[0],
        'hour': parts[1],
        'day': parts[2],
        'month': parts[3],
        'day_of_week': parts[4],
    }


_scheduler_started = False


def _start_scheduler(config):
    """Inicia o APScheduler com os jobs configurados em config.yaml."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    sc = config.get('scheduler', {})

    # Verificar se há pelo menos um job habilitado
    any_enabled = (
        sc.get('collection_enabled', False)
        or sc.get('evening_summary_enabled', False)
        or sc.get('statistics_enabled', False)
        or sc.get('cleanup_enabled', False)
    )
    if not any_enabled:
        logger.info("Scheduler: nenhum job habilitado — scheduler não iniciado")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        tz_br = pytz.timezone('America/Sao_Paulo')
        scheduler = BackgroundScheduler(timezone=tz_br)

        from ..scheduler.jobs import (
            collect_solar_data, send_evening_summary,
            calculate_statistics, cleanup_old_data
        )

        if sc.get('collection_enabled', False):
            cron = _parse_cron(sc.get('collection_interval', '0 */1 * * *'))
            if cron:
                scheduler.add_job(collect_solar_data, CronTrigger(**cron, timezone=tz_br),
                                  id='collection', replace_existing=True,
                                  misfire_grace_time=300)
                logger.info(f"Scheduler: coleta agendada — {sc.get('collection_interval')}")

        if sc.get('evening_summary_enabled', False):
            cron = _parse_cron(sc.get('evening_summary_interval', '0 20 * * *'))
            if cron:
                scheduler.add_job(send_evening_summary, CronTrigger(**cron, timezone=tz_br),
                                  id='evening_summary', replace_existing=True,
                                  misfire_grace_time=600)
                logger.info(f"Scheduler: resumo vespertino agendado — {sc.get('evening_summary_interval')}")

        if sc.get('statistics_enabled', False):
            cron = _parse_cron(sc.get('statistics_interval', '55 23 * * *'))
            if cron:
                scheduler.add_job(calculate_statistics, CronTrigger(**cron, timezone=tz_br),
                                  id='statistics', replace_existing=True,
                                  misfire_grace_time=300)
                logger.info(f"Scheduler: estatísticas agendado — {sc.get('statistics_interval')}")

        if sc.get('cleanup_enabled', False):
            cron = _parse_cron(sc.get('cleanup_interval', '0 2 * * 0'))
            if cron:
                scheduler.add_job(cleanup_old_data, CronTrigger(**cron, timezone=tz_br),
                                  id='cleanup', replace_existing=True,
                                  misfire_grace_time=300)
                logger.info(f"Scheduler: limpeza agendada — {sc.get('cleanup_interval')}")

        scheduler.start()
        logger.info("Scheduler iniciado com sucesso")

        # Coleta imediata no startup se configurado
        if sc.get('collection_on_startup', False):
            logger.info("Scheduler: executando coleta no startup...")
            scheduler.add_job(collect_solar_data, id='collection_startup',
                              replace_existing=True)

    except ImportError as e:
        logger.error(f"Scheduler: APScheduler não instalado — {e}")
    except Exception as e:
        logger.error(f"Scheduler: erro ao iniciar — {e}", exc_info=True)


def get_repository():
    """Helper para obter repositório."""
    return Repository()


def get_alert_manager():
    """Helper para obter gerenciador de alertas."""
    return AlertManager()


def get_statistics_calculator():
    """Helper para obter calculador de estatísticas."""
    return StatisticsCalculator()
