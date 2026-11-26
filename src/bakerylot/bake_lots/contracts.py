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
class OvenTicket:
    lot: str
    revision: int
    day: int
    station: str
    sku: str
    baked: int
    arrival_min: int
    shelf_minutes: int
    display_min: int
    price_cents: int

    @classmethod
    def parse(cls, document: Mapping) -> "OvenTicket":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        lot = label(document, 'lot', max_chars=40)
        revision = magnitude(document, 'revision', 1, 99, whole=True)
        day = magnitude(document, 'day', 1, 366, whole=True)
        station = label(document, 'station', max_chars=32)
        sku = label(document, 'sku', max_chars=40)
        baked = magnitude(document, 'baked', 1, 1000, whole=True)
        arrival_min = magnitude(document, 'arrival_min', 0, 1439, whole=True)
        shelf_minutes = magnitude(document, 'shelf_minutes', 1, 1440, whole=True)
        display_min = magnitude(document, 'display_min', 0, 1439, whole=True)
        price_cents = magnitude(document, 'price_cents', 1, 50000, whole=True)
        return cls(
            lot=lot,
            revision=revision,
            day=day,
            station=station,
            sku=sku,
            baked=baked,
            arrival_min=arrival_min,
            shelf_minutes=shelf_minutes,
            display_min=display_min,
            price_cents=price_cents,
        )

    def evidence(self) -> dict:
        return {
            'lot': self.lot,
            'revision': self.revision,
            'day': self.day,
            'station': self.station,
            'sku': self.sku,
            'baked': self.baked,
            'arrival_min': self.arrival_min,
            'shelf_minutes': self.shelf_minutes,
            'display_min': self.display_min,
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
