import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR        = Path("data")
EXTRACTIONS_F   = Path("extractions.json")
ANNOTATIONS_F   = DATA_DIR / "annotations.json"
CORRECTIONS_F   = DATA_DIR / "corrections.json"
AUDIT_LOG_F     = DATA_DIR / "audit_log.json"
USERS_F         = DATA_DIR / "users.json"

CORRECTABLE_FIELDS = [
    "requester_name", "department", "request_type", "project_type",
    "cnpj", "smart_account", "smart_account_domain", "virtual_account", "project_ref",
]

TIMELINES_F       = DATA_DIR / "timelines.json"
DEALS_F           = DATA_DIR / "deals.json"
CCW_VALIDATIONS_F = DATA_DIR / "ccw_validations.json"

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


def _ensure() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def _stable_id(q: dict) -> str:
    key = f"{q.get('date','')}{q.get('from','')}{q.get('subject','')}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# ── Extractions ───────────────────────────────────────────────────────────────

def load_extractions() -> list:
    if not EXTRACTIONS_F.exists():
        return []
    quotes = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8"))
    for q in quotes:
        if "id" not in q:
            q["id"] = _stable_id(q)
    return list(reversed(quotes))  # newest first


def find_quote_by_deal_field(key: str, value: str):
    """Returns quote_id if any deal entry has deals[id][key] == value, else None."""
    if not value:
        return None
    for quote_id, deal in load_deals().items():
        if (deal.get(key) or "").strip() == value.strip():
            return quote_id
    return None


def get_extraction_by_id(quote_id: str):
    if not EXTRACTIONS_F.exists():
        return None
    entries = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8"))
    for q in entries:
        if "id" not in q:
            q["id"] = _stable_id(q)
        if q["id"] == quote_id:
            return q
    return None


def update_extraction_fields(quote_id: str, updates: dict, subject: str, user: str) -> bool:
    if not EXTRACTIONS_F.exists():
        return False
    entries = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8"))
    for entry in entries:
        if "id" not in entry:
            entry["id"] = _stable_id(entry)
        if entry["id"] == quote_id:
            changes = {k: [entry.get(k), v] for k, v in updates.items() if entry.get(k) != v}
            entry.update(updates)
            EXTRACTIONS_F.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            if changes:
                _append_audit(quote_id, subject, changes, user, action="bulk_import_update")
            return True
    return False


def save_products(quote_id: str, subject: str, products: list, user: str) -> None:
    if not EXTRACTIONS_F.exists():
        return
    entries = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8"))
    for entry in entries:
        if "id" not in entry:
            entry["id"] = _stable_id(entry)
        if entry["id"] == quote_id:
            old_count = len(entry.get("products", []))
            entry["products"] = products
            EXTRACTIONS_F.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            _append_audit(quote_id, subject,
                          {"produtos": [f"{old_count} itens", f"{len(products)} itens"]},
                          user, action="products_edit")
            return


def append_products(quote_id: str, subject: str, new_products: list, user: str) -> None:
    if not EXTRACTIONS_F.exists():
        return
    entries = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8"))
    for entry in entries:
        if "id" not in entry:
            entry["id"] = _stable_id(entry)
        if entry["id"] == quote_id:
            existing = entry.get("products", [])
            entry["products"] = existing + new_products
            EXTRACTIONS_F.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            _append_audit(quote_id, subject,
                          {"produtos": [f"{len(existing)} itens", f"{len(entry['products'])} itens (+{len(new_products)})"]},
                          user, action="products_append")
            return


def append_extraction_entry(quote: dict, user: str) -> None:
    entries = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8")) if EXTRACTIONS_F.exists() else []
    entries.append(quote)
    EXTRACTIONS_F.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_audit(quote["id"], quote.get("subject", ""),
                  {"_criado": [None, quote["id"]]}, user, action="bulk_import_create")


# ── Annotations ───────────────────────────────────────────────────────────────

def load_annotations() -> dict:
    if not ANNOTATIONS_F.exists():
        return {}
    return json.loads(ANNOTATIONS_F.read_text(encoding="utf-8"))


