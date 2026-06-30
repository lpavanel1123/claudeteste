# Como Rodar

## Produção — Railway (hospedagem em nuvem)

O projeto está hospedado no Railway com Postgres gerenciado.
URLs públicas: **https://app.flowsquote.com** (portal) · **https://webhook.flowsquote.com** (webhook)

### Deploy (automático)

Qualquer push para `main` no GitHub aciona redeploy automático dos dois serviços Railway.

### Configurações no Railway (já aplicadas, só consultar se precisar alterar)

| Serviço | Start Command |
|---|---|
| `portal` | `gunicorn portal:app --bind 0.0.0.0:$PORT` |
| `webhook` | `gunicorn webhook_server:app --bind 0.0.0.0:$PORT` |

Variáveis de ambiente configuradas em cada serviço:
- `DATABASE_URL` → referência ao plugin Postgres do projeto
- `PORTAL_SECRET_KEY`, `PORTAL_API_KEY`
- `WEBHOOK_SECRET_TOKEN`, `EMAIL_ADDRESS`

### Primeiro setup do banco (uma única vez)

```bash
# Obter DATABASE_URL público no painel Railway → Postgres → Connect → Public URL
psql $DATABASE_URL -f schema.sql
```

### Migração dos dados JSON → Postgres (uma única vez)

```bash
DATABASE_URL="..." python scripts/migrate_json_to_postgres.py
```

---

## Desenvolvimento local

Para rodar localmente, aponte `DATABASE_URL` para o Postgres do Railway (via proxy TCP público)
ou para um Postgres local (`postgres://localhost/claudeteste`).

### 1. Clonar e instalar

```powershell
git clone https://github.com/lpavanel1123/claudeteste.git
cd claudeteste
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configurar

```powershell
Copy-Item .env.example .env
# Edite o .env com DATABASE_URL, PORTAL_SECRET_KEY, WEBHOOK_SECRET_TOKEN etc.
```

```dotenv
DATABASE_URL=postgres://user:pass@host:port/db
PORTAL_SECRET_KEY=...
PORTAL_API_KEY=...
WEBHOOK_SECRET_TOKEN=...
EMAIL_ADDRESS=...
```

### 3. Rodar (2 terminais)

**Terminal 1 — Portal web** → http://localhost:8080
```powershell
$env:PYTHONUTF8 = "1"
.\venv\Scripts\python.exe portal.py
```

**Terminal 2 — Webhook** → porta 8025
```powershell
$env:PYTHONUTF8 = "1"
.\venv\Scripts\python.exe main.py
```

> Login: `admin` / `admin123`

> **Nota:** em produção os dois serviços sobem via `gunicorn` (Railway).
> O `cloudflared`/`tunnel.sh` não é mais necessário em produção — o Railway
> fornece HTTPS público nativamente. Pode continuar usando para expor
> desenvolvimento local se quiser.

---

## DNS / Cloudflare (domínio próprio)

Os subdomínios `app.flowsquote.com` e `webhook.flowsquote.com` apontam para Railway via CNAME (DNS-only no Cloudflare).

Para reconfigurar ou alterar:
1. No Railway → serviço → Settings → Domains → copiar CNAME alvo
2. No Cloudflare DNS → editar/criar registro CNAME para o subdomínio com proxy **desativado** (cinza)

---

## Cloudmailin

Target URL do webhook: `https://webhook.flowsquote.com/webhook?token=<WEBHOOK_SECRET_TOKEN>`
(Inalterado após migração para Railway)
