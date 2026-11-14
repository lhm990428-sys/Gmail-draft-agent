import asyncio
from contextlib import asynccontextmanager
import hmac
import json
from pathlib import Path
import secrets
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware
from mail_tools.settings import ROOT
from .broker import PolicyDenied, StaleReview, UncertainWrite
from .service import Service, NotFound, Busy
from .store import events
from .ops import assess


class Body(BaseModel): model_config=ConfigDict(extra="forbid")
class Bootstrap(Body): token: str = Field(min_length=32,max_length=200)
class Start(Body):
    query: str = "label:agent-test"
    maxItems: int = Field(default=1,ge=1,le=10)
    source: str = "fixture"
    kind: str = "reply"
class Edit(Body): revision: int; body: str=Field(min_length=1,max_length=10000)
class Decision(Body): revision: int; action: str
class Promotion(Body): target: str
class GatewayCommand(Body):
    command: str=Field(pattern="^(run|status)$")
    run_id: str|None=Field(default=None,max_length=80)
    request_id: str=Field(min_length=36,max_length=36)
class MailboxControl(Body): paused: bool


def create_app(service: Service,bootstrap_token: str,run_telemetry=True,gateway_key: str|None=None):
    sessions={};attempts=[];bootstrap_used=False;stop=threading.Event()
    def background():
        maintenance_at=0
        while not stop.wait(5):
            try: service.telemetry.flush(limit=10)
            except Exception: pass  # outbox remains durable and health stays UNKNOWN.
            try:service.telemetry.export_experiments()
            except Exception:pass
            if time.time()-maintenance_at>3600:
                from .retention import expire_artifacts
                try:expire_artifacts(service)
                except Exception:pass
                maintenance_at=time.time()
    @asynccontextmanager
    async def lifespan(app):
        worker=threading.Thread(target=background,name="telemetry-outbox",daemon=True) if run_telemetry else None
        if worker: worker.start()
        if service.config.automatic_mail:service.mailbox.start()
        yield
        await asyncio.to_thread(service.mailbox.close)
        stop.set()
        if worker: await asyncio.to_thread(worker.join)
    app=FastAPI(title="Hermes Mail Local Console",docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1","localhost"])
    origins={"http://127.0.0.1:8000","http://localhost:8000","http://127.0.0.1:5173","http://localhost:5173"}

    @app.middleware("http")
    async def guard(request,call_next):
        path=request.url.path
        if request.headers.get("origin") and request.headers["origin"] not in origins:
            await asyncio.to_thread(service.audit,"auth.origin_denied","failed",request.method,"/api/*")
            return JSONResponse({"detail":"Origin rejected"},403)
        if path.startswith("/api/") and path not in ("/api/v1/health","/api/v1/session/bootstrap","/api/v1/gateway/command"):
            session=sessions.get(request.cookies.get("hermes_session",""))
            if not session or session["expires"]<time.time():
                await asyncio.to_thread(service.audit,"auth.denied","failed",request.method,"/api/*")
                return JSONResponse({"detail":"로컬 콘솔 로그인이 필요합니다."},401)
            request.state.session=session
            if request.method not in ("GET","HEAD","OPTIONS"):
                if request.headers.get("origin") not in origins or not hmac.compare_digest(request.headers.get("x-csrf-token",""),session["csrf"]):
                    await asyncio.to_thread(service.audit,"auth.csrf_denied","failed",request.method,"/api/*")
                    return JSONResponse({"detail":"CSRF validation failed"},403)
        if path=="/api/v1/session/bootstrap" and request.headers.get("origin") not in origins:
            return JSONResponse({"detail":"Bootstrap origin rejected"},403)
        response=await call_next(request)
        if path.startswith("/api/") and path!="/api/v1/health":
            route=getattr(request.scope.get("route"),"path","/api/*")
            await asyncio.to_thread(service.audit,"api.request.completed","done" if response.status_code<400 else "failed",request.method,route)
        response.headers["Cache-Control"]="no-store" if path.startswith("/api/") else "no-cache"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Content-Security-Policy"]="frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        return response

    for error,status in ((PolicyDenied,403),(StaleReview,409),(UncertainWrite,503),(NotFound,404),(Busy,429)):
        def handle(request,exc,status=status): return JSONResponse({"detail":str(exc)},status)
        app.add_exception_handler(error,handle)
    @app.exception_handler(Exception)
    async def unexpected(request,error):
        return JSONResponse({"detail":"서버 요청 실패 · "+type(error).__name__+" (비밀 보호를 위해 원문 숨김)"},500)

    @app.get("/api/v1/health")
    def health(): return {"status":"ok","mode":"local-dev","phase":4}

    @app.post("/api/v1/session/bootstrap")
    def bootstrap(body: Bootstrap):
        nonlocal bootstrap_used
        attempts[:]=[stamp for stamp in attempts if stamp>time.time()-60]
        if len(attempts)>=5: raise HTTPException(429,"로그인 시도 한도")
        attempts.append(time.time())
        if bootstrap_used or not hmac.compare_digest(body.token,bootstrap_token): raise HTTPException(403,"시작 코드가 유효하지 않습니다. 로컬 실행기를 다시 시작하세요.")
        bootstrap_used=True
        identifier=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        sessions[identifier]={"csrf":csrf,"expires":time.time()+service.config.session_seconds,"actor":"local-human"}
        response=JSONResponse({"csrf":csrf,"actor":"local-human"})
        response.set_cookie("hermes_session",identifier,httponly=True,samesite="strict",max_age=service.config.session_seconds,path="/")
        return response

    @app.get("/api/v1/session")
    def session(request: Request): return {"csrf":request.state.session["csrf"],"actor":"local-human"}
    @app.post("/api/v1/gateway/command")
    def gateway_command(body: GatewayCommand,request: Request):
        from uuid import UUID
        try: UUID(body.request_id)
        except ValueError: raise HTTPException(400,"Invalid command receipt")
        token=request.headers.get("authorization","").removeprefix("Bearer ")
        if gateway_key is None or not hmac.compare_digest(token,gateway_key): raise HTTPException(403,"Gateway credential rejected")
        if body.command=="status":
            job=service.store.get("job",body.run_id) if body.run_id else None
            return {"status":"ready","execution":None if job is None else {"id":job["id"],"status":job["status"],"decision":job["decision"]},"allowed_input":"synthetic fixture","human_approval":"local console only"}
        with service.store.lock:
            existing=service.store.get("gateway-receipt",body.request_id)
            if existing: return existing
            result=service.start(source="fixture",receipt=body.request_id)
            service.store.put("gateway-receipt",body.request_id,result)
            service.store.emit(result["id"],"gateway","gateway.command.accepted","done","인증된 Hermes 명령 · 합성 입력만",memory={"request_id":body.request_id})
            return result
    @app.get("/api/v1/snapshot")
    def snapshot(): return service.snapshot()
    @app.get("/api/v1/mailbox")
    def mailbox():return service.mailbox.view()
    @app.post("/api/v1/mailbox/control")
    def mailbox_control(body: MailboxControl):return service.mailbox.pause(body.paused)
    @app.post("/api/v1/runs",status_code=201)
    def start(body: Start):
        if body.query!="label:"+service.config.label: raise PolicyDenied("QUERY_OUTSIDE_APPROVED_LABEL")
        # Existing console sends maxItems=10; admission deliberately processes one.
        return service.start(source=body.source,kind=body.kind)
    @app.put("/api/v1/reviews/{mid}/draft")
    def edit(mid: str,body: Edit): return service.edit(mid,body.revision,body.body)
    @app.post("/api/v1/reviews/{mid}/decision")
    def decide(mid: str,body: Decision): return service.decide(mid,body.revision,body.action)
    @app.post("/api/v1/reviews/{mid}/reconcile")
    def reconcile(mid: str): return service.reconcile(mid)
    @app.post("/api/v1/runs/{rid}/retry",status_code=201)
    def retry(rid: str): return service.retry(rid)
    @app.get("/api/v1/runs/{rid}/runtime")
    def runtime(rid: str,mode: str="normal"):
        if mode!="normal": raise PolicyDenied("HYPOTHETICAL_BRANCHES_ARE_MOCK_ONLY")
        return service.runtime(rid)
    @app.get("/api/v1/releases/{rid}/manifest")
    def release_manifest(rid: str):
        value=service.store.get("manifest",rid)
        if not value: raise NotFound(rid)
        return value
    @app.get("/api/v1/releases/{rid}/evidence")
    def evidence(rid: str): return assess(service.store,service.config,service.telemetry,rid)[1]
    @app.get("/api/v1/releases/{rid}/artifact")
    def artifact(rid: str):
        value=service.store.get("release-artifact",rid)
        if not value:raise NotFound(rid)
        return value
    @app.post("/api/v1/releases/{rid}/promote")
    def promote(rid: str,body: Promotion):
        from .deployment import activate
        activate(service,rid,body.target)
        return service.store.get("release",rid)
    @app.post("/api/v1/deployments/canary/rollback")
    def rollback_canary():
        from .deployment import rollback
        return rollback(service)
    @app.get("/api/v1/evaluations/cases/{cid}")
    def case(cid: str):
        value=service.store.get("eval-case",cid)
        if not value: raise NotFound(cid)
        return value
    @app.post("/api/v1/ops/flush")
    def flush(): return service.telemetry.flush(limit=20)
    @app.post("/api/v1/ops/diagnose")
    def diagnose(): return service.diagnose()
    @app.post("/api/v1/ops/evaluate")
    def evaluate():
        from .evaluation import evaluate
        return evaluate(service)
    @app.get("/api/v1/events")
    async def stream(request: Request):
        raw=request.headers.get("last-event-id","0")
        if not raw.isdigit(): raise HTTPException(400,"Invalid event cursor")
        async def generate():
            cursor=int(raw)
            while not await request.is_disconnected():
                if request.state.session["expires"]<time.time(): break
                with service.store.engine.connect() as connection:
                    rows=connection.execute(select(events.c.global_sequence,events.c.run_id,events.c.sequence).where(events.c.global_sequence>cursor).order_by(events.c.global_sequence).limit(100)).all()
                for row in rows:
                    cursor=row.global_sequence
                    if row.run_id.startswith("audit-"):continue
                    yield "id: "+str(cursor)+"\nevent: refresh\ndata: "+json.dumps({"runId":row.run_id,"sequence":row.sequence})+"\n\n"
                if not rows: yield ": heartbeat\n\n"
                await asyncio.sleep(.75)
        return StreamingResponse(generate(),media_type="text/event-stream",headers={"X-Accel-Buffering":"no"})
    dist=ROOT/"frontend/dist-api"
    if (dist/"assets").exists(): app.mount("/assets",StaticFiles(directory=dist/"assets"),name="assets")
    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"): raise HTTPException(404,"Unknown API")
        if not (dist/"index.html").exists(): raise HTTPException(503,"프론트엔드 API 빌드가 필요합니다.")
        return FileResponse(dist/"index.html")
    return app
