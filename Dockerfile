FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

WORKDIR /srv

# CPU-only torch: the default wheel bundles ~2 GB of GPU libraries this box can't use.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt requirements-models.txt ./
RUN pip install -r requirements.txt -r requirements-models.txt

COPY app ./app

RUN useradd --create-home --uid 10001 tts && mkdir -p /models && chown tts:tts /models
USER tts

EXPOSE 8000
# One worker: each worker would load its own copy of both models.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
