import os
import json
import logging
from flask import Flask, request, jsonify
import cirq
import qsimcirq

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QuantumEngine")

app = Flask(__name__)

def get_simulator():
    """
    Returns a qsim options object.
    Checks if GPU is actually usable by attempting a dummy run.
    """
    # 1. Option A: Simple Fix for Local Dev (Force CPU)
    # return qsimcirq.QSimOptions(use_gpu=False) 

    # 2. Option B: Robust Auto-detection
    try:
        # Create GPU options
        options = qsimcirq.QSimOptions(use_gpu=True)
        
        # Create a dummy simulator and run a tiny circuit to see if it crashes
        sim = qsimcirq.QSimSimulator(qsim_options=options)
        q0 = cirq.LineQubit(0)
        sim.run(cirq.Circuit(cirq.I(q0)), repetitions=1)
        
        logger.info("Simulator configured for GPU execution.")
        return options
    except Exception as e:
        # If the dummy run failed, fall back to CPU
        logger.warning(f"GPU check failed ({str(e)}). Falling back to CPU.")
        return qsimcirq.QSimOptions(use_gpu=False)
    
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ready", "engine": "qsimcirq"}), 200

@app.route('/run', methods=['POST'])
def run_circuit():
    """
    Expects a JSON payload:
    {
        "circuit": <string (json_serialized_cirq_circuit)>,
        "repetitions": <int>
    }
    """
    try:
        data = request.get_json()
        if not data or 'circuit' not in data:
            return jsonify({"error": "Missing 'circuit' payload"}), 400

        # 1. Deserialize the Circuit
        # We use cirq.read_json to parse the standard JSON format coming from the frontend/Go
        # For the prototype, we assume the string is passed directly. 
        # In production, we might read from a temp file or io stream.
        circuit = cirq.read_json(json_text=data['circuit'])
        
        # 2. Configure Simulator
        qsim_options = get_simulator()
        qsim_sim = qsimcirq.QSimSimulator(qsim_options=qsim_options)

        # 3. Execute
        repetitions = data.get('repetitions', 1000)
        
        # We assume the circuit has measurements. If not, results will be empty.
        result = qsim_sim.run(circuit, repetitions=repetitions)

        # 4. Format Output
        # We convert the Result object to a dictionary histogram for the frontend
        # output format: { "q0": { "0": 50, "1": 50 } }
        # Note: Cirq's result.data is a pandas DataFrame usually, but here we want raw counts.
        
        histogram = result.multi_measurement_histogram(keys=result.measurements.keys())
        
        # Convert tuple keys (measurements) to simple strings for JSON response
        # e.g. (0, 1) -> "01"
        json_histogram = {
            "".join(str(bit) for bit in k): v 
            for k, v in histogram.items()
        }

        return jsonify({
            "status": "success",
            "results": json_histogram,
            "backend": "qsim_gpu" if qsim_options.use_gpu else "qsim_cpu"
        })

    except Exception as e:
        logger.error(f"Execution Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run on port 5001 to avoid conflict with standard React/Go ports
    app.run(host='0.0.0.0', port=5001, debug=True)