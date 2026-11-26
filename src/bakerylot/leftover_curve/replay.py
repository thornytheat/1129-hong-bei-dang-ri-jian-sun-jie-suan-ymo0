from collections import defaultdict
from dataclasses import dataclass
from math import fsum
from statistics import median

from .analysis import chronological_sample, fit, one, points


@dataclass(frozen=True, slots=True)
class Trial:
    sku: str
    day: int
    total: int
    baseline_error: float
    model_error: float
    missed_stock: int
    soldout: int

    def evidence(self):
        return {
            "商品": self.sku,
            "业务日": self.day,
            "留出炉次数": self.total,
            "朴素基线总误差": round(self.baseline_error, 3),
            "模型总误差": round(self.model_error, 3),
            "原价售罄": self.soldout,
            "预估不足炉次": self.missed_stock,
        }


def recent_replay(history, day, station_skus, days):
    by_key = defaultdict(list)
    for item in chronological_sample(history, day):
        if (item.station, item.sku) in station_skus:
            by_key[item.sku, item.day].append(item)
    trials = []
    denied = []
    for (sku, date), fixtures in sorted(by_key.items()):
        if date < day - days:
            continue
        candidates = chronological_sample(history, date, product=sku)
        if len(candidates) < 4:
            denied.append({"商品": sku, "业务日": date, "结果": "训练样本不足"})
            continue
        regression = fit(candidates, date, product=sku)
        naive = median(row.late_sales for row in candidates)
        raw_errors = []
        estimated_errors = []
        missed = 0
        soldout = 0
        for row in fixtures:
            expectation = one(regression, points(row))
            raw_errors.append(abs(min(row.remaining, naive) - row.late_sales))
            estimated_errors.append(abs(expectation - row.late_sales))
            missed += expectation + 0.5 < row.late_sales
            soldout += row.remaining == row.late_sales
        trials.append(Trial(sku, date, len(fixtures), fsum(raw_errors), fsum(estimated_errors), missed, soldout))
    return trials, denied


def replay_summary(trials):
    groups = defaultdict(list)
    for trial in trials:
        groups[trial.sku].append(trial)
    outcomes = []
    for sku, group in sorted(groups.items()):
        slices = len({line.day for line in group})
        count = sum(line.total for line in group)
        baseline = fsum(line.baseline_error for line in group)
        estimate = fsum(line.model_error for line in group)
        signed = (baseline - estimate) / baseline if baseline else None
        outcomes.append({
            "商品": sku,
            "回放日": slices,
            "回放炉次": count,
            "历史中位绝对误差": round(baseline/count, 3) if count else None,
            "模型平均绝对误差": round(estimate/count, 3) if count else None,
            "误差改善率": round(signed, 4) if signed is not None else None,
            "原价售罄": sum(line.soldout for line in group),
        })
    return outcomes


def masked_station(history, station, day):
    eligible = chronological_sample(history, day)
    visible = [line for line in eligible if line.station != station]
    absent = [line for line in eligible if line.station == station]
    return visible, absent


def replay_held_stations(history, day, *, min_training=15):
    results = []
    for station in sorted({row.station for row in history}):
        anchors, trials = masked_station(history, station, day)
        if len(anchors) < min_training or not trials:
            results.append({"柜台": station, "验证量": len(trials), "模型误差": None, "状态": "样本量不足"})
            continue
        trained = fit(anchors, day)
        errors = [abs(one(trained, points(row)) - row.late_sales) for row in trials]
        count = len(errors)
        results.append({"柜台": station, "验证量": count, "模型误差": round(fsum(errors)/count, 3), "状态": "已验证"})
    return results
