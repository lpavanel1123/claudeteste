-- Portal de Cotações — schema PostgreSQL
-- Aplicar uma única vez: psql $DATABASE_URL -f schema.sql

CREATE TABLE IF NOT EXISTS users (
  username       VARCHAR(64) PRIMARY KEY,
  password_hash  TEXT NOT NULL,
  role           VARCHAR(16) NOT NULL DEFAULT 'viewer',
  nome           TEXT,
  email          TEXT,
  celular        TEXT,
  empresa        TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extractions (
  id                    TEXT PRIMARY KEY,
  is_manual             BOOLEAN DEFAULT FALSE,
  is_bulk_import        BOOLEAN DEFAULT FALSE,
  is_training           BOOLEAN DEFAULT FALSE,
  date                  TIMESTAMP NOT NULL,
  "from"                TEXT,
  subject               TEXT,
  request_type          VARCHAR(16),
  project_type          VARCHAR(32),
  requester_name        TEXT,
  department            TEXT,
  recipient             TEXT,
  cnpj                  TEXT,
  smart_account         TEXT,
  smart_account_domain  TEXT,
  virtual_account       TEXT,
  project_ref           TEXT,
  body                  TEXT,
  raw_email             JSONB NOT NULL DEFAULT '{}',
  products              JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_extractions_date ON extractions(date DESC);
CREATE INDEX IF NOT EXISTS idx_extractions_type ON extractions(request_type);

CREATE TABLE IF NOT EXISTS annotations (
  quote_id             TEXT PRIMARY KEY REFERENCES extractions(id) ON DELETE CASCADE,
  status               VARCHAR(32) NOT NULL DEFAULT 'Em Aberto',
  valor_total          NUMERIC(14,2),
  responsavel_interno  TEXT,
  fornecedor           TEXT,
  observacoes          TEXT,
  entregue             BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at           TIMESTAMP,
  updated_by           TEXT
);
CREATE INDEX IF NOT EXISTS idx_annotations_status ON annotations(status);
CREATE INDEX IF NOT EXISTS idx_annotations_fornecedor ON annotations(fornecedor);
-- Idempotente para bancos onde a tabela já existia antes deste campo:
ALTER TABLE annotations ADD COLUMN IF NOT EXISTS entregue BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS corrections (
  quote_id  TEXT PRIMARY KEY REFERENCES extractions(id) ON DELETE CASCADE,
  fields    JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS timelines (
  quote_id    TEXT PRIMARY KEY REFERENCES extractions(id) ON DELETE CASCADE,
  dates       JSONB NOT NULL DEFAULT '{}',
  updated_at  TIMESTAMP,
  updated_by  TEXT
);

CREATE TABLE IF NOT EXISTS deals (
  quote_id                TEXT PRIMARY KEY REFERENCES extractions(id) ON DELETE CASCADE,
  projeto_id_vale         TEXT,
  logicalis_id            TEXT,
  ntt_id                  TEXT,
  estimate_nacional       TEXT,
  estimate_importado      TEXT,
  order_id                TEXT,
  deal_id                 TEXT,
  last_ccw_sync           TIMESTAMP,
  max_estimated_delivery  DATE,
  response_received_at    TIMESTAMP,
  updated_at              TIMESTAMP,
  updated_by              TEXT
);
-- Idempotente para bancos onde a tabela já existia antes deste campo:
ALTER TABLE deals ADD COLUMN IF NOT EXISTS response_received_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS ccw_validations (
  id                      SERIAL PRIMARY KEY,
  quote_id                TEXT REFERENCES extractions(id) ON DELETE CASCADE,
  subject                 TEXT,
  order_id                TEXT,
  validated_at            TIMESTAMP,
  scenario                SMALLINT,
  max_estimated_delivery  DATE,
  max_lead_time_days      INT,
  products_created        INT,
  intersection            JSONB,
  only_in_portal          JSONB,
  only_in_ccw             JSONB,
  contributing_items      JSONB
);
CREATE INDEX IF NOT EXISTS idx_ccw_validations_quote ON ccw_validations(quote_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id          SERIAL PRIMARY KEY,
  "timestamp" TIMESTAMP NOT NULL DEFAULT now(),
  username    TEXT,
  quote_id    TEXT,
  subject     TEXT,
  action      VARCHAR(32),
  changes     JSONB
);
CREATE INDEX IF NOT EXISTS idx_audit_quote ON audit_log(quote_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log("timestamp" DESC);

CREATE TABLE IF NOT EXISTS pid_kb (
  part_number  VARCHAR(64) PRIMARY KEY,
  arquitetura  TEXT,
  categoria    TEXT,
  source       VARCHAR(16)
);

-- Substitui inbox.md (markdown reescrito por inteiro a cada email recebido)
CREATE TABLE IF NOT EXISTS email_log (
  id           SERIAL PRIMARY KEY,
  received_at  TIMESTAMP NOT NULL DEFAULT now(),
  sender       TEXT,
  recipient    TEXT,
  subject      TEXT,
  body         TEXT,
  attachments  JSONB DEFAULT '[]'
);

-- Status do bot_to_ccw (push model — bot envia após cada run)
CREATE TABLE IF NOT EXISTS bot_status (
  id            INT PRIMARY KEY DEFAULT 1,
  pushed_at     TIMESTAMP NOT NULL DEFAULT now(),
  runs          JSONB NOT NULL DEFAULT '[]',
  order_errors  JSONB NOT NULL DEFAULT '{}',
  token_info    JSONB NOT NULL DEFAULT '{}'
);

-- Correlação de emails: liga Message-IDs recebidos ao registro (quote_id) correto,
-- para que respostas/follow-ups na mesma thread atualizem em vez de duplicar.
CREATE TABLE IF NOT EXISTS email_threads (
  message_id   TEXT PRIMARY KEY,
  quote_id     TEXT NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
  in_reply_to  TEXT,
  "references" TEXT,
  received_at  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_threads_quote ON email_threads(quote_id);

-- Forecast de vendas (área Cisco): campos manuais por cotação/pedido, um por
-- projeto NTT ou Logicalis. Valor do projeto e nome do projeto não são
-- armazenados aqui — são calculados sob demanda (ver data_store.get_sales_forecast).
CREATE TABLE IF NOT EXISTS cisco_forecast (
  quote_id              TEXT PRIMARY KEY REFERENCES extractions(id) ON DELETE CASCADE,
  booking_date          DATE,
  tech_lead             TEXT,
  pm_name               TEXT,
  status                VARCHAR(32) NOT NULL DEFAULT 'Pipeline',
  -- Classificação do projeto (flags)
  projeto_capital       BOOLEAN NOT NULL DEFAULT FALSE,
  kec                   BOOLEAN NOT NULL DEFAULT FALSE,
  vbm                   BOOLEAN NOT NULL DEFAULT FALSE,
  projeto_obsolescencia BOOLEAN NOT NULL DEFAULT FALSE,
  prioridade_quarter    BOOLEAN NOT NULL DEFAULT FALSE,
  -- Acompanhamento
  proxima_acao          TEXT,
  proxima_acao_data     DATE,
  -- Qualificação MEDDPICC (versão enxuta)
  economic_buyer        TEXT,
  champion              TEXT,
  competition           TEXT,
  updated_at            TIMESTAMP,
  updated_by            TEXT
);

-- Migração para bancos criados antes das colunas acima (CREATE TABLE IF NOT
-- EXISTS não adiciona colunas em tabela existente)
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS projeto_capital       BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS kec                   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS vbm                   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS projeto_obsolescencia BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS prioridade_quarter    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS proxima_acao          TEXT;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS proxima_acao_data     DATE;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS economic_buyer        TEXT;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS champion              TEXT;
ALTER TABLE cisco_forecast ADD COLUMN IF NOT EXISTS competition           TEXT;

-- Override manual da cotação do dólar (Spend Analysis e Forecast de Vendas).
-- Enquanto existir a linha (id=1), ela substitui a busca automática via API
-- (fx_rate.get_usd_brl_rate) — ver data_store.get_effective_fx_rate.
CREATE TABLE IF NOT EXISTS fx_rate_override (
  id          INT PRIMARY KEY DEFAULT 1,
  rate        NUMERIC NOT NULL,
  updated_at  TIMESTAMP NOT NULL DEFAULT now(),
  updated_by  TEXT
);

-- Cotações favoritadas por usuário ("Favoritos" na sidebar)
CREATE TABLE IF NOT EXISTS favorites (
  username    TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  quote_id    TEXT NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
  created_at  TIMESTAMP NOT NULL DEFAULT now(),
  PRIMARY KEY (username, quote_id)
);
