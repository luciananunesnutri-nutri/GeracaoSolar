from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .email_sender import EmailSender
from ..database.repository import Repository
from ..utils.logger import logger


class AlertManager:
    """Gerenciador de alertas do sistema."""

    def __init__(self):
        self.email_sender = EmailSender()
        self.repository = Repository()
        self.debounce_window = timedelta(minutes=30)  # Evitar alertas duplicados em 30 min

    def process_alert(self, alert_data: Dict) -> bool:
        """
        Processa e armazena um alerta.

        Args:
            alert_data: Dicionário com dados do alerta

        Returns:
            True se processado com sucesso
        """
        try:
            # Verificar se já existe alerta similar recente (debouncing)
            if self._is_duplicate_alert(alert_data):
                logger.debug(f"Alerta duplicado ignorado: {alert_data['alert_type']}")
                return False

            # Salvar alerta no banco (email enviado apenas nos horários programados)
            alert = self.repository.save_alert(alert_data)

            return True

        except Exception as e:
            logger.error(f"Erro ao processar alerta: {e}")
            return False

    def send_alert_notifications(self, alert: Dict) -> bool:
        """
        Envia notificações de alerta.

        Args:
            alert: Dicionário com dados do alerta

        Returns:
            True se enviado com sucesso
        """
        try:
            # Enviar email
            success = self.email_sender.send_alert_email(alert)

            if success:
                logger.info(f"Notificação de alerta enviada: {alert['message']}")
            else:
                logger.warning(f"Falha ao enviar notificação de alerta: {alert['message']}")

            return success

        except Exception as e:
            logger.error(f"Erro ao enviar notificações: {e}")
            return False

    def get_active_alerts(self) -> List[Dict]:
        """
        Retorna alertas ativos (não resolvidos).

        Returns:
            Lista de alertas ativos
        """
        try:
            alerts = self.repository.get_recent_alerts(limit=100, unresolved_only=True)
            return [self._alert_to_dict(a) for a in alerts]
        except Exception as e:
            logger.error(f"Erro ao buscar alertas ativos: {e}")
            return []

    def resolve_alert(self, alert_id: int) -> bool:
        """
        Marca um alerta como resolvido.

        Args:
            alert_id: ID do alerta

        Returns:
            True se resolvido com sucesso
        """
        try:
            success = self.repository.resolve_alert(alert_id)
            if success:
                logger.info(f"Alerta {alert_id} resolvido")
            return success
        except Exception as e:
            logger.error(f"Erro ao resolver alerta {alert_id}: {e}")
            return False

    def _is_duplicate_alert(self, alert_data: Dict) -> bool:
        """
        Verifica se já existe alerta similar recente.

        Args:
            alert_data: Dados do novo alerta

        Returns:
            True se é duplicado
        """
        try:
            # Buscar alertas recentes do mesmo tipo
            recent_alerts = self.repository.get_recent_alerts(limit=50, unresolved_only=True)

            cutoff_time = datetime.now() - self.debounce_window
            alert_type = alert_data['alert_type']

            for alert in recent_alerts:
                # Verificar tipo e tempo
                if (alert.alert_type.value == alert_type and
                    alert.timestamp > cutoff_time):
                    return True

            return False

        except Exception as e:
            logger.error(f"Erro ao verificar alerta duplicado: {e}")
            return False

    def _alert_to_dict(self, alert) -> Dict:
        """
        Converte objeto Alert para dicionário.

        Args:
            alert: Objeto Alert

        Returns:
            Dicionário
        """
        return {
            'id': alert.id,
            'timestamp': alert.timestamp.isoformat(),
            'alert_type': alert.alert_type.value,
            'severity': alert.severity.value,
            'message': alert.message,
            'details': alert.details,
            'resolved': alert.resolved,
            'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None
        }

    def send_daily_report(self, stats: Dict) -> bool:
        """
        Envia relatório diário.

        Args:
            stats: Estatísticas do dia

        Returns:
            True se enviado com sucesso
        """
        try:
            success = self.email_sender.send_daily_report_email(stats)
            if success:
                logger.info(f"Relatório diário enviado: {stats['date']}")
            return success
        except Exception as e:
            logger.error(f"Erro ao enviar relatório diário: {e}")
            return False

    def process_multiple_alerts(self, alerts: List[Dict]) -> int:
        """
        Processa múltiplos alertas.

        Args:
            alerts: Lista de alertas

        Returns:
            Número de alertas processados
        """
        count = 0
        for alert in alerts:
            if self.process_alert(alert):
                count += 1
        return count
