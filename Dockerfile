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

ENV PORT=7860 SOCAREGUARD_SANDBOX=1 SOCAREGUARD_MAX_REQUESTS_PER_HOUR=20
EXPOSE 7860
CMD ["sh", "-c", "python -m socareguard.proxy --host 0.0.0.0 --port ${PORT}"]
