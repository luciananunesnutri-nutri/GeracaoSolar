from datetime import datetime, date, timedelta
from pathlib import Path
import os
import yaml
from ..api.apsystems_openapi_client import APSystemsOpenAPIClient
from ..database.repository import Repository
from ..analysis.detector import AnomalyDetector
from ..analysis.statistics import StatisticsCalculator
from ..alerts.alert_manager import AlertManager
from ..utils.logger import logger


def _log_job(job_name: str, started_at: datetime, success: bool, message: str = None):
    """Salva o resultado de uma execução de job no banco. Erros aqui são silenciosos."""
    try:
        finished_at = datetime.now()
        duration = (finished_at - started_at).total_seconds()
        Repository.save_scheduler_log({
            'job_name': job_name,
            'started_at': started_at,
            'finished_at': finished_at,
            'success': success,
            'duration_seconds': round(duration, 1),
            'message': message,
        })
    except Exception as e:
        logger.warning(f"Erro ao salvar log do scheduler: {e}")


def load_config():
    """Carrega configurações."""
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_credentials():
    """Carrega credenciais (arquivo + variáveis de ambiente)."""
    cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
    try:
        with open(cred_path, 'r', encoding='utf-8') as f:
            creds = yaml.safe_load(f) or {}
    except FileNotFoundError:
        creds = {}

    ap = creds.setdefault('apsystems', {})
    ap['app_id'] = os.environ.get('APSYSTEMS_APP_ID') or ap.get('app_id') or ''
    ap['app_secret'] = os.environ.get('APSYSTEMS_APP_SECRET') or ap.get('app_secret') or ''
    ap['sid'] = os.environ.get('APSYSTEMS_SID') or ap.get('sid') or ''

    em = creds.setdefault('email', {})
    em['sender_email'] = os.environ.get('EMAIL_SENDER') or em.get('sender_email')
    em['sender_password'] = os.environ.get('EMAIL_PASSWORD') or em.get('sender_password')
    em['recipient_email'] = os.environ.get('EMAIL_RECIPIENT') or em.get('recipient_email')
    em['smtp_host'] = os.environ.get('SMTP_HOST') or em.get('smtp_host', 'smtp.gmail.com')
    em['smtp_port'] = int(os.environ.get('SMTP_PORT', 0) or em.get('smtp_port', 587))

    return creds


