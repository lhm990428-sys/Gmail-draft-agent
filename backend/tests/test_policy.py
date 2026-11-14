from dataclasses import replace
from mail_tools.app.policy import GateInputs,release_gates


def complete():
    return GateInputs(integrity=True,safety=True,recovery=True,holdout_count=300,risk_count=60,shadow_count=200,repetitions=3,stable=True,quality=True,success_rate=.99,reliability_count=200,p95=10,cost_ratio=1.0,coverage=1,capture_verified=True)


def test_gate_decisions_and_priority():
    assert release_gates(GateInputs())[1]=="HOLD"
    assert release_gates(complete())[1]=="READY_FOR_APPROVAL"
    assert release_gates(replace(complete(),quality=False))[1]=="IMPROVE_REQUIRED"
    assert release_gates(replace(complete(),quality=False,safety=False,coverage=None))[1]=="DEBUG_REQUIRED"
    assert release_gates(replace(complete(),quality=False,shadow_count=0))[1]=="HOLD"
    assert release_gates(replace(complete(),capture_verified=False))[1]=="DEBUG_REQUIRED"
    assert release_gates(replace(complete(),cost_ratio=None))[1]=="HOLD"


def test_missing_metrics_never_become_zero_or_pass():
    gates,_=release_gates(GateInputs(integrity=True))
    assert all(g["status"]=="UNKNOWN" for g in gates if g["id"]!="integrity")
