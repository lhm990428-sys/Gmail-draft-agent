import socket

import pytest

from mail_tools.app.gateway import HermesGateway
from mail_tools.cli import failure_report


def test_gateway_port_conflict_reports_actionable_safe_error(monkeypatch):
    class OccupiedSocket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address):
            assert address == ("127.0.0.1", 8642)
            raise OSError(10048, "private system message")

    monkeypatch.setattr(socket, "socket", OccupiedSocket)
    with pytest.raises(RuntimeError, match="^HERMES_GATEWAY_PORT_IN_USE$") as caught:
        HermesGateway("synthetic-command-key").start()
    report = failure_report(caught.value)
    assert report["code"] == "HERMES_GATEWAY_PORT_IN_USE"
    assert "8642" in report["message"] and "Ctrl+C" in report["message"]
    assert "private system message" not in str(report)
