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
class MarkdownRequest:
    lot: str
    decision: str
    sku: str
    station: str
    available: int
    at_risk: int
    priority: float
    price_cents: int
    markdown_pct: int

    @classmethod
    def parse(cls, document: Mapping) -> "MarkdownRequest":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        lot = label(document, 'lot', max_chars=34)
        decision = label(document, 'decision', max_chars=36)
        sku = label(document, 'sku', max_chars=40)
        station = label(document, 'station', max_chars=40)
        available = magnitude(document, 'available', 0, 2000, whole=True)
        at_risk = magnitude(document, 'at_risk', 0, 2000, whole=True)
        priority = magnitude(document, 'priority', 0, 2000, whole=False)
        price_cents = magnitude(document, 'price_cents', 1, 50000, whole=True)
        markdown_pct = magnitude(document, 'markdown_pct', 1, 45, whole=True)
        return cls(
            lot=lot,
            decision=decision,
            sku=sku,
            station=station,
            available=available,
            at_risk=at_risk,
            priority=priority,
            price_cents=price_cents,
            markdown_pct=markdown_pct,
        )

    def evidence(self) -> dict:
        return {
            'lot': self.lot,
            'decision': self.decision,
            'sku': self.sku,
            'station': self.station,
            'available': self.available,
            'at_risk': self.at_risk,
            'priority': self.priority,
            'price_cents': self.price_cents,
            'markdown_pct': self.markdown_pct,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
