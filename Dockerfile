# Single-container image for the synthetic-data sandbox (Hugging Face Spaces, Docker SDK) and
# for `docker compose up` on an agency server. CPU only.
FROM python:3.12-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 HF_HOME=/app/.cache/hf

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY policy-packs/ ./policy-packs/
COPY demo/sample-inputs/ ./demo/sample-inputs/

RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -e ".[detect]" gliner2 peft \
 && python -m spacy download en_core_web_lg

# Warm the model caches into the image so the first request downloads nothing.
RUN python -c "from socareguard.detect import backends; backends._presidio(); backends._gliner()"

# Runtime state (vault, key, ledger) lives under /app/vault; mount a volume on a real server.
RUN mkdir -p /app/vault /app/.cache && useradd -m app && chown -R app /app
USER app

ENV PORT=7860 SOCAREGUARD_SANDBOX=1 SOCAREGUARD_MAX_REQUESTS_PER_HOUR=20 SOCAREGUARD_TRUST_PROXY=1 SOCAREGUARD_RETENTION_HOURS=24
EXPOSE 7860
# /healthz answers without a key; the image has no curl, so Python makes the request.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '7860'), timeout=4)" || exit 1
CMD ["sh", "-c", "python -m socareguard.proxy --host 0.0.0.0 --port ${PORT}"]
