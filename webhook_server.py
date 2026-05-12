import hmac
import hashlib
from flask import Flask, request, abort
import email_parser
import storage
import config

app = Flask(__name__)


def _verify_signature(token: str, timestamp: str, signature: str) -> bool:
    if not config.MAILGUN_SIGNING_KEY:
        return True  # skip verification when key not configured
    value = (timestamp + token).encode("utf-8")
    digest = hmac.new(
        key=config.MAILGUN_SIGNING_KEY.encode("utf-8"),
        msg=value,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, signature)


@app.route("/webhook", methods=["POST"])
def webhook():
    token = request.form.get("token", "")
    timestamp = request.form.get("timestamp", "")
    signature = request.form.get("signature", "")

    if not _verify_signature(token, timestamp, signature):
        print("  [aviso] assinatura inválida — requisição rejeitada")
        abort(406)

    sender = request.form.get("from", "?")
    recipient = request.form.get("To") or request.form.get("to", "?")
    print(f"\n[email recebido] de {sender!r} para {recipient!r}")

    try:
        parsed = email_parser.parse_webhook(request.form, request.files)
        storage.save(parsed)
    except Exception as exc:
        print(f"  [erro ao processar]: {exc}")
        return "500 Internal Error", 500

    return "200 OK", 200


def create_app() -> Flask:
    return app
