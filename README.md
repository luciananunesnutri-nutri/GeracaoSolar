# Sistema de Monitoramento Solar APSystems

Sistema completo de monitoramento de geração de energia solar para equipamentos APSystems, com coleta automatizada de dados, análise de anomalias, alertas por email e dashboard web.

## Características

- ✅ Coleta automatizada de dados da API Cloud EMA APSystems (a cada hora)
- ✅ Armazenamento de histórico em banco de dados SQLite
- ✅ Análise individual por painel solar
- ✅ Detecção de anomalias e geração de alertas
- ✅ Notificações por email (Gmail)
- ✅ Dashboard web interativo com gráficos
- ✅ Estatísticas diárias, mensais e anuais
- ✅ Respeita limite de 1000 chamadas/mês da API

## Requisitos

- Python 3.9 ou superior
- Conta APSystems Cloud EMA
- Conta Gmail (para envio de alertas)

## Instalação

### 1. Clone ou baixe o repositório

```bash
cd C:\desenv_build\projetos\GeracaoSolar
```

### 2. Crie um ambiente virtual (recomendado)

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as credenciais

Copie o arquivo de exemplo e edite com suas credenciais:

```bash
copy config\credentials.yaml.example config\credentials.yaml
```

Edite `config\credentials.yaml` e preencha:

```yaml
apsystems:
  username: "seu_email_apsystems"
  password: "sua_senha_apsystems"
  ecu_id: "seu_ecu_id"  # Encontrado na app APSystems

email:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  sender_email: "seu_email@gmail.com"
  sender_password: "senha_de_aplicativo_google"  # Ver instruções abaixo
  recipient_email: "email_destino_alertas@gmail.com"
```

#### Como obter senha de aplicativo do Google

1. Acesse https://myaccount.google.com/security
2. Ative "Verificação em duas etapas"
3. Vá em "Senhas de app"
4. Gere uma senha para "Email" ou "Outro"
5. Use essa senha no campo `sender_password`

## Uso

### Iniciar o Scheduler (Coleta Automatizada)

O scheduler executa a coleta de dados a cada hora e processa estatísticas diariamente:

```bash
python main.py
```

Isso irá:
- Coletar dados a cada hora (0 minutos)
- Calcular estatísticas diariamente às 23:55
- Limpar dados antigos semanalmente (domingos às 2h)

### Iniciar o Dashboard Web

Em outro terminal, inicie o servidor web:

```bash
python web_server.py
```

Acesse o dashboard em: **http://localhost:5000**

### Teste Manual de Coleta

Para testar a coleta sem aguardar o agendamento:

```bash
python -c "from src.scheduler.jobs import collect_solar_data; collect_solar_data()"
```

## Estrutura do Projeto

```
GeracaoSolar/
├── config/                      # Configurações
│   ├── config.yaml              # Configurações gerais
│   ├── credentials.yaml         # Credenciais (não commitado)
│   └── alerts_rules.yaml        # Regras de alertas
├── src/                         # Código fonte
│   ├── api/                     # Cliente API APSystems
│   ├── database/                # Modelos e repositório
│   ├── analysis/                # Detecção de anomalias
│   ├── alerts/                  # Sistema de alertas
│   ├── scheduler/               # Jobs agendados
│   ├── web/                     # Dashboard Flask
│   └── utils/                   # Utilitários
├── data/                        # Banco de dados (criado automaticamente)
├── logs/                        # Logs da aplicação
├── tests/                       # Testes
├── main.py                      # Entry point scheduler
├── web_server.py                # Entry point dashboard
└── requirements.txt             # Dependências
```

## Funcionalidades Detalhadas

### 1. Coleta de Dados

- **Frequência**: A cada hora (configurável)
- **Dados coletados**:
  - Potência em tempo real
  - Energia gerada (diária e total)
  - Dados por inversor/painel
  - Alarmes do hardware
- **Limite de API**: ~720 chamadas/mês (dentro do limite de 1000)

### 2. Detecção de Anomalias

#### Pico de Geração
- Detecta quando geração ultrapassa 80% da capacidade
- Severidade: INFO
- Notificação por email

#### Geração Zero Durante o Dia
- Detecta geração zero entre 8h-17h
- Severidade: CRITICAL
- Indica possível falha no sistema

#### Queda de Potência
- Compara com média histórica (últimos 30 dias)
- Detecta quedas > 50%
- Severidade: WARNING

#### Sistema Offline
- Detecta ausência de comunicação > 2 horas
- Severidade: CRITICAL

#### Alarmes de Hardware
- Processa alarmes reportados pela ECU
- Severidade: WARNING

### 3. Dashboard Web

