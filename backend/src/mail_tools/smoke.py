"""Synthetic SDK compatibility check, with tracing forcibly disabled."""
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from sqlalchemy import create_engine, text


class ProbeState(TypedDict):
    marker: str
    approved: bool


def build_graph(checkpointer):
    def review(state: ProbeState):
        answer = interrupt({"kind": "synthetic-setup-check", "marker": state["marker"]})
        return {"approved": answer is True}

    graph = StateGraph(ProbeState)
    graph.add_node("synthetic_review", review)
    graph.add_edge(START, "synthetic_review")
    graph.add_edge("synthetic_review", END)
    return graph.compile(checkpointer=checkpointer)


def offline_smoke() -> dict:
    with TemporaryDirectory(prefix="hermes-setup-") as directory, tracing_context(enabled=False):
        checkpoint = str(Path(directory) / "checkpoint.sqlite")
        config = {"configurable": {"thread_id": str(uuid4())}}
        with SqliteSaver.from_conn_string(checkpoint) as saver:
            graph = build_graph(saver)
            result = graph.invoke({"marker": "synthetic-only", "approved": False}, config)
            assert result.get("__interrupt__"), "Graph did not interrupt"
            assert graph.get_state(config).next == ("synthetic_review",)
        # Re-open the actual SQLite file and reconstruct graph, not MemorySaver.
        with SqliteSaver.from_conn_string(checkpoint) as saver:
            graph = build_graph(saver)
            assert graph.get_state(config).values["approved"] is False
            resumed = graph.invoke(Command(resume=True), config)
            assert resumed["approved"] is True
            assert not graph.get_state(config).next
        engine = create_engine(f"sqlite:///{Path(directory) / 'ledger-probe.sqlite'}")
        with engine.begin() as conn:
            mode = conn.execute(text("PRAGMA journal_mode=WAL")).scalar()
            assert mode == "wal"
            conn.execute(text("CREATE TABLE setup_probe (id TEXT PRIMARY KEY)"))
            conn.execute(text("INSERT INTO setup_probe VALUES ('synthetic')"))
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM setup_probe")).scalar() == 1
        engine.dispose()
    return {"status": "pass", "source": "synthetic", "checks": [
        "LangGraph compile/invoke", "interrupt", "SQLite close/reopen resume",
        "SQLAlchemy WAL transaction", "outbound tracing disabled",
    ], "business_harness": "not_built"}
