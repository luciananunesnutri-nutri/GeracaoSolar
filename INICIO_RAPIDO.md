# 🚀 Início Rápido - Sistema de Monitoramento Solar

## 📋 Pré-requisitos

- Python 3.9+ instalado
- Conta APSystems Cloud EMA
- Conta Gmail

## ⚡ 5 Passos para Começar

### 1. Instalar Dependências (2 minutos)

```bash
cd C:\desenv_build\projetos\GeracaoSolar
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar Credenciais (3 minutos)

```bash
copy config\credentials.yaml.example config\credentials.yaml
notepad config\credentials.yaml
```

Preencha com suas informações:
- Username e senha do APSystems
- ECU ID (encontre no app APSystems)
- Email Gmail e senha de aplicativo

**Como obter senha de aplicativo do Google:**
https://myaccount.google.com/security → Senhas de app

### 3. Testar Instalação (1 minuto)

```bash
python test_manual.py
```

Deve mostrar: `✅ TODOS OS TESTES PASSARAM!`

### 4. Executar Coleta de Teste (2 minutos)

```bash
python -c "from src.scheduler.jobs import collect_solar_data; collect_solar_data()"
```

Verifique os logs:
```bash
type logs\app.log
```

### 5. Iniciar Sistema (1 minuto)

**Terminal 1** - Scheduler (coleta a cada hora):
```bash
venv\Scripts\activate
python main.py
```

**Terminal 2** - Dashboard web:
```bash
venv\Scripts\activate
python web_server.py
```

**Navegador** - Acesse:
```
http://localhost:5000
```

## ✅ Pronto!

Você verá:
- ⚡ Potência atual do sistema
- ☀️ Geração do dia
- 📊 Gráfico de geração por hora
- 🔔 Alertas ativos
- 📱 Performance dos painéis

## 🔄 Atualizações

O dashboard se atualiza automaticamente a cada 5 minutos.

## 📧 Alertas por Email

Você receberá emails quando:
- Sistema gerar >80% da capacidade (pico)
- Geração zero durante o dia (8h-17h)
- Queda >50% vs média histórica
- Sistema ficar offline >2 horas
- Alarmes do hardware

## 📁 Arquivos Importantes

```
logs/app.log              → Logs de execução
data/solar_monitoring.db  → Banco de dados
config/config.yaml        → Configurações gerais
config/alerts_rules.yaml  → Regras de alertas
```

## 🛠️ Comandos Úteis

**Ver logs em tempo real:**
```bash
tail -f logs\app.log  # Linux/Mac
Get-Content logs\app.log -Wait  # PowerShell
```

**Executar coleta manual:**
```bash
python -c "from src.scheduler.jobs import collect_solar_data; collect_solar_data()"
```

**Calcular estatísticas:**
```bash
python -c "from src.scheduler.jobs import calculate_statistics; calculate_statistics()"
```

**Testar envio de email:**
```bash
python -c "from src.alerts.email_sender import EmailSender; EmailSender().send_email('Teste', 'Funcionando!')"
```

## ❓ Problemas Comuns

### Dashboard não mostra dados
→ Execute coleta manual primeiro e aguarde alguns minutos

### Erro de autenticação API
→ Verifique username/password em `credentials.yaml`

### Erro ao enviar email
→ Use senha de aplicativo (não senha normal do Gmail)
→ Ative "Verificação em duas etapas" no Google

### Porta 5000 ocupada
→ Edite `config/config.yaml` e mude `web.port` para 8080

## 📚 Mais Informações

- `README.md` - Documentação completa
- `INSTALL.md` - Guia detalhado de instalação
- `PROJETO_COMPLETO.md` - Visão geral da implementação

## 🎯 Próximos Passos

1. **Monitore por alguns dias** para verificar funcionamento
2. **Ajuste regras de alertas** em `config/alerts_rules.yaml`
3. **Configure execução em background** (Task Scheduler no Windows)
4. **Faça backup** do banco de dados periodicamente

---

**Dúvidas?** Consulte `README.md` ou verifique `logs/app.log`

**Aproveite seu sistema de monitoramento solar!** ☀️⚡
