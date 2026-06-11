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

TIMELINES_F = DATA_DIR / "timelines.json"

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

    active = [q for q in quotes if q["_status"] in {"Em Aberto", "Em Análise", "Aprovada"}]
    oldest = sorted(active, key=lambda q: _parse_date(q.get("date", "")))[:10]
    top10  = []
    for q in oldest:
        rtype      = q.get("request_type", "Cotação")
        steps_list = TIMELINE_STEPS.get(rtype, TIMELINE_STEPS["Cotação"])
        tl_dates   = timelines.get(q["id"], {}).get("dates", {})
        stage      = "Concluído"
        for step in steps_list:
            if not tl_dates.get(step["key"]):
                stage = step["label"]
                break
        age = (now - _parse_date(q.get("date", ""))).days
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


# ── Users ─────────────────────────────────────────────────────────────────────

def load_users() -> list:
    if not USERS_F.exists():
        return []
    return json.loads(USERS_F.read_text(encoding="utf-8"))


def verify_user(username: str, password: str) -> bool:
    for u in load_users():
        if u["username"] == username:
            return check_password_hash(u["password_hash"], password)
    return False


def create_user(username: str, password: str, role: str = "admin") -> None:
    _ensure()
    users = load_users()
    users.append({
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
    })
    USERS_F.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_default_user() -> None:
    _ensure()
    if not load_users():
        create_user("admin", "admin123")
        print("  [portal] Usuário padrão criado → admin / admin123  ⚠️  ALTERE A SENHA!")
