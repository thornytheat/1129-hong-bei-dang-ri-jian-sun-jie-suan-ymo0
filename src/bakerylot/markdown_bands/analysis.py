from dataclasses import dataclass
from math import ceil, exp, fsum, isfinite
from .contracts import StockForecast


@dataclass(frozen=True, slots=True)
class Validation:
    deviations: tuple[float, ...]
    radius: float
    positives: int
    observed: int


def validate(pairs, *, coverage: float = 0.85) -> Validation:
    if not 0 < coverage < 1:
        raise ValueError("INTERVAL_LEVEL_INVALID")
    deviations = []
    hits = 0
    for actual, estimate in pairs:
        if not isfinite(actual) or not isfinite(estimate):
            continue
        deviations.append(abs(actual - estimate))
        hits += actual > estimate
    ordered = sorted(deviations)
    if not ordered:
        return Validation((), 0.0, 0, 0)
    index = min(len(ordered), ceil((len(ordered) + 1) * coverage)) - 1
    return Validation(tuple(ordered), ordered[index], hits, len(ordered))


def share_from_logit(logit: float) -> float:
    if logit >= 0:
        return 1.0 / (1.0 + exp(-logit))
    proportion = exp(logit)
    return proportion / (1.0 + proportion)


def proposal(stock: StockForecast, validation: Validation) -> dict:
    upper = min(stock.available, ceil(stock.forecast + validation.radius))
    lower = max(0, int(stock.forecast - validation.radius))
    at_risk = max(0, stock.available - upper)
    urgency = share_from_logit((70 - stock.shelf_remaining) / 18)
    if not validation.observed:
        state = "验证为空"
    elif stock.distance > 5.0:
        state = "超出历史工况"
    elif stock.shelf_remaining <= 15:
        state = "即将下架"
    elif not at_risk:
        state = "维持原价"
    else:
        state = "可申请折价"
    return {"lot": stock.lot, "median": round(stock.forecast, 2), "sale_low": lower,
            "sale_high": upper, "at_risk": at_risk, "priority": round(urgency * at_risk, 4),
            "price_cents": stock.price_cents, "decision": state,
            "distance": round(stock.distance, 3)}


def summarize(validation: Validation) -> dict:
    return {"n": validation.observed, "radius": validation.radius,
            "mean_error": fsum(validation.deviations) / validation.observed if validation.observed else None,
            "under_prediction_rate": validation.positives / validation.observed if validation.observed else None}
