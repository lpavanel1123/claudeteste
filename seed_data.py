"""
Gera dados de treinamento realistas para o portal.
Uso: python3 seed_data.py
Marca todas as entradas com "is_training": true.
"""
import json
import uuid
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

REQUESTERS = [
    ("Carlos Eduardo Ferreira", "Tecnologia Operacional - Santos, SP"),
    ("Mariana Silva Costa", "TI - Infraestrutura - São Paulo, SP"),
    ("Roberto Alves Mendes", "Redes e Segurança - Rio de Janeiro, RJ"),
    ("Fernanda Lima Souza", "Operações de TI - Brasília, DF"),
    ("Lucas Pavanelli", "Tecnologia Operacional Porto - Vitoria, ES"),
    ("Juliana Rocha Neves", "Segurança da Informação - Belo Horizonte, MG"),
    ("André Martins Pinto", "Infraestrutura e Redes - Curitiba, PR"),
    ("Patricia Gomes Ramos", "TI | Technology - Recife, PE"),
    ("Diego Carvalho Teixeira", "Datacenter Operations - Campinas, SP"),
    ("Ana Paula Barbosa", "Conectividade e Redes - Manaus, AM"),
]

COMPANIES = [
    ("Vale S.A.", "33.592.510/0001-54"),
    ("Petrobras S.A.", "33.000.167/0001-01"),
    ("Eletrobras S.A.", "00.001.180/0001-26"),
    ("Porto de Santos", "60.447.591/0001-69"),
    ("Transpetro", "08.292.811/0001-03"),
    ("Braskem S.A.", "42.150.391/0001-70"),
    ("CEDAE", "33.352.394/0001-04"),
    ("Embraer S.A.", "07.689.002/0001-89"),
]

PRODUCTS_CATALOG = [
    {"part_number": "C9300-48P-A",       "description": "Catalyst 9300 48-port PoE+ Network Advantage"},
    {"part_number": "C9300-24T-A",       "description": "Catalyst 9300 24-port data only, Network Advantage"},
    {"part_number": "C9500-48Y4C-A",     "description": "Catalyst 9500 48-port 25G + 4x100G, Network Advantage"},
    {"part_number": "C9200-24T-A",       "description": "Catalyst 9200 24-port data only, Network Advantage"},
    {"part_number": "N9K-C93180YC-FX3",  "description": "Nexus 9300 with 48p 1/10G/25G SFP28 + 6p 100G QSFP28"},
    {"part_number": "C8300-1N1S-6T",     "description": "Catalyst 8300 Series Edge Platform"},
    {"part_number": "ISR4331/K9",        "description": "Cisco ISR 4331 Router"},
    {"part_number": "FPR2130-NGFW-K9",  "description": "Firepower 2130 NGFW Appliance, 1U"},
    {"part_number": "FPR1140-NGFW-K9",  "description": "Firepower 1140 NGFW Appliance"},
    {"part_number": "AIR-AP2802I-B-K9", "description": "Aironet 2800 Series Access Point"},
    {"part_number": "C9800-40-K9",       "description": "Catalyst 9800-40 Wireless Controller"},
    {"part_number": "PWR-C1-715WAC-P/2", "description": "715W AC 80+ Platinum Config 1 Secondary Power Supply"},
    {"part_number": "SFP-10G-LR",        "description": "10GBASE-LR SFP Module"},
    {"part_number": "QSFP-40G-SR4",      "description": "40GBASE-SR4 QSFP Transceiver Module"},
    {"part_number": "C9300-NM-8X",       "description": "Catalyst 9300 8x10GE Network Module"},
    {"part_number": "StackPower-Cable-30CM", "description": "StackPower cable 30cm"},
    {"part_number": "DNA-A-3Y",          "description": "Cisco DNA Advantage 3-Year Term License"},
    {"part_number": "C9300-DNA-A-24",    "description": "Cisco DNA Advantage 24-port License"},
    {"part_number": "ASA5545-K9",        "description": "ASA 5545-X Firewall Edition"},
    {"part_number": "WS-C3850-24T-S",   "description": "Catalyst 3850 24 Port Data IP Base"},
]

SUBJECTS_COTACAO = [
    "Cotação de switches para expansão de datacenter",
    "Solicitação de proposta - Equipamentos Cisco",
    "Cotação - Renovação de infraestrutura de rede",
    "Gentileza nos fornecer cotação conforme anexo",
    "Pedido de cotação - Switches e roteadores",
    "Cotação equipamentos Cisco - Projeto expansão",
    "Solicitação de orçamento - Firewall e switches",
    "Cotação urgente - Substituição de switches core",
    "Proposta comercial solicitada - Equipamentos Cisco",
    "Cotação - Access Points e controladora wireless",
]

SUBJECTS_PEDIDO = [
    "Pedido de compra - Equipamentos Cisco",
    "Ordem de compra - Switches datacenter",
    "PO #2026-0{n} - Cisco networking gear",
    "Pedido formal - Firewall Firepower",
    "Ordem de fornecimento - Switches Catalyst 9300",
]

