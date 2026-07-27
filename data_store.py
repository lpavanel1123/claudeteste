import hashlib
from datetime import datetime, timedelta
from collections import defaultdict

from werkzeug.security import generate_password_hash, check_password_hash
from psycopg2.extras import Json

import db

# ── Constants (unchanged) ──────────────────────────────────────────────────────

CORRECTABLE_FIELDS = [
    "requester_name", "department", "request_type", "project_type",
    "cnpj", "smart_account", "smart_account_domain", "virtual_account", "project_ref",
]

DEAL_FIELDS = [
    {"key": "projeto_id_vale",       "label": "Projeto ID (Vale)"},
    {"key": "logicalis_id",          "label": "Logicalis ID (ETC)"},
    {"key": "ntt_id",                "label": "NTT ID"},
    {"key": "estimate_nacional",     "label": "Estimate Nacional"},
    {"key": "estimate_importado",    "label": "Estimate Importado"},
    {"key": "order_id",              "label": "Order ID"},
    {"key": "deal_id",               "label": "Deal ID"},
]

FORECAST_STATUSES = ["Commit", "Best Case", "Pipeline", "Upside"]

TIMELINE_STEPS = {
    "Cotação": [
        {"key": "solicitacao_orcamento", "label": "Solicitação de Orçamento",    "icon": "fa-envelope"},
        {"key": "entrega_orcamento",     "label": "Entrega do Orçamento",         "icon": "fa-file-invoice-dollar"},
    ],
    "Pedido": [
        {"key": "solicitacao_pedido",  "label": "Solicitação do Pedido",          "icon": "fa-envelope"},
        {"key": "entrega_orcamento",   "label": "Entrega do Orçamento",           "icon": "fa-file-invoice-dollar"},
        {"key": "aceite_area",         "label": "Aceite da Área Demandante",      "icon": "fa-circle-check"},
        {"key": "pedido_cisco",        "label": "Pedido na Cisco",                "icon": "fa-building"},
        {"key": "inicio_fabricacao",   "label": "Início de Fabricação",           "icon": "fa-industry",
         "extra_key": "previsao_fabricacao", "extra_label": "Previsão de Conclusão"},
        {"key": "entrega_parceiro",    "label": "Entrega ao Parceiro",            "icon": "fa-truck"},
        {"key": "entrega_demandante",  "label": "Entrega à Área Demandante",      "icon": "fa-flag-checkered"},
    ],
}

_UPDATABLE_EXTRACTION_COLS = {
    "subject", "request_type", "project_type", "requester_name", "department",
    "recipient", "cnpj", "smart_account", "smart_account_domain", "virtual_account",
    "project_ref", "is_manual", "is_bulk_import", "date",
}


def _stable_id(q: dict) -> str:
    """Fallback ID derivation for legacy records without an explicit id field."""
    key = f"{q.get('date','')}{q.get('from','')}{q.get('subject','')}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _str_dates(row: dict) -> dict:
    """Convert datetime/date objects to ISO strings so templates can slice them."""
    from datetime import datetime as _dt, date as _d
    for k, v in row.items():
        if isinstance(v, _dt):
            row[k] = str(v)[:19]
        elif isinstance(v, _d):
            row[k] = str(v)[:10]
    return row


# ── Extractions ───────────────────────────────────────────────────────────────

def load_extractions() -> list:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM extractions ORDER BY date DESC")
        return [_str_dates(dict(r)) for r in cur.fetchall()]


def find_quote_by_deal_field(key: str, value: str):
    """Returns quote_id if any deal entry has deals[key] == value, else None."""
    if not value or key not in {f["key"] for f in DEAL_FIELDS}:
        return None
    with db.get_cursor() as cur:
        cur.execute(f"SELECT quote_id FROM deals WHERE {key} = %s LIMIT 1", (value.strip(),))
        row = cur.fetchone()
        return row["quote_id"] if row else None


def delete_quotes(ids: list, user: str) -> int:
    """Delete extractions by id list. CASCADE removes all related rows."""
    with db.get_cursor() as cur:
        cur.execute("SELECT id, subject FROM extractions WHERE id = ANY(%s)", (ids,))
        rows = cur.fetchall()
    with db.get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM extractions WHERE id = ANY(%s)", (ids,))
        deleted = cur.rowcount
    for r in rows:
        _append_audit(r["id"], r["subject"] or "", {"_excluido": [r["id"], None]}, user, action="delete")
    return deleted


def get_extraction_by_id(quote_id: str):
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM extractions WHERE id = %s", (quote_id,))
        row = cur.fetchone()
        return _str_dates(dict(row)) if row else None


def update_extraction_fields(quote_id: str, updates: dict, subject: str, user: str,
                              action: str = "bulk_import_update") -> bool:
    safe = {k: v for k, v in updates.items() if k in _UPDATABLE_EXTRACTION_COLS}
    if not safe:
        return False
    old = get_extraction_by_id(quote_id)
    if old is None:
        return False
    changes = {k: [old.get(k), v] for k, v in safe.items() if old.get(k) != v}
    cols = sorted(safe.keys())
    set_clause = ", ".join(f'"{c}" = %s' for c in cols)
    params = [safe[c] for c in cols] + [quote_id]
    with db.get_cursor(commit=True) as cur:
        cur.execute(f"UPDATE extractions SET {set_clause} WHERE id = %s", params)
    if changes:
        _append_audit(quote_id, subject, changes, user, action=action)
    return True


def save_products(quote_id: str, subject: str, products: list, user: str) -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT jsonb_array_length(products) AS cnt FROM extractions WHERE id = %s", (quote_id,))
        row = cur.fetchone()
    if row is None:
        return
    old_count = row["cnt"] or 0
    with db.get_cursor(commit=True) as cur:
        cur.execute("UPDATE extractions SET products = %s WHERE id = %s",
                    (Json(products), quote_id))
    _append_audit(quote_id, subject,
                  {"produtos": [f"{old_count} itens", f"{len(products)} itens"]},
                  user, action="products_edit")


def append_products(quote_id: str, subject: str, new_products: list, user: str) -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT jsonb_array_length(products) AS cnt FROM extractions WHERE id = %s", (quote_id,))
        row = cur.fetchone()
    if row is None:
        return
    old_count = row["cnt"] or 0
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE extractions SET products = products || %s WHERE id = %s",
            (Json(new_products), quote_id),
        )
    new_count = old_count + len(new_products)
    _append_audit(quote_id, subject,
                  {"produtos": [f"{old_count} itens", f"{new_count} itens (+{len(new_products)})"]},
                  user, action="products_append")


def append_extraction_entry(quote: dict, user: str) -> None:
    _insert_extraction(quote)
    _append_audit(quote["id"], quote.get("subject", ""),
                  {"_criado": [None, quote["id"]]}, user, action="bulk_import_create")


def _insert_extraction(q: dict) -> None:
    with db.get_cursor(commit=True) as cur:
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
                Json(q.get("raw_email") or {}),
                Json(q.get("products") or []),
            ),
        )


# ── Annotations ───────────────────────────────────────────────────────────────

def load_annotations() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM annotations")
        return {r["quote_id"]: _str_dates(dict(r)) for r in cur.fetchall()}


