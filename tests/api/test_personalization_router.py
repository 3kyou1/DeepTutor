from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
router = importlib.import_module("deeptutor.api.routers.personalization").router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/personalization")
    return app


def test_list_cold_start_questions(monkeypatch) -> None:
    class FakeService:
        def list_cold_start_questions(self, language="zh"):
            return {
                "questions": [{"id": "CT_1", "factor": "CT", "order": 1, "prompt": "问题 1"}],
                "scale": [{"value": 1, "label": "非常不同意"}],
                "question_count": 12,
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_cold_start_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/personalization/cold-start/questions?language=zh")

    assert response.status_code == 200
    assert response.json()["questions"][0]["id"] == "CT_1"


def test_get_cold_start_status(monkeypatch) -> None:
    class FakeService:
        def get_cold_start_status(self):
            return {"profile_source": "cold_start", "completed": True}

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_cold_start_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/personalization/cold-start/status")

    assert response.status_code == 200
    assert response.json()["profile_source"] == "cold_start"


def test_submit_cold_start_answers(monkeypatch) -> None:
    class FakeService:
        async def submit_cold_start_answers(self, answers, language="zh"):
            return {
                "profile_source": "cold_start",
                "profile_updated": True,
                "profile_preview": "## CoPA Factors",
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_cold_start_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/cold-start/submit",
            json={"language": "zh", "answers": {"CT_1": 4}},
        )

    assert response.status_code == 200
    assert response.json()["profile_source"] == "cold_start"


def test_get_scientist_resonance(monkeypatch) -> None:
    class FakeService:
        async def get_resonance(self, language="zh"):
            return {
                "long_term": {"slug": "ramanujan", "name": "Srinivasa Ramanujan"},
                "recent_state": None,
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_scientist_resonance_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/personalization/scientist-resonance?language=zh")

    assert response.status_code == 200
    assert response.json()["long_term"]["slug"] == "ramanujan"


def test_regenerate_scientist_resonance(monkeypatch) -> None:
    class FakeService:
        async def regenerate(self, language="zh", mode="both"):
            assert mode == "recent_state"
            return {
                "long_term": {"slug": "turing", "name": "Alan Turing"},
                "recent_state": {"slug": "feynman", "name": "Richard Feynman"},
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_scientist_resonance_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/scientist-resonance/regenerate",
            json={"language": "zh", "mode": "recent_state"},
        )

    assert response.status_code == 200
    assert response.json()["recent_state"]["slug"] == "feynman"
