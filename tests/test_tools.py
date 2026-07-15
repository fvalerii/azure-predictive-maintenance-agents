"""Unit tests for the local tool functions used by the Foundry agents.

These functions only read/write local JSON files -- no Azure credentials or
network access are needed to run this suite. They're the same functions the
Anomaly Detection and Fault Diagnosis agents call via function calling, so
these tests are a fast, free way to verify the underlying logic is correct
independent of whether Foundry infrastructure is deployed.
"""
import json

import agents
import deploy


# --- check_thresholds (agents.py) -------------------------------------------

def test_check_thresholds_flags_critical_machine():
    result = json.loads(agents.check_thresholds("CP-003"))
    assert result["status"] == "critical"
    anomaly_sensors = {a["sensor"] for a in result["anomalies"]}
    assert {"temperature", "pressure", "vibration"} <= anomaly_sensors


def test_check_thresholds_normal_machine_has_no_anomalies():
    result = json.loads(agents.check_thresholds("EX-002"))
    assert result["status"] == "normal"
    assert result["anomalies"] == []


def test_check_thresholds_accepts_id_or_name():
    by_id = json.loads(agents.check_thresholds("MX-001"))
    by_name = json.loads(agents.check_thresholds("mixer"))
    assert by_id["machine_id"] == by_name["machine_id"] == "MX-001"


def test_check_thresholds_unknown_machine_returns_error():
    result = json.loads(agents.check_thresholds("ZZ-999"))
    assert "error" in result


# --- deploy.py has its own copy of check_thresholds; keep them in sync -----

def test_deploy_check_thresholds_matches_agents_version():
    for machine in agents._load_sensor_batch():
        mid = machine["machine_id"]
        a = json.loads(agents.check_thresholds(mid))
        d = json.loads(deploy.check_thresholds(mid))
        assert a["status"] == d["status"]
        assert {x["sensor"] for x in a["anomalies"]} == {x["sensor"] for x in d["anomalies"]}


# --- fetch_maintenance_history -----------------------------------------------

def test_fetch_maintenance_history_known_machine():
    history = json.loads(agents.fetch_maintenance_history("CP-003"))
    assert isinstance(history, list) and len(history) >= 1
    assert all("date" in entry and "action" in entry for entry in history)


def test_fetch_maintenance_history_covers_every_machine():
    for machine in agents._load_sensor_batch():
        history = json.loads(agents.fetch_maintenance_history(machine["machine_id"]))
        assert history != "No past maintenance history found."


def test_fetch_maintenance_history_unknown_machine():
    history = json.loads(agents.fetch_maintenance_history("ZZ-999"))
    assert history == "No past maintenance history found."


# --- lookup_spare_parts -------------------------------------------------------

def test_lookup_spare_parts_in_stock():
    part = json.loads(agents.lookup_spare_parts("TF-101"))
    assert part["status"] == "IN_STOCK"
    assert part["quantity"] > 0


def test_lookup_spare_parts_out_of_stock():
    part = json.loads(agents.lookup_spare_parts("TF-202"))
    assert part["status"] == "OUT_OF_STOCK"


def test_lookup_spare_parts_strips_hash_prefix():
    with_hash = json.loads(agents.lookup_spare_parts("#TF-303"))
    without_hash = json.loads(agents.lookup_spare_parts("TF-303"))
    assert with_hash == without_hash


def test_lookup_spare_parts_unknown_part():
    part = json.loads(agents.lookup_spare_parts("TF-999"))
    assert part["status"] == "UNKNOWN_PART"


# --- create_work_order --------------------------------------------------------

def test_create_work_order_writes_expected_record(tmp_path, monkeypatch):
    monkeypatch.setattr(agents, "REPO_ROOT", tmp_path)

    result = json.loads(agents.create_work_order("CP-003", "Replace heating coil", "IMMEDIATE"))
    assert result["status"] == "SUCCESS"
    assert result["work_order_id"].startswith("WO-")

    work_orders = json.loads((tmp_path / "work_orders.json").read_text())
    assert work_orders[0]["machine_id"] == "CP-003"
    assert work_orders[0]["urgency"] == "IMMEDIATE"
