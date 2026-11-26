import pytest

from bakerylot.shelf_action.service import inspect, per_unit_discount, authorize, allocate_voucher
from bakerylot.shelf_action.contracts import MarkdownRequest, RecordError


@pytest.fixture
def document():
    return {'lot': 'LOT', 'decision': 'DECISION', 'sku': 'SKU', 'station': 'STATION', 'available': 0, 'at_risk': 0, 'priority': 0.0, 'price_cents': 1, 'markdown_pct': 1}


def test_contract_round_trip(document):
    entry = MarkdownRequest.parse(document)
    assert entry.evidence() == document
    assert MarkdownRequest.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['lot'] = "　ＡＢＣ-１２　"
    entry = MarkdownRequest.parse(document)
    assert getattr(entry, 'lot') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['lot']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'lot'


def test_boolean_is_not_magnitude(document):
    document['available'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        MarkdownRequest.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'available': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['available'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'available'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_budget_and_sku_limits_can_both_bind(document):
    req = MarkdownRequest.parse({**document, "decision": "可申请折价", "available": 30,
                                 "at_risk": 15, "price_cents": 1000, "markdown_pct": 20})
    later = replace(req, lot="Z", priority=1.0)
    result, used = authorize([req, later], 2100, 8)
    assert sum(row["units"] for row in result) == 8
    assert used == 1600
    assert result[0]["lot"] == "Z"
    assert result[1]["reason"] == "柜台同品限量"


def test_duplicate_request_has_no_reservation(document):
    req = MarkdownRequest.parse({**document, "decision": "可申请折价", "available": 30, "at_risk": 15})
    result, used = authorize([req, req], 500)
    assert used == 0
    assert all(line["reason"] == "批次重复待核对" for line in result)


def test_largest_remainder_conserves_voucher_cents():
    # TRAP-24
    weights = {"roll-a": 1, "roll-b": 1, "roll-c": 1}
    assert allocate_voucher(10, weights) == {"roll-a": 4, "roll-b": 3, "roll-c": 3}
    assert allocate_voucher(10, dict(reversed(tuple(weights.items())))) == allocate_voucher(10, weights)
    assert sum(allocate_voucher(13, {"a": 12, "b": 2, "c": 3}).values()) == 13


def test_sub_cent_discount_uses_commercial_rounding():
    assert per_unit_discount(1305, 10) == 131
    assert per_unit_discount(1, 1) == 1
