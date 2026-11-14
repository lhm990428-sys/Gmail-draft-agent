def topology(run_id: str, source: str, history: list,registry=None) -> dict:
    specs = [("gateway", "Gmail 수신", "tool", 0,220), ("supervisor", "Supervisor", "agent",540,-60),
             ("context","Context","agent",240,220), ("triage","Triage","agent",500,110), ("risk","Risk","agent",500,350),
             ("draft","Draft","agent",770,240), ("critic","Critic","agent",1030,240), ("human","사용자 승인","human",1030,480),
             ("broker","Draft Broker","tool",770,480), ("checkpoint","공개 상태 / Checkpoint","checkpoint",240,570)]
    if any(e["nodeId"]=="diagnose" for e in history): specs.append(("diagnose","Diagnose","agent",540,780))
    custom=sorted({e["nodeId"] for e in history}-{x[0] for x in specs})
    for index,identifier in enumerate(custom):specs.append((identifier,identifier,"agent",240+260*(index%3),800+180*(index//3)))
    nodes = [{"id": n,"name": name,"kind": kind,"role": name,"x": x,"y": y,"taskId": "t-"+n,"scope": "외부 쓰기 금지; 공개 결과만" if kind=="agent" else "승인된 로컬 업무 범위"} for n,name,kind,x,y in specs]
    relationships = [("receive","gateway","context","data"), ("context-triage","context","triage","data"), ("context-risk","context","risk","data"), ("triage-draft","triage","draft","data"), ("risk-draft","risk","draft","data"), ("draft-critic","draft","critic","data"), ("critic-review","critic","human","data"), ("approval","human","broker","data"), ("rework","critic","draft","rework")]
    relationships += [("dispatch-"+n,"supervisor",n,"delegation") for n in ("context","triage","risk","draft","critic")]
    relationships += [("memory-"+n,n,"checkpoint","memory") for n in ("context","triage","risk","draft","critic")]
    economy=any(e["type"]=="supervisor.plan.validated" and "코드 감독" in e["summary"] for e in history)
    if economy:
        for node in nodes:
            if node["id"] in ("supervisor","context","risk"):node["name"]+=" · CODE";node["role"]+=" · 코드 / LLM 없음"
        relationships=[r for r in relationships if r[0] not in ("receive","context-triage","context-risk","rework","approval")]
        relationships += [("receive","gateway","triage","data"),("triage-context","triage","context","data"),("triage-risk","triage","risk","data")]
        if any(e["type"]=="review.completed" for e in history):relationships.append(("review-result","human","checkpoint","memory"))
    for identifier in custom:
        parent=next((key for key,spec in registry.entries.items() if identifier in spec.children),"supervisor") if registry else "supervisor"
        relationships += [("dispatch-"+identifier,parent,identifier,"delegation"),("memory-"+identifier,identifier,"checkpoint","memory")]
    edges = [{"id": key,"source": a,"target": b,"kind": kind,"label": kind,"contract": "TaskEnvelope / typed artifact / versioned state"} for key,a,b,kind in relationships]
    deps = {"context":["t-gateway","t-supervisor"],"triage":["t-context"],"risk":["t-context"],"draft":["t-triage","t-risk"],"critic":["t-draft"],"human":["t-critic"],"broker":["t-human"]}
    for identifier in custom:deps[identifier]=["t-context"]
    tasks = [{"id": n["taskId"],"owner": n["id"],"goal": n["role"],"dependsOn": deps.get(n["id"],[])} for n in nodes]
    from datetime import datetime
    start = datetime.fromisoformat(history[0]["time"]) if history else None
    events = []
    for event in history:
        entry = {"sequence": event["sequence"], "atMs": round((datetime.fromisoformat(event["time"])-start).total_seconds()*1000), "type": event["type"], "nodeId": event["nodeId"], "status": event["status"], "summary": event["summary"]}
        entry.update({key: event[key] for key in ("input","output","memory","edgeId","checkpoint") if key in event})
        events.append(entry)
    return {"version":"runtime.v1","runId":run_id,"source":source,"mode":"rework" if any(e["type"]=="critic.rework" for e in history) else "normal","nodes":nodes,"edges":edges,"tasks":tasks,"events":events}
