import pytest

from bakerylot.leftover_curve.service import inspect, Curve, points, center_scale, chronological_sample, fit, one, predict
from bakerylot.leftover_curve.contracts import DailyFinish, RecordError


@pytest.fixture
def document():
    return {'historical_lot': 'HISTORICAL_LOT', 'day': 1, 'station': 'STATION', 'sku': 'SKU', 'remaining': 0, 'minutes': 0, 'late_sales': 0, 'daypart': 0, 'rain_mm': 0.0, 'censored': 0, 'observed_day': 1}


def test_contract_round_trip(document):
    entry = DailyFinish.parse(document)
    assert entry.evidence() == document
    assert DailyFinish.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['historical_lot'] = "　ＡＢＣ-１２　"
    entry = DailyFinish.parse(document)
    assert getattr(entry, 'historical_lot') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['historical_lot']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'historical_lot'


def test_boolean_is_not_magnitude(document):
    document['day'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        DailyFinish.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'day': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['day'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'day'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def training_rows(document):
    for day in range(1, 19):
        yield DailyFinish.parse({**document, "historical_lot": f"HB-{day:02}", "day": day,
                                 "observed_day": day, "remaining": day + 2,
                                 "late_sales": day // 2, "minutes": 10 + day})


def test_late_posted_history_does_not_change_training(document):
    # TRAP-42
    records = list(training_rows(document))
    before = fit(records, 16)
    late = replace(records[6], historical_lot="LATE", observed_day=20, late_sales=9)
    censored = replace(records[8], historical_lot="CENSORED", censored=1, late_sales=10)
    assert fit(records + [late, censored], 16) == before
    assert before.count == 15


def test_welford_equivalent_variance_stays_scaled():
    # TRAP-32
    a = [1e12 + 0.25, 1e12 + 0.5, 1e12 + 0.75]
    assert center_scale(a)[1] == pytest.approx((1 / 24) ** 0.5)
    assert center_scale([1e8] * 8) == (1e8, 1.0)


def test_mixed_batches_do_not_shift_predictions(document):
    # TRAP-53
    trained = fit(list(training_rows(document)), 17)
    low = (6.0, 13.0, 3.0, 0.0)
    high = (500.0, 150.0, 0.0, 34.0)
    assert predict(trained, [low, high])[0] == predict(trained, [low])[0]
    assert predict(trained, [high, low])[1] == one(trained, low)


def test_model_improves_on_constant_baseline(document):
    trained = fit(list(training_rows(document)), 15)
    low, high = (5.0, 13.0, 0.0, 0.0), (15.0, 23.0, 0.0, 0.0)
    assert abs(one(trained, low) - 1) < abs(trained.intercept - 1)
    assert one(trained, low) < one(trained, high)
