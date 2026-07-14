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
import data_store
import email_matcher
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

        match = email_matcher.resolve(parsed)
        quote_id = match["quote_id"]
        is_followup = bool(quote_id)

        if quote_id:
            # Follow-up correlacionado: atualiza o registro certo em vez de duplicar.
            safe_updates = {
                k: v for k, v in extracted.items()
                if k in email_matcher.MERGE_FIELDS and v and v != "NA"
            }
            if safe_updates:
                data_store.update_extraction_fields(
                    quote_id, safe_updates, parsed["subject"], "webhook",
                    action="email_correlation_update",
                )
            if extracted.get("products"):
                data_store.append_products(quote_id, parsed["subject"], extracted["products"], "webhook")
            print(f"  [correlação] email vinculado ao quote_id existente {quote_id!r}")
        else:
            quote_id = extractions.save(parsed, extracted)

        deal_updates = {}
        if match["vendor"] and match["vendor_ref"]:
            deal_key = "ntt_id" if match["vendor"] == "NTT" else "logicalis_id"
            deal_updates[deal_key] = match["vendor_ref"]
        if match["project_code"]:
            deal_updates["projeto_id_vale"] = match["project_code"]
        if is_followup and attachment:
            # Data de recebimento da resposta do orçamento (não confundir com a
            # data de criação do pedido original, que fica em extractions.date):
            # só marcamos quando o email correlacionado a uma cotação já
            # existente vem com anexo XLS/XLSX, que é o formato real em que a
            # resposta com produtos/preços chega hoje.
            deal_updates["response_received_at"] = parsed["date"]
        if deal_updates:
            data_store.save_deal(quote_id, parsed["subject"], deal_updates, "webhook")

        email_matcher.record_thread(
            parsed.get("message_id", ""), quote_id,
            parsed.get("in_reply_to", ""), parsed.get("references", ""),
        )

    except Exception as exc:
        print(f"  [erro ao processar]: {exc}")
        return "500 Internal Error", 500

    return "200 OK", 200


def create_app() -> Flask:
    return app
