from __future__ import annotations


def _pt_br_number(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_integer(value: int | None) -> str:
    if value is None:
        return "Não disponível"
    return f"{value:,}".replace(",", ".")


def format_decimal(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "Não disponível"
    return _pt_br_number(float(value), decimals)


def format_percentage(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "Não disponível"
    return f"{format_decimal(float(value) * 100.0, decimals)}%"


def format_usd(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "Não disponível"
    return f"US$ {format_decimal(float(value), decimals)}"
