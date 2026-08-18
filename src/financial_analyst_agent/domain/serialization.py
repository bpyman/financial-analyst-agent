"""JSON serialization helpers for exact monetary values."""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer


def validate_monetary_value(value: Any) -> Decimal:
    """Reject float/bool coercion; accept Decimal, int, and exact decimal strings."""
    if isinstance(value, bool):
        raise ValueError("monetary values cannot be boolean")
    if isinstance(value, float):
        raise ValueError("monetary values cannot be float; use Decimal or exact decimal string")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"invalid monetary string: {value!r}") from exc
    raise ValueError(f"monetary values must be Decimal, int, or str, got {type(value).__name__}")


DecimalStr = Annotated[
    Decimal,
    BeforeValidator(validate_monetary_value),
    PlainSerializer(str, return_type=str),
]
