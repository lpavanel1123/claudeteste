import re

# ── Architecture: PID prefix rules (checked in order) ────────────────────────
# For CON-* items, the prefix is stripped first so the underlying product PID
# is matched (e.g. CON-L1NBD-N9KC93X3 → N9KC93X3 → Datacenter).

_ARCH_PID = [
    # Datacenter: Nexus, NXA/NXK accessories, UCS, CML, NX-OS, Nexus power cords
    (re.compile(r'^(N[39]K-|NXA-|NXK-|NXS-|UCS[BCSX]?-|CML-|NXOS-|DCN-|MEM-UPG|C1-SUBS-|MODE-NX|CAB-250V)', re.I), 'Datacenter'),
    # Enterprise Switching: Catalyst 9x00, C9K accessories, IOS XE images, TE agents on C9K
    # Note: match C9[2-6][0-9]{2} without requiring dash — works for CON-stripped PIDs too
    (re.compile(r'^(C9[2-6][0-9]{2}|C9K-|C9N-|WS-C|CAB-AC|PWR-C1-|STACK-T|CAB-GUIDE|C9[0-9]+-NM|SC9|S9[35]|NETWORK-PNP|TE-|D-DNAS-)', re.I), 'Enterprise Switching'),
    (re.compile(r'^(AIR-|C91[0-3][0-9]-|C9120|C9124|C9130|C9136|ANT-)', re.I), 'Wireless'),
    (re.compile(r'^(ISR|ASR|C8[0-9]{3}-|ENCS|VBOND|VSMART|VMANAGE|IR[0-9]{3}-)', re.I), 'Routing'),
    (re.compile(r'^(FPR-|FTD-|ASA[0-9-]|IPS-|FMC-|ISE-|AMP-)', re.I), 'Segurança'),
    (re.compile(r'^(IE-|CGR[0-9]|IC3000|ESS-)', re.I), 'IOT'),
]

_ARCH_DESC = [
    (re.compile(r'nexus|n9k|n3k|datacenter|data center|ucs|\bcml\b|modeling lab|nxos', re.I), 'Datacenter'),
    (re.compile(r'catalyst 9[2-6]|\bC9[2-6][0-9]{2}\b|switch|stacking|stack cable|fan tray|power supply|power cord|rubber feet|rack|screws|cable management|thousandeyes', re.I), 'Enterprise Switching'),
    (re.compile(r'wireless|access point|wi-?fi|aironet', re.I), 'Wireless'),
    (re.compile(r'router|routing|\bisr\b|\basr\b|sd-wan|viptela', re.I), 'Routing'),
    (re.compile(r'firewall|\basa\b|\bftd\b|ngfw|ngips|identity services|\bise\b', re.I), 'Segurança'),
    (re.compile(r'industrial|\biot\b', re.I), 'IOT'),
]

# ── Category: Serviços / Software / Hardware ──────────────────────────────────

_SVC_PID  = re.compile(r'^(CON-|SVS-|SNTC-)', re.I)
_SVC_DESC = re.compile(
    r'\b(support|maintenance|nbd|cx level|sntc|smartnet|service agreement|supt for|sw supt|sw bas supt|sw sub)\b',
    re.I,
)

_SW_PID = re.compile(
    r'(-DNA-|-DNA$|-LIC\b|-NW-A|-NW-E|-NW-\d|NXOS-|^SC9|^S9[35]|CML-ENT|NXOS-AD|'
    r'(-3Y|-1Y|-5Y)$|^NETWORK-PNP-LIC|^TE-EMBEDDED|^TE-C9K|^D-DNAS-|^MODE-NXOS|'
    r'^MEM-UPG-OPT|^C1-SUBS-OPT|^DCN-OTHER|^NXK-AF-|NXOS-CS-)',
    re.I,
)
_SW_DESC = re.compile(
    r'\b(license|dna\b|term license|subscription|ios xe|nxos|software|'
    r'plug-n-play|thousandeyes|dna spaces|modeling lab|opt out)\b',
    re.I,
)

# Strip CON-XXXXX- prefix to get the "effective" PID for architecture lookup
_CON_PREFIX = re.compile(r'^CON-[A-Z0-9]+-', re.I)
_SVS_PREFIX = re.compile(r'^SVS-[A-Z0-9]+-', re.I)


def classify(part_number: str, description: str) -> tuple:
    """Return (arquitetura, categoria) for a Cisco product line."""
    pid  = str(part_number or "").strip()
    desc = str(description  or "").strip()

    # ── categoria ──
    if _SVC_PID.match(pid) or _SVC_DESC.search(desc):
        categoria = 'Serviços'
    elif _SW_PID.search(pid) or _SW_DESC.search(desc):
        categoria = 'Software'
    else:
        categoria = 'Hardware'

    # ── arquitetura ──
    # Strip service wrapper to expose the underlying product PID
    if pid.upper().startswith('CON-'):
        effective = _CON_PREFIX.sub('', pid)
    elif pid.upper().startswith('SVS-'):
        effective = _SVS_PREFIX.sub('', pid)
    else:
        effective = pid

    arquitetura = 'Outros'
    for pattern, arch in _ARCH_PID:
        if pattern.match(effective):
            arquitetura = arch
            break

    if arquitetura == 'Outros':
        for pattern, arch in _ARCH_DESC:
            if pattern.search(desc):
                arquitetura = arch
                break

    return arquitetura, categoria
