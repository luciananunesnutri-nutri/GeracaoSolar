#!/bin/bash
# =============================================================================
# update.sh — Atualiza o projeto sem reinstalar tudo
# Rodar como: sudo bash deploy/update.sh
# =============================================================================
set -e
APP_DIR="/opt/geracaosolar"

echo "[1/4] Parando serviços..."
systemctl stop solar-web solar-scheduler

echo "[2/4] Atualizando código..."
cd "$APP_DIR"
git pull

echo "[3/4] Atualizando dependências..."
source venv/bin/activate
pip install -q -r requirements.txt

echo "[4/4] Reiniciando serviços..."
systemctl start solar-web solar-scheduler
sleep 2
systemctl status solar-web --no-pager -l
systemctl status solar-scheduler --no-pager -l

echo ""
echo "Atualização concluída!"
