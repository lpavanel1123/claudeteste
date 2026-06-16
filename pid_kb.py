"""
PID Knowledge Base — aprende de classificações manuais.

Fluxo:
  1. No upload: classify_with_kb() tenta a KB primeiro, usa o classifier como fallback
     e grava o resultado automaticamente (source="auto").
  2. Quando o usuário corrige manualmente: update() é chamado com source="manual".
  3. Entradas "manual" têm precedência sobre "auto" e nunca são sobrescritas pelo
     upload automático.
"""

import json
from pathlib import Path

_KB_FILE = Path("data/pid_kb.json")


def _load() -> dict:
    if not _KB_FILE.exists():
        return {}
    try:
        return json.loads(_KB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(kb: dict) -> None:
    _KB_FILE.parent.mkdir(exist_ok=True)
    _KB_FILE.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")


def lookup(pid: str):
    """Return (arquitetura, categoria) from KB, or (None, None) if not found."""
    entry = _load().get(str(pid).strip().upper())
    if entry:
        return entry.get("arquitetura"), entry.get("categoria")
    return None, None


def update(pid: str, arquitetura: str, categoria: str, source: str = "manual") -> None:
    """Persist a classification for a PID.

    Manual entries are never overwritten by auto-classification on future uploads.
    """
    kb  = _load()
    key = str(pid).strip().upper()
    existing = kb.get(key, {})
    # Don't downgrade a manual entry to auto
    if existing.get("source") == "manual" and source == "auto":
        return
    kb[key] = {"arquitetura": arquitetura, "categoria": categoria, "source": source}
    _save(kb)


def classify_with_kb(pid: str, desc: str, classifier_fn) -> tuple:
    """Classify a PID, using KB first and classifier as fallback.

    Stores the result in KB with source='auto' so future lookups are faster.
    Manual entries are never overwritten here.
    """
    arch, cat = lookup(pid)
    if arch:
        return arch, cat
    arch, cat = classifier_fn(pid, desc)
    update(pid, arch, cat, source="auto")
    return arch, cat


def apply_manual_corrections(old_products: list, new_products: list) -> int:
    """Compare old vs new product lists and persist manual overrides to KB.

    Returns the number of PIDs updated.
    """
    old_map = {p["part_number"].strip().upper(): p for p in old_products if p.get("part_number")}
    count = 0
    for p in new_products:
        pid = str(p.get("part_number") or "").strip().upper()
        if not pid:
            continue
        new_arch = p.get("arquitetura", "")
        new_cat  = p.get("categoria", "")
        if not new_arch:
            continue
        old = old_map.get(pid, {})
        old_arch = old.get("arquitetura", "")
        old_cat  = old.get("categoria", "")
        # If arquitetura or categoria changed, it's a manual correction
        if new_arch != old_arch or new_cat != old_cat:
            update(pid, new_arch, new_cat, source="manual")
            count += 1
    return count