def save_annotation(quote_id: str, subject: str, new_data: dict, user: str) -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM annotations WHERE quote_id = %s", (quote_id,))
        old = dict(cur.fetchone() or {})

    changes = {k: [old.get(k), v] for k, v in new_data.items() if old.get(k) != v}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO annotations (quote_id, status, valor_total, responsavel_interno,
                                     fornecedor, observacoes, entregue, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (quote_id) DO UPDATE SET
                status              = EXCLUDED.status,
                valor_total         = EXCLUDED.valor_total,
                responsavel_interno = EXCLUDED.responsavel_interno,
                fornecedor          = EXCLUDED.fornecedor,
                observacoes         = EXCLUDED.observacoes,
                entregue            = EXCLUDED.entregue,
                updated_at          = EXCLUDED.updated_at,
                updated_by          = EXCLUDED.updated_by
            """,
            (
                quote_id,
                new_data.get("status", "Em Aberto"),
                new_data.get("valor_total"),
                new_data.get("responsavel_interno", ""),
                new_data.get("fornecedor", ""),
                new_data.get("observacoes", ""),
                bool(new_data.get("entregue", False)),
                now_str,
                user,
            ),
        )
    if changes:
        _append_audit(quote_id, subject, changes, user)


# ── Corrections ───────────────────────────────────────────────────────────────

def load_corrections() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT quote_id, fields FROM corrections")
        return {r["quote_id"]: r["fields"] for r in cur.fetchall()}


def save_correction(quote_id: str, subject: str, fields: dict, user: str) -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT fields FROM corrections WHERE quote_id = %s", (quote_id,))
        row = cur.fetchone()
    entry = dict(row["fields"]) if row else {}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    changes = {}
    for field, new_val in fields.items():
        new_val = new_val.strip() if isinstance(new_val, str) else new_val
        current = entry.get(field, {}).get("current")
        if current == new_val:
            continue
        history = list(entry.get(field, {}).get("history", []))
        history.append({"value": current, "at": timestamp, "by": user})
        entry[field] = {"current": new_val, "history": history}
        changes[field] = [current, new_val]

    if not changes:
        return

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO corrections (quote_id, fields) VALUES (%s, %s)
            ON CONFLICT (quote_id) DO UPDATE SET fields = EXCLUDED.fields
            """,
            (quote_id, Json(entry)),
        )
    _append_audit(quote_id, subject, changes, user, action="correction")


# ── Audit log ─────────────────────────────────────────────────────────────────

def serialize_for_json(obj):
    """Recursively convert non-JSON-serializable types to JSON-safe types."""
    from decimal import Decimal
    from datetime import datetime, date

    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    return obj


def _append_audit(quote_id: str, subject: str, changes: dict, user: str, action: str = "edit") -> None:
    changes = serialize_for_json(changes)
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO audit_log (username, quote_id, subject, action, changes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user, quote_id, subject, action, Json(changes)),
        )


def load_audit_log() -> list:
    with db.get_cursor() as cur:
        cur.execute('SELECT * FROM audit_log ORDER BY "timestamp" DESC')
        rows = cur.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        row["timestamp"] = str(row.get("timestamp", ""))[:19]
        row["user"] = row.pop("username", "")
        result.append(row)
    return result


