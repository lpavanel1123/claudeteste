import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_store


def _mock_common(monkeypatch, request_type="Pedido", dates=None, entregue=False,
                  deal=None, forecast=(None, None)):
    monkeypatch.setattr(data_store, "get_extraction_by_id",
                         lambda qid: {"id": qid, "request_type": request_type, "products": []})
    monkeypatch.setattr(data_store, "load_timelines",
                         lambda: {"quote-1": {"dates": dict(dates or {})}})
    monkeypatch.setattr(data_store, "load_annotations",
                         lambda: {"quote-1": {"entregue": entregue}})
    monkeypatch.setattr(data_store, "load_deals", lambda: {"quote-1": dict(deal or {})})
    monkeypatch.setattr(data_store, "compute_auto_forecast", lambda q, tl, d: forecast)

    saved = {}
    monkeypatch.setattr(
        data_store, "save_timeline",
        lambda quote_id, subject, dates_, user, action="timeline":
            saved.update({"quote_id": quote_id, "dates": dict(dates_), "action": action}),
    )
    pending = {}
    monkeypatch.setattr(
        data_store, "_append_audit",
        lambda quote_id, subject, changes, user, action="edit":
            pending.update({"changes": changes, "action": action}),
    )
    return saved, pending


def test_prazo_vencido_avanca_etapa(monkeypatch):
    ontem = (date.today() - timedelta(days=1)).isoformat()
    saved, pending = _mock_common(monkeypatch, forecast=(ontem, None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "bot_ccw")

    assert saved.get("dates", {}).get("entrega_parceiro") == ontem
    assert saved.get("action") == "auto_advance_deadline"
    assert not pending


def test_prazo_dentro_do_prazo_nao_avanca(monkeypatch):
    amanha = (date.today() + timedelta(days=1)).isoformat()
    saved, pending = _mock_common(monkeypatch, forecast=(amanha, None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "bot_ccw")

    assert saved == {}
    assert pending == {}


def test_checkbox_entregue_avanca_mesmo_com_prazo_futuro(monkeypatch):
    amanha = (date.today() + timedelta(days=1)).isoformat()
    saved, _ = _mock_common(monkeypatch, entregue=True, forecast=(amanha, None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "usuario")

    assert saved.get("dates", {}).get("entrega_parceiro") == amanha


def test_checkbox_entregue_sem_prazo_usa_hoje(monkeypatch):
    saved, _ = _mock_common(monkeypatch, entregue=True, forecast=(None, None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "usuario")

    assert saved.get("dates", {}).get("entrega_parceiro") == date.today().isoformat()


def test_sem_prazo_e_sem_checkbox_nao_faz_nada(monkeypatch):
    saved, pending = _mock_common(monkeypatch, forecast=(None, None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "bot_ccw")

    assert saved == {}
    assert pending == {}


def test_ja_avancado_e_idempotente(monkeypatch):
    ontem = (date.today() - timedelta(days=1)).isoformat()
    saved, _ = _mock_common(
        monkeypatch, dates={"entrega_parceiro": "2026-01-01"}, forecast=(ontem, None),
    )

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "bot_ccw")

    assert saved == {}  # não mexe de novo


def test_nao_se_aplica_a_cotacao_apenas_a_pedido(monkeypatch):
    ontem = (date.today() - timedelta(days=1)).isoformat()
    saved, pending = _mock_common(monkeypatch, request_type="Cotação", forecast=(ontem, None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "bot_ccw")

    assert saved == {}
    assert pending == {}


def test_prazo_malformado_sinaliza_pendente_sem_alterar_dados(monkeypatch):
    saved, pending = _mock_common(monkeypatch, forecast=("data-invalida", None))

    data_store.check_and_advance_by_deadline("quote-1", "assunto", "bot_ccw")

    assert saved == {}  # nada foi alterado
    assert pending.get("action") == "deadline_check_pending"
