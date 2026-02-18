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
            "name": "Baseline (Generic)",
            "payload": {
                "circuit": circuit_json, 
                "target": "generic", 
                "simulation_type": "perfect"
            }
        },
        {
            "name": "Google Sycamore (Transpilation Check)",
            "payload": {
                "circuit": circuit_json, 
                "target": "sycamore", 
                "simulation_type": "perfect"
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
                }
            }
        },
        {
            "name": "IonQ / Linear Trap",
            "payload": {
                "circuit": circuit_json, 
                "target": "ionq", 
                "simulation_type": "perfect"
            }
        }
    ]

    print(f"Starting Test Suite on {SERVER_URL}...\n")

    for test in tests:
        name = test["name"]
        payload = test["payload"]
        
        print(f"=== TEST: {name} ===")
        print(f"Config: {payload['target']} | {payload['simulation_type']}")
        
        start = time.time()
        
        try:
            response = session.post(SERVER_URL, json=payload)
            response.raise_for_status() # Raises error for 4xx/5xx
            
            data = response.json()
            elapsed = round(time.time() - start, 3)

            # Success Output
            config = data.get('config', {})
            results = data.get('results', {})
            depth = data.get('depth')
            
            print(f"Status: Success ({elapsed}s)")
            print(f"Depth: {depth}")
            
            # Simplified Histogram Display
            sorted_res = dict(sorted(results.items(), key=lambda item: item[1], reverse=True))
            print(f"Results: {json.dumps(sorted_res)}")
            
        except requests.exceptions.ConnectionError:
            print("ERROR: Connection refused. Is server.py running?")
            break
        except requests.exceptions.HTTPError as e:
            print(f"HTTP ERROR: {e}")
            print(f"Details: {response.text}")
        except Exception as e:
            print(f" unexpected ERROR: {e}")
            
        print("-" * 40 + "\n")

if __name__ == "__main__":
    run_suite()