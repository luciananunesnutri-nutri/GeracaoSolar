import logging
import logging.handlers
import os
import yaml
from pathlib import Path


def setup_logger(name: str = "solar_monitoring") -> logging.Logger:
    """
    Configura e retorna um logger configurado.

    Args:
        name: Nome do logger

    Returns:
        Logger configurado
    """
    # Carregar configurações
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    log_config = config['logging']

    # Criar diretório de logs se não existir
    log_file = Path(log_config['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Configurar logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_config['level']))

    # Evitar duplicação de handlers
    if logger.handlers:
        return logger

    # Handler para arquivo com rotação
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_config['max_bytes'],
        backupCount=log_config['backup_count'],
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_config['level']))

    # Handler para console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Adicionar handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Logger global
logger = setup_logger()
