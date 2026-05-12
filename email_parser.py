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
    subject = _sanitize(form.get("subject", "(sem assunto)"))
    sender = _sanitize(form.get("from", "desconhecido"))
    recipient = _sanitize(form.get("To") or form.get("to", ""))

    date_raw = form.get("Date") or form.get("date", "")
    try:
        date = email.utils.parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        timestamp = form.get("timestamp")
        if timestamp:
            date = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = form.get("body-plain", "").strip()
    if not body:
        body_html = form.get("body-html", "")
        if body_html:
            body = _html_to_text(body_html)

    attachment_count = min(int(form.get("attachment-count", 0)), _MAX_ATTACHMENTS)
    attachments = []
    for i in range(1, attachment_count + 1):
        file = files.get(f"attachment-{i}")
        if file and file.filename:
            attachments.append(_sanitize(file.filename))

    return {
        "subject": subject,
        "from": sender,
        "to": recipient,
        "date": date,
        "body": body,
        "attachments": attachments,
    }


def find_attachment(files):
    """Return the first XLS/XLSX file found in request.files, regardless of field name."""
    for file in files.values():
        if hasattr(file, "filename") and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext in ("xls", "xlsx"):
                return file
    return None
