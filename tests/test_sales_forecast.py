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

    valor, fallback, _ = data_store._compute_project_value(products, "NTT", discount_pivot, vendor_avg)

    assert valor == 1000 * 2 * (1 - 0.20)
    assert fallback is False


def test_compute_project_value_cai_para_media_do_fornecedor_sem_historico():
    products = [_product("NOVO-PN-123", 500, qty=1)]
    discount_pivot = {}  # nenhum histórico para esse part number
    vendor_avg = {"NTT": 15.0, "Logicalis": 8.0}

    valor, fallback, _ = data_store._compute_project_value(products, "Logicalis", discount_pivot, vendor_avg)

    assert valor == 500 * (1 - 0.08)
    assert fallback is True


def test_compute_project_value_sem_desconto_nenhum_usa_zero_e_sinaliza_fallback():
    products = [_product("SEM-HISTORICO", 200)]
    valor, fallback, _ = data_store._compute_project_value(products, "NTT", {}, {})

    assert valor == 200  # 0% de desconto
    assert fallback is True


def test_compute_project_value_ignora_produto_sem_preco_de_lista():
    products = [_product("SEM-PRECO", 0), _product("COM-PRECO", 100)]
    valor, _, _ = data_store._compute_project_value(products, "NTT", {}, {"NTT": 0.0})

    assert valor == 100


def test_compute_project_value_soma_multiplos_produtos():
    products = [_product("PN-A", 100), _product("PN-B", 200)]
    pivot = {
        ("PN-A", "Enterprise Switching"): {"ntt": {"avg": 10.0}},
        ("PN-B", "Enterprise Switching"): {"ntt": {"avg": 10.0}},
    }
    valor, fallback, _ = data_store._compute_project_value(products, "NTT", pivot, {})

    assert valor == (100 + 200) * 0.90
    assert fallback is False


# ── get_sales_forecast(): filtros de escopo (via monkeypatch dos loaders) ────

def _mock_forecast_deps(monkeypatch, quotes, annotations=None, deals=None, forecasts=None,
                         discount_history=None, vendor_avg=None, rate=(5.0, True)):
    import fx_rate
    monkeypatch.setattr(data_store, "load_extractions", lambda: quotes)
    monkeypatch.setattr(data_store, "load_annotations", lambda: annotations or {})
    monkeypatch.setattr(data_store, "load_deals", lambda: deals or {})
    monkeypatch.setattr(data_store, "load_cisco_forecast", lambda: forecasts or {})
    monkeypatch.setattr(data_store, "get_discount_history", lambda: discount_history or [])
    monkeypatch.setattr(data_store, "_vendor_avg_discount", lambda: vendor_avg or {})
    monkeypatch.setattr(fx_rate, "get_usd_brl_rate", lambda: rate)


def test_get_sales_forecast_ignora_fornecedor_fora_de_ntt_logicalis(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "assunto", "products": []}]
    _mock_forecast_deps(monkeypatch, quotes, annotations={"q1": {"fornecedor": "Outros"}})

    result = data_store.get_sales_forecast()

    assert result["items"] == []


def test_get_sales_forecast_ignora_pedido_so_mostra_cotacao(monkeypatch):
    """Uma vez que virou Pedido já foi bookado — sai do forecast."""
    quotes = [
        {"id": "q1", "request_type": "Pedido", "subject": "a", "products": []},
        {"id": "q2", "request_type": "Cotação", "subject": "b", "products": []},
    ]
    annotations = {
        "q1": {"fornecedor": "NTT", "status": "Em Aberto"},
        "q2": {"fornecedor": "NTT", "status": "Em Aberto"},
    }
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert [r["quote_id"] for r in result["items"]] == ["q2"]


def test_get_sales_forecast_exclui_perdida_e_rejeitada(monkeypatch):
    quotes = [
        {"id": "q1", "request_type": "Cotação", "subject": "a", "products": []},
        {"id": "q2", "request_type": "Cotação", "subject": "b", "products": []},
    ]
    annotations = {
        "q1": {"fornecedor": "NTT", "status": "Perdida"},
        "q2": {"fornecedor": "NTT", "status": "Em Aberto"},
    }
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert [r["quote_id"] for r in result["items"]] == ["q2"]


