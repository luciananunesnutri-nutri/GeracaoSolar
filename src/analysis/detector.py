from datetime import datetime, timedelta, date
from typing import Optional, Dict, List, Any
import yaml
from pathlib import Path
from ..database.repository import Repository
from ..utils.logger import logger


class AnomalyDetector:
    """Detector de anomalias na geração solar."""

    def __init__(self):
        # Carregar regras de alertas
        rules_path = Path(__file__).parent.parent.parent / "config" / "alerts_rules.yaml"
        with open(rules_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        self.rules = config['alerts']
        self.repository = Repository()

    def detect_peak_generation(self, current_power: float, max_capacity: float) -> Optional[Dict]:
        """
        Detecta pico de geração (>80% da capacidade).

        Args:
            current_power: Potência atual em watts
            max_capacity: Capacidade máxima em watts

        Returns:
            Dicionário com alerta ou None
        """
        if not self.rules['peak_generation']['enabled']:
            return None

        threshold = self.rules['peak_generation']['threshold_percent'] / 100
        capacity_threshold = max_capacity * threshold

        if current_power >= capacity_threshold:
            percentage = (current_power / max_capacity) * 100
            logger.info(f"Pico de geração detectado: {current_power}W ({percentage:.1f}% da capacidade)")

            return {
                'alert_type': 'peak',
                'severity': self.rules['peak_generation']['severity'],
                'message': f"Pico de geração: {current_power}W ({percentage:.1f}% da capacidade máxima)",
                'details': {
                    'current_power': current_power,
                    'max_capacity': max_capacity,
                    'percentage': percentage
                }
            }

        return None

    def detect_zero_generation(self, timestamp: datetime, power: float) -> Optional[Dict]:
        """
        Detecta geração zero durante o dia (8h-17h).

        Args:
            timestamp: Timestamp da leitura
            power: Potência em watts

        Returns:
            Dicionário com alerta ou None
        """
        if not self.rules['zero_generation']['enabled']:
            return None

        # Verificar se está no horário de luz do dia
        hour = timestamp.hour
        daylight_hours = self.rules['zero_generation']['daylight_hours']

        if hour in daylight_hours and power == 0:
            logger.warning(f"Geração zero detectada durante o dia às {timestamp}")

            return {
                'alert_type': 'low_generation',
                'severity': self.rules['zero_generation']['severity'],
                'message': f"Sistema com geração zero durante o dia ({hour}h)",
                'details': {
                    'timestamp': timestamp.isoformat(),
                    'hour': hour,
                    'power': power
                }
            }

        return None

    def detect_power_drop(self, current_power: float, timestamp: datetime) -> Optional[Dict]:
        """
        Detecta queda de potência >50% comparado com média histórica.

        Args:
            current_power: Potência atual em watts
            timestamp: Timestamp da leitura

        Returns:
            Dicionário com alerta ou None
        """
        if not self.rules['power_drop']['enabled']:
            return None

        # Obter média histórica para a mesma hora
        window_days = self.rules['power_drop']['comparison_window_days']
        historical_avg = self._get_historical_average(timestamp, window_days)

        if historical_avg is None or historical_avg == 0:
            # Sem dados históricos suficientes
            return None

        threshold = self.rules['power_drop']['threshold_percent'] / 100
        drop_threshold = historical_avg * (1 - threshold)

        if current_power < drop_threshold:
            drop_percentage = ((historical_avg - current_power) / historical_avg) * 100
            logger.warning(f"Queda de potência detectada: {current_power}W vs {historical_avg}W média ({drop_percentage:.1f}%)")

            return {
                'alert_type': 'low_generation',
                'severity': self.rules['power_drop']['severity'],
                'message': f"Queda de {drop_percentage:.1f}% na geração: {current_power}W vs {historical_avg:.1f}W média",
                'details': {
                    'current_power': current_power,
                    'historical_average': historical_avg,
                    'drop_percentage': drop_percentage,
                    'timestamp': timestamp.isoformat()
                }
            }

        return None

    def detect_offline_system(self, last_communication: datetime) -> Optional[Dict]:
        """
        Detecta sistema offline (sem comunicação por mais de X minutos).

        Args:
            last_communication: Último timestamp de comunicação

        Returns:
            Dicionário com alerta ou None
        """
        if not self.rules['system_offline']['enabled']:
            return None

        timeout_minutes = self.rules['system_offline']['timeout_minutes']
        threshold_time = datetime.now() - timedelta(minutes=timeout_minutes)

        if last_communication < threshold_time:
            offline_minutes = (datetime.now() - last_communication).total_seconds() / 60
            logger.error(f"Sistema offline há {offline_minutes:.0f} minutos")

            return {
                'alert_type': 'offline',
                'severity': self.rules['system_offline']['severity'],
                'message': f"Sistema offline há {offline_minutes:.0f} minutos",
                'details': {
                    'last_communication': last_communication.isoformat(),
                    'offline_minutes': offline_minutes
                }
            }

        return None

    def check_system_alarms(self, alarm_data: Dict) -> List[Dict]:
        """
        Processa alarmes do hardware.

        Args:
            alarm_data: Dados de alarmes da API

        Returns:
            Lista de alertas gerados
        """
        if not self.rules['hardware_alarms']['enabled']:
            return []

        alerts = []
        alarms = alarm_data.get('alarms', [])

        for alarm in alarms:
            logger.warning(f"Alarme do hardware detectado: {alarm}")

            alerts.append({
                'alert_type': 'alarm',
                'severity': self.rules['hardware_alarms']['severity'],
                'message': f"Alarme do hardware: {alarm.get('message', 'Sem descrição')}",
                'details': alarm
            })

        return alerts

    def detect_ecu_alarms(self, inverters_data: List) -> List[Dict]:
        """
        Detecta alarmes de hardware reportados pelas ECUs.

        Args:
            inverters_data: Lista de ECUs retornada por get_system_inverters()

        Returns:
            Lista de alertas gerados
        """
        if not self.rules.get('ecu_alarm', {}).get('enabled', True):
            return []

        alerts = []
        severity = self.rules.get('ecu_alarm', {}).get('severity', 'critical')

        for ecu in (inverters_data or []):
            alarm_count = int(ecu.get('alarm', 0) or 0)
            ecu_id = ecu.get('eid', 'desconhecida')
            if alarm_count > 0:
                logger.warning(f"ECU {ecu_id}: {alarm_count} alarme(s) de hardware")
                alerts.append({
                    'alert_type': 'ecu_alarm',
                    'severity': severity,
                    'message': f"ECU {ecu_id} reportou {alarm_count} alarme(s) de hardware",
                    'details': {
                        'ecu_id': ecu_id,
                        'alarm_count': alarm_count,
                    }
                })
        return alerts

    def detect_inverter_channel_faults(self, inverter_summaries: Dict, system_today_kwh: float) -> List[Dict]:
        """
        Detecta canais com energia zero hoje que geraram no dia anterior.
        Só alerta se o canal tinha geração ontem E hoje está zerado — evita falsos
        positivos em canais sem painel ou sem histórico.

        Args:
            inverter_summaries: {uid: {d1, m1, y1, t1, d2, m2, ...}} da API (hoje)
            system_today_kwh: Energia total gerada pelo sistema hoje (kWh)

        Returns:
            Lista de alertas gerados
        """
        rule = self.rules.get('inverter_fault', {})
        if not rule.get('enabled', True):
            return []

        min_kwh = float(rule.get('min_system_kwh', 0.3))
        severity = rule.get('severity', 'warning')

        # Só verifica se o sistema está efetivamente gerando hoje
        if system_today_kwh < min_kwh:
            return []

        # Buscar summaries de ontem para comparação
        yesterday_channels = {}  # {uid: {ch_num: today_kwh}}
        try:
            yesterday = (datetime.now() - timedelta(days=1)).date()
            yesterday_records = self.repository.get_all_inverter_summaries_for_date(yesterday)
            for rec in yesterday_records:
                ch_map = {}
                for ch_num, ch_data in (rec.channels or {}).items():
                    val = ch_data.get('today') if isinstance(ch_data, dict) else None
                    ch_map[int(ch_num)] = float(val) if val is not None else 0.0
                yesterday_channels[rec.inverter_uid] = ch_map
        except Exception as e:
            logger.warning(f"Não foi possível carregar summaries de ontem: {e}")
            return []  # Sem histórico, não alertar

        alerts = []
        for uid, summary in (inverter_summaries or {}).items():
            yesterday_uid = yesterday_channels.get(uid, {})

            # Se não há dados de ontem para este inversor, não há base de comparação
            if not yesterday_uid:
                continue

            faulty_channels = []
            active_channels = {}

            for ch in range(1, 5):
                d_today = summary.get(f'd{ch}')
                if d_today is None:
                    continue
                d_today_val = float(d_today)
                d_yesterday_val = yesterday_uid.get(ch, 0.0)

                if d_today_val == 0.0 and d_yesterday_val > 0.0:
                    # Canal zerou hoje mas gerou ontem → falha real
                    faulty_channels.append({'ch': ch, 'yesterday_kwh': d_yesterday_val})
                elif d_today_val > 0.0:
                    active_channels[ch] = d_today_val

            if faulty_channels:
                ch_nums = [f['ch'] for f in faulty_channels]
                ch_detail = {f['ch']: f['yesterday_kwh'] for f in faulty_channels}
                logger.warning(f"Inversor {uid}: canais {ch_nums} com zero hoje "
                               f"(geraram ontem: {ch_detail})")
                alerts.append({
                    'alert_type': 'inverter_fault',
                    'severity': severity,
                    'message': (f"Microinversor {uid}: canal(s) {ch_nums} sem geração hoje "
                                f"(ontem geraram {', '.join(f'{v:.2f} kWh' for v in ch_detail.values())})"),
                    'details': {
                        'inverter_uid': uid,
                        'faulty_channels': ch_nums,
                        'yesterday_kwh_per_channel': ch_detail,
                        'active_channels': active_channels,
                        'system_today_kwh': system_today_kwh,
                    }
                })
        return alerts

    def detect_low_generation_daylight(self, today_kwh: float, timestamp: datetime) -> Optional[Dict]:
        """
        Detecta geração zero após as 11h — possível sistema offline ou falha total.

        Args:
            today_kwh: Energia gerada hoje (kWh) conforme resumo da API
            timestamp: Timestamp da coleta

        Returns:
            Dicionário com alerta ou None
        """
        rule = self.rules.get('low_generation_daylight', {})
        if not rule.get('enabled', True):
            return None

        hour = timestamp.hour
        min_hour = int(rule.get('min_hour', 11))
        severity = rule.get('severity', 'critical')

        if hour < min_hour:
            return None

        if today_kwh == 0.0:
            logger.error(f"Sistema sem geração (0.00 kWh) às {hour}h")
            return {
                'alert_type': 'offline',
                'severity': severity,
                'message': f"Sistema sem geração às {hour}h — possível falha ou offline",
                'details': {
                    'today_kwh': today_kwh,
                    'hour': hour,
                    'timestamp': timestamp.isoformat(),
                }
            }
        return None

    def analyze_openapi_data(self, data: Dict) -> List[Dict]:
        """
        Analisa dados coletados via OpenAPI e retorna todos os alertas detectados.

        Args:
            data: Dicionário retornado por collect_all_data()

        Returns:
            Lista de alertas detectados
        """
        alerts = []
        timestamp = data.get('timestamp', datetime.now())
        summary = data.get('summary') or {}
        today_kwh = float(summary.get('today', 0) or 0)

        # 1. Sistema sem geração durante horário solar
        try:
            alert = self.detect_low_generation_daylight(today_kwh, timestamp)
            if alert:
                alerts.append(alert)
        except Exception as e:
            logger.warning(f"Erro em detect_low_generation_daylight: {e}")

        # 2. Alarmes de hardware da ECU
        try:
            ecu_alerts = self.detect_ecu_alarms(data.get('inverters') or [])
            alerts.extend(ecu_alerts)
        except Exception as e:
            logger.warning(f"Erro em detect_ecu_alarms: {e}")

        # 3. Canais de microinversor com energia zero
        try:
            inv_summaries = data.get('inverter_summaries') or {}
            if inv_summaries:
                fault_alerts = self.detect_inverter_channel_faults(inv_summaries, today_kwh)
                alerts.extend(fault_alerts)
        except Exception as e:
            logger.warning(f"Erro em detect_inverter_channel_faults: {e}")

        return alerts

    def _get_historical_average(self, timestamp: datetime, window_days: int) -> Optional[float]:
        """
        Calcula média histórica de potência para a mesma hora do dia.

        Args:
            timestamp: Timestamp de referência
            window_days: Janela de dias para calcular média

        Returns:
            Média de potência em watts ou None
        """
        try:
            hour = timestamp.hour
            end_date = timestamp.date() - timedelta(days=1)  # Excluir hoje
            start_date = end_date - timedelta(days=window_days)

            # Buscar dados do período
            data = self.repository.get_generation_data_for_period(start_date, end_date)

            # Filtrar pela mesma hora
            same_hour_data = [d.power_watts for d in data if d.timestamp.hour == hour]

            if same_hour_data:
                return sum(same_hour_data) / len(same_hour_data)

            return None

        except Exception as e:
            logger.error(f"Erro ao calcular média histórica: {e}")
            return None

    def analyze_generation_data(self, data: Dict, max_capacity: float = 5000) -> List[Dict]:
        """
        Analisa dados de geração e retorna lista de alertas.

        Args:
            data: Dados coletados da API
            max_capacity: Capacidade máxima do sistema em watts

        Returns:
            Lista de alertas detectados
        """
        alerts = []

        try:
            timestamp = data.get('timestamp', datetime.now())
            realtime_power = data.get('realtime_power', {})
            current_power = realtime_power.get('power', 0)

            # 1. Detectar pico de geração
            peak_alert = self.detect_peak_generation(current_power, max_capacity)
            if peak_alert:
                alerts.append(peak_alert)

            # 2. Detectar geração zero
            zero_alert = self.detect_zero_generation(timestamp, current_power)
            if zero_alert:
                alerts.append(zero_alert)

            # 3. Detectar queda de potência
            drop_alert = self.detect_power_drop(current_power, timestamp)
            if drop_alert:
                alerts.append(drop_alert)

            # 4. Verificar alarmes do hardware
            alarm_data = data.get('alarm_data', {})
            hardware_alerts = self.check_system_alarms(alarm_data)
            alerts.extend(hardware_alerts)

            # 5. Detectar sistema offline
            last_comm = realtime_power.get('last_update', timestamp)
            if isinstance(last_comm, str):
                last_comm = datetime.fromisoformat(last_comm)
            offline_alert = self.detect_offline_system(last_comm)
            if offline_alert:
                alerts.append(offline_alert)

        except Exception as e:
            logger.error(f"Erro ao analisar dados de geração: {e}")

        return alerts
