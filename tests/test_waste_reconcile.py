import pytest

from bakerylot.waste_reconcile.service import inspect, snapshot, sellable, evidence_totals
from bakerylot.waste_reconcile.contracts import StockMovement, RecordError


@pytest.fixture
def document():
    return {'movement': 'MOVEMENT', 'lot': 'LOT', 'kind': 'KIND', 'units': 0, 'day': 1, 'posted_min': 0, 'discount_cents': 0}


def test_contract_round_trip(document):
    entry = StockMovement.parse(document)
    assert entry.evidence() == document
    assert StockMovement.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['movement'] = "　ＡＢＣ-１２　"
    entry = StockMovement.parse(document)
    assert getattr(entry, 'movement') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['movement']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'movement'


def test_boolean_is_not_magnitude(document):
    document['units'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        StockMovement.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'units': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['units'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'units'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_duplicate_movement_counts_once(document):
    document.update(kind="sale", units=5)
    move = StockMovement.parse(document)
    result, issues = snapshot([move, move], day=1, minute=9)
    assert not issues and result[move.lot]["sale"] == 5


def test_cutoff_omits_not_yet_posted_movement(document):
    document.update(kind="sale", units=6, posted_min=50)
    move = StockMovement.parse(document)
    assert snapshot([move], day=1, minute=49) == ({}, [])
    assert snapshot([move], day=1, minute=50)[0][move.lot]["sale"] == 6


def test_overdraw_preserves_inventory_variance():
    line = sellable("BT-18", 3, {"sale": 5, "damage": 2})
    assert line["variance"] == -4 and line["sellable"] == 0
    assert evidence_totals([line])["oven"] == 3


def test_conflicting_daily_move_keeps_no_units(document):
    document.update(kind="damage", units=1)
    move = StockMovement.parse(document)
    result, issues = snapshot([move, replace(move, units=2)], day=1, minute=9)
    assert not result and issues[0]["reason"] == "MOVEMENT_CONFLICT"
