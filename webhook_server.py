import hmac
from flask import Flask, request, abort
import email_parser
import storage
import config

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB


@app.errorhandler(413)
def too_large(e):
    print("  [rejeitado] payload acima de 1 MB")
    return "413 Payload Too Large", 413


@app.route("/webhook", methods=["POST"])
def webhook():
    token = request.args.get("token", "")
    if config.WEBHOOK_SECRET_TOKEN and not hmac.compare_digest(token, config.WEBHOOK_SECRET_TOKEN):
        print("  [rejeitado] token inválido")
        abort(403)

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
