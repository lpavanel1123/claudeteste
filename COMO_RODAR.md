# Como Rodar

## 1. Clonar e instalar

```powershell
git clone https://github.com/lpavanel1123/claudeteste.git
cd claudeteste
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configurar

```powershell
Copy-Item .env.example .env
# Edite o .env com seu EMAIL_ADDRESS e tokens
```

## 3. Rodar (3 terminais)

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

**Terminal 3 — Cloudflare Tunnel**
```powershell
cloudflared tunnel run claudeteste
```

> Login: `admin` / `admin123`

---

## Setup do tunnel (uma vez)

```powershell
cloudflared tunnel login
cloudflared tunnel create claudeteste
cloudflared tunnel route dns claudeteste app.flowsquote.com
cloudflared tunnel route dns claudeteste webhook.flowsquote.com
```

URLs públicas após o tunnel:
- Portal → `https://app.flowsquote.com`
- Webhook → `https://webhook.flowsquote.com/webhook`
