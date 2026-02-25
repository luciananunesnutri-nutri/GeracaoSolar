# 🔧 Como Configurar as Credenciais

## 📝 Passo 1: Editar Credenciais.txt

Abra o arquivo `Credenciais.txt` e preencha com suas informações:

```bash
notepad Credenciais.txt
```

### Exemplo de preenchimento:

```ini
[APSystems]
username = joao.silva@gmail.com
password = MinhaSenh@123
ecu_id = ECU-1234567890

[Email - Gmail]
sender_email = solar.alerts@gmail.com
sender_password = abcd efgh ijkl mnop
recipient_email = joao.silva@gmail.com
```

## 🔍 Como Encontrar Suas Credenciais

### ECU ID do APSystems

1. Abra o **aplicativo APSystems mobile** no seu celular
2. Vá em **"Dispositivos"** ou **"ECU"**
3. Copie o ID (formato: `ECU-xxxxxxxxxx`)

**OU**

1. Acesse o **portal web APSystems EMA**: https://ema.apsystemsema.com
2. Faça login
3. Vá em **"Sistema"** → **"Informações da ECU"**
4. Copie o ECU ID

### Senha de Aplicativo do Google

**IMPORTANTE**: NÃO use sua senha normal do Gmail!

1. Acesse: https://myaccount.google.com/security
2. Clique em **"Verificação em duas etapas"** e ative (se não estiver ativa)
3. Volte e procure por **"Senhas de app"**
4. Selecione:
   - **App**: Selecione "Email" ou "Outro (nome personalizado)"
   - **Dispositivo**: Digite "Monitoramento Solar"
5. Clique em **"Gerar"**
6. Copie a senha de 16 caracteres (pode ter espaços, tudo bem)
7. Cole no campo `sender_password`

## ⚙️ Passo 2: Executar Configuração

Depois de preencher o `Credenciais.txt`, execute:

```bash
python setup_credentials.py
```

Você verá:

```
====================================================
CONFIGURAÇÃO DE CREDENCIAIS
====================================================

📖 Lendo Credenciais.txt...
🔍 Validando credenciais...
✅ Credenciais validadas com sucesso!

📝 Criando config/credentials.yaml...
✅ Arquivo criado: config\credentials.yaml

====================================================
RESUMO DA CONFIGURAÇÃO
====================================================
APSystems Username: joao.silva@gmail.com
APSystems ECU ID:   ECU-1234567890
Email Remetente:    solar.alerts@gmail.com
Email Destinatário: joao.silva@gmail.com
====================================================

✅ CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!
```

## ✅ Passo 3: Testar Configuração

```bash
python test_manual.py
```

Se tudo estiver correto, você verá:

```
✅ TODOS OS TESTES PASSARAM!
```

## 🚀 Passo 4: Iniciar Sistema

```bash
# Terminal 1 - Scheduler
python main.py

# Terminal 2 - Dashboard
python web_server.py
```

## ❓ Problemas Comuns

### ❌ "Username do APSystems não preenchido"
→ Edite `Credenciais.txt` e preencha o campo `username` na seção `[APSystems]`

### ❌ "Senha de aplicativo do Google não preenchida"
→ Gere uma senha de aplicativo (veja instruções acima)
→ NÃO use sua senha normal do Gmail!

### ❌ "ECU ID não encontrado"
→ Verifique no app APSystems mobile
→ Deve ter formato: `ECU-xxxxxxxxxx`

### ❌ Erro ao enviar email de teste
→ Verifique se ativou "Verificação em duas etapas" no Google
→ Gere novamente a senha de aplicativo
→ Remova espaços da senha se houver

## 📋 Checklist de Configuração

- [ ] Editei o arquivo `Credenciais.txt`
- [ ] Preenchi username e password do APSystems
- [ ] Preenchi o ECU ID
- [ ] Configurei senha de aplicativo do Google (não senha normal!)
- [ ] Executei `python setup_credentials.py`
- [ ] Vi mensagem de sucesso
- [ ] Executei `python test_manual.py`
- [ ] Todos os testes passaram

## 🎉 Pronto!

Agora você pode iniciar o sistema:

```bash
python main.py          # Coleta automática
python web_server.py    # Dashboard web
```

Acesse: **http://localhost:5000**

---

**Dúvidas?** Consulte `README.md` ou `INSTALL.md`
