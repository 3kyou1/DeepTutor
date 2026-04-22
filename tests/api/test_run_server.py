from __future__ import annotations

import importlib
import os


def test_run_server_uses_relative_reload_excludes(monkeypatch) -> None:
    run_server = importlib.import_module("deeptutor.api.run_server")

    captured: dict[str, object] = {}

    monkeypatch.setattr("deeptutor.services.setup.get_backend_port", lambda project_root=None: 8001)

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(run_server.uvicorn, "run", fake_run)

    run_server.main()

    reload_excludes = captured["kwargs"]["reload_excludes"]
    assert reload_excludes
    assert all(not os.path.isabs(pattern) for pattern in reload_excludes)