# ── Stats ──────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    now = datetime.now()

    # ── 1. Scalar totals ──────────────────────────────────────────────────────
    # One query: total, cotações, pedidos, valor_total, abertas — all via SQL
    # aggregation so no rows are loaded into Python memory.
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)                                                          AS total,
                COUNT(*) FILTER (WHERE e.request_type = 'Cotação')               AS cotacoes,
                COUNT(*) FILTER (WHERE e.request_type = 'Pedido')                AS pedidos,
                COALESCE(SUM(a.valor_total), 0)                                  AS valor_total,
                COUNT(*) FILTER (WHERE COALESCE(a.status, 'Em Aberto')
                                       IN ('Em Aberto', 'Em Análise'))           AS abertas
            FROM extractions e
            LEFT JOIN annotations a ON a.quote_id = e.id
            """
        )
        row = cur.fetchone()

    total       = int(row["total"])
    cotacoes    = int(row["cotacoes"])
    pedidos     = int(row["pedidos"])
    valor_total = float(row["valor_total"])
    abertas     = int(row["abertas"])
    fechadas    = total - abertas

    # ── 2. Count by request_type ──────────────────────────────────────────────
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(request_type, 'NA') AS label, COUNT(*) AS cnt
            FROM extractions
            GROUP BY request_type
            ORDER BY cnt DESC
            """
        )
        tipos_rows = cur.fetchall()

    chart_tipos = {
        "labels": [r["label"] for r in tipos_rows],
        "data":   [int(r["cnt"]) for r in tipos_rows],
    }

    # ── 3. Count by status ────────────────────────────────────────────────────
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(a.status, 'Em Aberto') AS label, COUNT(*) AS cnt
            FROM extractions e
            LEFT JOIN annotations a ON a.quote_id = e.id
            GROUP BY a.status
            ORDER BY cnt DESC
            """
        )
        status_rows = cur.fetchall()

    chart_status = {
        "labels": [r["label"] for r in status_rows],
        "data":   [int(r["cnt"]) for r in status_rows],
    }

    # ── 4. Top 5 departments ──────────────────────────────────────────────────
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT department AS label, COUNT(*) AS cnt
            FROM extractions
            WHERE department IS NOT NULL AND department <> '' AND department <> 'NA'
            GROUP BY department
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
        depto_rows = cur.fetchall()

    chart_deptos = {
        "labels": [r["label"][:25] for r in depto_rows],
        "data":   [int(r["cnt"]) for r in depto_rows],
    }

    # ── 5. Weekly buckets (last 8 weeks) ──────────────────────────────────────
    # week_idx = 7 means "this week", 0 means "7 weeks ago".
    # EXTRACT(EPOCH …) / 604800 gives fractional weeks; FLOOR gives whole weeks.
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT
                (7 - FLOOR(EXTRACT(EPOCH FROM (NOW() - date)) / 604800)::int) AS week_idx,
                COUNT(*) AS cnt
            FROM extractions
            WHERE date >= NOW() - INTERVAL '8 weeks'
            GROUP BY week_idx
            """
        )
        week_rows = cur.fetchall()

    week_map    = {int(r["week_idx"]): int(r["cnt"]) for r in week_rows
                   if 0 <= int(r["week_idx"]) <= 7}
    week_labels = [(now - timedelta(weeks=7 - i)).strftime("Sem %d/%m") for i in range(8)]
    week_data   = [week_map.get(i, 0) for i in range(8)]

    chart_semanas = {"labels": week_labels, "data": week_data}

    # ── 6. Top 10 fornecedores by cotações + pedidos ──────────────────────────
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT
                TRIM(a.fornecedor)                                              AS fornecedor,
                COUNT(*) FILTER (WHERE e.request_type = 'Cotação')             AS cotacoes,
                COUNT(*) FILTER (WHERE e.request_type = 'Pedido')              AS pedidos
            FROM annotations a
            JOIN extractions e ON e.id = a.quote_id
            WHERE a.fornecedor IS NOT NULL AND TRIM(a.fornecedor) <> ''
            GROUP BY TRIM(a.fornecedor)
            ORDER BY (COUNT(*) FILTER (WHERE e.request_type = 'Cotação')
                    + COUNT(*) FILTER (WHERE e.request_type = 'Pedido')) DESC
            LIMIT 10
            """
        )
        forn_rows = cur.fetchall()

    chart_fornecedor = {
        "labels":   [r["fornecedor"] for r in forn_rows],
        "cotacoes": [int(r["cotacoes"]) for r in forn_rows],
        "pedidos":  [int(r["pedidos"]) for r in forn_rows],
    }

    # ── 7. Timeline stages (etapas) ───────────────────────────────────────────
    # Fetch only (id, request_type, timeline dates) — no products/body/raw_email.
    # The first-incomplete-step logic is O(steps) per quote, not O(n*m) overall.
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.request_type, COALESCE(t.dates, '{}'::jsonb) AS dates
            FROM extractions e
            LEFT JOIN timelines t ON t.quote_id = e.id
            """
        )
        tl_rows = cur.fetchall()

    etapas: dict = defaultdict(int)
    for row in tl_rows:
        rtype      = row["request_type"] or "Cotação"
        steps_list = TIMELINE_STEPS.get(rtype, TIMELINE_STEPS["Cotação"])
        tl_dates   = row["dates"] or {}
        for step in steps_list:
            if not tl_dates.get(step["key"]):
                etapas[step["label"]] += 1
                break
        else:
            etapas["Concluído"] += 1

    chart_etapas = {"labels": list(etapas.keys()), "data": list(etapas.values())}

    # ── 8. Top 10 oldest active quotes ───────────────────────────────────────
    # Only 10 rows fetched; stage/age calculation done in Python on those 10.
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT
                e.id,
                e.subject,
                e.date,
                e.request_type,
                COALESCE(a.status, 'Em Aberto')    AS status,
                COALESCE(t.dates, '{}'::jsonb)     AS tl_dates
            FROM extractions e
            LEFT JOIN annotations a ON a.quote_id = e.id
            LEFT JOIN timelines   t ON t.quote_id = e.id
            WHERE COALESCE(a.status, 'Em Aberto') IN ('Em Aberto', 'Em Análise', 'Aprovada')
            ORDER BY e.date ASC
            LIMIT 10
            """
        )
        oldest_rows = cur.fetchall()

    def _parse_dt(d):
        try:
            return datetime.strptime(str(d)[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

    def _parse_step_date(d):
        try:
            return datetime.strptime(str(d), "%Y-%m-%d")
        except Exception:
            return None

    top10 = []
    for row in oldest_rows:
        rtype      = row["request_type"] or "Cotação"
        steps_list = TIMELINE_STEPS.get(rtype, TIMELINE_STEPS["Cotação"])
        tl_dates   = row["tl_dates"] or {}
        stage           = "Concluído"
        stage_entry     = _parse_dt(row["date"])
        last_step_entry = None
        for step in steps_list:
            step_date = _parse_step_date(tl_dates.get(step["key"], ""))
            if not step_date:
                stage = step["label"]
                break
            last_step_entry = step_date
        if last_step_entry:
            stage_entry = last_step_entry
        age = (now - stage_entry).days
        top10.append({
            "id":      row["id"],
            "subject": (row["subject"] or "—")[:55],
            "date":    str(row["date"] or "")[:10],
            "age":     age,
            "type":    rtype,
            "stage":   stage,
            "status":  row["status"],
        })

    return {
        "total":            total,
        "cotacoes":         cotacoes,
        "pedidos":          pedidos,
        "valor_total":      valor_total,
        "abertas":          abertas,
        "fechadas":         fechadas,
        "chart_tipos":      chart_tipos,
        "chart_status":     chart_status,
        "chart_deptos":     chart_deptos,
        "chart_semanas":    chart_semanas,
        "chart_fornecedor": chart_fornecedor,
        "chart_etapas":     chart_etapas,
        "top10":            top10,
    }


def compute_auto_forecast(quote: dict, timeline: dict, deal: dict) -> tuple:
    from datetime import date as _date, timedelta as _td

    ccw_delivery = deal.get("max_estimated_delivery", "") if deal else ""
    if ccw_delivery:
        return str(ccw_delivery), {"source": "CCW", "last_sync": deal.get("last_ccw_sync", "")}

    aggressor = None
    inicio_str = timeline.get("dates", {}).get("inicio_fabricacao", "")
    if not inicio_str:
        return None, None
    try:
        start = _date.fromisoformat(str(inicio_str)[:10])
    except ValueError:
        return None, None

    max_lt = 0
    for p in quote.get("products", []):
        lt_raw = str(p.get("lead_time") or "").strip()
        if lt_raw and lt_raw.upper() != "N/A":
            try:
                lt = int(float(lt_raw))
                if lt > max_lt:
                    max_lt = lt
                    aggressor = {"part_number": p.get("part_number", ""),
                                 "description": p.get("description", ""),
                                 "lead_time":   lt}
            except ValueError:
                pass
    if max_lt > 0:
        return (start + _td(days=max_lt + 10)).isoformat(), aggressor
    return None, None


def get_delivery_forecasts(after: str = "") -> list:
    quotes      = load_extractions()
    annotations = load_annotations()
    timelines   = load_timelines()
    deals       = load_deals()

    after_date = None
    if after:
        try:
            from datetime import datetime as _dt
            after_date = _dt.strptime(after, "%Y-%m-%d").date()
        except ValueError:
            after_date = None

    result = []
    for q in quotes:
        if q.get("request_type") != "Pedido":
            continue
        timeline = timelines.get(q["id"], {"dates": {}})
        deal     = deals.get(q["id"], {})
        forecast, _ = compute_auto_forecast(q, timeline, deal)
        if not forecast:
            continue
        try:
            from datetime import datetime as _dt
            forecast_date = _dt.strptime(forecast[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if after_date and forecast_date <= after_date:
            continue
        ann = annotations.get(q["id"], {})
        result.append({
            "id":         q["id"],
            "subject":    (q.get("subject") or "—")[:55],
            "forecast":   forecast_date.isoformat(),
            "fornecedor": ann.get("fornecedor") or "—",
            "status":     ann.get("status", "Em Aberto"),
        })

    result.sort(key=lambda r: r["forecast"], reverse=True)
    return result


# ── Deals ──────────────────────────────────────────────────────────────────────

def load_deals() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM deals")
        result = {}
        for r in cur.fetchall():
            row = _str_dates(dict(r))
            qid = row.pop("quote_id")
            result[qid] = row
        return result


def save_deal(quote_id: str, subject: str, data: dict, user: str) -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM deals WHERE quote_id = %s", (quote_id,))
        old_row = cur.fetchone()
    old = dict(old_row) if old_row else {}
    changes = {k: [old.get(k), v] for k, v in data.items() if old.get(k) != v and v}
    changes = serialize_for_json(changes)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    max_del = data.get("max_estimated_delivery") or None

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO deals (quote_id, projeto_id_vale, logicalis_id, ntt_id,
                               estimate_nacional, estimate_importado, order_id, deal_id,
                               last_ccw_sync, max_estimated_delivery, response_received_at,
                               updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (quote_id) DO UPDATE SET
                projeto_id_vale       = COALESCE(NULLIF(EXCLUDED.projeto_id_vale, ''),       deals.projeto_id_vale),
                logicalis_id          = COALESCE(NULLIF(EXCLUDED.logicalis_id, ''),          deals.logicalis_id),
                ntt_id                = COALESCE(NULLIF(EXCLUDED.ntt_id, ''),                deals.ntt_id),
                estimate_nacional     = COALESCE(NULLIF(EXCLUDED.estimate_nacional, ''),     deals.estimate_nacional),
                estimate_importado    = COALESCE(NULLIF(EXCLUDED.estimate_importado, ''),    deals.estimate_importado),
                order_id              = COALESCE(NULLIF(EXCLUDED.order_id, ''),              deals.order_id),
                deal_id               = COALESCE(NULLIF(EXCLUDED.deal_id, ''),               deals.deal_id),
                last_ccw_sync         = COALESCE(EXCLUDED.last_ccw_sync,                     deals.last_ccw_sync),
                max_estimated_delivery= COALESCE(EXCLUDED.max_estimated_delivery,            deals.max_estimated_delivery),
                response_received_at = COALESCE(EXCLUDED.response_received_at,               deals.response_received_at),
                updated_at            = EXCLUDED.updated_at,
                updated_by            = EXCLUDED.updated_by
            """,
            (
                quote_id,
                data.get("projeto_id_vale", ""),
                data.get("logicalis_id", ""),
                data.get("ntt_id", ""),
                data.get("estimate_nacional", ""),
                data.get("estimate_importado", ""),
                data.get("order_id", ""),
                data.get("deal_id", ""),
                data.get("last_ccw_sync") or None,
                max_del if max_del else None,
                data.get("response_received_at") or None,
                now_str,
                user,
            ),
        )
    if changes:
        _append_audit(quote_id, subject, changes, user, action="deal")


# ── Timelines ─────────────────────────────────────────────────────────────────

def load_timelines() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM timelines")
        return {r["quote_id"]: {"dates": r["dates"],
                                "updated_at": str(r["updated_at"] or "")[:19],
                                "updated_by": r["updated_by"] or ""}
                for r in cur.fetchall()}


