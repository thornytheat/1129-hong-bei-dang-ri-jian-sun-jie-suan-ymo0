import pytest

from bakerylot.markdown_bands.service import inspect, Validation, validate, share_from_logit, proposal, summarize
from bakerylot.markdown_bands.contracts import StockForecast, RecordError


@pytest.fixture
def document():
    return {'lot': 'LOT', 'available': 0, 'forecast': 0.0, 'distance': 0.0, 'shelf_remaining': 0, 'price_cents': 1}


def test_contract_round_trip(document):
    entry = StockForecast.parse(document)
    assert entry.evidence() == document
    assert StockForecast.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['lot'] = "　ＡＢＣ-１２　"
    entry = StockForecast.parse(document)
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
        StockForecast.parse(document)


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


def test_extreme_logits_do_not_overflow():
    # TRAP-31
    assert share_from_logit(-1000) == 0.0
    assert share_from_logit(0) == 0.5
    assert share_from_logit(1000) == 1.0


def test_no_validation_history_has_explicit_state(document):
    # TRAP-43
    stock = StockForecast.parse(document)
    no_validation = validate([])
    assert summarize(no_validation)["under_prediction_rate"] is None
    assert proposal(stock, no_validation)["decision"] == "验证为空"


def test_distribution_shift_holds_high_forecast(document):
    # TRAP-44
    stock = StockForecast.parse({**document, "available": 30, "forecast": 25, "distance": 9.2})
    assert proposal(stock, validate([(3, 3), (4, 3)]))["decision"] == "超出历史工况"


def test_conformal_radius_is_held_out_order_statistic():
    result = validate([(10, 8), (0, 0), (5, 1), (9, 8)], coverage=0.6)
    assert result.deviations == (0, 1, 2, 4)
    assert result.radius == 2
    assert summarize(result)["under_prediction_rate"] == 0.75
