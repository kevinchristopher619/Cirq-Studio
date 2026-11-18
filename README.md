# Cirq-Studio ⚛️

**Cirq-Studio** is a full-stack, hardware-aware quantum circuit composer and asynchronous simulation platform. Built around Google's [Cirq](https://quantumai.google/cirq) framework and [`qsimcirq`](https://github.com/quantumlib/qsim) (with GPU acceleration via cuQuantum), Cirq-Studio offers an intuitive drag-and-drop web UI, high-performance asynchronous simulation backend, real-time 3D state visualization, hardware transpilation, and noise modeling.

---

## 🌟 Key Features & Abilities

### 🎨 Visual Circuit Composer (Frontend)
- **Interactive Drag-and-Drop Canvas**: Easily compose multi-qubit quantum circuits with Pauli ($X, Y, Z$), Hadamard ($H$), Phase ($S, T$), Multi-Qubit ($CNOT$, $CZ$, $SWAP$, $Toffoli$), Parametric ($RX, RY, RZ$), Native Google Hardware ($PhasedXZ$, $XPow$, $FSim$), and classical operations (Measurement, Reset).
- **Dual Workspace Modes**:
  - **Normal Mode**: Clean, beginner-friendly workspace with linear qubit lines and standard quantum gate sets.
  - **Research Mode**: Hardware-focused workspace supporting 2D grid/line topologies, native hardware gatesets (Google Sycamore, IonQ), coupling constraint enforcement, and custom noise models.
- **Real-Time 3D Q-Sphere Visualization**: Interactive 3D sphere powered by Three.js to inspect multi-qubit state vectors, phase angles, and state amplitudes.
- **Histogram & Measurement Analysis**: Real-time rendering of measurement outcome probability distributions across configurable shot counts (repetitions).
- **Coupling Map & Constraint Checking**: Visual topology view highlighting qubit connectivity and flagging gate coupling violations on hardware grid layouts.
- **Cirq Python Code Exporter**: Auto-generates clean, executable Python Cirq code matching the visual canvas state in real time.
- **Transpilation Preview**: Side-by-side compilation preview showing how generic circuits decompose onto target hardware gatesets.

### ⚡ High-Performance Quantum Engine (Backend)
- **Cirq + `qsimcirq` Integration**: Uses `qsimcirq` for high-speed state-vector and shot-based quantum simulation, supporting GPU acceleration with NVIDIA cuQuantum.
- **Hardware Transpilation**: Target-specific transpilation pipelines (Google Sycamore, IonQ, linear topologies) with built-in LRU caching for compiled circuits.
- **Noise Simulation**: Realistic noise modeling including Thermal Relaxation and Depolarizing noise channels with adjustable error rates.
- **State-Vector Extraction**: Full state-vector computation for up to 12 qubits returned as normalized complex float arrays.

### 🛡️ Scalable Go Gateway & Task Queue
- **Asynchronous Execution Pipeline**: Uses **Redis** and **Asynq** background task queues to process simulation workloads asynchronously without blocking client requests.
- **Firebase & Cloud Firestore Persistence**: Authenticates requests via Firebase Auth and persists job metadata and execution results in Cloud Firestore.
- **Automated Lifecycle & Garbage Collection**: Built-in background garbage collector automatically cleans up expired job records after 24 hours.
- **Development Fallback Mode**: Graceful fallback (`ENV=development`) allowing local development without live Firebase credentials.

---

## 🏗️ System Architecture

Cirq-Studio is built as a three-tier system:

```
┌─────────────────────────────────────────────────────────┐
│              SvelteKit 5 Frontend (Port 5173)           │
│    Drag-and-Drop Canvas | 3D Q-Sphere | Code Exporter    │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP / REST
                             ▼
┌─────────────────────────────────────────────────────────┐
│               Go API Gateway (Port 8080)                │
│    Gin Router | Firebase Auth & Firestore | Asynq Queue  │
└──────────────┬───────────────────────────▲──────────────┘
               │ Dispatch Job              │ Store Result
               ▼                           │
┌─────────────────────────────┐   ┌────────┴──────────────┐
│     Redis Queue (Port 6379) │   │ Cloud Firestore (DB) │
└──────────────┬──────────────┘   └───────────────────────┘
               │ Asynq Worker
               ▼
┌─────────────────────────────────────────────────────────┐
│           Python Quantum Engine (Port 5001)             │
│    FastAPI | Cirq | qsimcirq (cuQuantum GPU)            │
└─────────────────────────────────────────────────────────┘
```

