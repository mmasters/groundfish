# groundfish

A small, stateless HTTP service that wraps native **Stockfish (NNUE)** and returns chess
moves over a JSON API. Point it at a Stockfish binary and it serves best-move and raw-UCI
requests from a pool of engine processes.

- **Stateless.** No database, no sessions. Configuration is via environment variables.
- **Pooled engines.** A fixed pool of Stockfish subprocesses serves requests concurrently;
  each request leases one engine (Stockfish is stateful, so engines are never shared
  mid-search). Crashed or timed-out engines are automatically replaced.
- **Two endpoints.** A typed `POST /move` and a raw, safety-capped `POST /uci`
  command-batch passthrough.
- **JSON logging.** Each engine request is written as a JSON line to a rotating log file
  for debugging and metrics.

> **Note:** this service performs no authentication. It is intended to run on a trusted
> network (e.g. behind a firewall or reverse proxy). Add your own auth/rate-limiting layer
> in front of it if exposing it more widely.

## Endpoints

| Method | Path           | Purpose                                                          |
|--------|----------------|------------------------------------------------------------------|
| GET    | `/healthz`     | Liveness.                                                        |
| GET    | `/readyz`      | Readiness (503 until ≥1 engine is live).                        |
| GET    | `/engine/info` | Engine name/authors + configured caps.                          |
| POST   | `/move`        | `{fen, skill_level?, movetime_ms?, difficulty?}` → `{bestmove}` |
| POST   | `/uci`         | `{commands: [...]}` → `{lines, bestmove, ponder}`               |

`/move` accepts either explicit `skill_level` (0–20) and `movetime_ms`, or a `difficulty`
preset (`easy`/`medium`/`hard`). Explicit fields win over the preset. `movetime_ms` and
`skill_level` are always clamped to configured bounds. Interactive API docs are at `/docs`.

The `/uci` passthrough runs an ordered list of UCI commands on a freshly-reset engine and
returns its output. It enforces hard caps so a single request can't pin a CPU forever:
`go infinite` and unbounded `go` are rewritten to a capped `movetime`, `go movetime N` is
clamped, and `quit` is rejected.

## Run with Docker (recommended)

The image compiles Stockfish from source (pinned to a release tag) so the NNUE net is
embedded and the build is reproducible.

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/readyz
```

### Choosing `SF_ARCH` (CPU target)

Stockfish is compiled for a specific CPU instruction set. The `SF_ARCH` build argument
selects that target — it's a trade-off between **portability** and **speed**. A binary
built for a newer instruction set runs faster but will crash with `SIGILL` (illegal
instruction) on a CPU that lacks those instructions.

The default is `x86-64-sse41-popcnt`, a conservative floor that runs on virtually any
x86-64 host. **For best performance, set `SF_ARCH` to the newest target your host CPU
supports.**

| `SF_ARCH` | Use when | Notes |
|---|---|---|
| `x86-64-sse41-popcnt` | Unknown / older / emulated x86-64 hosts | **Default.** Safest; slowest. |
| `x86-64-avx2` | Modern x86-64 (Intel Haswell+ / AMD Zen+) | Good speedup; widely supported on cloud VMs. |
| `x86-64-bmi2` | Recent Intel / AMD Zen 3+ | Fastest common x86 target. Crashes on Zen 1/2 and older. |
| `armv8` | ARM64 hosts (Apple Silicon, AWS Graviton, etc.) | Required for arm64 builds. |
| `apple-silicon` | Apple Silicon (M1/M2/M3…) | Tuned variant of armv8 for Apple chips. |

```bash
# example: faster x86 build on a modern server
SF_ARCH=x86-64-bmi2 docker compose up --build

# example: arm64 host (Apple Silicon, Graviton)
SF_ARCH=armv8 docker compose up --build
```

> Not sure what your CPU supports? On Linux, `cat /proc/cpuinfo | grep -o 'avx2\|bmi2'`
> shows the relevant flags. When in doubt, keep the default — a slightly slower engine is
> better than a binary that won't start. Stockfish's full list of architecture targets is
> shown by running `make help` in its `src/` directory.

## Run locally (no Docker)

Requires a `stockfish` binary on the host (e.g. `brew install stockfish`,
`apt install stockfish`, or a [release build](https://stockfishchess.org/download/)).

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
echo "STOCKFISH_ENGINE_PATH=$(which stockfish)" >> .env
uv run uvicorn app.main:app --reload
```

## Example requests

```bash
# typed move
curl -s -X POST localhost:8000/move -H 'Content-Type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","difficulty":"medium"}'
# -> {"bestmove":"e2e4"}

# explicit parameters
curl -s -X POST localhost:8000/move -H 'Content-Type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","skill_level":20,"movetime_ms":1000}'

# raw UCI passthrough
curl -s -X POST localhost:8000/uci -H 'Content-Type: application/json' \
  -d '{"commands":["position fen rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","go movetime 600"]}'
# -> {"lines":[...],"bestmove":"e2e4","ponder":"e7e5"}
```

## Tests

```bash
uv run pytest -m "not integration"   # unit suite (no engine needed)
uv run pytest -m integration         # real-engine suite (needs a stockfish binary)
uv run pytest                        # everything
```

## Configuration

All settings are environment variables prefixed `STOCKFISH_` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `STOCKFISH_ENGINE_PATH` | `/usr/local/bin/stockfish` | Path to the Stockfish binary |
| `STOCKFISH_ENGINE_POOL_SIZE` | `min(cpu, 4)` | Number of engine subprocesses |
| `STOCKFISH_ENGINE_HASH_MB` | `64` | Per-engine UCI Hash size |
| `STOCKFISH_DEFAULT_MOVETIME_MS` | `600` | Default search time |
| `STOCKFISH_MIN_MOVETIME_MS` / `STOCKFISH_MAX_MOVETIME_MS` | `50` / `2000` | Movetime clamp bounds |
| `STOCKFISH_POOL_ACQUIRE_TIMEOUT_S` | `5.0` | Max wait for a free engine before 503 |
| `STOCKFISH_LOG_FILE` | `./logs/groundfish.log` | Rotating JSON request log |
| `STOCKFISH_LOG_LEVEL` | `INFO` | Log level |

## License

This project bundles and runs [Stockfish](https://github.com/official-stockfish/Stockfish),
which is licensed under the **GNU General Public License v3**. As a result this project is
also distributed under the **GPLv3** — see [`LICENSE`](LICENSE). If you distribute this
server you must make the corresponding source available under the same license.
