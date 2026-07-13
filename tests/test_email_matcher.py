import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import email_matcher
import data_store


# ── normalize_subject ─────────────────────────────────────────────────────────

def test_normalize_subject_strips_reply_and_vendor_id_prefix():
    a = email_matcher.normalize_subject(
        "NTT31072: Cotação NTT Firewall projeto - P0004156 SUD_ITA - Firewall rede automação"
    )
    b = email_matcher.normalize_subject(
        "RES: NTT31072: Cotação NTT Firewall projeto - P0004156 SUD_ITA - Firewall rede automação"
    )
    assert a == b == "firewall projeto - p0004156 sud_ita - firewall rede automação"


def test_normalize_subject_strips_etc_suffix_and_vendor_label():
    a = email_matcher.normalize_subject(
        "Cotação Logicalis Firewall projeto - P0004156 SUD_ITA - Firewall rede automação"
    )
    b = email_matcher.normalize_subject(
        "RES: Cotação Logicalis Firewall projeto - P0004156 SUD_ITA - Firewall rede automação - ETC 5773"
    )
    assert a == b == "firewall projeto - p0004156 sud_ita - firewall rede automação"


def test_normalize_subject_different_projects_stay_different():
    a = email_matcher.normalize_subject("Cotação NTT Projeto Alpha")
    b = email_matcher.normalize_subject("Cotação NTT Projeto Beta")
    assert a != b


# ── detect_vendor ─────────────────────────────────────────────────────────────

def test_detect_vendor_ntt():
    assert email_matcher.detect_vendor("Simone Goncalves <simone.goncalves@nttdata.com>", "") == "NTT"
    assert email_matcher.detect_vendor("", "am.br.pedidos.vale@global.ntt") == "NTT"


def test_detect_vendor_logicalis():
    assert email_matcher.detect_vendor("CCE-BR-DemandasVale <br.demandasvale@la.logicalis.com>", "") == "Logicalis"


def test_detect_vendor_ignores_relay_domain_not_in_from_to():
    # owner-extdom.tracking-cisco@cisco.com é o envelope/relay real visto em produção;
    # não deve ser confundido com um vendor.
    assert email_matcher.detect_vendor("owner-extdom.tracking-cisco@cisco.com", "") == ""


def test_detect_vendor_unknown_returns_empty():
    assert email_matcher.detect_vendor("alguem@vale.com", "outroalguem@vale.com") == ""


# ── extract_vendor_ref / extract_project_code ────────────────────────────────

def test_extract_vendor_ref_ntt_from_subject_and_body():
    subject = "NTT31072: Cotação NTT Firewall projeto - P0004156 SUD_ITA"
    body = "Para acompanhamento, o ID NTT da sua solicitação é: NTT31072"
    assert email_matcher.extract_vendor_ref("NTT", subject, "") == "31072"
    assert email_matcher.extract_vendor_ref("NTT", "", body) == "31072"


def test_extract_vendor_ref_logicalis_etc_suffix():
    subject = "RES: Cotação Logicalis Firewall projeto - ... - ETC 5773"
    assert email_matcher.extract_vendor_ref("Logicalis", subject, "") == "5773"


def test_extract_vendor_ref_unknown_vendor_returns_empty():
    assert email_matcher.extract_vendor_ref("", "NTT31072: algo", "") == ""


def test_extract_project_code_prefers_prj_over_p00():
    text = "cotação referente ao firewall do projeto PRJ0078112-SUD_ITA, ref pedido P0004156"
    # a regex captura o token PRJ+dígitos; deve priorizar PRJ e ignorar o P00 presente no mesmo texto
    code = email_matcher.extract_project_code(text)
    assert code.startswith("PRJ0078112")


def test_extract_project_code_falls_back_to_p00_when_no_prj():
    text = "Cotação NTT Firewall projeto - P0004156 SUD_ITA - Firewall rede automação"
    assert email_matcher.extract_project_code(text) == "P0004156"


def test_extract_project_code_none_found():
    assert email_matcher.extract_project_code("sem nenhum código aqui") == ""


