import requests
import cirq
import json

def run_test(name, circuit, repetitions=100):
    print(f"--- Running Test: {name} ---")
    payload = {
        "circuit": cirq.to_json(circuit),
        "repetitions": repetitions
    }
    try:
        response = requests.post("http://localhost:5001/run", json=payload)
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data['status']}")
            print(f"Backend Used: {data['backend']}")
            print(f"Qubit Count: {data['qubit_count']}")
            # Only print results if it's the small circuit to avoid spamming the console
            #if data['qubit_count'] < 5:
            print(f"Results: {data['results']}")
        else:
            print("Error:", response.text)
    except Exception as e:
        print(f"Connection failed: {e}")
    print("\n")

# Test 1: Small Circuit (Should use CPU)
q0, q1 = cirq.LineQubit.range(2)
small_circuit = cirq.Circuit(
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='m')
)

# Test 2: Large Circuit (Should attempt GPU)
# We create 21 qubits to trigger the >20 threshold
qubits = cirq.LineQubit.range(21)
large_circuit = cirq.Circuit(
    # Just apply Identity to all to verify count, plus one H on q0
    cirq.H(qubits[0]),
    [cirq.I(q) for q in qubits],
    cirq.measure(qubits, key='m')
)

if __name__ == "__main__":
    run_test("Small Circuit (<20 Qubits)", small_circuit)
    run_test("Large Circuit (>20 Qubits)", large_circuit)