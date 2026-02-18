import logging
import uvicorn
import hashlib
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse  # OPTIMIZATION 2: Faster JSON
from pydantic import BaseModel, Field
from typing import Optional

import cirq
import cirq_google
import qsimcirq

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QuantumEngine")

# OPTIMIZATION 2: Use ORJSONResponse by default for all endpoints
app = FastAPI(default_response_class=ORJSONResponse)

# --- HARDWARE SETUP ---
try:
    SYCAMORE_QUBITS = cirq_google.Sycamore.metadata.qubit_set
except AttributeError:
    SYCAMORE_QUBITS = set(cirq_google.Sycamore.qubits)

GATESET_MAP = {
    "sycamore": cirq_google.SycamoreTargetGateset(),
    "ionq": cirq.CZTargetGateset(allow_partial_czs=True),
    "linear": cirq.CZTargetGateset(allow_partial_czs=True),
}

# --- PYDANTIC MODELS ---
class NoiseConfig(BaseModel):
    type: str = "depolarizing"
    p: float = 0.001
    readout_p: float = 0.0

class RunRequest(BaseModel):
    circuit: str
    target: str = "generic"
    simulation_type: str = "perfect"
    noise_config: Optional[NoiseConfig] = None
    repetitions: int = 1000

# --- CORE LOGIC ---

# OPTIMIZATION 1: Caching Transpilation
# We cannot cache 'cirq.Circuit' objects directly, so we cache based on the
# unique hash of the JSON string and the target name.
@lru_cache(maxsize=1024)
def get_cached_transpiled_circuit(circuit_json: str, target_name: str) -> cirq.Circuit:
    """
    Deserializes and transpiles. 
    If this exact JSON + Target combo was seen before, returns result instantly.
    """
    # 1. Deserialize
    circuit = cirq.read_json(json_text=circuit_json)
    
    # 2. Transpile
    if target_name == "generic":
        return circuit

    gateset = GATESET_MAP.get(target_name)
    if not gateset:
        raise ValueError(f"Unknown target: {target_name}")

    logger.info(f"Transpiling (Cache Miss) -> {target_name}")
    return cirq.optimize_for_target_gateset(circuit, gateset=gateset)


def apply_noise(circuit: cirq.Circuit, noise_config: NoiseConfig) -> cirq.Circuit:
    if not noise_config: return circuit
    # Noise is fast enough that caching is rarely worth the memory trade-off
    if noise_config.type == 'depolarizing':
        circuit = circuit.with_noise(cirq.depolarize(noise_config.p))
    if noise_config.readout_p > 0:
        circuit = circuit.with_noise(cirq.bit_flip(noise_config.readout_p))
    return circuit

# --- ENDPOINT ---
@app.post("/run")
def run_circuit(payload: RunRequest):
    try:
        # STEP A: Get Transpiled Circuit (Cached)
        # We pass the raw JSON string to the cache function
        try:
            exec_circuit = get_cached_transpiled_circuit(payload.circuit, payload.target)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # STEP B: Apply Noise (Physics)
        # We must copy here because 'exec_circuit' might come from the Cache,
        # and we don't want to modify the cached version with noise!
        if payload.simulation_type == 'noisy' and payload.noise_config:
            exec_circuit = apply_noise(exec_circuit, payload.noise_config)
        
        # STEP C: Run Simulation
        num_qubits = len(exec_circuit.all_qubits())
        # Heuristic: GPU if qubits > 20
        options = qsimcirq.QSimOptions(use_gpu=(num_qubits > 20))
        qsim_sim = qsimcirq.QSimSimulator(qsim_options=options)

        result = qsim_sim.run(exec_circuit, repetitions=payload.repetitions)

        # STEP D: Format Results
        # Optimization: qsim returns counters, we can just return that dict directly
        # but we need to convert keys (tuples) to strings for JSON.
        histogram = result.multi_measurement_histogram(keys=result.measurements.keys())
        
        return {
            "status": "success",
            "results": {"".join(str(b) for b in k): v for k, v in histogram.items()},
            "depth": len(exec_circuit),
            "backend": payload.target
        }

    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5001)