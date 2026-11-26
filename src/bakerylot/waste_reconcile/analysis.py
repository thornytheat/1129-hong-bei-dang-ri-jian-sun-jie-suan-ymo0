from collections import defaultdict
from .contracts import StockMovement

KINDS = frozenset(("sale", "donation", "damage", "markdown_sale"))


def snapshot(movements: tuple[StockMovement, ...], *, day: int, minute: int):
    by_id = defaultdict(set)
    for movement in movements:
        if (movement.day, movement.posted_min) <= (day, minute):
            by_id[movement.movement].add(movement)
    totals = defaultdict(lambda: {kind: 0 for kind in sorted(KINDS)})
    excluded = []
    for identifier, candidates in sorted(by_id.items()):
        if len(candidates) != 1:
            excluded.append({"movement": identifier, "reason": "MOVEMENT_CONFLICT"})
            continue
        item = candidates.pop()
        if item.kind not in KINDS:
            excluded.append({"movement": identifier, "reason": "UNKNOWN_MOVEMENT"})
            continue
        if item.kind != "markdown_sale" and item.discount_cents:
            excluded.append({"movement": identifier, "reason": "UNEXPECTED_DISCOUNT"})
            continue
        totals[item.lot][item.kind] += item.units
    return dict(totals), excluded


def sellable(lot: str, baked: int, outflow: dict[str, int]) -> dict:
    sold = outflow.get("sale", 0) + outflow.get("markdown_sale", 0)
    disposed = outflow.get("damage", 0) + outflow.get("donation", 0)
    difference = baked - sold - disposed
    if difference < 0:
        reason = "OUTFLOW_EXCEEDS_OVEN_COUNT"
    elif difference == 0:
        reason = "SOLD_OUT_OR_WRITTEN_OFF"
    else:
        reason = "BALANCED"
    return {
        "lot": lot,
        "oven": baked,
        "sold": sold,
        "disposed": disposed,
        "sellable": max(difference, 0),
        "variance": min(difference, 0),
        "reason": reason,
    }


def evidence_totals(stock: list[dict]) -> dict:
    keys = ("oven", "sold", "disposed", "sellable", "variance")
    result = {key: sum(item[key] for item in stock) for key in keys}
    if result["oven"] != sum(result[key] for key in keys[1:]):
        raise ValueError("INVENTORY_IDENTITY_FAILED")
    return result
