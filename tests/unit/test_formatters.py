from agentscope.reporting.formatters import (
    format_decimal,
    format_integer,
    format_percentage,
    format_usd,
)


def test_formats_integer_with_pt_br_thousands_separator():
    assert format_integer(1465312344) == "1.465.312.344"
    assert format_integer(0) == "0"
    assert format_integer(None) == "Não disponível"


def test_formats_decimal_with_pt_br_decimal_separator():
    assert format_decimal(4.3144, 4) == "4,3144"
    assert format_decimal(1234.5, 2) == "1.234,50"
    assert format_decimal(None) == "Não disponível"


def test_formats_ratio_as_percentage():
    assert format_percentage(0.9463) == "94,63%"
    assert format_percentage(0.0) == "0,00%"
    assert format_percentage(None) == "Não disponível"


def test_formats_usd_summary_with_two_decimals():
    assert format_usd(13.777432) == "US$ 13,78"
    assert format_usd(1234.5) == "US$ 1.234,50"
    assert format_usd(None) == "Não disponível"


def test_usd_detail_can_preserve_more_precision():
    assert format_usd(0.003, decimals=6) == "US$ 0,003000"
