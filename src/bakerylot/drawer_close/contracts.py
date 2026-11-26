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
class SaleSlip:
    slip: str
    lot: str
    station: str
    units: int
    list_cents: int
    charged_cents: int
    voucher_cents: int

    @classmethod
    def parse(cls, document: Mapping) -> "SaleSlip":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        slip = label(document, 'slip', max_chars=44)
        lot = label(document, 'lot', max_chars=40)
        station = label(document, 'station', max_chars=40)
        units = magnitude(document, 'units', 1, 10000, whole=True)
        list_cents = magnitude(document, 'list_cents', 1, 55000, whole=True)
        charged_cents = magnitude(document, 'charged_cents', 0, 10000000, whole=True)
        voucher_cents = magnitude(document, 'voucher_cents', 0, 10000000, whole=True)
        return cls(
            slip=slip,
            lot=lot,
            station=station,
            units=units,
            list_cents=list_cents,
            charged_cents=charged_cents,
            voucher_cents=voucher_cents,
        )

    def evidence(self) -> dict:
        return {
            'slip': self.slip,
            'lot': self.lot,
            'station': self.station,
            'units': self.units,
            'list_cents': self.list_cents,
            'charged_cents': self.charged_cents,
            'voucher_cents': self.voucher_cents,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
