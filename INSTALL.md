# Guia de Instalação - Sistema de Monitoramento Solar

## Pré-requisitos

Antes de começar, certifique-se de ter:

1. **Python 3.9 ou superior** instalado
2. **Conta APSystems Cloud EMA** com acesso à API
3. **Conta Gmail** para envio de alertas

## Passo a Passo

### 1. Verificar Python

```bash
python --version
# Deve mostrar Python 3.9 ou superior
```

### 2. Instalar Dependências

```bash
# Navegar até o diretório do projeto
cd C:\desenv_build\projetos\GeracaoSolar

# Criar ambiente virtual (recomendado)
python -m venv venv

# Ativar ambiente virtual
# Windows:
venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

### 3. Configurar Credenciais

#### 3.1. Criar arquivo de credenciais

```bash
copy config\credentials.yaml.example config\credentials.yaml
```

#### 3.2. Editar credenciais

Abra `config\credentials.yaml` em um editor de texto e preencha com suas informações.

### 4. Executar Testes

```bash
python test_manual.py
```

### 5. Iniciar Sistema

```bash
# Terminal 1 - Scheduler
python main.py

# Terminal 2 - Dashboard
python web_server.py
```

### 6. Acessar Dashboard

```
http://localhost:5000
```

---

Consulte documentação completa em README.md