SMART_ACCOUNTS = [
    ("BR (Brasil)", "vale.com", "BR-OT-SP-SANTOS"),
    ("BR (Brasil)", "petrobras.com.br", "BR-TI-RJ-CENTRO"),
    ("BR (Brasil)", "eletrobras.com", "BR-OPS-BSB-LAGO"),
    ("BR (Brasil)", "portosantos.com.br", "BR-NET-SP-SANTOS"),
    ("BR (Brasil)", "transpetro.com.br", "BR-INF-RJ-CENTRO"),
]

STATUSES   = ["Em Aberto", "Em Análise", "Aprovada", "Ganha", "Perdida", "Rejeitada"]
STATUS_W   = [0.30, 0.25, 0.20, 0.12, 0.08, 0.05]
TYPES      = ["Cotação", "Cotação", "Cotação", "Pedido", "Pedido"]
PROJ_TYPES = ["NA", "NA", "NA", "Novo Projeto", "Obsolescência"]


def _random_products(n: int = None):
    if n is None:
        n = random.randint(2, 8)
    items = random.sample(PRODUCTS_CATALOG, min(n, len(PRODUCTS_CATALOG)))
    return [{"qty": str(random.choice([1, 2, 2, 4, 4, 8, 10, 16])),
             "part_number": p["part_number"],
             "description": p["description"]} for p in items]


def _random_date(weeks_ago_max: int = 10) -> str:
    delta = timedelta(days=random.randint(0, weeks_ago_max * 7))
    return (datetime.now() - delta).strftime("%Y-%m-%d %H:%M:%S")


def _body(name: str, dept: str, rtype: str, sa: tuple) -> str:
    greeting = random.choice(["Prezados, boa tarde.", "Bom dia a todos.", "Prezados,"])
    verb = "cotação" if rtype == "Cotação" else "pedido de compra"
    return f"""{greeting}

Gentileza nos fornecer {verb} conforme planilha em anexo.

CNPJ contribuinte conforme cadastro.

Smart Account Domain ID: {sa[1]} (Fixo)
Smart Account: {sa[0]}
Virtual Account: {sa[2]}.

Quaisquer dúvidas, estou à disposição.

At.te,

{name}
{dept}
Tel. (+55) 11 3xxx-xxxx
www.empresa.com.br"""


def generate(n: int = 28) -> list:
    quotes = []
    for i in range(n):
        requester, dept = random.choice(REQUESTERS)
        company, cnpj   = random.choice(COMPANIES)
        sa               = random.choice(SMART_ACCOUNTS)
        rtype            = random.choice(TYPES)
        ptype            = random.choice(PROJ_TYPES)
        date             = _random_date()

        subj_pool = SUBJECTS_COTACAO if rtype == "Cotação" else SUBJECTS_PEDIDO
        subject   = random.choice(subj_pool).replace("{n}", str(i + 100))

        entry = {
            "id":                    str(uuid.uuid4()),
            "is_training":           True,
            "date":                  date,
            "from":                  f"{requester.lower().replace(' ', '.')[:20]}@{sa[1]}",
            "subject":               subject,
            "request_type":          rtype,
            "project_type":          ptype,
            "requester_name":        requester,
            "department":            dept,
            "recipient":             "451afe006c20b48af958@cloudmailin.net",
            "cnpj":                  cnpj,
            "smart_account":         sa[0],
            "smart_account_domain":  sa[1],
            "virtual_account":       sa[2],
            "project_ref":           f"PROJ-2026-{i+1:03d}" if random.random() > 0.4 else "NA",
            "products":              _random_products(),
            "body":                  _body(requester, dept, rtype, sa),
        }
        quotes.append(entry)
    return quotes


def seed_annotations(quotes: list) -> dict:
    annotations = {}
    for q in quotes:
        if random.random() < 0.75:
            status  = random.choices(STATUSES, STATUS_W)[0]
            valor   = round(random.uniform(8_000, 980_000), 2) if random.random() > 0.3 else None
            annotations[q["id"]] = {
                "status":              status,
                "valor_total":         valor,
                "responsavel_interno": random.choice(["João Silva", "Marina Faria", "Pedro Cunha", "Aline Torres", ""]),
                "fornecedor":          random.choice(["Cisco Brasil", "Westcon", "Ingram Micro", "TD SYNNEX", "Logicalis", "NTT", ""]),
                "observacoes":         "",
                "updated_at":          q["date"],
                "updated_by":          "seed",
            }
    return annotations


def main():
    quotes = generate(28)

    extr_path = Path("extractions.json")
    existing  = json.loads(extr_path.read_text(encoding="utf-8")) if extr_path.exists() else []
    extr_path.write_text(json.dumps(existing + quotes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[seed] {len(quotes)} cotações de treinamento adicionadas a extractions.json")

    Path("data").mkdir(exist_ok=True)
    ann_path = Path("data/annotations.json")
    existing_ann = json.loads(ann_path.read_text(encoding="utf-8")) if ann_path.exists() else {}
    existing_ann.update(seed_annotations(quotes))
    ann_path.write_text(json.dumps(existing_ann, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[seed] annotations atualizadas")


if __name__ == "__main__":
    main()
