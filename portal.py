from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import data_store
import config

app = Flask(__name__)
app.secret_key = config.PORTAL_SECRET_KEY or "dev-only-change-me"

STATUSES = ["Em Aberto", "Em Análise", "Aprovada", "Rejeitada", "Ganha", "Perdida"]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
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
        if data_store.verify_user(u, p):
            session["user"] = u
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
    ann  = data_store.load_annotations().get(quote_id, {})
    corr = data_store.load_corrections().get(quote_id, {})
    return render_template("quote_detail.html", quote=quote, ann=ann, corr=corr,
                           statuses=STATUSES, correctable=data_store.CORRECTABLE_FIELDS)


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
