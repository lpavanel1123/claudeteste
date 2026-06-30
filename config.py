from dotenv import load_dotenv
import os

load_dotenv()

EMAIL_ADDRESS        = os.getenv("EMAIL_ADDRESS", "")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", "")
WEBHOOK_HOST         = "0.0.0.0"
WEBHOOK_PORT         = int(os.getenv("WEBHOOK_PORT", "8025"))
INBOX_FILE           = "inbox.md"

PORTAL_PORT          = int(os.getenv("PORTAL_PORT", "8080"))
PORTAL_SECRET_KEY    = os.getenv("PORTAL_SECRET_KEY", "")
PORTAL_API_KEY       = os.getenv("PORTAL_API_KEY", "")

DATABASE_URL         = os.getenv("DATABASE_URL", "")

WEBEX_USER_TOKEN     = os.getenv("WEBEX_USER_TOKEN", "")
WEBHOOK_HEALTH_URL   = os.getenv("WEBHOOK_HEALTH_URL",
                                  f"http://localhost:{os.getenv('WEBHOOK_PORT', '8025')}/health")
