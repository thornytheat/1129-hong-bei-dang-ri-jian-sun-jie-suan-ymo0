from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DepositLine:
    counter: str
    takings: int
    confirmed: int
    review: int
    vouchers: int
    markdowns: int
    duplicates: int

    def evidence(self):
        return {
            "柜台": self.counter,
            "登记实收（分）": self.takings,
            "可入账（分）": self.confirmed,
            "暂挂（分）": self.review,
            "入账抵扣（分）": self.vouchers,
            "入账折价（分）": self.markdowns,
            "暂挂笔数": self.duplicates,
        }


def receipt_counters(receipts):
    index = defaultdict(set)
    for slip in receipts:
        index[slip.slip].add(slip.station)
    return {identifier: next(iter(counters)) if len(counters) == 1 else "待定柜台"
            for identifier, counters in index.items()}


def rollup(claims, closures):
    counters = receipt_counters(claims)
    by_counter = defaultdict(list)
    recorded = set()
    for entry in closures:
        receipt = entry["slip"]
        if receipt in recorded:
            raise ValueError("RECEIPT_EVIDENCE_REPEATED")
        if receipt not in counters:
            raise ValueError("RECEIPT_EVIDENCE_UNKNOWN")
        recorded.add(receipt)
        by_counter[counters[receipt]].append(entry)
    if recorded != counters.keys():
        raise ValueError("RECEIPT_EVIDENCE_MISSING")
    result = []
    for station, rows in sorted(by_counter.items()):
        accepted = [row for row in rows if row["state"] == "对账通过"]
        held = [row for row in rows if row["state"] != "对账通过"]
        balance = DepositLine(
            station,
            takings=sum(row["net_cents"] for row in rows),
            confirmed=sum(row["net_cents"] for row in accepted),
            review=sum(row["net_cents"] for row in held),
            vouchers=sum(row.get("voucher_cents", 0) for row in accepted),
            markdowns=sum(row.get("untendered", 0) for row in accepted),
            duplicates=len(held),
        )
        if balance.takings != balance.confirmed + balance.review:
            raise RuntimeError("DEPOSIT_INVARIANT")
        result.append(balance)
    return result


def coupon_amounts(campaigns, receipts, split):
    aliases = defaultdict(set)
    for line in receipts:
        aliases[line.slip].add(line)
    output = defaultdict(int)
    issues = []
    vouchers = set()
    for ticket in campaigns:
        campaign_id = ticket["campaign"]
        if campaign_id in vouchers:
            raise ValueError("CAMPAIGN_DUPLICATED")
        vouchers.add(campaign_id)
        line_ids = ticket["receipts"]
        if len(line_ids) != len(set(line_ids)):
            issues.append({"优惠活动": campaign_id, "异常": "重复抵扣收据"})
            continue
        if any(len(aliases[ref]) != 1 for ref in line_ids):
            issues.append({"优惠活动": campaign_id, "异常": "抵扣关联收据缺失或冲突"})
            continue
        exact = [next(iter(aliases[ref])) for ref in line_ids]
        weights = {line.slip: line.units * line.list_cents for line in exact}
        amount = ticket["cents"]
        if not weights or not 0 <= amount <= sum(weights.values()):
            issues.append({"优惠活动": campaign_id, "异常": "抵扣金额超过标价"})
            continue
        shares = split(amount, weights)
        for identifier, part in shares.items():
            output[identifier] += part
    return dict(output), issues


def evidence_totals(deposits):
    return {
        "登记实收分": sum(line.takings for line in deposits),
        "日结已入账分": sum(line.confirmed for line in deposits),
        "争议暂挂分": sum(line.review for line in deposits),
        "渠道抵扣分": sum(line.vouchers for line in deposits),
        "策略预留实用分": sum(line.markdowns for line in deposits),
        "暂挂收据数": sum(line.duplicates for line in deposits),
    }