def save_timeline(quote_id: str, subject: str, dates: dict, user: str, action: str = "timeline") -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT dates FROM timelines WHERE quote_id = %s", (quote_id,))
        row = cur.fetchone()
    old_dates = dict(row["dates"]) if row else {}
    changes = {k: [old_dates.get(k), v] for k, v in dates.items() if old_dates.get(k) != v}

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO timelines (quote_id, dates, updated_at, updated_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (quote_id) DO UPDATE SET
                dates      = EXCLUDED.dates,
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
            """,
            (quote_id, Json(dates), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user),
        )
    if changes:
        _append_audit(quote_id, subject, changes, user, action=action)


def apply_import_dates_to_timeline(quote_id: str, subject: str, request_type: str,
                                    solicitacao_date: str, resposta_date: str, user: str) -> None:
    """Deriva os 2 primeiros passos da Timeline a partir de 'Data da
    Solicitação' e 'Resposta da Cotação' (import batch, /admin/import) —
    o mesmo dado que já vira extractions.date/deals.response_received_at
    também alimenta 'Solicitação de Orçamento/Pedido' e 'Entrega do
    Orçamento'. Só preenche o que ainda estiver vazio; nunca sobrescreve
    uma data de timeline já existente (ex: avançada manualmente depois)."""
    if not solicitacao_date and not resposta_date:
        return

    first_step = "solicitacao_pedido" if request_type == "Pedido" else "solicitacao_orcamento"
    dates = dict(load_timelines().get(quote_id, {}).get("dates", {}))
    changed = False

    if solicitacao_date and not dates.get(first_step):
        dates[first_step] = solicitacao_date[:10]
        changed = True
    if resposta_date and not dates.get("entrega_orcamento"):
        dates["entrega_orcamento"] = resposta_date[:10]
        changed = True

    if changed:
        save_timeline(quote_id, subject, dates, user, action="bulk_import_update")


def check_and_advance_by_deadline(quote_id: str, subject: str, user: str) -> None:
    """Avança 'Entrega ao Parceiro' quando o prazo previsto (CCW ou estimativa
    calculada, vale a que estiver disponível) já passou, ou quando alguém marcou
    a cotação como entregue manualmente (checkbox 'Entregue' em Informações
    Manuais). Só se aplica a Pedidos — é a única etapa em jogo — e é idempotente:
    não faz nada se a etapa já tiver data preenchida. Prazo ausente não é erro
    (a maioria dos Pedidos ainda não tem um); prazo presente mas malformado é
    sinalizado no histórico como pendente de revisão, sem alterar dados.
    Chamado (1) a cada sync do bot de CCW (process_ccw_sync) e (2) ao salvar
    Informações Manuais no portal, para refletir o checkbox na hora.
    """
    from datetime import date as _date

    quote = get_extraction_by_id(quote_id)
    if not quote or quote.get("request_type") != "Pedido":
        return

    dates = dict(load_timelines().get(quote_id, {}).get("dates", {}))
    if dates.get("entrega_parceiro"):
        return  # já avançado

    entregue = bool(load_annotations().get(quote_id, {}).get("entregue", False))
    deal = load_deals().get(quote_id, {})

    forecast, _ = compute_auto_forecast(quote, {"dates": dates}, deal)

    delivery_date = None
    if forecast:
        try:
            forecast_date = _date.fromisoformat(str(forecast)[:10])
        except ValueError:
            _append_audit(
                quote_id, subject,
                {"_pendente_revisao": [None, f"prazo previsto inválido para avanço automático: {forecast!r}"]},
                user, action="deadline_check_pending",
            )
            return
        if entregue or forecast_date < _date.today():
            delivery_date = forecast_date
    elif entregue:
        delivery_date = _date.today()

    if delivery_date is None:
        return  # sem prazo vencido e não marcado como entregue: nada a fazer

    dates["entrega_parceiro"] = delivery_date.isoformat()
    save_timeline(quote_id, subject, dates, user, action="auto_advance_deadline")


# ── Pendências (itens que precisam de atenção humana) ──────────────────────────

STAGE_AGE_WARN_DAYS = 30
STAGE_AGE_CRITICAL_DAYS = 60
VENDOR_RESPONSE_WARN_DAYS = 15

_OPEN_STATUSES = ("Em Aberto", "Em Análise", "Aprovada")


def _days_since(date_str: str):
    """Dias corridos desde uma data em 'YYYY-MM-DD' ou 'YYYY-MM-DD HH:MM:SS'.
    Retorna None se vazia/não reconhecida (nunca lança)."""
    s = str(date_str or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return (datetime.now() - datetime.strptime(s[:19], fmt)).days
        except ValueError:
            continue
    return None


def get_pending_items() -> dict:
    """Itens que precisam de atenção humana, calculados sob demanda (sem
    escrever nada em lugar nenhum) — usado pelo badge 'Pendências' da sidebar,
    pela seção correspondente no Dashboard, e exposto via
    GET /api/v1/pending-items para o Bot-rotina consumir no futuro.

    - overdue_forecast: Pedido com prazo previsto (CCW ou estimado) já
      vencido, mas ainda não avançado para 'Entrega ao Parceiro' — mesma
      comparação de check_and_advance_by_deadline, sem o efeito colateral.
    - stuck_stage: cotação/pedido parado há mais de STAGE_AGE_WARN_DAYS na
      etapa atual (mesma lógica de idade do Top 10 do Dashboard, generalizada
      para todos os itens acima do limiar, não só os 10 primeiros).
    - pending_review: entradas 'deadline_check_pending' no histórico que
      ainda não tiveram um 'auto_advance_deadline' posterior para o mesmo
      quote_id (prazo malformado, nunca resolvido).
    - awaiting_vendor: cotação com fornecedor NTT/Logicalis sem
      deals.response_received_at preenchido há mais de VENDOR_RESPONSE_WARN_DAYS.
    """
    quotes      = load_extractions()
    annotations = load_annotations()
    timelines   = load_timelines()
    deals       = load_deals()

    overdue_forecast, stuck_stage, awaiting_vendor = [], [], []

    for q in quotes:
        ann = annotations.get(q["id"], {})
        if ann.get("status", "Em Aberto") not in _OPEN_STATUSES:
            continue

        timeline = timelines.get(q["id"], {"dates": {}})
        tl_dates = timeline.get("dates", {})

        if q.get("request_type") == "Pedido" and not tl_dates.get("entrega_parceiro"):
            deal = deals.get(q["id"], {})
            forecast, _ = compute_auto_forecast(q, timeline, deal)
            if forecast:
                try:
                    from datetime import date as _date
                    if _date.fromisoformat(str(forecast)[:10]) < _date.today():
                        overdue_forecast.append({
                            "quote_id": q["id"], "subject": q.get("subject", ""),
                            "dias": _days_since(forecast),
                        })
                except ValueError:
                    pass

        rtype = q.get("request_type") or "Cotação"
        steps_list = TIMELINE_STEPS.get(rtype, TIMELINE_STEPS["Cotação"])
        last_step_date = None
        for step in steps_list:
            val = tl_dates.get(step["key"], "")
            if not val:
                break
            last_step_date = val
        age = _days_since(last_step_date or q.get("date"))
        if age is not None and age > STAGE_AGE_WARN_DAYS:
            stuck_stage.append({"quote_id": q["id"], "subject": q.get("subject", ""), "dias": age})

        fornecedor = (ann.get("fornecedor") or "").strip()
        if fornecedor in ("NTT", "Logicalis"):
            deal = deals.get(q["id"], {})
            if not deal.get("response_received_at"):
                age_sent = _days_since(q.get("date"))
                if age_sent is not None and age_sent > VENDOR_RESPONSE_WARN_DAYS:
                    awaiting_vendor.append({
                        "quote_id": q["id"], "subject": q.get("subject", ""), "dias": age_sent,
                    })

    audit = load_audit_log()
    pending_by_quote = {}
    for entry in sorted(audit, key=lambda a: a.get("timestamp", "")):
        qid = entry.get("quote_id")
        if entry.get("action") == "deadline_check_pending":
            pending_by_quote[qid] = entry
        elif entry.get("action") == "auto_advance_deadline":
            pending_by_quote.pop(qid, None)
    pending_review = [
        {"quote_id": qid, "subject": e.get("subject", ""), "timestamp": e.get("timestamp", "")}
        for qid, e in pending_by_quote.items()
    ]

    return {
        "overdue_forecast": overdue_forecast,
        "stuck_stage":      stuck_stage,
        "pending_review":   pending_review,
        "awaiting_vendor":  awaiting_vendor,
        "total": len(overdue_forecast) + len(stuck_stage) + len(pending_review) + len(awaiting_vendor),
    }


_pending_count_cache = {"total": 0, "at": 0.0}
_PENDING_COUNT_CACHE_TTL = 60  # segundos


def get_pending_count_cached() -> int:
    """Versão cacheada (60s) de get_pending_items()['total'] — usada pelo
    badge da sidebar, que aparece em toda página. get_pending_items() faz
    5 consultas (extractions/annotations/timelines/deals/audit_log); rodar
    isso a cada navegação seria caro, então o badge usa este cache e só a
    página de Dashboard chama get_pending_items() direto, sem cache."""
    import time as _time
    now = _time.time()
    if now - _pending_count_cache["at"] > _PENDING_COUNT_CACHE_TTL:
        _pending_count_cache["total"] = get_pending_items()["total"]
        _pending_count_cache["at"] = now
    return _pending_count_cache["total"]


def get_distinct_names() -> dict:
    """Valores distintos já usados para nomes de pessoas, para alimentar
    autocomplete/datalist em vez de retranscrever o nome inteiro de novo."""
    with db.get_cursor() as cur:
        cur.execute("SELECT DISTINCT requester_name FROM extractions WHERE TRIM(requester_name) <> '' ORDER BY 1")
        requester_name = [r["requester_name"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT responsavel_interno FROM annotations WHERE TRIM(responsavel_interno) <> '' ORDER BY 1")
        responsavel_interno = [r["responsavel_interno"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT tech_lead FROM cisco_forecast WHERE TRIM(tech_lead) <> '' ORDER BY 1")
        tech_lead = [r["tech_lead"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT pm_name FROM cisco_forecast WHERE TRIM(pm_name) <> '' ORDER BY 1")
        pm_name = [r["pm_name"] for r in cur.fetchall()]
    return {
        "requester_name":      requester_name,
        "responsavel_interno": responsavel_interno,
        "tech_lead":           tech_lead,
        "pm_name":             pm_name,
    }


def find_related_quotes_other_vendor(quote_id: str) -> list:
    """Cotações de OUTRO vendor (NTT/Logicalis) que parecem ser do mesmo
    projeto (mesmo assunto normalizado). Só leitura — é um atalho de
    navegação entre as duas cotações, nunca mescla nada (mesma garantia de
    email_matcher.resolve(), que não é reaproveitado aqui de propósito)."""
    import email_matcher

    quote = get_extraction_by_id(quote_id)
    if not quote:
        return []
    own_fornecedor = (load_annotations().get(quote_id, {}).get("fornecedor") or "").strip()
    if own_fornecedor not in ("NTT", "Logicalis"):
        return []
    own_normalized = email_matcher.normalize_subject(quote.get("subject", ""))
    if not own_normalized:
        return []

    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.subject, a.fornecedor, COALESCE(a.status, 'Em Aberto') AS status
            FROM extractions e
            JOIN annotations a ON a.quote_id = e.id
            WHERE e.id <> %s AND a.fornecedor IN ('NTT', 'Logicalis') AND a.fornecedor <> %s
            """,
            (quote_id, own_fornecedor),
        )
        candidates = cur.fetchall()

    related = []
    for row in candidates:
        if email_matcher.normalize_subject(row["subject"] or "") == own_normalized:
            related.append({
                "quote_id":   row["id"],
                "subject":    row["subject"],
                "fornecedor": row["fornecedor"],
                "status":     row["status"],
            })
    return related


