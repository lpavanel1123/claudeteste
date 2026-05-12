# Receptor de Email

Servidor webhook em Python que recebe emails enviados para um endereço Cloudmailin e os salva automaticamente em um arquivo Markdown (`inbox.md`), com os emails mais recentes sempre no topo.

## Como funciona

```
Gmail / qualquer remetente
        │
        ▼
  Cloudmailin (recebe o email e faz POST)
        │
        ▼
  Serveo / túnel SSH (expõe o servidor local)
        │
        ▼
  Flask (localhost:8025/webhook)
        │
        ▼
     inbox.md
```

## Pré-requisitos

- Python 3.8+
- Conta gratuita no [Cloudmailin](https://cloudmailin.com)
- Acesso SSH (já vem no macOS/Linux)

## Instalação

```bash
pip3 install -r requirements.txt
```

## Configuração

Edite o arquivo `config.py`:

```python
EMAIL_ADDRESS = "seu-endereco@cloudmailin.net"  # endereço fornecido pelo Cloudmailin
MAILGUN_SIGNING_KEY = ""                         # deixe vazio ao usar Cloudmailin
WEBHOOK_HOST = "0.0.0.0"
WEBHOOK_PORT = 8025
INBOX_FILE = "inbox.md"
```

## Como usar

### 1. Inicie o servidor (Terminal 1)

```bash
python3 main.py
```

Saída esperada:
```
=======================================================
  Receptor de Email — Mailgun Webhook
=======================================================
  Endereço monitorado : seu-endereco@cloudmailin.net
  Webhook local       : http://localhost:8025/webhook
  Arquivo de saída    : inbox.md
=======================================================
  Aguardando emails... (Ctrl+C para encerrar)
```

### 2. Abra o túnel SSH (Terminal 2)

```bash
ssh -R 80:localhost:8025 serveo.net
```

O serveo exibirá uma URL pública, por exemplo:
```
Forwarding HTTP traffic from https://abcdef.serveo.net
```

### 3. Configure o Cloudmailin

No painel do Cloudmailin:
- **Addresses** → selecione seu endereço
- **Target URL** → `https://abcdef.serveo.net/webhook`
- **Format** → `Multipart`

### 4. Envie um email

Envie qualquer email do Gmail (ou outro cliente) para o seu endereço `@cloudmailin.net`.

O email será salvo automaticamente no arquivo `inbox.md`.

## Estrutura do inbox.md

Cada email recebido é adicionado ao topo do arquivo no formato:

```markdown
# Caixa de Entrada — seu-endereco@cloudmailin.net

---
## [2026-05-12 17:30:00] Assunto do email
**De:** remetente@gmail.com
**Para:** seu-endereco@cloudmailin.net
**Data:** 2026-05-12 17:30:00

Corpo do email aqui...

> **Anexos:** arquivo.pdf, imagem.png
```

## Estrutura do projeto

```
├── main.py            # Ponto de entrada — inicia o servidor Flask
├── webhook_server.py  # Servidor Flask que recebe os POSTs do Cloudmailin
├── email_parser.py    # Extrai remetente, assunto, corpo e anexos do webhook
├── storage.py         # Salva os emails no inbox.md
├── config.py          # Configurações (endereço, porta, arquivo de saída)
├── requirements.txt   # Dependências Python
└── inbox.md           # Gerado automaticamente com os emails recebidos
```

## Solução de problemas

| Erro | Causa | Solução |
|---|---|---|
| `502 Bad Gateway` | Servidor Flask não está rodando | Execute `python3 main.py` |
| `406` no Flask | Chave de assinatura incompatível | Deixe `MAILGUN_SIGNING_KEY = ""` no `config.py` |
| Email rejeitado (5.7.1) | Domínio sandbox não aceita inbound | Use Cloudmailin em vez de Mailgun sandbox |
| Serveo cai | Instabilidade do serviço | Reconecte com `ssh -R 80:localhost:8025 serveo.net` |
