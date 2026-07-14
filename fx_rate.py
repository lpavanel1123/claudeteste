"""Cotação atual do dólar (BRL por 1 USD), usada para converter produtos
'Nacional' (cotados em Real pelos distribuidores) para USD nos totais do
portal (Spend Analysis, Forecast de Vendas). Produtos 'Importado' já vêm
em USD e não passam por conversão nenhuma.
"""
import json
import time
import urllib.request

_API_URL = "https://economia.awesomeapi.com.br/last/USD-BRL"
_CACHE_TTL_SECONDS = 3600  # 1h — evita bater na API a cada carga de página
_FALLBACK_RATE = 5.30      # só usado se a API falhar e não houver cache anterior

_cache = {"rate": None, "fetched_at": 0.0}


def get_usd_brl_rate() -> tuple:
    """Retorna (rate, is_live). `rate` = quantos BRL equivalem a 1 USD hoje.
    `is_live=True` quando o valor veio da API (nesta chamada ou de um cache
    ainda válido); `False` quando a busca falhou e caiu no último valor
    conhecido (ou no fallback estático, se nunca buscou com sucesso)."""
    now = time.time()
    if _cache["rate"] and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
        return _cache["rate"], True

    try:
        with urllib.request.urlopen(_API_URL, timeout=4) as resp:
            data = json.loads(resp.read().decode())
        rate = float(data["USDBRL"]["bid"])
        _cache["rate"] = rate
        _cache["fetched_at"] = now
        return rate, True
    except Exception:
        if _cache["rate"]:
            return _cache["rate"], False
        return _FALLBACK_RATE, False


def to_usd(value: float, tipo: str, rate: float) -> float:
    """Converte um valor em BRL para USD quando o produto é 'Nacional'.
    Produtos 'Importado' (ou sem tipo definido) já estão em USD."""
    if (tipo or "").strip() == "Nacional" and rate:
        return value / rate
    return value