def find_duplicate_groups() -> list:
    """Agrupa cotações pelo mesmo assunto normalizado + mesmo fornecedor —
    candidatas a duplicata (ex.: histórico anterior à correlação de email).
    Só relatório para revisão manual em /admin/duplicates — nunca mescla."""
    import email_matcher

    quotes      = load_extractions()
    annotations = load_annotations()

    groups: dict = {}
    for q in quotes:
        ann = annotations.get(q["id"], {})
        fornecedor = (ann.get("fornecedor") or "").strip()
        if not fornecedor:
            continue  # vendor desconhecido — não agrupa (mesmo princípio do email_matcher: nunca correlacionar sem saber o vendor)
        normalized = email_matcher.normalize_subject(q.get("subject", ""))
        if not normalized:
            continue
        key = (normalized, fornecedor)
        groups.setdefault(key, []).append({
            "quote_id": q["id"],
            "subject":  q.get("subject", ""),
            "date":     q.get("date", ""),
            "status":   ann.get("status", "Em Aberto"),
        })

    result = [
        # "quotes", não "items" — em Jinja, g.items colidiria com o método dict.items()
        {"normalized": key[0], "fornecedor": key[1], "quotes": sorted(items, key=lambda i: i["date"])}
        for key, items in groups.items() if len(items) > 1
    ]
    result.sort(key=lambda g: len(g["quotes"]), reverse=True)
    return result


# ── CCW Bot sync ──────────────────────────────────────────────────────────────

def process_ccw_sync(quote_id: str, subject: str, order_id: str,
                     lines: list, user: str) -> dict:
    """
    Unified CCW sync. Detects scenario, computes final lead_time, creates products
    if needed, updates deals, and saves a validation report.
    """
    from collections import defaultdict as _dd

    quote_entry = get_extraction_by_id(quote_id)
    if quote_entry is None:
        return {"scenario": 0, "error": "quote not found"}

    # Deduplica CCW lines por part_number
    ccw_map  = {}
    qty_sum  = _dd(int)
    for ln in lines:
        pn = str(ln.get("part_number") or "").strip().upper()
        if not pn:
            continue
        try:
            qty_sum[pn] += int(float(ln.get("qty") or 0))
        except (ValueError, TypeError):
            pass
        lt = int(ln.get("lead_time_days") or 0)
        if pn not in ccw_map or lt > ccw_map[pn]["lead_time_days"]:
            ccw_map[pn] = {
                "part_number":        pn,
                "lead_time_days":     lt,
                "estimated_delivery": ln.get("estimated_delivery", ""),
            }

    ccw_parts       = set(ccw_map.keys())
    portal_products = list(quote_entry.get("products") or [])
    portal_parts    = {
        str(p.get("part_number") or "").strip().upper()
        for p in portal_products if p.get("part_number")
    }

    products_created = 0

    if not portal_products:
        scenario     = 2
        new_products = []
        for pn, data in ccw_map.items():
            new_products.append({
                "part_number":        pn,
                "qty":               str(qty_sum[pn]) if qty_sum[pn] else "1",
                "description":       "",
                "unit_list_price":   "",
                "lead_time":         str(data["lead_time_days"]),
                "discount_pct":      "0",
                "unit_net_price":    "",
                "extended_net_price": "",
                "tipo":              "",
                "arquitetura":       "",
                "categoria":         "",
            })
        with db.get_cursor(commit=True) as cur:
            cur.execute("UPDATE extractions SET products = %s WHERE id = %s",
                        (Json(new_products), quote_id))
        products_created = len(new_products)
        portal_parts  = ccw_parts.copy()
        intersection  = ccw_parts.copy()
        only_in_portal = set()
        only_in_ccw    = set()
        _append_audit(quote_id, subject,
                      {"ccw_products_created": [None,
                          f"cenário 2 — {products_created} produto(s) criados do XLS CCW"]},
                      user, action="ccw_sync")
    else:
        intersection   = portal_parts & ccw_parts
        only_in_portal = portal_parts - ccw_parts
        only_in_ccw    = ccw_parts    - portal_parts
        scenario = 1 if not only_in_portal else 3

    contributing = []
    max_lt_days  = 0
    max_delivery = None
    for pn in intersection:
        if pn in ccw_map:
            item = ccw_map[pn]
            contributing.append(item)
            if item["lead_time_days"] > max_lt_days:
                max_lt_days  = item["lead_time_days"]
                max_delivery = item["estimated_delivery"]
    contributing.sort(key=lambda x: x["lead_time_days"], reverse=True)

    deal_update = {
        "last_ccw_sync":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "max_estimated_delivery": max_delivery or "",
    }
    if order_id:
        deal_update["order_id"] = order_id
    save_deal(quote_id, subject, deal_update, user)

    # Roda a cada sync diário do bot de CCW — ver check_and_advance_by_deadline.
    check_and_advance_by_deadline(quote_id, subject, user)

    _append_audit(quote_id, subject,
                  {"ccw_sync": [None,
                      f"cenário={scenario} order={order_id} "
                      f"intersecção={len(intersection)} "
                      f"só_portal={len(only_in_portal)} "
                      f"só_ccw={len(only_in_ccw)} "
                      f"leadtime_final={max_lt_days}d delivery={max_delivery}"]},
                  user, action="ccw_sync")

    result = {
        "scenario":               scenario,
        "max_estimated_delivery": max_delivery,
        "max_lead_time_days":     max_lt_days,
        "products_created":       products_created,
        "intersection":           sorted(intersection),
        "only_in_portal":         sorted(only_in_portal),
        "only_in_ccw":            sorted(only_in_ccw),
        "contributing_items":     contributing,
    }
    _save_ccw_validation(quote_id, subject, order_id, result)
    return result


