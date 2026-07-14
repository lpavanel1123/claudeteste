import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_store


def _product(pn, list_price, qty=1, arquitetura="Enterprise Switching"):
    return {"part_number": pn, "unit_list_price": list_price, "qty": qty, "arquitetura": arquitetura}


def test_compute_project_value_usa_desconto_especifico_do_part_number():
    products = [_product("C9300-48P-A", 1000, qty=2)]
    discount_pivot = {("C9300-48P-A", "Enterprise Switching"): {"ntt": {"avg": 20.0}, "logicalis": {"avg": 10.0}}}
    vendor_avg = {"NTT": 5.0, "Logicalis": 5.0}

    valor, fallback = data_store._compute_project_value(products, "NTT", discount_pivot, vendor_avg)

    assert valor == 1000 * 2 * (1 - 0.20)
    assert fallback is False


def test_compute_project_value_cai_para_media_do_fornecedor_sem_historico():
    products = [_product("NOVO-PN-123", 500, qty=1)]
    discount_pivot = {}  # nenhum histórico para esse part number
    vendor_avg = {"NTT": 15.0, "Logicalis": 8.0}

    valor, fallback = data_store._compute_project_value(products, "Logicalis", discount_pivot, vendor_avg)

    assert valor == 500 * (1 - 0.08)
    assert fallback is True


def test_compute_project_value_sem_desconto_nenhum_usa_zero_e_sinaliza_fallback():
    products = [_product("SEM-HISTORICO", 200)]
    valor, fallback = data_store._compute_project_value(products, "NTT", {}, {})

    assert valor == 200  # 0% de desconto
    assert fallback is True


def test_compute_project_value_ignora_produto_sem_preco_de_lista():
    products = [_product("SEM-PRECO", 0), _product("COM-PRECO", 100)]
    valor, _ = data_store._compute_project_value(products, "NTT", {}, {"NTT": 0.0})

    assert valor == 100


def test_compute_project_value_soma_multiplos_produtos():
    products = [_product("PN-A", 100), _product("PN-B", 200)]
    pivot = {
        ("PN-A", "Enterprise Switching"): {"ntt": {"avg": 10.0}},
        ("PN-B", "Enterprise Switching"): {"ntt": {"avg": 10.0}},
    }
    valor, fallback = data_store._compute_project_value(products, "NTT", pivot, {})

    assert valor == (100 + 200) * 0.90
    assert fallback is False


# ── get_sales_forecast(): filtros de escopo (via monkeypatch dos loaders) ────

def _mock_forecast_deps(monkeypatch, quotes, annotations=None, deals=None, forecasts=None,
                         discount_history=None, vendor_avg=None):
    monkeypatch.setattr(data_store, "load_extractions", lambda: quotes)
    monkeypatch.setattr(data_store, "load_annotations", lambda: annotations or {})
    monkeypatch.setattr(data_store, "load_deals", lambda: deals or {})
    monkeypatch.setattr(data_store, "load_cisco_forecast", lambda: forecasts or {})
    monkeypatch.setattr(data_store, "get_discount_history", lambda: discount_history or [])
    monkeypatch.setattr(data_store, "_vendor_avg_discount", lambda: vendor_avg or {})


def test_get_sales_forecast_ignora_fornecedor_fora_de_ntt_logicalis(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "assunto", "products": []}]
    _mock_forecast_deps(monkeypatch, quotes, annotations={"q1": {"fornecedor": "Outros"}})

    result = data_store.get_sales_forecast()

    assert result == []


def test_get_sales_forecast_exclui_perdida_e_rejeitada(monkeypatch):
    quotes = [
        {"id": "q1", "request_type": "Pedido", "subject": "a", "products": []},
        {"id": "q2", "request_type": "Pedido", "subject": "b", "products": []},
    ]
    annotations = {
        "q1": {"fornecedor": "NTT", "status": "Perdida"},
        "q2": {"fornecedor": "NTT", "status": "Em Aberto"},
    }
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert [r["quote_id"] for r in result] == ["q2"]


def test_get_sales_forecast_ganha_permanece_na_lista(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Pedido", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT", "status": "Ganha"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert len(result) == 1


def test_get_sales_forecast_nome_projeto_usa_projeto_id_vale_prioritario(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação",
               "subject": "RES: Cotação NTT Firewall projeto - X", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT"}}
    deals = {"q1": {"projeto_id_vale": "PRJ0001234"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, deals=deals)

    result = data_store.get_sales_forecast()

    assert result[0]["projeto"] == "PRJ0001234"


def test_get_sales_forecast_nome_projeto_cai_para_assunto_normalizado(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação",
               "subject": "RES: Cotação NTT Firewall projeto - X", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert result[0]["projeto"] == "firewall projeto - x"


def test_get_sales_forecast_traz_deal_id_como_did(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Pedido", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "Logicalis"}}
    deals = {"q1": {"deal_id": "DEAL-999"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, deals=deals)

    result = data_store.get_sales_forecast()

    assert result[0]["deal_id"] == "DEAL-999"
