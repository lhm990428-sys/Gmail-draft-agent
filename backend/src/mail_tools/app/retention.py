from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from .store import documents, events, now


def expire_artifacts(service,at=None):
    at=at or datetime.now(timezone.utc)
    cutoff=(at-timedelta(days=service.config.artifact_days)).isoformat()
    expired=[]
    with service.store.lock:
        with service.store.engine.begin() as connection:
            for item in service.store.list("mailbox-message"):
                if item.get("receivedAt",now())<cutoff:
                    connection.execute(delete(documents).where(documents.c.kind=="mailbox-message",documents.c.id==item["id"]))
        for job in service.store.list("job"):
            if job["startedAt"]>=cutoff or job.get("artifactsExpired") or job["status"]=="running":continue
            rid=job["id"]
            with service.store.engine.begin() as connection:
                rows=connection.execute(select(events.c.payload).where(events.c.run_id==rid)).scalars().all()
                for row in rows:
                    envelope=service.store.open(row)
                    ref=envelope.get("artifactRef")
                    if ref:
                        service.store.put("artifact-tombstone",ref,{"id":ref,"hash":envelope["artifactHash"],"expiredAt":at.isoformat()},connection)
                        connection.execute(delete(documents).where(documents.c.kind=="event-artifact",documents.c.id==ref))
                if job.get("mailId"):
                    connection.execute(delete(documents).where(documents.c.kind=="mail",documents.c.id==job["mailId"]))
                for draft in service.store.list("local-draft"):
                    intent=service.store.get("intent",draft["intent"])
                    if intent and intent.get("mailId")==job.get("mailId"):
                        connection.execute(delete(documents).where(documents.c.kind=="local-draft",documents.c.id==draft["id"]))
            # Checkpoint SQLite is a separate encrypted store; erase the continuation.
            with service.harness.saver.lock:
                for table in ("writes","checkpoints"):
                    # SqliteSaver's schema uses these fixed table names.
                    service.harness.connection.execute(f"DELETE FROM {table} WHERE thread_id=?",(rid,))
                service.harness.connection.commit()
            job.update(artifactsExpired=True,subject="민감 자료 보존 기간 만료",mailId=None)
            if job["status"]=="review":job.update(status="failed",decision="REVIEW_EXPIRED",error="ARTIFACT_RETENTION_EXPIRED")
            service.store.put("job",rid,job)
            service.store.emit(rid,"checkpoint","artifact.expired","done","정책에 따른 민감 artifact 삭제 · 감사 metadata 유지")
            expired.append(rid)
    return {"expired_runs":expired,"policy_days":service.config.artifact_days}
