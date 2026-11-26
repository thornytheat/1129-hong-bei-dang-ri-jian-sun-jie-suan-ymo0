from collections import defaultdict
from hashlib import sha256
from json import dumps
from .contracts import SaleSlip


def batch_close(slips: tuple[SaleSlip, ...], authorization: list[dict], vouchers: dict[str, int]):
    plans = {item["lot"]: item for item in authorization}
    duplicates = defaultdict(set)
    for line in slips:
        duplicates[line.slip].add(line)
    proceeds = []
    approved_units = defaultdict(int)
    for slip, conflicting in sorted(duplicates.items()):
        if len(conflicting) != 1:
            proceeds.append({"slip": slip, "state": "收据内容冲突", "lot": "—", "net_cents": 0})
            continue
        line = conflicting.pop()
        plain_total = line.units * line.list_cents
        discount = plain_total - line.charged_cents - line.voucher_cents
        plan = plans.get(line.lot)
        if discount < 0:
            state = "实收超出标价"
        elif vouchers.get(slip, 0) != line.voucher_cents:
            state = "优惠券分摊差异"
        elif discount and (plan is None or plan["station"] != line.station):
            state = "无本柜台折价授权"
        elif discount and (discount != plan["discount_cents"] * line.units
                           or approved_units[line.lot] + line.units > plan["units"]):
            state = "超出折价授权"
        else:
            state = "对账通过"
            if discount:
                approved_units[line.lot] += line.units
        proceeds.append({"slip": slip, "lot": line.lot, "state": state, "net_cents": line.charged_cents,
                         "units": line.units, "untendered": discount, "voucher_cents": line.voucher_cents})
    return proceeds


def receipt_totals(closed: list[dict]) -> dict:
    settled = [row for row in closed if row["state"] == "对账通过"]
    approval = sum(row["net_cents"] for row in settled)
    exceptions = sum(row["net_cents"] for row in closed if row["state"] != "对账通过")
    return {"approved": len(settled), "exceptions": len(closed) - len(settled),
            "net_cents": approval, "unsettled_cents": exceptions}


def revision_key(*, policies, inputs, evidence) -> str:
    document = {"schema": 1, "policies": policies, "input_hash": inputs, "evidence": evidence}
    return sha256(dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
