from dataclasses import replace

import pytest

from bakerylot.drawer_close.cashbook import coupon_amounts, evidence_totals, receipt_counters, rollup
from bakerylot.drawer_close.service import SaleSlip, batch_close
from bakerylot.shelf_action.service import allocate_voucher


def slip(identifier, *, station="窗台", charged=400, units=1, voucher=0):
    return SaleSlip.parse(dict(slip=identifier, lot="BAT-1", station=station, units=units,
                               list_cents=400, charged_cents=charged, voucher_cents=voucher))


def test_book_identifies_two_eligible_stations_and_held_deposit():
    a = slip("A")
    b = slip("B", station="南厅", charged=300)
    c = slip("C", station="南厅", charged=300, voucher=100)
    slips = [a,b,c]
    closures = batch_close(slips, [], {"C": 100})
    entries = rollup(slips,closures)
    totals = evidence_totals(entries)
    assert totals["日结已入账分"] == 700
    assert totals["争议暂挂分"] == 300
    assert totals["登记实收分"] == 1000
    assert totals["渠道抵扣分"] == 100
    assert totals["暂挂收据数"] == 1
    south = next(line for line in entries if line.counter=="南厅")
    assert south.evidence()["暂挂（分）"] == 300
    assert south.evidence()["入账抵扣（分）"] == 100


def test_bill_from_conflicting_counters_is_held_at_unresolved_station():
    original = slip("A")
    other = replace(original, station="北区")
    receipts = [original,other]
    assert receipt_counters(receipts) == {"A":"待定柜台"}
    row, = rollup(receipts,batch_close(receipts,[],{}))
    assert row.counter == "待定柜台"
    assert row.takings == 0 and row.duplicates == 1


def test_rollup_refuses_duplicate_missing_and_unknown_evidence():
    receipts = [slip("F-1"), slip("F-2")]
    first, second = batch_close(receipts, [], {})
    with pytest.raises(ValueError, match="REPEATED"):
        rollup(receipts, [first, first, second])
    with pytest.raises(ValueError, match="MISSING"):
        rollup(receipts, [first])
    with pytest.raises(ValueError, match="UNKNOWN"):
        rollup(receipts, [first, {**first, "slip":"F-404"}])


def test_receipt_voucher_share_is_weighted_by_undiscounted_value():
    slips = [slip("A"),slip("B",units=2),slip("C",units=2)]
    shares, issues = coupon_amounts([{"campaign":"V","receipts":["A","B","C"],"cents":183}], slips, allocate_voucher)
    assert not issues
    assert shares == {"A":37,"B":73,"C":73}
    assert sum(shares.values()) == 183


def test_conflicting_voucher_isolated_with_its_original_campaign():
    source = slip("A")
    other = replace(source, station="北区")
    vouchers = [{"campaign":"VR-1", "receipts":["A"], "cents":100},
                {"campaign":"VR-2", "receipts":["B","B"], "cents":100},
                {"campaign":"VR-3", "receipts":["B"], "cents":450},
                {"campaign":"VR-4", "receipts":["B"], "cents":31}]
    shares, issues = coupon_amounts(vouchers,[source,other,slip("B")],allocate_voucher)
    assert shares == {"B":31}
    assert [x["优惠活动"] for x in issues] == ["VR-1","VR-2","VR-3"]
    assert [x["异常"] for x in issues] == ["抵扣关联收据缺失或冲突","重复抵扣收据","抵扣金额超过标价"]
