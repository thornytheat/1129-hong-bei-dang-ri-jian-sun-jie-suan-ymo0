from hashlib import sha256
from json import loads
from pathlib import Path
from math import sqrt, fsum

from .bake_lots import service as ovens
from .waste_reconcile import service as inventory
from .leftover_curve import service as demand
from .markdown_bands import service as uncertainty
from .shelf_action import service as approvals
from .drawer_close import service as closing

ROOT = Path(__file__).resolve().parents[2]


def stage(title, summary, records):
    return {"title": title, "summary": summary, "records": records}


def read_documents(folder: Path, filename: str):
    raw = (folder / filename).read_bytes()
    rows = []
    for line in raw.decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(loads(line))
        except ValueError:
            rows.append(None)
    return rows, sha256(raw).hexdigest()


def assess_model(history, prior_day, product, coverage):
    # 训练、回放和待决当天严格按业务日分离。
    training_day = prior_day - 5
    baseline = demand.fit(history, training_day, product=product)
    validation_samples = [row for row in demand.chronological_sample(history, prior_day)
                          if row.sku == product and row.day >= training_day]
    points = [(row.late_sales, demand.one(baseline, demand.points(row))) for row in validation_samples]
    band = uncertainty.validate(points, coverage=coverage)
    return baseline, band


def run(capacity: int | None = None, *, dataset: Path | None = None) -> dict:
    config = loads((ROOT / "configs" / "bakery_policy.json").read_text(encoding="utf-8"))
    budget = config["capacity_yuan"] if capacity is None else capacity
    if not 1 <= budget <= 100:
        raise ValueError("DISCOUNT_BUDGET_RANGE")
    source = ROOT / "sample_data" if dataset is None else dataset
    files = ("oven_handover.ndjson", "counter_postings.ndjson", "dayend_history.ndjson", "register_receipts.ndjson", "voucher_campaigns.ndjson")
    (oven_rows, movements, past_rows, slips, campaigns), hashes = zip(*(read_documents(source, name) for name in files), strict=True)
    intake, ledger, history, registers = ovens.inspect(oven_rows), inventory.inspect(movements), demand.inspect(past_rows), closing.inspect(slips)
    cutoff = {"day": config["day"], "minute": config["minute"]}
    current, current_errors = ovens.close_candidates(intake.records, **cutoff)
    balances, ledger_errors = inventory.snapshot(ledger.records, **cutoff)
    usable = [inventory.sellable(ticket.lot, ticket.baked, balances.get(ticket.lot, {})) for ticket in current]
    totals = inventory.evidence_totals(usable)
    forecasts, proposals = [], []
    training = {sku: assess_model(history.records, config["day"], sku, config["coverage"])
                for sku in sorted({ticket.sku for ticket in current})}
    for ticket, stock in zip(current, usable, strict=True):
        if stock["variance"]:
            continue
        curve, band = training[ticket.sku]
        remaining = ovens.lot_clock(ticket, config["minute"])["minutes_left"]
        vector = (stock["sellable"], remaining, config["day"] % 7, config["rain_mm"])
        estimate = demand.one(curve, vector)
        distance = sqrt(fsum(((value - mean) / scale) ** 2 for value, (mean, scale) in zip(vector, curve.moments, strict=True)))
        measured = uncertainty.StockForecast.parse({"lot": ticket.lot, "available": stock["sellable"], "forecast": estimate,
                    "distance": distance, "shelf_remaining": remaining, "price_cents": ticket.price_cents})
        result = uncertainty.proposal(measured, band)
        forecasts.append({**result, "训练样本": curve.count, "校准样本": band.observed, "校准半径": round(band.radius, 2)})
        proposals.append({**result, "station": ticket.station, "sku": ticket.sku,
                          "available": stock["sellable"], "markdown_pct": config["markdown_pct"]})
    requests = approvals.inspect(proposals)
    authorized, used = approvals.authorize(requests.records, budget * 100, per_sku=config["per_counter_sku"])
    for ticket, stock in zip(current, usable, strict=True):
        if stock["variance"]:
            authorized.append({"lot": ticket.lot, "station": ticket.station, "sku": ticket.sku, "available": 0,
                               "at_risk": 0, "units": 0,"reserved": 0, "reason": "盘亏待核对"})
    vouchers, coupon_issues = closing.coupon_amounts(campaigns, registers.records, approvals.allocate_voucher)
    receipts = closing.batch_close(registers.records, authorized, vouchers)
    receipts_summary = closing.receipt_totals(receipts)
    cashbook = closing.rollup(registers.records, receipts)
    audit_id = closing.revision_key(policies={**config, "budget_yuan": budget}, inputs=hashes, evidence=receipts)
    rows = [{**row, "reserved_yuan": round(row["reserved"] / 100, 2)} for row in authorized]
    diagnostics = approvals.estimate_combinations(
        requests.records, budget * 100, config["per_counter_sku"]
    )
    comparison = approvals.discount_breakdown(requests.records, rows, diagnostics)
    trials, denied = demand.recent_replay(
        history.records, config["day"],
        {(ticket.station, ticket.sku) for ticket in current}, 6
    )
    replay = demand.replay_summary(trials)
    transfer_check = demand.replay_held_stations(history.records, config["day"])
    stages = [
        stage("炉次流水", f"截止前仍可售 {len(current)} 炉，需查 {len(current_errors) + len(intake.rejected)} 条", [ovens.lot_clock(ticket, config["minute"]) for ticket in current] + current_errors + [x.evidence() for x in intake.rejected]),
        stage("损耗核算", f"已处理 {ledger.read_count} 条变动，报损及捐赠 {totals['disposed']} 件", usable + ledger_errors),
        stage("余货拟合", f"按 {len(training)} 种商品独立拟合尾段销量", forecasts + replay + transfer_check + denied),
        stage("折价区间", f"批准前核对 {len(forecasts)} 个区间和历史距离", [{"商品": sku, **uncertainty.summarize(model[1])} for sku, model in training.items()]),
        stage("促销限量", f"按 ¥{budget} 上限预留 ¥{used/100:.2f}", rows + [diagnostics.evidence()] + comparison + approvals.stock_movements(rows)),
        stage("日结汇总", f"{receipts_summary['approved']} 张收据验证通过，{receipts_summary['exceptions']} 张待查", receipts + [line.evidence() for line in cashbook] + coupon_issues),
    ]
    series = [{"label": row["lot"], "value": row["at_risk"]} for row in sorted(rows, key=lambda row: row["lot"])[:12]]
    return {"metrics": {"仍可售件数": totals["sellable"], "预留折扣（元）": used / 100,
                        "待查收据": receipts_summary["exceptions"], "通过收据实收（元）": receipts_summary["net_cents"] / 100},
            "columns": {"lot": "炉次", "station": "柜台", "sku": "商品", "available": "可售", "at_risk": "滞销预测",
                        "units": "核准件数", "reserved_yuan": "预留金额（元）", "reason": "处置"},
            "rows": rows, "series": series, "stages": stages, "audit_id": audit_id, "ranking_scenario": {
                "budget_cents": budget * 100, "comparison": comparison,
                "reservations": approvals.burn_curve(rows),
            }, "model_replay": [trial.evidence() for trial in trials]}
