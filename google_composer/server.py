import logging
import os
import uvicorn
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import cirq
import cirq_google
import qsimcirq
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QuantumEngine")

app = FastAPI(default_response_class=ORJSONResponse)

try:
    SYCAMORE_QUBITS = cirq_google.Sycamore.metadata.qubit_set
except AttributeError:
    SYCAMORE_QUBITS = set(cirq_google.Sycamore.qubits)

GATESET_MAP = {
    "sycamore": cirq_google.SycamoreTargetGateset(),
    "ionq": cirq.CZTargetGateset(allow_partial_czs=True),
    "linear": cirq.CZTargetGateset(allow_partial_czs=True),
}

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
    return_state_vector: bool = False

# OPTIMIZED: Global Simulator Instance (Thread-safe execution)
global_qsim_options = qsimcirq.QSimOptions(use_gpu=True) 
global_qsim_sim = qsimcirq.QSimSimulator(qsim_options=global_qsim_options)

@lru_cache(maxsize=1024)
def get_cached_transpiled_circuit(circuit_json: str, target_name: str) -> cirq.Circuit:
    circuit = cirq.read_json(json_text=circuit_json)
    if target_name == "generic":
        return circuit

    gateset = GATESET_MAP.get(target_name)
    if not gateset:
        raise ValueError(f"Unknown target: {target_name}")

    logger.info(f"Transpiling (Cache Miss) -> {target_name}")
    cirq.optimize_for_target_gateset(circuit, gateset=gateset)
    return circuit

def apply_noise(circuit: cirq.Circuit, noise_config: NoiseConfig) -> cirq.Circuit:
    if not noise_config: return circuit
    if noise_config.type == 'depolarizing':
        circuit = circuit.with_noise(cirq.depolarize(noise_config.p))
    if noise_config.readout_p > 0:
        circuit = circuit.with_noise(cirq.bit_flip(noise_config.readout_p))
    return circuit

@app.post("/run")
def run_circuit(payload: RunRequest):
    try:
        try:
            # OPTIMIZED: ALWAYS copy the cached circuit to prevent state mutation across threads
            base_circuit = get_cached_transpiled_circuit(payload.circuit, payload.target)
            exec_circuit = base_circuit.copy() 
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if payload.simulation_type == 'noisy' and payload.noise_config:
            exec_circuit = apply_noise(exec_circuit, payload.noise_config)
        
        # OPTIMIZED: Use the global simulator
        result = global_qsim_sim.run(exec_circuit, repetitions=payload.repetitions)
        
        if result.measurements:
            histogram = result.multi_measurement_histogram(keys=result.measurements.keys())
            formatted_results = {"".join(str(b) for b in k): v for k, v in histogram.items()}
        else:
            formatted_results = {}
        
        response_payload = {
            "status": "success",
            "results": formatted_results,
            "depth": len(exec_circuit),
            "backend": payload.target
        }

        if payload.return_state_vector:
            num_qubits = len(exec_circuit.all_qubits())
            if num_qubits > 12:
                raise HTTPException(
                    status_code=413, 
                    detail=f"State vector too large for {num_qubits} qubits. Max allowed is 12."
                )
            
            circuit_no_meas = cirq.Circuit(
                op for moment in exec_circuit for op in moment if not cirq.is_measurement(op)
            )
            
            sim_result = global_qsim_sim.simulate(circuit_no_meas)
            sv = sim_result.state_vector()
            
            flat_sv = np.empty(sv.size * 2, dtype=float)
            flat_sv[0::2] = sv.real
            flat_sv[1::2] = sv.imag
            
            response_payload["state_vector"] = flat_sv.tolist()

        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == '__main__':
    # OPTIMIZED: Use Environment variables for host/port bindings
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5001))
    uvicorn.run(app, host=host, port=port)