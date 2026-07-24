import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portal


def test_parse_import_date_formato_br():
    assert portal._parse_import_date("15/06/2026") == "2026-06-15 00:00:00"


def test_parse_import_date_formato_iso():
    assert portal._parse_import_date("2026-06-15") == "2026-06-15 00:00:00"


def test_parse_import_date_iso_com_hora():
    assert portal._parse_import_date("2026-06-15 14:30:00") == "2026-06-15 14:30:00"


def test_parse_import_date_br_com_hora():
    assert portal._parse_import_date("15/06/2026 14:30:00") == "2026-06-15 14:30:00"


def test_parse_import_date_vazio_retorna_vazio():
    assert portal._parse_import_date("") == ""
    assert portal._parse_import_date(None) == ""


def test_parse_import_date_invalida_retorna_vazio_sem_lancar():
    assert portal._parse_import_date("data qualquer") == ""
    assert portal._parse_import_date("31/02/2026") == ""  # 31 de fevereiro não existe


def test_parse_import_date_datetime_stringificado_do_excel():
    # célula formatada como data no Excel chega como str(datetime(...)) via openpyxl
    assert portal._parse_import_date("2026-06-15 00:00:00") == "2026-06-15 00:00:00"
