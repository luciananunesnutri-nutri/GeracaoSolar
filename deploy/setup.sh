#!/bin/bash
# =============================================================================
# setup.sh — Deploy automático no Oracle Cloud (Ubuntu 22.04)
# Rodar como: sudo bash setup.sh
# =============================================================================
set -e

APP_DIR="/opt/geracaosolar"
APP_USER="solar"
REPO_URL=""          # preencher com a URL do repositório git, ou deixar vazio
                     # para upload manual

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERRO]${NC} $1"; exit 1; }

# ── 1. Sistema ────────────────────────────────────────────────────────────────
info "Atualizando pacotes..."
apt-get update -qq && apt-get upgrade -y -qq

info "Instalando dependências do sistema..."
apt-get install -y -qq python3 python3-pip python3-venv git nginx curl ufw

# ── 2. Usuário dedicado ───────────────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    info "Criando usuário $APP_USER..."
    useradd -r -m -d "$APP_DIR" -s /bin/bash "$APP_USER"
fi

# ── 3. Código da aplicação ────────────────────────────────────────────────────
if [ -n "$REPO_URL" ]; then
    info "Clonando repositório..."
    if [ -d "$APP_DIR/.git" ]; then
        cd "$APP_DIR" && git pull
    else
        git clone "$REPO_URL" "$APP_DIR"
    fi
else
    info "Diretório da aplicação: $APP_DIR"
    [ -d "$APP_DIR" ] || mkdir -p "$APP_DIR"
fi

# ── 4. Ambiente Python ────────────────────────────────────────────────────────
info "Configurando virtualenv..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q gunicorn

# ── 5. Diretórios e permissões ────────────────────────────────────────────────
info "Configurando diretórios..."
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod 750 "$APP_DIR/data" "$APP_DIR/logs"

# ── 6. Serviços systemd ───────────────────────────────────────────────────────
info "Instalando serviços systemd..."
cp "$APP_DIR/deploy/solar-web.service"       /etc/systemd/system/
cp "$APP_DIR/deploy/solar-scheduler.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable solar-web solar-scheduler

# ── 7. Nginx ──────────────────────────────────────────────────────────────────
info "Configurando Nginx..."
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/geracaosolar
ln -sf /etc/nginx/sites-available/geracaosolar /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl enable nginx && systemctl restart nginx

# ── 8. Firewall (ufw + iptables Oracle Cloud) ─────────────────────────────────
info "Configurando firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Oracle Cloud bloqueia via iptables por padrão — liberar porta 80
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
# Persistir regras iptables
apt-get install -y -qq iptables-persistent
netfilter-persistent save

# ── 9. Verificar credenciais ──────────────────────────────────────────────────
if [ ! -f "$APP_DIR/config/credentials.yaml" ]; then
    warn "ATENÇÃO: config/credentials.yaml não encontrado!"
    warn "Copie o arquivo de credenciais antes de iniciar os serviços:"
    warn "  scp credentials.yaml ubuntu@<IP>:$APP_DIR/config/"
    warn "Depois execute: sudo systemctl start solar-web solar-scheduler"
else
    info "Iniciando serviços..."
    systemctl start solar-web solar-scheduler
    sleep 3
    systemctl status solar-web --no-pager
    systemctl status solar-scheduler --no-pager
fi

# ── Resumo ────────────────────────────────────────────────────────────────────
IP=$(curl -s ifconfig.me 2>/dev/null || echo "<IP-do-servidor>")
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Deploy concluído!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e " Dashboard: ${YELLOW}http://$IP${NC}"
echo -e " Logs web:  journalctl -u solar-web -f"
echo -e " Logs sched: journalctl -u solar-scheduler -f"
echo ""
