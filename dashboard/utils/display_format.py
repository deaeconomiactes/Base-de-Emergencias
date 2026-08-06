"""Formateadores semanticos para la capa visual del dashboard.

Las funciones no modifican los valores de origen ni deben usarse en joins,
filtros, agrupaciones o calculos.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import pandas as pd


MISSING_TEXT = {"", "none", "nan", "nat", "null", "<na>", "s/d", "sd", "sin dato", "sin datos"}


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in MISSING_TEXT
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def format_missing(value, label: str = "Sin dato") -> str:
    return label if _is_missing(value) else str(value).strip()


def _decimal(value) -> Decimal | None:
    if _is_missing(value):
        return None
    text = str(value).strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", text):
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _number_es(number: Decimal, decimals: int) -> str:
    rendered = f"{number:,.{decimals}f}"
    return rendered.replace(",", "X").replace(".", ",").replace("X", ".")


def format_year(value) -> str:
    if _is_missing(value):
        return "Sin dato"
    text = str(value).strip()
    compact = re.sub(r"[.,\s]", "", re.sub(r"\.0+$", "", text))
    if re.fullmatch(r"\d{4}", compact):
        year = int(compact)
        if 1000 <= year <= 2999:
            return str(year)
    number = _decimal(value)
    if number is not None and number == number.to_integral_value() and 1000 <= int(number) <= 2999:
        return str(int(number))
    return "Sin dato"


def _digits(value) -> str:
    if _is_missing(value):
        return ""
    text = re.sub(r"\.0+$", "", str(value).strip())
    return re.sub(r"\D", "", text)


def format_cuit_cuil(value) -> str:
    digits = _digits(value)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
    return digits or "No registra"


def format_document(value) -> str:
    return _digits(value) or "No registra"


def format_renspa(value) -> str:
    return "No registra" if _is_missing(value) else str(value).strip()


def format_adrema(value) -> str:
    return "No registra" if _is_missing(value) else str(value).strip()


def format_date(value) -> str:
    if _is_missing(value):
        return "Sin dato"
    parsed = pd.to_datetime(value, errors="coerce")
    return "Sin dato" if pd.isna(parsed) else parsed.strftime("%d/%m/%Y")


def format_surface(value) -> str:
    number = _decimal(value)
    return "No registra" if number is None else f"{_number_es(number, 2)} ha"


def format_percentage(value, scale: str = "0-100") -> str:
    number = _decimal(value)
    if number is None:
        return "Sin dato"
    if scale == "0-1":
        number *= 100
    elif scale != "0-100":
        raise ValueError("scale debe ser '0-1' o '0-100'")
    return f"{_number_es(number, 2)} %"


def format_money(value, currency: str = "ARS") -> str:
    number = _decimal(value)
    if number is None:
        return "Sin dato"
    decimals = 0 if number == number.to_integral_value() else 2
    return f"{currency} {_number_es(number, decimals)}"


def format_quantity(value, unit=None) -> str:
    number = _decimal(value)
    if number is None:
        return "Sin dato"
    decimals = 0 if number == number.to_integral_value() else 2
    rendered = _number_es(number, decimals)
    unit_text = format_missing(unit, "").strip()
    return f"{rendered} {unit_text}".strip()


def format_count(value) -> str:
    number = _decimal(value)
    if number is None or number != number.to_integral_value():
        return "Sin dato"
    return f"{int(number):,}".replace(",", ".")


def clean_display_name(value) -> str:
    if _is_missing(value):
        return "Sin dato"
    return re.sub(r"\s+", " ", str(value).strip())


def format_code(value, missing: str = "Sin dato") -> str:
    if _is_missing(value):
        return missing
    return re.sub(r"\.0+$", "", str(value).strip())
