from flask import render_template, jsonify, request
from datetime import date, datetime, timedelta
from ..database.repository import Repository
from ..alerts.alert_manager import AlertManager
from ..analysis.statistics import StatisticsCalculator
from ..utils.logger import logger
import yaml
import threading
from pathlib import Path

# Cache em memória para dados históricos da API (evita chamadas repetidas)
_api_cache = {}  # key -> {'value': ..., 'date': date}

# Estado da coleta em andamento
_collect_state = {'running': False, 'last_result': None, 'last_run': None}


def _load_credentials():
    cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
    with open(cred_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _make_api_client():
    from ..api.apsystems_openapi_client import APSystemsOpenAPIClient
    creds = _load_credentials()
    return APSystemsOpenAPIClient(
        app_id=creds['apsystems']['app_id'],
        app_secret=creds['apsystems']['app_secret'],
        system_id=creds['apsystems']['sid']
    )


def register_routes(app):
    """Registra todas as rotas da aplicação."""

    @app.route('/')
    def index():
        """Dashboard principal."""
        return render_template('dashboard.html')

    @app.route('/config')
    def config_page():
        """Página de configurações do sistema."""
        return render_template('config.html')

    @app.route('/insights')
    def insights_page():
        """Página de insights e análises do sistema."""
        return render_template('insights.html')

    # ── API de Configurações ──────────────────────────────────────────────────

    @app.route('/api/config/all', methods=['GET'])
    def api_config_all():
        """Retorna todas as configurações do sistema."""
        try:
            cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            cfg_path  = Path(__file__).parent.parent.parent / "config" / "config.yaml"

            with open(cred_path, 'r', encoding='utf-8') as f:
                creds = yaml.safe_load(f)
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)

            ap = creds.get('apsystems', {})
            em = creds.get('email', {})
            sc = cfg.get('scheduler', {})
            lo = cfg.get('logging', {})
            wb = cfg.get('web', {})

            return jsonify({
                'status': 'success',
                'apsystems': {
                    'app_id':  ap.get('app_id', ''),
                    'app_secret': '••••••' if ap.get('app_secret') else '',
                    'sid': ap.get('sid', '')
                },
                'email': {
                    'smtp_host':     em.get('smtp_host', 'smtp.gmail.com'),
                    'smtp_port':     em.get('smtp_port', 587),
                    'sender_email':  em.get('sender_email', ''),
                    'has_password':  bool(em.get('sender_password') and
                                         em.get('sender_password') != 'senha_aplicativo_google'),
                },
                'scheduler': {
                    'collection_enabled':       sc.get('collection_enabled', True),
                    'collection_on_startup':    sc.get('collection_on_startup', False),
                    'evening_summary_enabled':  sc.get('evening_summary_enabled', True),
                    'statistics_enabled':       sc.get('statistics_enabled', True),
                    'cleanup_enabled':          sc.get('cleanup_enabled', True),
                    'collection_interval':      sc.get('collection_interval', '0 18 * * *'),
                    'evening_summary_interval': sc.get('evening_summary_interval', '0 20 * * *'),
                    'statistics_interval':      sc.get('statistics_interval', '40 20 * * *'),
                    'cleanup_interval':         sc.get('cleanup_interval', '0 2 * * 0'),
                },
                'logging': {
                    'level': lo.get('level', 'INFO'),
                },
                'web': {
                    'port':  wb.get('port', 5000),
                    'debug': wb.get('debug', False),
                }
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/config/apsystems', methods=['POST'])
    def api_config_save_apsystems():
        """Salva credenciais APSystems."""
        try:
            data = request.get_json()
            cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            with open(cred_path, 'r', encoding='utf-8') as f:
                creds = yaml.safe_load(f)

            if 'apsystems' not in creds:
                creds['apsystems'] = {}
            if data.get('app_id'):
                creds['apsystems']['app_id'] = data['app_id'].strip()
            if data.get('app_secret') and '••' not in data['app_secret']:
                creds['apsystems']['app_secret'] = data['app_secret'].strip()
            if data.get('sid'):
                creds['apsystems']['sid'] = data['sid'].strip()

            with open(cred_path, 'w', encoding='utf-8') as f:
                yaml.dump(creds, f, allow_unicode=True, default_flow_style=False)

            logger.info("Credenciais APSystems atualizadas")
            return jsonify({'status': 'success', 'message': 'Credenciais APSystems salvas'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/config/scheduler', methods=['POST'])
    def api_config_save_scheduler():
        """Salva configuração do scheduler."""
        try:
            data = request.get_json()
            cfg_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)

            sc = cfg.setdefault('scheduler', {})
            # Flags booleanas
            for key in ('collection_enabled', 'collection_on_startup',
                        'evening_summary_enabled', 'statistics_enabled', 'cleanup_enabled'):
                if key in data:
                    sc[key] = bool(data[key])
            # Expressões cron
            for key in ('collection_interval', 'evening_summary_interval',
                        'statistics_interval', 'cleanup_interval'):
                if data.get(key):
                    sc[key] = data[key].strip()

            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

            logger.info("Configuração do scheduler atualizada")
            return jsonify({'status': 'success',
                            'message': 'Agendamentos salvos com sucesso'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/scheduler/log')
    def api_scheduler_log():
        """Retorna histórico de execuções dos jobs agendados."""
        try:
            limit = min(int(request.args.get('limit', 100)), 500)
            job_name = request.args.get('job') or None
            logs = Repository.get_scheduler_logs(limit=limit, job_name=job_name)
            JOB_LABELS = {
                'collection': 'Coleta', 'evening_summary': 'Resumo Vespertino',
                'statistics': 'Estatísticas', 'cleanup': 'Limpeza', 'unknown': '—'
            }
            result = [{
                'id': e.id,
                'started_at': e.started_at.strftime('%d/%m/%Y %H:%M:%S'),
                'finished_at': e.finished_at.strftime('%d/%m/%Y %H:%M:%S') if e.finished_at else None,
                'job_name': e.job_name,
                'job_label': JOB_LABELS.get(e.job_name, e.job_name),
                'success': e.success,
                'duration_seconds': e.duration_seconds,
                'message': e.message,
            } for e in logs]
            return jsonify({'status': 'success', 'logs': result, 'total': len(result)})
        except Exception as e:
            logger.error(f"Erro ao buscar log do scheduler: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/scheduler/restart', methods=['POST'])
    def api_scheduler_restart():
        """Reinicia o processo do scheduler (main.py)."""
        import subprocess, sys as _sys
        project_root = Path(__file__).parent.parent.parent
        pid_path     = project_root / 'data' / 'scheduler.pid'
        log_path     = project_root / 'logs' / 'scheduler.log'

        # Encerra processo atual se existir
        if pid_path.exists():
            try:
                old_pid = int(pid_path.read_text().strip())
                if _sys.platform == 'win32':
                    subprocess.run(['taskkill', '/F', '/PID', str(old_pid)],
                                   capture_output=True)
                else:
                    import signal as _sig
                    import os as _os
                    _os.kill(old_pid, _sig.SIGTERM)
                logger.info(f"Scheduler anterior (PID {old_pid}) encerrado")
            except Exception as e:
                logger.warning(f"Não foi possível encerrar scheduler anterior: {e}")

        # Inicia novo processo
        try:
            log_file = open(str(log_path), 'a')
            subprocess.Popen(
                [_sys.executable, str(project_root / 'main.py')],
                cwd=str(project_root),
                stdout=log_file,
                stderr=log_file
            )
            logger.info("Scheduler reiniciado com sucesso")
            return jsonify({'status': 'success', 'message': 'Scheduler reiniciado com sucesso'})
        except Exception as e:
            logger.error(f"Erro ao reiniciar scheduler: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/config/system', methods=['POST'])
    def api_config_save_system():
        """Salva configuração do sistema (logging, web)."""
        try:
            data = request.get_json()
            cfg_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)

            if data.get('log_level'):
                cfg.setdefault('logging', {})['level'] = data['log_level']
            if data.get('web_port'):
                cfg.setdefault('web', {})['port'] = int(data['web_port'])
            if 'web_debug' in data:
                cfg.setdefault('web', {})['debug'] = bool(data['web_debug'])

            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

            logger.info("Configuração do sistema atualizada")
            return jsonify({'status': 'success',
                            'message': 'Configuração salva — reinicie o servidor para aplicar'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500


    @app.route('/api/current')
    def api_current():
        """Retorna dados em tempo real."""
        try:
            repository = Repository()

            # Buscar dados mais recentes
            today = date.today()
            data = repository.get_generation_data_for_period(today, today)

            if not data:
                return jsonify({
                    'status': 'no_data',
                    'message': 'Sem dados disponíveis'
                }), 404

            # Registro agregado mais recente (última coleta do dia) com totais de energia
            aggregate = next((d for d in reversed(data) if d.panel_id is None and d.energy_kwh_total is not None), None)

            # Potência atual = último registro horário até a hora corrente
            from datetime import datetime as _dt
            current_hour = _dt.now().hour
            hourly_records = [d for d in data if d.panel_id == 'hourly' and d.timestamp.hour <= current_hour]
            current_power = hourly_records[-1].power_watts if hourly_records else 0

            # Pico e média calculados direto dos registros horários (sem depender de statistics)
            hourly_watts = [d.power_watts for d in data if d.panel_id == 'hourly']
            peak_today = max(hourly_watts) if hourly_watts else 0
            active_hours = [w for w in hourly_watts if w > 0]
            average_today = sum(active_hours) / len(active_hours) if active_hours else 0

            response = {
                'status': 'success',
                'timestamp': (aggregate or data[-1]).timestamp.isoformat(),
                'current_power': current_power,
                'energy_today': (aggregate.energy_kwh_daily or 0) if aggregate else 0,
                'energy_total': (aggregate.energy_kwh_total or 0) if aggregate else 0,
                'peak_today': peak_today,
                'average_today': average_today
            }

            return jsonify(response)

        except Exception as e:
            logger.error(f"Erro ao buscar dados atuais: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/daily/<date_str>')
    def api_daily(date_str):
        """Retorna estatísticas diárias."""
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            repository = Repository()

            # Buscar estatísticas
            stats = repository.get_daily_stats(target_date)

            if not stats:
                # Calcular se não existir
                calculator = StatisticsCalculator()
                stats_dict = calculator.calculate_daily_stats(target_date)
                if not stats_dict:
                    return jsonify({
                        'status': 'no_data',
                        'message': f'Sem dados para {date_str}'
                    }), 404
            else:
                stats_dict = {
                    'date': stats.date.isoformat(),
                    'total_generation_kwh': stats.total_generation_kwh,
                    'peak_power_watts': stats.peak_power_watts,
                    'average_power_watts': stats.average_power_watts,
                    'panel_stats': stats.panel_stats
                }

            # Buscar dados horários para gráfico (apenas registros com panel_id='hourly')
            data = repository.get_generation_data_for_period(target_date, target_date)
            hourly_map = {
                record.timestamp.hour: record.power_watts
                for record in data
                if record.panel_id == 'hourly'
            }

            chart_data = [
                {'hour': hour, 'power': hourly_map.get(hour, 0)}
                for hour in range(24)
            ]

            response = {
                'status': 'success',
                'date': date_str,
                'statistics': stats_dict,
                'chart_data': chart_data
            }

            return jsonify(response)

        except ValueError:
            return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400
        except Exception as e:
            logger.error(f"Erro ao buscar dados diários: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/monthly/<int:year>/<int:month>')
    def api_monthly(year, month):
        """Retorna estatísticas mensais."""
        try:
            repository = Repository()
            stats = repository.get_monthly_stats(year, month)

            if not stats:
                # Calcular se não existir
                calculator = StatisticsCalculator()
                stats_dict = calculator.calculate_monthly_stats(year, month)
                if not stats_dict:
                    return jsonify({
                        'status': 'no_data',
                        'message': f'Sem dados para {year}-{month:02d}'
                    }), 404
            else:
                stats_dict = {
                    'date': stats.date.isoformat(),
                    'total_generation_kwh': stats.total_generation_kwh,
                    'peak_power_watts': stats.peak_power_watts,
                    'average_power_watts': stats.average_power_watts,
                    'panel_stats': stats.panel_stats
                }

            return jsonify({
                'status': 'success',
                'year': year,
                'month': month,
                'statistics': stats_dict
            })

        except Exception as e:
            logger.error(f"Erro ao buscar dados mensais: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/yearly/<int:year>')
    def api_yearly(year):
        """Retorna estatísticas anuais."""
        try:
            repository = Repository()
            stats = repository.get_yearly_stats(year)

            if not stats:
                # Calcular se não existir
                calculator = StatisticsCalculator()
                stats_dict = calculator.calculate_yearly_stats(year)
                if not stats_dict:
                    return jsonify({
                        'status': 'no_data',
                        'message': f'Sem dados para {year}'
                    }), 404
            else:
                stats_dict = {
                    'date': stats.date.isoformat(),
                    'total_generation_kwh': stats.total_generation_kwh,
                    'peak_power_watts': stats.peak_power_watts,
                    'average_power_watts': stats.average_power_watts,
                    'panel_stats': stats.panel_stats
                }

            return jsonify({
                'status': 'success',
                'year': year,
                'statistics': stats_dict
            })

        except Exception as e:
            logger.error(f"Erro ao buscar dados anuais: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/panels')
    def api_panels():
        """Retorna comparação entre painéis (inversores) com dados reais."""
        try:
            repository = Repository()
            credentials = _load_credentials()
            ecu_id = credentials['apsystems']['sid']
            today = date.today()

            # Buscar batch power do dia e summaries de energia por inversor
            batch = repository.get_latest_inverter_batch_for_date(today)
            summaries = repository.get_all_inverter_summaries()

            # Agrupar todos os valores de potência por inverter uid
            inverter_power = {}  # uid -> [float, ...]
            if batch and batch.power_data:
                for ch_key, values in batch.power_data.get('power', {}).items():
                    # ch_key = 'uid-channel', e.g. '802000171000-2'
                    uid = ch_key.rsplit('-', 1)[0]
                    float_vals = [float(v) for v in values if v is not None]
                    inverter_power.setdefault(uid, []).extend(float_vals)

            # Somar energia de hoje por inverter uid (todos os canais)
            inverter_energy = {}  # uid -> total kWh today
            for rec in (summaries or []):
                total = sum(
                    float(ch.get('today') or 0)
                    for ch in (rec.channels or {}).values()
                )
                inverter_energy[rec.inverter_uid] = total

            # Montar lista de painéis
            all_uids = set(inverter_power.keys()) | set(inverter_energy.keys())
            panels = []
            for uid in sorted(all_uids):
                vals = inverter_power.get(uid, [])
                non_zero = [v for v in vals if v > 0]
                panels.append({
                    'panel_id': uid,
                    'average_power': round(sum(non_zero) / len(non_zero), 1) if non_zero else 0,
                    'peak_power': round(max(vals), 1) if vals else 0,
                    'total_energy': round(inverter_energy.get(uid, 0), 3),
                    'readings_count': len(vals)
                })

            return jsonify({
                'status': 'success',
                'period_start': today.isoformat(),
                'period_end': today.isoformat(),
                'panels': panels
            })

        except Exception as e:
            logger.error(f"Erro ao buscar dados de painéis: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/alerts')
    def api_alerts():
        """Retorna alertas. ?today=1 filtra apenas hoje. ?all=1 inclui resolvidos. ?limit=N limita."""
        try:
            show_all   = request.args.get('all', '0') == '1'
            today_only = request.args.get('today', '0') == '1'
            limit      = int(request.args.get('limit', 50))
            repository = Repository()
            if today_only:
                alerts = repository.get_todays_alerts(unresolved_only=not show_all)
            else:
                alerts = repository.get_recent_alerts(limit=limit, unresolved_only=not show_all)

            def _to_dict(a):
                return {
                    'id': a.id,
                    'timestamp': a.timestamp.isoformat(),
                    'alert_type': a.alert_type.value,
                    'severity': a.severity.value,
                    'message': a.message,
                    'details': a.details,
                    'resolved': a.resolved,
                    'resolved_at': a.resolved_at.isoformat() if a.resolved_at else None
                }

            unresolved_count = sum(1 for a in alerts if not a.resolved)
            return jsonify({
                'status': 'success',
                'count': unresolved_count,
                'total': len(alerts),
                'alerts': [_to_dict(a) for a in alerts]
            })

        except Exception as e:
            logger.error(f"Erro ao buscar alertas: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
    def api_resolve_alert(alert_id):
        """Resolve um alerta."""
        try:
            alert_manager = AlertManager()
            success = alert_manager.resolve_alert(alert_id)

            if success:
                return jsonify({
                    'status': 'success',
                    'message': f'Alerta {alert_id} resolvido'
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Alerta {alert_id} não encontrado'
                }), 404

        except Exception as e:
            logger.error(f"Erro ao resolver alerta: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/available-dates')
    def api_available_dates():
        """Retorna lista de datas com dados de geração (para navegação no dashboard)."""
        try:
            repository = Repository()
            dates = repository.get_dates_with_data()
            return jsonify({
                'status': 'success',
                'dates': [d.isoformat() for d in dates]
            })
        except Exception as e:
            logger.error(f"Erro ao buscar datas disponíveis: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/telemetry')
    def api_telemetry():
        """Retorna telemetria minutely da ECU para uma data. Parâmetro ?date=YYYY-MM-DD (padrão: hoje)."""
        try:
            repository = Repository()
            date_str = request.args.get('date')
            if date_str:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                target_date = date.today()

            record = repository.get_latest_ecu_telemetry_for_date(target_date)
            if not record or not record.time_series:
                return jsonify({'status': 'no_data', 'message': 'Telemetria minutely não disponível'}), 404

            ts = record.time_series
            return jsonify({
                'status': 'success',
                'ecu_id': record.ecu_id,
                'date': target_date.isoformat(),
                'time': ts.get('time', []),
                'power': [float(v) if v else 0 for v in ts.get('power', [])],
                'energy': [float(v) if v else 0 for v in ts.get('energy', [])],
                'today_total': ts.get('today')
            })
        except Exception as e:
            logger.error(f"Erro ao buscar telemetria: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/inverters/batch')
    def api_inverters_batch():
        """Retorna batch power de todos os inversores para hoje."""
        try:
            repository = Repository()
            today = date.today()

            record = repository.get_latest_inverter_batch_for_date(today)
            if not record:
                return jsonify({'status': 'no_data', 'message': 'Batch data não disponível'}), 404

            return jsonify({
                'status': 'success',
                'ecu_id': record.ecu_id,
                'date': today.isoformat(),
                'power_data': record.power_data,
                'energy_data': record.energy_data
            })
        except Exception as e:
            logger.error(f"Erro ao buscar batch data: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/meter')
    def api_meter():
        """Retorna dados mais recentes do medidor de energia."""
        try:
            repository = Repository()
            credentials = _load_credentials()
            # Medidores usam o mesmo ID da ECU/sistema
            meter_id = credentials['apsystems']['sid']

            record = repository.get_latest_meter_data(meter_id)
            if not record:
                return jsonify({'status': 'no_data', 'message': 'Dados do medidor não disponíveis'}), 404

            return jsonify({
                'status': 'success',
                'meter_id': record.meter_id,
                'timestamp': record.timestamp.isoformat(),
                'today': record.today,
                'month': record.month,
                'year': record.year,
                'lifetime': record.lifetime
            })
        except Exception as e:
            logger.error(f"Erro ao buscar dados do medidor: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/energy/totals')
    def api_energy_totals():
        """Retorna totais de energia: mês, ano e lifetime do sistema."""
        try:
            repository = Repository()
            today = date.today()

            # Somar mês e ano diretamente do inverter_summary (mais recente por inversor)
            summaries = repository.get_all_inverter_summaries()
            month_kwh = 0.0
            year_kwh = 0.0
            for rec in (summaries or []):
                for ch in (rec.channels or {}).values():
                    month_kwh += float(ch.get('month') or 0)
                    year_kwh  += float(ch.get('year')  or 0)

            # Lifetime do registro agregado mais recente (generation_data sem panel_id)
            data = repository.get_generation_data_for_period(today, today)
            aggregate = next(
                (d for d in reversed(data) if d.panel_id is None and d.energy_kwh_total is not None),
                None
            )

            return jsonify({
                'status': 'success',
                'month_kwh': round(month_kwh, 2),
                'year_kwh': round(year_kwh, 2),
                'lifetime_kwh': float(aggregate.energy_kwh_total) if aggregate else 0
            })
        except Exception as e:
            logger.error(f"Erro ao buscar totais de energia: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/inverters/summary')
    def api_inverters_summary():
        """Retorna resumo de energia por inversor e canal."""
        try:
            repository = Repository()
            records = repository.get_all_inverter_summaries()

            if not records:
                return jsonify({'status': 'no_data', 'message': 'Resumo dos inversores não disponível'}), 404

            inverters = []
            for rec in records:
                inverters.append({
                    'inverter_uid': rec.inverter_uid,
                    'channels': rec.channels,
                    'timestamp': rec.timestamp.isoformat()
                })

            return jsonify({
                'status': 'success',
                'inverters': inverters
            })
        except Exception as e:
            logger.error(f"Erro ao buscar resumo dos inversores: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/energy/prev-year-month')
    def api_energy_prev_year_month():
        """Retorna geração do mesmo mês no ano anterior (com cache diário)."""
        try:
            today = date.today()
            prev_year = today.year - 1
            cache_key = f'prev_year_month_{prev_year}_{today.month}'

            # Usar cache se já buscado hoje
            cached = _api_cache.get(cache_key)
            if cached and cached['date'] == today:
                return jsonify({'status': 'success', 'year': prev_year,
                                'month': today.month, 'kwh': cached['value']})

            client = _make_api_client()
            monthly_data = client.get_system_energy('monthly', str(prev_year))

            # API retorna lista de 12 valores mensais (Jan=índice 0)
            idx = today.month - 1
            value = 0.0
            if monthly_data and len(monthly_data) > idx:
                value = float(monthly_data[idx] or 0)

            _api_cache[cache_key] = {'value': value, 'date': today}
            logger.info(f"Energia mês {today.month}/{prev_year}: {value} kWh")

            return jsonify({'status': 'success', 'year': prev_year,
                            'month': today.month, 'kwh': value})
        except Exception as e:
            logger.error(f"Erro ao buscar energia do ano anterior: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/energy/prev-day')
    def api_energy_prev_day():
        """Retorna geração do dia anterior usando a mesma fonte que /api/current
        (MAX de energy_kwh_daily na generation_data com panel_id IS NULL)."""
        try:
            from sqlalchemy import func as _func
            from ..database.models import db as _db, GenerationData as _GD
            yesterday = date.today() - timedelta(days=1)
            session = _db.get_session()
            try:
                result = session.query(_func.max(_GD.energy_kwh_daily)).filter(
                    _func.date(_GD.timestamp) == yesterday.isoformat(),
                    _GD.panel_id.is_(None),
                    _GD.energy_kwh_daily.isnot(None)
                ).scalar()
                kwh = float(result or 0)
            finally:
                session.close()
            return jsonify({'status': 'success', 'date': yesterday.isoformat(), 'kwh': kwh})
        except Exception as e:
            logger.error(f"Erro ao buscar energia do dia anterior: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/collect', methods=['POST'])
    def api_collect():
        """Dispara coleta de dados em background."""
        if _collect_state['running']:
            return jsonify({'status': 'running', 'message': 'Coleta já em andamento'}), 409

        def run_collection():
            _collect_state['running'] = True
            _collect_state['last_result'] = None
            try:
                from ..scheduler.jobs import collect_solar_data
                collect_solar_data()
                _collect_state['last_result'] = 'success'
                logger.info("Coleta manual concluída com sucesso")
            except Exception as e:
                _collect_state['last_result'] = f'error: {str(e)}'
                logger.error(f"Erro na coleta manual: {e}")
            finally:
                _collect_state['running'] = False
                _collect_state['last_run'] = datetime.now()

        thread = threading.Thread(target=run_collection, daemon=True)
        thread.start()

        return jsonify({'status': 'started', 'message': 'Coleta iniciada'})

    @app.route('/api/collect/status')
    def api_collect_status():
        """Retorna o estado atual da coleta."""
        return jsonify({
            'running': _collect_state['running'],
            'last_result': _collect_state['last_result'],
            'last_run': _collect_state['last_run'].isoformat() if _collect_state['last_run'] else None
        })

    # ── Email / Gmail ─────────────────────────────────────────────────────────

    # ── Destinatários de alertas ──────────────────────────────────────────────

    @app.route('/api/email/recipients', methods=['GET'])
    def api_recipients_list():
        """Lista todos os destinatários."""
        try:
            repository = Repository()
            records = repository.get_all_recipients()
            return jsonify({
                'status': 'success',
                'recipients': [{
                    'id': r.id,
                    'name': r.name,
                    'email': r.email,
                    'active': r.active,
                    'receive_alerts': r.receive_alerts,
                    'receive_reports': r.receive_reports,
                    'created_at': r.created_at.strftime('%d/%m/%Y %H:%M')
                } for r in records]
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/recipients', methods=['POST'])
    def api_recipients_add():
        """Cadastra novo destinatário."""
        try:
            data = request.get_json()
            if not data.get('email') or not data.get('name'):
                return jsonify({'status': 'error', 'message': 'Nome e email são obrigatórios'}), 400
            repository = Repository()
            r = repository.save_recipient(data)
            return jsonify({'status': 'success', 'message': 'Destinatário cadastrado',
                            'id': r.id})
        except Exception as e:
            msg = 'Email já cadastrado' if 'UNIQUE' in str(e) else str(e)
            return jsonify({'status': 'error', 'message': msg}), 400

    @app.route('/api/email/recipients/<int:rid>', methods=['PUT'])
    def api_recipients_update(rid):
        """Atualiza destinatário (ativo, preferências)."""
        try:
            data = request.get_json()
            repository = Repository()
            r = repository.update_recipient(rid, data)
            if not r:
                return jsonify({'status': 'error', 'message': 'Destinatário não encontrado'}), 404
            return jsonify({'status': 'success', 'message': 'Atualizado'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/recipients/<int:rid>', methods=['DELETE'])
    def api_recipients_delete(rid):
        """Remove destinatário."""
        try:
            repository = Repository()
            if repository.delete_recipient(rid):
                return jsonify({'status': 'success', 'message': 'Destinatário removido'})
            return jsonify({'status': 'error', 'message': 'Não encontrado'}), 404
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/config', methods=['GET'])
    def api_email_config_get():
        """Retorna configuração de email atual (senha mascarada)."""
        try:
            creds = _load_credentials()
            cfg = creds.get('email', {})
            configured = bool(cfg.get('sender_email') and
                              cfg.get('sender_password') and
                              cfg.get('sender_password') != 'senha_aplicativo_google' and
                              cfg.get('recipient_email'))
            return jsonify({
                'status': 'success',
                'configured': configured,
                'sender_email': cfg.get('sender_email', ''),
                'recipient_email': cfg.get('recipient_email', ''),
                'has_password': bool(cfg.get('sender_password') and
                                     cfg.get('sender_password') != 'senha_aplicativo_google'),
                'smtp_host': cfg.get('smtp_host', 'smtp.gmail.com'),
                'smtp_port': cfg.get('smtp_port', 587)
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/config', methods=['POST'])
    def api_email_config_save():
        """Salva configuração de email em credentials.yaml."""
        try:
            data = request.get_json()
            cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"

            with open(cred_path, 'r', encoding='utf-8') as f:
                creds = yaml.safe_load(f)

            if 'email' not in creds:
                creds['email'] = {}

            creds['email']['sender_email'] = data.get('sender_email', '').strip()
            creds['email']['recipient_email'] = data.get('recipient_email', '').strip()
            creds['email']['smtp_host'] = 'smtp.gmail.com'
            creds['email']['smtp_port'] = 587

            # Só atualiza a senha se foi fornecida
            if data.get('sender_password', '').strip():
                creds['email']['sender_password'] = data['sender_password'].strip()

            with open(cred_path, 'w', encoding='utf-8') as f:
                yaml.dump(creds, f, allow_unicode=True, default_flow_style=False)

            logger.info("Configuração de email atualizada")
            return jsonify({'status': 'success', 'message': 'Configuração salva com sucesso'})
        except Exception as e:
            logger.error(f"Erro ao salvar config de email: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/test', methods=['POST'])
    def api_email_test():
        """Envia email de teste."""
        try:
            from ..alerts.email_sender import EmailSender
            sender = EmailSender()

            subject = "✅ Teste — Sistema de Monitoramento Solar"
            body = f"""
            <!DOCTYPE html><html><body style="font-family:Arial,sans-serif;color:#333">
            <div style="max-width:520px;margin:0 auto;padding:24px">
              <div style="background:#28a745;color:white;padding:20px;border-radius:8px 8px 0 0">
                <h2 style="margin:0">☀️ Monitoramento Solar</h2>
                <p style="margin:4px 0 0">Email de teste</p>
              </div>
              <div style="background:#f8f9fa;padding:20px;border-radius:0 0 8px 8px">
                <p>Integração com Gmail configurada e funcionando corretamente.</p>
                <p style="color:#6c757d;font-size:12px">
                  Enviado em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}
                </p>
              </div>
            </div></body></html>
            """
            success = sender.send_email(subject, body, html=True, email_type='test')
            if success:
                return jsonify({'status': 'success', 'message': 'Email de teste enviado com sucesso'})
            else:
                return jsonify({'status': 'error', 'message': 'Falha ao enviar email'}), 500
        except Exception as e:
            logger.error(f"Erro ao enviar email de teste: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/insights')
    def api_insights():
        """Roda todas as análises e retorna relatório de insights do sistema."""
        try:
            from ..analysis.insights import generate_insights
            result = generate_insights()
            return jsonify(result)
        except Exception as e:
            logger.error(f"Erro ao gerar insights: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/log', methods=['GET'])
    def api_email_log():
        """Retorna o histórico de envios de email."""
        try:
            limit      = min(int(request.args.get('limit', 100)), 500)
            email_type = request.args.get('type')
            logs = Repository.get_email_logs(limit=limit, email_type=email_type or None)
            TYPE_LABELS = {
                'alert':           'Alerta',
                'daily_report':    'Relatório Diário',
                'evening_summary': 'Resumo Vespertino',
                'test':            'Teste',
                'unknown':         '—',
            }
            result = []
            for entry in logs:
                result.append({
                    'id':              entry.id,
                    'sent_at':         entry.sent_at.strftime('%d/%m/%Y %H:%M:%S') if entry.sent_at else '',
                    'email_type':      entry.email_type,
                    'type_label':      TYPE_LABELS.get(entry.email_type, entry.email_type),
                    'subject':         entry.subject,
                    'recipients':      entry.recipients or [],
                    'recipient_count': entry.recipient_count or 0,
                    'success':         entry.success,
                    'error_message':   entry.error_message,
                })
            return jsonify({'status': 'success', 'logs': result, 'total': len(result)})
        except Exception as e:
            logger.error(f"Erro ao buscar log de emails: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/email/report', methods=['POST'])
    def api_email_report():
        """Envia relatório diário por email."""
        try:
            from ..alerts.alert_manager import AlertManager
            from ..analysis.statistics import StatisticsCalculator

            today = date.today()
            calculator = StatisticsCalculator()
            stats = calculator.calculate_daily_stats(today)

            # Complementar com dados de mês/ano do inverter_summary
            repository = Repository()
            summaries = repository.get_all_inverter_summaries()
            month_kwh = sum(float(ch.get('month') or 0)
                            for rec in (summaries or [])
                            for ch in (rec.channels or {}).values())
            year_kwh = sum(float(ch.get('year') or 0)
                           for rec in (summaries or [])
                           for ch in (rec.channels or {}).values())

            if not stats:
                stats = {'date': today.isoformat(), 'total_generation_kwh': 0,
                         'peak_power_watts': 0, 'average_power_watts': 0}

            stats['month_kwh'] = round(month_kwh, 2)
            stats['year_kwh'] = round(year_kwh, 2)

            alert_manager = AlertManager()
            success = alert_manager.send_daily_report(stats)

            if success:
                return jsonify({'status': 'success', 'message': 'Relatório diário enviado'})
            else:
                return jsonify({'status': 'error', 'message': 'Falha ao enviar relatório'}), 500
        except Exception as e:
            logger.error(f"Erro ao enviar relatório: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
