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
    "project_ref", "is_manual", "is_bulk_import",
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


def update_extraction_fields(quote_id: str, updates: dict, subject: str, user: str) -> bool:
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
        _append_audit(quote_id, subject, changes, user, action="bulk_import_update")
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
                                     fornecedor, observacoes, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (quote_id) DO UPDATE SET
                status              = EXCLUDED.status,
                valor_total         = EXCLUDED.valor_total,
                responsavel_interno = EXCLUDED.responsavel_interno,
                fornecedor          = EXCLUDED.fornecedor,
                observacoes         = EXCLUDED.observacoes,
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

def _append_audit(quote_id: str, subject: str, changes: dict, user: str, action: str = "edit") -> None:
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
    quotes = load_extractions()
    annotations = load_annotations()

    for q in quotes:
        ann = annotations.get(q["id"], {})
        q["_status"] = ann.get("status", "Em Aberto")
        q["_valor"] = ann.get("valor_total") or 0

    total     = len(quotes)
    cotacoes  = sum(1 for q in quotes if q.get("request_type") == "Cotação")
    pedidos   = sum(1 for q in quotes if q.get("request_type") == "Pedido")
    valor_total = sum(float(q["_valor"]) for q in quotes if q["_valor"])
    abertas   = sum(1 for q in quotes if q["_status"] in ("Em Aberto", "Em Análise"))
    fechadas  = total - abertas

    tipos = defaultdict(int)
    for q in quotes:
        tipos[q.get("request_type", "NA")] += 1

    statuses = defaultdict(int)
    for q in quotes:
        statuses[q["_status"]] += 1

    deptos = defaultdict(int)
    for q in quotes:
        d = q.get("department", "NA")
        if d and d != "NA":
            deptos[d] += 1
    top_deptos = sorted(deptos.items(), key=lambda x: -x[1])[:5]

    now = datetime.now()
    weeks: dict = defaultdict(int)
    for q in quotes:
        try:
            qdate = datetime.strptime(str(q["date"])[:19], "%Y-%m-%d %H:%M:%S")
            w = (now - qdate).days // 7
            if 0 <= w < 8:
                weeks[7 - w] += 1
        except Exception:
            pass
    week_labels = [(now - timedelta(weeks=7 - i)).strftime("Sem %d/%m") for i in range(8)]
    week_data   = [weeks[i] for i in range(8)]

    # ── Operacional ──────────────────────────────────────────────────────────
    forn_data: dict = defaultdict(lambda: {"Cotação": 0, "Pedido": 0})
    for q in quotes:
        ann  = annotations.get(q["id"], {})
        forn = (ann.get("fornecedor") or "").strip()
        if not forn:
            continue
        forn_data[forn][q.get("request_type", "Cotação")] += 1
    sorted_forn = sorted(forn_data.items(), key=lambda x: -(x[1]["Cotação"] + x[1]["Pedido"]))[:10]

    timelines = load_timelines()
    etapas: dict = defaultdict(int)
    for q in quotes:
        rtype      = q.get("request_type", "Cotação")
        steps_list = TIMELINE_STEPS.get(rtype, TIMELINE_STEPS["Cotação"])
        tl_dates   = timelines.get(q["id"], {}).get("dates", {})
        for step in steps_list:
            if not tl_dates.get(step["key"]):
                etapas[step["label"]] += 1
                break
        else:
            etapas["Concluído"] += 1

    # Top 10 mais antigos ativos — idade na etapa atual
    def _parse_date(d):
        try:
            return datetime.strptime(str(d)[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

    def _parse_step_date(d):
        try:
            return datetime.strptime(str(d), "%Y-%m-%d")
        except Exception:
            return None

    active = [q for q in quotes if q["_status"] in {"Em Aberto", "Em Análise", "Aprovada"}]
    oldest = sorted(active, key=lambda q: _parse_date(q.get("date", "")))[:10]
    top10  = []
    for q in oldest:
        rtype      = q.get("request_type", "Cotação")
        steps_list = TIMELINE_STEPS.get(rtype, TIMELINE_STEPS["Cotação"])
        tl_dates   = timelines.get(q["id"], {}).get("dates", {})
        stage           = "Concluído"
        stage_entry     = _parse_date(q.get("date", ""))
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
            "id":      q["id"],
            "subject": (q.get("subject") or "—")[:55],
            "date":    str(q.get("date", ""))[:10],
            "age":     age,
            "type":    rtype,
            "stage":   stage,
            "status":  q["_status"],
        })

    return {
        "total":       total,
        "cotacoes":    cotacoes,
        "pedidos":     pedidos,
        "valor_total": valor_total,
        "abertas":     abertas,
        "fechadas":    fechadas,
        "chart_tipos":   {"labels": list(tipos.keys()),   "data": list(tipos.values())},
        "chart_status":  {"labels": list(statuses.keys()), "data": list(statuses.values())},
        "chart_deptos":  {"labels": [d[0][:25] for d in top_deptos], "data": [d[1] for d in top_deptos]},
        "chart_semanas": {"labels": week_labels, "data": week_data},
        "chart_fornecedor": {
            "labels":   [f[0] for f in sorted_forn],
            "cotacoes": [f[1]["Cotação"] for f in sorted_forn],
            "pedidos":  [f[1]["Pedido"]  for f in sorted_forn],
        },
        "chart_etapas": {"labels": list(etapas.keys()), "data": list(etapas.values())},
        "top10": top10,
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

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    max_del = data.get("max_estimated_delivery") or None

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO deals (quote_id, projeto_id_vale, logicalis_id, ntt_id,
                               estimate_nacional, estimate_importado, order_id, deal_id,
                               last_ccw_sync, max_estimated_delivery, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def save_timeline(quote_id: str, subject: str, dates: dict, user: str) -> None:
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
        _append_audit(quote_id, subject, changes, user, action="timeline")


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


def ensure_default_user() -> None:
    if not load_users():
        create_user("admin", "admin123", role="admin")
        print("  [portal] Usuário padrão criado → admin / admin123  ⚠️  ALTERE A SENHA!")
