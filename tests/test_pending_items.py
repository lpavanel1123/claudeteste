import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_store


def _dt(days_ago):
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _d(days_ago):
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# ── _days_since ───────────────────────────────────────────────────────────────

def test_days_since_datetime_format():
    assert data_store._days_since(_dt(5)) == 5


def test_days_since_date_only_format():
    assert data_store._days_since(_d(10)) == 10


def test_days_since_vazio_ou_invalido_retorna_none():
    assert data_store._days_since("") is None
    assert data_store._days_since(None) is None
    assert data_store._days_since("data qualquer") is None


# ── get_pending_items() — via monkeypatch dos loaders ────────────────────────

def _mock_deps(monkeypatch, quotes, annotations=None, timelines=None, deals=None, audit=None):
    monkeypatch.setattr(data_store, "load_extractions", lambda: quotes)
    monkeypatch.setattr(data_store, "load_annotations", lambda: annotations or {})
    monkeypatch.setattr(data_store, "load_timelines", lambda: timelines or {})
    monkeypatch.setattr(data_store, "load_deals", lambda: deals or {})
    monkeypatch.setattr(data_store, "load_audit_log", lambda: audit or [])


def test_pending_items_ignora_status_fechado(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "date": _dt(100)}]
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Ganha"}})

    result = data_store.get_pending_items()

    assert result["total"] == 0


def test_pending_items_overdue_forecast_pedido_com_prazo_vencido(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Pedido", "subject": "a", "date": _dt(5), "products": []}]
    timelines = {"q1": {"dates": {"inicio_fabricacao": _d(20)}}}
    deals = {"q1": {"max_estimated_delivery": _d(3)}}  # CCW: previsão já passou há 3 dias
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Em Aberto"}},
               timelines=timelines, deals=deals)

    result = data_store.get_pending_items()

    assert len(result["overdue_forecast"]) == 1
    assert result["overdue_forecast"][0]["quote_id"] == "q1"


def test_pending_items_nao_marca_pedido_ja_avancado(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Pedido", "subject": "a", "date": _dt(5), "products": []}]
    timelines = {"q1": {"dates": {"entrega_parceiro": _d(1)}}}  # já avançou
    deals = {"q1": {"max_estimated_delivery": _d(3)}}
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Em Aberto"}},
               timelines=timelines, deals=deals)

    result = data_store.get_pending_items()

    assert result["overdue_forecast"] == []


def test_pending_items_stuck_stage_acima_do_limiar(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "date": _dt(45), "products": []}]
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Em Aberto"}})

    result = data_store.get_pending_items()

    assert len(result["stuck_stage"]) == 1
    assert result["stuck_stage"][0]["dias"] == 45


def test_pending_items_nao_marca_stage_dentro_do_limiar(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "date": _dt(10), "products": []}]
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Em Aberto"}})

    result = data_store.get_pending_items()

    assert result["stuck_stage"] == []


def test_pending_items_awaiting_vendor_acima_de_15_dias(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "date": _dt(20), "products": []}]
    _mock_deps(monkeypatch, quotes,
               annotations={"q1": {"status": "Em Aberto", "fornecedor": "NTT"}},
               deals={"q1": {}})  # sem response_received_at

    result = data_store.get_pending_items()

    assert len(result["awaiting_vendor"]) == 1


def test_pending_items_nao_marca_awaiting_vendor_se_ja_respondeu(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "date": _dt(20), "products": []}]
    _mock_deps(monkeypatch, quotes,
               annotations={"q1": {"status": "Em Aberto", "fornecedor": "NTT"}},
               deals={"q1": {"response_received_at": _dt(2)}})

    result = data_store.get_pending_items()

    assert result["awaiting_vendor"] == []


def test_pending_items_pending_review_sem_resolucao_posterior(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Pedido", "subject": "a", "date": _dt(1), "products": []}]
    audit = [
        {"quote_id": "q1", "action": "deadline_check_pending", "timestamp": _dt(5), "subject": "a"},
    ]
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Em Aberto"}}, audit=audit)

    result = data_store.get_pending_items()

    assert len(result["pending_review"]) == 1


def test_pending_items_pending_review_ja_resolvido_nao_aparece(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Pedido", "subject": "a", "date": _dt(1), "products": []}]
    audit = [
        {"quote_id": "q1", "action": "deadline_check_pending", "timestamp": _dt(5), "subject": "a"},
        {"quote_id": "q1", "action": "auto_advance_deadline", "timestamp": _dt(2), "subject": "a"},
    ]
    _mock_deps(monkeypatch, quotes, annotations={"q1": {"status": "Em Aberto"}}, audit=audit)

    result = data_store.get_pending_items()

    assert result["pending_review"] == []


# ── find_related_quotes_other_vendor() ───────────────────────────────────────

def test_find_related_ignora_quando_sem_fornecedor(monkeypatch):
    monkeypatch.setattr(data_store, "get_extraction_by_id", lambda qid: {"id": qid, "subject": "x"})
    monkeypatch.setattr(data_store, "load_annotations", lambda: {"q1": {"fornecedor": "Outros"}})

    assert data_store.find_related_quotes_other_vendor("q1") == []


def test_find_related_quote_inexistente(monkeypatch):
    monkeypatch.setattr(data_store, "get_extraction_by_id", lambda qid: None)

    assert data_store.find_related_quotes_other_vendor("q1") == []


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *a, **kw):
        pass

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeGetCursor:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self, commit=False):
        return _FakeCursor(self._rows)