def _save_ccw_validation(quote_id: str, subject: str, order_id: str, result: dict) -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO ccw_validations
                (quote_id, subject, order_id, validated_at, scenario,
                 max_estimated_delivery, max_lead_time_days, products_created,
                 intersection, only_in_portal, only_in_ccw, contributing_items)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                quote_id, subject, order_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                result.get("scenario"),
                result.get("max_estimated_delivery") or None,
                result.get("max_lead_time_days"),
                result.get("products_created"),
                Json(result.get("intersection", [])),
                Json(result.get("only_in_portal", [])),
                Json(result.get("only_in_ccw", [])),
                Json(result.get("contributing_items", [])),
            ),
        )


# ── Users ─────────────────────────────────────────────────────────────────────

def load_users() -> list:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM users ORDER BY created_at")
        return [_str_dates(dict(r)) for r in cur.fetchall()]


def verify_user(username: str, password: str):
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def list_users_safe() -> list:
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in load_users()]


def username_exists(username: str) -> bool:
    with db.get_cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        return cur.fetchone() is not None


def create_user(username: str, password: str, role: str = "viewer",
                nome: str = "", email: str = "", celular: str = "", empresa: str = "") -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, nome, email, celular, empresa, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            (
                username,
                generate_password_hash(password, method="pbkdf2:sha256"),
                role, nome, email, celular, empresa,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )


def delete_user(username: str) -> bool:
    with db.get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM users WHERE username = %s", (username,))
        return cur.rowcount > 0


def get_fx_rate_override() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM fx_rate_override WHERE id = 1")
        row = cur.fetchone()
    return _str_dates(dict(row)) if row else {}


