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
class StockMovement:
    movement: str
    lot: str
    kind: str
    units: int
    day: int
    posted_min: int
    discount_cents: int

    @classmethod
    def parse(cls, document: Mapping) -> "StockMovement":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        movement = label(document, 'movement', max_chars=40)
        lot = label(document, 'lot', max_chars=40)
        kind = label(document, 'kind', max_chars=16)
        units = magnitude(document, 'units', 0, 20000, whole=True)
        day = magnitude(document, 'day', 1, 366, whole=True)
        posted_min = magnitude(document, 'posted_min', 0, 1439, whole=True)
        discount_cents = magnitude(document, 'discount_cents', 0, 50000, whole=True)
        return cls(
            movement=movement,
            lot=lot,
            kind=kind,
            units=units,
            day=day,
            posted_min=posted_min,
            discount_cents=discount_cents,
        )

    def evidence(self) -> dict:
        return {
            'movement': self.movement,
            'lot': self.lot,
            'kind': self.kind,
            'units': self.units,
            'day': self.day,
            'posted_min': self.posted_min,
            'discount_cents': self.discount_cents,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
