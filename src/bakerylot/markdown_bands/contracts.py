from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from unicodedata import normalize


class RecordError(ValueError):
    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}:{reason}")
        self.field = field
        self.reason = reason


def label(document: Mapping, key: str, *, max_chars: int) -> str:
    raw = document.get(key)
    if not isinstance(raw, str):
        raise RecordError(key, "TEXT_REQUIRED")
    value = normalize("NFKC", raw).strip()
    if not value or len(value) > max_chars:
        raise RecordError(key, "TEXT_LENGTH")
    if not all(ch.isprintable() for ch in value):
        raise RecordError(key, "TEXT_CONTROL")
    return value


def magnitude(document: Mapping, key: str, lower: float, upper: float, *, whole: bool) -> int | float:
    raw = document.get(key)
    if isinstance(raw, bool) or raw is None:
        raise RecordError(key, "NUMBER_REQUIRED")
    try:
        number = float(raw)
    except (ValueError, TypeError, OverflowError) as error:
        raise RecordError(key, "NUMBER_INVALID") from error
    if not isfinite(number):
        raise RecordError(key, "NUMBER_NONFINITE")
    if number < lower or number > upper:
        raise RecordError(key, "NUMBER_RANGE")
    if whole:
        if not number.is_integer():
            raise RecordError(key, "INTEGER_REQUIRED")
        return int(number)
    return number


@dataclass(frozen=True, slots=True)
class StockForecast:
    lot: str
    available: int
    forecast: float
    distance: float
    shelf_remaining: int
    price_cents: int

    @classmethod
    def parse(cls, document: Mapping) -> "StockForecast":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        lot = label(document, 'lot', max_chars=44)
        available = magnitude(document, 'available', 0, 5000, whole=True)
        forecast = magnitude(document, 'forecast', 0, 5000, whole=False)
        distance = magnitude(document, 'distance', 0, 100000, whole=False)
        shelf_remaining = magnitude(document, 'shelf_remaining', 0, 1440, whole=True)
        price_cents = magnitude(document, 'price_cents', 1, 55000, whole=True)
        return cls(
            lot=lot,
            available=available,
            forecast=forecast,
            distance=distance,
            shelf_remaining=shelf_remaining,
            price_cents=price_cents,
        )

    def evidence(self) -> dict:
        return {
            'lot': self.lot,
            'available': self.available,
            'forecast': self.forecast,
            'distance': self.distance,
            'shelf_remaining': self.shelf_remaining,
            'price_cents': self.price_cents,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
