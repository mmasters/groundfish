# syntax=docker/dockerfile:1

# ---- build stage: compile Stockfish (NNUE embedded) from a pinned tag ----
FROM python:3.12-slim AS sfbuild
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin the engine version. SF18 (tag sf_18) embeds the default NNUE net in the binary.
ARG SF_TAG=sf_18
# Portable instruction floor that won't SIGILL on most x86-64 hosts. Override to
# x86-64-bmi2 (faster) when the host CPU is known, or armv8 for arm64 builds.
ARG SF_ARCH=x86-64-sse41-popcnt

RUN git clone --depth 1 --branch ${SF_TAG} \
        https://github.com/official-stockfish/Stockfish.git /sf
WORKDIR /sf/src
RUN make -j"$(nproc)" net \
    && make -j"$(nproc)" profile-build ARCH=${SF_ARCH} \
    && make strip
# -> /sf/src/stockfish

# ---- runtime stage ----
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 app

COPY --from=sfbuild /sf/src/stockfish /usr/local/bin/stockfish

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY app/ ./app/

ENV STOCKFISH_ENGINE_PATH=/usr/local/bin/stockfish \
    STOCKFISH_LOG_FILE=/app/logs/groundfish.log

RUN mkdir -p /app/logs && chown -R app:app /app/logs
USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
