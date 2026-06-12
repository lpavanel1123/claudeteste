# Portal de Cotações — Cisco Procurement Portal

Sistema completo para **recebimento, extração e gestão de cotações** enviadas por email. Recebe emails via Cloudmailin, extrai dados estruturados do corpo e de anexos XLS, e disponibiliza um portal web com dashboard, gráficos, timeline de processo e gestão manual.

---

## Arquitetura

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
          Dashboard · Cotações · Nova Cotação · Histórico
```

---

## Pré-requisitos

- Python 3.8+
- Conta gratuita no [Cloudmailin](https://cloudmailin.com)
- Acesso SSH (nativo no macOS/Linux)

---

## Instalação

```bash
git clone https://github.com/lpavanel1123/claudeteste.git
cd claudeteste
python3 -m venv venv
source venv/bin/activate
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

```bash
cp .env.example .env
```

```dotenv
EMAIL_ADDRESS=seu-endereco@cloudmailin.net
WEBHOOK_SECRET_TOKEN=<gerar abaixo>
PORTAL_SECRET_KEY=<gerar abaixo>
WEBHOOK_PORT=8025
PORTAL_PORT=8080
```

> **Gerar tokens seguros:**
> ```bash
> python3 -c "import secrets; print(secrets.token_urlsafe(32))"
> ```

---

## Como executar

Abra **4 terminais** (com o venv ativo em cada):

| Terminal | Comando | Função |
|---|---|---|
| 1 | `python3 main.py` | Webhook na porta 8025 |
| 2 | `python3 portal.py` | Portal web em localhost:8080 |
| 3 | `./tunnel.sh` | Túnel SSH via serveo.net |
| 4 | `python3 heartbeat.py` | Mantém o túnel ativo (ping a cada 4 min) |

Acesse **http://localhost:8080** → login com `admin` / `admin123`  
*(altere a senha após o primeiro acesso)*

O Terminal 3 exibe a URL pública (ex: `https://abcdef.serveo.net`) — use-a no Cloudmailin.

---

## Configuração do Cloudmailin

No painel do Cloudmailin:
- **Target URL** → `https://abcdef.serveo.net/webhook?token=SEU_WEBHOOK_SECRET_TOKEN`
- **Format** → `Multipart`

> O `?token=` é obrigatório — requisições sem token são bloqueadas com 403.

---

## Portal web

### Telas

| Tela | Funcionalidade |
|---|---|
| **Dashboard** | KPIs + gráficos com atualização automática + seção Operacional |
| **Cotações** | Lista filtrável por tipo, status e busca livre |
| **Detalhe** | Visão completa de cada cotação com todas as seções abaixo |
| **Nova Cotação** | Formulário para inclusão manual completa |
| **Histórico** | Log de auditoria de toda alteração, filtrável por usuário |

### Seções do Detalhe de Cotação

| Seção | Descrição |
|---|---|
| **Dados Extraídos Automaticamente** | Campos extraídos do email/XLS com opção de correção inline e histórico de versões |
| **Informações Manuais** | Status, valor, responsável, fornecedor (Logicalis / NTT / Outros), observações |
| **IDs & Estimates** | Projeto ID (Vale), Logicalis ID, NTT ID, Estimate Nacional/Importado, Order ID, Deal ID — campos condicionais por fornecedor |
| **Timeline do Processo** | Etapas visuais com datas editáveis (ver abaixo) |
| **Email na Íntegra** | Cabeçalhos, corpo texto e HTML do email recebido |
| **Produtos** | Tabela de itens extraídos do XLS (Qtd, Part Number, Descrição) |

### Tags de entrada

- 🟡 **Dados de Treinamento** — gerado via `seed_data.py`
- 🔵 **Entrada Manual** — criado pelo formulário Nova Cotação

### Dashboard — Seção Operacional

Abaixo dos gráficos padrão, a seção Operacional exibe:

- **Cotações e Pedidos por Fornecedor** — barras agrupadas por Logicalis, NTT, etc.
- **Volume por Etapa do Processo** — barras horizontais com quantos itens estão em cada etapa
- **Top 10 Mais Antigos** — tabela clicável com idade em dias colorida (verde < 30d · amarelo < 60d · vermelho > 60d) e etapa atual

---

## Timeline do Processo

Cada cotação possui uma timeline visual com etapas específicas por tipo:

### Cotação (2 etapas)
1. Solicitação de Orçamento
2. Entrega do Orçamento

### Pedido (7 etapas)
1. Solicitação do Pedido
2. Entrega do Orçamento
3. Aceite da Área Demandante
4. Pedido na Cisco
5. Início de Fabricação *(+ Previsão de Conclusão)*
6. Entrega ao Parceiro
7. Entrega à Área Demandante