### Request Flow
1. **Client** submits circuit JSON to Gateway (`POST /api/jobs`).
2. **Gateway** writes job record (`status: QUEUED`) to Firestore, pushes task to **Redis/Asynq**, and immediately returns a `202 Accepted` response with `job_id`.
3. **Asynq Worker** in the Gateway picks up the job, updates status to `RUNNING`, and sends a synchronous payload to the **Python Engine** (`POST /run`).
4. **Python Engine** transpiles, simulates (with noise/shots/statevector), and returns the results.
5. **Worker** updates status to `COMPLETED` and saves results in Firestore.
6. **Client** polls `GET /api/jobs/:id` until simulation results are ready.

---

## 🛠️ Tech Stack

- **Frontend**: SvelteKit 5 (Runes), TypeScript, Vite, Three.js, Lucide Icons
- **API Gateway**: Go (1.21+), Gin Web Framework, Asynq (Redis queue), Firebase Admin SDK
- **Quantum Engine**: Python 3.11, FastAPI, Pydantic, Google Cirq, `qsimcirq` (cuQuantum)
- **Infrastructure & Orchestration**: Docker, Docker Compose, Redis, Google Cloud Firestore

---

## 📁 Repository Structure

```
Cirq-Studio/
├── docker-compose.yml           # Unified multi-container orchestrator
├── CLAUDE.md                    # Developer & architecture guide
├── frontend/                    # SvelteKit 5 Web Application
│   ├── src/
│   │   ├── routes/+page.svelte  # Single-page visual circuit composer
│   │   └── app.html
│   ├── package.json
│   └── Dockerfile
└── google_composer/             # Backend Services
    ├── server.py                # FastAPI Python Quantum Simulation Engine
    ├── Dockerfile               # Engine Dockerfile
    ├── environment_3.11.yml     # Conda environment definition
    ├── test_engine_run.py       # Engine integration test
    ├── test_gateway_pipeline.py # End-to-end pipeline test
    └── go-gateway/              # Go API Gateway & Worker
        ├── main.go              # Entry point & Gin routing
        ├── models/              # Job models & request schemas
        ├── worker/              # Asynq queue worker task definitions
        └── Dockerfile           # Gateway Dockerfile
```

---

## 🚀 Getting Started

### Option 1: Quickstart with Docker Compose (Recommended)

Run the full stack (Redis, Quantum Engine, Go Gateway, Frontend) with a single command:

```bash
docker-compose up --build
```

- **Frontend**: [http://localhost:5173](http://localhost:5173)
- **Go Gateway**: [http://localhost:8080](http://localhost:8080)
- **Python Engine**: [http://localhost:5001](http://localhost:5001)

---

### Option 2: Local Per-Tier Development

#### 1. Redis
Start a local Redis instance:
```bash
cd google_composer/go-gateway
docker-compose up -d redis
```

#### 2. Python Quantum Engine
Set up the Conda environment and launch the FastAPI server:
```bash
# Create and activate environment
conda env create -f google_composer/environment_3.11.yml
conda activate quantum-env

# Start server
cd google_composer
python server.py
```
*(Serves on `http://127.0.0.1:5001`)*

#### 3. Go API Gateway
Run the gateway in development mode (bypasses Firebase auth requirements):
```bash
cd google_composer/go-gateway
ENV=development go run .
```
*(Serves on `http://127.0.0.1:8080`)*

#### 4. SvelteKit Frontend
Install dependencies and launch Vite development server:
```bash
cd frontend
npm install
npm run dev
```
*(Serves on `http://localhost:5173`)*

---

## ⚙️ Environment Variables

| Variable | Tier | Description | Default |
| :--- | :--- | :--- | :--- |
| `PORT` | Gateway / Engine | HTTP server port | `8080` / `5001` |
| `API_HOST` | Engine | Host bind address for Python engine | `127.0.0.1` |
| `REDIS_ADDR` | Gateway | Redis connection address for Asynq | `localhost:6379` |
| `ENGINE_URL` | Gateway Worker | Endpoint URL of the Python engine `/run` API | `http://localhost:5001/run` |
| `ENV` | Gateway | Set to `development` to bypass Firebase auth | - |
| `FIREBASE_CREDENTIALS` | Gateway | Path to Firebase service account JSON key | Uses ADC if unset |

---

## 🧪 Testing & Verification

Integration test scripts are included in `google_composer/`:

- **Test Python Engine directly**:
  ```bash
  python google_composer/test_engine_run.py
  ```
- **Test Full Gateway Pipeline end-to-end**:
  ```bash
  python google_composer/test_gateway_pipeline.py
  ```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
