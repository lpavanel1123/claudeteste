from functools import wraps
from datetime import datetime
from pathlib import Path
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import data_store
import config

app = Flask(__name__)
app.secret_key = config.PORTAL_SECRET_KEY or "dev-only-change-me"

STATUSES = ["Em Aberto", "Em Análise", "Aprovada", "Rejeitada", "Ganha", "Perdida"]


@app.template_filter("date_br")
def date_br(value):
    parts = str(value).split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return value


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        u_data = data_store.verify_user(u, p)
        if u_data:
            session["user"] = u
            session["role"] = u_data.get("role", "viewer")
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha incorretos.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", stats=data_store.get_stats())


@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(data_store.get_stats())


# ── Quotes ────────────────────────────────────────────────────────────────────

@app.route("/quotes")
@login_required
def quotes():
    all_quotes  = data_store.load_extractions()
    annotations = data_store.load_annotations()

    tipo_f   = request.args.get("tipo", "")
    status_f = request.args.get("status", "")
    search   = request.args.get("q", "").lower()

    result = []
    for q in all_quotes:
        ann = annotations.get(q["id"], {})
        q["_status"] = ann.get("status", "Em Aberto")
        q["_valor"]  = ann.get("valor_total") or ""
        q["_resp"]   = ann.get("responsavel_interno", "")

        if tipo_f   and q.get("request_type") != tipo_f:
            continue
        if status_f and q["_status"] != status_f:
            continue
        if search:
            haystack = " ".join([
                q.get("subject", ""), q.get("from", ""),
                q.get("requester_name", ""), q.get("department", ""),
            ]).lower()
            if search not in haystack:
                continue
        result.append(q)

    return render_template(
        "quotes.html", quotes=result,
        tipo_f=tipo_f, status_f=status_f, search=search,
        statuses=STATUSES,
    )


@app.route("/quotes/<quote_id>")
@login_required
def quote_detail(quote_id):
    quote = next((q for q in data_store.load_extractions() if q["id"] == quote_id), None)
    if not quote:
        return "Cotação não encontrada", 404
    ann      = data_store.load_annotations().get(quote_id, {})
    corr     = data_store.load_corrections().get(quote_id, {})
    timeline = data_store.load_timelines().get(quote_id, {"dates": {}})
    deal     = data_store.load_deals().get(quote_id, {})
    request_type = corr.get("request_type", {}).get("current") or quote.get("request_type", "Cotação")
    tl_steps = data_store.TIMELINE_STEPS.get(request_type, data_store.TIMELINE_STEPS["Cotação"])
    return render_template("quote_detail.html", quote=quote, ann=ann, corr=corr,
                           statuses=STATUSES, correctable=data_store.CORRECTABLE_FIELDS,
                           timeline=timeline, timeline_steps=tl_steps,
                           deal=deal, deal_fields=data_store.DEAL_FIELDS)


@app.route("/quotes/new", methods=["GET", "POST"])
@login_required
def quote_new():
    if request.method == "POST":
        import uuid
        quote_id = str(uuid.uuid4())
        now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Produtos dinâmicos
        products = []
        for qty, part, desc in zip(
            request.form.getlist("qty[]"),
            request.form.getlist("part_number[]"),
            request.form.getlist("description[]"),
        ):
            part = part.strip()
            if part:
                products.append({"qty": qty.strip() or "1", "part_number": part, "description": desc.strip()})

        quote = {
            "id":                   quote_id,
            "is_manual":            True,
            "date":                 now_str,
            "from":                 session["user"],
            "subject":              request.form.get("subject", "").strip() or "(sem assunto)",
            "request_type":         request.form.get("request_type", "Cotação"),
            "project_type":         request.form.get("project_type", "NA"),
            "requester_name":       request.form.get("requester_name", "").strip(),
            "department":           request.form.get("department", "").strip(),
            "recipient":            config.EMAIL_ADDRESS,
            "cnpj":                 request.form.get("cnpj", "").strip(),
            "smart_account":        request.form.get("smart_account", "").strip(),
            "smart_account_domain": request.form.get("smart_account_domain", "").strip(),
            "virtual_account":      request.form.get("virtual_account", "").strip(),
            "project_ref":          request.form.get("project_ref", "").strip() or "NA",
            "products":             products,
            "body":                 request.form.get("body", "").strip(),
        }

        path = Path("extractions.json")
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        entries.append(quote)
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

        raw_valor = request.form.get("valor_total", "").replace(",", ".").replace("R$", "").strip()
        ann_data  = {
            "status":              request.form.get("status", "Em Aberto"),
            "valor_total":         float(raw_valor) if raw_valor else None,
            "responsavel_interno": request.form.get("responsavel_interno", "").strip(),
            "fornecedor":          request.form.get("fornecedor", "").strip(),
            "observacoes":         request.form.get("observacoes", "").strip(),
        }
        data_store.save_annotation(quote_id, quote["subject"], ann_data, session["user"])

        flash("Cotação criada com sucesso!", "success")
        return redirect(url_for("quote_detail", quote_id=quote_id))

    return render_template("new_quote.html", statuses=STATUSES,
                           now=datetime.now().strftime("%Y-%m-%dT%H:%M"))