def test_get_sales_forecast_ganha_permanece_na_lista(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT", "status": "Ganha"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert len(result["items"]) == 1


def test_get_sales_forecast_nome_projeto_usa_projeto_id_vale_prioritario(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação",
               "subject": "RES: Cotação NTT Firewall projeto - X", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT"}}
    deals = {"q1": {"projeto_id_vale": "PRJ0001234"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, deals=deals)

    result = data_store.get_sales_forecast()

    assert result["items"][0]["projeto"] == "PRJ0001234"


def test_get_sales_forecast_nome_projeto_cai_para_assunto_normalizado(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação",
               "subject": "RES: Cotação NTT Firewall projeto - X", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert result["items"][0]["projeto"] == "firewall projeto - x"


def test_get_sales_forecast_traz_deal_id_como_did(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "Logicalis"}}
    deals = {"q1": {"deal_id": "DEAL-999"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, deals=deals)

    result = data_store.get_sales_forecast()

    assert result["items"][0]["deal_id"] == "DEAL-999"


def test_get_sales_forecast_sem_produtos_usa_valor_total(monkeypatch):
    """Cotação importada em lote (sem XLS de produtos) — cai pro Valor Total
    manual (Informações Manuais), que já é digitado em US$ (sem conversão,
    diferente dos produtos Nacional que são digitados em R$)."""
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "Logicalis", "valor_total": 607790.32}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, rate=(5.0, True))

    result = data_store.get_sales_forecast()

    assert result["items"][0]["valor"] == 607790.32
    assert result["items"][0]["valor_origem"] == "valor_total"


def test_get_sales_forecast_com_produtos_nao_usa_valor_total(monkeypatch):
    """Havendo produto com valor > 0, o Valor Total manual é ignorado —
    o cálculo por produto é sempre mais preciso quando disponível."""
    quotes = [{
        "id": "q1", "request_type": "Cotação", "subject": "a",
        "products": [{"part_number": "PN-A", "unit_list_price": 1000, "qty": 1, "arquitetura": "Outros"}],
    }]
    annotations = {"q1": {"fornecedor": "NTT", "valor_total": 999999}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, vendor_avg={"NTT": 0.0})

    result = data_store.get_sales_forecast()

    assert result["items"][0]["valor"] == 1000
    assert result["items"][0]["valor_origem"] == "produtos"


def test_get_sales_forecast_sem_produtos_e_sem_valor_total_fica_zero(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "Logicalis"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert result["items"][0]["valor"] == 0.0
    assert result["items"][0]["valor_origem"] == "produtos"


def test_get_sales_forecast_expoe_a_cotacao_do_dolar_usada(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, rate=(5.25, False))

    result = data_store.get_sales_forecast()

    assert result["fx_rate"] == 5.25
    assert result["fx_rate_is_live"] is False


# ── Conversão de moeda: Nacional (Real) → USD pela cotação atual ─────────────

def test_compute_project_value_converte_nacional_para_usd():
    products = [_product("PN-BR", 1000, arquitetura="Enterprise Switching")]
    products[0]["tipo"] = "Nacional"

    valor, _, _ = data_store._compute_project_value(products, "NTT", {}, {"NTT": 0.0}, fx_rate_value=5.0)

    assert valor == 200  # R$1000 / 5.0 = USD 200, sem desconto


def test_compute_project_value_nao_converte_importado():
    products = [_product("PN-US", 1000, arquitetura="Enterprise Switching")]
    products[0]["tipo"] = "Importado"

    valor, _, _ = data_store._compute_project_value(products, "NTT", {}, {"NTT": 0.0}, fx_rate_value=5.0)

    assert valor == 1000  # já está em USD, taxa não se aplica


# ── Breakdown por arquitetura ────────────────────────────────────────────────

def test_compute_project_value_breakdown_por_arquitetura_fecha_com_total():
    products = [
        _product("PN-SW", 100, qty=2, arquitetura="Enterprise Switching"),
        _product("PN-SEC", 300, qty=1, arquitetura="Security"),
    ]
    valor, _, by_arch = data_store._compute_project_value(products, "NTT", {}, {"NTT": 0.0})

    assert by_arch == {"Enterprise Switching": 200.0, "Security": 300.0}
    assert round(sum(by_arch.values()), 2) == valor


def test_get_sales_forecast_sem_produtos_cai_no_bucket_sem_arquitetura(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT", "valor_total": 5000}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    result = data_store.get_sales_forecast()

    assert result["items"][0]["valor_por_arquitetura"] == {data_store.SEM_ARQUITETURA: 5000.0}


# ── Flags, próxima ação e MEDDPICC ───────────────────────────────────────────

def test_get_sales_forecast_flags_e_campos_meddpicc_fluem_ate_o_item(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT"}}
    forecasts = {"q1": {
        "status": "Commit", "booking_date": "2026-09-01",
        "projeto_capital": True, "kec": True, "vbm": False,
        "projeto_obsolescencia": False, "prioridade_quarter": True,
        "proxima_acao": "Emitir PO", "proxima_acao_data": "2026-08-01",
        "economic_buyer": "Fulano", "champion": "Beltrano", "competition": "OEM X",
    }}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, forecasts=forecasts)

    item = data_store.get_sales_forecast()["items"][0]

    assert item["projeto_capital"] is True
    assert item["kec"] is True
    assert item["vbm"] is False
    assert item["prioridade_quarter"] is True
    assert item["proxima_acao"] == "Emitir PO"
    assert item["proxima_acao_data"] == "2026-08-01"
    assert item["economic_buyer"] == "Fulano"
    assert item["champion"] == "Beltrano"
    assert item["competition"] == "OEM X"


def test_meddpicc_score_completo_e_vazio(monkeypatch):
    quotes = [{"id": "q1", "request_type": "Cotação", "subject": "a", "products": []}]
    annotations = {"q1": {"fornecedor": "NTT", "valor_total": 100}}  # Metrics ok
    forecasts = {"q1": {
        "status": "Commit", "booking_date": "2026-09-01",
        "projeto_capital": True, "proxima_acao": "Emitir PO",
        "economic_buyer": "Fulano", "champion": "Beltrano", "competition": "OEM X",
    }}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, forecasts=forecasts)
    assert data_store.get_sales_forecast()["items"][0]["meddpicc_score"] == 8

    # Sem registro de forecast e sem valor: nenhum critério atendido
    _mock_forecast_deps(monkeypatch, quotes, annotations={"q1": {"fornecedor": "NTT"}})
    assert data_store.get_sales_forecast()["items"][0]["meddpicc_score"] == 0


def test_get_sales_forecast_prioridade_quarter_ordena_primeiro(monkeypatch):
    quotes = [
        {"id": "q1", "request_type": "Cotação", "subject": "grande", "products": []},
        {"id": "q2", "request_type": "Cotação", "subject": "pequeno", "products": []},
    ]
    annotations = {
        "q1": {"fornecedor": "NTT", "valor_total": 900000},
        "q2": {"fornecedor": "NTT", "valor_total": 100},
    }
    forecasts = {"q2": {"prioridade_quarter": True}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, forecasts=forecasts)

    result = data_store.get_sales_forecast()

    assert [r["quote_id"] for r in result["items"]] == ["q2", "q1"]


# ── Departamento e pivots por estágio ────────────────────────────────────────

def test_get_sales_forecast_departamento_com_fallback(monkeypatch):
    quotes = [
        {"id": "q1", "request_type": "Cotação", "subject": "a", "products": [], "department": "TI Infra"},
        {"id": "q2", "request_type": "Cotação", "subject": "b", "products": [], "department": "NA"},
        {"id": "q3", "request_type": "Cotação", "subject": "c", "products": []},
    ]
    annotations = {q["id"]: {"fornecedor": "NTT"} for q in quotes}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations)

    deptos = {r["quote_id"]: r["departamento"] for r in data_store.get_sales_forecast()["items"]}

    assert deptos == {"q1": "TI Infra", "q2": "Não informado", "q3": "Não informado"}


def test_get_sales_forecast_pivot_departamento_soma_por_estagio(monkeypatch):
    quotes = [
        {"id": "q1", "request_type": "Cotação", "subject": "a", "products": [], "department": "TI"},
        {"id": "q2", "request_type": "Cotação", "subject": "b", "products": [], "department": "TI"},
        {"id": "q3", "request_type": "Cotação", "subject": "c", "products": [], "department": "Mina"},
    ]
    annotations = {
        "q1": {"fornecedor": "NTT", "valor_total": 100},
        "q2": {"fornecedor": "NTT", "valor_total": 200},
        "q3": {"fornecedor": "NTT", "valor_total": 50},
    }
    forecasts = {"q1": {"status": "Commit"}, "q2": {"status": "Upside"}, "q3": {"status": "Commit"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, forecasts=forecasts)

    by_dept = {r["label"]: r for r in data_store.get_sales_forecast()["by_department"]}

    assert by_dept["TI"]["stages"]["Commit"] == 100
    assert by_dept["TI"]["stages"]["Upside"] == 200
    assert by_dept["TI"]["total"] == 300
    assert by_dept["Mina"]["total"] == 50


def test_get_sales_forecast_pivot_arquitetura_fecha_com_total(monkeypatch):
    quotes = [{
        "id": "q1", "request_type": "Cotação", "subject": "a",
        "products": [
            _product("PN-SW", 100, qty=1, arquitetura="Enterprise Switching"),
            _product("PN-SEC", 300, qty=1, arquitetura="Security"),
        ],
    }]
    annotations = {"q1": {"fornecedor": "NTT"}}
    _mock_forecast_deps(monkeypatch, quotes, annotations=annotations, vendor_avg={"NTT": 0.0})

    result = data_store.get_sales_forecast()
    total_pivot = sum(r["total"] for r in result["by_architecture"])

    assert total_pivot == result["items"][0]["valor"] == 400
