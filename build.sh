#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Criar diretórios necessários
mkdir -p data logs config

# Gerar credentials.yaml a partir de variáveis de ambiente (se definidas)
cat > config/credentials.yaml <<CREDENTIALS
apsystems:
  app_id: ${APSYSTEMS_APP_ID:-}
  app_secret: ${APSYSTEMS_APP_SECRET:-}
  sid: ${APSYSTEMS_SID:-}
email:
  recipient_email: ${EMAIL_RECIPIENT:-}
  sender_email: ${EMAIL_SENDER:-}
  sender_password: ${EMAIL_PASSWORD:-}
  smtp_host: ${SMTP_HOST:-smtp.gmail.com}
  smtp_port: ${SMTP_PORT:-587}
CREDENTIALS

echo "Build concluído com sucesso!"
