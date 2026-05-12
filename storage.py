from pathlib import Path
import config


def save(parsed_email: dict) -> None:
    inbox = Path(config.INBOX_FILE)

    entry = _format_entry(parsed_email)

    if inbox.exists():
        existing = inbox.read_text(encoding="utf-8")
        header_end = existing.find("\n\n")
        if header_end != -1:
            header = existing[: header_end + 2]
            body = existing[header_end + 2 :]
            inbox.write_text(header + entry + "\n" + body, encoding="utf-8")
        else:
            inbox.write_text(existing + "\n" + entry, encoding="utf-8")
    else:
        header = f"# Caixa de Entrada — {config.EMAIL_ADDRESS}\n\n"
        inbox.write_text(header + entry, encoding="utf-8")

    print(f"  [salvo] {parsed_email['subject']!r} de {parsed_email['from']!r}")


def _format_entry(e: dict) -> str:
    lines = [
        "---",
        f"## [{e['date']}] {e['subject']}",
        f"**De:** {e['from']}  ",
        f"**Para:** {e['to']}  ",
        f"**Data:** {e['date']}",
        "",
        e["body"] or "_(sem corpo)_",
    ]

    if e["attachments"]:
        lines.append("")
        lines.append("> **Anexos:** " + ", ".join(e["attachments"]))

    lines.append("")
    return "\n".join(lines)
