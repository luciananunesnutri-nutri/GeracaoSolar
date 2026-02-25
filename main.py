#!/usr/bin/env python3
"""
Sistema de Monitoramento Solar APSystems
Entry point do scheduler - coleta automatizada de dados
"""

import sys
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import yaml

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from src.scheduler.jobs import collect_solar_data, calculate_statistics, cleanup_old_data, send_evening_summary
from src.utils.logger import logger


def load_config():
    """Carrega configurações."""
    config_path = Path(__file__).parent / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    """Função principal - inicia o scheduler."""
    logger.info("=" * 60)
    logger.info("SISTEMA DE MONITORAMENTO SOLAR APSYSTEMS")
    logger.info("=" * 60)

    # Carregar configurações
    config = load_config()
    scheduler_config = config['scheduler']

    # Criar scheduler
    scheduler = BlockingScheduler()

    # Job 1: Coleta de dados (a cada hora)
    scheduler.add_job(
        collect_solar_data,
        CronTrigger.from_crontab(scheduler_config['collection_interval']),
        id='collect_solar_data',
        name='Coleta de Dados Solares',
        replace_existing=True
    )
    logger.info(f"✓ Job 'Coleta de Dados' agendado: {scheduler_config['collection_interval']}")

    # Job 2: Resumo vespertino por email (diariamente às 17:00)
    scheduler.add_job(
        send_evening_summary,
        CronTrigger.from_crontab(scheduler_config['evening_summary_interval']),
        id='send_evening_summary',
        name='Resumo Vespertino por Email',
        replace_existing=True
    )
    logger.info(f"✓ Job 'Resumo Vespertino' agendado: {scheduler_config['evening_summary_interval']}")

    # Job 3: Cálculo de estatísticas (diariamente às 23:55)
    scheduler.add_job(
        calculate_statistics,
        CronTrigger.from_crontab(scheduler_config['statistics_interval']),
        id='calculate_statistics',
        name='Cálculo de Estatísticas',
        replace_existing=True
    )
    logger.info(f"✓ Job 'Cálculo de Estatísticas' agendado: {scheduler_config['statistics_interval']}")

    # Job 4: Limpeza de dados antigos (semanalmente)
    scheduler.add_job(
        cleanup_old_data,
        CronTrigger.from_crontab(scheduler_config['cleanup_interval']),
        id='cleanup_old_data',
        name='Limpeza de Dados Antigos',
        replace_existing=True
    )
    logger.info(f"✓ Job 'Limpeza de Dados' agendado: {scheduler_config['cleanup_interval']}")

    logger.info("=" * 60)
    logger.info("Scheduler iniciado. Aguardando execução dos jobs...")
    logger.info("Pressione Ctrl+C para interromper")
    logger.info("=" * 60)

    try:
        # Executar coleta inicial (opcional)
        logger.info("Executando coleta inicial...")
        try:
            collect_solar_data()
        except Exception as e:
            logger.warning(f"Coleta inicial falhou, scheduler continuará normalmente: {e}")

        # Iniciar scheduler
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrompido pelo usuário")
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"Erro no scheduler: {e}", exc_info=True)
        scheduler.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
