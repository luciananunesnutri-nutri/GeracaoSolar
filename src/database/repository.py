from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from sqlalchemy import func, and_
from .models import (
    db, GenerationData, Statistics, Alert, SystemStatusModel,
    EcuTelemetry, InverterBatchData, MeterData, InverterSummary,
    AlertRecipient, EmailLog, PeriodType, AlertType, Severity, SystemStatus
)
from ..utils.logger import logger


class Repository:
    """Repositório para operações de banco de dados."""

    @staticmethod
    def save_generation_data(data: Dict) -> GenerationData:
        """
        Salva dados de geração.

        Args:
            data: Dicionário com dados de geração

        Returns:
            Objeto GenerationData criado
        """
        session = db.get_session()
        try:
            gen_data = GenerationData(
                timestamp=data['timestamp'],
                ecu_id=data['ecu_id'],
                panel_id=data.get('panel_id'),
                power_watts=data['power_watts'],
                energy_kwh_daily=data.get('energy_kwh_daily'),
                energy_kwh_total=data.get('energy_kwh_total')
            )
            session.add(gen_data)
            session.commit()
            logger.info(f"Dados de geração salvos: {gen_data}")
            return gen_data
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar dados de geração: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_daily_stats(target_date: date) -> Optional[Statistics]:
        """
        Obtém estatísticas diárias.

        Args:
            target_date: Data alvo

        Returns:
            Objeto Statistics ou None
        """
        session = db.get_session()
        try:
            stats = session.query(Statistics).filter(
                and_(
                    Statistics.date == target_date,
                    Statistics.period_type == PeriodType.DAILY
                )
            ).first()
            return stats
        finally:
            session.close()

    @staticmethod
    def get_monthly_stats(year: int, month: int) -> Optional[Statistics]:
        """
        Obtém estatísticas mensais.

        Args:
            year: Ano
            month: Mês

        Returns:
            Objeto Statistics ou None
        """
        session = db.get_session()
        try:
            target_date = date(year, month, 1)
            stats = session.query(Statistics).filter(
                and_(
                    Statistics.date == target_date,
                    Statistics.period_type == PeriodType.MONTHLY
                )
            ).first()
            return stats
        finally:
            session.close()

    @staticmethod
    def get_yearly_stats(year: int) -> Optional[Statistics]:
        """
        Obtém estatísticas anuais.

        Args:
            year: Ano

        Returns:
            Objeto Statistics ou None
        """
        session = db.get_session()
        try:
            target_date = date(year, 1, 1)
            stats = session.query(Statistics).filter(
                and_(
                    Statistics.date == target_date,
                    Statistics.period_type == PeriodType.YEARLY
                )
            ).first()
            return stats
        finally:
            session.close()

    @staticmethod
    def get_panel_performance(panel_id: str, start_date: date, end_date: date) -> List[GenerationData]:
        """
        Obtém performance de um painel específico.

        Args:
            panel_id: ID do painel
            start_date: Data inicial
            end_date: Data final

        Returns:
            Lista de dados de geração
        """
        session = db.get_session()
        try:
            data = session.query(GenerationData).filter(
                and_(
                    GenerationData.panel_id == panel_id,
                    GenerationData.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    GenerationData.timestamp <= datetime.combine(end_date, datetime.max.time())
                )
            ).order_by(GenerationData.timestamp).all()
            return data
        finally:
            session.close()

    @staticmethod
    def save_alert(alert_data: Dict) -> Alert:
        """
        Salva um alerta.

        Args:
            alert_data: Dicionário com dados do alerta

        Returns:
            Objeto Alert criado
        """
        session = db.get_session()
        try:
            alert = Alert(
                alert_type=AlertType[alert_data['alert_type'].upper()],
                severity=Severity[alert_data['severity'].upper()],
                message=alert_data['message'],
                details=alert_data.get('details', {})
            )
            session.add(alert)
            session.commit()
            logger.warning(f"Alerta criado: {alert.message}")
            return alert
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar alerta: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_dates_with_data() -> List[date]:
        """Retorna lista de datas (desc) que possuem dados de geração ou telemetria."""
        session = db.get_session()
        try:
            telemetry_dates = {
                r.date for r in session.query(EcuTelemetry.date).distinct().all()
            }
            hourly_rows = session.query(
                func.date(GenerationData.timestamp).label('d')
            ).filter(GenerationData.panel_id == 'hourly').distinct().all()
            hourly_dates = set()
            for r in hourly_rows:
                try:
                    hourly_dates.add(date.fromisoformat(str(r.d)))
                except Exception:
                    pass
            return sorted(telemetry_dates | hourly_dates, reverse=True)
        finally:
            session.close()

    @staticmethod
    def get_todays_alerts(unresolved_only: bool = False) -> List[Alert]:
        """Retorna alertas gerados hoje."""
        session = db.get_session()
        try:
            today = date.today()
            q = session.query(Alert).filter(
                Alert.timestamp >= datetime.combine(today, datetime.min.time())
            )
            if unresolved_only:
                q = q.filter(Alert.resolved == False)
            return q.order_by(Alert.timestamp.desc()).all()
        finally:
            session.close()

    @staticmethod
    def get_recent_alerts(limit: int = 50, unresolved_only: bool = False) -> List[Alert]:
        """
        Obtém alertas recentes.

        Args:
            limit: Número máximo de alertas
            unresolved_only: Se True, retorna apenas alertas não resolvidos

        Returns:
            Lista de alertas
        """
        session = db.get_session()
        try:
            query = session.query(Alert)
            if unresolved_only:
                query = query.filter(Alert.resolved == False)
            alerts = query.order_by(Alert.timestamp.desc()).limit(limit).all()
            return alerts
        finally:
            session.close()

    @staticmethod
    def update_system_status(status_data: Dict) -> SystemStatusModel:
        """
        Atualiza status do sistema.

        Args:
            status_data: Dicionário com dados de status

        Returns:
            Objeto SystemStatusModel criado
        """
        session = db.get_session()
        try:
            status = SystemStatusModel(
                ecu_id=status_data['ecu_id'],
                status=SystemStatus[status_data['status'].upper()],
                last_communication=status_data['last_communication'],
                alarm_count=status_data.get('alarm_count', 0)
            )
            session.add(status)
            session.commit()
            logger.info(f"Status do sistema atualizado: {status}")
            return status
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao atualizar status: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def save_statistics(stats_data: Dict) -> Statistics:
        """
        Salva estatísticas.

        Args:
            stats_data: Dicionário com dados estatísticos

        Returns:
            Objeto Statistics criado
        """
        session = db.get_session()
        try:
            stats = Statistics(
                date=stats_data['date'],
                period_type=PeriodType[stats_data['period_type'].upper()],
                total_generation_kwh=stats_data['total_generation_kwh'],
                peak_power_watts=stats_data['peak_power_watts'],
                average_power_watts=stats_data['average_power_watts'],
                panel_stats=stats_data.get('panel_stats')
            )
            session.add(stats)
            session.commit()
            logger.info(f"Estatísticas salvas: {stats}")
            return stats
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar estatísticas: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_generation_data_for_period(start_date: date, end_date: date) -> List[GenerationData]:
        """
        Obtém dados de geração para um período.

        Args:
            start_date: Data inicial
            end_date: Data final

        Returns:
            Lista de dados de geração
        """
        session = db.get_session()
        try:
            data = session.query(GenerationData).filter(
                and_(
                    GenerationData.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    GenerationData.timestamp <= datetime.combine(end_date, datetime.max.time())
                )
            ).order_by(GenerationData.timestamp).all()
            return data
        finally:
            session.close()

    @staticmethod
    def get_latest_system_status(ecu_id: str) -> Optional[SystemStatusModel]:
        """
        Obtém o status mais recente do sistema.

        Args:
            ecu_id: ID da ECU

        Returns:
            Objeto SystemStatusModel ou None
        """
        session = db.get_session()
        try:
            status = session.query(SystemStatusModel).filter(
                SystemStatusModel.ecu_id == ecu_id
            ).order_by(SystemStatusModel.timestamp.desc()).first()
            return status
        finally:
            session.close()

    @staticmethod
    def resolve_alert(alert_id: int) -> bool:
        """
        Marca um alerta como resolvido.

        Args:
            alert_id: ID do alerta

        Returns:
            True se resolvido com sucesso
        """
        session = db.get_session()
        try:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                session.commit()
                logger.info(f"Alerta {alert_id} marcado como resolvido")
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao resolver alerta {alert_id}: {e}")
            raise
        finally:
            session.close()

    # ── ECU Telemetry ─────────────────────────────────────────────────────────

    @staticmethod
    def save_ecu_telemetry(data: Dict) -> EcuTelemetry:
        """Upsert de telemetria minutely por ECU (uma linha por dia por ECU)."""
        session = db.get_session()
        try:
            record = session.query(EcuTelemetry).filter(
                and_(EcuTelemetry.date == data['date'], EcuTelemetry.ecu_id == data['ecu_id'])
            ).first()
            if record:
                record.time_series = data['time_series']
                record.updated_at = datetime.now()
            else:
                record = EcuTelemetry(
                    date=data['date'],
                    ecu_id=data['ecu_id'],
                    time_series=data['time_series']
                )
                session.add(record)
            session.commit()
            logger.info(f"ECU telemetry salva: {data['ecu_id']} {data['date']}")
            return record
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar ECU telemetry: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_ecu_telemetry(ecu_id: str, target_date: date) -> Optional[EcuTelemetry]:
        """Busca telemetria minutely de uma ECU para uma data."""
        session = db.get_session()
        try:
            return session.query(EcuTelemetry).filter(
                and_(EcuTelemetry.ecu_id == ecu_id, EcuTelemetry.date == target_date)
            ).first()
        finally:
            session.close()

    @staticmethod
    def get_latest_ecu_telemetry_for_date(target_date: date) -> Optional[EcuTelemetry]:
        """Busca o registro mais recente de telemetria ECU para uma data (qualquer ECU)."""
        session = db.get_session()
        try:
            return session.query(EcuTelemetry).filter(
                EcuTelemetry.date == target_date
            ).order_by(EcuTelemetry.updated_at.desc()).first()
        finally:
            session.close()

    # ── Inverter Batch Data ───────────────────────────────────────────────────

    @staticmethod
    def save_inverter_batch_data(data: Dict) -> InverterBatchData:
        """Upsert de batch data por ECU (uma linha por dia por ECU)."""
        session = db.get_session()
        try:
            record = session.query(InverterBatchData).filter(
                and_(InverterBatchData.date == data['date'], InverterBatchData.ecu_id == data['ecu_id'])
            ).first()
            if record:
                if data.get('power_data') is not None:
                    record.power_data = data['power_data']
                if data.get('energy_data') is not None:
                    record.energy_data = data['energy_data']
                record.updated_at = datetime.now()
            else:
                record = InverterBatchData(
                    date=data['date'],
                    ecu_id=data['ecu_id'],
                    power_data=data.get('power_data'),
                    energy_data=data.get('energy_data')
                )
                session.add(record)
            session.commit()
            logger.info(f"Inverter batch data salva: {data['ecu_id']} {data['date']}")
            return record
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar inverter batch data: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_inverter_batch_data(ecu_id: str, target_date: date) -> Optional[InverterBatchData]:
        """Busca batch data de inversores de uma ECU para uma data."""
        session = db.get_session()
        try:
            return session.query(InverterBatchData).filter(
                and_(InverterBatchData.ecu_id == ecu_id, InverterBatchData.date == target_date)
            ).first()
        finally:
            session.close()

    # ── Alert Recipients ──────────────────────────────────────────────────────

    @staticmethod
    def get_all_recipients() -> List[AlertRecipient]:
        """Retorna todos os destinatários cadastrados."""
        session = db.get_session()
        try:
            return session.query(AlertRecipient).order_by(AlertRecipient.created_at).all()
        finally:
            session.close()

    @staticmethod
    def get_active_recipients(alerts_only: bool = False, reports_only: bool = False) -> List[AlertRecipient]:
        """Retorna destinatários ativos, com filtro opcional por tipo."""
        session = db.get_session()
        try:
            q = session.query(AlertRecipient).filter(AlertRecipient.active == True)
            if alerts_only:
                q = q.filter(AlertRecipient.receive_alerts == True)
            if reports_only:
                q = q.filter(AlertRecipient.receive_reports == True)
            return q.order_by(AlertRecipient.created_at).all()
        finally:
            session.close()

    @staticmethod
    def save_recipient(data: Dict) -> AlertRecipient:
        """Cadastra um novo destinatário."""
        session = db.get_session()
        try:
            recipient = AlertRecipient(
                name=data['name'],
                email=data['email'].strip().lower(),
                active=data.get('active', True),
                receive_alerts=data.get('receive_alerts', True),
                receive_reports=data.get('receive_reports', True),
            )
            session.add(recipient)
            session.commit()
            logger.info(f"Destinatário cadastrado: {recipient.email}")
            return recipient
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao cadastrar destinatário: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def update_recipient(recipient_id: int, data: Dict) -> Optional[AlertRecipient]:
        """Atualiza um destinatário existente."""
        session = db.get_session()
        try:
            recipient = session.query(AlertRecipient).filter(AlertRecipient.id == recipient_id).first()
            if not recipient:
                return None
            if 'name' in data:
                recipient.name = data['name']
            if 'email' in data:
                recipient.email = data['email'].strip().lower()
            if 'active' in data:
                recipient.active = data['active']
            if 'receive_alerts' in data:
                recipient.receive_alerts = data['receive_alerts']
            if 'receive_reports' in data:
                recipient.receive_reports = data['receive_reports']
            session.commit()
            logger.info(f"Destinatário {recipient_id} atualizado")
            return recipient
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao atualizar destinatário: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def delete_recipient(recipient_id: int) -> bool:
        """Remove um destinatário."""
        session = db.get_session()
        try:
            recipient = session.query(AlertRecipient).filter(AlertRecipient.id == recipient_id).first()
            if not recipient:
                return False
            session.delete(recipient)
            session.commit()
            logger.info(f"Destinatário {recipient_id} removido")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao remover destinatário: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_latest_inverter_batch_for_date(target_date: date) -> Optional[InverterBatchData]:
        """Busca o registro mais recente de batch data para uma data (qualquer ECU)."""
        session = db.get_session()
        try:
            return session.query(InverterBatchData).filter(
                InverterBatchData.date == target_date
            ).order_by(InverterBatchData.updated_at.desc()).first()
        finally:
            session.close()

    # ── Meter Data ────────────────────────────────────────────────────────────

    @staticmethod
    def save_meter_data(data: Dict) -> MeterData:
        """Salva dados do medidor de energia."""
        session = db.get_session()
        try:
            record = MeterData(
                meter_id=data['meter_id'],
                today=data.get('today'),
                month=data.get('month'),
                year=data.get('year'),
                lifetime=data.get('lifetime')
            )
            session.add(record)
            session.commit()
            logger.info(f"Meter data salva: {data['meter_id']}")
            return record
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar meter data: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_latest_meter_data(meter_id: str) -> Optional[MeterData]:
        """Busca os dados mais recentes do medidor."""
        session = db.get_session()
        try:
            return session.query(MeterData).filter(
                MeterData.meter_id == meter_id
            ).order_by(MeterData.timestamp.desc()).first()
        finally:
            session.close()

    # ── Inverter Summary ──────────────────────────────────────────────────────

    @staticmethod
    def save_inverter_summary(data: Dict) -> InverterSummary:
        """Salva resumo de energia por inversor e canal."""
        session = db.get_session()
        try:
            record = InverterSummary(
                inverter_uid=data['inverter_uid'],
                channels=data.get('channels')
            )
            session.add(record)
            session.commit()
            logger.info(f"Inverter summary salva: {data['inverter_uid']}")
            return record
        except Exception as e:
            session.rollback()
            logger.error(f"Erro ao salvar inverter summary: {e}")
            raise
        finally:
            session.close()

    @staticmethod
    def get_all_inverter_summaries_for_date(target_date: date) -> List[InverterSummary]:
        """Busca o último registro de summary por inversor gravado em uma data específica."""
        session = db.get_session()
        try:
            from sqlalchemy import func as sqlfunc
            day_start = datetime.combine(target_date, datetime.min.time())
            day_end   = datetime.combine(target_date, datetime.max.time())

            subq = session.query(
                InverterSummary.inverter_uid,
                sqlfunc.max(InverterSummary.timestamp).label('max_ts')
            ).filter(
                InverterSummary.timestamp >= day_start,
                InverterSummary.timestamp <= day_end
            ).group_by(InverterSummary.inverter_uid).subquery()

            return session.query(InverterSummary).join(
                subq,
                and_(
                    InverterSummary.inverter_uid == subq.c.inverter_uid,
                    InverterSummary.timestamp == subq.c.max_ts
                )
            ).all()
        finally:
            session.close()

    @staticmethod
    def get_latest_inverter_summary(inverter_uid: str) -> Optional[InverterSummary]:
        """Busca o resumo mais recente de um inversor."""
        session = db.get_session()
        try:
            return session.query(InverterSummary).filter(
                InverterSummary.inverter_uid == inverter_uid
            ).order_by(InverterSummary.timestamp.desc()).first()
        finally:
            session.close()

    @staticmethod
    def get_all_inverter_summaries() -> List[InverterSummary]:
        """Busca o resumo mais recente de todos os inversores."""
        session = db.get_session()
        try:
            from sqlalchemy import func as sqlfunc
            subq = session.query(
                InverterSummary.inverter_uid,
                sqlfunc.max(InverterSummary.timestamp).label('max_ts')
            ).group_by(InverterSummary.inverter_uid).subquery()

            return session.query(InverterSummary).join(
                subq,
                and_(
                    InverterSummary.inverter_uid == subq.c.inverter_uid,
                    InverterSummary.timestamp == subq.c.max_ts
                )
            ).all()
        finally:
            session.close()

    @staticmethod
    def save_email_log(data: Dict) -> EmailLog:
        """Registra um envio de email no histórico."""
        session = db.get_session()
        try:
            entry = EmailLog(
                email_type=data.get('email_type', 'unknown'),
                subject=data.get('subject', ''),
                recipients=data.get('recipients', []),
                recipient_count=data.get('recipient_count', 0),
                success=bool(data.get('success', False)),
                error_message=data.get('error_message'),
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry
        finally:
            session.close()

    @staticmethod
    def get_email_logs(limit: int = 100, email_type: str = None) -> List[EmailLog]:
        """Retorna o histórico de envios de email, do mais recente ao mais antigo."""
        session = db.get_session()
        try:
            q = session.query(EmailLog)
            if email_type:
                q = q.filter(EmailLog.email_type == email_type)
            return q.order_by(EmailLog.sent_at.desc()).limit(limit).all()
        finally:
            session.close()
