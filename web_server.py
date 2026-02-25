#!/usr/bin/env python3
"""
Sistema de Monitoramento Solar APSystems
Entry point do dashboard web
"""

import sys
from pathlib import Path
import yaml

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from src.web.app import create_app
from src.utils.logger import logger


def load_config():
    """Carrega configurações."""
    config_path = Path(__file__).parent / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    """Função principal - inicia o servidor web."""
    logger.info("=" * 60)
    logger.info("DASHBOARD WEB - MONITORAMENTO SOLAR")
    logger.info("=" * 60)

    # Carregar configurações
    config = load_config()
    web_config = config['web']

    # Criar app Flask
    app = create_app()

    host = web_config['host']
    port = web_config['port']
    debug = web_config['debug']

    logger.info(f"Iniciando servidor web em http://{host}:{port}")
    logger.info("Pressione Ctrl+C para interromper")
    logger.info("=" * 60)

    try:
        app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("Servidor web interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro no servidor web: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