# ── resolve(): cenários de ponta a ponta (DB isolado via monkeypatch) ────────

def _base_parsed(**overrides):
    parsed = {
        "subject": "Cotação NTT Firewall projeto - P0004156 SUD_ITA - Firewall rede automação",
        "body": "corpo do email",
        "from": "Simone Goncalves <simone.goncalves@nttdata.com>",
        "to": "Carlos <c0661353@vale.com>",
        "message_id": "",
        "in_reply_to": "",
        "references": "",
    }
    parsed.update(overrides)
    return parsed


def test_resolve_email_novo_sem_correlacao_cria_novo(monkeypatch):
    monkeypatch.setattr(email_matcher, "find_quote_by_message_id", lambda *a: None)
    monkeypatch.setattr(email_matcher, "find_quote_by_project_name", lambda *a, **k: None)
    monkeypatch.setattr(data_store, "find_quote_by_deal_field", lambda *a: None)

    parsed = _base_parsed(
        subject="Cotação NTT Projeto Totalmente Novo",
        body="sem nenhum ID ainda",
    )
    result = email_matcher.resolve(parsed)

    assert result["quote_id"] is None
    assert result["vendor"] == "NTT"


def test_resolve_followup_correlacionado_por_id_de_vendor(monkeypatch):
    monkeypatch.setattr(email_matcher, "find_quote_by_message_id", lambda *a: None)

    def fake_find_by_deal(key, value):
        if key == "ntt_id" and value == "31072":
            return "quote-existente-123"
        return None

    monkeypatch.setattr(data_store, "find_quote_by_deal_field", fake_find_by_deal)

    parsed = _base_parsed(
        subject="NTT31072: Cotação NTT Firewall projeto - P0004156 SUD_ITA - Firewall rede automação",
    )
    result = email_matcher.resolve(parsed)

    assert result["quote_id"] == "quote-existente-123"
    assert result["vendor"] == "NTT"
    assert result["vendor_ref"] == "31072"


def test_resolve_followup_correlacionado_por_thread_message_id(monkeypatch):
    monkeypatch.setattr(email_matcher, "find_quote_by_message_id", lambda *a: "quote-por-thread")
    # mesmo com um ID de vendor no assunto, a correlação por thread já resolveu antes
    monkeypatch.setattr(data_store, "find_quote_by_deal_field",
                         lambda *a: (_ for _ in ()).throw(AssertionError("não deveria consultar deals")))

    parsed = _base_parsed(in_reply_to="<msg-anterior@nttdata.com>")
    result = email_matcher.resolve(parsed)

    assert result["quote_id"] == "quote-por-thread"


def test_resolve_ambiguo_mesmo_projeto_vendor_diferente_nao_mescla(monkeypatch):
    """Mesmo projeto, mas a busca de fallback só olha o vendor do email atual (Logicalis);
    o registro correlato é de NTT e não deve ser retornado — deve criar novo."""
    monkeypatch.setattr(email_matcher, "find_quote_by_message_id", lambda *a: None)
    monkeypatch.setattr(data_store, "find_quote_by_deal_field", lambda *a: None)

    def fake_find_by_project_name(normalized_subject, vendor, days=180):
        # simula que só existe um registro desse projeto e ele é do vendor NTT
        if vendor == "NTT":
            return "quote-ntt-existente"
        return None  # Logicalis não tem nenhum registro correlato ainda

    monkeypatch.setattr(email_matcher, "find_quote_by_project_name", fake_find_by_project_name)

    parsed = _base_parsed(
        subject="RES: Cotação Logicalis Firewall projeto - P0004156 SUD_ITA - Firewall rede automação",
        body="resposta da logicalis",
        **{"from": "CCE-BR-DemandasVale <br.demandasvale@la.logicalis.com>", "to": "Carlos <c0661353@vale.com>"},
    )
    result = email_matcher.resolve(parsed)

    assert result["vendor"] == "Logicalis"
    assert result["quote_id"] is None  # nunca pega o registro NTT do mesmo projeto
