import html
import re
import email.utils
from datetime import datetime

_MAX_ATTACHMENTS = 20


def _html_to_text(html_content: str) -> str:
    text = html.unescape(html_content)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sanitize(value: str) -> str:
    """Remove newlines and tabs that could break Markdown structure."""
    return re.sub(r"[\r\n\t]", " ", value).strip()


def parse_webhook(form: dict, files: dict) -> dict:
    subject = _sanitize(form.get("headers[subject]", "(sem assunto)"))
    sender = _sanitize(form.get("headers[from]") or form.get("envelope[from]", "desconhecido"))
    recipient = _sanitize(form.get("headers[to]") or form.get("envelope[to]", ""))

    date_raw = form.get("headers[date]", "")
    try:
        date = email.utils.parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Headers de thread — usados para correlacionar follow-ups ao mesmo registro
    # (ver email_matcher.py). Cloudmailin nem sempre envia todos; ausência é normal
    # e degrada para os critérios de correlação por vendor/assunto.
    message_id = form.get("headers[message-id]", "").strip()
    in_reply_to = form.get("headers[in-reply-to]", "").strip()
    references = form.get("headers[references]", "").strip()

    body_plain = form.get("plain", "").strip()
    body_html = form.get("html", "")

    body = body_plain
    if not body and body_html:
        body = _html_to_text(body_html)

    attachments = []
    for file in files.getlist("attachments[]")[:_MAX_ATTACHMENTS]:
        if file and file.filename:
            attachments.append(_sanitize(file.filename))

    raw_email = {
        "from": sender,
        "to": recipient,
        "subject": subject,
        "date": date,
        "body_plain": body_plain,
        "body_html": body_html,
        "attachments": attachments,
    }

    return {
        "subject": subject,
        "from": sender,
        "to": recipient,
        "date": date,
        "body": body,
        "attachments": attachments,
        "raw_email": raw_email,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": references,
    }


def find_attachment(files):
    """Return the first XLS/XLSX file found in request.files, regardless of field name."""
    for file in files.values():
        if hasattr(file, "filename") and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext in ("xls", "xlsx"):
                return file
    return None
