"""Unit tests for the Phase 4 orchestration logic in challenge-4-deploy/deploy.py.

These exercise the workflow's decision-making (which machines get diagnosed,
which get escalated to a human) without calling any Azure agent -- the
agent-calling functions are monkeypatched out, since they need live
credentials and are exercised manually when running deploy.py end to end.
"""
import deploy


# --- _parse_escalation --------------------------------------------------------

def test_parse_escalation_detects_flag():
    assert deploy._parse_escalation("CRITICAL reading. ESCALATE: YES") is True


def test_parse_escalation_absent_by_default():
    assert deploy._parse_escalation("WARNING reading. ESCALATE: NO") is False
    assert deploy._parse_escalation("Nothing notable here.") is False


# --- run_anomaly_scan (parallel) ----------------------------------------------

def test_run_anomaly_scan_checks_every_machine_in_parallel(monkeypatch):
    calls = []

    def fake_check_single_machine(agent_name, machine_id):
        calls.append(machine_id)
        return {"machine_id": machine_id, "report": f"report for {machine_id}", "escalate": False}

    monkeypatch.setattr(deploy, "check_single_machine", fake_check_single_machine)

    machines = ["MX-001", "EX-002", "CP-003"]
    results = deploy.run_anomaly_scan("anomaly-detection-agent", machines=machines)

    assert set(calls) == set(machines)
    assert set(results.keys()) == set(machines)
    assert all(results[m]["report"] == f"report for {m}" for m in machines)


# --- run_factory_health_workflow: escalation gate -----------------------------

def test_escalated_machines_are_excluded_from_diagnosis(monkeypatch):
    """A machine the Anomaly Detection Agent flags as low-confidence (CP-003,
    which does have real anomalies per sensor_data.json) must be escalated
    to a human instead of being auto-diagnosed, while confidently-flagged
    machines (MX-001, IS-005) still get diagnosed.
    """
    fake_results = {
        "MX-001": {"machine_id": "MX-001", "report": "WARNING ... ESCALATE: NO", "escalate": False},
        "EX-002": {"machine_id": "EX-002", "report": "normal ... ESCALATE: NO", "escalate": False},
        "CP-003": {"machine_id": "CP-003", "report": "CRITICAL but ambiguous ... ESCALATE: YES", "escalate": True},
        "CU-004": {"machine_id": "CU-004", "report": "normal ... ESCALATE: NO", "escalate": False},
        "IS-005": {"machine_id": "IS-005", "report": "WARNING ... ESCALATE: NO", "escalate": False},
    }
    diagnosed = []

    def fake_run_anomaly_scan(agent_name, machines=None):
        return fake_results

    def fake_run_fault_diagnosis(agent_name, machine_id, anomalies):
        diagnosed.append(machine_id)
        return f"diagnosis for {machine_id}"

    monkeypatch.setattr(deploy, "run_anomaly_scan", fake_run_anomaly_scan)
    monkeypatch.setattr(deploy, "run_fault_diagnosis", fake_run_fault_diagnosis)

    report = deploy.run_factory_health_workflow("anomaly-detection-agent", "fault-diagnosis-agent")

    assert report["escalated_machines"] == ["CP-003"]
    assert "CP-003" not in report["diagnoses"]
    assert "CP-003" not in report["machines_with_anomalies"]
    assert set(report["machines_with_anomalies"]) == {"MX-001", "IS-005"}
    assert set(diagnosed) == {"MX-001", "IS-005"}


def test_no_escalations_diagnoses_all_anomalous_machines(monkeypatch):
    fake_results = {
        m: {"machine_id": m, "report": "ESCALATE: NO", "escalate": False}
        for m in deploy.MACHINES
    }
    monkeypatch.setattr(deploy, "run_anomaly_scan", lambda agent_name, machines=None: fake_results)
    monkeypatch.setattr(
        deploy, "run_fault_diagnosis",
        lambda agent_name, machine_id, anomalies: f"diagnosis for {machine_id}",
    )

    report = deploy.run_factory_health_workflow("anomaly-detection-agent", "fault-diagnosis-agent")

    assert report["escalated_machines"] == []
    assert set(report["machines_with_anomalies"]) == {"MX-001", "CP-003", "IS-005"}
    assert set(report["diagnoses"].keys()) == {"MX-001", "CP-003", "IS-005"}
