const myHeaders = new Headers();
myHeaders.append("Content-Type", "application/json");

const raw = JSON.stringify({
  "circuit": "{\n  \"cirq_type\": \"Circuit\",\n  \"moments\": [\n    {\n      \"cirq_type\": \"Moment\",\n      \"operations\": [\n        {\n          \"cirq_type\": \"GateOperation\",\n          \"gate\": {\n            \"cirq_type\": \"HPowGate\",\n            \"exponent\": 1.0,\n            \"global_shift\": 0.0\n          },\n          \"qubits\": [\n            {\n              \"cirq_type\": \"GridQubit\",\n              \"row\": 4,\n              \"col\": 4\n            }\n          ]\n        }\n      ]\n    },\n    {\n      \"cirq_type\": \"Moment\",\n      \"operations\": [\n        {\n          \"cirq_type\": \"GateOperation\",\n          \"gate\": {\n            \"cirq_type\": \"CXPowGate\",\n            \"exponent\": 1.0,\n            \"global_shift\": 0.0\n          },\n          \"qubits\": [\n            {\n              \"cirq_type\": \"GridQubit\",\n              \"row\": 4,\n              \"col\": 4\n            },\n            {\n              \"cirq_type\": \"GridQubit\",\n              \"row\": 4,\n              \"col\": 5\n            }\n          ]\n        }\n      ]\n    },\n    {\n      \"cirq_type\": \"Moment\",\n      \"operations\": [\n        {\n          \"cirq_type\": \"GateOperation\",\n          \"gate\": {\n            \"cirq_type\": \"MeasurementGate\",\n            \"num_qubits\": 2,\n            \"key\": \"result\",\n            \"invert_mask\": []\n          },\n          \"qubits\": [\n            {\n              \"cirq_type\": \"GridQubit\",\n              \"row\": 4,\n              \"col\": 4\n            },\n            {\n              \"cirq_type\": \"GridQubit\",\n              \"row\": 4,\n              \"col\": 5\n            }\n          ]\n        }\n      ]\n    }\n  ]\n}",
  "target": "generic",
  "simulation_type": "perfect"
});

const requestOptions = {
  method: "POST",
  headers: myHeaders,
  body: raw,
  redirect: "follow"
};

fetch("http://localhost:5001/run", requestOptions)
  .then((response) => response.text())
  .then((result) => console.log(result))
  .catch((error) => console.error(error));