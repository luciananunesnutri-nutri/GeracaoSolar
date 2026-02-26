#!/usr/bin/env python3
"""
Sistema de Monitoramento Solar APSystems
Entry point do scheduler - coleta automatizada de dados
"""

import os
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

    # Gravar PID para permitir reinicialização via web
    pid_path = Path(__file__).parent / "data" / "scheduler.pid"
    pid_path.write_text(str(os.getpid()))
    logger.info(f"PID do scheduler: {os.getpid()} → {pid_path}")

    # Carregar configurações
    config = load_config()
    sc = config['scheduler']

    collection_enabled        = sc.get('collection_enabled', True)
    collection_on_startup     = sc.get('collection_on_startup', False)
    evening_summary_enabled   = sc.get('evening_summary_enabled', True)
    statistics_enabled        = sc.get('statistics_enabled', True)
    cleanup_enabled           = sc.get('cleanup_enabled', True)

    # Criar scheduler
    scheduler = BlockingScheduler()

    # Job 1: Coleta de dados
    if collection_enabled:
        scheduler.add_job(
            collect_solar_data,
            CronTrigger.from_crontab(sc['collection_interval']),
            id='collect_solar_data',
            name='Coleta de Dados Solares',
            replace_existing=True
        )
        logger.info(f"✓ Job 'Coleta de Dados' agendado: {sc['collection_interval']}")
    else:
        logger.info("✗ Job 'Coleta de Dados' DESABILITADO (collection_enabled: false)")

    # Job 2: Resumo vespertino por email
    if evening_summary_enabled:
        scheduler.add_job(
            send_evening_summary,
            CronTrigger.from_crontab(sc['evening_summary_interval']),
            id='send_evening_summary',
            name='Resumo Vespertino por Email',
            replace_existing=True
        )
        logger.info(f"✓ Job 'Resumo Vespertino' agendado: {sc['evening_summary_interval']}")
    else:
        logger.info("✗ Job 'Resumo Vespertino' DESABILITADO (evening_summary_enabled: false)")

    # Job 3: Cálculo de estatísticas
    if statistics_enabled:
        scheduler.add_job(
            calculate_statistics,
            CronTrigger.from_crontab(sc['statistics_interval']),
            id='calculate_statistics',
            name='Cálculo de Estatísticas',
            replace_existing=True
        )
        logger.info(f"✓ Job 'Cálculo de Estatísticas' agendado: {sc['statistics_interval']}")
    else:
        logger.info("✗ Job 'Cálculo de Estatísticas' DESABILITADO (statistics_enabled: false)")

    # Job 4: Limpeza de dados antigos
    if cleanup_enabled:
        scheduler.add_job(
            cleanup_old_data,
            CronTrigger.from_crontab(sc['cleanup_interval']),
            id='cleanup_old_data',
            name='Limpeza de Dados Antigos',
            replace_existing=True
        )
        logger.info(f"✓ Job 'Limpeza de Dados' agendado: {sc['cleanup_interval']}")
    else:
        logger.info("✗ Job 'Limpeza de Dados' DESABILITADO (cleanup_enabled: false)")

    logger.info("=" * 60)
    logger.info("Scheduler iniciado. Aguardando execução dos jobs...")
    logger.info("Pressione Ctrl+C para interromper")
    logger.info("=" * 60)

    try:
        # Coleta inicial — somente se habilitada explicitamente na config
        if collection_enabled and collection_on_startup:
            logger.info("Executando coleta inicial (collection_on_startup: true)...")
            try:
                collect_solar_data()
            except Exception as e:
                logger.warning(f"Coleta inicial falhou, scheduler continuará normalmente: {e}")
        elif collection_on_startup and not collection_enabled:
            logger.info("Coleta inicial ignorada: coleta agendada está desabilitada.")
        else:
            logger.info("Coleta inicial desabilitada (collection_on_startup: false).")

        # Iniciar scheduler
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrompido pelo usuário")
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"Erro no scheduler: {e}", exc_info=True)
        scheduler.shutdown()
        sys.exit(1)
    finally:
        if pid_path.exists():
            pid_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
