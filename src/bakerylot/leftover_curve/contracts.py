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
class DailyFinish:
    historical_lot: str
    day: int
    station: str
    sku: str
    remaining: int
    minutes: int
    late_sales: int
    daypart: int
    rain_mm: float
    censored: int
    observed_day: int

    @classmethod
    def parse(cls, document: Mapping) -> "DailyFinish":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        historical_lot = label(document, 'historical_lot', max_chars=36)
        day = magnitude(document, 'day', 1, 366, whole=True)
        station = label(document, 'station', max_chars=40)
        sku = label(document, 'sku', max_chars=40)
        remaining = magnitude(document, 'remaining', 0, 3000, whole=True)
        minutes = magnitude(document, 'minutes', 0, 1440, whole=True)
        late_sales = magnitude(document, 'late_sales', 0, 3000, whole=True)
        daypart = magnitude(document, 'daypart', 0, 6, whole=True)
        rain_mm = magnitude(document, 'rain_mm', 0, 500, whole=False)
        censored = magnitude(document, 'censored', 0, 1, whole=True)
        observed_day = magnitude(document, 'observed_day', 1, 366, whole=True)
        return cls(
            historical_lot=historical_lot,
            day=day,
            station=station,
            sku=sku,
            remaining=remaining,
            minutes=minutes,
            late_sales=late_sales,
            daypart=daypart,
            rain_mm=rain_mm,
            censored=censored,
            observed_day=observed_day,
        )

    def evidence(self) -> dict:
        return {
            'historical_lot': self.historical_lot,
            'day': self.day,
            'station': self.station,
            'sku': self.sku,
            'remaining': self.remaining,
            'minutes': self.minutes,
            'late_sales': self.late_sales,
            'daypart': self.daypart,
            'rain_mm': self.rain_mm,
            'censored': self.censored,
            'observed_day': self.observed_day,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
