FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system onramp \
    && adduser --system --ingroup onramp --home /app onramp

COPY --chown=onramp:onramp pyproject.toml ./
COPY --chown=onramp:onramp app ./app
COPY --chown=onramp:onramp alembic ./alembic
COPY --chown=onramp:onramp alembic.ini ./

RUN pip install --upgrade pip \
    && pip install ".[s3]"

USER onramp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3).read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