@app.route("/quotes/<quote_id>/deal", methods=["POST"])
@login_required
def quote_deal(quote_id):
    quote = next((q for q in data_store.load_extractions() if q["id"] == quote_id), None)
    if not quote:
        return "Cotação não encontrada", 404
    data = {f["key"]: request.form.get(f["key"], "").strip() for f in data_store.DEAL_FIELDS}
    data_store.save_deal(quote_id, quote.get("subject", ""), data, session["user"])
    flash("IDs e Estimates salvos com sucesso!", "success")
    return redirect(url_for("quote_detail", quote_id=quote_id))


@app.route("/quotes/<quote_id>/timeline", methods=["POST"])
@login_required
def quote_timeline(quote_id):
    quote = next((q for q in data_store.load_extractions() if q["id"] == quote_id), None)
    if not quote:
        return "Cotação não encontrada", 404
    corr = data_store.load_corrections().get(quote_id, {})
    request_type = corr.get("request_type", {}).get("current") or quote.get("request_type", "Cotação")
    steps = data_store.TIMELINE_STEPS.get(request_type, data_store.TIMELINE_STEPS["Cotação"])
    dates = {}
    for step in steps:
        val = request.form.get(step["key"], "").strip()
        if val:
            dates[step["key"]] = val
        if "extra_key" in step:
            extra_val = request.form.get(step["extra_key"], "").strip()
            if extra_val:
                dates[step["extra_key"]] = extra_val
    data_store.save_timeline(quote_id, quote.get("subject", ""), dates, session["user"])
    flash("Timeline atualizada com sucesso!", "success")
    return redirect(url_for("quote_detail", quote_id=quote_id))


@app.route("/quotes/<quote_id>/correct", methods=["POST"])
@login_required
def quote_correct(quote_id):
    quote = next((q for q in data_store.load_extractions() if q["id"] == quote_id), None)
    if not quote:
        return "Cotação não encontrada", 404
    fields = {f: request.form.get(f, "").strip() for f in data_store.CORRECTABLE_FIELDS}
    data_store.save_correction(quote_id, quote.get("subject", ""), fields, session["user"])
    flash("Dados extraídos corrigidos com sucesso!", "success")
    return redirect(url_for("quote_detail", quote_id=quote_id))


@app.route("/quotes/<quote_id>/edit", methods=["POST"])
@login_required
def quote_edit(quote_id):
    quote = next((q for q in data_store.load_extractions() if q["id"] == quote_id), None)
    if not quote:
        return "Cotação não encontrada", 404

    raw_valor = request.form.get("valor_total", "").replace(",", ".").replace("R$", "").strip()
    new_data = {
        "valor_total":        float(raw_valor) if raw_valor else None,
        "status":             request.form.get("status", "Em Aberto"),
        "responsavel_interno": request.form.get("responsavel_interno", "").strip(),
        "fornecedor":         request.form.get("fornecedor", "").strip(),
        "observacoes":        request.form.get("observacoes", "").strip(),
    }
    data_store.save_annotation(quote_id, quote.get("subject", ""), new_data, session["user"])
    flash("Cotação atualizada com sucesso!", "success")
    return redirect(url_for("quote_detail", quote_id=quote_id))


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", users=data_store.list_users_safe())


@app.route("/admin/users", methods=["POST"])
@admin_required
def admin_create_user():
    username  = request.form.get("username", "").strip()
    password  = request.form.get("password", "")
    password2 = request.form.get("password_confirm", "")
    nome      = request.form.get("nome", "").strip()
    email     = request.form.get("email", "").strip()
    celular   = request.form.get("celular", "").strip()
    empresa   = request.form.get("empresa", "").strip()
    role      = request.form.get("role", "viewer")

    if not username or not password:
        flash("Username e senha são obrigatórios.", "danger")
        return redirect(url_for("admin"))
    if password != password2:
        flash("As senhas não coincidem.", "danger")
        return redirect(url_for("admin"))
    if data_store.username_exists(username):
        flash(f"Username '{username}' já existe.", "danger")
        return redirect(url_for("admin"))

    data_store.create_user(username, password, role=role,
                           nome=nome, email=email, celular=celular, empresa=empresa)
    flash(f"Usuário '{username}' criado com sucesso!", "success")
    return redirect(url_for("admin"))


# ── Logs ──────────────────────────────────────────────────────────────────────

@app.route("/logs")
@login_required
def logs():
    all_logs    = data_store.load_audit_log()
    user_filter = request.args.get("user", "")
    all_users   = sorted({lg.get("user", "") for lg in all_logs})

    filtered = [lg for lg in all_logs if not user_filter or lg.get("user") == user_filter]
    return render_template("logs.html", logs=filtered, user_filter=user_filter, all_users=all_users)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data_store.ensure_default_user()
    print(f"Portal rodando em http://127.0.0.1:{config.PORTAL_PORT}")
    app.run(host="127.0.0.1", port=config.PORTAL_PORT, debug=False)
