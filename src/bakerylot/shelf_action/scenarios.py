from collections import defaultdict
from dataclasses import dataclass
from itertools import accumulate
from math import isfinite

from .analysis import per_unit_discount
from .contracts import MarkdownRequest


@dataclass(frozen=True, slots=True)
class CounterChoice:
    units: int
    cost_cents: int
    benefit: int
    selections: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class Comparison:
    opportunity: int
    spent: int
    units: int
    selections: tuple[tuple[str, int], ...]
    alternatives: int

    def evidence(self):
        return {
            "模拟上限件数": self.units,
            "模拟必要分": self.spent,
            "加权减损": self.opportunity / 10000,
            "模拟入选炉次": len(self.selections),
            "有效组合数": self.alternatives,
        }


def choice_order(choice):
    return (-choice.benefit, -choice.units, choice.cost_cents, choice.selections)


def preferred(current, option):
    return option if current is None or choice_order(option) < choice_order(current) else current


def eligible_lots(proposals):
    multiplicities = defaultdict(int)
    for lot in proposals:
        multiplicities[lot.lot] += 1
    return sorted(
        (lot for lot in proposals
         if multiplicities[lot.lot] == 1 and lot.decision == "可申请折价"
         and lot.at_risk > 0 and lot.available > 0 and isfinite(lot.priority)),
        key=lambda item: (item.station, item.sku, item.lot),
    )


def options_for_lot(lot: MarkdownRequest, cap: int):
    unit_value = max(1, round(10_000 * lot.priority / lot.at_risk))
    unit_cost = per_unit_discount(lot.price_cents, lot.markdown_pct)
    count = min(cap, lot.available, lot.at_risk)
    return (
        CounterChoice(n, n * unit_cost, n * unit_value, ((lot.lot, n),) if n else ())
        for n in range(count + 1)
    )


def add_choices(a, b):
    return CounterChoice(
        a.units + b.units,
        a.cost_cents + b.cost_cents,
        a.benefit + b.benefit,
        tuple(sorted((*a.selections, *b.selections))),
    )


def prune_counter(states):
    kept = {}
    best_by_units = defaultdict(lambda: -1)
    for key, option in sorted(states.items(), key=lambda item: (item[1].cost_cents, item[1].units)):
        if option.benefit > best_by_units[option.units]:
            best_by_units[option.units] = option.benefit
            kept[key] = option
    return kept


def counter_frontier(lots, per_counter_sku, budget):
    empty = CounterChoice(0, 0, 0, ())
    states = {(0, 0): empty}
    for source in lots:
        options = tuple(options_for_lot(source, per_counter_sku))
        next_states = {}
        for previous in states.values():
            for proposal in options:
                if previous.units + proposal.units > per_counter_sku:
                    break
                if previous.cost_cents + proposal.cost_cents > budget:
                    break
                combined = add_choices(previous, proposal)
                key = (combined.units, combined.cost_cents)
                next_states[key] = preferred(next_states.get(key), combined)
        states = prune_counter(next_states)
    return prune_store(states.values())


def prune_store(options):
    best = None
    result = []
    for option in sorted(options, key=lambda choice: (choice.cost_cents, *choice_order(choice))):
        if best is None or (option.benefit, option.units) > (best.benefit, best.units):
            best = option
            result.append(option)
    return result


def estimate_combinations(proposals, budget, counter_limit):
    if budget < 0 or counter_limit < 0:
        raise ValueError("NEGATIVE_SIMULATION_LIMIT")
    by_group = defaultdict(list)
    for candidate in eligible_lots(proposals):
        by_group[candidate.station, candidate.sku].append(candidate)
    combinations = [CounterChoice(0, 0, 0, ())]
    for _, lots in sorted(by_group.items()):
        options = counter_frontier(lots, counter_limit, budget)
        by_cost = {}
        for previous in combinations:
            unspent = budget - previous.cost_cents
            for proposal in options:
                if proposal.cost_cents > unspent:
                    break
                combined = add_choices(previous, proposal)
                by_cost[combined.cost_cents] = preferred(by_cost.get(combined.cost_cents), combined)
        combinations = prune_store(by_cost.values())
    best = min(combinations, key=choice_order)
    return Comparison(best.benefit, best.cost_cents, best.units, best.selections, len(combinations))


def discount_breakdown(proposals, official, optimum):
    official_by_lot = {row["lot"]: row for row in official}
    proposed_by_lot = dict(optimum.selections)
    net = []
    for source in eligible_lots(proposals):
        active = official_by_lot.get(source.lot, {})
        approved = active.get("units", 0)
        simulated = proposed_by_lot.get(source.lot, 0)
        if approved == simulated:
            continue
        price_gap = (simulated - approved) * per_unit_discount(source.price_cents, source.markdown_pct)
        net.append({
            "炉次": source.lot,
            "柜台": source.station,
            "原审批": approved,
            "模拟件数": simulated,
            "折扣差（分）": price_gap,
        })
    return net


def stock_movements(rows):
    counts = defaultdict(lambda: {"可售": 0, "批准件": 0, "预留分": 0})
    for row in rows:
        counter = counts[row["station"]]
        counter["可售"] += row["available"]
        counter["批准件"] += row["units"]
        counter["预留分"] += row["reserved"]
    return [{"柜台": station, **totals} for station, totals in sorted(counts.items())]


def burn_curve(reservations):
    ordered = sorted(reservations, key=lambda line: (-line["reserved"], line["lot"]))
    cumulative = accumulate(item["reserved"] for item in ordered)
    return [
        {"炉次": item["lot"], "预留分": item["reserved"], "累计分": total}
        for item, total in zip(ordered, cumulative, strict=True)
    ]
