# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Cirq-Studio is a three-tier system for submitting and simulating quantum circuits. The tiers are independent processes that communicate over HTTP and a Redis queue:

1. **Frontend** (`frontend/`) — SvelteKit 5 (runes mode) + TypeScript + Vite. A single-page quantum circuit composer living almost entirely in `src/routes/+page.svelte` (~3200 lines): drag-and-drop gate palette, Normal vs. Research workspace modes, a Three.js Q-sphere, histogram/state-vector views, and a Cirq-code exporter. It builds the Cirq JSON itself (see below) and talks to the gateway at a hardcoded `http://localhost:8080`.

2. **Go Gateway** (`google_composer/go-gateway/`) — Gin HTTP API on port `8080`. It is the public entry point: it authenticates users (Firebase), persists job records (Firestore), and dispatches simulation work asynchronously (Asynq over Redis). It never runs a simulation itself.

3. **Python Quantum Engine** (`google_composer/server.py`) — FastAPI on port `5001`, wrapping Cirq + `qsimcirq` (GPU via cuQuantum). Exposes a single **synchronous** `POST /run` endpoint. This is the only tier that touches quantum libraries.

### Request lifecycle (the key flow to understand)

```
Client → POST /api/jobs (Gateway)
       → Gateway writes JobRecord{status:QUEUED} to Firestore, enqueues Asynq task to Redis, returns job_id (202)
Asynq worker (in-process in the Gateway) picks up task
       → sets status:RUNNING → POST /run to Python engine → gets histogram/state_vector
       → writes status:COMPLETED + result back to Firestore
Client → GET /api/jobs/:id (Gateway) polls until COMPLETED / FAILED
```

The full request payload is embedded in the Asynq task (`SimulationJobPayload`) so the worker does not re-read Firestore. Job records carry a 24h `ExpiresAt`; a background garbage collector in `main.go` deletes expired jobs hourly. The gateway also exposes `GET /health` (unauthenticated — the frontend's "Gateway: online/offline" indicator polls it) and `GET /api/gc` (triggers garbage collection on demand).

### Contract between tiers

The gateway's `models.JobRequest` (Go) and the engine's `RunRequest` (Pydantic) **must stay field-compatible** — the worker marshals `JobRequest` straight into the engine's request body. When adding a request field, change both `google_composer/go-gateway/models/job.go` and `google_composer/server.py` together.

`target` selects a transpilation gateset in the engine: `generic` is a passthrough (no transpilation), while `sycamore`, `ionq`, and `linear` map through `GATESET_MAP` (note `ionq` and `linear` currently resolve to the same `CZTargetGateset`). Circuits are passed as Cirq JSON strings. Transpiled circuits are LRU-cached by `(circuit_json, target)`; the engine always `.copy()`s before mutating to stay thread-safe under the global GPU simulator. State-vector return is capped at 12 qubits and is serialized as a flat `[real, imag, real, imag, …]` float array.

The **frontend never calls `cirq.to_json`** — `compileStateToCirqJson()` in `+page.svelte` hand-builds the Cirq JSON (`cirq_type` objects for each gate) directly from the drag-and-drop board state, and the Cirq-code exporter is a separate string builder for display only. The frontend only ever sends `target: 'generic'` or `'sycamore'`. Editing the board auto-submits a job (300ms debounce → `autoRunSimulation` → silent poll); the **Run Circuit** button is the explicit path (`runPipelineManual` → `pollJobStatus`). If you change gate serialization, this function is the source of truth on the client side.

## Development

### Whole stack via Docker
The root `docker-compose.yml` builds and runs all four tiers (redis, engine, gateway, frontend) together:
```bash
docker-compose up --build      # engine :5001, gateway :8080, frontend :5173, redis :6379
```
It runs the gateway with `ENV=development`, so the same dev-mode Firestore caveat below applies (polling `GET /api/jobs/:id` returns 503 unless real credentials are wired in). The engine image has no GPU, so it falls back to CPU simulation. Use this for a quick end-to-end spin-up; use the per-tier flow below for active development.

### Per-tier (local)
Run each tier in its own terminal. Start Redis and the Python engine before the gateway.

### Python engine
```bash
conda env create -f google_composer/environment_3.11.yml   # creates 'quantum-env' (needs CUDA/cuQuantum)
conda activate quantum-env
cd google_composer && python server.py                      # serves on 127.0.0.1:5001
```
`environment_3.11.yml` is the maintained env file (`environment11.yml` is an older unordered duplicate of the same deps — prefer the `_3.11` one).

### Go gateway
```bash
cd google_composer/go-gateway
docker-compose up -d redis    # Redis on :6379, required by Asynq
go run .                       # serves on :8080  (or: go build -o quantum-gateway.exe .)
```
Set `ENV=development` to bypass Firebase entirely — auth is skipped (userID becomes `local_test_user`) and Firestore init failures are tolerated. **Note:** in dev mode without Firestore, job submission succeeds but `GET /api/jobs/:id` returns 503, so polling won't work; run with real `FIREBASE_CREDENTIALS` to exercise the full pipeline.

### Frontend
```bash
cd frontend
npm install
npm run dev        # Vite dev server
npm run build
npm run check      # svelte-check type checking
```

### Tests
There is no unit-test suite — the two `test_*.py` files are **integration scripts against running servers** (plain `python`, not pytest):
- `python google_composer/test_engine_run.py` — hits the engine's `/run` directly (engine must be up). Covers all four targets + noisy sim.
- `python google_composer/test_gateway_pipeline.py` — submits through the gateway and polls to completion (full stack must be up).

## Environment variables

| Var | Tier | Purpose | Default |
|-----|------|---------|---------|
| `PORT` | gateway / engine | listen port | `8080` / `5001` |
| `API_HOST` | engine | bind host | `127.0.0.1` |
| `REDIS_ADDR` | gateway | Asynq broker | `localhost:6379` |
| `ENGINE_URL` | gateway worker | Python engine `/run` URL | `http://localhost:5001/run` |
| `ENV` | gateway | `development` bypasses Firebase auth/Firestore | — |
| `FIREBASE_CREDENTIALS` | gateway | path to service-account JSON | ADC if unset |

`go-gateway/firebase-service-account.json` is gitignored (see `.aiexclude`) — never commit credentials.

## Repository Rules

### 0. Create Reference Files

**Don't assume past completed work and errors**

After each task / session:

- Update MEMORY.md with the tasks completed
- Update ERRORS.md current errors faced and where to find them.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
