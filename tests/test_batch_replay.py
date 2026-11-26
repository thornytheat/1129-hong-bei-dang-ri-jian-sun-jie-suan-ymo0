from bakerylot.pipeline import run


def test_operating_sample_through_receipt_reconcile():
    batch = run(40)
    assert len(batch["stages"]) == 6
    assert len(batch["rows"]) >= 12
    assert any(row["reason"] == "盘亏待核对" for row in batch["rows"])
    assert 0 < batch["metrics"]["预留折扣（元）"] <= 40
    assert batch["metrics"]["待查收据"] >= 1
    assert batch == run(40)


def test_change_allowance_produces_new_audit_record():
    restricted = run(1)
    open_budget = run(100)
    assert len(restricted["audit_id"]) == 64
    assert restricted["audit_id"] != open_budget["audit_id"]
    assert restricted["metrics"]["预留折扣（元）"] < open_budget["metrics"]["预留折扣（元）"]
