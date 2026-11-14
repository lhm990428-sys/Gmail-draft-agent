from dataclasses import dataclass


@dataclass(frozen=True)
class GateInputs:
    integrity: bool|None=None
    safety: bool|None=None
    recovery: bool|None=None
    holdout_count: int=0
    risk_count: int=0
    shadow_count: int=0
    repetitions: int=0
    stable: bool|None=None
    quality: bool|None=None
    success_rate: float|None=None
    reliability_count: int=0
    unresolved_failure: bool=False
    p95: float|None=None
    cost_ratio: float|None=None
    coverage: float|None=None
    capture_verified: bool|None=None


def release_gates(inputs: GateInputs):
    def result(value):return "UNKNOWN" if value is None else "PASS" if value else "FAIL"
    enough=inputs.holdout_count>=300 and inputs.risk_count>=60 and inputs.shadow_count>=200 and inputs.repetitions>=3
    evidence=None if not enough or inputs.stable is None else inputs.stable
    reliability=False if inputs.unresolved_failure else None if inputs.reliability_count<200 or inputs.success_rate is None else inputs.success_rate>=.98
    performance=None if inputs.p95 is None or inputs.cost_ratio is None else inputs.p95<=30 and inputs.cost_ratio<=1.2
    observed=None if inputs.coverage is None or inputs.capture_verified is None else inputs.coverage==1 and inputs.capture_verified
    values=[("integrity","Integrity",inputs.integrity,"locked manifest / hash chain"),
            ("safety","Safety",inputs.safety,"fault suite: policy/send/secret/duplicate violations=0"),
            ("evidence","Evidence",evidence,"holdout>=300 / risk>=60 / shadow>=200 / repetitions>=3 / stable"),
            ("quality","Quality",inputs.quality,"all versioned quality thresholds + regression<=3pp"),
            ("reliability","Reliability",reliability,"confirmed success>=.98 / n>=200 / no unresolved failure"),
            ("performance","Performance / Cost",performance,"p95<=30s / cost ratio<=1.20"),
            ("observability","Observability",observed,"capture verified / delivery coverage=1.00"),
            ("recovery","Recovery",inputs.recovery,"checkpoint/replay/uncertain/rollback verified")]
    gates=[{"id":key,"name":name,"status":result(value),"evidence":"verified measurements" if value is not None else "필수 증거 미완료","threshold":threshold} for key,name,value,threshold in values]
    technical={"integrity","safety","reliability","observability","recovery"}
    decision="DEBUG_REQUIRED" if any(g["id"] in technical and g["status"]=="FAIL" for g in gates) else "HOLD" if any(g["status"]=="UNKNOWN" for g in gates) else "IMPROVE_REQUIRED" if any(g["status"]=="FAIL" for g in gates) else "READY_FOR_APPROVAL"
    return gates,decision
