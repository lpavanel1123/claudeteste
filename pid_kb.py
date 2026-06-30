"""
PID Knowledge Base — aprende de classificações manuais.

Fluxo:
  1. No upload: classify_with_kb() tenta a KB primeiro, usa o classifier como fallback
     e grava o resultado automaticamente (source="auto").
  2. Quando o usuário corrige manualmente: update() é chamado com source="manual".
  3. Entradas "manual" têm precedência sobre "auto" e nunca são sobrescritas pelo
     upload automático.
"""

import db


def lookup(pid: str):
    """Return (arquitetura, categoria) from KB, or (None, None) if not found."""
    with db.get_cursor() as cur:
        cur.execute(
            "SELECT arquitetura, categoria FROM pid_kb WHERE part_number = %s",
            (str(pid).strip().upper(),),
        )
        row = cur.fetchone()
    if row:
        return row["arquitetura"], row["categoria"]
    return None, None


def update(pid: str, arquitetura: str, categoria: str, source: str = "manual") -> None:
    """Persist a classification for a PID.

    Manual entries are never overwritten by auto-classification on future uploads.
    """
    key = str(pid).strip().upper()
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO pid_kb (part_number, arquitetura, categoria, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (part_number) DO UPDATE SET
                arquitetura = EXCLUDED.arquitetura,
                categoria   = EXCLUDED.categoria,
                source      = EXCLUDED.source
            WHERE pid_kb.source <> 'manual' OR EXCLUDED.source = 'manual'
            """,
            (key, arquitetura, categoria, source),
        )


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
        old      = old_map.get(pid, {})
        old_arch = old.get("arquitetura", "")
        old_cat  = old.get("categoria", "")
        if new_arch != old_arch or new_cat != old_cat:
            update(pid, new_arch, new_cat, source="manual")
            count += 1
    return count
