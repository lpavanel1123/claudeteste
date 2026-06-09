import hmac
import os
import tempfile
from pathlib import Path
from flask import Flask, request, abort
import email_parser
import extractor
import xls_reader
import extractions
import storage
import config

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB


@app.errorhandler(413)
def too_large(e):
    print("  [rejeitado] payload acima de 1 MB")
    return "413 Payload Too Large", 413


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    token = request.args.get("token", "")
    if config.WEBHOOK_SECRET_TOKEN and not hmac.compare_digest(token, config.WEBHOOK_SECRET_TOKEN):
        print("  [rejeitado] token inválido")
        abort(403)

    sender = request.form.get("headers[from]") or request.form.get("envelope[from]", "?")
    recipient = request.form.get("headers[to]") or request.form.get("envelope[to]", "?")
    print(f"\n[email recebido] de {sender!r} para {recipient!r}")

    try:
        parsed = email_parser.parse_webhook(request.form, request.files)
        extracted = extractor.extract_from_body(parsed["body"], parsed["to"])

        attachment = email_parser.find_attachment(request.files)
        if attachment:
            suffix = Path(attachment.filename).suffix or ".xls"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
            try:
                attachment.save(tmp_path)
                xls_data = xls_reader.read_xls(tmp_path)
            finally:
                os.unlink(tmp_path)

            extracted["products"] = xls_data["products"]
            for field in ("requester_name", "department", "cnpj"):
                if extracted.get(field) == "NA":
                    extracted[field] = xls_data.get(f"{field}_xls", "NA")
            if extracted.get("project_ref", "NA") == "NA":
                extracted["project_ref"] = xls_data.get("project_ref", "NA")
        else:
            extracted["products"] = []
            extracted["project_ref"] = "NA"

        storage.save(parsed)
        extractions.save(parsed, extracted)

    except Exception as exc:
        print(f"  [erro ao processar]: {exc}")
        return "500 Internal Error", 500

    return "200 OK", 200


def create_app() -> Flask:
    return app
