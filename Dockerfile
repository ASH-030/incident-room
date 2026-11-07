FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/pip \
    uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file /tmp/requirements.lock.txt \
    && pip install --require-hashes --timeout 30 --retries 2 -r /tmp/requirements.lock.txt
COPY backend ./backend
ENV PYTHONPATH=/app/backend
RUN useradd --uid 10001 --create-home incident && mkdir /app/runtime && chown incident:incident /app/runtime
USER incident
RUN git config --global --add safe.directory /workspace/retail-warehouse
EXPOSE 8400
CMD ["uvicorn", "incident_room.app:app", "--host", "0.0.0.0", "--port", "8400", "--workers", "1"]
