"""
One-off migration: read existing JSON files and backfill the Railway Postgres.

Usage (run from the project root with DATABASE_URL set):
    pip install psycopg2-binary python-dotenv
    DATABASE_URL="postgres://..." python scripts/migrate_json_to_postgres.py

All operations use INSERT ... ON CONFLICT DO NOTHING so the script is safe
to re-run without creating duplicates.
"""

import json
import hashlib
import sys
from pathlib import Path

# Allow running without full project imports
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not set. Export it before running this script.")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

ROOT       = Path(__file__).parent.parent
DATA       = ROOT / "data"
EXT_FILE   = ROOT / "extractions.json"
ANN_FILE   = DATA / "annotations.json"
CORR_FILE  = DATA / "corrections.json"
AUDIT_FILE = DATA / "audit_log.json"
TL_FILE    = DATA / "timelines.json"
DEALS_FILE = DATA / "deals.json"
CCW_FILE   = DATA / "ccw_validations.json"
USERS_FILE = DATA / "users.json"
KB_FILE    = DATA / "pid_kb.json"


def _load(path: Path, default):
    if not path.exists():
        print(f"  [skip] {path.name} not found")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [warn] could not parse {path.name}: {e}")
        return default


def _stable_id(q: dict) -> str:
    key = f"{q.get('date','')}{q.get('from','')}{q.get('subject','')}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def J(v):
    return psycopg2.extras.Json(v)


