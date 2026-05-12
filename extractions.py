import json
import uuid
from pathlib import Path

EXTRACTIONS_FILE = "extractions.json"


def save(parsed_email: dict, extracted: dict) -> None:
    path = Path(EXTRACTIONS_FILE)
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    entry = {
        "id":      str(uuid.uuid4()),
        "date":    parsed_email["date"],
        "from":    parsed_email["from"],
        "subject": parsed_email["subject"],
        **extracted,
    }
    entries.append(entry)

    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [extractions] salvo em {EXTRACTIONS_FILE} ({len(entries)} entradas)")
