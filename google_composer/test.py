import cirq
import json 

q0 = cirq.GridQubit(4, 4)
q1 = cirq.GridQubit(4, 5)
circuit = cirq.Circuit(
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
)

jscir = cirq.to_json(circuit)
jcir = json.loads(jscir)
print(jcir)