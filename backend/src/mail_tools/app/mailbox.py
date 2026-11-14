"""Single server-side readonly Gmail collector and durable message queue."""
import threading
import time
from datetime import datetime,timezone
from .config import digest
from .store import now
from .service import Busy


class Mailbox:
    def __init__(self,service):
        self.service=service;self.store=service.store;self.lock=threading.Lock()
        self.stop=threading.Event();self.thread=None
        service.gmail.stop_event=self.stop
        self.state=self.store.get("mailbox-control","main") or {"paused":False,"lastChecked":None,"lastSuccess":None,"error":None,"nextCheck":None}
        # Manual pause persists across restarts.
        self.state.update(running=False)

    def persist(self):self.store.put("mailbox-control","main",self.state)
    def view(self):
        cutoff=datetime.fromtimestamp(time.time()-72*3600,timezone.utc).isoformat()
        items=[i for i in self.store.list("mailbox-message") if i["receivedAt"]>=cutoff]
        for item in items:
            job=self.store.get("job",item["runId"]) if item.get("runId") else None
            if job:
                item["status"]="processing" if job["status"]=="running" else "review" if job["status"]=="review" else "error" if job["status"]=="failed" else "done"
                item["decision"]=job["decision"]
        return {**self.state,"enabled":self.service.config.automatic_mail,"pollSeconds":self.service.config.poll_seconds,"windowHours":72,"items":items,"costCap":False}
    def pause(self,paused):
        with self.lock:
            self.state["paused"]=paused;self.persist()
            self.service.audit("mailbox.paused" if paused else "mailbox.resumed","done","POST","/api/v1/mailbox/control")
        return self.view()
    def start(self):
        self.thread=threading.Thread(target=self.loop,name="gmail-readonly-collector",daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=40)
    def loop(self):
        while not self.stop.is_set():
            self.tick()
            if self.stop.wait(self.service.config.poll_seconds):break
    def tick(self):
        if not self.service.config.automatic_mail or not self.service.config.allow_real_mail_export:return
        if not self.lock.acquire(blocking=False):return
        try:
            if self.state.get("paused"):return
            stamp=time.time();self.state.update(running=True,lastChecked=now(),nextCheck=datetime.fromtimestamp(stamp+self.service.config.poll_seconds,timezone.utc).isoformat())
            scan=self.store.get("mailbox-scan","main") or {"since":stamp-72*3600,"until":stamp,"page":None}
            if not scan.get("page"):scan.update(since=stamp-72*3600,until=stamp)
            page,next_page=self.service.gmail.recent_page(scan["since"],scan["until"],scan["page"])
            if scan.get("page"):
                fresh,_=self.service.gmail.recent_page(stamp-72*3600,stamp,None)
                page=fresh+page
            discovered=[]
            with self.store.lock,self.store.engine.begin() as connection:
                for mail in page:
                    key=digest(mail["messageId"])
                    if not self.store.get("mailbox-message",key,connection):
                        entry={**mail,"id":key,"status":"excluded" if mail.get("reason") else "queued","runId":None,"discoveredAt":now()}
                        self.store.put("mailbox-message",key,entry,connection)
                        discovered.append(entry)
                if next_page:scan["page"]=next_page
                else:scan={"since":stamp-72*3600,"until":stamp,"page":None}
                self.store.put("mailbox-scan","main",scan,connection)
            for entry in discovered:
                self.service.audit("mailbox.message.excluded" if entry["status"]=="excluded" else "mailbox.message.discovered","done","GET","/gmail/recent",reference=entry["id"])
            self.state.update(error=None,lastSuccess=now())
            # Synchronize already-admitted jobs before admitting another one.
            items=self.store.list("mailbox-message")
            for item in items:
                if item.get("runId"):
                    job=self.store.get("job",item["runId"])
                    item["status"]=("processing" if job["status"]=="running" else "review" if job["status"]=="review" else "error" if job["status"]=="failed" else "done") if job else "error"
                    self.store.put("mailbox-message",item["id"],item)
                    if job and job.get("error") in ("AuthenticationError","PermissionDeniedError","RateLimitError"):
                        self.state.update(paused=True,error=job["error"])
            active=any(j["status"]=="running" for j in self.store.list("job"))
            today=now()[:10]
            admitted=sum(i.get("admittedAt","")[:10]==today for i in items)
            calls=sum(j.get("calls",0) for j in self.store.list("job") if j["startedAt"][:10]==today)
            enough_calls=calls+(3 if self.service.config.economy_profile else self.service.config.max_calls)<=self.service.config.daily_call_limit
            self.state["limitReason"]=None if enough_calls and admitted<self.service.config.auto_daily_messages else "일일 호출·처리 건수 한도 · 다음 UTC 날짜에 자동 재개"
            if not active and not self.state.get("paused") and admitted<self.service.config.auto_daily_messages and enough_calls:
                queue=sorted((i for i in items if i["status"]=="queued"),key=lambda i:i["receivedAt"],reverse=True)
                for item in queue:
                    if self.stop.is_set():break
                    rid="run-"+digest("gmail-auto-v1:"+item["messageId"])[:32]
                    # Recover an admission whose response/process was lost.
                    if self.store.get("job",rid):
                        item.update(runId=rid,status="processing",admittedAt=now());self.store.put("mailbox-message",item["id"],item);break
                    try:
                        mail=self.service.gmail.read_message(item["messageId"],time.time()-72*3600)
                        if mail.get("alreadyReplied") or mail.get("superseded"):
                            item.update(status="done",reason="이미 답장한 메일" if mail.get("alreadyReplied") else "같은 스레드의 새 수신이 있어 이전 건 생략");self.store.put("mailbox-message",item["id"],item);continue
                        if mail.get("contentLimited"):
                            item.update(status="needs_review",reason="본문 없음·길이 초과 · 자동 AI 전송 생략");self.store.put("mailbox-message",item["id"],item);continue
                        if self.stop.is_set():break
                        result=self.service.start(source="gmail",custom_mail=mail,receipt="gmail-auto-v1:"+item["messageId"])
                        item.update(runId=result["id"],status="processing",admittedAt=now());self.store.put("mailbox-message",item["id"],item)
                        self.service.store.emit(result["id"],"gateway","mail.auto_admitted","done","최근 72시간 받은편지함 · 자동 처리 · 중복 검사 완료")
                        break
                    except Busy:break
                    except Exception as exc:
                        item.update(status="error",reason=type(exc).__name__);self.store.put("mailbox-message",item["id"],item);break
        except Exception as exc:
            self.state["error"]=type(exc).__name__
            if type(exc).__name__ in ("RefreshError","DefaultCredentialsError"):self.state["paused"]=True
        finally:
            self.state["running"]=False;self.persist();self.lock.release()