def set_fx_rate_override(rate: float, user: str) -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO fx_rate_override (id, rate, updated_at, updated_by)
            VALUES (1, %s, now(), %s)
            ON CONFLICT (id) DO UPDATE SET
                rate       = EXCLUDED.rate,
                updated_at = now(),
                updated_by = EXCLUDED.updated_by
            """,
            (rate, user),
        )


def clear_fx_rate_override() -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM fx_rate_override WHERE id = 1")


def get_effective_fx_rate() -> tuple:
    """(rate, is_live, is_manual, updated_by). Um override manual salvo em
    fx_rate_override tem prioridade sobre a cotação automática buscada em
    fx_rate.get_usd_brl_rate — usado tanto no Spend Analysis quanto no
    Forecast de Vendas, que compartilham a mesma cotação do dólar."""
    import fx_rate

    override = get_fx_rate_override()
    if override.get("rate"):
        return float(override["rate"]), True, True, override.get("updated_by", "")
    rate, is_live = fx_rate.get_usd_brl_rate()
    return rate, is_live, False, ""


def get_cisco_spend_stats() -> dict:
    """Aggregates (unit_net_price × qty) per product across all quotes, em USD.
    Produtos 'Nacional' são cotados em Real pelos distribuidores — convertidos
    para USD pela cotação atual (fx_rate) antes de somar com 'Importado'.
    Returns totals grouped by fornecedor, arquitetura, and department."""
    import fx_rate

    def _num(s):
        try:
            return float(str(s or "0").strip().replace(",", ""))
        except ValueError:
            return 0.0

    def _sort(d):
        items = sorted(d.items(), key=lambda x: x[1], reverse=True)
        return {"labels": [k for k, v in items], "data": [round(v, 2) for k, v in items]}

    quotes      = load_extractions()
    annotations = load_annotations()
    rate, rate_is_live, rate_is_manual, _ = get_effective_fx_rate()

    by_fornecedor  = {}
    by_arquitetura = {}
    by_department  = {}
    grand_total    = 0.0

    for q in quotes:
        ann        = annotations.get(q["id"], {})
        fornecedor = (ann.get("fornecedor") or "").strip() or "Não informado"
        department = (q.get("department") or "").strip() or "Não informado"

        for p in (q.get("products") or []):
            unp = _num(p.get("unit_net_price"))
            qty = max(_num(p.get("qty") or "1"), 1)
            if unp <= 0:
                continue
            value = fx_rate.to_usd(unp, p.get("tipo"), rate) * qty
            grand_total += value

            by_fornecedor[fornecedor]  = by_fornecedor.get(fornecedor, 0.0)  + value
            by_department[department]  = by_department.get(department, 0.0)  + value

            arq = (p.get("arquitetura") or "").strip() or "Não informado"
            by_arquitetura[arq] = by_arquitetura.get(arq, 0.0) + value

    return {
        "total":           round(grand_total, 2),
        "n_fornecedores":  len(by_fornecedor),
        "n_arquiteturas":  len(by_arquitetura),
        "n_departamentos": len(by_department),
        "by_fornecedor":   _sort(by_fornecedor),
        "by_arquitetura":  _sort(by_arquitetura),
        "by_department":   _sort(by_department),
        "fx_rate":         rate,
        "fx_rate_is_live": rate_is_live,
        "fx_rate_is_manual": rate_is_manual,
    }


def get_discount_history() -> list[dict]:
    """Returns min/avg/max discount_pct per part_number+arquitetura for Logicalis and NTT."""
    sql = """
        WITH pd AS (
            SELECT
                UPPER(TRIM(p->>'part_number'))                           AS part_number,
                COALESCE(NULLIF(TRIM(p->>'arquitetura'), ''), 'Não informado') AS arquitetura,
                e.date                                                   AS quote_date,
                CASE
                    WHEN LOWER(a.fornecedor) LIKE '%%logicalis%%' THEN 'Logicalis'
                    WHEN LOWER(a.fornecedor) LIKE '%%ntt%%'       THEN 'NTT'
                END AS fornecedor,
                (p->>'discount_pct')::NUMERIC                            AS discount_pct
            FROM extractions e
            JOIN annotations a ON e.id = a.quote_id
            CROSS JOIN LATERAL jsonb_array_elements(e.products) AS p
            WHERE (LOWER(a.fornecedor) LIKE '%%logicalis%%' OR LOWER(a.fornecedor) LIKE '%%ntt%%')
              AND TRIM(COALESCE(p->>'part_number', '')) <> ''
              AND COALESCE(p->>'discount_pct', '') <> ''
              AND (p->>'discount_pct')::NUMERIC > 0
        )
        SELECT
            part_number,
            arquitetura,
            fornecedor,
            ROUND(MIN(discount_pct), 2) AS min_desc,
            ROUND(AVG(discount_pct), 2) AS avg_desc,
            ROUND(MAX(discount_pct), 2) AS max_desc,
            MAX(quote_date)             AS ultima_cotacao,
            COUNT(*)                    AS ocorrencias
        FROM pd
        WHERE part_number <> ''
        GROUP BY part_number, arquitetura, fornecedor
        ORDER BY arquitetura, part_number, fornecedor
    """
    with db.get_cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    # _raw_dt holds the max datetime for comparison; formatted at the end
    pivot: dict[tuple, dict] = {}
    raw_dt: dict[tuple, object] = {}

    for row in rows:
        key  = (row["part_number"], row["arquitetura"])
        forn = row["fornecedor"]
        if key not in pivot:
            pivot[key] = {
                "part_number":    row["part_number"],
                "arquitetura":    row["arquitetura"],
                "logicalis":      None,
                "ntt":            None,
                "ultima_cotacao": None,
            }
            raw_dt[key] = None

        dt = row["ultima_cotacao"]
        entry = {
            "min":   float(row["min_desc"]),
            "avg":   float(row["avg_desc"]),
            "max":   float(row["max_desc"]),
            "count": int(row["ocorrencias"]),
        }
        if forn == "Logicalis":
            pivot[key]["logicalis"] = entry
        elif forn == "NTT":
            pivot[key]["ntt"] = entry

        if dt and (raw_dt[key] is None or dt > raw_dt[key]):
            raw_dt[key] = dt

    for key, rec in pivot.items():
        dt = raw_dt[key]
        rec["ultima_cotacao"] = dt.strftime("%d/%m/%Y") if dt else None

    return sorted(pivot.values(), key=lambda x: (x["arquitetura"], x["part_number"]))


def _vendor_avg_discount() -> dict:
    """Desconto médio geral por fornecedor (todos os part numbers), usado como
    fallback em get_sales_forecast quando um part number específico ainda não
    tem histórico de desconto (comum em projetos de forecast ainda não fechados)."""
    sql = """
        SELECT
            CASE
                WHEN LOWER(a.fornecedor) LIKE '%%logicalis%%' THEN 'Logicalis'
                WHEN LOWER(a.fornecedor) LIKE '%%ntt%%'       THEN 'NTT'
            END AS fornecedor,
            ROUND(AVG((p->>'discount_pct')::NUMERIC), 2) AS avg_desc
        FROM extractions e
        JOIN annotations a ON e.id = a.quote_id
        CROSS JOIN LATERAL jsonb_array_elements(e.products) AS p
        WHERE (LOWER(a.fornecedor) LIKE '%%logicalis%%' OR LOWER(a.fornecedor) LIKE '%%ntt%%')
          AND COALESCE(p->>'discount_pct', '') <> ''
          AND (p->>'discount_pct')::NUMERIC > 0
        GROUP BY 1
    """
    with db.get_cursor() as cur:
        cur.execute(sql)
        return {r["fornecedor"]: float(r["avg_desc"]) for r in cur.fetchall() if r["fornecedor"]}


def _compute_project_value(products: list, fornecedor: str, discount_pivot: dict, vendor_avg: dict,
                            fx_rate_value: float = 0.0) -> tuple:
    """Soma unit_list_price × qty × (1 - desconto médio) por produto, em USD.
    Produtos 'Nacional' vêm cotados em Real pelos distribuidores — convertidos
    para USD por fx_rate_value antes de aplicar o desconto. Usa o desconto
    médio do part number específico (Histórico de Descontos) quando
    disponível; senão cai para a média geral do fornecedor. Retorna
    (valor_total, usou_fallback_em_algum_produto, valor_por_arquitetura)."""
    import fx_rate

    def _num(s):
        try:
            return float(str(s or "0").strip().replace(",", ""))
        except ValueError:
            return 0.0

    forn_key = fornecedor.lower()
    total = 0.0
    used_fallback = False
    by_arch = {}

    for p in products or []:
        pn = str(p.get("part_number") or "").strip().upper()
        list_price = _num(p.get("unit_list_price"))
        if not pn or list_price <= 0:
            continue
        list_price = fx_rate.to_usd(list_price, p.get("tipo"), fx_rate_value)
        qty = _num(p.get("qty") or "1") or 1.0
        arq = (p.get("arquitetura") or "").strip() or "Não informado"

        row = discount_pivot.get((pn, arq))
        entry = row.get(forn_key) if row else None
        if entry and entry.get("avg") is not None:
            desconto = entry["avg"]
        else:
            desconto = vendor_avg.get(fornecedor)
            used_fallback = True
        if desconto is None:
            desconto = 0.0
            used_fallback = True

        item_value = list_price * qty * (1 - desconto / 100)
        total += item_value
        by_arch[arq] = by_arch.get(arq, 0.0) + item_value

    by_arch = {k: round(v, 2) for k, v in by_arch.items()}
    return round(total, 2), used_fallback, by_arch


def load_cisco_forecast() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM cisco_forecast")
        return {r["quote_id"]: _str_dates(dict(r)) for r in cur.fetchall()}


def save_cisco_forecast(quote_id: str, subject: str, data: dict, user: str) -> None:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM cisco_forecast WHERE quote_id = %s", (quote_id,))
        old = dict(cur.fetchone() or {})
    changes = {k: [old.get(k), v] for k, v in data.items() if old.get(k) != v}
    changes = serialize_for_json(changes)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cisco_forecast (quote_id, booking_date, tech_lead, pm_name,
                                        status, projeto_capital, kec, vbm,
                                        projeto_obsolescencia, prioridade_quarter,
                                        proxima_acao, proxima_acao_data,
                                        economic_buyer, champion, competition,
                                        updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (quote_id) DO UPDATE SET
                booking_date          = EXCLUDED.booking_date,
                tech_lead             = EXCLUDED.tech_lead,
                pm_name               = EXCLUDED.pm_name,
                status                = EXCLUDED.status,
                projeto_capital       = EXCLUDED.projeto_capital,
                kec                   = EXCLUDED.kec,
                vbm                   = EXCLUDED.vbm,
                projeto_obsolescencia = EXCLUDED.projeto_obsolescencia,
                prioridade_quarter    = EXCLUDED.prioridade_quarter,
                proxima_acao          = EXCLUDED.proxima_acao,
                proxima_acao_data     = EXCLUDED.proxima_acao_data,
                economic_buyer        = EXCLUDED.economic_buyer,
                champion              = EXCLUDED.champion,
                competition           = EXCLUDED.competition,
                updated_at            = EXCLUDED.updated_at,
                updated_by            = EXCLUDED.updated_by
            """,
            (
                quote_id,
                data.get("booking_date") or None,
                data.get("tech_lead", ""),
                data.get("pm_name", ""),
                data.get("status") or "Pipeline",
                bool(data.get("projeto_capital")),
                bool(data.get("kec")),
                bool(data.get("vbm")),
                bool(data.get("projeto_obsolescencia")),
                bool(data.get("prioridade_quarter")),
                data.get("proxima_acao", ""),
                data.get("proxima_acao_data") or None,
                data.get("economic_buyer", ""),
                data.get("champion", ""),
                data.get("competition", ""),
                now_str,
                user,
            ),
        )
    if changes:
        _append_audit(quote_id, subject, changes, user, action="cisco_forecast")


# Bucket da visão por arquitetura para cotações valoradas pelo Valor Total
# manual (sem XLS de produtos — não há como saber a arquitetura)
SEM_ARQUITETURA = "Sem produtos cadastrados"

# Flags de classificação do projeto (aba Forecast da área Cisco)
FORECAST_FLAGS = ["projeto_capital", "kec", "vbm", "projeto_obsolescencia", "prioridade_quarter"]


def _meddpicc_score(item: dict, has_forecast_record: bool) -> int:
    """Completude do deal segundo o MEDDPICC (0–8), um ponto por critério:
    Metrics = valor calculado > 0; Economic Buyer = campo preenchido;
    Decision Criteria = status classificado manualmente (registro salvo);
    Decision Process = data de booking definida; Paper Process = próxima
    ação registrada; Identify Pain = alguma flag de classificação marcada;
    Champion = campo preenchido; Competition = campo preenchido."""
    criteria = [
        item["valor"] > 0,
        bool(item["economic_buyer"]),
        has_forecast_record,
        bool(item["booking_date"]),
        bool(item["proxima_acao"]),
        any(item[f] for f in FORECAST_FLAGS),
        bool(item["champion"]),
        bool(item["competition"]),
    ]
    return sum(criteria)


