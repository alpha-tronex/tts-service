import json
import logging

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import AudioCache, create_app
from app.text import MAX_TEXT_CHARS

SECRET = "test-secret"
AUTH = {"X-TTS-Key": SECRET}


class FakeEngine:
    sample_rate = 16000

    def __init__(self):
        self.calls: list[str] = []
        self.error: Exception | None = None
        self.silent = False

    def synthesize(self, text: str) -> np.ndarray:
        self.calls.append(text)
        if self.error:
            raise self.error
        if self.silent:
            return np.zeros(0, dtype=np.float32)
        return np.sin(np.linspace(0, 440, 4000)).astype(np.float32)


@pytest.fixture
def engines():
    return {"wo": FakeEngine(), "bm": FakeEngine()}


@pytest.fixture
def client(engines):
    with TestClient(create_app(load=lambda: engines, secret=SECRET)) as c:
        yield c


def test_health_lists_the_loaded_languages_without_a_key(client):
    res = client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "languages": ["bm", "wo"]}


def test_speaks_wolof_as_mp3(client, engines):
    res = client.post("/speak", json={"lang": "wo", "text": "Na nga def?"}, headers=AUTH)

    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.headers["cache-control"] == "no-store"
    assert res.content[0] == 0xFF
    assert engines["wo"].calls == ["Na nga def?"]
    assert engines["bm"].calls == []


def test_routes_bambara_to_the_bambara_model(client, engines):
    res = client.post("/speak", json={"lang": " BM ", "text": "I ni ce"}, headers=AUTH)

    assert res.status_code == 200
    assert engines["bm"].calls == ["I ni ce"]


def test_long_text_is_spoken_sentence_by_sentence(client, engines):
    client.post("/speak", json={"lang": "bm", "text": "I ni ce. I ka kɛnɛ wa?"}, headers=AUTH)

    assert engines["bm"].calls == ["I ni ce.", "I ka kɛnɛ wa?"]


@pytest.mark.parametrize("headers", [{}, {"X-TTS-Key": "wrong"}, {"X-TTS-Key": ""}])
def test_rejects_a_missing_or_wrong_key_before_touching_a_model(client, engines, headers):
    res = client.post("/speak", json={"lang": "wo", "text": "Na nga def?"}, headers=headers)

    assert res.status_code == 401
    assert engines["wo"].calls == []


def test_with_no_secret_configured_nobody_gets_audio(engines):
    with TestClient(create_app(load=lambda: engines, secret="")) as c:
        res = c.post("/speak", json={"lang": "wo", "text": "Na nga def?"}, headers={"X-TTS-Key": ""})

    assert res.status_code == 503
    assert engines["wo"].calls == []


def test_reads_the_secret_from_the_environment(engines, monkeypatch):
    monkeypatch.setenv("TTS_SHARED_SECRET", "from-env")
    with TestClient(create_app(load=lambda: engines)) as c:
        assert c.post("/speak", json={"lang": "wo", "text": "x"}, headers={"X-TTS-Key": "from-env"}).status_code == 200
        assert c.post("/speak", json={"lang": "wo", "text": "x"}, headers=AUTH).status_code == 401


def test_rejects_other_languages(client):
    res = client.post("/speak", json={"lang": "fr", "text": "Bonjour"}, headers=AUTH)

    assert res.status_code == 400
    assert res.json() == {"detail": "Unsupported language"}


@pytest.mark.parametrize("text", ["", "   \n "])
def test_rejects_blank_text(client, text):
    assert client.post("/speak", json={"lang": "wo", "text": text}, headers=AUTH).status_code == 400


def test_rejects_a_body_without_the_fields(client):
    assert client.post("/speak", json={"lang": "wo"}, headers=AUTH).status_code == 422


def test_caps_text_at_1000_characters(client, engines):
    ok = client.post("/speak", json={"lang": "bm", "text": "a" * MAX_TEXT_CHARS}, headers=AUTH)
    too_long = client.post("/speak", json={"lang": "bm", "text": "a" * (MAX_TEXT_CHARS + 1)}, headers=AUTH)

    assert ok.status_code == 200
    assert too_long.status_code == 413


def test_a_repeated_phrase_comes_from_the_cache(client, engines):
    first = client.post("/speak", json={"lang": "wo", "text": "Jërëjëf"}, headers=AUTH)
    second = client.post("/speak", json={"lang": "wo", "text": "  Jërëjëf "}, headers=AUTH)

    assert second.content == first.content
    assert engines["wo"].calls == ["Jërëjëf"]


def test_the_cache_is_per_language(client, engines):
    client.post("/speak", json={"lang": "wo", "text": "Baba"}, headers=AUTH)
    client.post("/speak", json={"lang": "bm", "text": "Baba"}, headers=AUTH)

    assert engines["wo"].calls == ["Baba"]
    assert engines["bm"].calls == ["Baba"]


def test_a_model_failure_is_a_plain_500_and_is_not_cached(client, engines):
    engines["wo"].error = RuntimeError("out of memory")
    assert client.post("/speak", json={"lang": "wo", "text": "Na nga def?"}, headers=AUTH).status_code == 500

    engines["wo"].error = None
    res = client.post("/speak", json={"lang": "wo", "text": "Na nga def?"}, headers=AUTH)

    assert res.status_code == 200
    assert len(engines["wo"].calls) == 2


def test_text_the_model_cannot_say_is_reported_not_returned_as_empty_audio(client, engines):
    engines["bm"].silent = True

    res = client.post("/speak", json={"lang": "bm", "text": "12345"}, headers=AUTH)

    assert res.status_code == 422


def test_logs_sizes_and_timings_but_never_the_text(client, caplog):
    with caplog.at_level(logging.INFO, logger="tts-service"):
        client.post("/speak", json={"lang": "wo", "text": "sama mbóot"}, headers=AUTH)

    lines = [json.loads(r.getMessage()) for r in caplog.records if '"speak"' in r.getMessage()]
    assert lines[-1]["lang"] == "wo"
    assert lines[-1]["chars"] == 10
    assert lines[-1]["cached"] is False
    assert "sama" not in caplog.text


def test_the_api_docs_pages_are_not_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cache_drops_the_least_recently_used_entry():
    cache = AudioCache(capacity=2)
    cache.put(("wo", "a"), b"1")
    cache.put(("wo", "b"), b"2")
    cache.get(("wo", "a"))
    cache.put(("wo", "c"), b"3")

    assert cache.get(("wo", "b")) is None
    assert cache.get(("wo", "a")) == b"1"
    assert cache.get(("wo", "c")) == b"3"
