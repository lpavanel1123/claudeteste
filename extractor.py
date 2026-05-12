import re


def extract_from_body(body: str, to: str = "") -> dict:
    return {
        "request_type":        _extract_request_type(body),
        "project_type":        _extract_project_type(body),
        "requester_name":      _extract_requester_name(body),
        "department":          _extract_department(body),
        "recipient":           to or "NA",
        "cnpj":                _extract_cnpj(body),
        "smart_account":       _extract_label(body, r"Smart Account\s*:"),
        "smart_account_domain": _extract_label(body, r"Smart Account Domain ID\s*:"),
        "virtual_account":     _extract_label(body, r"Virtual Account\s*:"),
    }


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_request_type(body: str) -> str:
    low = body.lower()
    if re.search(r"cotaç|orçament|propost|proposta|cota[çc]", low):
        return "Cotação"
    if re.search(r"\bpedido\b|\bordered\b|\bpo\b|\bordem de compra", low):
        return "Pedido"
    return "NA"


def _extract_project_type(body: str) -> str:
    low = body.lower()
    if re.search(r"obsolescên|obsoleto|eol|end.of.life|substituiç|end of life", low):
        return "Obsolescência"
    if re.search(r"novo projeto|new project|projeto novo", low):
        return "Novo Projeto"
    return "NA"


def _extract_cnpj(body: str) -> str:
    # Matches formatted (12.345.678/0001-90) and unformatted (12345678000190)
    match = re.search(
        r"\d{2}[\.\s]?\d{3}[\.\s]?\d{3}[\s/]?\d{4}[-\s]?\d{2}",
        body,
    )
    return match.group(0).strip() if match else "NA"


def _extract_label(body: str, label_pattern: str) -> str:
    """Extract value after a label on the same line."""
    match = re.search(label_pattern + r"\s*(.+)", body, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "NA"


def _extract_requester_name(body: str) -> str:
    """
    Look for signature block markers (At.te, Atenciosamente, Regards, etc.)
    and return the first non-empty line after it.
    """
    lines = body.splitlines()
    sig_keywords = re.compile(
        r"^\s*(at\.?te|atenciosamente|regards|saudações|abraços|cordialmente|sincerely)",
        re.IGNORECASE,
    )
    for i, line in enumerate(lines):
        if sig_keywords.match(line):
            for candidate in lines[i + 1:]:
                candidate = candidate.strip()
                if candidate and not _looks_like_metadata(candidate):
                    return candidate
    return "NA"


def _extract_department(body: str) -> str:
    """
    Return the line right after the requester name line in the signature block.
    Typically contains department / role info (often has '|', 'Tecnologia', 'TI', etc.)
    """
    lines = body.splitlines()
    sig_keywords = re.compile(
        r"^\s*(at\.?te|atenciosamente|regards|saudações|abraços|cordialmente|sincerely)",
        re.IGNORECASE,
    )
    dept_hints = re.compile(
        r"tecnolog|operac|ti\b|it\b|infra|suporte|engenharia|comercial|compras|financ|\|",
        re.IGNORECASE,
    )
    for i, line in enumerate(lines):
        if sig_keywords.match(line):
            name_found = False
            for candidate in lines[i + 1:]:
                candidate = candidate.strip()
                if not candidate:
                    continue
                if not name_found:
                    name_found = True  # skip name line
                    continue
                if dept_hints.search(candidate):
                    return candidate
                if not _looks_like_metadata(candidate):
                    return candidate  # return next non-empty line even without hint
    return "NA"


def _looks_like_metadata(line: str) -> bool:
    """Heuristic: skip lines that are clearly contact/URL metadata."""
    return bool(re.search(
        r"@|tel\.|www\.|http|cep|av\.|rua|fax|\+\d{2}|\d{5}-\d{3}",
        line,
        re.IGNORECASE,
    ))
