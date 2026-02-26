from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON, Date, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import enum
from pathlib import Path
import yaml

Base = declarative_base()


class PeriodType(enum.Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class AlertType(enum.Enum):
    PEAK = "peak"
    LOW_GENERATION = "low_generation"
    OFFLINE = "offline"
    ALARM = "alarm"
    INVERTER_FAULT = "inverter_fault"
    ECU_ALARM = "ecu_alarm"


class Severity(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SystemStatus(enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class GenerationData(Base):
    """Dados de geração de energia."""
    __tablename__ = 'generation_data'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    ecu_id = Column(String(50), nullable=False, index=True)
    panel_id = Column(String(50), nullable=True, index=True)
    power_watts = Column(Float, nullable=False)
    energy_kwh_daily = Column(Float, nullable=True)
    energy_kwh_total = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<GenerationData(ecu_id='{self.ecu_id}', timestamp='{self.timestamp}', power={self.power_watts}W)>"


class Statistics(Base):
    """Estatísticas agregadas de geração."""
    __tablename__ = 'statistics'

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    period_type = Column(Enum(PeriodType), nullable=False)
    total_generation_kwh = Column(Float, nullable=False)
    peak_power_watts = Column(Float, nullable=False)
    average_power_watts = Column(Float, nullable=False)
    panel_stats = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<Statistics(date='{self.date}', type='{self.period_type}', total={self.total_generation_kwh}kWh)>"


class Alert(Base):
    """Alertas do sistema."""
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    alert_type = Column(Enum(AlertType), nullable=False)
    severity = Column(Enum(Severity), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Alert(type='{self.alert_type}', severity='{self.severity}', resolved={self.resolved})>"


class SystemStatusModel(Base):
    """Status do sistema."""
    __tablename__ = 'system_status'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    ecu_id = Column(String(50), nullable=False, index=True)
    status = Column(Enum(SystemStatus), nullable=False)
    last_communication = Column(DateTime, nullable=False)
    alarm_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<SystemStatus(ecu_id='{self.ecu_id}', status='{self.status}')>"


class EcuTelemetry(Base):
    """Telemetria minutely da ECU — série temporal de potência ao longo do dia."""
    __tablename__ = 'ecu_telemetry'

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    ecu_id = Column(String(50), nullable=False, index=True)
    time_series = Column(JSON, nullable=True)   # {time:[HH:mm,...], power:[W,...], energy:[kWh,...], today:kWh}
    updated_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<EcuTelemetry(ecu_id='{self.ecu_id}', date='{self.date}')>"


class InverterBatchData(Base):
    """Power telemetry e energia diária de todos os inversores de uma ECU."""
    __tablename__ = 'inverter_batch_data'

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    ecu_id = Column(String(50), nullable=False, index=True)
    power_data = Column(JSON, nullable=True)    # {time:[HH:mm,...], power:{'uid-ch':[W,...]}}
    energy_data = Column(JSON, nullable=True)   # {energy:['uid-ch-kwh',...]}
    updated_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<InverterBatchData(ecu_id='{self.ecu_id}', date='{self.date}')>"


class MeterData(Base):
    """Dados do medidor de energia (consumo vs geração vs rede)."""
    __tablename__ = 'meter_data'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    meter_id = Column(String(50), nullable=False, index=True)
    today = Column(JSON, nullable=True)      # {consumed, exported, imported, produced} kWh
    month = Column(JSON, nullable=True)
    year = Column(JSON, nullable=True)
    lifetime = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<MeterData(meter_id='{self.meter_id}', timestamp='{self.timestamp}')>"


class InverterSummary(Base):
    """Resumo de energia por inversor e canal (hoje/mês/ano/lifetime)."""
    __tablename__ = 'inverter_summary'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    inverter_uid = Column(String(50), nullable=False, index=True)
    channels = Column(JSON, nullable=True)   # {1:{today,month,year,lifetime}, 2:{...}, ...}
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<InverterSummary(uid='{self.inverter_uid}', timestamp='{self.timestamp}')>"


class AlertRecipient(Base):
    """Destinatários de alertas e relatórios por email."""
    __tablename__ = 'alert_recipients'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False, unique=True)
    active = Column(Boolean, default=True, nullable=False)
    receive_alerts = Column(Boolean, default=True, nullable=False)
    receive_reports = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<AlertRecipient(email='{self.email}', active={self.active})>"


class EmailLog(Base):
    """Log de envios de email."""
    __tablename__ = 'email_log'

    id = Column(Integer, primary_key=True)
    sent_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    email_type = Column(String(50), nullable=False, default='unknown')
    subject = Column(String(500), nullable=False)
    recipients = Column(JSON, nullable=True)      # lista de endereços
    recipient_count = Column(Integer, default=0)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<EmailLog(type='{self.email_type}', success={self.success}, sent_at='{self.sent_at}')>"


class Database:
    """Gerenciador de banco de dados."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            db_path = config['database']['path']

        # Criar diretório se não existir
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self):
        """Retorna uma nova sessão do banco."""
        return self.Session()


# Instância global
db = Database()
