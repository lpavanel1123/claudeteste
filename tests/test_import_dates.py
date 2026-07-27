import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portal
import data_store


def test_parse_import_date_formato_br():
    assert portal._parse_import_date("15/06/2026") == "2026-06-15 00:00:00"


def test_parse_import_date_formato_iso():
    assert portal._parse_import_date("2026-06-15") == "2026-06-15 00:00:00"


def test_parse_import_date_iso_com_hora():
    assert portal._parse_import_date("2026-06-15 14:30:00") == "2026-06-15 14:30:00"


def test_parse_import_date_br_com_hora():
    assert portal._parse_import_date("15/06/2026 14:30:00") == "2026-06-15 14:30:00"


def test_parse_import_date_vazio_retorna_vazio():
    assert portal._parse_import_date("") == ""
    assert portal._parse_import_date(None) == ""


def test_parse_import_date_invalida_retorna_vazio_sem_lancar():
    assert portal._parse_import_date("data qualquer") == ""
    assert portal._parse_import_date("31/02/2026") == ""  # 31 de fevereiro não existe


def test_parse_import_date_datetime_stringificado_do_excel():
    # célula formatada como data no Excel chega como str(datetime(...)) via openpyxl
    assert portal._parse_import_date("2026-06-15 00:00:00") == "2026-06-15 00:00:00"


# ── apply_import_dates_to_timeline() ─────────────────────────────────────────

def _mock_timeline(monkeypatch, existing_dates=None):
    saved = {}
    monkeypatch.setattr(data_store, "load_timelines",
                         lambda: {"q1": {"dates": dict(existing_dates or {})}})
    monkeypatch.setattr(
        data_store, "save_timeline",
        lambda quote_id, subject, dates, user, action="timeline":
            saved.update({"quote_id": quote_id, "dates": dict(dates), "action": action}),
    )
    return saved


def test_apply_import_dates_preenche_cotacao_vazia(monkeypatch):
    saved = _mock_timeline(monkeypatch)

    data_store.apply_import_dates_to_timeline(
        "q1", "assunto", "Cotação",
        "2026-05-22 00:00:00", "2026-05-26 00:00:00", "admin",
    )

    assert saved["dates"]["solicitacao_orcamento"] == "2026-05-22"
    assert saved["dates"]["entrega_orcamento"] == "2026-05-26"
    assert saved["action"] == "bulk_import_update"


def test_apply_import_dates_usa_chave_de_pedido(monkeypatch):
    saved = _mock_timeline(monkeypatch)

    data_store.apply_import_dates_to_timeline(
        "q1", "assunto", "Pedido", "2026-05-22 00:00:00", "", "admin",
    )

    assert saved["dates"]["solicitacao_pedido"] == "2026-05-22"
    assert "solicitacao_orcamento" not in saved["dates"]


def test_apply_import_dates_nunca_sobrescreve_data_existente(monkeypatch):
    saved = _mock_timeline(monkeypatch, existing_dates={"solicitacao_orcamento": "2020-01-01"})

    data_store.apply_import_dates_to_timeline(
        "q1", "assunto", "Cotação", "2026-05-22 00:00:00", "", "admin",
    )

    assert saved == {}  # nada foi chamado — já tinha valor, e não havia resposta pra preencher


def test_apply_import_dates_preenche_so_o_que_falta(monkeypatch):
    saved = _mock_timeline(monkeypatch, existing_dates={"solicitacao_orcamento": "2020-01-01"})

    data_store.apply_import_dates_to_timeline(
        "q1", "assunto", "Cotação", "2026-05-22 00:00:00", "2026-05-26 00:00:00", "admin",
    )

    assert saved["dates"]["solicitacao_orcamento"] == "2020-01-01"  # preservada
    assert saved["dates"]["entrega_orcamento"] == "2026-05-26"      # nova


def test_apply_import_dates_sem_nenhuma_data_nao_faz_nada(monkeypatch):
    saved = _mock_timeline(monkeypatch)

    data_store.apply_import_dates_to_timeline("q1", "assunto", "Cotação", "", "", "admin")

    assert saved == {}
