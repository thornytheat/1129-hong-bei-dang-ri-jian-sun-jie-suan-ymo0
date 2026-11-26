import pytest

from bakerylot.bake_lots.service import inspect, close_candidates, lot_clock, carryable
from bakerylot.bake_lots.contracts import OvenTicket, RecordError


@pytest.fixture
def document():
    return {'lot': 'LOT', 'revision': 1, 'day': 1, 'station': 'STATION', 'sku': 'SKU', 'baked': 1, 'arrival_min': 0, 'shelf_minutes': 1, 'display_min': 0, 'price_cents': 1}


def test_contract_round_trip(document):
    entry = OvenTicket.parse(document)
    assert entry.evidence() == document
    assert OvenTicket.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['lot'] = "　ＡＢＣ-１２　"
    entry = OvenTicket.parse(document)
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
    document['revision'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        OvenTicket.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'revision': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['revision'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'revision'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_newer_revision_wins_independent_of_order(document):
    # TRAP-26
    document.update(arrival_min=5, display_min=5, shelf_minutes=20)
    first = OvenTicket.parse(document)
    newer = replace(first, revision=2, baked=40)
    assert close_candidates([newer, first], day=1, minute=10) == ([newer], [])
    assert close_candidates([first, newer], day=1, minute=10) == ([newer], [])


def test_identical_duplicate_is_safe_but_conflicting_revision_isolated(document):
    first = OvenTicket.parse(document)
    mismatch = replace(first, baked=200)
    accepted, rejected = close_candidates([first, mismatch], day=1, minute=0)
    assert not accepted and rejected == [{"lot": first.lot, "reason": "REVISION_CONFLICT"}]
    assert close_candidates([first, first], day=1, minute=0) == ([first], [])


def test_shelf_expiry_is_exclusive(document):
    # TRAP-23
    ticket = OvenTicket.parse(document)
    assert carryable(ticket, 0)
    assert not carryable(ticket, 1)
    assert lot_clock(ticket, 1)["minutes_left"] == 0
    assert close_candidates([ticket], day=1, minute=1)[1][0]["reason"] == "OUTSIDE_SHELF_WINDOW"
