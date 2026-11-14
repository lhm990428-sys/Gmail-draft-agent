from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, Text, select, insert, update, event, UniqueConstraint
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from .config import digest


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


metadata = MetaData()
documents = Table("documents", metadata, Column("kind", String, primary_key=True), Column("id", String, primary_key=True), Column("payload", Text, nullable=False), Column("updated_at", String, nullable=False))
events = Table("events", metadata, Column("global_sequence", Integer, primary_key=True, autoincrement=True), Column("id", String, unique=True, nullable=False), Column("run_id", String, nullable=False, index=True), Column("sequence", Integer, nullable=False), Column("node", String, nullable=False), Column("type", String, nullable=False), Column("status", String, nullable=False), Column("at", String, nullable=False), Column("payload", Text, nullable=False), Column("previous_hash", String, nullable=False), Column("hash", String, nullable=False), UniqueConstraint("run_id", "sequence"))
outbox = Table("outbox", metadata, Column("id", String, primary_key=True), Column("run_id", String, nullable=False), Column("status", String, nullable=False), Column("attempts", Integer, nullable=False), Column("payload", Text, nullable=False), Column("next_at", String, nullable=True))
claims = Table("claims", metadata, Column("id", String, primary_key=True), Column("run_id", String, nullable=False), Column("status", String, nullable=False), Column("updated_at", String, nullable=False))


class FernetCipher:
    def __init__(self, key: bytes): self.fernet = Fernet(key)
    def encrypt(self, plaintext): return "fernet", self.fernet.encrypt(plaintext)
    def decrypt(self, ciphername, ciphertext):
        if ciphername != "fernet": raise ValueError("Unknown checkpoint cipher")
        return self.fernet.decrypt(ciphertext)


class Store:
    def __init__(self, directory: Path, key: bytes):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory, self.lock = directory, RLock()
        self.fernet = Fernet(key)
        self.serde = EncryptedSerializer(FernetCipher(key))
        self.engine = create_engine(f"sqlite:///{directory / 'operations.sqlite'}", connect_args={"check_same_thread": False, "timeout": 15})
        @event.listens_for(self.engine, "connect")
        def pragmas(dbapi, _):
            dbapi.execute("PRAGMA journal_mode=WAL")
            dbapi.execute("PRAGMA foreign_keys=ON")
            dbapi.execute("PRAGMA busy_timeout=15000")
        from alembic import command
        from alembic.config import Config
        from mail_tools.settings import ROOT
        migration=Config(str(ROOT/"backend/alembic.ini"))
        migration.set_main_option("script_location",str(ROOT/"backend/migrations"))
        with self.engine.begin() as connection:
            migration.attributes["connection"]=connection
            command.upgrade(migration,"head")

    def seal(self, value) -> str:
        return self.fernet.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()

    def open(self, value: str):
        return json.loads(self.fernet.decrypt(value.encode()))

    def get(self, kind: str, identifier: str, conn=None):
        if conn is None:
            with self.engine.connect() as connection: return self.get(kind, identifier, connection)
        value = conn.execute(select(documents.c.payload).where(documents.c.kind == kind, documents.c.id == identifier)).scalar_one_or_none()
        return self.open(value) if value is not None else None

    def list(self, kind: str) -> list:
        with self.engine.connect() as conn:
            return [self.open(value) for value in conn.execute(select(documents.c.payload).where(documents.c.kind == kind).order_by(documents.c.updated_at.desc())).scalars()]

    def put(self, kind: str, identifier: str, payload, conn=None):
        if conn is None:
            with self.lock, self.engine.begin() as connection: return self.put(kind, identifier, payload, connection)
        from sqlalchemy.dialects.sqlite import insert as upsert
        stmt = upsert(documents).values(kind=kind, id=identifier, payload=self.seal(payload), updated_at=now())
        conn.execute(stmt.on_conflict_do_update(index_elements=[documents.c.kind, documents.c.id], set_={"payload": stmt.excluded.payload, "updated_at": stmt.excluded.updated_at}))

    def emit(self, run_id: str, node: str, typ: str, status: str, summary: str, *, conn=None, **payload) -> dict:
        if conn is None:
            with self.lock,self.engine.begin() as connection:
                return self.emit(run_id,node,typ,status,summary,conn=connection,**payload)
        previous=conn.execute(select(events.c.sequence,events.c.hash).where(events.c.run_id==run_id).order_by(events.c.sequence.desc()).limit(1)).first()
        sequence,previous_hash=(previous.sequence+1,previous.hash) if previous else (1,"")
        eid,at=str(uuid4()),now()
        envelope={"id":eid,"runId":run_id,"sequence":sequence,"nodeId":node,"type":typ,"status":status,"time":at,"summary":summary}
        # Sensitive public IO/state is an expiring artifact, not immutable ledger text.
        public={k:v for k,v in payload.items() if k in ("usage","attempt","startedEventId","errorCategory")}
        sensitive={k:v for k,v in payload.items() if k not in public}
        envelope.update(public)
        if sensitive:
            envelope.update(artifactRef=eid,artifactHash=digest(sensitive))
            self.put("event-artifact",eid,sensitive,conn)
        hashed=digest({"previous":previous_hash,"event":envelope})
        conn.execute(insert(events).values(id=eid,run_id=run_id,sequence=sequence,node=node,type=typ,status=status,at=at,payload=self.seal(envelope),previous_hash=previous_hash,hash=hashed))
        projection={"id":eid,"runId":run_id,"sequence":sequence,"node":node,"type":typ,"status":status,"at":at}
        if "usage" in payload:projection["usage"]=payload["usage"]
        if "evaluation" in payload:
            value=payload["evaluation"]
            projection["evaluation"]={k:value[k] for k in ("experimentId","datasetVersion","evaluatorVersion")}
            projection["evaluation"]["rubric"]=[{"criterion":r["criterion"],"score":r["score"]} for r in value["rubric"]]
        conn.execute(insert(outbox).values(id=eid,run_id=run_id,status="pending",attempts=0,payload=self.seal(projection)))
        return {**envelope,**sensitive}

    def history(self, run_id: str, after=0) -> list:
        with self.engine.connect() as conn:
            result=[]
            for value in conn.execute(select(events.c.payload).where(events.c.run_id==run_id,events.c.sequence>after).order_by(events.c.sequence)).scalars():
                envelope=self.open(value)
                if envelope.get("artifactRef"):
                    artifact=self.get("event-artifact",envelope["artifactRef"],conn)
                    if artifact is not None:envelope.update(artifact)
                    else:envelope["artifactExpired"]=True
                result.append(envelope)
            return result

    def integrity(self, run_id: str) -> bool:
        with self.engine.connect() as conn:
            records = conn.execute(select(events).where(events.c.run_id == run_id).order_by(events.c.sequence)).mappings().all()
        previous = ""
        for index, record in enumerate(records, 1):
            if record["sequence"] != index or record["previous_hash"] != previous: return False
            if digest({"previous": previous, "event": self.open(record["payload"])}) != record["hash"]: return False
            envelope=self.open(record["payload"])
            if envelope.get("artifactRef"):
                artifact=self.get("event-artifact",envelope["artifactRef"])
                if artifact is not None and digest(artifact)!=envelope["artifactHash"]:return False
                if artifact is None and self.get("artifact-tombstone",envelope["artifactRef"]) is None:return False
            previous = record["hash"]
        return True

    def close(self): self.engine.dispose()
