from psycopg2.extras import Json

import db


def save(parsed_email: dict) -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO email_log (sender, recipient, subject, body, attachments)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                parsed_email.get("from"),
                parsed_email.get("to"),
                parsed_email.get("subject"),
                parsed_email.get("body"),
                Json(parsed_email.get("attachments") or []),
            ),
        )
    print(f"  [salvo] {parsed_email.get('subject')!r} de {parsed_email.get('from')!r}")
