import uuid
from psycopg2.extras import Json

import db


def save(parsed_email: dict, extracted: dict) -> None:
    entry_id = str(uuid.uuid4())

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO extractions (
                id, date, "from", subject,
                request_type, project_type, requester_name, department,
                recipient, cnpj, smart_account, smart_account_domain,
                virtual_account, project_ref, body, raw_email, products
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                entry_id,
                parsed_email.get("date"),
                parsed_email.get("from"),
                parsed_email.get("subject"),
                extracted.get("request_type"),
                extracted.get("project_type"),
                extracted.get("requester_name"),
                extracted.get("department"),
                extracted.get("recipient"),
                extracted.get("cnpj"),
                extracted.get("smart_account"),
                extracted.get("smart_account_domain"),
                extracted.get("virtual_account"),
                extracted.get("project_ref"),
                parsed_email.get("body"),
                Json(parsed_email.get("raw_email") or {}),
                Json(extracted.get("products") or []),
            ),
        )

    print(f"  [extractions] salvo no Postgres: {parsed_email.get('subject')!r}")
