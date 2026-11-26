from dataclasses import replace
from itertools import product

import pytest

from bakerylot.shelf_action.contracts import MarkdownRequest
from bakerylot.shelf_action.scenarios import (
    burn_curve,
    discount_breakdown,
    eligible_lots,
    estimate_combinations,
    options_for_lot,
    stock_movements,
)
from bakerylot.shelf_action.service import authorize, per_unit_discount


def order(lot, *, station="南柜", sku="豆沙包", available=8, at_risk=8, price=100, priority=4):
    return MarkdownRequest.parse(dict(
        lot=lot, station=station, sku=sku, available=available, at_risk=at_risk,
        priority=priority, price_cents=price, markdown_pct=20, decision="可申请折价",
    ))


def brute_force_choices(choices, budget, limit):
    by_lot = {line.lot: line for line in choices}
    frames = [list(options_for_lot(line, limit)) for line in choices]
    best = (0, 0, 0)
    for combo in product(*frames):
        spent = sum(option.cost_cents for option in combo)
        if spent > budget:
            continue
        use = {}
        for choice in combo:
            if not choice.selections:
                continue
            lot, count = choice.selections[0]
            row = by_lot[lot]
            key = (row.station, row.sku)
            use[key] = use.get(key, 0) + count
        if any(x > limit for x in use.values()):
            continue
        summary = (sum(o.benefit for o in combo), sum(o.units for o in combo), -spent)
        best = max(best, summary)
    return best


@pytest.mark.parametrize("budget, limit", [(0, 5), (29, 2), (65, 4), (100, 3), (400, 1), (400, 7)])
def test_dynamic_program_matches_complete_reference_search(budget, limit):
    choices = [order("BF-L", price=161, priority=6), order("BF-A", price=91, priority=2),
               order("BF-B", price=102, priority=4, sku="红糖包"), order("BF-S", station="南区", price=90, priority=5)]
    result = estimate_combinations(choices, budget, limit)
    assert (result.opportunity, result.units, -result.spent) == brute_force_choices(choices, budget, limit)
    assert result == estimate_combinations(list(reversed(choices)), budget, limit)
    assert sum(value for _, value in result.selections) == result.units


def test_invalid_duplicate_shares_are_excluded_before_optimization():
    line = order("FB-1")
    revised = replace(line, price_cents=250)
    trusted = order("FB-2", priority=8, price=99)
    assert eligible_lots([line, revised, trusted]) == [trusted]
    result = estimate_combinations([line, revised, trusted], budget=100, counter_limit=6)
    assert set(dict(result.selections)) == {trusted.lot}
    assert result.units == 5
    assert result.spent == 100


def test_price_efficiency_changes_solver_choices():
    high_total = order("HB-A", price=400, priority=7)
    low_cost = order("HB-B", sku="黑麦圈", price=100, priority=6)
    candidates = [high_total, low_cost]
    greedy, _ = authorize(candidates, 80, 8)
    best = estimate_combinations(candidates, 80, 8)
    assert best.selections == (("HB-B", 4),)
    changes = discount_breakdown(candidates, greedy, best)
    assert sum(row["折扣差（分）"] for row in changes) == 0
    assert {line["炉次"] for line in changes} == {"HB-A", "HB-B"}


def test_unused_proposals_have_no_simulated_reservations():
    held=replace(order("FREEZE"), decision="即将下架")
    exhausted=order("EMPTY", available=0)
    empty=estimate_combinations([held,exhausted], 200, 8)
    assert empty.evidence() == {"模拟上限件数":0,"模拟必要分":0,"加权减损":0,"模拟入选炉次":0,"有效组合数":1}
    assert discount_breakdown([held,exhausted], [], empty) == []


def test_counter_totals_and_reservation_curve_match_allocations():
    options = [order("K-1", station="南柜", price=106), order("K-2", station="南柜", price=154),
               order("K-3", station="北柜", price=190)]
    allocations, spent = authorize(options, 850, 7)
    step_totals = burn_curve(allocations)
    assert step_totals[-1]["累计分"] == spent
    assert sum(row["预留分"] for row in stock_movements(allocations)) == spent
    assert sum(row["批准件"] for row in stock_movements(allocations)) == sum(row["units"] for row in allocations)
    assert len(step_totals) == 3
