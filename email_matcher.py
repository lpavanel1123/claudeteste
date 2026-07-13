import re

import db
import data_store

# ── Vendors suportados hoje (ver README / instrução do usuário: só NTT e Logicalis) ──

VENDOR_DOMAINS = {
    "NTT": ("nttdata.com", "global.ntt"),
    "Logicalis": ("logicalis.com",),
}

# ── Normalização de assunto ───────────────────────────────────────────────────
# Real: "Cotação NTT Firewall projeto - P0004156 SUD_ITA - Firewall rede automação"
#    -> "NTT31072: Cotação NTT Firewall projeto - ..."               (NTT atribui ID)
#    -> "RES: Cotação Logicalis Firewall projeto - ... - ETC 5773"    (Logicalis atribui ID)
# O núcleo do assunto (nome do projeto) é o que precisa sobreviver à normalização.

_REPLY_PREFIX_RE = re.compile(r"^\s*(re|res|enc|fwd|fw|encaminhar)\s*:\s*", re.IGNORECASE)
_VENDOR_ID_PREFIX_RE = re.compile(r"^\s*(NTT[\s\-]?\d{4,6})\s*:\s*", re.IGNORECASE)
_VENDOR_LABEL_RE = re.compile(r"^\s*Cota[çc][ãa]o\s+(NTT|Logicalis)\s*", re.IGNORECASE)
_ETC_SUFFIX_RE = re.compile(r"\s*-\s*ETC[\s\-]?\d{4,6}\s*$", re.IGNORECASE)

_NTT_ID_RE = re.compile(r"\bNTT[\s\-]?0*(\d{4,6})\b", re.IGNORECASE)
_ETC_ID_RE = re.compile(r"\bETC[\s\-]?0*(\d{4,6})\b", re.IGNORECASE)
_PRJ_RE = re.compile(r"\bPRJ[\s\-]?\d{4,}\b", re.IGNORECASE)
_P00_RE = re.compile(r"\bP\d{6,}\b")

MERGE_FIELDS = (
    "request_type", "project_type", "requester_name", "department",
    "cnpj", "smart_account", "smart_account_domain", "virtual_account", "project_ref",
)


def normalize_subject(subject: str) -> str:
    """Reduz o assunto ao 'nome do projeto', removendo prefixos de reply/encaminhamento
    e as marcações de ID que cada vendor injeta ao longo da conversa."""
    s = subject or ""
    prev = None
    while prev != s:
        prev = s
        s = _REPLY_PREFIX_RE.sub("", s)
    s = _VENDOR_ID_PREFIX_RE.sub("", s)
    s = _VENDOR_LABEL_RE.sub("", s)
    s = _ETC_SUFFIX_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def detect_vendor(*addresses: str) -> str:
    """Identifica o vendor pelo domínio real do header From/To (nunca pelo envelope/
    Return-Path, que pode ser um relay como owner-extdom.tracking-cisco@cisco.com)."""
    blob = " ".join(a or "" for a in addresses).lower()
    for vendor, domains in VENDOR_DOMAINS.items():
        if any(d in blob for d in domains):
            return vendor
    return ""


def extract_vendor_ref(vendor: str, *texts: str) -> str:
    """Extrai o ID que o próprio vendor atribuiu à cotação (ex.: NTT31072, ETC 5773)."""
    blob = "\n".join(t or "" for t in texts)
    pattern = _NTT_ID_RE if vendor == "NTT" else _ETC_ID_RE if vendor == "Logicalis" else None
    if not pattern:
        return ""
    m = pattern.search(blob)
    return m.group(1) if m else ""


def extract_project_code(*texts: str) -> str:
    """PRJ = nome/número do projeto (prioridade); P0xxxxxxx = número do pedido (fallback)."""
    blob = "\n".join(t or "" for t in texts)
    m = _PRJ_RE.search(blob)
    if m:
        return m.group(0).upper()
    m = _P00_RE.search(blob)
    return m.group(0).upper() if m else ""


# ── Persistência da thread (Message-ID / In-Reply-To / References) ───────────

def _split_refs(*values: str) -> list:
    blob = " ".join(v or "" for v in values)
    return [ref.strip("<>") for ref in re.findall(r"<[^<>\s]+>|\S+", blob) if ref.strip("<>")]


def find_quote_by_message_id(*values: str):
    ids = _split_refs(*values)
    if not ids:
        return None
    with db.get_cursor() as cur:
        cur.execute("SELECT quote_id FROM email_threads WHERE message_id = ANY(%s) LIMIT 1", (ids,))
        row = cur.fetchone()
        return row["quote_id"] if row else None


def record_thread(message_id: str, quote_id: str, in_reply_to: str = "", references: str = "") -> None:
    if not message_id or not quote_id:
        return
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO email_threads (message_id, quote_id, in_reply_to, "references")
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (message_id) DO NOTHING
            """,
            (message_id.strip(), quote_id, in_reply_to or "", references or ""),
        )


def find_quote_by_project_name(normalized_subject: str, vendor: str, days: int = 180):
    """Fallback: mesmo nome de projeto normalizado + mesmo vendor (por domínio do
    remetente/destinatário salvo em raw_email), dentro de uma janela recente."""
    domains = VENDOR_DOMAINS.get(vendor, ())
    if not domains or not normalized_subject:
        return None
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT id, subject, raw_email FROM extractions
            WHERE date >= now() - (%s || ' days')::interval
            ORDER BY date DESC
            """,
            (days,),
        )
        rows = cur.fetchall()
    for row in rows:
        if normalize_subject(row["subject"] or "") != normalized_subject:
            continue
        raw = row["raw_email"] or {}
        blob = f"{raw.get('from', '')} {raw.get('to', '')}".lower()
        if any(d in blob for d in domains):
            return row["id"]
    return None


# ── Resolução principal ────────────────────────────────────────────────────────

def resolve(parsed: dict) -> dict:
    """Decide se o email recebido pertence a um quote_id já existente.

    Retorna dict com: quote_id (ou None -> criar novo), vendor, vendor_ref, project_code.
    Nunca cruza vendors diferentes (NTT x Logicalis) — na dúvida, quote_id fica None.
    """
    subject = parsed.get("subject", "")
    body = parsed.get("body", "")
    sender = parsed.get("from", "")
    recipient = parsed.get("to", "")

    result = {"quote_id": None, "vendor": "", "vendor_ref": "", "project_code": ""}

    quote_id = find_quote_by_message_id(parsed.get("in_reply_to", ""), parsed.get("references", ""))
    if quote_id:
        result["quote_id"] = quote_id

    vendor = detect_vendor(sender, recipient)
    result["vendor"] = vendor
    if not vendor:
        return result  # sem vendor reconhecido: só correlaciona via thread (já resolvido acima)

    vendor_ref = extract_vendor_ref(vendor, subject, body)
    result["vendor_ref"] = vendor_ref
    project_code = extract_project_code(subject, body)
    result["project_code"] = project_code

    if result["quote_id"]:
        return result

    deal_key = "ntt_id" if vendor == "NTT" else "logicalis_id"
    if vendor_ref:
        found = data_store.find_quote_by_deal_field(deal_key, vendor_ref)
        if found:
            result["quote_id"] = found
            return result

    if project_code:
        found = data_store.find_quote_by_deal_field("projeto_id_vale", project_code)
        if found:
            result["quote_id"] = found
            return result

    norm_subject = normalize_subject(subject)
    found = find_quote_by_project_name(norm_subject, vendor)
    if found:
        result["quote_id"] = found

    return result
