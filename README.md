# tts-service

Wolof and Bambara speech for the Language Translator. OpenAI's voices don't cover these two languages, so the translator API (on Vercel) sends the translated text here and gets an MP3 back.

```
phone → Vercel API (/api/translate, /api/speak) → tts-service on Hetzner → MP3
```

Only the API calls this service. Phones never talk to it directly.

## API

| Route | Body | Returns |
|---|---|---|
| `POST /speak` | JSON `{ "lang": "wo" \| "bm", "text": "…" }`, up to 1,000 characters, header `X-TTS-Key` | `audio/mpeg` |
| `GET /health` | none | `{ "status": "ok", "languages": ["bm", "wo"] }` |

Errors: `401` wrong or missing key, `400` unsupported language or blank text, `413` text too long, `422` nothing sayable (for example only digits), `500` model failure, `503` no secret configured.

Text is never stored or logged. Each request logs one JSON line with the language, character count, audio size, time taken and whether it came from the in-memory cache.

## Models

| Language | Model | Type | Licence |
|---|---|---|---|
| Wolof (`wo`) | [`bilalfaye/speecht5_tts-wolof-v0.2`](https://huggingface.co/bilalfaye/speecht5_tts-wolof-v0.2) | SpeechT5 + HiFi-GAN vocoder | MIT |
| Bambara (`bm`) | [`facebook/mms-tts-bam`](https://huggingface.co/facebook/mms-tts-bam) | VITS (Meta MMS) | CC-BY-NC 4.0 |

Both run on CPU and output 16 kHz mono. They were chosen in v2 Week 9 because they are small enough for the shared server; the better-sounding candidates (Adia TTS and Oolel Voices for Wolof, MALIBA-AI for Bambara) are 0.5–0.9 billion parameters and need a GPU to answer in reasonable time.

**Licence note:** the Bambara model is non-commercial (CC-BY-NC). That fits a free app with no ads. If the app ever charges or shows ads, replace it first (the commercial option is Djelia).

`TTS_MODEL_WO` and `TTS_MODEL_BM` swap in another checkpoint of the same family without a code change.

## Run the tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use a fake voice engine, so they need neither the models nor PyTorch. They cover the web layer, text splitting and MP3 encoding. They do not prove the real models load or sound right: check that with the `curl` commands in [DEPLOY.md](DEPLOY.md) after the first deploy.

## Layout

- `app/main.py`: FastAPI app, shared-secret check, limits, cache, logging.
- `app/engines.py`: loads the two models (imports PyTorch lazily).
- `app/text.py`: cleans text and splits it into sentences.
- `app/audio.py`: joins sentence audio and encodes MP3.
- `deploy/`: nginx vhost.
- `DEPLOY.md`: the Hetzner runbook.