def save_annotation(quote_id: str, subject: str, new_data: dict, user: str) -> None:
    _ensure()
    annotations = load_annotations()
    old_data = annotations.get(quote_id, {})

    changes = {
        k: [old_data.get(k), v]
        for k, v in new_data.items()
        if old_data.get(k) != v
    }

    new_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data["updated_by"] = user
    annotations[quote_id] = new_data
    ANNOTATIONS_F.write_text(json.dumps(annotations, ensure_ascii=False, indent=2), encoding="utf-8")

    if changes:
        _append_audit(quote_id, subject, changes, user)


# ── Corrections ──────────────────────────────────────────────────────────────

def load_corrections() -> dict:
    if not CORRECTIONS_F.exists():
        return {}
    return json.loads(CORRECTIONS_F.read_text(encoding="utf-8"))


def save_correction(quote_id: str, subject: str, fields: dict, user: str) -> None:
    """Save manually corrected auto-extracted fields, keeping full history per field."""
    _ensure()
    all_corr  = load_corrections()
    entry     = all_corr.get(quote_id, {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    changes   = {}

    for field, new_val in fields.items():
        new_val = new_val.strip() if isinstance(new_val, str) else new_val
        current = entry.get(field, {}).get("current", None)
        if current == new_val:
            continue
        history = entry.get(field, {}).get("history", [])
        history.append({"value": current, "at": timestamp, "by": user})
        entry[field] = {"current": new_val, "history": history}
        changes[field] = [current, new_val]

    if not changes:
        return

    all_corr[quote_id] = entry
    CORRECTIONS_F.write_text(json.dumps(all_corr, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_audit(quote_id, subject, changes, user, action="correction")


# ── Audit log ─────────────────────────────────────────────────────────────────

def _append_audit(quote_id: str, subject: str, changes: dict, user: str, action: str = "edit") -> None:
    logs = load_audit_log()
    logs.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user,
        "quote_id": quote_id,
        "subject": subject,
        "action": action,
        "changes": changes,
    })
    AUDIT_LOG_F.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")


def load_audit_log() -> list:
    if not AUDIT_LOG_F.exists():
        return []
    return json.loads(AUDIT_LOG_F.read_text(encoding="utf-8"))


# ── Stats ─────────────────────────────────────────────────────────────────────

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
            qdate = datetime.strptime(q["date"], "%Y-%m-%d %H:%M:%S")
            w = (now - qdate).days // 7
            if 0 <= w < 8:
                weeks[7 - w] += 1
        except Exception:
            pass
    week_labels = [(now - timedelta(weeks=7 - i)).strftime("Sem %d/%m") for i in range(8)]
    week_data   = [weeks[i] for i in range(8)]

    # ── Operacional ──────────────────────────────────────────────────────────

    # Por fornecedor (cotações + pedidos agrupados)
    forn_data: dict = defaultdict(lambda: {"Cotação": 0, "Pedido": 0})
    for q in quotes:
        ann  = annotations.get(q["id"], {})
        forn = (ann.get("fornecedor") or "").strip()
        if not forn:
            continue
        forn_data[forn][q.get("request_type", "Cotação")] += 1
    sorted_forn = sorted(forn_data.items(), key=lambda x: -(x[1]["Cotação"] + x[1]["Pedido"]))[:10]

    # Por etapa do processo
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

    # Top 10 mais antigos ativos
    def _parse_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

    def _parse_step_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d")
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
            "date":    q.get("date", "")[:10],
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
    """
    Calcula a previsão de entrega de um pedido. Usa max_estimated_delivery do CCW
    se disponível; caso contrário, estima a partir de início_fabricação + maior lead_time + 10d.
    Retorna (forecast_date_str_or_None, aggressor_dict_or_None).
    """
    from datetime import date as _date, timedelta as _td

    ccw_delivery = deal.get("max_estimated_delivery", "") if deal else ""
    if ccw_delivery:
        return ccw_delivery, {"source": "CCW", "last_sync": deal.get("last_ccw_sync", "")}

    aggressor = None
    inicio_str = timeline.get("dates", {}).get("inicio_fabricacao", "")
    if not inicio_str:
        return None, None
    try:
        start  = _date.fromisoformat(inicio_str)
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
    """
    Lista de Pedidos (request_type == 'Pedido') com previsão de entrega calculada,
    opcionalmente filtrados para depois de `after` (YYYY-MM-DD), ordenados do mais
    distante para o mais próximo.
    """
    quotes      = load_extractions()
    annotations = load_annotations()
    timelines   = load_timelines()
    deals       = load_deals()

    after_date = None
    if after:
        try:
            after_date = datetime.strptime(after, "%Y-%m-%d").date()
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
            forecast_date = datetime.strptime(forecast[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if after_date and forecast_date <= after_date:
            continue
        ann = annotations.get(q["id"], {})
        result.append({
            "id":       q["id"],
            "subject":  (q.get("subject") or "—")[:55],
            "forecast": forecast_date.isoformat(),
            "fornecedor": ann.get("fornecedor") or "—",
            "status":   ann.get("status", "Em Aberto"),
        })

    result.sort(key=lambda r: r["forecast"], reverse=True)
    return result


# ── Deals ─────────────────────────────────────────────────────────────────────

def load_deals() -> dict:
    if not DEALS_F.exists():
        return {}
    return json.loads(DEALS_F.read_text(encoding="utf-8"))


def save_deal(quote_id: str, subject: str, data: dict, user: str) -> None:
    _ensure()
    deals    = load_deals()
    old_data = deals.get(quote_id, {})
    changes  = {k: [old_data.get(k), v] for k, v in data.items() if old_data.get(k) != v and v}
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["updated_by"] = user
    deals[quote_id]    = data
    DEALS_F.write_text(json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8")
    if changes:
        _append_audit(quote_id, subject, changes, user, action="deal")


# ── Timelines ─────────────────────────────────────────────────────────────────

def load_timelines() -> dict:
    if not TIMELINES_F.exists():
        return {}
    return json.loads(TIMELINES_F.read_text(encoding="utf-8"))


def save_timeline(quote_id: str, subject: str, dates: dict, user: str) -> None:
    _ensure()
    timelines = load_timelines()
    old_dates = timelines.get(quote_id, {}).get("dates", {})
    changes = {k: [old_dates.get(k), v] for k, v in dates.items() if old_dates.get(k) != v}
    timelines[quote_id] = {
        "dates": dates,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_by": user,
    }
    TIMELINES_F.write_text(json.dumps(timelines, ensure_ascii=False, indent=2), encoding="utf-8")
    if changes:
        _append_audit(quote_id, subject, changes, user, action="timeline")


# ── CCW Bot sync ─────────────────────────────────────────────────────────────

def process_ccw_sync(quote_id: str, subject: str, order_id: str,
                     lines: list, user: str) -> dict:
    """
    Unified CCW sync. Detects scenario, computes final lead_time, creates products
    if needed, updates deals.json, and saves a validation report.

    Scenarios:
      1 — quote has products AND all portal part_numbers found in CCW XLS
      2 — quote has NO products → creates them from XLS
      3 — quote has products AND some portal part_numbers NOT in CCW XLS

    Lead_time final = max(lead_time_days) of items in intersection(portal, CCW).

    Returns dict with scenario, max_estimated_delivery, max_lead_time_days,
    products_created, intersection, only_in_portal, only_in_ccw, contributing_items.
    """
    if not EXTRACTIONS_F.exists():
        return {"scenario": 0, "error": "extractions not found"}

    entries     = json.loads(EXTRACTIONS_F.read_text(encoding="utf-8"))
    quote_entry = None
    for entry in entries:
        if "id" not in entry:
            entry["id"] = _stable_id(entry)
        if entry["id"] == quote_id:
            quote_entry = entry
            break

    if quote_entry is None:
        return {"scenario": 0, "error": "quote not found"}

    # ── Deduplica CCW lines por part_number (max lead_time, soma qty) ──────────
    ccw_map  = {}   # UPPER(pn) → {part_number, lead_time_days, estimated_delivery, qty}
    qty_sum  = defaultdict(int)
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

    ccw_parts      = set(ccw_map.keys())
    portal_products = quote_entry.get("products", [])
    portal_parts   = {
        str(p.get("part_number") or "").strip().upper()
        for p in portal_products
        if p.get("part_number")
    }

    # ── Detecta cenário e executa ação ─────────────────────────────────────────
    products_created = 0
    extractions_dirty = False

    if not portal_products:
        # Cenário 2: sem produtos — cria a partir do XLS
        scenario    = 2
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
        quote_entry["products"] = new_products
        portal_parts     = ccw_parts
        products_created = len(new_products)
        extractions_dirty = True
        intersection  = ccw_parts.copy()
        only_in_portal = set()
        only_in_ccw    = set()

    else:
        intersection   = portal_parts & ccw_parts
        only_in_portal = portal_parts - ccw_parts
        only_in_ccw    = ccw_parts    - portal_parts
        scenario = 1 if not only_in_portal else 3

    # ── Calcula LeadTime final a partir da intersecção ─────────────────────────
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

    # ── Grava extractions.json se criou produtos ───────────────────────────────
    if extractions_dirty:
        EXTRACTIONS_F.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _append_audit(quote_id, subject,
                      {"ccw_products_created": [None,
                          f"cenário 2 — {products_created} produto(s) criados do XLS CCW"]},
                      user, action="ccw_sync")

    # ── Grava deals.json com max_estimated_delivery calculado ─────────────────
    _ensure()
    deals = load_deals()
    deal  = dict(deals.get(quote_id, {}))
    deal["last_ccw_sync"]          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    deal["max_estimated_delivery"] = max_delivery or ""
    if order_id:
        deal["order_id"] = order_id
    deals[quote_id] = deal
    DEALS_F.write_text(json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8")

    _append_audit(quote_id, subject,
                  {"ccw_sync": [None,
                      f"cenário={scenario} order={order_id} "
                      f"intersecção={len(intersection)} "
                      f"só_portal={len(only_in_portal)} "
                      f"só_ccw={len(only_in_ccw)} "
                      f"leadtime_final={max_lt_days}d delivery={max_delivery}"]},
                  user, action="ccw_sync")

    # ── Salva relatório de validação ───────────────────────────────────────────
    result = {
        "scenario":              scenario,
        "max_estimated_delivery": max_delivery,
        "max_lead_time_days":    max_lt_days,
        "products_created":      products_created,
        "intersection":          sorted(intersection),
        "only_in_portal":        sorted(only_in_portal),
        "only_in_ccw":           sorted(only_in_ccw),
        "contributing_items":    contributing,
    }
    _save_ccw_validation(quote_id, subject, order_id, result)
    return result


def _save_ccw_validation(quote_id: str, subject: str, order_id: str, result: dict) -> None:
    existing = {}
    if CCW_VALIDATIONS_F.exists():
        try:
            existing = json.loads(CCW_VALIDATIONS_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing[quote_id] = {
        "quote_id":    quote_id,
        "subject":     subject,
        "order_id":    order_id,
        "validated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **result,
    }
    CCW_VALIDATIONS_F.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Users ─────────────────────────────────────────────────────────────────────

def load_users() -> list:
    if not USERS_F.exists():
        return []
    return json.loads(USERS_F.read_text(encoding="utf-8"))


def verify_user(username: str, password: str):
    """Returns user dict on success, None on failure."""
    for u in load_users():
        if u["username"] == username:
            if check_password_hash(u["password_hash"], password):
                return u
    return None


def list_users_safe() -> list:
    """Returns all users without password hashes."""
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in load_users()]


def username_exists(username: str) -> bool:
    return any(u["username"] == username for u in load_users())


def create_user(username: str, password: str, role: str = "viewer",
                nome: str = "", email: str = "", celular: str = "", empresa: str = "") -> None:
    _ensure()
    users = load_users()
    users.append({
        "username":      username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role":          role,
        "nome":          nome,
        "email":         email,
        "celular":       celular,
        "empresa":       empresa,
        "created_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    USERS_F.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_default_user() -> None:
    _ensure()
    if not load_users():
        create_user("admin", "admin123", role="admin")
        print("  [portal] Usuário padrão criado → admin / admin123  ⚠️  ALTERE A SENHA!")
