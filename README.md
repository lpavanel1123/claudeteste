# Portal de Cotações — Cisco Procurement Portal

Sistema completo para **recebimento, extração e gestão de cotações** enviadas por email. Recebe emails via Cloudmailin, extrai dados estruturados do corpo e do anexo XLS, e disponibiliza um portal web com dashboard, gráficos e gestão manual das cotações.

---

## Arquitetura geral

```
Gmail / qualquer remetente
        │
        ▼
  Cloudmailin (recebe e faz POST via webhook)
        │
        ▼
  Serveo SSH tunnel  →  Flask Webhook (porta 8025)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              extractor.py          xls_reader.py
          (corpo do email)         (anexo XLS/XLSX)
                    │                   │
                    └─────────┬─────────┘
                              ▼
                    extractions.json + inbox.md
                              │
                              ▼
                   Portal Web Flask (porta 8080)
                   Dashboard · Cotações · Histórico
```

---

## Pré-requisitos

- Python 3.8+
- Conta gratuita no [Cloudmailin](https://cloudmailin.com)
- Acesso SSH (nativo no macOS/Linux)

---

## Instalação

```bash
pip3 install -r requirements.txt
```

### Dependências

| Pacote | Uso |
|---|---|
| `flask` | Servidor web (webhook + portal) |
| `python-dotenv` | Variáveis de ambiente via `.env` |
| `xlrd` | Leitura de arquivos `.xls` legados |
| `openpyxl` | Leitura de arquivos `.xlsx` |

---

## Configuração

Copie o modelo e preencha:

```bash
cp .env.example .env
```

```dotenv
EMAIL_ADDRESS=seu-endereco@cloudmailin.net
WEBHOOK_SECRET_TOKEN=gere-com-python3-c-import-secrets-print-secrets.token_urlsafe-32
WEBHOOK_PORT=8025

PORTAL_PORT=8080
PORTAL_SECRET_KEY=gere-outro-token-aqui
```

> **Gerar tokens seguros:**
> ```bash
> python3 -c "import secrets; print(secrets.token_urlsafe(32))"
> ```

---

## Como executar

### Terminal 1 — Servidor de webhook

```bash
python3 main.py
```

### Terminal 2 — Portal web

```bash
python3 portal.py
```

Acesse **http://localhost:8080** → login com `admin` / `admin123`
*(altere a senha após o primeiro acesso)*

### Terminal 3 — Túnel SSH para receber emails externos

```bash
./tunnel.sh
```

O script exibe a URL pública (ex: `https://abcdef.serveo.net`) e reconecta automaticamente se cair.

### Terminal 4 — Heartbeat opcional (mantém o túnel ativo)

```bash
python3 heartbeat.py
```

Faz ping em `/health` a cada 4 minutos para evitar que o túnel seja desligado por inatividade.

---

## Configuração do Cloudmailin

No painel do Cloudmailin:
- **Addresses** → selecione seu endereço
- **Target URL** → `https://abcdef.serveo.net/webhook?token=SEU_TOKEN`
- **Format** → `Multipart`

> O `?token=` é obrigatório — requisições sem token são bloqueadas com 403.

---

## Portal web

| Tela | Funcionalidade |
|---|---|
| **Dashboard** | 4 KPIs (total, valor R$, em aberto, fechadas) + 4 gráficos Chart.js com atualização automática a cada 5s |
| **Cotações** | Lista filtrável por tipo, status e busca livre; badge para dados de treinamento |
| **Detalhe** | Dados extraídos automaticamente + formulário de edição manual + tabela de produtos |
| **Corrigir** | Botão inline para corrigir campos auto-extraídos com histórico completo de versões |
| **Histórico** | Log de auditoria de toda alteração manual ou correção, filtrável por usuário |

### Campos extraídos automaticamente

| Campo | Fonte |
|---|---|
| Tipo (Cotação / Pedido) | Palavras-chave no corpo |
| Tipo de projeto (Novo / Obsolescência) | Palavras-chave no corpo |
| Requisitante + Departamento | Bloco de assinatura |
| CNPJ | Regex no corpo |
| Smart Account / Virtual Account / Domain ID | Labels no corpo |
| Produtos (Qtd + Part Number + Descrição) | Anexo XLS/XLSX |

### Campos manuais (editáveis no portal)

`valor_total` · `status` · `responsavel_interno` · `fornecedor` · `observacoes`

### Status disponíveis

`Em Aberto` · `Em Análise` · `Aprovada` · `Rejeitada` · `Ganha` · `Perdida`

---

## Dados de treinamento

Para popular o portal com dados realistas de teste:

```bash
python3 seed_data.py
```

Gera 28 cotações marcadas como `is_training: true` com equipamentos Cisco reais
(switches Catalyst/Nexus, firewalls Firepower, APs) e empresas brasileiras (Vale, Petrobras, Eletrobras…).

---

## Estrutura do projeto

```
├── main.py               # Inicia o servidor de webhook (porta 8025)
├── portal.py             # Inicia o portal web (porta 8080)
├── webhook_server.py     # Flask: recebe POSTs do Cloudmailin
├── email_parser.py       # Parse do payload multipart + detecção de anexos
├── extractor.py          # Extrai campos estruturados do corpo do email
├── xls_reader.py         # Lê XLS/XLSX e extorna produtos + metadados
├── extractions.py        # Persiste em extractions.json (com UUID por entrada)
├── storage.py            # Persiste email bruto em inbox.md
├── data_store.py         # Leitura/escrita de todos os JSONs do portal
├── config.py             # Configurações via variáveis de ambiente
├── seed_data.py          # Gerador de dados de treinamento
├── tunnel.sh             # Túnel SSH com auto-reconexão
├── heartbeat.py          # Ping periódico para manter túnel ativo
├── requirements.txt      # Dependências Python
├── .env.example          # Modelo de variáveis de ambiente
│
├── templates/            # Templates Jinja2 (Bootstrap 5 + Chart.js)
│   ├── base.html         # Layout com sidebar e navbar estilo Cisco
│   ├── login.html        # Tela de login
│   ├── dashboard.html    # Dashboard com KPIs e 4 gráficos
│   ├── quotes.html       # Lista de cotações com filtros
│   ├── quote_detail.html # Detalhe + edição manual + correção de dados
│   └── logs.html         # Histórico de alterações
│
├── static/style.css      # Design system Cisco (paleta #005073/#049FD9/#00BCEB)
│
└── data/                 # Gerado em runtime — NÃO versionado
    ├── users.json        # Usuários com senha em hash (werkzeug)
    ├── annotations.json  # Campos manuais por cotação
    ├── corrections.json  # Correções de dados auto-extraídos com histórico
    └── audit_log.json    # Log de toda alteração
```

---

## Segurança

| Medida | Implementação |
|---|---|
| Autenticação do webhook | Token secreto na URL (`?token=...`) verificado com `hmac.compare_digest` |
| Limite de payload | 1 MB máximo por requisição |
| Sanitização de inputs | Newlines/tabs removidos de campos antes de salvar |
| `attachment-count` limitado | Máximo 20 anexos por email |
| Senhas em hash | `werkzeug.security.generate_password_hash` |
| Credenciais fora do código | Todas as chaves em `.env` (gitignored) |

---

## Solução de problemas

| Sintoma | Causa | Solução |
|---|---|---|
| `502 Bad Gateway` | Servidor Flask parado | `python3 main.py` |
| `403` no webhook | Token ausente ou incorreto | Verifique `WEBHOOK_SECRET_TOKEN` no `.env` e na URL do Cloudmailin |
| `406` no Flask | Chave de assinatura incompatível | Deixe `MAILGUN_SIGNING_KEY = ""` (não usado com Cloudmailin) |
| Email rejeitado (5.7.1) | Domínio sandbox Mailgun não aceita inbound | Use Cloudmailin |
| Túnel cai | Instabilidade do serveo | Use `./tunnel.sh` (auto-reconexão automática) |
| Portal não atualiza | Polling parado | Verifique o console do browser (F12) |
| Produtos não extraídos | Formato XLS diferente do padrão | Verifique se a tabela tem colunas "Qtd" e "Part" |