def collect_solar_data():
    """
    Job principal: Coleta dados de geração solar.
    Executado a cada hora.
    """
    _job_started_at = datetime.now()
    logger.info("=" * 50)
    logger.info("Iniciando coleta de dados solares")
    logger.info("=" * 50)

    try:
        # Carregar configurações
        config = load_config()
        credentials = load_credentials()

        # Inicializar cliente API
        client = APSystemsOpenAPIClient(
            app_id=credentials['apsystems']['app_id'],
            app_secret=credentials['apsystems']['app_secret'],
            system_id=credentials['apsystems']['sid']
        )

        # Coletar dados
        logger.info("Coletando dados da API APSystems...")
        data = client.collect_all_data()

        # Armazenar dados no banco
        logger.info("Armazenando dados no banco...")
        repository = Repository()

        # Salvar dados de geração (resumo do sistema)
        summary = data.get('summary', {}) or {}

        generation_data = {
            'timestamp': data['timestamp'],
            'ecu_id': data['system_id'],
            'panel_id': None,  # Para dados agregados
            'power_watts': 0,
            'energy_kwh_daily': float(summary.get('today', 0) or 0),
            'energy_kwh_total': float(summary.get('lifetime', 0) or 0)
        }
        repository.save_generation_data(generation_data)

        # Salvar dados horários para o gráfico do dashboard
        energy_list = data.get('energy_today', []) or []
        if energy_list and len(energy_list) == 24:
            logger.info("Salvando dados horários de geração...")
            from ..database.models import db as _db, GenerationData as _GD

            today_date = data['timestamp'].date()

            # Remove registros horários anteriores do dia para evitar duplicatas
            _session = _db.get_session()
            try:
                _session.query(_GD).filter(
                    _GD.panel_id == 'hourly',
                    _GD.timestamp >= datetime.combine(today_date, datetime.min.time()),
                    _GD.timestamp <= datetime.combine(today_date, datetime.max.time())
                ).delete()
                _session.commit()
            finally:
                _session.close()

            # Salva um registro por hora (kWh → W médio da hora)
            for hour, kwh_str in enumerate(energy_list):
                kwh = float(kwh_str or 0)
                repository.save_generation_data({
                    'timestamp': datetime(today_date.year, today_date.month, today_date.day, hour, 0, 0),
                    'ecu_id': data['system_id'],
                    'panel_id': 'hourly',
                    'power_watts': kwh * 1000,
                    'energy_kwh_daily': None,
                    'energy_kwh_total': None
                })
            logger.info("Dados horários salvos: 24 horas")

        # Atualizar status do sistema
        logger.info("Atualizando status do sistema...")
        status_data = {
            'ecu_id': data['system_id'],
            'status': 'online' if summary else 'offline',
            'last_communication': data['timestamp'],
            'alarm_count': 0
        }
        repository.update_system_status(status_data)

        # ── Telemetria ECU (minutely) ─────────────────────────────────────────
        today_date = data['timestamp'].date()
        today_str = today_date.strftime('%Y-%m-%d')

        for ecu_id, telemetry in (data.get('ecu_telemetry') or {}).items():
            try:
                if telemetry and telemetry.get('time'):
                    repository.save_ecu_telemetry({
                        'date': today_date,
                        'ecu_id': ecu_id,
                        'time_series': telemetry
                    })
                    logger.info(f"ECU {ecu_id}: telemetria minutely salva ({len(telemetry['time'])} pontos)")
            except Exception as e:
                logger.warning(f"Erro ao salvar ECU telemetry {ecu_id}: {e}")

        # ── Inverter batch data ───────────────────────────────────────────────
        for ecu_id, batch_power in (data.get('inverter_batch_power') or {}).items():
            try:
                if batch_power:
                    repository.save_inverter_batch_data({
                        'date': today_date,
                        'ecu_id': ecu_id,
                        'power_data': batch_power
                    })
            except Exception as e:
                logger.warning(f"Erro ao salvar batch power {ecu_id}: {e}")

        for ecu_id, batch_energy in (data.get('inverter_batch_energy') or {}).items():
            try:
                if batch_energy:
                    repository.save_inverter_batch_data({
                        'date': today_date,
                        'ecu_id': ecu_id,
                        'energy_data': batch_energy
                    })
            except Exception as e:
                logger.warning(f"Erro ao salvar batch energy {ecu_id}: {e}")

        # ── Meter data ────────────────────────────────────────────────────────
        for meter_id, meter_summary in (data.get('meter_summaries') or {}).items():
            try:
                if meter_summary:
                    repository.save_meter_data({
                        'meter_id': meter_id,
                        'today': meter_summary.get('today'),
                        'month': meter_summary.get('month'),
                        'year': meter_summary.get('year'),
                        'lifetime': meter_summary.get('lifetime')
                    })
                    logger.info(f"Meter {meter_id}: dados salvos")
            except Exception as e:
                logger.warning(f"Erro ao salvar meter data {meter_id}: {e}")

        # ── Inverter summaries por canal ──────────────────────────────────────
        for uid, inv_summary in (data.get('inverter_summaries') or {}).items():
            try:
                if inv_summary:
                    # Mapear d1,m1,y1,t1,d2,m2... em estrutura por canal
                    channels = {}
                    for ch in range(1, 5):
                        d = inv_summary.get(f'd{ch}')
                        m = inv_summary.get(f'm{ch}')
                        y = inv_summary.get(f'y{ch}')
                        t = inv_summary.get(f't{ch}')
                        if any(v is not None for v in [d, m, y, t]):
                            channels[ch] = {'today': d, 'month': m, 'year': y, 'lifetime': t}
                    if channels:
                        repository.save_inverter_summary({
                            'inverter_uid': uid,
                            'channels': channels
                        })
            except Exception as e:
                logger.warning(f"Erro ao salvar inverter summary {uid}: {e}")

        # ── Detecção de anomalias ─────────────────────────────────────────────
        try:
            detector = AnomalyDetector()
            alert_manager = AlertManager()
            detected = detector.analyze_openapi_data(data)

            if detected:
                logger.warning(f"Anomalias detectadas: {len(detected)} alerta(s)")
                processed = alert_manager.process_multiple_alerts(detected)
                logger.warning(f"{processed} alerta(s) novo(s) processado(s) e notificado(s)")
            else:
                logger.info("Nenhuma anomalia detectada nesta coleta")
        except Exception as e:
            logger.warning(f"Erro na detecção de anomalias: {e}")

        logger.info("Coleta de dados concluída com sucesso")
        logger.info("=" * 50)
        _log_job('collection', _job_started_at, True, "Coleta concluída com sucesso")

    except Exception as e:
        logger.error(f"Erro na coleta de dados: {e}", exc_info=True)
        logger.info("=" * 50)
        _log_job('collection', _job_started_at, False, str(e))
        raise


