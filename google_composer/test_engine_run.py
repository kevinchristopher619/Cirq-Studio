import requests
import cirq
import json
import time

# --- SETUP ---
SERVER_URL = "http://localhost:5001/run"
# Define Circuit (Bell State on Sycamore Grid)
q0 = cirq.GridQubit(4, 4)
q1 = cirq.GridQubit(4, 5)
circuit = cirq.Circuit(
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
)

def run_suite():
    # Use a Session for connection pooling (Performance Optimization)
    session = requests.Session()
    
    # Pre-calculate circuit JSON once
    circuit_json = cirq.to_json(circuit)

    # --- TEST SCENARIOS (Data-Driven) ---
    tests = [
        {
            "name": "Baseline (Generic) WITH State Vector",
            "payload": {
                "circuit": circuit_json, 
                "target": "generic", 
                "simulation_type": "perfect",
                "return_state_vector": True
            }
        },
        {
            "name": "Google Sycamore (Transpilation Check)",
            "payload": {
                "circuit": circuit_json, 
                "target": "sycamore", 
                "simulation_type": "perfect",
                "return_state_vector": False
            }
        },
        {
            "name": "Sycamore (Noisy Simulation)",
            "payload": {
                "circuit": circuit_json, 
                "target": "sycamore", 
                "simulation_type": "noisy",
                "noise_config": {
                    "type": "depolarizing",
                    "p": 0.08,
                    "readout_p": 0.05
                },
                "return_state_vector": False
            }
        },
        {
            "name": "IonQ / Linear Trap",
            "payload": {
                "circuit": circuit_json, 
                "target": "ionq", 
                "simulation_type": "perfect",
                "return_state_vector": False
            }
        }
    ]

    print(f"Starting Test Suite on {SERVER_URL}...\n")

    for test in tests:
        name = test["name"]
        payload = test["payload"]
    
        print(f"=== TEST: {name} ===")
        print(f"Target: {payload['target']} | Sim Type: {payload['simulation_type']}")

        start = time.time()
        
        try:
            response = session.post(SERVER_URL, json=payload)
            response.raise_for_status() # Raises error for 4xx/5xx
            
            data = response.json()
            elapsed = round(time.time() - start, 3)

            # Success Output
            results = data.get('results', {})
            depth = data.get('depth')
            backend_used = data.get('backend')
            state_vector = data.get('state_vector')
            
            print(f"Status: Success ({elapsed}s)")
            print(f"Backend Routed: {backend_used} | Circuit Depth: {depth}")
            
            # Simplified Histogram Display
            if results:
                sorted_res = dict(sorted(results.items(), key=lambda item: item[1], reverse=True))
                print(f"Histogram: {json.dumps(sorted_res)}")
            else:
                print("Histogram: None (No measurements found or returned)")
                
            # State Vector Display (Prevent terminal flooding)
            if state_vector:
                sv_length = len(state_vector)
                # Show first 4 elements (real, imag, real, imag) as a preview
                preview = [round(x, 4) for x in state_vector[:4]]
                print(f"State Vector: Received array of {sv_length} floats.")
                print(f"SV Preview (First 2 Amplitudes): {preview} ...")
            
        except requests.exceptions.ConnectionError:
            print("ERROR: Connection refused. Is server.py running?")
            break
        except requests.exceptions.HTTPError as e:
            print(f"HTTP ERROR: {e}")
            print(f"Details: {response.text}")
        except Exception as e:
            print(f"Unexpected ERROR: {e}")
            
        print("-" * 50 + "\n")

if __name__ == "__main__":
    run_suite()