# ── 1. extractions ─────────────────────────────────────────────────────────────
print("Migrating extractions...")
entries = _load(EXT_FILE, [])
ok = skip = 0
for q in entries:
    if "id" not in q:
        q["id"] = _stable_id(q)
    cur.execute(
        """
        INSERT INTO extractions (
            id, is_manual, is_bulk_import, is_training,
            date, "from", subject, request_type, project_type,
            requester_name, department, recipient, cnpj,
            smart_account, smart_account_domain, virtual_account,
            project_ref, body, raw_email, products
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (id) DO NOTHING
        """,
        (
            q.get("id"),
            q.get("is_manual", False),
            q.get("is_bulk_import", False),
            q.get("is_training", False),
            q.get("date"),
            q.get("from"),
            q.get("subject"),
            q.get("request_type"),
            q.get("project_type"),
            q.get("requester_name"),
            q.get("department"),
            q.get("recipient"),
            q.get("cnpj"),
            q.get("smart_account"),
            q.get("smart_account_domain"),
            q.get("virtual_account"),
            q.get("project_ref"),
            q.get("body"),
            J(q.get("raw_email") or {}),
            J(q.get("products") or []),
        ),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  extractions: {ok} inserted, {skip} skipped (conflict)")

# ── 2. users ──────────────────────────────────────────────────────────────────
print("Migrating users...")
users = _load(USERS_FILE, [])
ok = skip = 0
for u in users:
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role, nome, email, celular, empresa, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (username) DO NOTHING
        """,
        (u.get("username"), u.get("password_hash"), u.get("role", "viewer"),
         u.get("nome", ""), u.get("email", ""), u.get("celular", ""), u.get("empresa", ""),
         u.get("created_at")),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  users: {ok} inserted, {skip} skipped")

# ── 3. annotations ────────────────────────────────────────────────────────────
print("Migrating annotations...")
anns = _load(ANN_FILE, {})
ok = skip = 0
for quote_id, a in anns.items():
    cur.execute(
        """
        INSERT INTO annotations (quote_id, status, valor_total, responsavel_interno,
                                 fornecedor, observacoes, updated_at, updated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (quote_id) DO NOTHING
        """,
        (quote_id, a.get("status", "Em Aberto"), a.get("valor_total"),
         a.get("responsavel_interno", ""), a.get("fornecedor", ""),
         a.get("observacoes", ""), a.get("updated_at"), a.get("updated_by")),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  annotations: {ok} inserted, {skip} skipped")

# ── 4. corrections ────────────────────────────────────────────────────────────
print("Migrating corrections...")
corrs = _load(CORR_FILE, {})
ok = skip = 0
for quote_id, fields in corrs.items():
    cur.execute(
        """
        INSERT INTO corrections (quote_id, fields) VALUES (%s, %s)
        ON CONFLICT (quote_id) DO NOTHING
        """,
        (quote_id, J(fields)),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  corrections: {ok} inserted, {skip} skipped")

# ── 5. timelines ─────────────────────────────────────────────────────────────
print("Migrating timelines...")
tls = _load(TL_FILE, {})
ok = skip = 0
for quote_id, tl in tls.items():
    cur.execute(
        """
        INSERT INTO timelines (quote_id, dates, updated_at, updated_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (quote_id) DO NOTHING
        """,
        (quote_id, J(tl.get("dates", {})), tl.get("updated_at"), tl.get("updated_by")),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  timelines: {ok} inserted, {skip} skipped")

# ── 6. deals ─────────────────────────────────────────────────────────────────
print("Migrating deals...")
deals = _load(DEALS_FILE, {})
ok = skip = 0
for quote_id, d in deals.items():
    max_del = d.get("max_estimated_delivery") or None
    if max_del == "":
        max_del = None
    last_sync = d.get("last_ccw_sync") or None
    cur.execute(
        """
        INSERT INTO deals (quote_id, projeto_id_vale, logicalis_id, ntt_id,
                           estimate_nacional, estimate_importado, order_id, deal_id,
                           last_ccw_sync, max_estimated_delivery, updated_at, updated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (quote_id) DO NOTHING
        """,
        (quote_id,
         d.get("projeto_id_vale", ""), d.get("logicalis_id", ""), d.get("ntt_id", ""),
         d.get("estimate_nacional", ""), d.get("estimate_importado", ""),
         d.get("order_id", ""), d.get("deal_id", ""),
         last_sync, max_del,
         d.get("updated_at"), d.get("updated_by")),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  deals: {ok} inserted, {skip} skipped")

# ── 7. ccw_validations ───────────────────────────────────────────────────────
print("Migrating ccw_validations...")
ccws = _load(CCW_FILE, {})
ok = 0
for quote_id, v in ccws.items():
    max_del = v.get("max_estimated_delivery") or None
    if max_del == "":
        max_del = None
    cur.execute(
        """
        INSERT INTO ccw_validations
            (quote_id, subject, order_id, validated_at, scenario,
             max_estimated_delivery, max_lead_time_days, products_created,
             intersection, only_in_portal, only_in_ccw, contributing_items)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (quote_id,
         v.get("subject", ""), v.get("order_id", ""), v.get("validated_at"),
         v.get("scenario"),
         max_del, v.get("max_lead_time_days"), v.get("products_created"),
         J(v.get("intersection", [])), J(v.get("only_in_portal", [])),
         J(v.get("only_in_ccw", [])), J(v.get("contributing_items", []))),
    )
    ok += 1
conn.commit()
print(f"  ccw_validations: {ok} inserted")

# ── 8. audit_log ─────────────────────────────────────────────────────────────
print("Migrating audit_log...")
logs = _load(AUDIT_FILE, [])
ok = 0
# Insert oldest-first so SERIAL id reflects original temporal order
for entry in reversed(logs):
    cur.execute(
        """
        INSERT INTO audit_log (username, quote_id, subject, action, changes, "timestamp")
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (entry.get("user", ""), entry.get("quote_id", ""), entry.get("subject", ""),
         entry.get("action", "edit"), J(entry.get("changes", {})),
         entry.get("timestamp")),
    )
    ok += 1
conn.commit()
print(f"  audit_log: {ok} inserted")

# ── 9. pid_kb ─────────────────────────────────────────────────────────────────
print("Migrating pid_kb...")
kb = _load(KB_FILE, {})
ok = skip = 0
for pn, v in kb.items():
    cur.execute(
        """
        INSERT INTO pid_kb (part_number, arquitetura, categoria, source)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (part_number) DO NOTHING
        """,
        (pn.upper(), v.get("arquitetura", ""), v.get("categoria", ""), v.get("source", "auto")),
    )
    if cur.rowcount:
        ok += 1
    else:
        skip += 1
conn.commit()
print(f"  pid_kb: {ok} inserted, {skip} skipped")

cur.close()
conn.close()
print("\nMigração concluída com sucesso!")