def send_evening_summary(force: bool = False):
    """
    Envia resumo do dia por email às 17:00.
    Coleta os dados mais recentes e envia para todos os destinatários ativos.
    Guard: não envia se já foi enviado com sucesso hoje (a menos que force=True).
    """
    _job_started_at = datetime.now()
    logger.info("=" * 50)
    logger.info("Enviando resumo vespertino por email")
    logger.info("=" * 50)

    # Idempotência: evitar duplo envio no mesmo dia
    if not force and Repository.was_email_sent_today('evening_summary'):
        logger.info("Resumo vespertino já enviado hoje — ignorando execução dupla")
        logger.info("=" * 50)
        return

    try:
        config = load_config()
        credentials = load_credentials()

        # Buscar dados mais recentes via API
        client = APSystemsOpenAPIClient(
            app_id=credentials['apsystems']['app_id'],
            app_secret=credentials['apsystems']['app_secret'],
            system_id=credentials['apsystems']['sid']
        )

        summary = client.get_system_summary()
        today_kwh  = float(summary.get('today', 0) or 0)
        month_kwh  = float(summary.get('month', 0) or 0)
        year_kwh   = float(summary.get('year', 0) or 0)
        lifetime_kwh = float(summary.get('lifetime', 0) or 0)

        # Buscar pico do dia nas estatísticas locais
        repository = Repository()
        today = date.today()
        stats = repository.get_daily_stats(today)
        peak_w = stats.peak_power_watts if stats else 0

        # Montar dados do resumo
        summary_data = {
            'date': today.strftime('%d/%m/%Y'),
            'total_generation_kwh': today_kwh,
            'peak_power_watts': peak_w,
            'average_power_watts': stats.average_power_watts if stats else 0,
            'month_kwh': month_kwh,
            'year_kwh': year_kwh,
            'lifetime_kwh': lifetime_kwh,
        }

        # Buscar alertas do dia para incluir no email
        todays_alerts = []
        try:
            alerts_objs = repository.get_todays_alerts(unresolved_only=True)
            todays_alerts = [
                {'alert_type': a.alert_type.value, 'severity': a.severity.value,
                 'message': a.message, 'timestamp': a.timestamp.isoformat()}
                for a in alerts_objs
            ]
            if todays_alerts:
                logger.info(f"Incluindo {len(todays_alerts)} alerta(s) no resumo vespertino")
        except Exception as e:
            logger.warning(f"Erro ao buscar alertas do dia: {e}")

        # Gerar insights para incluir no email
        insights = None
        try:
            from ..analysis.insights import generate_insights
            insights = generate_insights(repository=repository)
            logger.info("Insights gerados para o resumo vespertino")
            # Atualiza pico com dado da telemetria minutal (mais preciso que stats agregado)
            profile_peak = (insights or {}).get('profile', {}).get('peak_power_w', 0)
            if profile_peak and profile_peak > summary_data['peak_power_watts']:
                summary_data['peak_power_watts'] = profile_peak
                logger.info(f"Pico atualizado com telemetria minutal: {profile_peak} W")
        except Exception as e:
            logger.warning(f"Erro ao gerar insights para o email: {e}")

        # Enviar email
        from ..alerts.alert_manager import AlertManager

        alert_manager = AlertManager()
        success = alert_manager.email_sender.send_evening_summary_email(
            summary_data, todays_alerts, insights
        )

        if success:
            logger.info("Resumo vespertino enviado com sucesso")
            _log_job('evening_summary', _job_started_at, True, "Resumo vespertino enviado com sucesso")
        else:
            logger.warning("Falha ao enviar resumo vespertino")
            _log_job('evening_summary', _job_started_at, False, "Falha ao enviar resumo vespertino")

    except Exception as e:
        logger.error(f"Erro no envio do resumo vespertino: {e}", exc_info=True)
        _log_job('evening_summary', _job_started_at, False, str(e))
    finally:
        logger.info("=" * 50)


