from dataclasses import dataclass
from math import fsum, sqrt
from statistics import median
from .contracts import DailyFinish


FEATURES = ("remaining", "minutes", "daypart", "rain_mm")


@dataclass(frozen=True, slots=True)
class Curve:
    intercept: float
    slope: tuple[float, ...]
    moments: tuple[tuple[float, float], ...]
    count: int


def points(sample: DailyFinish) -> tuple[float, ...]:
    return tuple(float(getattr(sample, feature)) for feature in FEATURES)


def center_scale(values: list[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("NO_OBSERVATIONS")
    mean = fsum(values) / len(values)
    variance = fsum((value - mean) ** 2 for value in values) / len(values)
    return mean, sqrt(variance) if variance > 1e-12 else 1.0


def chronological_sample(history, cut_day: int, *, product: str | None = None):
    visible = [row for row in history if row.day < cut_day and row.observed_day < cut_day
               and not row.censored and row.late_sales <= row.remaining]
    if product:
        matching = [row for row in visible if row.sku == product]
        if len(matching) >= 12:
            visible = matching
    return sorted(visible, key=lambda row: (row.day, row.historical_lot))


def fit(history, cut_day: int, *, product=None, penalty: float = 0.10) -> Curve:
    if penalty < 0:
        raise ValueError("PENALTY_NEGATIVE")
    sequence = chronological_sample(history, cut_day, product=product)
    if len(sequence) < 4:
        raise ValueError("HISTORY_TOO_SMALL")
    raw = [points(row) for row in sequence]
    moments = tuple(center_scale(list(values)) for values in zip(*raw, strict=True))
    inputs = [tuple((value - mean) / scale for value, (mean, scale) in zip(row, moments, strict=True)) for row in raw]
    target = [row.late_sales for row in sequence]
    intercept = median(target)
    weights = [0.0] * len(FEATURES)
    for _ in range(75):
        errors = [intercept + fsum(a * b for a, b in zip(row, weights, strict=True)) - y
                  for row, y in zip(inputs, target, strict=True)]
        gradient = [max(-4.0, min(4.0, error)) for error in errors]
        intercept -= 0.10 * fsum(gradient) / len(sequence)
        for j, weight in enumerate(weights):
            direction = fsum(x[j] * error for x, error in zip(inputs, gradient, strict=True)) / len(sequence)
            weights[j] = weight - 0.10 * (direction + penalty * weight)
    return Curve(intercept, tuple(weights), moments, len(target))


def one(curve: Curve, values: tuple[float, ...]) -> float:
    normalized = [(value - mean) / scale for value, (mean, scale) in zip(values, curve.moments, strict=True)]
    result = curve.intercept + fsum(w * x for w, x in zip(curve.slope, normalized, strict=True))
    return min(max(result, 0.0), values[0])


def predict(curve: Curve, rows) -> list[float]:
    return [one(curve, values) for values in rows]
