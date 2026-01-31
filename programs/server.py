import os
import logging
from flask import Flask, request, jsonify
import cirq
import qsimcirq

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QuantumEngine")

app = Flask(__name__)

def get_simulator_options(prefer_gpu=False):
    """
    Returns qsim options.
    - If prefer_gpu is False: Returns CPU options immediately.
    - If prefer_gpu is True: Attempts to use GPU. If hardware check fails, falls back to CPU.
    """
    if not prefer_gpu:
        return qsimcirq.QSimOptions(use_gpu=False)

    # Attempt GPU initialization
    try:
        options = qsimcirq.QSimOptions(use_gpu=True)
        
        # Robust Check: Run a tiny dummy circuit to ensure GPU drivers are responding
        sim = qsimcirq.QSimSimulator(qsim_options=options)
        q_dummy = cirq.LineQubit(0)
        sim.run(cirq.Circuit(cirq.I(q_dummy),cirq.measure(q_dummy,key='m')), repetitions=1)
        
        logger.info("Hardware Check Passed: Using NVIDIA GPU.")
        return options
    except Exception as e:
        logger.warning(f"GPU requested but failed check ({str(e)}). Falling back to CPU.")
        return qsimcirq.QSimOptions(use_gpu=False)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ready", "engine": "qsimcirq"}), 200

@app.route('/run', methods=['POST'])
def run_circuit():
    try:
        data = request.get_json()
        if not data or 'circuit' not in data:
            return jsonify({"error": "Missing 'circuit' payload"}), 400

        # 1. Deserialize
        circuit = cirq.read_json(json_text=data['circuit'])
        
        # 2. Analyze Complexity
        # We count the unique qubits in the circuit
        num_qubits = len(circuit.all_qubits())
        
        # 3. Determine Strategy
        # Threshold: 20 qubits
        use_gpu_strategy = num_qubits > 20
        
        if use_gpu_strategy:
            logger.info(f"Circuit has {num_qubits} qubits. Attempting GPU execution.")
        else:
            logger.info(f"Circuit has {num_qubits} qubits. Using CPU execution (Threshold: >20).")

        # 4. Configure Simulator
        qsim_options = get_simulator_options(prefer_gpu=use_gpu_strategy)
        qsim_sim = qsimcirq.QSimSimulator(qsim_options=qsim_options)

        # 5. Execute
        repetitions = data.get('repetitions', 1000)
        result = qsim_sim.run(circuit, repetitions=repetitions)

        # 6. Format Output
        histogram = result.multi_measurement_histogram(keys=result.measurements.keys())
        json_histogram = {
            "".join(str(bit) for bit in k): v 
            for k, v in histogram.items()
        }

        # 7. Identify Backend Used for Response
        # This helps the frontend display "Ran on NVIDIA A100" vs "Ran on CPU"
        backend_used = "qsim_gpu" if qsim_options.use_gpu else "qsim_cpu"

        return jsonify({
            "status": "success",
            "results": json_histogram,
            "backend": backend_used,
            "qubit_count": num_qubits
        })

    except Exception as e:
        logger.error(f"Execution Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)