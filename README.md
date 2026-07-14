# Portal de Cotações — Cisco Procurement Portal

Sistema completo para **recebimento, extração e gestão de cotações** enviadas por email. Recebe emails via Cloudmailin, extrai dados estruturados do corpo e de anexos XLS, e disponibiliza um portal web com dashboard, gráficos, timeline de processo, classificação automática de produtos e área administrativa.

---

## Arquitetura

```
Gmail / qualquer remetente
        │
        ▼
  Cloudmailin (recebe e faz POST via webhook)
        │
        ▼
  Cloudflare Tunnel  →  Flask Webhook (porta 8025)
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
     Dashboard · Cotações · Nova Cotação · Histórico · Admin
```

---

## Pré-requisitos

- Python 3.10+
- Conta gratuita no [Cloudmailin](https://cloudmailin.com)
- Conta gratuita no [Cloudflare](https://cloudflare.com) com domínio gerenciado
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/) instalado

---

## Instalação

```bash
git clone https://github.com/lpavanel1123/claudeteste.git
cd claudeteste
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
.\venv\Scripts\Activate.ps1    # Windows PowerShell
pip install -r requirements.txt
```

### Dependências

| Pacote | Uso |
|---|---|
| `flask` | Servidor web (webhook + portal) |
| `python-dotenv` | Variáveis de ambiente via `.env` |
| `xlrd` | Leitura de arquivos `.xls` legados |
| `openpyxl` | Leitura e geração de arquivos `.xlsx` |
| `werkzeug` | Hash de senhas (pbkdf2:sha256) |

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

## Hospedagem (Railway)

O projeto roda no **Railway** (plano Hobby, US$5/mês), com Postgres gerenciado substituindo os arquivos JSON locais.

```
Railway Project "claudeteste"
├── Postgres (plugin gerenciado, backups automáticos, 5 GB)
├── portal   → gunicorn portal:app --bind 0.0.0.0:$PORT   → app.flowsquote.com
└── webhook  → gunicorn webhook_server:app --bind 0.0.0.0:$PORT → webhook.flowsquote.com
```

Push para `main` → deploy automático em ambos os serviços. Ver `COMO_RODAR.md` para instruções de setup e desenvolvimento local.

## Como executar localmente

> **Pré-requisito:** `DATABASE_URL` configurado no `.env` (Postgres do Railway via proxy TCP, ou instância local).

Abra **2 terminais** com o venv ativo:

| Terminal | Comando | Função |
|---|---|---|
| 1 | `$env:PYTHONUTF8="1"; python portal.py` | Portal web em localhost:8080 |
| 2 | `$env:PYTHONUTF8="1"; python main.py` | Webhook na porta 8025 |

Acesse **http://localhost:8080** → login com `admin` / `admin123`
*(altere a senha após o primeiro acesso via Admin → Usuários)*

---

## Configuração do Cloudflare Tunnel

### Setup inicial (uma vez)

```bash
cloudflared tunnel login                          # Abre browser para autorizar
cloudflared tunnel create claudeteste             # Cria o tunnel
cloudflared tunnel route dns claudeteste app.seudominio.com
cloudflared tunnel route dns claudeteste webhook.seudominio.com
```

Crie `~/.cloudflared/config.yml`:

```yaml
tunnel: <UUID-gerado>
credentials-file: ~/.cloudflared/<UUID>.json

ingress:
  - hostname: app.seudominio.com
    service: http://localhost:8080
  - hostname: webhook.seudominio.com
    service: http://localhost:8025
  - service: http_status:404
```

### Configuração do Cloudmailin

No painel do Cloudmailin:
- **Target URL** → `https://webhook.seudominio.com/webhook?token=SEU_WEBHOOK_SECRET_TOKEN`
- **Format** → `Multipart`

---

## Portal web

### Telas

| Tela | Funcionalidade |
|---|---|
| **Dashboard** | KPIs + gráficos com atualização automática + seção Operacional |
| **Cotações** | Lista filtrável com toggle de colunas, edição inline de assunto e coluna de Etapa Timeline |
| **Detalhe** | Visão completa com todas as seções abaixo |
| **Nova Cotação** | Formulário para inclusão manual completa |
| **Histórico** | Log de auditoria de toda alteração, filtrável por usuário |
| **Admin** | Gestão de usuários e importação batch (visível apenas para role=admin) |

### Lista de Cotações — funcionalidades

- **Filtros:** Busca livre, Tipo, Status, Etapa da Timeline, Fornecedor
- **Toggle de colunas:** mostrar/ocultar colunas individualmente (preferência salva no `localStorage`)
- **Assunto editável inline:** clique no assunto para editar sem sair da lista (salva via fetch)
- **Etapa Timeline:** barra de progresso + contador `X/Y` + ícone da etapa atual; verde quando concluído
- **Requisitante:** exibe `requester_name` em vez do remetente do email

### Seções do Detalhe de Cotação

| Seção | Descrição |
|---|---|
| **Dados Extraídos** | Campos do email/XLS com correção inline e histórico de versões |
| **Informações Manuais** | Status, valor, responsável, fornecedor, observações |
| **IDs & Estimates** | Projeto ID (Vale), Logicalis ID, NTT ID, Estimate Nacional/Importado, Order ID, Deal ID |
| **Timeline do Processo** | Etapas visuais com datas editáveis e Previsão de Conclusão automática |
| **Email na Íntegra** | Cabeçalhos, corpo texto e HTML do email recebido |
| **Produtos** | Tabela com Arquitetura, Categoria e Origem classificadas automaticamente |

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
5. Início de Fabricação *(+ Previsão de Conclusão automática)*
6. Entrega ao Parceiro
7. Entrega à Área Demandante

**Estados visuais:**
- Verde com ✓ — etapa concluída (data preenchida)
- Azul pulsante — próxima etapa pendente
- Cinza — etapas futuras

### Previsão de Conclusão automática

Quando `Início de Fabricação` está preenchido, o sistema calcula automaticamente:

```
Previsão = Início de Fabricação + max(Lead Times dos produtos) + 10 dias de buffer
```

- Se não há data manual de previsão → exibe o valor calculado em azul
- Se há data manual → respeita a manual; mantém a nota informativa
- Uma nota discreta exibe o produto "agressor" (maior lead time) e o buffer aplicado
- Essa mesma lógica (`data_store.compute_auto_forecast`) alimenta a tabela **Pedidos com Previsão de Entrega Após** no Dashboard

### Avanço automático de "Entrega ao Parceiro"

Um Pedido avança sozinho para a etapa **Entrega ao Parceiro** quando (`data_store.check_and_advance_by_deadline`):

- o checkbox **Entregue** (em Informações Manuais) está marcado, **ou**
- o prazo previsto (CCW confirmado via `deals.max_estimated_delivery`, ou a estimativa calculada acima quando não há sync de CCW) já passou.

Regras:
- É **idempotente** — só roda se a etapa ainda não tiver data preenchida.
- A data gravada em `entrega_parceiro` é o próprio prazo previsto/estimado (não a data em que o sistema percebeu o vencimento); se o checkbox estiver marcado mas não houver nenhum prazo disponível, usa a data de hoje.
- Se o prazo previsto existir mas estiver em formato inválido, **nada é alterado** — fica sinalizado no Histórico como `deadline_check_pending`, para revisão manual.
- Avança só até "Entrega ao Parceiro" (não em cascata até "Entrega à Área Demandante").
- É chamado em dois pontos: (1) a cada sync diário do bot de CCW (`process_ccw_sync`, quando `Bot-rotina/run_daily.py` faz `POST /api/v1/leadtime`) e (2) ao salvar Informações Manuais no portal, pra refletir o checkbox na hora sem esperar o próximo sync.

---

## Produtos

### Importação do CCW (.xls / .xlsx)

Clique em **Importar CCW**, selecione **Nacional** ou **Importado** no dropdown ao lado, e escolha o arquivo. O sistema:

- Detecta colunas **dinamicamente por nome** (compatível com `modelo.xlsx` e outros exports CCW)
- **Classifica automaticamente** cada produto em Arquitetura e Categoria
- **Acumula** os produtos na lista — um segundo upload adiciona, não substitui

### Classificação automática de produtos

Cada produto recebe duas classificações automáticas:

| Coluna | Valores |
|---|---|
| **Arquitetura** | Enterprise Switching · Datacenter · Wireless · Routing · Segurança · IOT · Outros |
| **Categoria** | Hardware · Software · Serviços |

**Como funciona:**
1. Consulta a **Base de PIDs** (`data/pid_kb.json`) — entradas manuais têm prioridade
2. Se não encontrar, aplica regras de **prefixo do Part Number** (`C9300-` → Switching, `N9K-` → Datacenter, `CON-` → Serviços…)
3. Como fallback, usa **palavras-chave na descrição**
4. Grava o resultado na base para acelerar classificações futuras

### Base de PIDs — aprendizado contínuo

O arquivo `data/pid_kb.json` acumula classificações:

- **`source: "auto"`** — gerado pelo classifier, pode ser sobrescrito
- **`source: "manual"`** — definido pelo usuário na edição; nunca sobrescrito por uploads futuros

Quando o usuário corrige Arquitetura ou Categoria na edição manual, o sistema detecta a mudança e persiste como `"manual"` automaticamente, exibindo o número de correções salvas no feedback.

### Filtros na tabela de produtos

Três dropdowns filtram os produtos sem recarregar a página:
- **Arquitetura** — Enterprise Switching, Datacenter, Wireless…
- **Categoria** — Hardware, Software, Serviços
- **Origem** — Nacional, Importado

---

## IDs & Estimates — lógica por fornecedor

| Fornecedor | Logicalis ID (ETC) | NTT ID |
|---|---|---|
| Logicalis | ✅ editável | bloqueado |
| NTT | bloqueado | ✅ editável |
| Outros / vazio | ✅ editável | ✅ editável |

### Correlação e extração automática de emails (`email_matcher.py`)

O webhook não cria mais um registro novo pra cada email recebido — antes de salvar, tenta correlacionar o email a uma cotação já existente, nesta ordem:

1. **Thread** (`Message-ID`/`In-Reply-To`/`References`, tabela `email_threads`) — se o Cloudmailin enviar esses headers.
2. **ID já atribuído pelo vendor**: `NTT#####` (assunto ou corpo — a NTT costuma declarar "ID NTT da sua solicitação é: NTT#####") vira `deals.ntt_id`; `ETC ####` (assunto) vira `deals.logicalis_id` (mesmo campo — "ETC" é a convenção de ID da Logicalis).
3. **Código de projeto Vale**: prioriza `PRJ######` sobre `P0######` quando ambos aparecem no assunto/corpo → `deals.projeto_id_vale`.
4. **Nome do projeto normalizado** (assunto sem `Re:`/`Fwd:`/`Enc:`/`Res:`/prefixo de vendor/sufixo `- ETC ####`) — só como fallback, sempre restrito ao mesmo vendor.

Em todos os critérios, o **domínio do remetente/destinatário** (`nttdata.com`/`global.ntt` = NTT, `logicalis.com` = Logicalis — nunca o envelope/Return-Path, que pode ser um relay) funciona como trava: um email de um vendor nunca atualiza o registro de outro vendor. Sem nenhuma correlação confiável, cria um registro novo (nunca mescla no escuro).

`deals.response_received_at` é gravado quando um email correlacionado (não o primeiro da cotação) chega com anexo XLS/XLSX — hoje é assim que a resposta com produtos/preços chega de fato. Ainda não há extração de produtos de tabela dentro do corpo do email (sem exemplo real pra validar o parser).

---

## Dashboard — Seção Operacional

- **Cotações e Pedidos por Fornecedor** — barras agrupadas
- **Volume por Etapa do Processo** — barras horizontais por etapa
- **Top 10 Mais Antigos** — tabela com idade em dias **na etapa atual** (dias desde a entrada na etapa, não desde a criação da cotação) (verde < 30d · amarelo < 60d · vermelho > 60d)
- **Pedidos com Previsão de Entrega Após** — tabela de Pedidos cuja Previsão de Conclusão (manual ou automática) é posterior a uma data filtro (campo de data, padrão 01/10/2026), ordenados do mais distante para o mais próximo. Consulta `GET /api/forecast?after=YYYY-MM-DD`

> **Nota:** valores monetários (`Valor Total`, `Unit List Price`) não são mais exibidos em nenhuma tela do portal (Dashboard, Cotações, Detalhe) — apenas continuam sendo armazenados em `data/annotations.json` e nos produtos, podendo ser editados pelos formulários e reaproveitados via API/exportação.

---

## Área Admin (role = admin)

### Usuários (`/admin`)
Criação de usuários com username, senha (hash pbkdf2:sha256) e role: `admin` ou `viewer`.

### Importar Cotações batch (`/admin/import`)

**Passo 1** — Baixar template (`GET /admin/import/template`) → `.xlsx` com 23 colunas e dropdowns de validação.

**Passo 2** — Upload (`POST /admin/import/upload`) — lógica de match:

| Prioridade | Campo |
|---|---|
| 1º | Coluna `id` preenchida |
| 2º | `projeto_id_vale` |
| 3º | `logicalis_id` |
| 4º | `ntt_id` |
| — | Cria novo registro |

---

## Estrutura do projeto

```
├── main.py               # Inicia o servidor de webhook (porta 8025)
├── portal.py             # Inicia o portal web (porta 8080)
├── webhook_server.py     # Flask: recebe POSTs do Cloudmailin
├── email_parser.py       # Parse do payload multipart Cloudmailin
├── extractor.py          # Extrai campos do corpo do email
├── xls_reader.py         # Lê XLS/XLSX (fallback genérico)
├── classifier.py         # Classifica PIDs em Arquitetura + Categoria (regras + keywords)
├── pid_kb.py             # Base de PIDs com aprendizado de correções manuais
├── data_store.py         # Leitura/escrita de todos os JSONs do portal
├── config.py             # Configurações via variáveis de ambiente
├── seed_data.py          # Gerador de dados de treinamento
├── heartbeat.py          # Ping periódico (uso com tunnel SSH legado)
├── modelo.xlsx           # Modelo de export CCW para referência de colunas
├── requirements.txt
├── .env.example
│
├── templates/
│   ├── base.html         # Layout com sidebar e navbar estilo Cisco
│   ├── login.html
│   ├── dashboard.html    # KPIs + gráficos + seção Operacional
│   ├── quotes.html       # Lista com filtros, toggle de colunas, etapa timeline
│   ├── quote_detail.html # Detalhe + edição + timeline + produtos classificados
│   ├── new_quote.html    # Formulário de inclusão manual
│   ├── logs.html         # Histórico de auditoria
│   ├── admin.html        # Gestão de usuários (admin only)
│   └── admin_import.html # Importação batch via Excel (admin only)
│
├── static/style.css      # Design system Cisco (#005073 · #049FD9 · #00BCEB)
│
└── data/                 # Gerado em runtime — NÃO versionado
    ├── users.json        # Usuários com senha em hash
    ├── annotations.json  # Campos manuais por cotação
    ├── corrections.json  # Correções de dados auto-extraídos
    ├── timelines.json    # Datas das etapas do processo
    ├── deals.json        # IDs e Estimates por cotação
    ├── pid_kb.json       # Base de PIDs classificados (auto + manual)
    └── audit_log.json    # Log de toda alteração
```

---

## Segurança

| Medida | Implementação |
|---|---|
| Autenticação do webhook | Token secreto na URL verificado com `hmac.compare_digest` |
| Controle de acesso por role | `login_required` e `admin_required` decorators |
| Edição inline por allowlist | Apenas campos explicitamente permitidos podem ser editados via `/inline` |
| Limite de payload | 1 MB máximo por requisição |
| Sanitização de inputs | Newlines/tabs removidos antes de salvar |
| Senhas em hash | `werkzeug.security` com `pbkdf2:sha256` |
| Credenciais fora do código | Todas as chaves em `.env` (gitignored) |

---

## Solução de problemas

| Sintoma | Causa | Solução |
|---|---|---|
| `UnicodeEncodeError` no Windows | Encoding CP1252 do terminal | Defina `$env:PYTHONUTF8="1"` antes de iniciar |
| `cloudflared` não reconhecido | PATH não atualizado na sessão | Abra um novo terminal ou use o caminho completo |
| `403` no webhook | Token incorreto na URL | Verifique `WEBHOOK_SECRET_TOKEN` no `.env` e no Cloudmailin |
| Portal vazio | Sem dados | Execute `python3 seed_data.py` |
| `Part Number` não encontrado no upload | Formato de export diferente | Verifique se o cabeçalho contém a coluna `Part Number` |
| Produto classificado como "Outros" | PID fora das regras do classifier | Corrija manualmente na edição — o sistema aprende e salva na KB |
| Admin não aparece na sidebar | Usuário sem role=admin | Verifique `data/users.json` ou crie novo usuário via Admin |
