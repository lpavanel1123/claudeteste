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
  updated_at           TIMESTAMP,
  updated_by           TEXT
);
CREATE INDEX IF NOT EXISTS idx_annotations_status ON annotations(status);
CREATE INDEX IF NOT EXISTS idx_annotations_fornecedor ON annotations(fornecedor);

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
  updated_at              TIMESTAMP,
  updated_by              TEXT
);

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
