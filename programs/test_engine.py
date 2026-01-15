import requests
import cirq
import json

# 1. Create a dummy circuit (Bell State)
q0, q1 = cirq.LineQubit.range(2)
circuit = cirq.Circuit(
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, key='q0'),
    cirq.measure(q1, key='q1')
)

# 2. Serialize it using Cirq's native JSON
circuit_json = cirq.to_json(circuit)

# 3. Define the payload
payload = {
    "circuit": circuit_json,
    "repetitions": 100
}

# 4. Send request to localhost
try:
    response = requests.post("http://localhost:5001/run", json=payload)
    print("Status Code:", response.status_code)
    print("Response Body:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Connection failed. Is server.py running?")
    print(e)