O dashboard exibe:

- **Cards de estatísticas**:
  - Potência atual
  - Geração do dia
  - Pico de potência
  - Total gerado

- **Gráfico de geração diária**:
  - Potência por hora do dia
  - Visualização em linha

- **Tabela de painéis**:
  - Performance individual
  - Comparação entre painéis

- **Alertas ativos**:
  - Lista de alertas não resolvidos
  - Opção de resolver alertas

- **Auto-refresh**: Atualiza a cada 5 minutos

### 4. Notificações por Email

Emails são enviados automaticamente quando:
- Anomalia é detectada
- Sistema fica offline
- Alarme de hardware é reportado

Formato do email:
- HTML responsivo
- Cores por severidade
- Detalhes completos do alerta

## Configuração

### config.yaml

Configurações gerais do sistema:

```yaml
apsystems:
  base_url: "http://api.apsystemsema.com:8073/apsema/v1"
  timeout: 30
  max_retries: 3

database:
  path: "data/solar_monitoring.db"

scheduler:
  collection_interval: "0 * * * *"      # A cada hora
  statistics_interval: "55 23 * * *"    # 23:55 diariamente
  cleanup_interval: "0 2 * * 0"         # 2h aos domingos

web:
  host: "0.0.0.0"
  port: 5000
  debug: false

logging:
  level: "INFO"
  file: "logs/app.log"
  max_bytes: 10485760  # 10MB
  backup_count: 5
```

### alerts_rules.yaml

Regras de detecção de alertas:

```yaml
alerts:
  peak_generation:
    enabled: true
    threshold_percent: 80
    severity: "info"

  zero_generation:
    enabled: true
    daylight_hours: [8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    severity: "critical"

  power_drop:
    enabled: true
    threshold_percent: 50
    comparison_window_days: 30
    severity: "warning"

  system_offline:
    enabled: true
    timeout_minutes: 120
    severity: "critical"

  hardware_alarms:
    enabled: true
    severity: "warning"
```

## API Endpoints

### Dashboard

- `GET /` - Dashboard principal

### API REST

- `GET /api/current` - Dados em tempo real
- `GET /api/daily/<date>` - Estatísticas diárias
- `GET /api/monthly/<year>/<month>` - Estatísticas mensais
- `GET /api/yearly/<year>` - Estatísticas anuais
- `GET /api/panels` - Performance dos painéis
- `GET /api/alerts` - Alertas ativos
- `POST /api/alerts/<id>/resolve` - Resolver alerta

## Banco de Dados

### Tabelas

1. **generation_data**: Dados brutos de geração
2. **statistics**: Estatísticas agregadas (diárias, mensais, anuais)
3. **alerts**: Histórico de alertas
4. **system_status**: Status do sistema

### Manutenção

- Dados brutos são mantidos por 6 meses
- Estatísticas são mantidas indefinidamente
- Limpeza automática semanal

## Logs

Logs são salvos em `logs/app.log` com rotação automática:
- Tamanho máximo: 10MB
- Backups mantidos: 5
- Formato: `YYYY-MM-DD HH:MM:SS - nome - level - mensagem`

## Solução de Problemas

### Erro de autenticação na API

- Verifique username e password em `credentials.yaml`
- Teste login manual no portal APSystems
- Verifique se ECU ID está correto

### Erro ao enviar emails

- Verifique se está usando senha de aplicativo do Google
- Confirme que "Verificação em duas etapas" está ativa
- Teste SMTP com telnet: `telnet smtp.gmail.com 587`

### Dashboard não mostra dados

- Verifique se o scheduler está rodando
- Execute coleta manual para popular banco
- Verifique logs em `logs/app.log`

### Banco de dados corrompido

```bash
# Backup do banco
copy data\solar_monitoring.db data\backup.db

# Remover e recriar
del data\solar_monitoring.db
python -c "from src.database.models import db; print('Banco recriado')"
```

## Melhorias Futuras

- [ ] Integração com previsão do tempo
- [ ] Machine Learning para previsão de geração
- [ ] Notificações via Telegram/WhatsApp
- [ ] Dashboard avançado com Grafana
- [ ] API REST completa
- [ ] Multi-usuários com autenticação
- [ ] Backup automático para nuvem
- [ ] App mobile

## Licença

Este projeto é de código aberto para uso pessoal.

## Suporte

Para dúvidas ou problemas:
1. Verifique os logs em `logs/app.log`
2. Consulte a documentação da API APSystems
3. Revise as configurações em `config/`

## Autor

Sistema desenvolvido para monitoramento de geração solar APSystems.

---

**Versão**: 1.0.0
**Data**: 2026-02-09