def calculate_statistics():
    """
    Job secundário: Calcula estatísticas diárias.
    Executado diariamente às 23:55.
    """
    _job_started_at = datetime.now()
    logger.info("=" * 50)
    logger.info("Iniciando cálculo de estatísticas")
    logger.info("=" * 50)

    try:
        calculator = StatisticsCalculator()

        # Calcular estatísticas de hoje
        today = date.today()
        logger.info(f"Calculando estatísticas para {today}")
        daily_stats = calculator.calculate_daily_stats(today)

        if daily_stats:
            logger.info(f"Geração total do dia: {daily_stats['total_generation_kwh']:.2f} kWh")

            # Enviar relatório diário por email
            try:
                repository = Repository()
                summaries = repository.get_all_inverter_summaries()
                daily_stats['month_kwh'] = round(sum(
                    float(ch.get('month') or 0)
                    for rec in (summaries or [])
                    for ch in (rec.channels or {}).values()
                ), 2)
                daily_stats['year_kwh'] = round(sum(
                    float(ch.get('year') or 0)
                    for rec in (summaries or [])
                    for ch in (rec.channels or {}).values()
                ), 2)
                # Incluir alertas do dia no relatório
                alerts_objs = repository.get_todays_alerts(unresolved_only=False)
                todays_alerts = [
                    {'alert_type': a.alert_type.value, 'severity': a.severity.value,
                     'message': a.message, 'timestamp': a.timestamp.isoformat()}
                    for a in alerts_objs
                ]
                # Gerar insights para incluir no relatório
                report_insights = None
                try:
                    from ..analysis.insights import generate_insights
                    report_insights = generate_insights(repository=repository)
                except Exception as _e:
                    logger.warning(f"Erro ao gerar insights para o relatório: {_e}")
                alert_manager = AlertManager()
                alert_manager.email_sender.send_daily_report_email(
                    daily_stats, todays_alerts, report_insights
                )
            except Exception as e:
                logger.warning(f"Falha ao enviar relatório diário por email: {e}")

        # Atualizar estatísticas mensais
        logger.info(f"Atualizando estatísticas mensais para {today.year}-{today.month:02d}")
        monthly_stats = calculator.calculate_monthly_stats(today.year, today.month)

        if monthly_stats:
            logger.info(f"Geração total do mês: {monthly_stats['total_generation_kwh']:.2f} kWh")

        # Atualizar estatísticas anuais
        logger.info(f"Atualizando estatísticas anuais para {today.year}")
        yearly_stats = calculator.calculate_yearly_stats(today.year)

        if yearly_stats:
            logger.info(f"Geração total do ano: {yearly_stats['total_generation_kwh']:.2f} kWh")

        logger.info("Cálculo de estatísticas concluído com sucesso")
        logger.info("=" * 50)
        _log_job('statistics', _job_started_at, True, "Estatísticas calculadas com sucesso")

    except Exception as e:
        logger.error(f"Erro no cálculo de estatísticas: {e}", exc_info=True)
        logger.info("=" * 50)
        _log_job('statistics', _job_started_at, False, str(e))
        raise


def cleanup_old_data():
    """
    Job terciário: Limpa dados antigos.
    Executado semanalmente (domingos às 2h).
    """
    _job_started_at = datetime.now()
    logger.info("=" * 50)
    logger.info("Iniciando limpeza de dados antigos")
    logger.info("=" * 50)

    try:
        from ..database.models import db, GenerationData
        from sqlalchemy import and_

        # Manter apenas últimos 6 meses de dados brutos
        cutoff_date = datetime.now() - timedelta(days=180)

        session = db.get_session()
        try:
            # Contar registros a remover
            count = session.query(GenerationData).filter(
                GenerationData.timestamp < cutoff_date
            ).count()

            if count > 0:
                logger.info(f"Removendo {count} registros antigos (antes de {cutoff_date.date()})")

                # Remover registros
                session.query(GenerationData).filter(
                    GenerationData.timestamp < cutoff_date
                ).delete()

                session.commit()
                logger.info(f"{count} registros removidos com sucesso")
            else:
                logger.info("Nenhum registro antigo para remover")

        finally:
            session.close()

        # Otimizar banco de dados (VACUUM — apenas SQLite)
        if 'sqlite' in str(db.engine.url):
            logger.info("Otimizando banco de dados (VACUUM)...")
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text("VACUUM"))
                conn.commit()

        logger.info("Limpeza de dados concluída com sucesso")
        logger.info("=" * 50)
        _log_job('cleanup', _job_started_at, True, "Limpeza de dados concluída com sucesso")

    except Exception as e:
        logger.error(f"Erro na limpeza de dados: {e}", exc_info=True)
        logger.info("=" * 50)
        _log_job('cleanup', _job_started_at, False, str(e))
        raise


# Função auxiliar para testes manuais
def test_collection():
    """
    Função para testar coleta de dados manualmente.
    """
    logger.info("Executando coleta de teste...")
    collect_solar_data()