def test_find_related_encontra_mesmo_projeto_outro_vendor(monkeypatch):
    monkeypatch.setattr(data_store, "get_extraction_by_id",
                         lambda qid: {"id": qid, "subject": "Cotação NTT Firewall projeto - X"})
    monkeypatch.setattr(data_store, "load_annotations", lambda: {"q1": {"fornecedor": "NTT"}})
    rows = [
        {"id": "q2", "subject": "RES: Cotação Logicalis Firewall projeto - X - ETC 5773",
         "fornecedor": "Logicalis", "status": "Em Aberto"},
    ]
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(rows))

    related = data_store.find_related_quotes_other_vendor("q1")

    assert len(related) == 1
    assert related[0]["quote_id"] == "q2"
    assert related[0]["fornecedor"] == "Logicalis"


def test_find_related_nao_bate_projeto_diferente(monkeypatch):
    monkeypatch.setattr(data_store, "get_extraction_by_id",
                         lambda qid: {"id": qid, "subject": "Cotação NTT Firewall projeto - X"})
    monkeypatch.setattr(data_store, "load_annotations", lambda: {"q1": {"fornecedor": "NTT"}})
    rows = [
        {"id": "q3", "subject": "Cotação Logicalis Projeto Totalmente Diferente",
         "fornecedor": "Logicalis", "status": "Em Aberto"},
    ]
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(rows))

    assert data_store.find_related_quotes_other_vendor("q1") == []


# ── get_pending_count_cached() ────────────────────────────────────────────────

# ── find_duplicate_groups() ───────────────────────────────────────────────────

def test_find_duplicate_groups_agrupa_mesmo_assunto_e_fornecedor(monkeypatch):
    quotes = [
        {"id": "q1", "subject": "Cotação NTT Firewall projeto - X", "date": "2026-01-01"},
        {"id": "q2", "subject": "RES: Cotação NTT Firewall projeto - X", "date": "2026-01-02"},
        {"id": "q3", "subject": "Cotação NTT Outro Projeto", "date": "2026-01-01"},
    ]
    annotations = {
        "q1": {"fornecedor": "NTT"}, "q2": {"fornecedor": "NTT"}, "q3": {"fornecedor": "NTT"},
    }
    monkeypatch.setattr(data_store, "load_extractions", lambda: quotes)
    monkeypatch.setattr(data_store, "load_annotations", lambda: annotations)

    groups = data_store.find_duplicate_groups()

    assert len(groups) == 1
    assert len(groups[0]["quotes"]) == 2
    assert {i["quote_id"] for i in groups[0]["quotes"]} == {"q1", "q2"}


def test_find_duplicate_groups_nao_agrupa_fornecedores_diferentes(monkeypatch):
    quotes = [
        {"id": "q1", "subject": "Cotação Firewall projeto - X", "date": "2026-01-01"},
        {"id": "q2", "subject": "RES: Cotação Firewall projeto - X", "date": "2026-01-02"},
    ]
    annotations = {"q1": {"fornecedor": "NTT"}, "q2": {"fornecedor": "Logicalis"}}
    monkeypatch.setattr(data_store, "load_extractions", lambda: quotes)
    monkeypatch.setattr(data_store, "load_annotations", lambda: annotations)

    assert data_store.find_duplicate_groups() == []


def test_find_duplicate_groups_ignora_fornecedor_nao_definido(monkeypatch):
    """Sem fornecedor conhecido, não agrupa — mesmo princípio do email_matcher:
    nunca correlacionar quando o vendor não está confirmado."""
    quotes = [
        {"id": "q1", "subject": "Cotação Firewall projeto - X", "date": "2026-01-01"},
        {"id": "q2", "subject": "RES: Cotação Firewall projeto - X", "date": "2026-01-02"},
    ]
    annotations = {"q1": {}, "q2": {"fornecedor": ""}}
    monkeypatch.setattr(data_store, "load_extractions", lambda: quotes)
    monkeypatch.setattr(data_store, "load_annotations", lambda: annotations)

    assert data_store.find_duplicate_groups() == []


def test_pending_count_cached_evita_recomputar_dentro_do_ttl(monkeypatch):
    data_store._pending_count_cache["total"] = 0
    data_store._pending_count_cache["at"] = 0.0

    calls = {"n": 0}

    def fake_get_pending_items():
        calls["n"] += 1
        return {"total": 42}

    monkeypatch.setattr(data_store, "get_pending_items", fake_get_pending_items)

    assert data_store.get_pending_count_cached() == 42
    assert data_store.get_pending_count_cached() == 42  # não recomputa
    assert calls["n"] == 1
