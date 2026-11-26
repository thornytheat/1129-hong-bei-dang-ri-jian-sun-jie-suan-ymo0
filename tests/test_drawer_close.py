import pytest

from bakerylot.drawer_close.service import inspect, batch_close, receipt_totals, revision_key
from bakerylot.drawer_close.contracts import SaleSlip, RecordError


@pytest.fixture
def document():
    return {'slip': 'SLIP', 'lot': 'LOT', 'station': 'STATION', 'units': 1, 'list_cents': 1, 'charged_cents': 0, 'voucher_cents': 0}


def test_contract_round_trip(document):
    entry = SaleSlip.parse(document)
    assert entry.evidence() == document
    assert SaleSlip.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['slip'] = "　ＡＢＣ-１２　"
    entry = SaleSlip.parse(document)
    assert getattr(entry, 'slip') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['slip']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'slip'


def test_boolean_is_not_magnitude(document):
    document['units'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        SaleSlip.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'units': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['units'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'units'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_vouchers_are_separate_from_markdown(document):
    slip = SaleSlip.parse({**document, "units": 2, "list_cents": 1000, "charged_cents": 1800, "voucher_cents": 200})
    result = batch_close([slip], [], {slip.slip: 200})
    assert result[0]["untendered"] == 0
    assert receipt_totals(result)["net_cents"] == 1800


def test_discount_authorization_cannot_be_reused(document):
    slip = SaleSlip.parse({**document, "units": 2, "list_cents": 1000, "charged_cents": 1600})
    plan = [{"lot": slip.lot, "station": slip.station, "units": 2, "discount_cents": 200}]
    result = batch_close([slip, replace(slip, slip="Z99")], plan, {})
    assert [line["state"] for line in result] == ["对账通过", "超出折价授权"]
    assert receipt_totals(result)["unsettled_cents"] == 1600


def test_cache_dependencies_are_in_fingerprint():
    # TRAP-54
    key = revision_key(policies={"sku_limit": 5}, inputs="H1", evidence=[])
    assert key != revision_key(policies={"sku_limit": 6}, inputs="H1", evidence=[])
    assert key != revision_key(policies={"sku_limit": 5}, inputs="H2", evidence=[])
    assert key == revision_key(inputs="H1", evidence=[], policies={"sku_limit": 5})
