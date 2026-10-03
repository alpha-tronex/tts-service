"""tts-service: Wolof and Bambara speech for the Language Translator API.

    POST /speak   {"lang": "wo" | "bm", "text": "..."}  ->  audio/mpeg
    GET  /health  ->  {"status": "ok", "languages": [...]}

Only the translator API calls this, with a shared secret in X-TTS-Key.
Nothing is stored: text comes in, audio goes out, and only sizes and
timings are logged.
"""
import hmac
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Callable, Mapping

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .audio import encode_mp3, join
from .engines import Engine
from .text import MAX_TEXT_CHARS, clean, split_for_speech

log = logging.getLogger("tts-service")

CACHE_ENTRIES = 200  # a class repeats the same phrases; cached audio is instant


class SpeakRequest(BaseModel):
    lang: str
    text: str


class AudioCache:
    """Small in-memory LRU of finished MP3s. Lost on restart, never written to disk."""

    def __init__(self, capacity: int = CACHE_ENTRIES):
        self._capacity = capacity
        self._items: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str]) -> bytes | None:
        with self._lock:
            audio = self._items.get(key)
            if audio is not None:
                self._items.move_to_end(key)
            return audio

    def put(self, key: tuple[str, str], audio: bytes) -> None:
        with self._lock:
            self._items[key] = audio
            self._items.move_to_end(key)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)


def create_app(
    load: Callable[[], Mapping[str, Engine]] | None = None,
    secret: str | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """`load` and `secret` are injectable so tests run without the real models."""
    engines: dict[str, Engine] = {}
    cache = AudioCache()
    # One synthesis at a time: the models are CPU-bound and the box is shared.
    busy = threading.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if load is None:
            from .engines import load_engines

            engines.update(load_engines())
        else:
            engines.update(load())
        log.info(json.dumps({"event": "ready", "languages": sorted(engines)}))
        yield

    app = FastAPI(title="tts-service", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def shared_secret() -> str:
        return (secret if secret is not None else os.environ.get("TTS_SHARED_SECRET", "")).strip()

    def synthesize(lang: str, text: str) -> bytes:
        engine = engines[lang]
        with busy:
            chunks = [engine.synthesize(chunk) for chunk in split_for_speech(text)]
        samples = join(chunks, engine.sample_rate)
        # Digits or symbols the model has no sounds for produce no samples.
        return encode_mp3(samples, engine.sample_rate) if samples.size else b""

    @app.get("/health")
    def health():
        return {"status": "ok", "languages": sorted(engines)}

    @app.post("/speak")
    async def speak(body: SpeakRequest, x_tts_key: str | None = Header(default=None)):
        expected = shared_secret()
        if not expected:
            # Fail closed: without a configured secret nobody gets audio.
            raise HTTPException(status_code=503, detail="Service is not configured")
        if not x_tts_key or not hmac.compare_digest(x_tts_key.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Unauthorized")

        lang = body.lang.strip().lower()
        text = clean(body.text)
        if lang not in engines:
            raise HTTPException(status_code=400, detail="Unsupported language")
        if not text:
            raise HTTPException(status_code=400, detail="Missing text")
        if len(text) > MAX_TEXT_CHARS:
            raise HTTPException(status_code=413, detail="Text too long")

        started = clock()
        key = (lang, text)
        audio = cache.get(key)
        cached = audio is not None
        if audio is None:
            try:
                audio = await run_in_threadpool(synthesize, lang, text)
            except Exception:
                log.exception("synthesis failed")
                raise HTTPException(status_code=500, detail="Speech failed")
            if not audio:
                raise HTTPException(status_code=422, detail="Nothing to say")
            cache.put(key, audio)

        # Sizes and timings only: never the text.
        log.info(
            json.dumps(
                {
                    "event": "speak",
                    "lang": lang,
                    "chars": len(text),
                    "bytes": len(audio),
                    "cached": cached,
                    "ms": round((clock() - started) * 1000),
                }
            )
        )
        return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    return app


logging.basicConfig(level=logging.INFO, format="%(message)s")
app = create_app()
