"""The troy-ounce to INR/gram conversion must be exact and guarded."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.providers.frankfurter import usd_ounce_to_inr_gram


def test_known_conversion_value() -> None:
    # 2000 USD/oz * 85 INR/USD / 31.1034768 g/oz == 5465.6269... INR/g
    value = usd_ounce_to_inr_gram(Decimal("2000"), Decimal("85"))
    assert value.quantize(Decimal("0.01")) == Decimal("5465.63")


def test_conversion_is_exact_rational() -> None:
    value = usd_ounce_to_inr_gram(Decimal("100"), Decimal("100"))
    expected = Decimal("100") * Decimal("100") / Decimal("31.1034768")
    assert value == expected


@pytest.mark.parametrize(
    ("price", "rate"),
    [
        (Decimal("0"), Decimal("85")),
        (Decimal("-1"), Decimal("85")),
        (Decimal("2000"), Decimal("0")),
        (Decimal("2000"), Decimal("-1")),
    ],
)
def test_rejects_non_positive_inputs(price: Decimal, rate: Decimal) -> None:
    with pytest.raises(ValueError):
        usd_ounce_to_inr_gram(price, rate)
