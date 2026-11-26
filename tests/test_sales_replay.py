from dataclasses import replace
from math import isclose

import pytest

from bakerylot.leftover_curve import service as demand
from bakerylot.leftover_curve.replay import Trial, masked_station
from bakerylot.pipeline import run


def receipts():
    data = []
    for slot in range(1, 20):
        for station, name in (("北柜", "青麦"), ("南柜", "碱水")):
            row = demand.DailyFinish.parse({
                "historical_lot": f"{station}-{slot}",
                "day": slot,
                "station": station,
                "sku": name,
                "remaining": slot+2,
                "minutes": 20+slot,
                "late_sales": slot//2,
                "daypart": slot % 7,
                "rain_mm": 0,
                "censored": 0,
                "observed_day": slot,
            })
            data.append(row)
    return data


def test_temporal_trial_recovers_late_volume_and_keeps_cabinet_filter():
    samples = receipts()
    kept = {("北柜", "青麦")}
    outcome, denied = demand.recent_replay(samples, 20, kept, 6)
    assert not denied
    assert [line.day for line in outcome] == list(range(14,20))
    assert all(line.sku == "青麦" and line.total == 1 for line in outcome)
    stat, = demand.replay_summary(outcome)
    assert stat["模型平均绝对误差"] < stat["历史中位绝对误差"]
    assert stat["回放日"] == 6
    assert stat["回放炉次"] == 6
    assert stat["误差改善率"] > 0.5


def test_retroactive_edit_can_only_affect_trial_after_publication():
    raw = receipts()
    admitted = {("北柜", "青麦")}
    historic = next(row for row in raw if row.historical_lot == "北柜-4")
    late = replace(historic, historical_lot="补录", observed_day=17, late_sales=6)
    baseline,_ = demand.recent_replay(raw,20,admitted,6)
    mutated,_ = demand.recent_replay(raw+[late],20,admitted,6)
    assert baseline[:4] == mutated[:4]
    assert baseline[4:] != mutated[4:]


def test_unknown_observations_and_sold_out_aggregates_stay_distinct():
    cases = [Trial("芝麻",10,2,0,1,1,0),Trial("芝麻",11,3,0,2,2,1)]
    view, = demand.replay_summary(cases)
    assert view["模型平均绝对误差"] == 0.6
    assert view["历史中位绝对误差"] == 0.0
    assert view["误差改善率"] is None
    assert view["原价售罄"] == 1
    evidence = cases[1].evidence()
    assert evidence["原价售罄"] == 1
    assert evidence["预估不足炉次"] == 2


def test_holdout_leaves_no_station_rows_in_training():
    before, after = masked_station(receipts(), "北柜", 18)
    assert len(before) == len(after) == 17
    assert {row.station for row in before} == {"南柜"}
    assert {row.station for row in after} == {"北柜"}
    accepted = demand.replay_held_stations(receipts(),20)
    assert {row["柜台"] for row in accepted} == {"南柜","北柜"}
    assert all(row["状态"]=="已验证" for row in accepted)
    assert isclose(accepted[0]["模型误差"], accepted[1]["模型误差"])


def test_short_history_has_explicit_cold_start_status():
    result = demand.replay_held_stations(receipts(),4,min_training=10)
    assert len(result)==2
    assert result[0]["验证量"]==3
    assert result[0]["模型误差"] is None
    trials, denied=demand.recent_replay(receipts(),4,{("南柜","碱水")},2)
    assert len(denied) == len(trials) == 1
    assert trials[0].day == 3
    assert {item["结果"] for item in denied}=={"训练样本不足"}


@pytest.mark.parametrize("budget", [1,26,69,100])
def test_live_workbench_budget_and_receipt_proofs_reconcile(budget):
    report=run(budget)
    summary=report["ranking_scenario"]
    official=sum(row["reserved"] for row in report["rows"])
    assert summary["budget_cents"] == budget*100
    assert summary["reservations"][-1]["累计分"] == official <= budget*100
    assert report["metrics"]["预留折扣（元）"] == official/100
    assert sum(record["登记实收（分）"] for record in report["stages"][-1]["records"] if "柜台" in record) >= report["metrics"]["通过收据实收（元）"]*100
    assert report["model_replay"]
    assert all(0<=item["原价售罄"]<=item["留出炉次数"] for item in report["model_replay"])



def test_dates_after_cutoff_do_not_add_trials():
    stream = receipts()
    late = replace(stream[-1], historical_lot="次日登记", day=25, observed_day=25)
    selection = {("北柜", "青麦"),("南柜", "碱水")}
    original = demand.recent_replay(stream, 20, selection, 5)
    injected = demand.recent_replay(stream + [late], 20, selection, 5)
    assert original == injected
    assert {trial.day for trial in injected[0]} == set(range(15, 20))


def test_censored_sales_never_create_a_perfect_baseline():
    sample = receipts()
    original = sample[-1]
    corrected = replace(original, historical_lot="停电停售", censored=1, late_sales=0)
    first = demand.recent_replay(sample, 20, {("南柜", "碱水")}, 5)
    second = demand.recent_replay(sample+[corrected], 20, {("南柜", "碱水")}, 5)
    assert first == second
    assert len(first[0]) == 5
