from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from .contracts import MarkdownRequest


def per_unit_discount(price_cents: int, percent: int) -> int:
    return max(1, int((Decimal(price_cents) * Decimal(percent) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def authorize(requests: tuple[MarkdownRequest, ...], budget_cents: int, per_sku: int = 18):
    if min(budget_cents, per_sku) < 0:
        raise ValueError("NEGATIVE_ALLOWANCE")
    allocated = []
    duplicate = defaultdict(int)
    position = defaultdict(int)
    used = 0
    for line in requests:
        duplicate[line.lot] += 1
    for line in sorted(requests, key=lambda item: (-item.priority, item.station, item.lot)):
        count = 0
        amount = per_unit_discount(line.price_cents, line.markdown_pct)
        station_sku = (line.station, line.sku)
        if duplicate[line.lot] > 1:
            reason = "批次重复待核对"
        elif line.decision != "可申请折价":
            reason = line.decision
        elif line.at_risk <= 0:
            reason = "预期可原价售完"
        elif position[station_sku] == per_sku:
            reason = "柜台同品限量"
        else:
            count = min(line.available, line.at_risk, per_sku - position[station_sku], (budget_cents - used) // amount)
            reason = "已批准" if count else "折扣额度不足"
        position[station_sku] += count
        used += count * amount
        allocated.append({"lot": line.lot, "station": line.station, "sku": line.sku,
                          "available": line.available, "units": count, "at_risk": line.at_risk,
                          "discount_cents": amount, "reserved": count * amount, "reason": reason})
    return allocated, used


def allocate_voucher(amount: int, weights: dict[str, int]) -> dict[str, int]:
    if amount < 0 or any(value < 0 for value in weights.values()):
        raise ValueError("UNSUPPORTED_REVERSAL")
    weight_total = sum(weights.values())
    if weight_total == 0:
        if amount:
            raise ValueError("VOUCHER_WITHOUT_ITEMS")
        return dict.fromkeys(weights, 0)
    raw = {key: divmod(value * amount, weight_total) for key, value in weights.items()}
    remainder = amount - sum(value for value, _ in raw.values())
    recipients = sorted(raw, key=lambda key: (-raw[key][1], key))[:remainder]
    return {key: quotient + (key in recipients) for key, (quotient, _) in sorted(raw.items())}