def _pivot_forecast_items(items: list, dimension: str) -> list:
    """Pivot dos itens do forecast por uma dimensão × estágio. `dimension` é
    'departamento' (valor cheio do item por depto) ou 'valor_por_arquitetura'
    (rateado pelo breakdown por arquitetura). Retorna linhas
    {label, stages: {status: valor}, total} ordenadas por total desc."""
    rows = {}
    for item in items:
        status = item["status"]
        if dimension == "valor_por_arquitetura":
            parts = item["valor_por_arquitetura"].items()
        else:
            parts = [(item[dimension], item["valor"])]
        for label, valor in parts:
            row = rows.setdefault(label, {"label": label, "stages": {s: 0.0 for s in FORECAST_STATUSES}, "total": 0.0})
            row["stages"][status] = round(row["stages"].get(status, 0.0) + valor, 2)
            row["total"] = round(row["total"] + valor, 2)
    return sorted(rows.values(), key=lambda r: r["total"], reverse=True)


def get_sales_forecast() -> dict:
    """Forecast de vendas (área Cisco): um item por Cotação (não Pedido — uma
    vez que virou Pedido já foi bookado, sai do forecast) com fornecedor NTT
    ou Logicalis, ainda em aberto (exclui Perdida/Rejeitada). Nome do projeto:
    projeto_id_vale quando existir, senão o assunto normalizado (mesma limpeza
    usada na correlação de email). Valor em USD — Nacional é convertido pela
    cotação atual do dólar (fx_rate); sem produtos, cai para o Valor Total
    manual (já digitado em US$, sem precisar de conversão)."""
    import email_matcher

    quotes      = load_extractions()
    annotations = load_annotations()
    deals       = load_deals()
    forecasts   = load_cisco_forecast()

    discount_pivot = {(row["part_number"], row["arquitetura"]): row for row in get_discount_history()}
    vendor_avg = _vendor_avg_discount()
    rate, rate_is_live, rate_is_manual, rate_updated_by = get_effective_fx_rate()

    items = []
    for q in quotes:
        if q.get("request_type") != "Cotação":
            continue
        ann = annotations.get(q["id"], {})
        fornecedor = (ann.get("fornecedor") or "").strip()
        if fornecedor not in ("NTT", "Logicalis"):
            continue
        if ann.get("status") in ("Perdida", "Rejeitada"):
            continue

        deal = deals.get(q["id"], {})
        fc   = forecasts.get(q["id"], {})

        projeto = (deal.get("projeto_id_vale") or "").strip()
        if not projeto:
            projeto = email_matcher.normalize_subject(q.get("subject", "")) or q.get("subject", "") or "—"

        valor, used_fallback, by_arch = _compute_project_value(
            q.get("products", []), fornecedor, discount_pivot, vendor_avg, rate
        )

        # Sem nenhum produto contribuindo com preço — cai para o Valor Total
        # manual (Informações Manuais), que já é digitado em US$ — não precisa
        # de conversão. Dois motivos distintos geram esse caso: (a) a cotação
        # realmente não tem produtos cadastrados (comum em importação em lote
        # sem XLS de produtos); ou (b) tem produtos, mas sem preço de lista —
        # comum quando vieram só da sincronização com o CCW (que traz part
        # number/qty/lead time, não preço). Distinguir os dois evita o tooltip
        # dizer "sem produtos" quando na verdade há produtos sem preço.
        n_produtos = len(q.get("products") or [])
        valor_origem = "produtos"
        if valor <= 0:
            valor_total_usd = ann.get("valor_total")
            if valor_total_usd:
                valor = round(float(valor_total_usd), 2)
                valor_origem = "valor_total"

        # Valor manual não tem produtos — sem arquitetura conhecida, mas o
        # total da visão por arquitetura precisa fechar com o total geral.
        if valor > 0 and not by_arch:
            by_arch = {SEM_ARQUITETURA: valor}

        departamento = (q.get("department") or "").strip()
        if not departamento or departamento.upper() == "NA":
            departamento = "Não informado"

        item = {
            "quote_id":       q["id"],
            "projeto":        projeto,
            "fornecedor":     fornecedor,
            "valor":          valor,
            "valor_fallback": used_fallback,
            "valor_origem":   valor_origem,
            "produtos_sem_preco": valor_origem == "valor_total" and n_produtos > 0,
            "n_produtos":     n_produtos,
            "valor_por_arquitetura": by_arch,
            "departamento":   departamento,
            "deal_id":        deal.get("deal_id", ""),
            "booking_date":   fc.get("booking_date", "") or "",
            "tech_lead":      fc.get("tech_lead", "") or "",
            "pm_name":        fc.get("pm_name", "") or "",
            "status":         fc.get("status") or "Pipeline",
            "projeto_capital":       bool(fc.get("projeto_capital")),
            "kec":                   bool(fc.get("kec")),
            "vbm":                   bool(fc.get("vbm")),
            "projeto_obsolescencia": bool(fc.get("projeto_obsolescencia")),
            "prioridade_quarter":    bool(fc.get("prioridade_quarter")),
            "proxima_acao":          fc.get("proxima_acao", "") or "",
            "proxima_acao_data":     fc.get("proxima_acao_data", "") or "",
            "economic_buyer":        fc.get("economic_buyer", "") or "",
            "champion":              fc.get("champion", "") or "",
            "competition":           fc.get("competition", "") or "",
            "updated_at":            fc.get("updated_at", "") or "",
            "updated_by":            fc.get("updated_by", "") or "",
        }
        item["meddpicc_score"] = _meddpicc_score(item, has_forecast_record=bool(fc))
        items.append(item)

    items.sort(key=lambda r: (r["prioridade_quarter"], r["valor"]), reverse=True)
    return {
        "items":           items,
        "by_department":   _pivot_forecast_items(items, "departamento"),
        "by_architecture": _pivot_forecast_items(items, "valor_por_arquitetura"),
        "fx_rate":            rate,
        "fx_rate_is_live":    rate_is_live,
        "fx_rate_is_manual":  rate_is_manual,
        "fx_rate_updated_by": rate_updated_by,
    }


def change_password(username: str, current_password: str, new_password: str) -> tuple[bool, str]:
    """Verify current password then update to new hash. Returns (ok, error_msg)."""
    user = verify_user(username, current_password)
    if not user:
        return False, "Senha atual incorreta."
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE username = %s",
            (generate_password_hash(new_password, method="pbkdf2:sha256"), username),
        )
    return True, ""


def save_bot_status(runs: list, order_errors: dict, token_info: dict) -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO bot_status (id, pushed_at, runs, order_errors, token_info)
            VALUES (1, now(), %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                pushed_at    = now(),
                runs         = EXCLUDED.runs,
                order_errors = EXCLUDED.order_errors,
                token_info   = EXCLUDED.token_info
            """,
            (Json(runs), Json(order_errors), Json(token_info)),
        )


def load_bot_status() -> dict:
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM bot_status WHERE id = 1")
        row = cur.fetchone()
    if not row:
        return {"runs": [], "order_errors": {}, "token_info": {}, "pushed_at": None}
    return _str_dates(dict(row))


def ensure_default_user() -> None:
    if not load_users():
        create_user("admin", "admin123", role="admin")
        print("  [portal] Usuário padrão criado → admin / admin123  ⚠️  ALTERE A SENHA!")


# ── Favoritos ────────────────────────────────────────────────────────────────

def list_favorites(username: str) -> list:
    """IDs das cotações favoritadas por este usuário, mais recentes primeiro."""
    with db.get_cursor() as cur:
        cur.execute(
            "SELECT quote_id FROM favorites WHERE username = %s ORDER BY created_at DESC",
            (username,),
        )
        return [r["quote_id"] for r in cur.fetchall()]


def is_favorite(username: str, quote_id: str) -> bool:
    with db.get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM favorites WHERE username = %s AND quote_id = %s",
            (username, quote_id),
        )
        return cur.fetchone() is not None


def add_favorite(username: str, quote_id: str) -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO favorites (username, quote_id) VALUES (%s, %s)
            ON CONFLICT (username, quote_id) DO NOTHING
            """,
            (username, quote_id),
        )


def remove_favorite(username: str, quote_id: str) -> None:
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM favorites WHERE username = %s AND quote_id = %s",
            (username, quote_id),
        )


def toggle_favorite(username: str, quote_id: str) -> bool:
    """Alterna o favorito e retorna o novo estado (True = favoritado)."""
    if is_favorite(username, quote_id):
        remove_favorite(username, quote_id)
        return False
    add_favorite(username, quote_id)
    return True