**Estados visuais:**
- 🟢 Verde com ✓ — etapa concluída (data preenchida)
- 🔵 Azul pulsante — próxima etapa pendente
- ⚫ Cinza — etapas futuras

---

## IDs & Estimates — lógica por fornecedor

| Fornecedor | Logicalis ID (ETC) | NTT ID |
|---|---|---|
| Logicalis | ✅ editável | 🔒 bloqueado |
| NTT | 🔒 bloqueado | ✅ editável |
| Outros / vazio | ✅ editável | ✅ editável |

---

## Campos extraídos automaticamente

| Campo | Fonte |
|---|---|
| Tipo (Cotação / Pedido) | Palavras-chave no corpo |
| Tipo de projeto | Palavras-chave no corpo |
| Requisitante + Departamento | Bloco de assinatura |
| CNPJ | Regex no corpo |
| Smart Account / Virtual Account / Domain ID | Labels no corpo |
| Produtos (Qtd + Part Number + Descrição) | Anexo XLS/XLSX |

---

## Dados de treinamento

```bash
python3 seed_data.py
```

Gera 28 cotações com:
- Equipamentos Cisco reais (Catalyst, Nexus, Firepower, APs)
- Empresas brasileiras (Vale, Petrobras, Eletrobras…)
- Status, valores e responsáveis variados
- **Timelines** com progressão realista por estágio
- Marcadas como `is_training: true`

---

## Estrutura do projeto

```
├── main.py               # Inicia o servidor de webhook (porta 8025)
├── portal.py             # Inicia o portal web (porta 8080)
├── webhook_server.py     # Flask: recebe POSTs do Cloudmailin
├── email_parser.py       # Parse do payload multipart Cloudmailin
├── extractor.py          # Extrai campos estruturados do corpo do email
├── xls_reader.py         # Lê XLS/XLSX e retorna produtos + metadados
├── extractions.py        # Persiste em extractions.json (UUID por entrada)
├── storage.py            # Persiste email bruto em inbox.md
├── data_store.py         # Leitura/escrita de todos os JSONs do portal
├── config.py             # Configurações via variáveis de ambiente
├── seed_data.py          # Gerador de dados de treinamento
├── tunnel.sh             # Túnel SSH com auto-reconexão
├── heartbeat.py          # Ping periódico para manter túnel ativo
├── requirements.txt
├── .env.example
│
├── templates/
│   ├── base.html         # Layout com sidebar e navbar estilo Cisco
│   ├── login.html
│   ├── dashboard.html    # KPIs, 4 gráficos + seção Operacional
│   ├── quotes.html       # Lista com filtros
│   ├── quote_detail.html # Detalhe completo + edição + timeline
│   ├── new_quote.html    # Formulário de inclusão manual
│   └── logs.html         # Histórico de auditoria
│
├── static/style.css      # Design system Cisco (#005073 · #049FD9 · #00BCEB)
│
└── data/                 # Gerado em runtime — NÃO versionado
    ├── users.json        # Usuários com senha em hash (pbkdf2:sha256)
    ├── annotations.json  # Campos manuais por cotação
    ├── corrections.json  # Correções de dados auto-extraídos com histórico
    ├── timelines.json    # Datas das etapas do processo por cotação
    ├── deals.json        # IDs e Estimates por cotação
    └── audit_log.json    # Log de toda alteração
```

---

## Segurança

| Medida | Implementação |
|---|---|
| Autenticação do webhook | Token secreto na URL verificado com `hmac.compare_digest` |
| Limite de payload | 1 MB máximo por requisição |
| Sanitização de inputs | Newlines/tabs removidos antes de salvar |
| Senhas em hash | `werkzeug.security` com `pbkdf2:sha256` |
| Credenciais fora do código | Todas as chaves em `.env` (gitignored) |

---

## Solução de problemas

| Sintoma | Causa | Solução |
|---|---|---|
| `403` no webhook | Token incorreto na URL | Verifique `WEBHOOK_SECRET_TOKEN` no `.env` e na URL do Cloudmailin |
| `from` aparece como `desconhecido` | Formato multipart Cloudmailin | Verifique se o format no painel é `Multipart` |
| Túnel cai | Instabilidade do serveo | `./tunnel.sh` reconecta automaticamente a cada 5s |
| Portal vazio | Sem dados | Execute `python3 seed_data.py` |
| Erro `scrypt` no Python 3.9 | OpenSSL sem suporte a scrypt | Já corrigido — usa `pbkdf2:sha256` |
| Produtos não extraídos | Formato XLS diferente | Verifique se a tabela tem colunas "Qtd" e "Part" |
